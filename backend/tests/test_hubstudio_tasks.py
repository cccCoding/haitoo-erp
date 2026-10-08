import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import hub, main
from app.database import Base, get_db
from app.models import Company, HubAgent, HubEnvironment, HubEnvironmentAccess, HubRuntimeLock, HubUploadAttempt, HubUploadTask, ProductDraft, ProductTemplate, Role, TiktokCategoryCatalog, User
from app.schemas import HubTaskClaimInput, HubTaskAction, HubUploadTaskCreate, HubUploadTaskReport, HubstudioAccountUpdate
from app.tiktok_export import TEMPLATE_PATH, listing_options


class HubstudioTaskTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.mock_storage()
        self.seed()

    def mock_storage(self):
        self.files = {}
        def upload(content, company_id):
            url = f"https://r2.invalid/private/hub-exports/company/{company_id}/{len(self.files)}.xlsx"
            self.files[url] = content
            return url
        for name, fn in (("upload_hub_export", upload), ("read_hub_export", lambda url, *args: self.files[url]), ("delete_hub_export", lambda url, *args: self.files.pop(url, None))):
            mock = patch.object(main, name, side_effect=fn)
            mock.start(); self.addCleanup(mock.stop)

    def seed(self):
        with self.Session() as db:
            db.add_all([
                Company(id=1, name="Company"),
                User(id=1, company_id=1, email="admin@example.com", name="Admin", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=2, company_id=1, email="member@example.com", name="Member", password_hash="x", role=Role.MEMBER),
                HubAgent(id=1, company_id=1, user_id=1, name="Mac", platform="macos", token_hash=hashlib.sha256(b"a" * 48).hexdigest()),
                HubAgent(id=2, company_id=1, user_id=1, name="Windows", platform="windows", token_hash="b" * 64),
                HubAgent(id=3, company_id=1, user_id=2, name="Other", platform="macos", token_hash="c" * 64),
                ProductTemplate(id=1, company_id=1, name="Y1", product_description="Description", size_chart_url="https://x/chart.jpg", package_weight=.2, package_length=20, package_width=10, package_height=2),
                TiktokCategoryCatalog(id=1, company_id=1, name="Catalog", source_filename=TEMPLATE_PATH.name, template_blob=TEMPLATE_PATH.read_bytes(), parsed_options=listing_options()),
                ProductDraft(id=1, company_id=1, template_id=1, title="A valid title for automated TikTok listing", product_description="Description", image_urls=["https://x/a.jpg"], sku_items=[{"image_url":"https://x/a.jpg", "sku":"Y1AA000001"}], created_by=1, updated_by=1),
            ])
            db.commit()
            main.update_hubstudio_account(HubstudioAccountUpdate(app_id="id", app_secret="secret", group_code="group"), db.get(User, 1), db)

    def claim(self, db, agent_id, code="env-1"):
        return hub.claim(db, db.get(HubAgent, agent_id), HubTaskClaimInput(container_code=code, environment_name="Environment " + code, confirmed_local=True))

    def create(self, db):
        return main.create_hubstudio_upload_task(HubUploadTaskCreate(draft_ids=[1], category_catalog_id=1, category="女士上装/女士衬衫", default_price=10, default_quantity=3, attributes={"product_property/100198": "花朵"}), db.get(User, 1), db)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def test_record_list_scope_permissions_and_agent_compatibility(self):
        def database():
            with self.Session() as db:
                yield db
        main.app.dependency_overrides[get_db] = database
        client = TestClient(main.app)
        with self.Session() as db:
            db.add_all([
                Company(id=2, name="Other company"),
                User(id=3, company_id=1, email="leader@example.com", name="Leader", password_hash="x", role=Role.TEAM_LEADER),
                User(id=4, company_id=2, email="other@example.com", name="Other", password_hash="x", role=Role.COMPANY_ADMIN),
                HubUploadTask(id=10, company_id=1, created_by=1, draft_ids=[1, 2], export_filename="admin.xlsx"),
                HubUploadTask(id=11, company_id=1, created_by=2, draft_ids=[3], export_filename="member.xlsx", environment_name="TikTok", container_code="env-1", status="completed"),
                HubUploadTask(id=12, company_id=1, created_by=3, draft_ids=[], export_filename="leader.xlsx"),
                HubUploadTask(id=13, company_id=2, created_by=4, draft_ids=[4], export_filename="other.xlsx"),
                HubUploadTask(id=14, company_id=1, created_by=999, draft_ids=[], export_filename="historical.xlsx"),
            ])
            db.commit()
            users = {i: db.get(User, i) for i in (1, 2, 3)}
        main.app.dependency_overrides[main.current_user] = lambda: users[1]
        result = client.get("/hub-upload-tasks?scope=company&page_size=2").json()
        self.assertEqual(result["total"], 4)
        self.assertEqual([item["id"] for item in result["items"]], [14, 12])
        self.assertIsNone(result["items"][0]["created_by_name"])
        second = client.get("/hub-upload-tasks?scope=company&page_size=2&page=2").json()["items"]
        self.assertEqual([item["id"] for item in second], [11, 10])
        self.assertEqual(second[0]["created_by_name"], "Member")
        self.assertEqual(second[0]["environment_name"], "TikTok")
        self.assertEqual(second[0]["status"], "completed")
        self.assertEqual(second[1]["product_count"], 2)
        self.assertIsNone(second[1]["environment_name"])
        self.assertNotIn("claim_token", second[0])
        self.assertNotIn("export_blob", second[0])
        self.assertEqual(client.get("/hub-upload-tasks").json()["total"], 1)
        filtered = client.get("/hub-upload-tasks?scope=company&creator_id=2").json()
        self.assertEqual([item["id"] for item in filtered["items"]], [11])
        self.assertEqual(client.get("/hub-upload-tasks?scope=company&creator_id=4").json()["total"], 0)
        self.assertEqual(client.get("/hub-upload-tasks?scope=invalid").status_code, 422)
        self.assertEqual(client.get("/hub-upload-tasks?creator_id=0").status_code, 422)
        for user_id, task_id in ((2, 11), (3, 12)):
            main.app.dependency_overrides[main.current_user] = lambda user_id=user_id: users[user_id]
            self.assertEqual([item["id"] for item in client.get("/hub-upload-tasks").json()["items"]], [task_id])
            self.assertEqual(client.get(f"/hub-upload-tasks?creator_id={user_id}").json()["total"], 1)
            self.assertEqual(client.get("/hub-upload-tasks?scope=company").status_code, 403)
            self.assertEqual(client.get("/hub-upload-tasks?creator_id=1").status_code, 403)
            self.assertEqual(client.put("/hubstudio/account", json={"app_id":"id", "app_secret":"secret", "group_code":"group"}).status_code, 403)
        agent_headers = {"X-Hub-Agent-Token": "a" * 48, "X-Hub-Protocol": "3"}
        agent_result = client.get("/hub-agent/tasks?scope=company&creator_id=2", headers=agent_headers)
        self.assertEqual(agent_result.status_code, 200)
        self.assertEqual([item["id"] for item in agent_result.json()["items"]], [10])

    def test_snapshot_does_not_publish_until_explicit_submission(self):
        with self.Session() as db:
            result = self.create(db)
            task = db.get(HubUploadTask, result["id"])
            original = self.files[task.export_url]
            self.assertIsNone(task.export_blob)
            self.assertEqual(task.export_sha256, hashlib.sha256(original).hexdigest())
            self.assertTrue(original.startswith(b"PK"))
            self.assertIsNone(task.agent_id)
            self.assertIsNone(task.shop_id)
            self.assertNotIn("export_blob", result)
            self.assertNotIn("claim_token", result)
            draft = db.get(ProductDraft, 1)
            self.assertNotEqual(draft.status, "published")
            self.assertEqual(draft.export_count, 1)
            draft.title = "Changed title"; db.commit()
            claim = self.claim(db, 1)
            self.assertEqual(self.files[db.get(HubUploadTask, task.id).export_url], original)
            hub.report(db, db.get(HubAgent, 1), task.id, claim["claim_token"], HubUploadTaskReport(status="completed", stage="submitted"))
            db.refresh(draft)
            self.assertEqual(draft.status, "published")
            self.assertIsNone(db.get(HubRuntimeLock, 1).task_id)

    def test_creation_needs_no_environment_and_cross_border_rejected(self):
        with self.Session() as db:
            task = self.create(db)
            self.assertIsNone(task["environment_id"])
            self.assertIsNone(task["container_code"])
            self.assertIsNone(task["environment_name"])
            self.assertEqual(db.scalars(select(HubEnvironment)).all(), [])
            self.assertEqual(db.scalars(select(HubEnvironmentAccess)).all(), [])
            db.get(TiktokCategoryCatalog, 1).template_type = "tiktok_cross_border"; db.commit()
            with self.assertRaises(HTTPException): self.create(db)

    def test_old_shop_argument_rejected(self):
        for key in ("shop_id", "environment_id"):
            with self.assertRaises(ValidationError):
                HubUploadTaskCreate(**{key: 1}, draft_ids=[1], category_catalog_id=1, category="X", default_price=10)

    def test_task_creation_rolls_back_draft_update(self):
        with self.Session() as db:
            with patch.object(db, "commit", side_effect=RuntimeError("write failed")):
                with self.assertRaises(RuntimeError): self.create(db)
            self.assertEqual(db.get(ProductDraft, 1).export_count, 0)
            self.assertNotEqual(db.get(ProductDraft, 1).status, "published")
            self.assertIsNone(db.scalar(select(HubUploadTask)))
            self.assertEqual(self.files, {})

    def test_data_error_tasks_cannot_be_retried(self):
        with self.Session() as db:
            result = self.create(db)
            task = db.get(HubUploadTask, result["id"])
            task.status, task.stage = "failed", "import_data_error"
            task.failure_reason = "上传成功，添加商品失败（数据错误）"
            db.commit()
            with self.assertRaises(HTTPException) as error:
                hub.task_action(db, task.id, 1, 1, "retry", HubTaskAction(confirmed_platform_checked=True))
            self.assertEqual(error.exception.status_code, 409)
            self.assertIn("不可重试", error.exception.detail)
            db.refresh(task)
            self.assertEqual((task.status, task.stage), ("failed", "import_data_error"))
            self.assertEqual(task.failure_reason, "上传成功，添加商品失败（数据错误）")

    def test_expired_files_cannot_be_claimed_or_retried(self):
        with self.Session() as db:
            result = self.create(db)
            task = db.get(HubUploadTask, result["id"])
            task.export_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
            self.assertIsNone(self.claim(db, 1)["task"])
            db.refresh(task)
            self.assertEqual(task.status, "expired")
            task.status = "awaiting_attention"; db.commit()
            with self.assertRaises(HTTPException) as error:
                hub.task_action(db, task.id, 1, 1, "retry", HubTaskAction(confirmed_platform_checked=True))
            self.assertEqual(error.exception.status_code, 410)
            self.assertEqual(len(self.files), 1)

    def test_r2_failure_rolls_back_draft_update(self):
        with self.Session() as db:
            with patch.object(main, "upload_hub_export", side_effect=main.StorageError("R2 unavailable")):
                with self.assertRaises(HTTPException) as error: self.create(db)
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(db.get(ProductDraft, 1).export_count, 0)
            self.assertIsNone(db.scalar(select(HubUploadTask)))

    def test_authenticated_file_download_and_legacy_fallback(self):
        def database():
            with self.Session() as db: yield db
        main.app.dependency_overrides[get_db] = database
        client = TestClient(main.app)
        headers = {"X-Hub-Agent-Token": "a" * 48, "X-Hub-Protocol": "3"}
        with self.Session() as db:
            task = self.create(db)
            claim = self.claim(db, 1)
            expected = self.files[task["export_url"]]
        path = f"/hub-agent/tasks/{task['id']}/file?claim_token={claim['claim_token']}"
        self.assertEqual(client.get(path, headers=headers).content, expected)
        with self.Session() as db:
            stored = db.get(HubUploadTask, task["id"])
            stored.export_url = None
            stored.export_blob = expected
            db.commit()
        self.assertEqual(client.get(path, headers=headers).content, expected)
        with self.Session() as db:
            stored = db.get(HubUploadTask, task["id"])
            stored.export_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(client.get(path, headers=headers).status_code, 410)

    def test_cleanup_deletes_only_expired_objects_and_keeps_tasks(self):
        with self.Session() as db:
            first = self.create(db)
            second = self.create(db)
            db.get(HubUploadTask, first["id"]).export_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        with patch.object(main, "SessionLocal", self.Session): main._delete_expired_hub_exports()
        self.assertNotIn(first["export_url"], self.files)
        self.assertIn(second["export_url"], self.files)
        with self.Session() as db:
            self.assertIsNotNone(db.get(HubUploadTask, first["id"]).export_deleted_at)
            self.assertIsNone(db.get(HubUploadTask, second["id"]).export_deleted_at)

    def test_oversized_xlsx_returns_clear_error_and_rolls_back(self):
        with self.Session() as db:
            with patch.object(hub, "MAX_XLSX_BYTES", 1):
                with self.assertRaises(HTTPException) as error:
                    self.create(db)
            self.assertEqual(error.exception.status_code, 413)
            self.assertIsNone(db.scalar(select(HubUploadTask)))
            self.assertEqual(db.get(ProductDraft, 1).export_count, 0)

    def test_erp_environment_sync_rejected_without_persisting_directory(self):
        def database():
            with self.Session() as db: yield db
        main.app.dependency_overrides[get_db] = database
        client = TestClient(main.app)
        headers = {"X-Hub-Agent-Token": "a" * 48, "X-Hub-Protocol": "3"}
        self.assertEqual(client.post("/hub-agent/environments/sync", headers=headers,
            json={"environments": [{"container_code": "env-1", "name": "Environment"}]}).status_code, 410)
        with self.Session() as db:
            self.assertEqual(db.scalars(select(HubEnvironment)).all(), [])
            self.assertEqual(db.scalars(select(HubEnvironmentAccess)).all(), [])

    def test_claim_requires_selected_confirmed_environment(self):
        with self.Session() as db:
            self.create(db)
            with self.assertRaises(HTTPException):
                hub.claim(db, db.get(HubAgent, 1), HubTaskClaimInput(container_code="env-1", environment_name="E"))
            result = self.claim(db, 1, "local-choice")
            self.assertEqual(result["task"]["container_code"], "local-choice")
            self.assertEqual(result["hubstudio"]["container_code"], "local-choice")
            self.assertEqual(db.scalars(select(HubEnvironment)).all(), [])

    def test_empty_poll_does_not_save_any_environment_identity(self):
        with self.Session() as db:
            self.assertIsNone(self.claim(db, 1)["task"])
            self.assertEqual(db.scalars(select(HubRuntimeLock)).all(), [])
            self.assertEqual(db.scalars(select(HubEnvironment)).all(), [])

    def test_two_computers_can_use_different_environments(self):
        with self.Session() as db:
            first, second = self.create(db), self.create(db)
            self.assertEqual(self.claim(db, 1, "env-1")["task"]["id"], first["id"])
            self.assertEqual(self.claim(db, 2, "env-2")["task"]["id"], second["id"])
            self.assertEqual(len(db.scalars(select(HubUploadAttempt)).all()), 2)

    def test_account_isolation_and_environment_serialization(self):
        with self.Session() as db:
            first, second = self.create(db), self.create(db)
            claim = self.claim(db, 1)
            self.assertEqual(claim["task"]["id"], first["id"])
            self.assertIsNone(self.claim(db, 2)["task"])
            self.assertIsNone(self.claim(db, 3)["task"])
            self.assertEqual(hub.list_tasks(db, 2, 1)["total"], 0)
            with self.assertRaises(HTTPException): hub.detail(db, first["id"], 2, 1)
            hub.report(db, db.get(HubAgent, 1), first["id"], claim["claim_token"], HubUploadTaskReport(status="awaiting_attention", stage="manual_attention", message="unknown result"))
            self.assertIsNone(self.claim(db, 2)["task"])
            hub.task_action(db, first["id"], 1, 1, "cancel", HubTaskAction())
            self.assertEqual(self.claim(db, 2)["task"]["id"], second["id"])

    def test_lease_loss_retry_and_late_report(self):
        with self.Session() as db:
            task = self.create(db); claim = self.claim(db, 1)
            record = db.get(HubUploadTask, task["id"]); record.lease_expires_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
            detail = hub.detail(db, record.id, 1, 1)
            self.assertEqual(detail["status"], "awaiting_attention")
            self.assertNotIn("claim_token", detail)
            with self.assertRaises(HTTPException):
                hub.report(db, db.get(HubAgent, 1), record.id, claim["claim_token"], HubUploadTaskReport(status="completed", stage="submitted"))
            with self.assertRaises(HTTPException): hub.task_action(db, record.id, 1, 1, "retry", HubTaskAction())
            hub.task_action(db, record.id, 1, 1, "retry", HubTaskAction(confirmed_platform_checked=True))
            second = self.claim(db, 1, "env-2")
            self.assertNotEqual(second["claim_token"], claim["claim_token"])
            attempts = db.scalars(select(HubUploadAttempt).order_by(HubUploadAttempt.number)).all()
            self.assertEqual([a.number for a in attempts], [1, 2])
            self.assertEqual(attempts[0].status, "awaiting_attention")
            self.assertTrue(attempts[0].logs)
            self.assertEqual([a.container_code for a in attempts], ["env-1", "env-2"])

    def test_running_cancel_rejected_and_manual_confirm_publishes(self):
        with self.Session() as db:
            task = self.create(db); claim = self.claim(db, 1)
            with self.assertRaises(HTTPException): hub.task_action(db, task["id"], 1, 1, "cancel", HubTaskAction())
            hub.heartbeat(db, db.get(HubAgent, 1), task["id"], claim["claim_token"])
            hub.report(db, db.get(HubAgent, 1), task["id"], claim["claim_token"], HubUploadTaskReport(status="awaiting_attention", stage="unknown_result"))
            result = hub.task_action(db, task["id"], 1, 1, "confirm-submitted", HubTaskAction(confirmed_platform_checked=True))
            self.assertEqual(result["resolved_by"], 1)
            self.assertEqual(db.get(ProductDraft, 1).status, "published")
            self.assertEqual(result["attempts"][0]["status"], "awaiting_attention")

    def test_history_with_multiple_running_tasks_all_expires(self):
        with self.Session() as db:
            first, second = self.create(db), self.create(db)
            for identity in (first["id"], second["id"]):
                task = db.get(HubUploadTask, identity)
                task.status = "running"
                task.container_code = "env-1"
                task.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.add(HubRuntimeLock(company_id=1, container_code="env-1", task_id=first["id"]))
            db.commit()
            hub.sweep_expired(db)
            self.assertEqual([t.status for t in db.scalars(select(HubUploadTask).order_by(HubUploadTask.id))], ["awaiting_attention", "awaiting_attention"])

    def test_http_protocol_and_private_task_data(self):
        def database():
            with self.Session() as db: yield db
        main.app.dependency_overrides[get_db] = database
        client = TestClient(main.app)
        token = {"X-Hub-Agent-Token": "a" * 48}
        self.assertEqual(client.post("/hub-agent/claim", headers=token).status_code, 426)
        headers = token | {"X-Hub-Protocol": "3"}
        self.assertEqual(client.get("/hub-agent/config", headers=headers).status_code, 200)
        with self.Session() as db: self.create(db)
        result = client.get("/hub-agent/tasks", headers=headers).json()
        self.assertEqual(result["total"], 1)
        self.assertNotIn("claim_token", result["items"][0])
        claim = client.post("/hub-agent/claim", headers=headers, json={"container_code": "local-env", "environment_name": "本机启用环境", "confirmed_local": True})
        self.assertEqual(claim.status_code, 200)
        self.assertEqual(claim.json()["task"]["container_code"], "local-env")
        with self.Session() as db:
            self.assertNotIn("token_hash", main.hub_agent_view(db.get(HubAgent, 1)))


class HubConcurrencyTests(HubstudioTaskTests):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'hub.db'}", connect_args={"check_same_thread": False, "timeout": 10})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.mock_storage()
        self.seed()

    def tearDown(self):
        super().tearDown(); self.temp.cleanup()

    def test_two_computers_compete_atomically(self):
        with self.Session() as db:
            self.create(db); self.create(db)
        def claim(agent_id):
            with self.Session() as db:
                return self.claim(db, agent_id)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, [1, 2]))
        self.assertEqual(sum(bool(r["task"]) for r in results), 1)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(HubUploadAttempt)).all()), 1)


if __name__ == "__main__": unittest.main()
