import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, task_jobs
from app.ai_providers import GrsaiProvider, ProviderError, ProviderTaskTerminalError
from app.config import Settings
from app.database import Base
from app.models import AIProviderSetting, MaterialAsset, PodTask, ProductDraft, ProductTemplate, Role, TaskQueueSetting, TaskStatus, User
from app.schemas import PodTaskCreate


class TaskJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                TaskQueueSetting(id=1, submit_interval_seconds=1, result_interval_seconds=5),
                AIProviderSetting(provider="grsai", display_name="Grsai", model="nano", enabled=True, is_default=True, images_per_task=2),
                AIProviderSetting(provider="seedream", display_name="Seedream", model="seed", enabled=True, is_default=False, images_per_task=1),
                ProductTemplate(id=1, company_id=1, name="Template", cover_url="https://img.example/template.png"),
                User(id=1, company_id=1, email="operator@example.com", name="Operator", password_hash="x", role=Role.MEMBER),
            ])
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def fake_get_db(self):
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def add_task(self, *, status=TaskStatus.QUEUED, provider_task_id=None) -> int:
        with self.session_factory() as db:
            task = PodTask(
                company_id=1, template_id=1, created_by=1, status=status,
                parameters={"ratio": "1:1", "quality": "1K", "creative_requirement": "test", "print_urls": ["https://img.example/print.png"], "print_url": "https://img.example/print.png"},
                result_urls=[], result_map=[], provider="grsai", provider_model="nano", provider_task_id=provider_task_id,
            )
            db.add(task); db.commit(); db.refresh(task)
            return task.id

    def test_bulk_create_splits_into_independent_tasks(self) -> None:
        payload = PodTaskCreate(
            template_id=1, provider="grsai", creative_requirement="test",
            print_urls=[f"https://img.example/creative/{index}.png" for index in range(5)],
        )
        with self.session_factory() as db, patch.object(main, "is_company_r2_url", return_value=True), patch.object(main, "provider_has_credentials", return_value=True):
            user = db.get(User, 1)
            response = main.create_task(payload, user=user, db=db)
            tasks = db.scalars(select(PodTask).order_by(PodTask.id)).all()
        self.assertEqual(response["total"], 3)
        self.assertEqual([len(task.parameters["print_urls"]) for task in tasks], [2, 2, 1])
        self.assertTrue(all(task.status == TaskStatus.QUEUED for task in tasks))

    def test_submit_retries_twice_with_same_idempotency_key(self) -> None:
        task_id = self.add_task()
        requests = []

        async def submit(_, request):
            requests.append(request)
            if len(requests) < 3:
                raise ProviderError("temporary")
            return {"id": "provider-1"}, "", {}

        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "queue_interval", return_value=1), patch.object(task_jobs, "submit_async_generation", side_effect=submit):
            sleep = AsyncMock()
            asyncio.run(task_jobs.process_submission_task(task_id, sleep=sleep))
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            self.assertEqual(task.status, TaskStatus.RUNNING)
            self.assertEqual(task.submit_attempts, 3)
            self.assertEqual(task.provider_task_id, "provider-1")
        self.assertEqual([request.idempotency_key for request in requests], [f"haitoro-task-{task_id}"] * 3)
        self.assertEqual(sleep.await_count, 2)

    def test_sync_provider_completes_in_submit_worker(self) -> None:
        task_id = self.add_task()
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            task.provider = "seedream"; task.provider_model = "seed"
            db.commit()
        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "generate", new=AsyncMock(return_value=["https://img.example/result.png"])), patch.object(task_jobs, "persist_generated_images", new=AsyncMock(side_effect=lambda urls, *_: urls)):
            asyncio.run(task_jobs.process_submission_task(task_id, sleep=AsyncMock()))
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            self.assertEqual(task.status, TaskStatus.AWAITING_SELECTION)
            self.assertEqual(task.result_urls, ["https://img.example/result.png"])
            self.assertEqual(task.result_map[0]["print_url"], "https://img.example/print.png")

    def test_three_submit_failures_are_terminal(self) -> None:
        task_id = self.add_task()
        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "queue_interval", return_value=1), patch.object(task_jobs, "submit_async_generation", new=AsyncMock(side_effect=ProviderError("offline"))):
            sleep = AsyncMock()
            asyncio.run(task_jobs.process_submission_task(task_id, sleep=sleep))
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            self.assertEqual(task.status, TaskStatus.FAILED)
            self.assertEqual(task.submit_attempts, 3)
        self.assertEqual(sleep.await_count, 2)

    def test_result_pending_and_query_error_remain_running(self) -> None:
        task_id = self.add_task(status=TaskStatus.RUNNING, provider_task_id="provider-1")
        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "poll_async_generation", new=AsyncMock(return_value=None)):
            asyncio.run(task_jobs.process_result_task(task_id))
        with self.session_factory() as db:
            self.assertEqual(db.get(PodTask, task_id).status, TaskStatus.RUNNING)
        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "poll_async_generation", new=AsyncMock(side_effect=ProviderError("network"))):
            asyncio.run(task_jobs.process_result_task(task_id))
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            self.assertEqual(task.status, TaskStatus.RUNNING)
            self.assertIn("下轮继续", task.failure_reason)

    def test_result_cycle_processes_snapshot_once_in_creation_order(self) -> None:
        first = self.add_task(status=TaskStatus.RUNNING, provider_task_id="provider-1")
        second = self.add_task(status=TaskStatus.RUNNING, provider_task_id="provider-2")
        visited = []

        async def visit(task_id):
            visited.append(task_id)

        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "process_result_task", side_effect=visit), patch.object(task_jobs, "queue_interval", return_value=5):
            sleep = AsyncMock()
            count = asyncio.run(task_jobs.run_cycle("result", sleep=sleep))
        self.assertEqual(count, 2)
        self.assertEqual(visited, [first, second])
        self.assertEqual(sleep.await_count, 2)

    def test_terminal_provider_failure_marks_task_failed(self) -> None:
        task_id = self.add_task(status=TaskStatus.RUNNING, provider_task_id="provider-1")
        with patch.object(task_jobs, "get_db", self.fake_get_db), patch.object(task_jobs, "poll_async_generation", new=AsyncMock(side_effect=ProviderTaskTerminalError("rejected"))):
            asyncio.run(task_jobs.process_result_task(task_id))
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            self.assertEqual(task.status, TaskStatus.FAILED)
            self.assertEqual(task.provider_task_id, "provider-1")

    def test_grsai_failed_status_is_terminal(self) -> None:
        response = httpx.Response(200, request=httpx.Request("GET", "https://grsai.example/result"), json={"status": "failed", "error": "rejected"})
        client = AsyncMock(); client.get.return_value = response
        with self.assertRaises(ProviderTaskTerminalError):
            asyncio.run(GrsaiProvider().poll_once("provider-1", Settings(grsai_api_key="test"), client))

    def test_task_summary_omits_bulk_payload_and_has_no_batches(self) -> None:
        task_id = self.add_task()
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            summary = main.serialize_task_view(task, "Operator", "Template", include_details=False)
            detail = main.serialize_task_view(task, "Operator", "Template", include_details=True)
        self.assertNotIn("print_urls", summary["parameters"])
        self.assertNotIn("batches", summary)
        self.assertEqual(len(detail["parameters"]["print_urls"]), 1)

    def test_manual_retry_resets_failed_task(self) -> None:
        task_id = self.add_task(status=TaskStatus.FAILED, provider_task_id="provider-1")
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            task.submit_attempts = 3; task.failure_reason = "rejected"
            db.commit()
            response = main.retry_task(task_id, user=db.get(User, 1), db=db)
            task = db.get(PodTask, task_id)
        self.assertEqual(response["status"], "queued")
        self.assertEqual(task.submit_attempts, 0)
        self.assertIsNone(task.provider_task_id)

    def test_legacy_batch_migration_clears_tasks_and_preserves_assets(self) -> None:
        task_id = self.add_task()
        with self.session_factory() as db:
            db.add(MaterialAsset(company_id=1, source_task_id=task_id, url="https://img.example/material.png", name="material", claimed_by=1))
            db.add(ProductDraft(company_id=1, source_task_id=task_id, title="draft", image_urls=[], sku_items=[]))
            db.commit()
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE pod_task_batches (id INTEGER PRIMARY KEY)"))
        with patch.object(main, "engine", self.engine):
            main.ensure_schema()
        with self.session_factory() as db:
            self.assertEqual(db.scalar(select(PodTask.id)), None)
            self.assertIsNone(db.scalar(select(MaterialAsset.source_task_id)))
            self.assertIsNone(db.scalar(select(ProductDraft.source_task_id)))
        self.assertNotIn("pod_task_batches", inspect(self.engine).get_table_names())


if __name__ == "__main__":
    unittest.main()
