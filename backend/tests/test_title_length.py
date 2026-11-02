"""词库标题软长度目标、选词预算及多次成文的结果保留。"""
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_providers import ProviderError
from app.database import Base
from app.title_models import TitleMarket, TitleRecord
from app.title_service import choose_keywords, create_record, generate_record, match_keywords


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
        # Gaun + 空格 + 196 字符 + 空格 + 8 字符 = 210。
        words = [keyword(1, 'a' * 196), keyword(2, 'bbbbbbbbb'), keyword(3, 'cccccccc')]
        for supply, expected in ((False, [1, 3]), (True, [2, 3])):
            with self.subTest(supply=supply):
                result = choose_keywords(self.snapshot(supply=supply), words, {1: 0, 2: 1, 3: 2})
                self.assertEqual([w['id'] for w in result], expected)

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


class TitleLengthGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.company_sequence = 0
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    async def generate(self, answers, *, supply=False, site='MY', history=None):
        core = 'Daster' if site == 'ID' else 'Gaun'
        self.company_sequence += 1
        market = TitleMarket(company_id=self.company_sequence, platform='TikTok', site=site,
                             language='id' if site == 'ID' else 'ms')
        self.db.add(market)
        self.db.flush()
        snapshot = {'template_id': 1, 'category': '连衣裙', 'category_localized_name': core,
                    'platform': 'TikTok', 'site': site, 'language': market.language,
                    'attributes': {}, 'keywords': [], 'locked_keyword_ids': [],
                    'forbidden_keyword_ids': [], 'forbidden_phrases': []}
        record = create_record(self.db, market, 1, snapshot, 'https://img.example/1.png', 'length-test', supply=supply)
        record.facts = {'attributes': [
            {'tag': '品类', 'value': '连衣裙', 'localized_value': core, 'source': 'manual'},
            {'tag': '细节元素', 'value': '已确认款式描述', 'localized_value':
             ID_182 if site == 'ID' else MY_231 + ' ' + MY_220, 'source': 'manual'},
            {'tag': '结构设计', 'value': '长袖', 'localized_value': 'Lengan Panjang', 'source': 'manual'},
            {'tag': '颜色', 'value': '蓝色', 'localized_value': 'Biru', 'source': 'manual'},
        ], 'warnings': []}
        if history:
            self.db.add(TitleRecord(market_id=market.id, user_id=1, template_id=1, request_key='history',
                category='连衣裙', image_url=record.image_url, snapshot=snapshot, title=history,
                selected_keywords=[], adopted_at=datetime.utcnow(), state='adopted'))
        self.db.commit()
        self.record_id = record.id
        sequence = [item if isinstance(item, Exception) else {'title': item} for item in answers]
        model = AsyncMock(side_effect=sequence)
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
        for title, length, supply in ((MY_180, 180, False), (MY_230, 230, False), (MY_220, 220, True)):
            with self.subTest(length=length, supply=supply):
                self.assertEqual(len(title), length)
                result, model = await self.generate([title], supply=supply)
                self.assertEqual(result['title'], title)
                self.assertEqual(model.await_count, 1)
                if supply:
                    self.assertEqual(model.await_args.args[2]['target_maximum'], 220)
                    self.assertEqual(len(result['title'] + ' - L01'), 226)

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

    async def test_in_range_similar_title_is_kept_over_shorter_unique_title(self):
        result, _ = await self.generate([MY_180, SHORT, ProviderError('failed'), SHORT], history=MY_180)
        self.assertEqual(result['title'], MY_180)
        self.assertTrue(any('高度相似' in warning for warning in result['warnings']))

    async def test_lower_similarity_wins_when_both_candidates_are_in_range(self):
        # 仅隔离相似度判定，成文及其余事实校验仍走实际流水线。
        with patch('app.title_service.similarity', side_effect=[True, False, False]):
            result, model = await self.generate([MY_180, MY_230], history=MY_180)
        self.assertEqual(result['title'], MY_230)
        self.assertEqual(model.await_count, 2)
        self.assertFalse(any('高度相似' in warning for warning in result['warnings']))

    async def test_equal_score_keeps_first_candidate_and_its_metadata(self):
        with patch('app.title_service.similarity', return_value=True):
            result, _ = await self.generate([MY_180, MY_230, MY_230, MY_230], history=MY_180)
        self.assertEqual(result['title'], MY_180)
        self.assertEqual(result['character_count'], 180)

    async def test_unconfirmed_material_cannot_replace_an_accepted_short_title(self):
        result, _ = await self.generate([SHORT, SHORT + ' Kapas', SHORT + ' Kalis Air', ProviderError('failed')])
        self.assertEqual(result['title'], SHORT)
        self.assertEqual(result['attempts'], 4)

    async def test_indonesian_titles_use_same_soft_length_policy(self):
        short = 'Daster Wanita Lengan Panjang Motif Bunga'
        result, model = await self.generate([short, ID_182], site='ID')
        self.assertEqual(result['title'], ID_182)
        self.assertEqual((result['site'], result['language']), ('ID', 'id'))
        self.assertIn('Bahasa Indonesia', model.await_args.args[1])
