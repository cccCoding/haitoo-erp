"""白底图历史删除核对：只使用隔离内存库，不连接生产数据库或 R2。"""
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
import json
import unittest
from unittest.mock import patch

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, create_engine, event, insert
from sqlalchemy.orm import sessionmaker

from scripts import audit_white_image_deletions as audit


class WhiteImageDeletionAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine)

    def schema(self, *, legacy=False):
        metadata = MetaData()
        columns = [Column("id", Integer, primary_key=True), Column("company_id", Integer),
                   Column("user_id", Integer), Column("template_id", Integer), Column("image_url", String)]
        if not legacy:
            columns.append(Column("deleted_at", DateTime))
        self.white = Table("user_template_white_images", metadata, *columns)
        self.task = Table("pod_tasks", metadata, Column("id", Integer, primary_key=True),
                          Column("company_id", Integer), Column("template_id", Integer),
                          Column("created_by", Integer), Column("task_type", String), Column("parameters", JSON))
        if not legacy:
            self.style = Table("material_styles", metadata, Column("id", Integer, primary_key=True),
                               Column("company_id", Integer), Column("template_id", Integer),
                               Column("created_by", Integer), Column("source_white_image_id", Integer), Column("name", String))
        metadata.create_all(self.engine)

    def add_white(self, identity=1, **values):
        with self.engine.begin() as db:
            db.execute(insert(self.white).values(id=identity, **{
                "company_id": 1, "user_id": 2, "template_id": 3, "image_url": "https://img/white.png", **values}))

    def add_task(self, identity=1, **values):
        with self.engine.begin() as db:
            db.execute(insert(self.task).values(id=identity, **{
                "company_id": 1, "created_by": 2, "template_id": 3, "task_type": "sku_image",
                "parameters": {"white_image_id": 1, "white_image_name": "正面", "white_image_url": "https://img/white.png"},
                **values}))

    def add_style(self, identity=1, **values):
        with self.engine.begin() as db:
            db.execute(insert(self.style).values(id=identity, **{
                "company_id": 1, "created_by": 2, "template_id": 3, "source_white_image_id": 1, "name": "正面", **values}))

    def report(self, **filters):
        with self.sessions() as db:
            return audit.load_report(db, **filters)

    def test_legacy_schema_missing_sources_are_grouped_without_migration(self):
        self.schema(legacy=True)
        for identity in range(1, 8):
            self.add_task(identity)
        self.add_task(8, task_type="carousel")
        report = self.report()
        self.assertFalse(report["supports_soft_delete"])
        self.assertFalse(report["has_style_table"])
        self.assertEqual(report["counts"]["scanned_tasks"], 7)
        self.assertEqual(report["counts"]["missing_white_image_ids"], 1)
        self.assertEqual(report["rows"][0]["reference_count"], 7)
        self.assertEqual(report["rows"][0]["example_reference_ids"], [1, 2, 3, 4, 5])
        self.assertIn("疑似物理删除", report["conclusion"])

    def test_soft_deletion_and_renaming_are_not_physical_deletion(self):
        self.schema()
        self.add_white(deleted_at=datetime(2026, 10, 20))
        self.add_task()
        self.add_style(name="改名后的风格")
        report = self.report()
        self.assertEqual(report["rows"], [])
        self.assertEqual(report["counts"]["soft_deleted_tasks"], 1)
        self.assertEqual(report["counts"]["soft_deleted_styles"], 1)
        self.assertEqual(report["counts"]["soft_deleted_white_images"], 1)

    def test_historical_image_replacement_is_separate_from_missing_record(self):
        self.schema()
        self.add_white(image_url="https://img/new.png")
        self.add_task()
        row = self.report()["rows"][0]
        self.assertEqual(row["kind"], "url_changed")
        self.assertEqual(row["current_record"]["image_url"], "https://img/new.png")
        self.assertEqual(self.report()["counts"]["missing_white_image_ids"], 0)

    def test_global_id_lookup_detects_other_company_owner_and_template(self):
        self.schema()
        for overrides in ({"company_id": 9}, {"user_id": 9}, {"template_id": 9}):
            with self.subTest(overrides=overrides):
                # 清空测试数据；不能以公司筛选后的不存在误报物理删除。
                with self.engine.begin() as db:
                    db.execute(self.white.delete())
                    db.execute(self.task.delete())
                self.add_white(**overrides)
                self.add_task()
                report = self.report(company_id=1, creator_id=2, template_id=3)
                self.assertEqual(report["rows"][0]["kind"], "identity_mismatch")
                self.assertEqual(report["counts"]["missing_white_image_ids"], 0)

    def test_style_only_missing_source_and_unique_missing_id_count(self):
        self.schema()
        self.add_white()
        self.add_style()
        self.assertEqual(self.report()["rows"], [])
        with self.engine.begin() as db:
            db.execute(self.white.delete())
        self.assertEqual(self.report()["rows"][0]["source"], "style")
        self.add_task()
        report = self.report()
        self.assertEqual({row["source"] for row in report["rows"]}, {"task", "style"})
        self.assertEqual(report["counts"]["missing_white_image_ids"], 1)
        self.assertEqual(self.report(creator_id=99)["rows"], [])

    def test_invalid_or_absent_references_are_not_reported_as_deletions(self):
        self.schema(legacy=True)
        self.add_white()
        for identity, params in enumerate(({}, None, "bad json", [], {"white_image_id": True},
                {"white_image_id": -1}, {"white_image_id": 10**100}, {"white_image_url": "https://img/old.png"},
                json.dumps({"white_image_id": "1"})), 1):
            self.add_task(identity, parameters=params)
        report = self.report()
        self.assertEqual(report["counts"]["missing_white_image_ids"], 0)
        self.assertEqual(report["counts"]["unreferenced_tasks"], 1)
        self.assertEqual(report["counts"]["task_unverifiable"], 7)
        self.assertEqual(report["counts"]["matching_tasks"], 1)

    def test_pagination_scans_all_matches_and_output_limit_only_limits_details(self):
        self.schema()
        for identity in range(1, 7):
            self.add_task(identity, parameters={"white_image_id": identity})
        with patch.object(audit, "BATCH_SIZE", 2):
            report = self.report()
        output = StringIO()
        audit.write_report(report, output, output_format="json", limit=1)
        data = json.loads(output.getvalue())
        self.assertEqual(data["counts"]["scanned_tasks"], 6)
        self.assertEqual(data["total_groups"], 6)
        self.assertEqual(len(data["rows"]), 1)
        output = StringIO()
        audit.write_report(report, output, limit=0)
        self.assertIn("本次显示 6 个", output.getvalue())

    def test_audit_executes_no_data_or_schema_writes_and_cli_json_is_valid(self):
        self.schema()
        self.add_task()
        statements = []
        event.listen(self.engine, "before_cursor_execute", lambda conn, cursor, statement, params, context, many:
                     statements.append(statement))
        output = StringIO()
        with patch.object(audit, "SessionLocal", self.sessions), redirect_stdout(output):
            self.assertEqual(audit.run(["--format", "json", "--limit", "0"]), 0)
        self.assertEqual(json.loads(output.getvalue())["counts"]["missing_white_image_ids"], 1)
        self.assertTrue(all(statement.lstrip().split()[0].upper() in {"SELECT", "PRAGMA"} for statement in statements))


if __name__ == "__main__":
    unittest.main()
