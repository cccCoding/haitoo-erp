"""货盘列表大字段回归：摘要兼容、分页隔离和数据库结果集体积。"""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import event

from app.models import SupplyAudit, SupplyJob
from app.supply_common import job_payload
from tests.test_supply_catalog import SupplyFixture


class SupplyJobListTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.clock = datetime(2026, 11, 5, 12)
        self.enterContext(patch("app.supply_common.now", return_value=self.clock))
        with self.sessions() as db:
            for identity, company, owner in ((10, 1, 4), (20, 1, 7), (30, 1, 4),
                                              (40, 1, 7), (50, 1, 4), (90, 2, 5)):
                snapshot = {"candidates": [{"description": "x" * 524288}]}
                if identity != 50:
                    snapshot.update(strategy={"name": '夏日/长袍:"新款\\\n'}, user_name="历史用户名")
                db.add(SupplyJob(id=identity, company_id=company, user_id=owner,
                    strategy_id=None, template_id=company, category_catalog_id=company,
                    agent_name="历史代理" if owner == 7 else None,
                    idempotency_key=f"list-regression-{identity}", request_hash="a" * 64,
                    snapshot=snapshot, category_blob=b"c" * 262144,
                    checkpoint={"links": [{"description": "y" * 262144}]},
                    export_blob=b"e" * 262144, state="completed", stage="completed",
                    progress={"links_done": 10, "links_total": 10},
                    error="历史错误" if identity == 30 else None,
                    created_at=datetime(2026, 11, 3, 16, 30), completed_at=self.clock,
                    output_expires_at=self.clock + timedelta(days=-1 if identity == 10 else 1),
                    output_deleted_at=self.clock if identity == 20 else None))
            for company, action, target, identity in (
                (1, "download", "job", 40), (1, "download", "job", 40),
                (1, "download", "job", 50), (2, "download", "job", 30),
                (1, "download", "material", 30), (1, "submit_job", "job", 30),
            ):
                db.add(SupplyAudit(company_id=company, user_id=3, action=action,
                    target_type=target, target_id=identity))
            db.commit()
            self.expected = {identity: {**job_payload(db.get(SupplyJob, identity)),
                "downloaded": identity in (40, 50)} for identity in (10, 20, 30, 40, 50, 90)}

    def test_summaries_match_detail_rules_without_fetching_large_fields(self):
        result_columns = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            if cursor.description:
                result_columns.append({column[0] for column in cursor.description})

        def forbid_full_job_load(target, context):
            raise AssertionError("任务列表不应加载完整 SupplyJob 对象")

        event.listen(self.engine, "after_cursor_execute", capture)
        event.listen(SupplyJob, "load", forbid_full_job_load)
        try:
            response = self.request("GET", "/supply/jobs?scope=company&page_size=30", uid=3)
        finally:
            event.remove(self.engine, "after_cursor_execute", capture)
            event.remove(SupplyJob, "load", forbid_full_job_load)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"items": [self.expected[i] for i in (50, 40, 30, 20, 10)],
            "total": 5, "page": 1, "page_size": 30})
        self.assertTrue(any("strategy_name" in columns for columns in result_columns))
        for columns in result_columns:
            self.assertFalse(columns & {"snapshot", "category_blob", "checkpoint", "export_blob"})
        self.assertEqual(self.expected[50]["filename"], "货盘_2026-11-04.xlsx")

    def test_pagination_own_scope_permissions_and_company_isolation(self):
        for uid, scope, page, size, ids, total in (
            (3, "company", 1, 2, (50, 40), 5),
            (3, "company", 2, 2, (30, 20), 5),
            (3, "company", 3, 2, (10,), 5),
            (3, "company", 4, 2, (), 5),
            (4, "own", 1, 2, (50, 30), 3),
            (4, "own", 2, 2, (10,), 3),
            (7, "own", 1, 30, (40, 20), 2),
            (1, "own", 1, 30, (), 0),
            (5, "company", 1, 30, (90,), 1),
        ):
            with self.subTest(uid=uid, scope=scope, page=page):
                response = self.request("GET", "/supply/jobs", uid=uid,
                    params={"scope": scope, "page": page, "page_size": size})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), {"items": [self.expected[i] for i in ids],
                    "total": total, "page": page, "page_size": size})
        for uid in (2, 4):
            self.assertEqual(self.request("GET", "/supply/jobs?scope=company", uid=uid).status_code, 403)


if __name__ == "__main__":
    unittest.main()
