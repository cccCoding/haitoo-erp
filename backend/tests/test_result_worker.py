"""结果并发调度、连接生命周期、短事务与分阶段统计的行为验证。"""
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from io import BytesIO
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from PIL import Image

from app import ai_providers, image_files, main, result_worker as worker, task_jobs
from app.ai_providers import ProviderError, ProviderRateLimitError, ProviderTaskTerminalError
from app.credentials import encrypt_secret
from app.database import Base
from app.models import (AIProviderSetting, Company, PodTask, ProductTemplate, Role, TaskQueueSetting,
                        TaskStatus, User, UserAIProviderCredential)
from app.schemas import TaskQueueSettingUpdate


async def until(predicate, timeout=3):
    async def wait():
        while not predicate():
            await asyncio.sleep(.002)
    await asyncio.wait_for(wait(), timeout)


async def stop(task):
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


class PacerAndMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_interval_and_no_catch_up(self):
        now = [0.0]
        async def sleep(delay):
            now[0] += delay
        pacer = worker.QueryPacer(.1, clock=lambda: now[0], sleep=sleep)
        key = (1, 2, 'grsai')
        self.assertEqual(await pacer.start(key), 0)
        self.assertAlmostEqual(await pacer.start(key), .1)
        now[0] = 100
        self.assertEqual(await pacer.start(key), 100)
        self.assertAlmostEqual(await pacer.start(key), 100.1)

    async def test_interval_change_wakes_waiters(self):
        pacer = worker.QueryPacer(60)
        await pacer.start((1, 1, 'grsai'))
        waiting = asyncio.create_task(pacer.start((1, 1, 'grsai')))
        await asyncio.sleep(.01)
        pacer.configure(.001)
        await asyncio.wait_for(waiting, .2)

    async def test_pending_waiter_observes_credential_cooldown(self):
        pacer = worker.QueryPacer(.03)
        key = (1, 1, 'grsai')
        await pacer.start(key)
        waiting = asyncio.create_task(pacer.start(key))
        await asyncio.sleep(.005)
        pacer.cooldowns[key] = time.monotonic() + 5
        self.assertIsNone(await waiting)
        self.assertIsNotNone(await pacer.start((1, 2, 'grsai')))

    async def test_cooldown_releases_all_waiting_slots_without_waiting_for_interval(self):
        pacer = worker.QueryPacer(60)
        key = (1, 1, 'grsai')
        await pacer.start(key)
        waiting = [asyncio.create_task(pacer.start(key)) for _ in range(4)]
        await asyncio.sleep(.01)
        pacer.cool_down(key, 5)
        self.assertEqual(await asyncio.wait_for(asyncio.gather(*waiting), .2), [None] * 4)

    async def test_parallel_waiters_share_global_start_spacing(self):
        pacer = worker.QueryPacer(.01)
        starts = await asyncio.gather(*(pacer.start((1, i, 'grsai')) for i in range(10)))
        ordered = sorted(starts)
        self.assertTrue(all(b - a >= .01 for a, b in zip(ordered, ordered[1:])))

    def test_bounded_p95_full_average_and_empty_window(self):
        now = [0.0]
        metrics = worker.QueryMetrics(clock=lambda: now[0])
        options = dict(queued=2, active=1, concurrency=5, interval=.01)
        self.assertEqual(metrics.summary(**options)['timings_ms'], {})
        for i in range(10001):
            metrics.add('query_ms', i / 1000)
        metrics.requests = 10001
        metrics.outcomes['pending'] = 10000
        now[0] = 60
        summary = metrics.summary(**options)
        values = summary['timings_ms']['query_ms']
        self.assertEqual(values['count'], 10001)
        self.assertEqual(values['p95_samples'], 10000)
        self.assertEqual(values['avg'], 5000)
        self.assertEqual(values['p95'], 9500)
        self.assertAlmostEqual(summary['requests_per_second'], 10001 / 60)
        metrics.reset()
        self.assertEqual(metrics.summary(**options)['requests'], 0)
        self.assertFalse(metrics.timings)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.refs = [worker.TaskRef(i, f'provider-{i}', 1, i, 'grsai') for i in range(1, 101)]
        self.concurrency = 5
        self.interval = .001
        self.schedule_patch = patch.object(worker, 'read_schedule', side_effect=lambda: (
            self.concurrency, self.interval, list(self.refs)))
        self.schedule_patch.start()
        self.addCleanup(self.schedule_patch.stop)

    async def test_continuous_filling_bound_duplicate_refresh_and_slow_request(self):
        scheduler = worker.ResultScheduler(None)
        started, active, maximum = [], set(), [0]
        slow = asyncio.Event()
        async def process(task_id, **kwargs):
            self.assertNotIn(task_id, active)
            active.add(task_id)
            started.append(task_id)
            maximum[0] = max(maximum[0], len(active))
            try:
                if task_id == 1:
                    await slow.wait()
                else:
                    await asyncio.sleep(.005)
                self.refs = [ref for ref in self.refs if ref.id != task_id]
                return 'succeeded'
            finally:
                active.remove(task_id)
        with patch.object(worker, 'process_result', side_effect=process):
            running = asyncio.create_task(scheduler.run())
            try:
                await until(lambda: len(started) >= 20)
                self.assertIn(1, active)
                await scheduler.refresh()
                self.assertEqual(len(scheduler.ready), len(set(scheduler.ready)))
                self.assertFalse(set(scheduler.ready) & scheduler.active.keys())
                self.assertEqual(maximum[0], 5)
            finally:
                await stop(running)
        self.assertFalse(active)
        self.assertFalse(scheduler.active)

    async def test_online_concurrency_increase_and_decrease(self):
        scheduler = worker.ResultScheduler(None)
        blocked = asyncio.Event()
        async def process(task_id, **kwargs):
            await blocked.wait()
            self.refs = [ref for ref in self.refs if ref.id != task_id]
            return 'succeeded'
        with patch.object(worker, 'process_result', side_effect=process):
            self.concurrency = 2
            running = asyncio.create_task(scheduler.run())
            try:
                await until(lambda: len(scheduler.active) == 2)
                self.concurrency = 5
                await until(lambda: len(scheduler.active) == 5, 1.5)
                self.concurrency = 1
                await until(lambda: scheduler.concurrency == 1, 1.5)
                self.assertEqual(len(scheduler.active), 5)
                blocked.set()
                await until(lambda: not self.refs)
            finally:
                await stop(running)

    async def test_cooling_credential_uses_no_slot_and_other_user_continues(self):
        scheduler = worker.ResultScheduler(None)
        self.refs = [worker.TaskRef(i, str(i), 1, 1 if i < 4 else 2, 'grsai') for i in range(1, 6)]
        await scheduler.refresh()
        scheduler.pacer.cooldowns[(1, 1, 'grsai')] = time.monotonic() + 60
        with patch.object(worker, 'process_result', new=AsyncMock(return_value='succeeded')) as process:
            scheduler.fill_slots()
            self.assertEqual(set(scheduler.active), {4, 5})
            await asyncio.gather(*list(scheduler.active.values()))
            self.assertEqual(process.await_count, 2)
            self.assertEqual(list(scheduler.ready), [1, 2, 3])

    async def test_pending_requeues_after_other_tasks_and_new_task_joins(self):
        self.refs = self.refs[:2]
        scheduler = worker.ResultScheduler(None)
        seen = []
        async def process(task_id, **kwargs):
            seen.append(task_id)
            await asyncio.sleep(.005)
            return 'pending'
        with patch.object(worker, 'process_result', side_effect=process):
            running = asyncio.create_task(scheduler.run())
            try:
                await until(lambda: len(seen) >= 4)
                self.refs.append(worker.TaskRef(999, 'new', 1, 3, 'grsai'))
                await until(lambda: 999 in seen, 1.5)
                self.assertEqual(seen[:2], [1, 2])
            finally:
                await stop(running)

    async def test_shared_client_owned_and_closed_on_cancellation(self):
        entered = asyncio.Event()
        client = httpx.AsyncClient()
        async def run(instance):
            self.assertIs(instance.client, client)
            entered.set()
            await asyncio.Event().wait()
        with patch.object(worker.httpx, 'AsyncClient', return_value=client), patch.object(worker.ResultScheduler, 'run', run):
            task = asyncio.create_task(worker.run_result_worker())
            await entered.wait()
            await stop(task)
        self.assertTrue(client.is_closed)

    async def test_hundred_queries_measured_speedup_and_real_start_spacing(self):
        async def benchmark(concurrency):
            self.refs = [worker.TaskRef(i, str(i), 1, 1, 'grsai') for i in range(100)]
            self.concurrency = concurrency
            self.interval = .001
            scheduler = worker.ResultScheduler(None)
            starts = []
            async def process(task_id, *, pacer, **kwargs):
                await pacer.start((1, 1, 'grsai'))
                starts.append(time.monotonic())
                await asyncio.sleep(.025)
                self.refs = [ref for ref in self.refs if ref.id != task_id]
                return 'succeeded'
            with patch.object(worker, 'process_result', side_effect=process):
                began = time.monotonic()
                running = asyncio.create_task(scheduler.run())
                try:
                    await until(lambda: len(starts) == 100 and not scheduler.active, timeout=8)
                finally:
                    await stop(running)
            self.assertTrue(all(b - a >= .0009 for a, b in zip(starts, starts[1:])))
            return time.monotonic() - began
        serial = await benchmark(1)
        parallel = await benchmark(5)
        print(f'\n100 任务模拟查询：并发 1={serial:.3f}s，并发 5={parallel:.3f}s，提速={serial/parallel:.2f}x')
        self.assertGreaterEqual(serial / parallel, 3)


class ResultDatabaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{Path(self.directory.name) / "results.db"}',
                                    connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name='Company'),
                User(id=1, company_id=1, email='test@example.com', name='Test', user_code='AA', password_hash='x', role=Role.MEMBER),
                ProductTemplate(id=1, company_id=1, name='Template', cover_url='https://example.com/white.png'),
                AIProviderSetting(provider='grsai', display_name='Grsai', model='nano', credential_provider='grsai'),
                AIProviderSetting(provider='grsai-gpt-image-2', display_name='Grsai 2', model='gpt-image-2', credential_provider='grsai'),
                TaskQueueSetting(id=1, submit_interval_ms=50, result_interval_ms=10, result_concurrency=5),
                UserAIProviderCredential(company_id=1, user_id=1, provider='grsai', secret_encrypted=encrypt_secret('member-key')),
            ])
            db.commit()
        def get_db():
            with self.sessions() as db:
                yield db
        self.db_patch = patch.object(task_jobs, 'get_db', get_db)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.engine.dispose)

    def add_task(self, provider='grsai'):
        with self.sessions() as db:
            task = PodTask(company_id=1, template_id=1, created_by=1, task_type='sku_image',
                status=TaskStatus.RUNNING, provider=provider, provider_task_id='provider-1', provider_model='nano',
                parameters={'print_urls': ['https://example.com/print.png']}, result_urls=[], result_map=[])
            db.add(task)
            db.commit()
            return task.id

    async def test_concurrent_pipeline_with_independent_database_connections(self):
        ids = [self.add_task() for _ in range(15)]
        starts, finishes = [], []
        slow_storage = asyncio.Event()
        first_storage = asyncio.Event()
        async def poll(provider, external_id, key, **kwargs):
            self.assertEqual(key, 'member-key')
            starts.append(time.monotonic())
            await asyncio.sleep(.015)
            return ['https://example.com/result.png']
        async def persist(urls, company, task_id):
            if task_id == ids[0]:
                first_storage.set()
                await slow_storage.wait()
            finishes.append(task_id)
            return ['https://img.example/saved.png']
        async with httpx.AsyncClient() as client:
            scheduler = worker.ResultScheduler(client)
            with patch.object(task_jobs, 'poll_async_generation', side_effect=poll), patch.object(task_jobs, 'persist_generated_images', side_effect=persist):
                running = asyncio.create_task(scheduler.run())
                try:
                    await asyncio.wait_for(first_storage.wait(), 2)
                    await until(lambda: len(finishes) == 14)
                    self.assertIn(ids[0], scheduler.active)
                    self.assertEqual(len(starts), 15)
                    slow_storage.set()
                    await until(lambda: not scheduler.active)
                finally:
                    await stop(running)
        with self.sessions() as db:
            self.assertTrue(all(db.get(PodTask, task_id).status == TaskStatus.AWAITING_SELECTION for task_id in ids))

    async def test_deleted_or_finished_task_is_removed_and_does_not_query(self):
        task_id = self.add_task()
        scheduler = worker.ResultScheduler(None)
        await scheduler.refresh()
        self.assertEqual(list(scheduler.ready), [task_id])
        with self.sessions() as db:
            db.get(PodTask, task_id).status = TaskStatus.FAILED
            db.commit()
        await scheduler.refresh()
        self.assertFalse(scheduler.ready)
        with patch.object(task_jobs, 'poll_async_generation', new=AsyncMock()) as poll:
            self.assertEqual(await worker.process_result(task_id), 'skipped')
        poll.assert_not_awaited()

    async def test_real_image_ingestion_releases_connection_before_r2(self):
        content = BytesIO()
        Image.new('RGB', (4, 4), 'white').save(content, format='PNG')
        checked_out = set()
        event.listen(self.engine, 'checkout', lambda connection, record, proxy: checked_out.add(id(connection)))
        event.listen(self.engine, 'checkin', lambda connection, record: checked_out.discard(id(connection)))
        def save(*args):
            self.assertFalse(checked_out)
            return 'images/company/1/saved.png', 'https://img.example/saved.png'
        async def download(*args):
            self.assertFalse(checked_out)
            return content.getvalue()
        with patch.object(main, 'SessionLocal', self.sessions), patch.object(image_files, 'download_image', side_effect=download), patch.object(image_files, 'save_content_image', side_effect=save):
            urls = await main.persist_generated_images(['https://example.com/result.png'], 1, 1)
        self.assertEqual(urls, ['https://img.example/saved.png'])
        self.assertFalse(checked_out)

    async def test_no_database_connection_during_network_or_storage_and_timing(self):
        task_id = self.add_task()
        checked_out = set()
        event.listen(self.engine, 'checkout', lambda connection, record, proxy: checked_out.add(id(connection)))
        event.listen(self.engine, 'checkin', lambda connection, record: checked_out.discard(id(connection)))
        async def poll(*args, **kwargs):
            self.assertFalse(checked_out)
            self.assertIs(kwargs['client'], client)
            await asyncio.sleep(.005)
            return ['https://example.com/result.png']
        async def persist(*args):
            self.assertFalse(checked_out)
            return ['https://img.example/saved.png']
        metrics = worker.QueryMetrics()
        last = {}
        async with httpx.AsyncClient() as client:
            with patch.object(task_jobs, 'poll_async_generation', side_effect=poll), patch.object(task_jobs, 'persist_generated_images', side_effect=persist):
                result = await worker.process_result(task_id, client=client, metrics=metrics,
                    enqueued_at=time.monotonic() - .01, last_polls=last)
        self.assertEqual(result, 'succeeded')
        self.assertIn('persist_ms', metrics.timings)
        self.assertIn('query_ms', metrics.timings)
        self.assertIn('queue_wait_ms', metrics.timings)
        self.assertNotIn('poll_gap_ms', metrics.timings)
        self.assertEqual(metrics.requests, 1)
        with self.sessions() as db:
            self.assertEqual(db.get(PodTask, task_id).status, TaskStatus.AWAITING_SELECTION)
            self.assertEqual(db.get(PodTask, task_id).result_urls, ['https://img.example/saved.png'])

    async def test_pending_failure_isolation_terminal_and_storage_failure(self):
        for error, expected in ((None, 'pending'), (httpx.ReadTimeout('slow'), 'retry'),
                                (ProviderError('server 503'), 'retry'),
                                (ProviderTaskTerminalError('rejected'), 'failed')):
            task_id = self.add_task()
            poll = AsyncMock(return_value=None, side_effect=error)
            metrics = worker.QueryMetrics()
            with patch.object(task_jobs, 'poll_async_generation', poll):
                self.assertEqual(await worker.process_result(task_id, metrics=metrics), expected)
            self.assertNotIn('persist_ms', metrics.timings)
            with self.sessions() as db:
                self.assertEqual(db.get(PodTask, task_id).status,
                    TaskStatus.FAILED if expected == 'failed' else TaskStatus.RUNNING)
        task_id = self.add_task()
        with patch.object(task_jobs, 'poll_async_generation', new=AsyncMock(return_value=['remote'])), patch.object(task_jobs, 'persist_generated_images', new=AsyncMock(side_effect=RuntimeError('storage offline'))):
            self.assertEqual(await worker.process_result(task_id), 'retry')
        with self.sessions() as db:
            self.assertEqual(db.get(PodTask, task_id).status, TaskStatus.RUNNING)
            self.assertIn('转存临时失败', db.get(PodTask, task_id).failure_reason)

    async def test_old_query_cannot_overwrite_changed_provider_task(self):
        task_id = self.add_task()
        async def poll(*args):
            with self.sessions() as db:
                task = db.get(PodTask, task_id)
                task.provider_task_id = 'new-provider-id'
                task.failure_reason = 'new attempt'
                db.commit()
            return None
        with patch.object(task_jobs, 'poll_async_generation', side_effect=poll):
            self.assertEqual(await worker.process_result(task_id), 'skipped')
        with self.sessions() as db:
            self.assertEqual(db.get(PodTask, task_id).failure_reason, 'new attempt')

    async def test_rate_limit_shared_models_and_redacted_error(self):
        task_id = self.add_task('grsai-gpt-image-2')
        pacer = worker.QueryPacer(.001)
        with patch.object(task_jobs, 'poll_async_generation', new=AsyncMock(side_effect=ProviderRateLimitError('15'))):
            self.assertEqual(await worker.process_result(task_id, pacer=pacer), 'rate_limited')
        self.assertFalse(pacer.available((1, 1, 'grsai')))
        self.assertTrue(pacer.available((1, 2, 'grsai')))
        message = 'member-key https://example.com/result?signature=private'
        with patch.object(task_jobs, 'poll_async_generation', new=AsyncMock(side_effect=ProviderError(message))):
            with self.assertLogs(worker.logger, level='WARNING') as logs:
                await worker.process_result(task_id)
        self.assertNotIn('member-key', str(logs.output))
        self.assertNotIn('signature=private', str(logs.output))

    async def test_repoll_gap_and_slow_warning(self):
        task_id = self.add_task()
        metrics = worker.QueryMetrics()
        polls = {}
        now = [20.0]
        pacer = worker.QueryPacer(.001, clock=lambda: now[0])
        async def poll(*args):
            now[0] += 11
            return None
        with patch.object(task_jobs, 'poll_async_generation', side_effect=poll):
            with self.assertLogs(worker.logger, level='WARNING') as logs:
                await worker.process_result(task_id, pacer=pacer, metrics=metrics, last_polls=polls)
                await worker.process_result(task_id, pacer=pacer, metrics=metrics, last_polls=polls)
        self.assertIn('结果慢查询', str(logs.output))
        self.assertEqual(metrics.timings['poll_gap_ms'].report()['avg'], 11000)

    def test_settings_validation_and_legacy_update_preserves_concurrency(self):
        from pydantic import ValidationError
        for value in (0, 21, 1.5, True, '5'):
            with self.assertRaises(ValidationError):
                TaskQueueSettingUpdate(result_concurrency=value)
        with self.sessions() as db:
            user = db.get(User, 1)
            updated = main.update_task_queue_settings(TaskQueueSettingUpdate(
                submit_interval_ms=50, result_interval_ms=10, result_concurrency=8), user=user, db=db)
            self.assertEqual(updated['result_concurrency'], 8)
            legacy = main.update_task_queue_settings(TaskQueueSettingUpdate(
                submit_interval_ms=50, result_interval_ms=10), user=user, db=db)
            self.assertEqual(legacy['result_concurrency'], 8)
            self.assertEqual(legacy['result_interval_ms'], 10)


class ProviderConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_client_per_request_authorization_and_ownership(self):
        seen = []
        async def respond(request):
            seen.append(request.headers['Authorization'])
            return httpx.Response(200, json={'status': 'running'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await asyncio.gather(*[ai_providers.poll_async_generation('grsai', str(i), key, client=client)
                                   for i, key in enumerate(('first-key', 'second-key'))])
            self.assertFalse(client.is_closed)
            self.assertNotIn('Authorization', client.headers)
        self.assertEqual(seen, ['Bearer first-key', 'Bearer second-key'])
        self.assertTrue(client.is_closed)

    async def test_fallback_client_owned_and_closed(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={'status': 'running'})))
        with patch.object(ai_providers.httpx, 'AsyncClient', return_value=client):
            await ai_providers.poll_async_generation('grsai', 'task', 'key')
        self.assertTrue(client.is_closed)

    async def test_retry_after_parser_and_query_429(self):
        for header, expected in ((None, 5), ('bad', 5), ('0', 1), ('999', 300), ('nan', 5), ('12', 12)):
            self.assertEqual(ProviderRateLimitError(header).retry_after_seconds, expected)
        future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
        self.assertGreater(ProviderRateLimitError(future).retry_after_seconds, 28)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(429, headers={'Retry-After': '12'}, text='private response'))) as client:
            with self.assertRaises(ProviderRateLimitError) as raised:
                await ai_providers.poll_async_generation('grsai', 'task', 'key', client=client)
        self.assertEqual(raised.exception.retry_after_seconds, 12)
        self.assertNotIn('private response', str(raised.exception))

    async def test_invalid_query_json_does_not_log_signed_urls(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, text='https://example.com/image?signature=private'))) as client:
            with self.assertLogs('app.ai_providers', level='ERROR') as logs:
                with self.assertRaises(ProviderError):
                    await ai_providers.poll_async_generation('grsai', 'task', 'key', client=client)
        self.assertNotIn('signature=private', str(logs.output))
