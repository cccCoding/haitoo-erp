"""逐轮诊断区分模型遗漏和清理删除，并在重试、恢复后保留证据。"""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_providers import ProviderError
from app.database import Base
from app.title_models import TitleKeyword, TitleMarket, TitleRecord
from app.title_service import create_record, generate_record
from tests.test_title_length import MY_180, keyword


VALID = MY_180.replace('Gaun', 'Skirt Wanita').replace('Pinggang Berikat', 'Pinggang Elastik')
MISSING = VALID.replace('Pinggang Elastik', 'Pinggang Anjal')
INVALID_FORMAT = MISSING.replace('Wanita', 'Wanita\n', 1)


class TitleDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def record(self, *, supply=True, cleanup_conflict=False):
        market = TitleMarket(company_id=1, platform='TikTok', site='MY', language='ms')
        self.db.add(market)
        self.db.flush()
        words = [keyword(1, 'Pinggang Elastik', tag='结构设计', code='KW007956', label_tag='腰头设计')]
        if cleanup_conflict:
            words += [keyword(2, 'Siap Jahit', tag='营销修饰'), keyword(3, 'SIAP JAHIT', tag='工艺')]
        for word in words:
            self.db.add(TitleKeyword(id=word['id'], market_id=market.id, code=str(word['id']),
                identity_hash=str(word['id']), phrase=word['phrase'], tag=word['tag'],
                translation=word['translation'], categories=word['categories']))
        snapshot = {'template_id': 1, 'category': '连衣裙', 'category_localized_name': 'Skirt Wanita',
            'platform': 'TikTok', 'site': 'MY', 'language': 'ms', 'attributes': {},
            'keywords': words, 'locked_keyword_ids': [1], 'forbidden_keyword_ids': [],
            'forbidden_phrases': ['Viral'], 'keyword_policy_version': 2, 'confirmed_choices_version': 1}
        record = create_record(self.db, market, 1, snapshot, 'https://img.example/1.png', 'diagnostics', supply=supply)
        record.facts = {'attributes': [
            {'tag': '品类', 'value': '连衣裙', 'localized_value': 'Skirt Wanita', 'source': 'manual'},
            {'tag': '结构设计', 'value': '松紧腰', 'localized_value': 'Pinggang Elastik', 'source': 'image'}],
            'warnings': []}
        self.db.commit()
        return record.id

    async def generate(self, record_id, responses):
        model = AsyncMock(side_effect=responses)
        with patch('app.title_service.ask_json', new=model):
            result = await generate_record(self.db, record_id, 'private-test-key')
        return result, model

    def attempts(self, record_id):
        self.db.expire_all()
        return self.db.get(TitleRecord, record_id).snapshot['title_diagnostics']['attempts']

    async def test_keeps_every_failure_and_success_with_original_input(self):
        record_id = self.record()
        result, model = await self.generate(record_id, [ProviderError('DeepSeek 调用失败：HTTP 429'),
            {'title': VALID + ' ' + 'a' * 100}, {'title': INVALID_FORMAT}, {'title': VALID}])
        self.assertEqual(result['title'], VALID)
        attempts = self.attempts(record_id)
        self.assertEqual([row['attempt'] for row in attempts], [1, 2, 3, 4])
        self.assertEqual([row['status'] for row in attempts], ['failed', 'failed', 'failed', 'valid'])
        self.assertEqual([row['stage'] for row in attempts],
            ['provider', 'localized_title', 'localized_title', 'complete'])
        self.assertIsNone(attempts[0]['raw_title'])
        self.assertEqual(attempts[0]['missing_phrases'], {})
        self.assertIn('HTTP 429', attempts[0]['error'])
        self.assertGreater(attempts[1]['raw_length'], 230)
        self.assertEqual(attempts[2]['raw_title'], INVALID_FORMAT)
        self.assertIn('单行纯文本', attempts[2]['error'])
        self.assertEqual(attempts[2]['missing_phrases']['raw'], ['Pinggang Elastik'])
        self.assertEqual(attempts[2]['missing_phrases']['cleaned'], ['Pinggang Elastik'])
        self.assertEqual(attempts[2]['selected_keywords'][0]['label_tag'], '腰头设计')
        self.assertEqual(attempts[3]['missing_phrases']['cleaned'], [])
        self.assertTrue(all(row['started_at'] and row['finished_at'] for row in attempts))
        self.assertNotIn('private-test-key', json.dumps(attempts))
        self.assertEqual(model.await_count, 4)

    async def test_cross_tag_words_and_legacy_forbidden_text_are_preserved(self):
        record_id = self.record(cleanup_conflict=True)
        raw = VALID[:170] + ' SIAP JAHIT Viral'
        result, _ = await self.generate(record_id, [{'title': raw}])
        self.assertEqual(result['title'], raw)
        row = self.attempts(record_id)[0]
        self.assertEqual(row['raw_title'], raw)
        self.assertEqual(row['cleaned_title'], raw)
        self.assertEqual(row['missing_phrases']['raw'], [])
        self.assertEqual(row['missing_phrases']['cleaned'], [])
        self.assertNotIn('removed_unselected_claims', row)
        self.assertNotIn('removed_forbidden_phrases', row)
        self.assertEqual(row['policy_version'], 4)

    async def test_non_string_response_preserves_type_without_inventing_missing_phrases(self):
        record_id = self.record()
        result, _ = await self.generate(record_id, [{'title': 123}, {'title': VALID}])
        self.assertEqual(result['title'], VALID)
        row = self.attempts(record_id)[0]
        self.assertEqual(row['raw_title'], 123)
        self.assertEqual(row['missing_phrases'], {})
        self.assertEqual(row['stage'], 'localized_title')

    async def test_resume_preserves_history_and_marks_unfinished_attempt(self):
        record_id = self.record()
        with self.assertRaises(asyncio.CancelledError):
            await self.generate(record_id, [{'title': INVALID_FORMAT}, asyncio.CancelledError()])
        self.assertEqual([row['status'] for row in self.attempts(record_id)], ['failed', 'running'])
        result, _ = await self.generate(record_id, [{'title': VALID}])
        self.assertEqual(result['attempts'], 3)
        attempts = self.attempts(record_id)
        self.assertEqual([row['status'] for row in attempts], ['failed', 'interrupted', 'valid'])
        self.assertEqual([row['attempt'] for row in attempts], [1, 2, 3])
        self.assertEqual(attempts[0]['raw_title'], INVALID_FORMAT)
        self.assertIsNone(attempts[1]['raw_title'])

    async def test_single_title_also_keeps_diagnostics_and_replay_does_not_duplicate(self):
        record_id = self.record(supply=False)
        result, _ = await self.generate(record_id, [{'title': VALID}])
        replay, model = await self.generate(record_id, [])
        self.assertEqual(result, replay)
        model.assert_not_awaited()
        self.assertEqual(len(self.attempts(record_id)), 1)

    async def test_exhausted_interrupted_attempt_is_marked_without_another_model_call(self):
        record_id = self.record()
        record = self.db.get(TitleRecord, record_id)
        record.attempts = 4
        record.snapshot = {**record.snapshot, 'title_diagnostics': {'version': 1,
            'attempts': [{'attempt': 4, 'status': 'running', 'raw_title': None}]}}
        self.db.commit()
        model = AsyncMock()
        with patch('app.title_service.ask_json', new=model):
            with self.assertRaisesRegex(ProviderError, '最多 4 次'):
                await generate_record(self.db, record_id, 'test-key')
        model.assert_not_awaited()
        self.assertEqual(self.attempts(record_id)[0]['status'], 'interrupted')
        self.assertIsNotNone(self.attempts(record_id)[0]['interruption_detected_at'])

    async def test_unexpected_failure_is_recorded_without_exception_secrets(self):
        record_id = self.record()
        with self.assertRaises(RuntimeError):
            await self.generate(record_id, [RuntimeError('private-test-key')])
        attempts = self.attempts(record_id)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['status'], 'failed')
        self.assertEqual(attempts[0]['error'], '标题生成失败')
        self.assertNotIn('private-test-key', json.dumps(attempts))
