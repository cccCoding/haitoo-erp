import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, task_jobs
from app.ai_providers import GrsaiProvider, ProviderError, ProviderTaskTerminalError
from app.config import Settings
from app.database import Base
from app.credentials import encrypt_secret
from app.models import AIProviderSetting, Company, MaterialAsset, PodTask, ProductDraft, ProductTemplate, Role, TaskQueueSetting, TaskStatus, User, UserAIProviderCredential, UserTemplatePrompt, UserTemplateWhiteImage
from app.schemas import AIProviderCredentialUpdate, ClaimMaterials, DraftImageApply, DraftImagesConfirm, DraftImageTaskCreate, DraftOrderedImageSelection, DraftUpdate, MaterialDownloadInput, MaterialDraftCreate, PodTaskCreate, TemplateCreate, UserTemplatePromptCreate


class TaskJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                Company(id=1, name="Test Company", miaoshou_app_id="app-id", miaoshou_secret_encrypted="encrypted-secret"),
                TaskQueueSetting(id=1, submit_interval_seconds=1, result_interval_seconds=5),
                AIProviderSetting(provider="grsai", display_name="Grsai", model="nano", enabled=True, is_default=True, images_per_task=2),
                AIProviderSetting(provider="seedream", display_name="Seedream", model="seed", enabled=True, is_default=False, images_per_task=1),
                ProductTemplate(id=1, company_id=1, name="M05L", cover_url="https://img.example/template.png"),
                User(id=1, company_id=1, email="operator@example.com", name="Operator", user_code="AA", password_hash="x", role=Role.MEMBER),
                User(id=2, company_id=1, email="admin@example.com", name="Admin", user_code="AB", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=3, company_id=1, email="other@example.com", name="Other", user_code="AC", password_hash="x", role=Role.MEMBER),
                UserAIProviderCredential(company_id=1, user_id=1, provider="grsai", secret_encrypted=encrypt_secret("member-key")),
                UserAIProviderCredential(company_id=1, user_id=1, provider="seedream", secret_encrypted=encrypt_secret("seedream-member-key")),
                UserTemplateWhiteImage(id=1, company_id=1, user_id=1, template_id=1, name="Front", image_url="https://img.example/template-white/1.png"),
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
            template_id=1, white_image_id=1, provider="grsai", creative_requirement="test",
            print_urls=[f"https://img.example/creative/{index}.png" for index in range(5)],
        )
        with self.session_factory() as db, patch.object(main, "is_company_r2_url", return_value=True):
            user = db.get(User, 1)
            response = main.create_task(payload, user=user, db=db)
            tasks = db.scalars(select(PodTask).order_by(PodTask.id)).all()
        self.assertEqual(response["total"], 3)
        self.assertEqual([len(task.parameters["print_urls"]) for task in tasks], [2, 2, 1])
        self.assertTrue(all(task.status == TaskStatus.QUEUED for task in tasks))

    def test_submit_retries_twice_with_same_idempotency_key(self) -> None:
        task_id = self.add_task()
        requests = []

        async def submit(_, request, api_key):
            requests.append(request)
            self.assertEqual(api_key, "member-key")
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

    def test_member_credential_status_and_update_never_return_secret(self) -> None:
        with self.session_factory() as db:
            admin = db.get(User, 2)
            rows = main.list_members(user=admin, db=db)
            member_row = next(row for row in rows if row["id"] == 1)
            response = main.update_member_ai_provider_credential(
                1, "grsai", AIProviderCredentialUpdate(api_key="replacement-key"), user=admin, db=db,
            )
            stored = db.scalar(select(UserAIProviderCredential).where(UserAIProviderCredential.user_id == 1))
        self.assertTrue(member_row["ai_provider_credentials"]["grsai"])
        self.assertEqual(member_row["ai_provider_credential_previews"]["grsai"], "mem...ey")
        self.assertNotIn("member-key", str(member_row))
        self.assertEqual(response, {"member_id": 1, "provider": "grsai", "configured": True})
        self.assertNotIn("replacement-key", stored.secret_encrypted)

    def test_api_key_preview_keeps_only_prefix_and_suffix(self) -> None:
        self.assertEqual(main.mask_api_key("sk-a08-example-secret-71465"), "sk-a08...71465")

    def test_available_providers_include_current_users_credential_status_without_secret(self) -> None:
        with self.session_factory() as db:
            member_rows = main.list_available_ai_providers(user=db.get(User, 1), db=db)
            admin_rows = main.list_available_ai_providers(user=db.get(User, 2), db=db)

        self.assertTrue(all(row["credential_configured"] for row in member_rows))
        self.assertTrue(all(not row["credential_configured"] for row in admin_rows))
        self.assertTrue(all("api_key" not in row and "secret_encrypted" not in row for row in member_rows))

    def test_task_creation_requires_its_creators_credential(self) -> None:
        payload = PodTaskCreate(
            template_id=1, white_image_id=1, provider="grsai", creative_requirement="test",
            print_urls=["https://img.example/creative/1.png"],
        )
        with self.session_factory() as db, patch.object(main, "is_company_r2_url", return_value=True):
            credential = db.scalar(select(UserAIProviderCredential).where(UserAIProviderCredential.user_id == 1))
            db.delete(credential); db.commit()
            with self.assertRaisesRegex(Exception, "个人 Grsai 平台密钥"):
                main.create_task(payload, user=db.get(User, 1), db=db)

    def test_task_snapshots_and_worker_uses_selected_white_image(self) -> None:
        payload = PodTaskCreate(
            template_id=1, white_image_id=1, provider="grsai", creative_requirement="test",
            print_urls=["https://img.example/creative/1.png"],
        )
        with self.session_factory() as db, patch.object(main, "is_company_r2_url", return_value=True):
            response = main.create_task(payload, user=db.get(User, 1), db=db)
            task = db.get(PodTask, response["items"][0]["id"])
            request = task_jobs._request_for(task, db.get(ProductTemplate, 1))
        self.assertEqual(task.parameters["white_image_name"], "Front")
        self.assertEqual(request.template_url, "https://img.example/template-white/1.png")

    def test_member_cannot_use_or_read_another_members_resources(self) -> None:
        with self.session_factory() as db:
            other_image = UserTemplateWhiteImage(
                company_id=1, user_id=3, template_id=1, name="Other Front",
                image_url="https://img.example/template-white/other.png",
            )
            db.add(other_image); db.commit(); db.refresh(other_image)
            payload = PodTaskCreate(
                template_id=1, white_image_id=other_image.id, provider="grsai", creative_requirement="test",
                print_urls=["https://img.example/creative/1.png"],
            )
            with patch.object(main, "is_company_r2_url", return_value=True), self.assertRaisesRegex(Exception, "自己的产品白底图"):
                main.create_task(payload, user=db.get(User, 1), db=db)
            with self.assertRaisesRegex(Exception, "只能管理自己"):
                main.list_user_template_resources(template_id=1, user_id=3, user=db.get(User, 1), db=db)

    def test_resource_management_can_list_all_templates_without_ai_selection(self) -> None:
        with self.session_factory() as db:
            db.add_all([
                ProductTemplate(id=2, company_id=1, name="M06L", cover_url="https://img.example/template-2.png"),
                UserTemplateWhiteImage(id=2, company_id=1, user_id=1, template_id=2, name="Back", image_url="https://img.example/template-white/2.png"),
                UserTemplatePrompt(company_id=1, user_id=1, template_id=2, name="Soft", content="soft fabric"),
            ])
            db.commit()
            user = db.get(User, 1)
            all_resources = main.list_user_template_resources(user=user, db=db)
            filtered_resources = main.list_user_template_resources(template_id=1, user=user, db=db)

        self.assertEqual({item["template_id"] for item in all_resources["white_images"]}, {1, 2})
        self.assertEqual([item["template_id"] for item in all_resources["prompts"]], [2])
        self.assertEqual([item["template_id"] for item in filtered_resources["white_images"]], [1])
        self.assertEqual(filtered_resources["prompts"], [])

    def test_admin_can_manage_member_prompt_and_other_member_sees_redacted_task(self) -> None:
        with self.session_factory() as db:
            admin = db.get(User, 2)
            created = main.create_user_template_prompt(
                UserTemplatePromptCreate(template_id=1, user_id=1, name="Natural", content="private prompt"),
                user=admin, db=db,
            )
            managed = main.list_user_template_resources(template_id=1, user_id=1, user=admin, db=db)
            self.assertEqual(managed["prompts"][0]["id"], created["id"])
            task = PodTask(
                company_id=1, template_id=1, created_by=1, status=TaskStatus.QUEUED,
                parameters={"ratio":"1:1","quality":"1K","creative_requirement":"private prompt","white_image_id":1,"white_image_name":"Front","white_image_url":"https://img.example/template-white/1.png","print_urls":["https://img.example/print.png"]},
                result_urls=[], result_map=[], provider="grsai", provider_model="nano",
            )
            db.add(task); db.commit(); db.refresh(task)
            hidden = main.serialize_task_view(task, "Operator", "Template", db.get(User, 3), include_details=True)
            visible = main.serialize_task_view(task, "Operator", "Template", admin, include_details=True)
        self.assertTrue(hidden["parameters"]["private_creative_configuration"])
        self.assertNotIn("white_image_url", hidden["parameters"])
        self.assertIsNone(hidden["parameters"]["creative_requirement"])
        self.assertEqual(visible["parameters"]["creative_requirement"], "private prompt")

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
            asyncio.run(GrsaiProvider().poll_once("provider-1", "test", Settings(), client))

    def test_grsai_invalid_json_logs_complete_raw_response(self) -> None:
        raw_body = "event: error\ndata: upstream returned HTML <bad gateway>\n"
        response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://grsai.example/generate"),
            headers={"content-type": "text/event-stream"},
            text=raw_body,
        )

        with self.assertLogs("app.ai_providers", level="ERROR") as captured:
            with self.assertRaisesRegex(ProviderError, "无效的 JSON 响应"):
                GrsaiProvider._response_data(response)

        message = "\n".join(captured.output)
        self.assertIn("status_code=200", message)
        self.assertIn("content_type=text/event-stream", message)
        self.assertIn(repr(raw_body), message)

    def test_task_summary_omits_bulk_payload_and_has_no_batches(self) -> None:
        task_id = self.add_task()
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            viewer = db.get(User, 1)
            summary = main.serialize_task_view(task, "Operator", "Template", viewer, include_details=False)
            detail = main.serialize_task_view(task, "Operator", "Template", viewer, include_details=True)
        self.assertNotIn("print_urls", summary["parameters"])
        self.assertNotIn("batches", summary)
        self.assertEqual(len(detail["parameters"]["print_urls"]), 1)

    def test_members_only_see_their_tasks_and_admin_can_filter_by_creator(self) -> None:
        own_task_id = self.add_task()
        with self.session_factory() as db:
            other_task = PodTask(
                company_id=1, template_id=1, created_by=3, status=TaskStatus.QUEUED,
                parameters={}, result_urls=[], result_map=[], provider="grsai", provider_model="nano",
            )
            db.add(other_task); db.commit(); db.refresh(other_task)

            member_page = main.list_tasks(page=1, page_size=20, creator_id=None, user=db.get(User, 1), db=db)
            admin_page = main.list_tasks(page=1, page_size=20, creator_id=3, user=db.get(User, 2), db=db)

            self.assertEqual([item["id"] for item in member_page["items"]], [own_task_id])
            self.assertEqual([item["id"] for item in admin_page["items"]], [other_task.id])
            self.assertFalse(main.can_access_task(other_task, db.get(User, 1)))
            self.assertTrue(main.can_access_task(other_task, db.get(User, 2)))

    def test_task_list_filters_by_status_and_created_time_range(self) -> None:
        older_id = self.add_task(status=TaskStatus.AWAITING_SELECTION)
        newer_id = self.add_task(status=TaskStatus.COMPLETED)
        with self.session_factory() as db:
            db.get(PodTask, older_id).created_at = datetime(2026, 9, 8, 1, 0)
            db.get(PodTask, newer_id).created_at = datetime(2026, 9, 9, 2, 30)
            db.commit()
            utc_plus_8 = timezone(timedelta(hours=8))
            result = main.list_tasks(
                page=1,
                page_size=20,
                creator_id=None,
                status=TaskStatus.COMPLETED,
                created_from=datetime(2026, 9, 9, 10, 0, tzinfo=utc_plus_8),
                created_to=datetime(2026, 9, 9, 11, 0, tzinfo=utc_plus_8),
                user=db.get(User, 1),
                db=db,
            )

            self.assertEqual([item["id"] for item in result["items"]], [newer_id])
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["status_counts"], {"completed": 1})

            with self.assertRaisesRegex(HTTPException, "开始时间不能晚于结束时间"):
                main.list_tasks(
                    page=1, page_size=20, creator_id=None, status=None,
                    created_from=datetime(2026, 9, 10), created_to=datetime(2026, 9, 9),
                    user=db.get(User, 1), db=db,
                )

    def test_members_only_see_their_materials_and_template_update_route_is_removed(self) -> None:
        with self.session_factory() as db:
            own = MaterialAsset(company_id=1, template_id=1, url="https://img.example/own.png", name="own", claimed_by=1)
            own_newer = MaterialAsset(company_id=1, template_id=1, url="https://img.example/own-newer.png", name="own-newer", claimed_by=1)
            other = MaterialAsset(company_id=1, template_id=1, url="https://img.example/other.png", name="other", claimed_by=3)
            db.add_all([own, own_newer, other]); db.commit(); db.refresh(own); db.refresh(own_newer); db.refresh(other)

            member_assets = main.list_material_assets(page=2, page_size=1, creator_id=None, template_id=1, user=db.get(User, 1), db=db)
            admin_assets = main.list_material_assets(page=1, page_size=20, creator_id=3, template_id=None, user=db.get(User, 2), db=db)
            self.assertEqual([item["id"] for item in member_assets["items"]], [own.id])
            self.assertEqual(member_assets["total"], 2)
            self.assertEqual(member_assets["page"], 2)
            self.assertEqual([item["id"] for item in admin_assets["items"]], [other.id])
            self.assertEqual(admin_assets["items"][0]["created_by_name"], "Other")
            self.assertEqual(admin_assets["items"][0]["source_type"], "local_upload")
            self.assertEqual(admin_assets["total"], 1)

            route_paths = {route.path for route in main.app.routes}
            self.assertNotIn("/material-assets/template", route_paths)

    def test_material_download_uses_sku_as_single_image_and_zip_filenames(self) -> None:
        with self.session_factory() as db:
            first = MaterialAsset(company_id=1, template_id=1, url="https://img.example/first.png", name="效果图", sku="M05LAA111111", claimed_by=1)
            second = MaterialAsset(company_id=1, template_id=1, url="https://img.example/second.png", name="效果图", sku="M05LAA222222", claimed_by=1)
            db.add_all([first, second]); db.commit(); db.refresh(first); db.refresh(second)
            member = db.get(User, 1)

            transport = httpx.MockTransport(lambda request: httpx.Response(200, content=request.url.path.encode(), headers={"content-type": "image/png"}))
            real_async_client = httpx.AsyncClient
            with patch.object(main.httpx, "AsyncClient", side_effect=lambda **kwargs: real_async_client(transport=transport, **kwargs)):
                single = asyncio.run(main.download_material_assets(MaterialDownloadInput(material_asset_ids=[first.id]), user=member, db=db))
                bundled = asyncio.run(main.download_material_assets(MaterialDownloadInput(material_asset_ids=[first.id, second.id]), user=member, db=db))

            self.assertEqual(single.media_type, "image/png")
            self.assertEqual(single.body, b"/first.png")
            self.assertIn("M05LAA111111.png", single.headers["content-disposition"])
            self.assertEqual(bundled.media_type, "application/zip")
            with zipfile.ZipFile(BytesIO(bundled.body)) as archive:
                self.assertEqual(archive.namelist(), ["M05LAA111111.png", "M05LAA222222.png"])
                self.assertEqual(archive.read("M05LAA111111.png"), b"/first.png")

    def test_material_download_rejects_assets_outside_member_scope(self) -> None:
        with self.session_factory() as db:
            other = MaterialAsset(company_id=1, template_id=1, url="https://img.example/other.png", name="other", sku="M05LAA333333", claimed_by=3)
            db.add(other); db.commit(); db.refresh(other)
            with self.assertRaisesRegex(HTTPException, "素材不存在或无权下载"):
                asyncio.run(main.download_material_assets(MaterialDownloadInput(material_asset_ids=[other.id]), user=db.get(User, 1), db=db))

    def test_template_name_is_normalized_for_sku_prefix(self) -> None:
        payload = TemplateCreate(name="y1", group_id=1)
        self.assertEqual(payload.name, "Y1")
        self.assertEqual(MaterialAsset.__table__.c.sku.type.length, 24)
        for invalid_name in ("中文", "M-05", "ABCDEF"):
            with self.assertRaises(Exception):
                TemplateCreate(name=invalid_name, group_id=1)

    def test_material_sku_retries_database_collision(self) -> None:
        with self.session_factory() as db:
            db.add(MaterialAsset(
                company_id=1, template_id=1, url="https://img.example/existing.png",
                name="existing", sku="M05LAAAAAAAA", claimed_by=1,
            ))
            db.commit()
            with patch.object(main.secrets, "choice", side_effect=list("AAAAAABBBBBB")):
                asset = main.add_material_asset_with_sku(
                    db, template=db.get(ProductTemplate, 1), owner=db.get(User, 1), company_id=1,
                    source_task_id=None, url="https://img.example/new.png", name="new",
                )
                db.commit()
            self.assertEqual(asset.sku, "M05LAABBBBBB")

    def test_claimed_material_gets_permanent_sku_and_duplicate_claim_reuses_it(self) -> None:
        task_id = self.add_task(status=TaskStatus.AWAITING_SELECTION)
        result_url = "https://img.example/result.png"
        with self.session_factory() as db:
            task = db.get(PodTask, task_id)
            task.result_urls = [result_url]
            db.commit()
            payload = ClaimMaterials(result_urls=[result_url])
            first = main.claim_task_materials(task_id, payload, user=db.get(User, 1), db=db)
            asset = db.scalar(select(MaterialAsset).where(MaterialAsset.source_task_id == task_id))
            original_sku = asset.sku
            second = main.claim_task_materials(task_id, payload, user=db.get(User, 1), db=db)
            self.assertRegex(original_sku, r"^M05LAA[A-Z0-9]{6}$")
            self.assertEqual(first["claimed"], 1)
            self.assertEqual(second["claimed"], 0)
            self.assertEqual(asset.sku, original_sku)

    def test_material_draft_reuses_skus_and_rejects_legacy_assets(self) -> None:
        with self.session_factory() as db:
            current = MaterialAsset(company_id=1, template_id=1, url="https://img.example/current.png", name="current", sku="M05LAA123456", claimed_by=1)
            legacy = MaterialAsset(company_id=1, template_id=1, url="https://img.example/legacy.png", name="legacy", claimed_by=1)
            db.add_all([current, legacy]); db.commit(); db.refresh(current); db.refresh(legacy)
            payload = MaterialDraftCreate(template_id=1, material_asset_ids=[current.id], title="D" * 25)
            draft = main.create_draft_from_material_assets(payload, user=db.get(User, 1), db=db)
            self.assertEqual(draft["sku_items"], [{"image_url": current.url, "size": None, "sku": current.sku}])
            self.assertEqual(draft["status"], "pending_publish")
            self.assertIsNone(draft["miaoshou_collect_box_id"])
            self.assertIsNone(draft["tiktok_collect_box_id"])
            with self.assertRaisesRegex(Exception, "无 SKU"):
                main.create_draft_from_material_assets(
                    MaterialDraftCreate(template_id=1, material_asset_ids=[legacy.id], title="L" * 25),
                    user=db.get(User, 1), db=db,
                )

    def test_draft_title_requires_25_to_255_trimmed_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 25 characters"):
            MaterialDraftCreate(template_id=1, material_asset_ids=[1], title="短标题")
        with self.assertRaisesRegex(ValueError, "at most 255 characters"):
            DraftUpdate(title="T" * 256, product_description=None)
        payload = DraftUpdate(title=f"  {'T' * 25}  ", product_description=None)
        self.assertEqual(payload.title, "T" * 25)

    def test_tiktok_claim_persists_miaoshou_id_before_claiming(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25,
                image_urls=["https://img.example/product.png"],
                sku_items=[{"image_url": "https://img.example/product.png", "size": None, "sku": "M05LAA123456"}],
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)

            async def create_common(current_draft, _company, _template):
                current_draft.miaoshou_collect_box_id = "123"
                return "123"

            async def fail_claim(current_draft, _company):
                with self.session_factory() as other_db:
                    persisted = other_db.get(ProductDraft, current_draft.id)
                    self.assertEqual(persisted.miaoshou_collect_box_id, "123")
                    self.assertEqual(persisted.status, "published_to_miaoshou")
                raise HTTPException(502, "认领失败")

            with patch.object(main, "create_common_collect_box_detail", side_effect=create_common), patch.object(main, "claim_common_collect_box_to_tiktok", side_effect=fail_claim):
                with self.assertRaisesRegex(HTTPException, "认领失败"):
                    asyncio.run(main.claim_draft_to_tiktok(draft.id, user=db.get(User, 1), db=db))

    def test_task_draft_route_is_removed(self) -> None:
        route_paths = {route.path for route in main.app.routes}
        self.assertNotIn("/tasks/{task_id}/draft", route_paths)

    def test_members_only_see_and_modify_their_drafts(self) -> None:
        with self.session_factory() as db:
            own = ProductDraft(company_id=1, template_id=1, title="own", image_urls=[], sku_items=[], created_by=1, updated_by=1)
            other = ProductDraft(company_id=1, template_id=1, title="other", image_urls=[], sku_items=[], created_by=3, updated_by=3)
            db.add_all([own, other]); db.commit(); db.refresh(own); db.refresh(other)

            member_drafts = main.list_drafts(shop_id=None, creator_id=None, user=db.get(User, 1), db=db)
            admin_drafts = main.list_drafts(shop_id=None, creator_id=3, user=db.get(User, 2), db=db)
            self.assertEqual([item["id"] for item in member_drafts], [own.id])
            self.assertEqual([item["id"] for item in admin_drafts], [other.id])
            self.assertEqual(admin_drafts[0]["created_by_name"], "Other")
            self.assertFalse(main.can_access_draft(other, db.get(User, 1)))
            self.assertTrue(main.can_access_draft(other, db.get(User, 2)))

            with self.assertRaisesRegex(Exception, "商品草稿不存在"):
                main.update_draft(
                    other.id, DraftUpdate(title="Changed product draft title", product_description=None),
                    user=db.get(User, 1), db=db,
                )

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

    def test_carousel_generation_creates_one_task_per_sku(self) -> None:
        sku_items = [
            {"image_url": f"https://img.example/sku-{index}.png", "sku": f"M05LAA{index:06d}", "size": None}
            for index in range(6)
        ]
        with self.session_factory() as db:
            draft = ProductDraft(company_id=1, template_id=1, title="T" * 25, image_urls=[item["image_url"] for item in sku_items], sku_items=sku_items, created_by=1, updated_by=1)
            db.add(draft); db.commit(); db.refresh(draft)
            response = main.create_draft_image_tasks(
                draft.id,
                DraftImageTaskCreate(task_type="carousel", source_skus=[item["sku"] for item in sku_items], creative_requirement="生成轮播图"),
                user=db.get(User, 1), db=db,
            )
            tasks = db.scalars(select(PodTask).where(PodTask.task_type == "carousel").order_by(PodTask.id)).all()
        self.assertEqual(response["total"], 6)
        self.assertEqual([task.parameters["source_sku"] for task in tasks], [item["sku"] for item in sku_items])
        self.assertTrue(all(len(task.parameters["reference_urls"]) == 1 for task in tasks))

    def test_task_list_uses_three_separate_task_types(self) -> None:
        with self.session_factory() as db:
            db.add_all([
                PodTask(company_id=1, template_id=1, created_by=1, task_type="sku_image", status=TaskStatus.QUEUED, parameters={}, result_urls=[], result_map=[]),
                PodTask(company_id=1, template_id=1, created_by=1, task_type="carousel", status=TaskStatus.QUEUED, parameters={}, result_urls=[], result_map=[]),
                PodTask(company_id=1, template_id=1, created_by=1, task_type="main_image", status=TaskStatus.QUEUED, parameters={}, result_urls=[], result_map=[]),
            ])
            db.commit()
            carousel_page = main.list_tasks(page=1, page_size=20, task_type="carousel", creator_id=None, user=db.get(User, 1), db=db)
        self.assertEqual([item["task_type"] for item in carousel_page["items"]], ["carousel"])
        self.assertEqual(carousel_page["task_type_counts"], {"sku_image": 1, "carousel": 1, "main_image": 1})

    def test_first_image_can_reference_unconfirmed_carousel_task_result(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(company_id=1, template_id=1, title="T" * 25, image_urls=[], carousel_items=[], sku_items=[{"sku": "SKU1", "image_url": "https://img.example/sku.png"}], created_by=1, updated_by=1)
            db.add(draft); db.commit(); db.refresh(draft)
            carousel_task = PodTask(
                company_id=1, template_id=1, created_by=1, task_type="carousel",
                status=TaskStatus.AWAITING_SELECTION,
                parameters={"draft_id": draft.id, "source_sku": "SKU1"},
                result_urls=["https://img.example/unconfirmed-carousel.png"], result_map=[],
            )
            db.add(carousel_task); db.commit()
            result = main.create_draft_image_tasks(
                draft.id,
                DraftImageTaskCreate(task_type="main_image", reference_mode="random", reference_urls=["https://img.example/unconfirmed-carousel.png"], creative_requirement="生成主图"),
                user=db.get(User, 1), db=db,
            )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["parameters"]["reference_urls"], ["https://img.example/unconfirmed-carousel.png"])

    def test_first_image_uses_sku_fallback_when_carousel_was_not_generated(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25, image_urls=[], carousel_items=[],
                sku_items=[{"sku": "SKU1", "image_url": "https://img.example/sku.png"}],
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)
            workspace = main.get_draft_image_workspace(draft.id, user=db.get(User, 1), db=db)
            result = main.create_draft_image_tasks(
                draft.id,
                DraftImageTaskCreate(task_type="main_image", reference_mode="random", creative_requirement="生成首图"),
                user=db.get(User, 1), db=db,
            )
        self.assertTrue(workspace["using_sku_fallback"])
        self.assertEqual(workspace["carousel_items"][0]["image_url"], "https://img.example/sku.png")
        self.assertEqual(workspace["published_image_urls"], ["https://img.example/sku.png"])
        self.assertEqual(result["items"][0]["parameters"]["reference_urls"], ["https://img.example/sku.png"])

    def test_main_image_requires_explicit_carousel_removal_at_nine_images(self) -> None:
        carousel = [{"sku": f"SKU{index}", "image_url": f"https://img.example/carousel-{index}.png", "task_id": index} for index in range(9)]
        with self.session_factory() as db:
            draft = ProductDraft(company_id=1, template_id=1, title="T" * 25, image_urls=[item["image_url"] for item in carousel], carousel_items=carousel, sku_items=[{"sku": "BASE", "image_url": "https://img.example/sku.png"}], created_by=1, updated_by=1)
            task = PodTask(company_id=1, template_id=1, created_by=1, task_type="main_image", status=TaskStatus.AWAITING_SELECTION, parameters={"draft_id": 1, "reference_urls": [carousel[0]["image_url"]]}, result_urls=["https://img.example/main.png"], result_map=[])
            db.add_all([draft, task]); db.commit(); db.refresh(draft); db.refresh(task)
            task.parameters = {**task.parameters, "draft_id": draft.id}; db.commit()
            with self.assertRaisesRegex(HTTPException, "请选择移除"):
                main.apply_draft_image_result(draft.id, task.id, DraftImageApply(result_url=task.result_urls[0]), user=db.get(User, 1), db=db)
            result = main.apply_draft_image_result(draft.id, task.id, DraftImageApply(result_url=task.result_urls[0], remove_carousel_sku="SKU8"), user=db.get(User, 1), db=db)
            confirmed = main.confirm_draft_images(draft.id, user=db.get(User, 1), db=db)
        self.assertEqual(result["carousel_items"][0]["image_url"], "https://img.example/main.png")
        self.assertEqual(result["carousel_items"][0]["source_type"], "main_image")
        self.assertEqual(len(result["carousel_items"]), 9)
        self.assertEqual(len(result["published_image_urls"]), 9)
        self.assertEqual(confirmed["image_urls"], result["published_image_urls"])

    def test_confirm_images_applies_staged_selection_in_one_request(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25,
                image_urls=["https://img.example/original.png"], carousel_items=[],
                sku_items=[{"sku": "SKU1", "image_url": "https://img.example/sku.png"}],
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)
            carousel_task = PodTask(
                company_id=1, template_id=1, created_by=1, task_type="carousel",
                status=TaskStatus.AWAITING_SELECTION,
                parameters={"draft_id": draft.id, "source_sku": "SKU1"},
                result_urls=["https://img.example/carousel.png"], result_map=[],
            )
            main_task = PodTask(
                company_id=1, template_id=1, created_by=1, task_type="main_image",
                status=TaskStatus.AWAITING_SELECTION,
                parameters={"draft_id": draft.id},
                result_urls=["https://img.example/main.png"], result_map=[],
            )
            db.add_all([carousel_task, main_task]); db.commit(); db.refresh(carousel_task); db.refresh(main_task)
            carousel_task_id = carousel_task.id
            result = main.confirm_draft_images(
                draft.id,
                DraftImagesConfirm(image_items=[
                    DraftOrderedImageSelection(result_url=main_task.result_urls[0], task_id=main_task.id),
                    DraftOrderedImageSelection(sku="SKU1", result_url=carousel_task.result_urls[0], task_id=carousel_task.id),
                ]),
                user=db.get(User, 1), db=db,
            )
        self.assertEqual(result["image_urls"], ["https://img.example/main.png", "https://img.example/carousel.png"])
        self.assertEqual(result["carousel_items"][1]["task_id"], carousel_task_id)
        self.assertEqual(result["carousel_items"][0]["source_type"], "main_image")

    def test_confirm_images_preserves_dragged_final_order(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25,
                image_urls=[], carousel_items=[],
                sku_items=[
                    {"sku": "SKU1", "image_url": "https://img.example/sku-1.png"},
                    {"sku": "SKU2", "image_url": "https://img.example/sku-2.png"},
                ],
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)
            main_task = PodTask(
                company_id=1, template_id=1, created_by=1, task_type="main_image",
                status=TaskStatus.AWAITING_SELECTION,
                parameters={"draft_id": draft.id},
                result_urls=["https://img.example/ai-main.png"], result_map=[],
            )
            db.add(main_task); db.commit(); db.refresh(main_task)
            result = main.confirm_draft_images(
                draft.id,
                DraftImagesConfirm(image_items=[
                    DraftOrderedImageSelection(result_url="https://img.example/sku-2.png", sku="SKU2"),
                    DraftOrderedImageSelection(result_url=main_task.result_urls[0], task_id=main_task.id),
                    DraftOrderedImageSelection(result_url="https://img.example/sku-1.png", sku="SKU1"),
                ]),
                user=db.get(User, 1), db=db,
            )
            workspace = main.get_draft_image_workspace(draft.id, user=db.get(User, 1), db=db)
        expected = [
            "https://img.example/sku-2.png",
            "https://img.example/ai-main.png",
            "https://img.example/sku-1.png",
        ]
        self.assertEqual(result["image_urls"], expected)
        self.assertEqual(workspace["working_image_urls"], expected)
        self.assertEqual([item["image_url"] for item in result["carousel_items"]], expected)

    def test_multiple_images_from_the_same_sku_can_be_adopted_and_confirmed(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25,
                image_urls=[], carousel_items=[],
                sku_items=[{"sku": "SKU1", "image_url": "https://img.example/sku.png"}],
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)
            tasks = [PodTask(
                company_id=1, template_id=1, created_by=1, task_type="carousel",
                status=TaskStatus.AWAITING_SELECTION,
                parameters={"draft_id": draft.id, "source_sku": "SKU1"},
                result_urls=[f"https://img.example/carousel-{index}.png"], result_map=[],
            ) for index in range(2)]
            db.add_all(tasks); db.commit()
            for task in tasks:
                db.refresh(task)

            first = main.apply_draft_image_result(
                draft.id, tasks[0].id, DraftImageApply(result_url=tasks[0].result_urls[0]),
                user=db.get(User, 1), db=db,
            )
            second = main.apply_draft_image_result(
                draft.id, tasks[1].id, DraftImageApply(result_url=tasks[1].result_urls[0]),
                user=db.get(User, 1), db=db,
            )
            result = main.confirm_draft_images(
                draft.id,
                DraftImagesConfirm(image_items=[
                    DraftOrderedImageSelection(result_url=item["image_url"], sku=item.get("sku"), task_id=item.get("task_id"))
                    for item in second["carousel_items"]
                ]),
                user=db.get(User, 1), db=db,
            )

        self.assertEqual(len(first["carousel_items"]), 2)
        self.assertEqual(len(second["carousel_items"]), 3)
        self.assertEqual([item.get("sku") for item in result["carousel_items"]], ["SKU1", "SKU1", "SKU1"])

    def test_published_draft_images_remain_editable(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25,
                image_urls=["https://img.example/sku-1.png", "https://img.example/sku-2.png"],
                carousel_items=[],
                sku_items=[
                    {"sku": "SKU1", "image_url": "https://img.example/sku-1.png"},
                    {"sku": "SKU2", "image_url": "https://img.example/sku-2.png"},
                ],
                tiktok_collect_box_id="published-1",
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)
            workspace = main.get_draft_image_workspace(draft.id, user=db.get(User, 1), db=db)
            result = main.confirm_draft_images(
                draft.id,
                DraftImagesConfirm(image_items=[
                    DraftOrderedImageSelection(result_url="https://img.example/sku-2.png", sku="SKU2"),
                    DraftOrderedImageSelection(result_url="https://img.example/sku-1.png", sku="SKU1"),
                ]),
                user=db.get(User, 1), db=db,
            )

        self.assertTrue(workspace["published"])
        self.assertEqual(result["image_urls"], [
            "https://img.example/sku-2.png",
            "https://img.example/sku-1.png",
        ])

    def test_empty_custom_layout_restores_sku_images(self) -> None:
        with self.session_factory() as db:
            draft = ProductDraft(
                company_id=1, template_id=1, title="T" * 25,
                image_urls=["https://img.example/published.png"],
                carousel_items=[{"sku": "SKU1", "image_url": "https://img.example/carousel.png", "task_id": 1}],
                sku_items=[{"sku": "SKU1", "image_url": "https://img.example/sku.png"}],
                created_by=1, updated_by=1,
            )
            db.add(draft); db.commit(); db.refresh(draft)
            result = main.confirm_draft_images(
                draft.id,
                DraftImagesConfirm(image_items=[]),
                user=db.get(User, 1), db=db,
            )
        self.assertEqual(result["image_urls"], ["https://img.example/sku.png"])
        self.assertEqual(result["carousel_items"], [])

    def test_legacy_batch_migration_clears_tasks_and_preserves_assets(self) -> None:
        task_id = self.add_task()
        with self.session_factory() as db:
            db.add(MaterialAsset(company_id=1, source_task_id=task_id, url="https://img.example/material.png", name="material", claimed_by=1))
            db.add(ProductDraft(company_id=1, title="draft", image_urls=[], sku_items=[]))
            db.commit()
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE pod_task_batches (id INTEGER PRIMARY KEY)"))
        with patch.object(main, "engine", self.engine):
            main.ensure_schema()
        with self.session_factory() as db:
            self.assertEqual(db.scalar(select(PodTask.id)), None)
            self.assertIsNone(db.scalar(select(MaterialAsset.source_task_id)))
        self.assertNotIn("pod_task_batches", inspect(self.engine).get_table_names())


if __name__ == "__main__":
    unittest.main()
