"""标题 Worker 的任务调度、全局并发上限及取消保护。"""
import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.ai_providers import ProviderError
from app.title_models import TitleRecord, TitleTask
from app.title_service import get_market
from app.title_worker import claim_task, run_task, serve
from tests.test_supply_catalog import SupplyFixture


class TitleWorkerConcurrencyTests(SupplyFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.settings = SimpleNamespace(title_worker_concurrency=2, title_item_concurrency=3)
        self.enterContext(patch('app.title_worker.get_settings', return_value=self.settings))

    def batch(self, key, count):
        with self.sessions() as db:
            market = get_market(db, 1, create=True)
            task = TitleTask(market_id=market.id, user_id=2, kind='batch', state='queued',
                request_key=key, request_hash=key, snapshot={}, progress={'total': count, 'completed': 0})
            db.add(task); db.flush()
            records = []
            for index in range(count):
                record = TitleRecord(market_id=market.id, user_id=2, template_id=1, task_id=task.id,
                    request_key=f'{key}-{index}', category='连衣裙', image_url=f'https://img.example/{index}.png', snapshot={})
                db.add(record); db.flush(); records.append(record.id)
            task.snapshot = {'groups': [{'key': str(index), 'generation_id': identity} for index, identity in enumerate(records)]}
            identity = task.id
            db.commit()
        return identity, records

    def task(self, identity):
        with self.sessions() as db:
            task = db.get(TitleTask, identity)
            return task.state, dict(task.progress), dict(task.result)

    async def test_groups_overlap_with_a_bounded_pool_and_save_results_out_of_order(self):
        identity, records = self.batch('overlap', 5)
        claimed = claim_task(self.sessions)
        started, release = asyncio.Event(), asyncio.Event()
        active = 0
        maximum = 0
        sessions = set()

        async def generate(db, record_id):
            nonlocal active, maximum
            active += 1; maximum = max(maximum, active); sessions.add(id(db))
            if active == 3:
                started.set()
            try:
                if record_id == records[0]:
                    await release.wait()
                else:
                    await started.wait()
                    await asyncio.sleep(0)
                if record_id == records[2]:
                    raise ProviderError('测试单项失败')
                return {'title': f'Gaun Lengan Panjang Corak Bunga {record_id}', 'generation_id': record_id}
            finally:
                active -= 1

        with patch('app.title_worker.generate_record', side_effect=generate):
            runner = asyncio.create_task(run_task(*claimed, session_factory=self.sessions))
            try:
                await asyncio.wait_for(started.wait(), 3)
                for _ in range(100):
                    if self.task(identity)[1]['completed'] == 4:
                        break
                    await asyncio.sleep(0.01)
                state, progress, result = self.task(identity)
                self.assertEqual(state, 'running')
                self.assertEqual(progress['completed'], 4)
                self.assertNotIn('0', result['items'])
                self.assertEqual(maximum, 3)
                self.assertGreaterEqual(len(sessions), 3)
            finally:
                release.set()
                await asyncio.wait_for(runner, 3)
        state, progress, result = self.task(identity)
        self.assertEqual(state, 'completed_with_errors')
        self.assertEqual(progress, {'total': 5, 'completed': 5, 'succeeded': 4, 'failed': 1})
        self.assertEqual(set(result['items']), {'0', '1', '2', '3', '4'})
        self.assertEqual(result['items']['2']['error'], '测试单项失败')

    async def test_cancellation_fences_late_results_and_does_not_start_waiting_groups(self):
        identity, _ = self.batch('cancel', 6)
        claimed = claim_task(self.sessions)
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def generate(db, record_id):
            calls.append(record_id)
            if len(calls) == 3:
                started.set()
            await release.wait()
            return {'title': 'Gaun Lengan Panjang Corak Bunga', 'generation_id': record_id}
        with patch('app.title_worker.generate_record', side_effect=generate):
            runner = asyncio.create_task(run_task(*claimed, session_factory=self.sessions))
            try:
                await asyncio.wait_for(started.wait(), 3)
                with self.sessions() as db:
                    db.get(TitleTask, identity).state = 'cancelled'
                    db.commit()
            finally:
                release.set()
                await asyncio.wait_for(runner, 3)
        state, progress, result = self.task(identity)
        self.assertEqual(state, 'cancelled')
        self.assertEqual(progress['completed'], 0)
        self.assertFalse(result.get('items'))
        self.assertEqual(len(calls), 3)

    async def test_dispatcher_runs_multiple_tasks_with_one_global_item_limit(self):
        first, _ = self.batch('global-first', 2)
        second, _ = self.batch('global-second', 2)
        third, _ = self.batch('global-third', 1)
        started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        active = 0
        maximum = 0
        seen_tasks = set()
        async def generate(db, record_id):
            nonlocal active, maximum
            active += 1; maximum = max(maximum, active)
            seen_tasks.add(db.get(TitleRecord, record_id).task_id)
            if active == 3:
                started.set()
            try:
                await release.wait()
                return {'title': 'Gaun Lengan Panjang Corak Bunga', 'generation_id': record_id}
            finally:
                active -= 1
        with patch('app.title_worker.generate_record', side_effect=generate):
            dispatcher = asyncio.create_task(serve(stop_event=stop, session_factory=self.sessions))
            try:
                await asyncio.wait_for(started.wait(), 3)
                self.assertEqual(seen_tasks, {first, second})
                self.assertEqual(self.task(first)[0], 'running')
                self.assertEqual(self.task(second)[0], 'running')
                self.assertEqual(self.task(third)[0], 'queued')
                self.assertEqual(maximum, 3)
            finally:
                stop.set(); release.set()
                await asyncio.wait_for(dispatcher, 3)
        self.assertEqual(self.task(first)[0], 'completed')
        self.assertEqual(self.task(second)[0], 'completed')
        self.assertEqual(self.task(third)[0], 'queued')

    async def test_free_slot_claims_next_task_while_an_earlier_task_is_slow(self):
        slow, slow_records = self.batch('slow', 1)
        fast, _ = self.batch('fast', 1)
        next_task, next_records = self.batch('next', 1)
        release, next_started, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def generate(db, record_id):
            if record_id == slow_records[0]:
                await release.wait()
            if record_id == next_records[0]:
                next_started.set()
            return {'title': 'Gaun Lengan Panjang Corak Bunga', 'generation_id': record_id}
        with patch('app.title_worker.generate_record', side_effect=generate):
            dispatcher = asyncio.create_task(serve(stop_event=stop, session_factory=self.sessions))
            try:
                await asyncio.wait_for(next_started.wait(), 3)
                self.assertEqual(self.task(slow)[0], 'running')
                self.assertEqual(self.task(fast)[0], 'completed')
            finally:
                stop.set(); release.set()
                await asyncio.wait_for(dispatcher, 3)
        self.assertEqual(self.task(next_task)[0], 'completed')

    def test_active_task_is_not_reclaimed_by_its_own_dispatcher(self):
        identity, _ = self.batch('exclude-active', 1)
        claimed = claim_task(self.sessions)
        with self.sessions() as db:
            db.get(TitleTask, identity).lease_expires_at = datetime.utcnow()-timedelta(seconds=1)
            db.commit()
        self.assertIsNone(claim_task(self.sessions, exclude_ids=(identity,)))
        self.assertEqual(claim_task(self.sessions)[0], claimed[0])

    async def test_old_owner_cannot_overwrite_results_after_lease_takeover(self):
        identity, _ = self.batch('takeover', 5)
        claimed = claim_task(self.sessions)
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def generate(db, record_id):
            calls.append(record_id)
            if len(calls) == 3:
                started.set()
            await release.wait()
            return {'title': 'Gaun Lengan Panjang Corak Bunga', 'generation_id': record_id}
        new_result = {'items': {'replacement': {'title': 'New owner saved this result'}}}
        with patch('app.title_worker.generate_record', side_effect=generate):
            runner = asyncio.create_task(run_task(*claimed, session_factory=self.sessions))
            try:
                await asyncio.wait_for(started.wait(), 3)
                with self.sessions() as db:
                    db.get(TitleTask, identity).lease_expires_at = datetime.utcnow()-timedelta(seconds=1)
                    db.commit()
                _, new_owner = claim_task(self.sessions)
                with self.sessions() as db:
                    db.get(TitleTask, identity).result = new_result
                    db.commit()
            finally:
                release.set()
                await asyncio.wait_for(runner, 3)
        with self.sessions() as db:
            task = db.get(TitleTask, identity)
            self.assertEqual(task.lease_owner, new_owner)
            self.assertEqual(task.state, 'running')
            self.assertEqual(task.result, new_result)
        self.assertEqual(len(calls), 3)

    async def test_dispatcher_recovers_from_a_claim_failure(self):
        stop = asyncio.Event()
        claims = 0
        async def execute(identity, owner, **kwargs):
            stop.set()
        def claim(*args, **kwargs):
            nonlocal claims
            claims += 1
            if claims == 1:
                raise RuntimeError('模拟数据库暂时不可用')
            return (10, 'owner') if claims == 2 else None
        with self.assertLogs('app.title_worker', level='ERROR') as logs:
            with patch('app.title_worker.claim_task', side_effect=claim), patch('app.title_worker.run_task', side_effect=execute) as runner:
                await asyncio.wait_for(serve(stop_event=stop, session_factory=self.sessions), 4)
        self.assertIn('标题任务领取失败', logs.output[0])
        runner.assert_awaited_once()


class TitleWorkerSettingsTests(unittest.TestCase):
    def test_concurrency_settings_have_finite_positive_limits(self):
        from pydantic import ValidationError
        from app.config import Settings
        settings = Settings(_env_file=None)
        self.assertEqual((settings.title_worker_concurrency, settings.title_item_concurrency), (3, 10))
        for values in ({'title_worker_concurrency': 0}, {'title_worker_concurrency': 21},
                       {'title_item_concurrency': 0}, {'title_item_concurrency': 11}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(_env_file=None, **values)
