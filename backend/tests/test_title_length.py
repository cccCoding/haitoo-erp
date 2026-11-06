"""词库标题软长度目标、选词预算及多次成文的结果保留。"""
import asyncio
import copy
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ai_providers import ProviderError
from app.database import Base
from app import supply_title_rules as supply_rules
from app.title_models import TitleKeyword, TitleMarket, TitleRecord, TitleTask
from app.title_service import (choose_keywords, create_record, generate_record, match_keywords,
                               prepare_supply_compression)


MY_180 = ('Gaun Wanita Dewasa Lengan Panjang Corak Bunga Potongan Longgar Labuh Leher Bulat '
          'Dengan Poket Sisi Butang Hadapan Pinggang Berikat Untuk Pakaian Harian Gaya Santai Warna Biru Cerah')
MY_220 = MY_180 + ' Corak Daun Mini Dengan Lipatan Di Depan'
MY_230 = MY_180 + ' Corak Daun Mini Dengan Perincian Di Bahagian Sisi'
MY_231 = MY_180 + ' Corak Daun Kecil Dengan Perincian Di Bahagian Sisi'
ID_182 = ('Daster Wanita Dewasa Lengan Panjang Motif Bunga Potongan Longgar Leher Bulat '
          'Dengan Saku Samping Kancing Depan Pinggang Bertali Untuk Pakaian Harian Gaya Santai Warna Biru Motif Daun')
SHORT = 'Gaun Wanita Lengan Panjang Corak Bunga'


def keyword(identity, phrase, *, tag='细节元素', **extra):
    return {'id': identity, 'phrase': phrase, 'translation': phrase, 'tag': tag,
            'categories': ['连衣裙'], 'synonyms': [], 'conflicts': [],
            'priority': 'normal', 'selected_count': 0, **extra}


