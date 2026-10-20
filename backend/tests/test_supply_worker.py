"""货盘租约恢复、最终图片检查、兜底与文件完成的行为测试。"""
import asyncio
import copy
import hashlib
from datetime import datetime, timedelta
from io import BytesIO
import random
import unittest
from unittest.mock import AsyncMock, patch

from openpyxl import load_workbook
from sqlalchemy import select

from app.credentials import encrypt_secret
from app.models import (Company, MaterialAsset, ProductTemplate, SupplyJob,
                        SupplyJobMaterial, TiktokCategoryCatalog, User)
from app.supply_common import (digest, eligible_materials, normalize_title,
                              template_snapshot, template_version, unique_title)
if __package__:
    from .test_supply_catalog import SupplyFixture
else:
    from test_supply_catalog import SupplyFixture


class SupplyWorkerTests(SupplyFixture, unittest.TestCase):
    def test_each_generated_link_obeys_snapshot_filter_after_flags_change(self):
        for mode in ("exclude", "include", "only"):
            with self.sessions() as db:
                for asset in db.scalars(select(MaterialAsset).where(MaterialAsset.company_id == 1)):
                    asset.is_infringing = asset.id <= 10
                db.commit()
            identity = self.submit(self.create_strategy(infringement_filter=mode), key=f"filter-{mode}-job")
            # 提交后反转标记，执行仍须使用原候选和标记快照。
            with self.sessions() as db:
                for asset in db.scalars(select(MaterialAsset).where(MaterialAsset.company_id == 1)):
                    asset.is_infringing = not asset.is_infringing
                db.commit()
            self.run_job(identity)
            checkpoint = self.assert_completed(identity)
            for link in checkpoint["links"]:
                self.assertEqual(len(link["materials"]), 5)
                for item in link["materials"]:
                    self.assertEqual(item["is_infringing"], item["id"] <= 10)
                    if mode != "include":
                        self.assertEqual(item["is_infringing"], mode == "only")

    def setUp(self):
        super().setUp()
        from app import supply_worker
        self.worker = supply_worker
        settings = supply_worker.get_settings().model_copy(update={"supply_heartbeat_seconds": 3600})
        self.enterContext(patch("app.supply_worker.get_settings", return_value=settings))
        self.enterContext(patch("app.supply_worker.RETRY_DELAYS", (0, 0, 0)))
        self.title = self.enterContext(patch("app.supply_worker.request_title", new_callable=AsyncMock,
                                            return_value="Printed Long Sleeve Nursing Maxi Dress for Daily Wear"))
        self.image = self.image_mock
        self.contents = []
        def upload(company, job, epoch, filename, content):
            self.contents.append(content)
            return {"key": f"supply-exports/company/{company}/jobs/{job}/{epoch}/" + "a" * 32 + ".xlsx",
                    "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
        self.upload = self.enterContext(patch("app.supply_worker.upload_supply_export", side_effect=upload))
        self.delete = self.enterContext(patch("app.supply_worker.delete_supply_export"))
        self.enterContext(patch("app.supply_worker.list_supply_exports", return_value=[]))
        with self.sessions() as db:
            db.get(Company, 1).supply_ai_secret_encrypted = encrypt_secret("test-deepseek-key")
            db.commit()

    def make_job(self, uid=4, *, candidates=None, link_count=10, key=None):
        with self.sessions() as db:
            template = template_snapshot(db.get(ProductTemplate, 1))
            version = template_version(template)
            parameters = self.strategy_input(link_count=link_count)
            parameters.update(stock=999, cod="Y", title_requirements="")
            source = eligible_materials(db, 1, 1, version) if candidates is None else candidates
            catalog = db.get(TiktokCategoryCatalog, 1)
            job = SupplyJob(company_id=1, user_id=uid, agent_id=1, agent_name="原代理", template_id=1,
                category_catalog_id=1, idempotency_key=key or f"job-{random.random()}", request_hash="a" * 64,
                category_blob=catalog.template_blob,
                snapshot={"strategy": parameters, "template": template, "template_version": version,
                    "catalog_options": copy.deepcopy(catalog.parsed_options), "catalog_type": catalog.template_type,
                    "candidates": copy.deepcopy(source), "seed": "fixed-seed", "user_name": "用户", "internal_usage": False,
                    "expected_rows": 5 * link_count * 2})
            db.add(job)
            db.flush()
            db.add_all(SupplyJobMaterial(company_id=1, job_id=job.id, material_id=item["id"],
                version_hash=item["version_hash"], link_index=-1) for item in source)
            db.commit()
            return job.id

    def run_job(self, identity):
        claimed = self.worker.claim_job(self.sessions, owner="test-worker")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed[0], identity)
        asyncio.run(self.worker.run_job(*claimed, session_factory=self.sessions))

    def assert_completed(self, identity):
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "completed", job.error)
            self.assertIsNone(job.export_blob)
            self.assertEqual(job.output_size, len(self.contents[-1]))
            self.assertIsNone(job.lease_owner)
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, successful=True).count(), 50)
            return copy.deepcopy(job.checkpoint)

    def export_rows(self):
        book = load_workbook(BytesIO(self.contents[-1]), read_only=True, data_only=False)
        sheet = book["Template"]
        iterator = sheet.iter_rows(values_only=True)
        headers = next(iterator)
        fields = {str(value): index for index, value in enumerate(headers) if value}
        rows = [dict((field, row[index]) for field, index in fields.items())
                for row in sheet.iter_rows(min_row=7, max_row=106, values_only=True)]
        book.close()
        return rows

    def test_lease_reclaim_and_fencing_prevent_old_worker_from_committing(self):
        identity = self.make_job()
        first = self.worker.claim_job(self.sessions, owner="worker-a")
        self.assertIsNone(self.worker.claim_job(self.sessions, owner="worker-b"))
        with self.sessions() as db:
            db.get(SupplyJob, identity).lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        second = self.worker.claim_job(self.sessions, owner="worker-b")
        self.assertEqual(second[0], identity)
        self.assertGreater(second[1], first[1])
        with self.assertRaises(self.worker.LostLease):
            self.worker.mutate(*first, lambda db, job: setattr(job, "state", "completed"), session_factory=self.sessions)
        self.worker.mutate(*second, lambda db, job: setattr(job, "stage", "new-owner"), session_factory=self.sessions)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).stage, "new-owner")

    def test_company_concurrency_and_ineligible_accounts(self):
        first, second, third = self.make_job(), self.make_job(uid=7), self.make_job(uid=2)
        self.assertEqual(self.worker.claim_job(self.sessions, owner="worker-a")[0], first)
        self.assertEqual(self.worker.claim_job(self.sessions, owner="worker-b")[0], second)
        self.assertIsNone(self.worker.claim_job(self.sessions, owner="worker-c"))
        with self.sessions() as db:
            db.get(User, 4).supply_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.get(User, 7).is_active = False
            db.get(SupplyJob, first).export_blob = b"unfinished-export"
            db.get(SupplyJob, second).export_blob = b"unfinished-export"
            db.commit()
        self.worker.cancel_ineligible_jobs(self.sessions)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, first).state, "cancelled")
            self.assertEqual(db.get(SupplyJob, second).state, "cancelled")
            self.assertIsNone(db.get(SupplyJob, first).export_blob)
            self.assertIsNone(db.get(SupplyJob, second).export_blob)
        self.assertEqual(self.worker.claim_job(self.sessions, owner="worker-c")[0], third)

    def test_success_is_snapshot_based_with_unique_titles_and_deduplicated_images(self):
        identity = self.make_job()
        with self.sessions() as db:
            db.get(ProductTemplate, 1).supply_public = False
            db.get(ProductTemplate, 1).sku_specifications = {"size": {"options": ["XL"]}}
            for material in db.scalars(select(MaterialAsset).where(MaterialAsset.company_id == 1)):
                material.supply_listed = False
            db.delete(db.get(TiktokCategoryCatalog, 1))
            db.commit()
        completed_at = datetime.utcnow()
        with patch("app.supply_worker.now", return_value=completed_at):
            self.run_job(identity)
        state = self.assert_completed(identity)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).output_expires_at, completed_at + timedelta(days=7))
        self.assertEqual(self.title.call_count, 10)
        urls = [call.args[0] for call in self.image.call_args_list]
        self.assertEqual(len(urls), len(set(urls)))
        self.image.assert_not_called()
        rows = self.export_rows()
        self.assertEqual(len({normalize_title(row["product_name"]) for row in rows}), 10)
        self.assertEqual({row["product_name"] for row in rows}, {
            f"Printed Long Sleeve Nursing Maxi Dress for Daily Wear - L{index:02d}" for index in range(1, 11)})
        self.assertTrue(all(row["seller_sku"].endswith(("-S", "-M")) for row in rows))
        self.assertTrue(all(25 <= len(link["title"]) <= 255 for link in state["links"]))

    def test_title_failure_has_durable_four_call_budget_then_fallback(self):
        identity = self.make_job()
        self.title.side_effect = ValueError("provider failed")
        self.run_job(identity)
        state = self.assert_completed(identity)
        self.assertEqual(self.title.call_count, 40)
        self.assertEqual(set(state["title_attempts"].values()), {4})
        self.assertEqual([link["title"] for link in state["links"]], [
            f"Printed Long Sleeve Nursing Maxi Dress - L{index:02d}" for index in range(1, 11)])
        self.assertEqual(len({normalize_title(link["title"]) for link in state["links"]}), 10)










    def test_upload_retry_reuses_excel_without_regenerating_or_rechecking(self):
        identity = self.make_job()
        upload = self.upload.side_effect
        self.upload.side_effect = ValueError("storage outage")
        self.run_job(identity)
        first_titles, first_images = self.title.call_count, self.image.call_count
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "retry_wait", job.error)
            self.assertIsNotNone(job.export_blob)
            self.assertEqual(job.upload_attempts, 1)
            first_bytes = bytes(job.export_blob)
            job.available_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.upload.side_effect = upload
        self.run_job(identity)
        self.assert_completed(identity)
        self.assertEqual(self.contents[-1], first_bytes)
        self.assertEqual(self.title.call_count, first_titles)
        self.assertEqual(self.image.call_count, first_images)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).upload_attempts, 2)

    def test_four_upload_failures_end_task_without_success_statistics(self):
        identity = self.make_job()
        self.upload.side_effect = ValueError("storage outage")
        for attempt in range(4):
            self.run_job(identity)
            with self.sessions() as db:
                job = db.get(SupplyJob, identity)
                self.assertEqual(job.upload_attempts, attempt + 1)
                self.assertEqual(job.state, "failed" if attempt == 3 else "retry_wait")
                self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, successful=True).count(), 0)
        self.assertEqual(self.upload.call_count, 4)
        self.assertEqual(self.title.call_count, 10)
        urls = [call.args[0] for call in self.image.call_args_list]
        self.assertEqual(len(urls), len(set(urls)))
        with self.sessions() as db:
            self.assertIsNone(db.get(SupplyJob, identity).export_blob)

    def test_user_cancellation_after_upload_prevents_completion_and_deletes_orphan(self):
        identity = self.make_job()
        upload = self.upload.side_effect
        def cancel_after_upload(company, job_id, epoch, filename, content):
            result = upload(company, job_id, epoch, filename, content)
            response = self.request("POST", f"/supply/jobs/{job_id}/cancel", uid=4)
            self.assertEqual(response.status_code, 200, response.text)
            return result
        self.upload.side_effect = cancel_after_upload
        self.run_job(identity)
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "cancelled")
            self.assertIsNone(job.output_key)
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, successful=True).count(), 0)
        self.delete.assert_called_once()


    def test_file_cleanup_keeps_task_metadata_and_skips_live_referenced_files(self):
        expired, retained = self.make_job(), self.make_job(uid=7)
        expired_key = f"supply-exports/company/1/jobs/{expired}/1/" + "a" * 32 + ".xlsx"
        retained_key = f"supply-exports/company/1/jobs/{retained}/1/" + "b" * 32 + ".xlsx"
        orphan_key = "supply-exports/company/1/jobs/999/1/" + "c" * 32 + ".xlsx"
        with self.sessions() as db:
            for identity, key, delta in ((expired, expired_key, -1), (retained, retained_key, 1)):
                job = db.get(SupplyJob, identity)
                job.state, job.output_key = "completed", key
                job.output_expires_at = datetime.utcnow() + timedelta(days=delta)
            db.commit()
        with patch("app.supply_worker.list_supply_exports", return_value=[retained_key, orphan_key]):
            self.worker.cleanup_exports(self.sessions)
        self.assertEqual({call.args[0] for call in self.delete.call_args_list}, {expired_key, orphan_key})
        with self.sessions() as db:
            job = db.get(SupplyJob, expired)
            self.assertEqual(job.state, "completed")
            self.assertIsNotNone(job.output_deleted_at)
            self.assertTrue(job.snapshot)
            self.assertIsNone(db.get(SupplyJob, retained).output_deleted_at)

    def test_stable_title_codes_survive_normalization_and_truncation(self):
        titles = [unique_title("Ａ" * 255, "Printed Long Sleeve Nursing Maxi Dress", index) for index in range(100)]
        self.assertEqual(len({normalize_title(title) for title in titles}), 100)
        self.assertTrue(all(len(title) <= 255 for title in titles))
        self.assertTrue(titles[0].endswith(" - L01"))
        self.assertTrue(titles[9].endswith(" - L10"))
        self.assertTrue(titles[98].endswith(" - L99"))
        self.assertTrue(titles[99].endswith(" - L100"))


if __name__ == "__main__":
    unittest.main()
