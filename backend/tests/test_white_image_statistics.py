import csv
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from botocore.stub import Stubber
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models import Company, ProductTemplate, User, UserTemplateWhiteImage
from app.storage import StorageError, _r2_client
from scripts.white_image_statistics import load_records, read_sizes, run, write_report


class WhiteImageStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.tables = [Company.__table__, User.__table__, ProductTemplate.__table__, UserTemplateWhiteImage.__table__]
        for table in self.tables:
            table.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions.begin() as db:
            for index in (1, 2):
                db.add(Company(id=index, name=f"公司{index}"))
                db.add(User(id=index, company_id=index, name="同名创作人", email=f"{index}@example.com", password_hash="unused"))
                db.add(ProductTemplate(id=index, company_id=index, name=f"模板{index}"))
        self.settings = Settings(_env_file=None, r2_endpoint="https://r2.example.invalid",
                                 r2_access_key_id="test-access", r2_secret_access_key="test-secret",
                                 r2_bucket="images", r2_public_base_url="https://images.example.com/assets")
        self.client = _r2_client(self.settings.r2_endpoint, "test-access", "test-secret")

    def add_image(self, image_id, **values):
        defaults = dict(id=image_id, company_id=1, user_id=1, template_id=1, name=f"白底图{image_id}",
                        image_url=f"https://images.example.com/assets/template-white/company/1/{image_id}.png")
        defaults.update(values)
        with self.sessions.begin() as db:
            db.add(UserTemplateWhiteImage(**defaults))

    def records(self, **filters):
        with self.sessions() as db:
            return load_records(db, **filters)

    def expected_request(self, company_id, **extra):
        return {"Bucket": "images", "Prefix": f"template-white/company/{company_id}/", "MaxKeys": 1000, **extra}

    def test_records_include_names_filters_and_missing_history(self):
        self.add_image(2, company_id=2, user_id=2, template_id=2,
                       image_url="https://images.example.com/assets/template-white/company/2/2.png")
        self.add_image(1)
        self.add_image(3, company_id=99, user_id=88, template_id=77)
        rows = self.records()
        self.assertEqual([row.image_id for row in rows], [1, 2, 3])
        self.assertEqual((rows[0].company_name, rows[0].creator_name, rows[0].template_name),
                         ("公司1", "同名创作人", "模板1"))
        self.assertEqual(rows[1].creator_name, rows[0].creator_name)
        self.assertNotEqual(rows[1].creator_id, rows[0].creator_id)
        self.assertEqual((rows[2].company_name, rows[2].creator_name, rows[2].template_name),
                         ("历史公司信息缺失", "历史人员信息缺失", "历史模板信息缺失"))
        self.assertEqual([row.image_id for row in self.records(company_id=2, creator_id=2, template_id=2)], [2])
        self.assertEqual([row.image_id for row in self.records(creator_id=1)], [1])
        self.assertEqual(self.records(company_id=1, template_id=2), [])

    def test_paginated_company_lists_match_sizes_and_mark_missing_objects(self):
        self.add_image(1)
        self.add_image(2)
        self.add_image(3, company_id=2, user_id=2, template_id=2,
                       image_url="https://images.example.com/assets/template-white/company/2/3.png")
        rows, progress = self.records(), StringIO()
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "next",
                              "Contents": [{"Key": "template-white/company/1/unregistered.png", "Size": 999}]},
                              self.expected_request(1))
            stub.add_response("list_objects_v2", {"IsTruncated": False,
                              "Contents": [{"Key": "template-white/company/1/1.png", "Size": 1024 ** 2}]},
                              self.expected_request(1, ContinuationToken="next"))
            stub.add_response("list_objects_v2", {"IsTruncated": False,
                              "Contents": [{"Key": "template-white/company/2/3.png", "Size": 0}]},
                              self.expected_request(2))
            with patch("scripts.white_image_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings, progress=progress)
            stub.assert_no_pending_responses()
        self.assertEqual([(row.size_bytes, row.status) for row in rows],
                         [(1024 ** 2, "正常"), (None, "R2 对象不存在"), (0, "正常")])
        self.assertEqual([row.cells()[8] for row in rows], ["1.00 MiB", "—", "0.00 KiB"])
        self.assertIn("已读取 3 页（公司 2）", progress.getvalue())
        self.assertIn("成功读取 2 条，无法读取 1 条", progress.getvalue())

    def test_duplicate_urls_are_matched_once_and_stop_after_all_targets_found(self):
        url = "https://images.example.com/assets/template-white/company/1/%E7%99%BD%E5%BA%95.png"
        self.add_image(1, image_url=url)
        self.add_image(2, image_url=url)
        rows = self.records()
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "unused",
                              "Contents": [{"Key": "template-white/company/1/白底.png", "Size": 512}]},
                              self.expected_request(1))
            with patch("scripts.white_image_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings)
            stub.assert_no_pending_responses()
        self.assertEqual([row.cells()[8] for row in rows], ["0.50 KiB"] * 2)

    def test_foreign_invalid_and_wrong_directory_links_do_not_request_r2(self):
        for index, url in enumerate((
            "https://other.example.com/a.png",
            "https://images.example.com.evil/assets/template-white/company/1/a.png",
            "https://images.example.com/assets/material/company/1/a.png",
            "https://images.example.com/assets/template-white/company/2/a.png",
            "https://images.example.com/assets/template-white/company/1/../a.png",
        ), start=1):
            self.add_image(index, image_url=url)
        rows = self.records()
        with patch("scripts.white_image_statistics.create_client") as client:
            read_sizes(rows, self.settings)
        client.assert_not_called()
        self.assertTrue(all(row.size_bytes is None and row.status != "待查询" for row in rows))

    def test_missing_public_url_is_configuration_error(self):
        self.add_image(1)
        with self.assertRaisesRegex(StorageError, "R2_PUBLIC_BASE_URL"):
            read_sizes(self.records(), self.settings.model_copy(update={"r2_public_base_url": None}))

    def test_empty_selection_no_requests_and_csv_header_only(self):
        with patch("scripts.white_image_statistics.SessionLocal", self.sessions), \
                patch("scripts.white_image_statistics.create_client") as client, \
                redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as progress:
            self.assertEqual(run(["--format", "csv"]), 0)
        client.assert_not_called()
        self.assertEqual(len(list(csv.reader(StringIO(output.getvalue())))), 1)
        self.assertIn("共 0 条记录", progress.getvalue())

    def test_cli_csv_progress_and_table_have_same_values(self):
        self.add_image(1, name='白底图,"一"')
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"Contents": [{"Key": "template-white/company/1/1.png", "Size": 2048}]},
                              self.expected_request(1))
            with patch("scripts.white_image_statistics.SessionLocal", self.sessions), \
                    patch("scripts.white_image_statistics.get_settings", return_value=self.settings), \
                    patch("scripts.white_image_statistics.create_client", return_value=self.client), \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as progress:
                self.assertEqual(run(["--format", "csv", "--company-id", "1", "--creator-id", "1", "--template-id", "1"]), 0)
        csv_rows = list(csv.reader(StringIO(output.getvalue())))
        self.assertEqual(csv_rows[1][1], '白底图,"一"')
        self.assertEqual(csv_rows[1][4:6], ["1", "同名创作人"])
        self.assertEqual(csv_rows[1][8:10], ["2.00 KiB", "正常"])
        self.assertIn("统计完成", progress.getvalue())
        self.assertNotIn("统计完成", output.getvalue())
        self.assertNotIn("字节", output.getvalue())
        rows = self.records()
        rows[0].size_bytes, rows[0].status = 2048, "正常"
        table = StringIO()
        write_report(rows, table, "table")
        self.assertEqual([line.split("\t") for line in table.getvalue().splitlines()], csv_rows)

    def test_no_progress_and_invalid_ids(self):
        with patch("scripts.white_image_statistics.SessionLocal", self.sessions), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()) as progress:
            self.assertEqual(run(["--no-progress"]), 0)
        self.assertEqual(progress.getvalue(), "")
        for args in (["--company-id", "0"], ["--creator-id", "-1"], ["--template-id", "abc"]):
            with self.subTest(args=args), patch("scripts.white_image_statistics.SessionLocal") as db, \
                    redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                run(args)
            db.assert_not_called()

    def test_later_page_failure_has_no_final_report_or_success_message(self):
        self.add_image(1)
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "next"},
                              self.expected_request(1))
            stub.add_client_error("list_objects_v2", service_error_code="AccessDenied", service_message="private-secret",
                                  expected_params=self.expected_request(1, ContinuationToken="next"))
            with patch("scripts.white_image_statistics.SessionLocal", self.sessions), \
                    patch("scripts.white_image_statistics.get_settings", return_value=self.settings), \
                    patch("scripts.white_image_statistics.create_client", return_value=self.client), \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as progress:
                self.assertEqual(run([]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("AccessDenied", progress.getvalue())
        self.assertIn("已读取 1 页", progress.getvalue())
        self.assertNotIn("统计完成", progress.getvalue())
        self.assertNotIn("private-secret", progress.getvalue())

    def test_database_is_only_read_and_business_data_unchanged(self):
        self.add_image(1)
        with self.engine.connect() as connection:
            before = [connection.execute(select(table)).all() for table in self.tables]
        statements = []

        def record_statement(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_statement)
        try:
            self.records()
        finally:
            event.remove(self.engine, "before_cursor_execute", record_statement)
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].lstrip().upper().startswith("SELECT"))
        with self.engine.connect() as connection:
            self.assertEqual(before, [connection.execute(select(table)).all() for table in self.tables])


if __name__ == "__main__":
    unittest.main()