class TitleKeywordBudgetTests(unittest.TestCase):
    def snapshot(self, **extra):
        return {'category': '连衣裙', 'category_localized_name': 'Gaun',
                'locked_keyword_ids': [], 'forbidden_keyword_ids': [], **extra}

    def test_distinct_confirmed_details_are_not_randomly_skipped_or_limited_to_eight(self):
        phrases = ['poket sisi', 'butang hadapan', 'zip belakang', 'pinggang berikat',
                   'lipatan', 'manset', 'renda', 'sulaman', 'tali', 'lapisan']
        words = [keyword(i, phrase) for i, phrase in enumerate(phrases, 1)]
        facts = [{'tag': word['tag'], 'value': word['translation'], 'localized_value': word['phrase']}
                 for word in words]
        snapshot = self.snapshot(keywords=words)
        candidates = match_keywords(snapshot, {'attributes': facts})
        for turn in range(8):
            self.assertEqual({w['id'] for w in choose_keywords(snapshot, candidates, {}, turn, facts=facts)},
                             set(range(1, 11)))

    def test_budget_reserves_core_and_skips_long_optional_word_but_keeps_shorter_words(self):
        # Gaun + 空格 + 166 字符 + 空格 + 8 字符 = 180。
        words = [keyword(1, 'a' * 166), keyword(2, 'bbbbbbbbb'), keyword(3, 'cccccccc')]
        for supply, expected in ((False, [1, 3]), (True, [2, 3])):
            with self.subTest(supply=supply):
                result = choose_keywords(self.snapshot(supply=supply), words, {1: 0, 2: 1, 3: 2})
                self.assertEqual([w['id'] for w in result], expected)

    def test_supply_initial_optional_budget_is_170_including_core_and_spaces(self):
        snapshot = self.snapshot(supply=True)
        self.assertEqual([word['id'] for word in choose_keywords(snapshot, [keyword(1, 'a' * 165)], {})], [1])
        self.assertEqual(choose_keywords(snapshot, [keyword(1, 'a' * 166)], {}), [])
        snapshot['locked_keyword_ids'] = [1]
        self.assertEqual([word['id'] for word in choose_keywords(snapshot, [keyword(1, 'a' * 166)], {})], [1])

    def test_required_words_and_selected_material_survive_soft_budget(self):
        words = [keyword(1, 'a' * 150), keyword(2, 'b' * 150), keyword(3, 'kapas', tag='材质'),
                 keyword(4, 'linen', tag='材质'), keyword(5, 'poket')]
        snapshot = self.snapshot(locked_keyword_ids=[1, 2], selected_material_keyword=words[2])
        result = choose_keywords(snapshot, words, {})
        self.assertEqual({w['id'] for w in result}, {1, 2, 3})

    def test_synonyms_shared_facts_and_conflicts_are_not_selected_together(self):
        words = [keyword(1, 'poket', translation='口袋'), keyword(2, 'saku', translation='口袋'),
                 keyword(3, 'poket sisi', synonyms=['poket']), keyword(4, 'butang', conflicts=[1])]
        facts = [{'tag': '细节元素', 'value': '口袋', 'localized_value': 'poket'}]
        result = choose_keywords(self.snapshot(), words, {1: 0, 2: 1, 3: 2, 4: 3}, facts=facts)
        self.assertEqual([w['id'] for w in result], [1])
        with self.assertRaises(ProviderError):
            choose_keywords(self.snapshot(locked_keyword_ids=[1, 2]), words, {}, facts=facts)

    def test_priority_and_evidence_frequency_still_precede_usage_tiebreaks(self):
        words = [keyword(1, 'poket', synonyms=['saku'], evidence_frequency=9),
                 keyword(2, 'saku', evidence_frequency=1)]
        self.assertEqual(choose_keywords(self.snapshot(), words, {})[0]['id'], 1)
        words[1]['priority'] = 'preferred'
        self.assertEqual(choose_keywords(self.snapshot(), words, {})[0]['id'], 2)

    def test_supply_protected_content_over_170_has_no_optional_additions(self):
        words = [keyword(1, 'a' * 166), keyword(2, 'Gaun'), keyword(3, 'Biru')]
        chosen = choose_keywords(self.snapshot(supply=True, locked_keyword_ids=[1]), words, {})
        self.assertEqual([word['id'] for word in chosen], [1])

    def test_compression_scales_to_actual_overflow_and_preserves_necessary_content(self):
        self.assertEqual(supply_rules.content_characters(['Gaun', 'GAUN', '  Kapas ']), 10)
        for length, expected in ((236, 136), (264, 122), (362, 89)):
            self.assertEqual(supply_rules.compression_budget(1, 170, 40, length), expected)
        self.assertEqual(supply_rules.compression_budget(1, 170, 150, 362), 150)
        self.assertEqual(supply_rules.compression_budget(2, 136, 40, 264), 92)
        self.assertEqual(supply_rules.compression_budget(3, 92, 40, 264), 40)


class TitleLengthGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.company_sequence = 0
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    async def generate(self, answers, *, supply=False, site='MY', history=None, forbidden=(), words=(),
                       locked=(), material=None, craft=None, brand=None, response_callback=None):
        core = 'Daster' if site == 'ID' else 'Gaun'
        self.company_sequence += 1
        market = TitleMarket(company_id=self.company_sequence, platform='TikTok', site=site,
                             language='id' if site == 'ID' else 'ms')
        self.db.add(market)
        self.db.flush()
        snapshot = {'template_id': 1, 'category': '连衣裙', 'category_localized_name': core,
                    'platform': 'TikTok', 'site': site, 'language': market.language,
                    'attributes': {}, 'keywords': list(words), 'locked_keyword_ids': list(locked),
                    'forbidden_keyword_ids': [], 'forbidden_phrases': list(forbidden)}
        if material:
            snapshot['selected_material_keyword'] = material
        if craft or brand:
            snapshot['confirmed_choices_version'] = 1
            for kind, word in (('craft', craft), ('brand', brand)):
                if word:
                    snapshot[f'selected_{kind}_keyword'] = word
        for word in words:
            self.db.add(TitleKeyword(id=word['id'], market_id=market.id, code=str(word['id']),
                identity_hash=str(word['id']).zfill(64), phrase=word['phrase'], translation=word['translation'],
                tag=word['tag'], categories=word['categories']))
        record = create_record(self.db, market, 1, snapshot, 'https://img.example/1.png', 'length-test', supply=supply)
        record.facts = {'attributes': [
            {'tag': '品类', 'value': '连衣裙', 'localized_value': core, 'source': 'manual'},
            {'tag': '细节元素', 'value': '已确认款式描述', 'localized_value':
             ID_182 if site == 'ID' else MY_231 + ' ' + MY_220, 'source': 'manual'},
            {'tag': '结构设计', 'value': '长袖', 'localized_value': 'Lengan Panjang', 'source': 'manual'},
            {'tag': '颜色', 'value': '蓝色', 'localized_value': 'Biru', 'source': 'manual'},
        ], 'warnings': []}
        record.facts['attributes'].extend({'tag': word['tag'], 'value': word['translation'],
            'localized_value': word['phrase'], 'source': 'manual'} for word in words)
        if history:
            self.db.add(TitleRecord(market_id=market.id, user_id=1, template_id=1, request_key='history',
                category='连衣裙', image_url=record.image_url, snapshot=snapshot, title=history,
                selected_keywords=[], adopted_at=datetime.utcnow(), state='adopted'))
        self.db.commit()
        self.record_id = record.id
        sequence = [item if isinstance(item, BaseException) else {'title': item} for item in answers]
        model = AsyncMock(side_effect=response_callback or sequence)
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
            # 已完成的记录重放不调用模型。
            self.assertEqual(await generate_record(self.db, record.id, 'test-key'), result)
        return result, model

    async def test_short_title_is_expanded_with_previous_title_count_and_unused_facts(self):
        result, model = await self.generate([SHORT, MY_180])
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['attempts'], 2)
        retry = model.await_args.args[2]
        self.assertEqual(retry['previous_title'], SHORT)
        self.assertEqual(retry['character_count'], len(SHORT))
        self.assertIn('Biru', [f['localized_value'] for f in retry['unused_confirmed_attributes']])
        self.assertNotIn('Lengan Panjang', [f['localized_value'] for f in retry['unused_confirmed_attributes']])
        self.assertIn(str(len(SHORT)), retry['feedback'])
        self.assertEqual((retry['target_minimum'], retry['target_maximum'], retry['maximum']), (180, 230, 255))
        self.assertIn('Never repeat phrases', model.await_args.args[1])

    async def test_persistently_short_title_returns_silently_with_four_attempts(self):
        result, model = await self.generate([SHORT] * 4)
        self.assertEqual((result['title'], result['state'], result['attempts']), (SHORT, 'generated', 4))
        self.assertEqual(model.await_count, 4)
        self.assertFalse(any('长度' in warning or '字符' in warning for warning in result['warnings']))

    async def test_regular_target_boundaries_and_supply_body_boundary(self):
        for title, length, supply in ((MY_180, 180, False), (MY_230, 230, False), (MY_230, 230, True)):
            with self.subTest(length=length, supply=supply):
                self.assertEqual(len(title), length)
                result, model = await self.generate([title] * (4 if supply else 1), supply=supply)
                self.assertEqual(result['title'], title)
                self.assertEqual(model.await_count, 4 if supply else 1)
                if supply:
                    self.assertEqual(model.await_args.args[2]['target_maximum'], 200)
                    self.assertEqual(len(result['title'] + ' - L01'), 236)

    async def test_over_target_but_within_hard_limit_is_compressed(self):
        result, model = await self.generate([MY_231, MY_230])
        self.assertEqual(result['title'], MY_230)
        self.assertEqual(model.await_count, 2)
        self.assertIn('231', model.await_args.args[2]['feedback'])

    async def test_best_out_of_range_title_survives_worse_titles_and_provider_failure(self):
        result, _ = await self.generate([SHORT, MY_231, SHORT, ProviderError('temporary failure')])
        self.assertEqual(result['title'], MY_231)
        self.assertEqual(result['attempts'], 4)
        self.assertEqual(self.db.get(TitleRecord, self.record_id).title, MY_231)

    async def test_identical_adopted_title_finishes_immediately_without_history_prompt(self):
        result, model = await self.generate([MY_180], history=MY_180)
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(model.await_count, 1)
        self.assertNotIn('avoid', model.await_args.args[2])
        self.assertNotIn('similarity', str(model.await_args).lower())
        self.assertFalse(any('高度相似' in warning for warning in result['warnings']))

    async def test_identical_supply_title_finishes_immediately(self):
        result, model = await self.generate([MY_180], supply=True, history=MY_180)
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(model.await_count, 1)
        self.assertNotIn('avoid', model.await_args.args[2])

    async def test_identical_title_in_same_batch_does_not_trigger_another_call(self):
        await self.generate([MY_180])
        record = self.db.get(TitleRecord, self.record_id)
        task = TitleTask(market_id=record.market_id, user_id=1, kind='batch', state='running',
            snapshot={}, request_key='same-batch', request_hash='same-batch')
        self.db.add(task); self.db.flush()
        record.task_id, record.title, record.attempts = task.id, None, 0
        record.state = 'queued'
        self.db.add(TitleRecord(market_id=record.market_id, user_id=1, template_id=1,
            task_id=task.id, request_key='same-batch-history', category=record.category,
            image_url=record.image_url, snapshot={}, title=MY_180, state='generated'))
        self.db.commit()
        model = AsyncMock(return_value={'title': MY_180})
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(model.await_count, 1)
        self.assertFalse(any('高度相似' in warning for warning in result['warnings']))

    async def test_equal_length_scores_keep_first_candidate_and_its_metadata(self):
        reordered = 'Gaun Lengan Panjang Wanita Corak Bunga'
        self.assertEqual(len(reordered), len(SHORT))
        result, _ = await self.generate([SHORT, reordered, ProviderError('failed'), reordered])
        self.assertEqual(result['title'], SHORT)
        self.assertEqual(result['character_count'], len(SHORT))
        self.assertEqual(result['attempts'], 4)

    async def test_unconfirmed_material_does_not_short_circuit_length_attempts(self):
        result, model = await self.generate([SHORT, SHORT + ' Kapas', SHORT + ' Kalis Air', ProviderError('failed')])
        self.assertEqual(result['title'], SHORT + ' Kalis Air')
        self.assertEqual(result['attempts'], 4)
        self.assertEqual(model.await_count, 4)

    async def test_supply_preserves_body_and_ignores_legacy_forbidden_words(self):
        body = MY_220 + ' Kapas'
        result, model = await self.generate([body] * 4, supply=True, forbidden=['Kapas'])
        self.assertEqual(result['title'], body)
        self.assertEqual(result['character_count'], len(body))
        self.assertEqual(model.await_count, 4)

    async def test_indonesian_titles_use_same_soft_length_policy(self):
        short = 'Daster Wanita Lengan Panjang Motif Bunga'
        result, model = await self.generate([short, ID_182], site='ID')
        self.assertEqual(result['title'], ID_182)
        self.assertEqual((result['site'], result['language']), ('ID', 'id'))
        self.assertIn('Bahasa Indonesia', model.await_args.args[1])

    async def test_supply_overlong_retry_preserves_words_and_explains_exact_length(self):
        for site, title in (('MY', MY_180), ('ID', ID_182)):
            with self.subTest(site=site):
                result, model = await self.generate([title + ' X' * 40, title], supply=True, site=site)
                first, retry = [call.args[2] for call in model.await_args_list]
                self.assertEqual(first['selected'], retry['selected'])
                self.assertEqual(retry['character_count'], len(title) + 80)
                self.assertIn(str(len(title) + 80 - 230), retry['feedback'])
                self.assertIn('180-200', retry['feedback'])
                self.assertEqual(result['attempts'], 2)
                self.assertEqual(result['title'], title)

    async def test_supply_reduces_optional_words_after_first_overlong_response(self):
        words = [keyword(1, 'Gaun', tag='品类'), keyword(2, 'Lengan Panjang', tag='结构设计'),
                 keyword(3, 'kapas', tag='材质'), keyword(4, 'Corak Bunga', tag='图案')]
        overlong = MY_180 + ' X' * 40
        result, model = await self.generate([overlong, overlong, MY_180 + ' Kapas'], supply=True,
            words=words, locked=[2], material=words[2])
        selections = [[w['id'] for w in call.args[2]['selected']] for call in model.await_args_list]
        self.assertEqual(set(selections[1]), {1, 2, 3})
        self.assertEqual(set(selections[2]), {1, 2, 3})
        self.assertNotIn('Corak Bunga', model.await_args.args[2]['required_phrases'])
        state = self.db.get(TitleRecord, self.record_id).snapshot['supply_generation']
        self.assertEqual(state['removed_keyword_ids'], [4])
        self.assertEqual(result['attempts'], 3)
        counts = {row.id: row.selected_count for row in self.db.scalars(select(TitleKeyword))}
        self.assertEqual(counts, {1: 3, 2: 3, 3: 3, 4: 1})

    async def test_supply_removes_multiple_optional_words_and_finishes_second_call(self):
        phrases = ['Lengan Panjang', 'Corak Bunga', 'Potongan Longgar', 'Labuh', 'Leher Bulat',
                   'Poket Sisi', 'Butang Hadapan', 'Pinggang Berikat', 'Pakaian Harian', 'Warna Biru Cerah',
                   'Dengan Lipatan Di Depan Rapi']
        words = [keyword(i, phrase) for i, phrase in enumerate(phrases, 1)]
        responses = []
        def answer(_key, _instructions, data, **_kwargs):
            title = MY_180 + ' X' * 91 if not responses else ' '.join(data['required_phrases'])
            responses.append(title)
            return {'title': title}

        result, model = await self.generate([], supply=True, words=words, response_callback=answer)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['title'], responses[1])
        first, retry = [call.args[2] for call in model.await_args_list]
        self.assertEqual(first['required_phrase_characters'], 170)
        self.assertEqual(retry['keyword_budget'], 89)
        self.assertLessEqual(retry['required_phrase_characters'], 89)
        self.assertGreater(len(retry['omitted_optional_phrases']), 1)
        self.assertIn('Compression mode', model.await_args.args[1])
        self.assertNotIn('expand it using unused_confirmed_attributes', model.await_args.args[1])
        self.assertNotIn('unused_confirmed_attributes', retry)
        self.assertIn('Facts are evidence for truth checking only', model.await_args.args[1])
        self.assertTrue(all(any(fact['localized_value'] == phrase for fact in retry['facts'])
                            for phrase in retry['omitted_optional_phrases']))
        state = self.db.get(TitleRecord, self.record_id).snapshot['supply_generation']
        self.assertEqual(len(state['compression_history']), 1)
        removed_ids = set(state['removed_keyword_ids'])
        counts = {row.id: row.selected_count for row in self.db.scalars(select(TitleKeyword))}
        self.assertTrue(all(counts[identity] == 1 for identity in removed_ids))
        self.assertTrue(all(counts[word['id']] == 2 for word in retry['selected']))

    async def test_supply_compression_accepts_full_valid_range_for_both_markets(self):
        for site, core in (('MY', 'Gaun'), ('ID', 'Daster')):
            for length in (25, 179, 200, 230):
                with self.subTest(site=site, length=length):
                    title = core + ' ' + 'a' * (length - len(core) - 1)
                    result, model = await self.generate([core + ' ' + 'a' * 270, title], supply=True, site=site)
                    self.assertEqual(result['title'], title)
                    self.assertEqual(result['attempts'], 2)
                    self.assertEqual(model.await_count, 2)

    async def test_supply_second_overlong_response_reduces_budget_again_and_finishes_third_call(self):
        words = [keyword(i, phrase) for i, phrase in enumerate([
            'Lengan Panjang', 'Corak Bunga', 'Potongan Longgar', 'Labuh', 'Leher Bulat', 'Poket Sisi',
            'Butang Hadapan', 'Pinggang Berikat', 'Pakaian Harian', 'Warna Biru Cerah',
            'Dengan Lipatan Di Depan Rapi'], 1)]
        responses = [MY_180 + ' X' * 28, MY_180 + ' X' * 42]
        def answer(_key, _instructions, data, **_kwargs):
            return {'title': responses.pop(0) if responses else ' '.join(data['required_phrases'])}

        result, model = await self.generate([], supply=True, words=words, response_callback=answer)
        first, second, third = [call.args[2] for call in model.await_args_list]
        self.assertEqual(first['required_phrase_characters'], 170)
        self.assertEqual(second['keyword_budget'], 136)
        self.assertEqual(third['keyword_budget'], second['required_phrase_characters'] * 180 // 264)
        self.assertLess(third['required_phrase_characters'], second['required_phrase_characters'])
        self.assertEqual(result['attempts'], 3)
        self.assertLessEqual(result['character_count'], 230)
        state = self.db.get(TitleRecord, self.record_id).snapshot['supply_generation']
        history = state['compression_history']
        self.assertEqual([item['response_attempt'] for item in history], [1, 2])
        self.assertTrue(set(history[0]['removed_keyword_ids']).isdisjoint(history[1]['removed_keyword_ids']))

    async def test_supply_compression_rejects_24_and_231_then_finishes_third_call(self):
        for length in (24, 231):
            with self.subTest(length=length):
                result, model = await self.generate([MY_231, 'Gaun ' + 'a' * (length - 5), SHORT], supply=True)
                self.assertEqual(result['attempts'], 3)
                self.assertEqual(result['title'], SHORT)
                stages = [call.args[2]['compression_level'] for call in model.await_args_list]
                self.assertEqual(stages, [0, 1, 1 if length == 24 else 2])

    async def test_supply_compression_protects_core_manual_choices_and_legacy_locked_words(self):
        words = [keyword(1, 'Gaun', tag='品类'), keyword(2, 'Lengan Panjang'), keyword(3, 'kapas', tag='材质'),
                 keyword(4, 'sulaman', tag='工艺'), keyword(5, 'Acme', tag='品牌'), keyword(6, 'Corak Bunga')]
        title = 'Gaun Lengan Panjang kapas sulaman Acme'
        result, model = await self.generate([title + ' X' * 150] * 3 + [title], supply=True, words=words,
            locked=[2], material=words[2], craft=words[3], brand=words[4])
        self.assertEqual(result['attempts'], 4)
        self.assertEqual(result['title'], title)
        self.assertEqual({word['id'] for word in model.await_args.args[2]['selected']}, {1, 2, 3, 4, 5})
        self.assertEqual(model.await_args.args[2]['compression_level'], 3)

    async def test_supply_non_length_failures_do_not_advance_compression(self):
        result, model = await self.generate([MY_231, ProviderError('模型超时'), 'Baju\n' + 'a' * 30, SHORT], supply=True)
        self.assertEqual(result['attempts'], 4)
        payloads = [call.args[2] for call in model.await_args_list]
        self.assertEqual([data['compression_level'] for data in payloads], [0, 1, 1, 1])
        self.assertEqual(len({data['keyword_budget'] for data in payloads[1:]}), 1)
        state = self.db.get(TitleRecord, self.record_id).snapshot['supply_generation']
        self.assertEqual(len(state['compression_history']), 1)

    async def test_supply_compression_uses_cleaned_length_and_logs_success(self):
        with self.assertLogs('app.title_service', level='INFO') as logs:
            result, model = await self.generate([MY_231 + ' Kapas', SHORT], supply=True)
        retry = model.await_args.args[2]
        self.assertEqual(retry['character_count'], len(MY_231 + ' Kapas'))
        state = self.db.get(TitleRecord, self.record_id).snapshot['supply_generation']
        self.assertEqual(state['compression_history'][0]['previous_length'], len(MY_231 + ' Kapas'))
        self.assertEqual(result['attempts'], 2)
        self.assertTrue(any('货盘标题成文完成' in line and 'attempts=2' in line and 'compression_level=1' in line
                            for line in logs.output))

    async def test_supply_preserves_overlapping_necessary_phrases_beyond_soft_budget(self):
        shared = 'Corak Bunga ' * 9
        phrases = [(shared + 'Wanita').strip(), ('Gaun ' + shared).strip()]
        words = [keyword(i, phrase) for i, phrase in enumerate(phrases, 1)]
        title = 'Gaun ' + shared + 'Wanita'
        self.assertGreater(supply_rules.content_characters(['Gaun', *phrases]), 230)
        self.assertLess(len(title), 230)
        result, model = await self.generate([title + ' X' * 100, title], supply=True, words=words, locked=[1, 2])
        self.assertEqual(result['title'], title)
        retry = model.await_args.args[2]
        self.assertEqual({word['id'] for word in retry['selected']}, {1, 2})
        self.assertGreater(retry['keyword_budget'], 170)

    async def test_supply_keeps_best_title_and_selection_across_interruption(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([MY_230, asyncio.CancelledError()], supply=True)
        record = self.db.get(TitleRecord, self.record_id)
        self.assertEqual(record.attempts, 2)
        self.assertEqual(record.snapshot['supply_generation']['best']['title'], MY_230)
        retry = AsyncMock(side_effect=ProviderError('temporary failure'))
        with patch('app.title_service.ask_json', new=retry), \
             patch('app.title_service.choose_keywords', side_effect=AssertionError('禁止重新选词')):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['title'], MY_230)
        self.assertEqual(result['attempts'], 4)
        self.assertEqual(retry.await_count, 2)

    async def test_supply_resumes_legacy_three_part_score_and_removes_only_similarity_feedback(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([MY_230, asyncio.CancelledError()], supply=True)
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        state['best']['score'] = [True, 30, True]
        state['best']['warnings'] = ['保留原提示', '与本批或近 90 天已采用标题高度相似，真实属性有限时允许保留']
        state['feedback'] = ('Compress to 180-200 characters. '
            'High similarity. Rotate optional verified attributes and synonyms; retain category.')
        record.snapshot = {**record.snapshot, 'supply_generation': state}
        self.db.commit()
        selected = state['selected']
        model = AsyncMock(return_value={'title': MY_180})
        with patch('app.title_service.ask_json', new=model), \
             patch('app.title_service.choose_keywords', side_effect=AssertionError('禁止重新选词')):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['attempts'], 3)
        self.assertEqual(model.await_count, 1)
        self.assertEqual(model.await_args.args[2]['selected'], selected)
        self.assertEqual(model.await_args.args[2]['feedback'], 'Compress to 180-200 characters.')
        self.assertNotIn('avoid', model.await_args.args[2])
        stored = self.db.get(TitleRecord, record.id, populate_existing=True).snapshot['supply_generation']
        self.assertEqual(stored['best']['score'], [False, 0])

    async def test_supply_legacy_in_range_best_requires_no_more_calls_and_keeps_attempt_count(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([MY_230, asyncio.CancelledError()], supply=True)
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        state['best'].update(title=MY_180, score=[False, 0, True],
            warnings=['保留原提示', '与并发生成的同批标题高度相似，请核对'])
        record.snapshot = {**record.snapshot, 'supply_generation': state}
        self.db.commit()
        model = AsyncMock(side_effect=AssertionError('不得因旧相似度标记继续成文'))
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        model.assert_not_awaited()
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['warnings'], ['保留原提示'])

    async def test_supply_legacy_equal_length_score_preserves_first_candidate_metadata(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([MY_230, asyncio.CancelledError()], supply=True)
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        state['best'].update(score=[True, 30, True], warnings=['首个候选的提示'])
        record.snapshot = {**record.snapshot, 'supply_generation': state}
        self.db.commit()
        model = AsyncMock(side_effect=[{'title': MY_230}, ProviderError('最后一次请求失败')])
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['title'], MY_230)
        self.assertEqual(result['attempts'], 4)
        self.assertEqual(result['warnings'], ['首个候选的提示'])

    async def test_supply_resume_does_not_remove_optional_word_twice(self):
        words = [keyword(1, 'Corak Bunga', tag='图案'), keyword(2, 'Lengan Panjang', tag='结构设计')]
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([MY_231, asyncio.CancelledError()], supply=True, words=words)
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        self.assertEqual(record.attempts, 2)
        self.assertEqual(len(state['removed_keyword_ids']), 1)
        selection = state['selected']
        model = AsyncMock(return_value={'title': MY_180})
        with patch('app.title_service.ask_json', new=model):
            await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(model.await_args.args[2]['selected'], selection)
        self.assertEqual(record.attempts, 3)
        self.assertEqual(record.snapshot['supply_generation']['compression_history'], state['compression_history'])

    async def test_supply_resume_applies_pending_compression_once(self):
        def interrupt_pending(state, *args):
            if state.get('compression_source_attempt'):
                raise asyncio.CancelledError()
            return prepare_supply_compression(state, *args)

        words = [keyword(1, 'Corak Bunga'), keyword(2, 'Lengan Panjang')]
        with patch('app.title_service.prepare_supply_compression', side_effect=interrupt_pending):
            with self.assertRaises(asyncio.CancelledError):
                await self.generate([MY_231], supply=True, words=words)
        record = self.db.get(TitleRecord, self.record_id)
        self.assertEqual(record.attempts, 1)
        self.assertNotIn('compression_applied_attempt', record.snapshot['supply_generation'])
        model = AsyncMock(return_value={'title': SHORT})
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['attempts'], 2)
        state = record.snapshot['supply_generation']
        self.assertEqual(state['compression_applied_attempt'], 1)
        self.assertEqual(len(state['compression_history']), 1)

    async def test_supply_legacy_reduction_flag_does_not_remove_more_words_on_resume(self):
        words = [keyword(1, 'Corak Bunga'), keyword(2, 'Lengan Panjang')]
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([asyncio.CancelledError()], supply=True, words=words)
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        state.update(reduce_optional=True, overlong_streak=2, cleaned_length=264)
        record.snapshot = {**record.snapshot, 'supply_generation': state}
        self.db.commit()
        model = AsyncMock(return_value={'title': MY_180})
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(model.await_args.args[2]['selected'], state['selected'])
        self.assertEqual(model.await_args.args[2]['compression_level'], 0)
        self.assertNotIn('reduce_optional', record.snapshot['supply_generation'])

    async def test_supply_compression_restore_adopts_saved_valid_candidate_without_call(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.generate([MY_230, asyncio.CancelledError()], supply=True)
        record = self.db.get(TitleRecord, self.record_id)
        state = copy.deepcopy(record.snapshot['supply_generation'])
        state.update(compression_level=1, compression_source_attempt=2, compression_source_length=264)
        record.snapshot = {**record.snapshot, 'supply_generation': state}
        self.db.commit()
        model = AsyncMock(side_effect=AssertionError('已有合格候选不得继续成文'))
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        model.assert_not_awaited()
        self.assertEqual(result['title'], MY_230)
        self.assertEqual(result['attempts'], 2)

    async def test_supply_empty_type_short_and_boundary_titles(self):
        for value in (None, '', 'Gaun', 123):
            with self.subTest(value=value):
                result, model = await self.generate([value, MY_180], supply=True)
                self.assertEqual(result['attempts'], 2)
                self.assertIn('180-200', model.await_args.args[2]['feedback'])
        for length in (24, 25, 179, 180, 200, 201, 230, 231):
            title = 'Gaun ' + 'a' * (length - 5)
            with self.subTest(length=length):
                if length in (24, 231):
                    with self.assertRaisesRegex(ProviderError, f'实际 {length} 字符'):
                        await self.generate([title] * 4, supply=True)
                else:
                    result, _ = await self.generate([title] * 4, supply=True)
                    self.assertEqual(len(result['title']), length)

    async def test_supply_long_selected_phrase_does_not_block_valid_model_title(self):
        word = keyword(1, 'a' * 231)
        result, model = await self.generate([MY_180], supply=True, words=[word], locked=[1])
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(model.await_count, 1)

    async def test_supply_takeover_prevents_stale_candidate_and_state_writes(self):
        def takeover(*args, **kwargs):
            record = self.db.get(TitleRecord, self.record_id)
            record.lease_owner = 'replacement-worker'
            self.db.commit()
            return {'title': MY_180}

        with self.assertRaisesRegex(ProviderError, '执行权'):
            await self.generate([MY_180], supply=True, response_callback=takeover)
        record = self.db.get(TitleRecord, self.record_id)
        self.assertEqual(record.lease_owner, 'replacement-worker')
        self.assertEqual(record.attempts, 1)
        self.assertNotIn('best', record.snapshot['supply_generation'])
        self.assertEqual(record.snapshot['title_diagnostics']['attempts'][0]['status'], 'running')
        self.assertIsNone(record.snapshot['title_diagnostics']['attempts'][0]['raw_title'])
        self.assertIsNone(record.title)
