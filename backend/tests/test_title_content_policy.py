"""取消字面删词、可选营销和旧执行状态恢复的行为回归。"""
import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.ai_providers import ProviderError
from app.models import ProductDraft, Role
from app.title_models import TitleKeyword, TitleRecord
from app.title_service import (adopt_record, choose_keywords, content_phrases, count_adopted_keywords,
                               generate_record, match_keywords, validate_localized_title)
from tests import test_title_length as length_tests

MY_180 = length_tests.MY_180
keyword = length_tests.keyword


class TitleContentPolicyTests(unittest.IsolatedAsyncioTestCase):
    setUp = length_tests.TitleLengthGenerationTests.setUp
    generate = length_tests.TitleLengthGenerationTests.generate

    async def test_other_tag_subphrases_do_not_delete_confirmed_descriptions(self):
        for whole, part, other_tag in (
                ('Pinggang Elastik', 'Elastik', '材质'),
                ('Kolar Linen', 'Linen', '材质'),
                ('Corak Sulaman', 'Sulaman', '工艺')):
            with self.subTest(whole=whole):
                # 每组独立词库，不让固定词面成为规则例外。
                words = [keyword(1, whole, tag='结构设计'), keyword(2, part, tag=other_tag)]
                body = MY_180 + ' ' + whole
                result, _ = await self.generate([body] * 4, supply=True, words=words, locked=[1], forbidden=[part])
                self.assertEqual(result['title'], body)
                record = self.db.get(TitleRecord, self.record_id)
                self.assertNotIn('forbidden_phrases', record.snapshot)
                self.assertTrue(all(row['raw_title'] == row['cleaned_title']
                    for row in record.snapshot['title_diagnostics']['attempts']))
                # 下一组需要复用相同测试 ID，清理测试记录和关键词即可。
                self.db.delete(record)
                for word in words:
                    self.db.delete(self.db.get(TitleKeyword, word['id']))
                self.db.commit()

    async def test_known_material_function_craft_and_brand_words_are_not_rejected(self):
        body = MY_180 + ' Kapas Waterproof'
        result, _ = await self.generate([body] * 4, supply=True)
        self.assertEqual(result['title'], body)

    def test_language_checks_use_script_and_format_instead_of_word_lists(self):
        for site, language in (('MY', 'ms'), ('ID', 'id')):
            body = 'Busana Modis Kekinian Menawan Eksklusif'
            self.assertEqual(validate_localized_title(body, site=site, language=language), body)
        for invalid in ('1' * 40, '中文' * 20, 'Busana Modis\nKekinian Menawan Eksklusif',
                        'Busana Modis **Kekinian** Menawan Eksklusif'):
            with self.assertRaises(ProviderError):
                validate_localized_title(invalid)

    async def test_one_optional_marketing_word_can_be_omitted_without_failure(self):
        words = [keyword(1, 'Pilihan Popular', tag='营销修饰'), keyword(2, 'Gaya Istimewa', tag='营销修饰')]
        result, model = await self.generate([MY_180] * 4, supply=True, words=words)
        for call in model.await_args_list:
            payload = call.args[2]
            self.assertEqual(len(payload['optional_marketing_phrases']), 1)
            self.assertFalse(set(payload['optional_marketing_phrases']) & set(payload['required_phrases']))
        record = self.db.get(TitleRecord, result['generation_id'])
        self.assertEqual(record.state, 'generated')
        self.assertEqual(record.selected_keywords, [])
        count_adopted_keywords(self.db, record, result['title'])
        self.db.commit()
        self.assertEqual(self.db.get(TitleKeyword, 1).adopted_count, 0)
        self.assertEqual(self.db.get(TitleKeyword, 2).adopted_count, 0)
        for row in record.snapshot['title_diagnostics']['attempts']:
            self.assertEqual(row['missing_phrases']['cleaned'], [])
            self.assertEqual(row['omitted_marketing_phrases'], row['optional_marketing_phrases'])

    async def test_locked_marketing_can_be_omitted_and_blocks_extra_marketing(self):
        words = [keyword(1, 'Pilihan Popular', tag='营销修饰'), keyword(2, 'Gaya Istimewa', tag='营销修饰')]
        result, model = await self.generate([MY_180], supply=True, words=words, locked=[1])
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(model.await_count, 1)
        for row in self.db.get(TitleRecord, self.record_id).snapshot['title_diagnostics']['attempts']:
            self.assertEqual([word['id'] for word in row['selected_keywords']], [1])
            self.assertEqual(row['optional_marketing_phrases'], [])

    def test_exact_duplicate_required_phrases_preserve_all_keyword_references(self):
        words = [keyword(1, 'Pinggang Elastik', tag='结构设计'), keyword(2, 'pinggang elastik', tag='细节元素')]
        snapshot = {'supply': True, 'locked_keyword_ids': [1, 2]}
        chosen = choose_keywords(snapshot, words, {}, core='Gaun')
        self.assertEqual({word['id'] for word in chosen}, {1, 2})
        self.assertEqual(len(content_phrases('Gaun', chosen)), 2)

    def test_legacy_forbidden_priority_and_ids_do_not_exclude_eligible_words(self):
        word = keyword(1, 'Pilihan Popular', tag='营销修饰', priority='forbidden')
        snapshot = {'category': '连衣裙', 'keyword_policy_version': 3, 'keywords': [word],
                    'locked_keyword_ids': [], 'forbidden_keyword_ids': [1]}
        self.assertEqual(match_keywords(snapshot, {'attributes': []}), [word])
        self.assertEqual(choose_keywords(snapshot, [word], {}), [word])

    async def test_resume_relimits_marketing_and_discards_obsolete_feedback_without_resetting_attempts(self):
        words = [keyword(1, 'Pilihan Popular', tag='营销修饰'), keyword(2, 'Gaya Istimewa', tag='营销修饰')]
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([], supply=True, words=words,
                response_callback=AsyncMock(side_effect=asyncio.CancelledError()))
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        state.update(selected=words, feedback='标题包含未选定的工艺词：example', last_error='旧禁用规则')
        record.snapshot = {**record.snapshot, 'keyword_policy_version': 2,
                           'forbidden_phrases': ['Gaun'], 'supply_generation': state}
        self.db.commit()
        model = AsyncMock(return_value={'title': MY_180})
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'key')
        self.assertEqual(result['attempts'], 2)
        payload = model.await_args.args[2]
        self.assertEqual(payload['feedback'], '')
        self.assertEqual(payload['core_category'], 'Gaun')
        self.assertEqual(len(payload['optional_marketing_phrases']), 1)
        self.db.refresh(record)
        self.assertEqual(record.snapshot['keyword_policy_version'], 4)
        self.assertNotIn('forbidden_phrases', record.snapshot)
        self.assertEqual(record.snapshot['title_diagnostics']['attempts'][0]['status'], 'interrupted')

    async def test_recovered_best_candidate_does_not_require_exact_core_phrase(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([], supply=True,
                response_callback=AsyncMock(side_effect=asyncio.CancelledError()))
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        title = MY_180.replace('Gaun', 'Busana')
        state['best'] = {'title': title, 'warnings': ['按首图描述，请核对其他 SKU'], 'keywords': [], 'score': [False, 0]}
        record.snapshot = {**record.snapshot, 'keyword_policy_version': 2, 'supply_generation': state}
        self.db.commit()
        model = AsyncMock(return_value={'title': MY_180})
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'key')
        self.assertEqual(result['title'], title)
        self.assertEqual(result['attempts'], 1)
        model.assert_not_awaited()
        self.assertNotIn('按首图描述，请核对其他 SKU', result['warnings'])

    async def test_manual_case_only_edit_does_not_require_selected_brand_spelling(self):
        brand = keyword(1, 'Acme', tag='品牌')
        body = MY_180 + ' Acme'
        result, _ = await self.generate([body] * 4, words=[brand], brand=brand)
        draft = ProductDraft(company_id=1, created_by=1, template_id=1,
            title=body.replace('Acme', 'acme'), image_urls=['https://img.example/1.png'])
        user = SimpleNamespace(id=1, company_id=1, role=Role.MEMBER)
        adopt_record(self.db, draft, user, result['generation_id'])

    async def test_manual_edit_can_rephrase_core_and_omit_selected_brand(self):
        brand = keyword(1, 'Acme', tag='品牌')
        body = MY_180 + ' Acme'
        result, _ = await self.generate([body] * 4, words=[brand], brand=brand)
        draft = ProductDraft(company_id=1, created_by=1, template_id=1,
            title=MY_180.replace('Gaun', 'Busana'), image_urls=['https://img.example/1.png'])
        user = SimpleNamespace(id=1, company_id=1, role=Role.MEMBER)
        adopt_record(self.db, draft, user, result['generation_id'])
        self.db.flush()
        manual = self.db.query(TitleRecord).filter_by(source='manual').one()
        self.assertEqual(manual.title, draft.title)
