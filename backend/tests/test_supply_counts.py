"""汇总快照、个人终身额度和列表只读汇总的回归。"""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import event, select

from app.models import (MaterialAsset, ProductTemplate, SupplyJob, SupplyJobMaterial,
                        SupplyTemplateCount, SupplyUserExhaustedCount)
from app.supply_count_worker import refresh_company, run_cycle
from tests.test_supply_catalog import SupplyFixture


class SupplyCountTests(SupplyFixture, unittest.TestCase):
    def refresh(self):
        with self.sessions.begin() as db:
            refresh_company(db, 1)

    def counts(self, uid=4):
        response = self.request("GET", "/supply/templates", uid=uid)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()[0]

    def history(self, sku="SOURCE001", count=3, uid=4, state="completed", successful=True):
        with self.sessions.begin() as db:
            job = SupplyJob(company_id=1, user_id=uid, template_id=1, category_catalog_id=1,
                category_blob=b"old", idempotency_key=f"{sku}-{uid}-{state}-{successful}", request_hash="x", state=state)
            db.add(job)
            db.flush()
            for index in range(count):
                db.add(SupplyJobMaterial(company_id=1, job_id=job.id, material_id=1, sku=sku,
                    version_hash=str(index), link_index=index, successful=successful))
            return job.id

    def test_initial_zero_invalid_and_unpublished_templates(self):
        self.assertIsNone(self.counts()["material_count"])
        self.assertIsNone(self.counts()["my_available_count"])
        self.assertIsNone(self.counts()["counts_updated_at"])
        with self.sessions.begin() as db:
            db.get(MaterialAsset, 1).supply_listed = False
            db.get(MaterialAsset, 2).sku = "\t \n"
            db.get(MaterialAsset, 3).url = "\n\t"
            db.add(ProductTemplate(id=3, company_id=1, name="空模板", supply_public=False))
        self.refresh()
        self.assertEqual(self.counts()["material_count"], 17)
        self.assertEqual(self.counts()["my_available_count"], 17)
        manager = self.request("GET", "/supply/templates").json()
        self.assertEqual(manager[1]["material_count"], 0)
        self.assertEqual(manager[1]["my_available_count"], 0)
        self.assertEqual(len(self.request("GET", "/supply/templates", uid=4).json()), 1)

    def test_quota_deduplicates_links_and_ignores_failed_or_cancelled_jobs(self):
        self.history(count=2)
        job_id = self.history(sku="SOURCE002")
        self.history(sku="SOURCE003", state="failed")
        self.history(sku="SOURCE004", state="cancelled")
        self.history(sku="SOURCE005", successful=False)
        with self.sessions.begin() as db:
            # 同一链接的不同素材版本只能扣一次。
            db.add(SupplyJobMaterial(company_id=1, job_id=job_id, material_id=1,
                sku="SOURCE002", version_hash="another", link_index=0, successful=True))
        self.refresh()
        self.assertEqual(self.counts()["my_available_count"], 19)
        self.assertEqual(self.counts(uid=7)["my_available_count"], 20)
        self.assertEqual(self.counts(uid=1)["my_available_count"], 20)
        self.assertIsNone(self.counts(uid=5)["material_count"])
        with self.sessions() as db:
            self.assertEqual(len(db.scalars(select(SupplyUserExhaustedCount)).all()), 1)

    def test_reimport_and_listing_changes_follow_sku_and_current_template(self):
        self.history()
        self.refresh()
        with self.sessions.begin() as db:
            db.delete(db.get(MaterialAsset, 1))
            db.flush()
            db.add(MaterialAsset(id=100, company_id=1, template_id=1, claimed_by=2,
                name="重新导入", sku="\tSOURCE001 ", url="https://img/new", supply_listed=True))
        self.refresh()
        self.assertEqual(self.counts()["material_count"], 20)
        self.assertEqual(self.counts()["my_available_count"], 19)
        with self.sessions.begin() as db:
            db.get(MaterialAsset, 100).supply_listed = False
        self.refresh()
        self.assertEqual(self.counts()["material_count"], 19)
        self.assertEqual(self.counts()["my_available_count"], 19)
        with self.sessions() as db:
            self.assertEqual(db.scalars(select(SupplyUserExhaustedCount)).all(), [])

    def test_failed_publish_rolls_back_both_tables(self):
        self.history()
        self.refresh()
        before = self.counts()
        with self.sessions.begin() as db:
            db.get(MaterialAsset, 2).supply_listed = False
        def fail_insert(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO supply_user_exhausted_counts"):
                raise RuntimeError("模拟发布失败")
        event.listen(self.engine, "before_cursor_execute", fail_insert)
        try:
            with self.assertRaisesRegex(RuntimeError, "模拟发布失败"):
                self.refresh()
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_insert)
        self.assertEqual(self.counts(), before)

    def test_list_reads_only_summary_and_worker_skips_fresh_snapshots(self):
        run_cycle(self.engine)
        statements = []
        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(self.engine, "before_cursor_execute", record)
        try:
            self.assertEqual(self.counts()["material_count"], 20)
            self.assertEqual(self.counts(uid=5)["material_count"], 1)
            self.assertFalse(any("material_assets" in sql or "supply_job_materials" in sql or "image_files" in sql
                                 for sql in statements))
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        with patch("app.supply_count_worker.refresh_company") as refresh:
            run_cycle(self.engine)
            refresh.assert_not_called()
        with self.sessions.begin() as db:
            for item in db.scalars(select(SupplyTemplateCount)):
                item.updated_at = datetime.utcnow() - timedelta(minutes=5)
        with patch("app.supply_count_worker.refresh_company", wraps=refresh_company) as refresh:
            run_cycle(self.engine)
            self.assertEqual(refresh.call_count, 2)
