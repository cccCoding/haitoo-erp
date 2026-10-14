"""货盘素材统计、任务明细分页与数据库聚合回归。"""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import event

from app.models import MaterialAsset, SupplyAudit, SupplyJob, SupplyJobMaterial
from test_supply_catalog import SupplyFixture


class SupplyStatisticsTests(SupplyFixture, unittest.TestCase):
    def add_job(self, db, identity, *, user_id=4, company_id=1, state="completed", links=1,
                material_id=1, successful=True, agent_id=1, agent_name="原代理", completed_at=None):
        job = SupplyJob(id=identity, company_id=company_id, user_id=user_id,
            agent_id=agent_id, agent_name=agent_name, template_id=1, category_catalog_id=1,
            idempotency_key=f"statistics-{identity}", request_hash="a" * 64, category_blob=b"large-template",
            snapshot={"user_name": f"历史用户{user_id}", "strategy": {"link_count": links}},
            state=state, completed_at=completed_at or datetime(2026, 10, 17, 10))
        db.add(job)
        for index in range(links):
            db.add(SupplyJobMaterial(company_id=company_id, job_id=identity, material_id=material_id,
                version_hash="a" * 64, link_index=index, successful=successful))
        return job

    def test_summary_and_details_share_success_scope_and_task_granularity(self):
        with self.sessions() as db:
            self.add_job(db, 1, links=10)
            self.add_job(db, 2, user_id=2, links=3)
            self.add_job(db, 3, state="failed", links=7)
            self.add_job(db, 4, state="running", links=5)
            self.add_job(db, 5, links=4, successful=False)
            self.add_job(db, 6, company_id=2, user_id=6, links=2)
            # 错误关联的公司字段也不能将外公司的任务计入本公司。
            db.add(SupplyJobMaterial(company_id=1, job_id=6, material_id=1,
                version_hash="b" * 64, link_index=0, successful=True))
            db.add(SupplyJobMaterial(company_id=1, job_id=1, material_id=1,
                version_hash="c" * 64, link_index=-1, successful=False))
            db.get(MaterialAsset, 1).supply_listed = False
            db.get(MaterialAsset, 1).supply_listed_at = datetime(2026, 10, 16)
            db.commit()
        response = self.request("GET", "/supply/materials", params={"listed": "false"})
        self.assertEqual(response.status_code, 200, response.text)
        result = next(row for row in response.json()["items"] if row["id"] == 1)
        self.assertEqual((result["user_count"], result["job_count"], result["use_count"]), (2, 2, 13))
        details = self.request("GET", "/supply/materials/1/usage").json()
        self.assertEqual(details["total"], 2)
        self.assertEqual(details["page_size"], 20)
        self.assertEqual([row["job_id"] for row in details["items"]], [2, 1])
        self.assertEqual([row["link_count"] for row in details["items"]], [3, 10])
        self.assertEqual(sum(row["link_count"] for row in details["items"]), result["use_count"])
        self.assertEqual(details["items"][0]["user_name"], "历史用户2")
        personal = self.request("GET", "/supply/materials/1/usage", uid=2).json()
        self.assertEqual(personal["total"], 1)
        self.assertEqual(personal["items"][0]["job_id"], 2)
        self.assertEqual(self.request("GET", "/supply/materials/1/usage", uid=3).json()["total"], 2)
        self.assertEqual(self.request("GET", "/supply/materials/99/usage").status_code, 404)

    def test_pagination_reaches_all_history_with_stable_completion_order(self):
        with self.sessions() as db:
            for identity in range(1, 206):
                self.add_job(db, identity, completed_at=datetime(2026, 10, 17) + timedelta(days=identity % 2))
            db.commit()
        seen = []
        for page in range(1, 12):
            response = self.request("GET", "/supply/materials/1/usage", params={"page": page})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual((result["total"], result["page"], result["page_size"]), (205, page, 20))
            self.assertEqual(len(result["items"]), 20 if page < 11 else 5)
            seen.extend(row["job_id"] for row in result["items"])
        self.assertEqual(seen, sorted(range(1, 206), key=lambda identity: (identity % 2, identity), reverse=True))
        self.assertEqual(self.request("GET", "/supply/materials/1/usage?page=12").json(),
            {"items": [], "total": 205, "page": 12, "page_size": 20})
        self.assertEqual(self.request("GET", "/supply/materials/2/usage").json()["total"], 0)
        for query in ("page=0", "page_size=0", "page_size=101"):
            self.assertEqual(self.request("GET", f"/supply/materials/1/usage?{query}").status_code, 422)

    def test_overview_aggregates_metrics_without_material_list_or_download_fanout(self):
        with self.sessions() as db:
            self.add_job(db, 1, links=10)
            self.add_job(db, 2, user_id=2, links=3, agent_name="代理新名称")
            self.add_job(db, 3, state="failed", links=7, agent_name="代理最新名称")
            self.add_job(db, 4, user_id=2, links=2, agent_id=None, agent_name=None)
            self.add_job(db, 5, company_id=2, user_id=6, links=9, agent_id=2)
            for job_id, company_id, action, target in ((1, 1, "download", "job"), (1, 1, "download", "job"),
                (4, 1, "download", "job"), (5, 2, "download", "job"), (1, 2, "download", "job"),
                (1, 1, "download", "material"), (1, 1, "submit", "job")):
                db.add(SupplyAudit(company_id=company_id, user_id=1, action=action,
                    target_type=target, target_id=job_id))
            db.commit()
        with patch("app.supply_catalog.material_statistics", side_effect=AssertionError("不能聚合全部素材")):
            response = self.request("GET", "/supply/statistics")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["summary"], {"job_count": 4, "success_count": 3,
            "user_count": 2, "download_count": 3, "use_count": 15})
        self.assertNotIn("materials", result)
        agents = {row["agent_id"]: row for row in result["agents"]}
        self.assertEqual(agents[1], {"agent_id": 1, "agent_name": "代理最新名称", "job_count": 3,
            "success_count": 2, "user_count": 2, "link_count": 13, "download_count": 2})
        self.assertEqual(agents[None]["agent_name"], "内部使用")
        self.assertEqual(agents[None]["download_count"], 1)

    def test_empty_overview_and_queries_do_not_load_job_blobs(self):
        self.assertEqual(self.request("GET", "/supply/statistics").json(), {
            "summary": {"job_count": 0, "success_count": 0, "user_count": 0, "download_count": 0, "use_count": 0},
            "agents": []})
        with self.sessions() as db:
            self.add_job(db, 1, links=10)
            db.commit()
        statements = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            for path in ("/supply/statistics", "/supply/materials/1/usage?page_size=1"):
                self.assertEqual(self.request("GET", path).status_code, 200)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        job_queries = [sql for sql in statements if "supply_jobs" in sql]
        self.assertTrue(job_queries)
        self.assertTrue(any("LIMIT" in sql and "OFFSET" in sql for sql in job_queries))
        for sql in job_queries:
            self.assertNotIn("category_blob", sql)
            self.assertNotIn("export_blob", sql)
            self.assertNotIn("supply_jobs.checkpoint", sql)


if __name__ == "__main__":
    unittest.main()
