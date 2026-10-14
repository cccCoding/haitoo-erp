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
from app.models import (Company, MaterialAsset, ProductTemplate, SupplyImageHealth, SupplyJob,
                        SupplyJobMaterial, TiktokCategoryCatalog, User)
from app.supply_common import (begin_check, digest, eligible_materials, finish_check, normalize_title,
                              template_snapshot, template_version, unique_title)
if __package__:
    from .test_supply_catalog import SupplyFixture
else:
    from test_supply_catalog import SupplyFixture


class SupplyWorkerTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from app import supply_worker
        self.worker = supply_worker
        settings = supply_worker.get_settings().model_copy(update={"supply_heartbeat_seconds": 3600})
        self.enterContext(patch("app.supply_worker.get_settings", return_value=settings))
        self.enterContext(patch("app.supply_worker.RETRY_DELAYS", (0, 0, 0)))
        self.title = self.enterContext(patch("app.supply_worker.request_title", new_callable=AsyncMock,
                                            return_value="Printed Long Sleeve Nursing Maxi Dress for Daily Wear"))
        self.image = self.enterContext(patch("app.supply_worker.check_image", new_callable=AsyncMock,
                                            return_value={"status": "available", "reason": ""}))
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
        self.assertIn("https://img.example/size1.png", urls)
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

    def test_invalid_product_image_is_replaced_with_matching_source_sku(self):
        identity = self.make_job()
        with self.sessions() as db:
            candidates = db.get(SupplyJob, identity).snapshot["candidates"]
        sample = self.worker.distinct_sample(candidates, 5, random.Random("fixed-seed"))
        bad_url, bad_sku = sample[0]["url"], sample[0]["sku"]
        async def image(url):
            return {"status": "invalid", "reason": "HTTP 404"} if url == bad_url else {"status": "available", "reason": ""}
        self.image.side_effect = image
        self.run_job(identity)
        state = self.assert_completed(identity)
        rows = self.export_rows()
        self.assertTrue(all(row["property_1_image"] != bad_url for row in rows))
        self.assertTrue(all(not row["seller_sku"].startswith(bad_sku + "-") for row in rows))
        self.assertTrue(any(link["replaced"] for link in state["links"]))
        self.assertTrue(all(link["title_source"] == "fallback_after_replacement" for link in state["links"] if link["replaced"]))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(SupplyImageHealth).where(SupplyImageHealth.url == bad_url)).status, "invalid")
        self.assertEqual([call.args[0] for call in self.image.call_args_list].count(bad_url), 1)

    def test_required_size_chart_failure_never_produces_partial_file(self):
        identity = self.make_job()
        async def image(url):
            return {"status": "invalid", "reason": "HTTP 410"} if url.endswith("size1.png") else {"status": "available", "reason": ""}
        self.image.side_effect = image
        self.run_job(identity)
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "failed")
            self.assertIn("尺码图", job.error)
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, successful=True).count(), 0)
        self.upload.assert_not_called()

    def prepare_live_replacement(self, *, incompatible=False):
        with self.sessions() as db:
            template = template_snapshot(db.get(ProductTemplate, 1))
            candidates = eligible_materials(db, 1, 1, template_version(template))[:5]
            for material in db.scalars(select(MaterialAsset).where(MaterialAsset.id.between(6, 20))):
                material.supply_listed = False
            db.commit()
        identity = self.make_job(candidates=candidates)
        with self.sessions() as db:
            db.add(MaterialAsset(id=21, company_id=1, template_id=1, claimed_by=2, name="新增替换素材", sku="NEWREPLACEMENT",
                                 url="https://img.example/new-replacement.png", supply_listed=True))
            if incompatible:
                db.get(ProductTemplate, 1).sku_specifications = {"size": {"options": ["XL"]}}
            db.commit()
        bad = candidates[0]["url"]
        async def image(url):
            return {"status": "invalid", "reason": "HTTP 404"} if url == bad else {"status": "available", "reason": ""}
        self.image.side_effect = image
        return identity

    def test_newly_listed_compatible_material_can_replace_snapshot_failure(self):
        identity = self.prepare_live_replacement()
        self.run_job(identity)
        state = self.assert_completed(identity)
        self.assertTrue(all(any(item["id"] == 21 for item in link["materials"]) for link in state["links"]))
        rows = self.export_rows()
        self.assertTrue(any(row["seller_sku"] == "NEWREPLACEMENT-S" for row in rows))
        with self.sessions() as db:
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, material_id=21, source="replacement", successful=True).count(), 10)
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, material_id=21, link_index=-1).count(), 1)

    def test_live_template_version_change_cannot_supply_incompatible_replacement(self):
        identity = self.prepare_live_replacement(incompatible=True)
        self.run_job(identity)
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "failed")
            self.assertIn("替换素材不足", job.error)
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, successful=True).count(), 0)
        self.assertNotIn("https://img.example/new-replacement.png", [call.args[0] for call in self.image.call_args_list])
        self.upload.assert_not_called()

    def test_live_material_rebound_between_selection_and_snapshot_registration_is_rejected(self):
        identity = self.prepare_live_replacement()
        original_query = self.worker.eligible_materials
        def rebind_after_query(db, company_id, template_id, version):
            candidates = original_query(db, company_id, template_id, version)
            if any(item["id"] == 21 for item in candidates):
                with self.sessions() as changed:
                    changed.get(MaterialAsset, 21).template_id = 2
                    changed.commit()
            return candidates
        with patch("app.supply_worker.eligible_materials", side_effect=rebind_after_query):
            self.run_job(identity)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).state, "failed")
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, material_id=21).count(), 0)
        self.upload.assert_not_called()

    def test_recovered_title_and_image_attempt_budgets_do_not_reset(self):
        identity = self.make_job()
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            snapshot = job.snapshot
            rng = random.Random(snapshot["seed"])
            links = [{"index": index, "materials": self.worker.distinct_sample(snapshot["candidates"], 5, rng),
                "replaced": False, "title": None if index == 0 else unique_title("An Already Saved Product Title", snapshot["template"]["supply_fallback_title"], index)} for index in range(10)]
            bad = links[0]["materials"][0]["url"]
            job.checkpoint = {"links": links, "title_attempts": {"0": 3},
                "image_checks": {digest(bad): {"url": bad, "attempts": 2}}}
            db.add(SupplyImageHealth(company_id=1, url=bad, url_hash=digest(bad), status="check_failed", check_sequence=2))
            db.commit()
        self.title.side_effect = ValueError("final title attempt failed")
        async def image(url):
            return {"status": "check_failed", "reason": "temporary outage"} if url == bad else {"status": "available", "reason": ""}
        self.image.side_effect = image
        self.run_job(identity)
        state = self.assert_completed(identity)
        self.assertEqual(self.title.call_count, 1)
        self.assertEqual(state["title_attempts"]["0"], 4)
        self.assertEqual([call.args[0] for call in self.image.call_args_list].count(bad), 1)
        self.assertEqual(state["image_checks"][digest(bad)]["attempts"], 3)

    def test_recovered_replacement_candidate_available_in_old_epoch_is_rechecked(self):
        with self.sessions() as db:
            version = template_version(template_snapshot(db.get(ProductTemplate, 1)))
            candidates = eligible_materials(db, 1, 1, version)[:6]
        identity = self.make_job(candidates=candidates)
        original_bad, prior_replacement = candidates[0], candidates[5]
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            links = [{"index": index, "materials": copy.deepcopy(candidates[:5]), "replaced": False,
                "title": unique_title("An Already Saved Product Title", job.snapshot["template"]["supply_fallback_title"], index)} for index in range(10)]
            job.lease_epoch = 1
            job.checkpoint = {"links": links,
                "replacement_attempts": {"0:0": {"tried": [prior_replacement["version_hash"]]}},
                "image_checks": {digest(prior_replacement["url"]): {"url": prior_replacement["url"], "attempts": 1,
                    "result": {"status": "available", "reason": ""}, "result_epoch": 1}}}
            db.commit()
        async def image(url):
            return {"status": "invalid", "reason": "source removed after prior check"} if url in {
                original_bad["url"], prior_replacement["url"]} else {"status": "available", "reason": ""}
        self.image.side_effect = image
        self.run_job(identity)
        state = self.assert_completed(identity)
        self.assertIn(prior_replacement["url"], [call.args[0] for call in self.image.call_args_list])
        self.assertEqual(state["image_checks"][digest(prior_replacement["url"])]["attempts"], 2)
        self.assertTrue(all(item["url"] not in {original_bad["url"], prior_replacement["url"]}
            for link in state["links"] for item in link["materials"]))
        self.assertTrue(all(row["property_1_image"] != prior_replacement["url"] for row in self.export_rows()))

    def test_replacement_candidate_budget_exhaustion_cannot_output_partial_file(self):
        identity = self.make_job()
        self.image.return_value = {"status": "invalid", "reason": "HTTP 404"}
        # 尺码图有效，商品源全部失效；缺失位置只能尝试 10 个候选。
        async def image(url):
            return {"status": "available", "reason": ""} if url.endswith("size1.png") else {"status": "invalid", "reason": "HTTP 404"}
        self.image.side_effect = image
        self.run_job(identity)
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "failed")
            self.assertIn("替换素材不足", job.error)
            self.assertEqual(len(job.checkpoint["replacement_attempts"]["0:0"]["tried"]), 10)
            self.assertEqual(db.query(SupplyJobMaterial).filter_by(job_id=identity, successful=True).count(), 0)
        self.upload.assert_not_called()

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

    def test_stale_health_result_cannot_overwrite_newer_success(self):
        url = "https://img.example/1.png"
        with self.sessions() as db:
            first = begin_check(db, 1, url)
            second = begin_check(db, 1, url)
            finish_check(db, 1, url, second, {"status": "available", "reason": ""})
            finish_check(db, 1, url, first, {"status": "invalid", "reason": "stale"})
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(SupplyImageHealth).where(SupplyImageHealth.url == url)).status, "available")

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
