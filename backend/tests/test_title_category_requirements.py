"""AI 必须使用完整品类词，遗漏时重新成文，程序不拼接标题。"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_providers import ProviderError
from app.database import Base
from app.title_models import TitleKeyword, TitleMarket, TitleRecord
from app.title_service import create_record, generate_record

class TitleCategoryRequirementsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    async def generate(self, title, *, site='MY', core='Gaun', selected=None, forbidden=(), supply=False):
        market = TitleMarket(company_id=1, platform='TikTok', site=site,
                             language='id' if site == 'ID' else 'ms')
        self.db.add(market)
        self.db.flush()
        snapshot = {'template_id': 1, 'category': '连衣裙', 'category_localized_name': core,
                    'attributes': {}, 'keywords': [], 'locked_keyword_ids': [],
                    'forbidden_keyword_ids': [], 'forbidden_phrases': list(forbidden)}
        if selected:
            word = TitleKeyword(market_id=market.id, code='KW000001', identity_hash='keyword',
                                phrase=selected, translation='长袖', tag='结构设计', categories=['连衣裙'])
            self.db.add(word)
            self.db.flush()
            snapshot['keywords'] = [{'id': word.id, 'phrase': selected, 'translation': '长袖',
                'tag': '结构设计', 'categories': ['连衣裙'], 'synonyms': [], 'conflicts': [],
                'priority': 'normal', 'selected_count': 0}]
            snapshot['locked_keyword_ids'] = [word.id]
        record = create_record(self.db, market, 1, snapshot, 'https://img.example/1.png', 'category-test', supply=supply)
        record.facts = {'attributes': [
            {'tag': tag, 'value': value, 'localized_value': expression, 'source': 'manual'}
            for tag, value, expression in [('品类', '连衣裙', core), ('结构设计', '长袖', 'Lengan Panjang'),
                                            ('图案', '花卉', 'Corak Bunga' if site == 'MY' else 'Motif Bunga')]],
            'warnings': []}
        self.db.commit()
        model = (AsyncMock(side_effect=[{'title': item} for item in title + [title[-1]] * (4 - len(title))])
                 if isinstance(title, list) else AsyncMock(return_value={'title': title}))
        self.record_id = record.id
        self.model = model
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record.id, 'test-key')
        expected_core = core
        self.assertEqual(model.await_args.args[2]['core_category'], expected_core)
        if expected_core:
            self.assertIn(expected_core, model.await_args.args[2]['required_phrases'])
        if selected:
            expected_selected = selected
            if expected_selected:
                self.assertIn(expected_selected, model.await_args.args[2]['required_phrases'])
        return result

    async def test_missing_category_retries_with_exact_phrase_and_keeps_model_word_order(self):
        rewritten = 'Lengan Panjang Gaun Corak Bunga'
        result = await self.generate(['Lengan Panjang Corak Bunga', rewritten], selected='Lengan Panjang')
        self.assertEqual(result['title'], rewritten)
        self.assertEqual(result['attempts'], 4)
        self.assertEqual(self.model.await_count, 4)
        first, retry = self.model.await_args_list[:2]
        self.assertEqual(first.args[2]['feedback'], '')
        self.assertIn('核心品类：Gaun', retry.args[2]['feedback'])
        record = self.db.get(TitleRecord, self.record_id, populate_existing=True)
        self.assertEqual(record.title, result['title'])
        self.assertEqual(record.state, 'generated')

    async def test_repeated_missing_category_is_rejected_instead_of_appended(self):
        with self.assertRaisesRegex(ProviderError, '标题遗漏核心品类：Gaun'):
            await self.generate('Lengan Panjang Corak Bunga')
        self.assertEqual(self.model.await_count, 4)
        record = self.db.get(TitleRecord, self.record_id, populate_existing=True)
        self.assertIsNone(record.title)
        self.assertEqual(record.state, 'failed')

    async def test_existing_category_is_not_duplicated_or_reordered(self):
        title = 'Lengan Panjang GAUN Corak Bunga'
        result = await self.generate(title)
        self.assertEqual(result['title'], title)

    async def test_indonesian_category_uses_confirmed_localized_name(self):
        title = 'Lengan Panjang Daster Wanita Motif Bunga'
        result = await self.generate(title, site='ID', core='Daster Wanita')
        self.assertEqual(result['title'], title)

    async def test_category_cannot_be_split_into_noncontiguous_words(self):
        with self.assertRaisesRegex(ProviderError, '标题遗漏核心品类：Daster Wanita'):
            await self.generate('Daster Lengan Panjang Wanita Motif Bunga', site='ID', core='Daster Wanita')

    async def test_titles_cannot_exceed_regular_or_supply_length_limit(self):
        for supply, maximum in ((False, 255), (True, 230)):
            with self.subTest(supply=supply):
                raw = ('Gaun ' + 'Lengan Panjang ' * 20)[:maximum] + 'a'
                with self.assertRaisesRegex(ProviderError, f'25–{maximum}'):
                    await self.generate(raw, supply=supply)
                self.assertEqual(self.model.await_count, 4)
                self.assertIsNone(self.db.get(TitleRecord, self.record_id).title)
                self.db.rollback()
                self.db.query(TitleRecord).delete()
                self.db.query(TitleMarket).delete()
                self.db.commit()

    async def test_missing_selected_phrase_has_specific_error(self):
        with self.assertRaisesRegex(ProviderError, '标题遗漏选定词组：Lengan Panjang'):
            await self.generate('Gaun Corak Bunga Corak Bunga Corak Bunga', selected='Lengan Panjang')
        self.assertEqual(self.model.await_count, 4)


    async def test_words_outside_facts_selected_keywords_and_grammar_are_accepted(self):
        title = 'Gaun Lengan Panjang Moden Anggun Selesa Beralun Casual Elegant'
        result = await self.generate(title)
        self.assertEqual(result['title'], title)
        self.assertIsNone(self.db.get(TitleRecord, self.record_id).error)

    async def test_indonesian_words_outside_word_list_are_accepted(self):
        title = 'Daster Wanita Lengan Panjang Motif Bunga Kekinian Santai Casual'
        result = await self.generate(title, site='ID', core='Daster Wanita')
        self.assertEqual(result['title'], title)

    async def test_common_malay_title_expressions_pass_without_confirmed_attributes(self):
        title = 'Gaun Labuh Lengan Panjang Corak Bunga Dengan Potongan Yang Sesuai'
        result = await self.generate(title)
        self.assertEqual(result['title'], title)
        self.assertNotIn('allowed_expression_words', self.model.await_args.args[2])
        self.assertFalse(any('未经确认' in warning for warning in result['warnings']))

    async def test_common_indonesian_connective_passes_without_confirmed_attribute(self):
        title = 'Daster Wanita Lengan Panjang Motif Bunga Dengan Potongan Yang Sesuai'
        result = await self.generate(title, site='ID', core='Daster Wanita')
        self.assertEqual(result['title'], title)
        self.assertNotIn('allowed_expression_words', self.model.await_args.args[2])


    async def test_blank_model_output_is_not_replaced_with_category(self):
        with self.assertRaisesRegex(ProviderError, '标题长度'):
            await self.generate('   ')
