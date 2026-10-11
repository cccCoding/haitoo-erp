import csv
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
import unittest
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models import Company, PodTask, ProductTemplate, TaskStatus, User, UserTemplateWhiteImage
from app.storage import StorageError, _r2_client
from scripts.white_image_generation_statistics import SAMPLE_LIMIT, load_report, read_sizes, run, write_report


class WhiteImageGenerationStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.tables = [Company.__table__, User.__table__, ProductTemplate.__table__,
                       UserTemplateWhiteImage.__table__, PodTask.__table__]
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

    def white_url(self, image_id=1, company_id=1):
        return f"https://images.example.com/assets/template-white/company/{company_id}/{image_id}.png"

    def result_url(self, name, company_id=1):
        return f"https://images.example.com/assets/generated/task-1/company/{company_id}/{name}.png"

    def add_white(self, image_id=1, **values):
        defaults = dict(id=image_id, company_id=1, user_id=1, template_id=1, name=f"当前白底图{image_id}",
                        image_url=self.white_url(image_id))
        defaults.update(values)
        with self.sessions.begin() as db:
            db.add(UserTemplateWhiteImage(**defaults))

    def add_task(self, task_id, results=(), **values):
        defaults = dict(id=task_id, company_id=1, created_by=1, template_id=1, task_type="sku_image",
                        status=TaskStatus.AWAITING_SELECTION, selected_result_url=None,
                        created_at=datetime(2026, 10, 1), completed_at=datetime(2026, 10, 2),
                        parameters={"white_image_id": 1, "white_image_name": "历史白底图1", "white_image_url": self.white_url()},
                        result_urls=list(results))
        defaults.update(values)
        with self.sessions.begin() as db:
            db.add(PodTask(**defaults))

    def report(self, **filters):
        with self.sessions() as db:
            return load_report(db, **filters)

    def request(self, prefix, **extra):
        return {"Bucket": "images", "Prefix": prefix, "MaxKeys": 1000, **extra}

    def test_only_sku_all_candidates_deduplicated_without_adoption_filter(self):
        self.add_white()
        a, b, c = [self.result_url(name) for name in ("a", "b", "c")]
        self.add_task(1, [a, b, a], status=TaskStatus.COMPLETED, selected_result_url=a)
        self.add_task(2, [b, c], status=TaskStatus.AWAITING_SELECTION)
        self.add_task(3, [self.result_url("carousel")], task_type="carousel")
        self.add_task(4, [self.result_url("main")], task_type="main_image")
        report = self.report()
        self.assertEqual(report.task_count, 2)
        self.assertEqual(len(report.rows), 1)
        self.assertEqual(report.rows[0].sample_urls, [b, c, a])
        self.assertEqual(len(report.rows[0].generated_urls), 3)
        self.assertEqual(report.rows[0].creator_source, "白底图所属人员")

    def test_latest_2000_uses_completion_fallback_id_and_result_order(self):
        old_results = [self.result_url(f"old-{index}") for index in range(2005)]
        self.add_task(1, old_results, completed_at=datetime(2026, 10, 9))
        self.add_task(2, [self.result_url("older-finish")], created_at=datetime(2026, 10, 10),
                      completed_at=datetime(2026, 10, 8))
        fallback = self.result_url("fallback")
        self.add_task(3, [fallback, old_results[-1], fallback], created_at=datetime(2026, 10, 9), completed_at=None)
        row = self.report().rows[0]
        self.assertEqual(SAMPLE_LIMIT, 2000)
        self.assertEqual(row.sample_urls, ([fallback, old_results[-1]] + old_results[:-1])[:2000])
        self.assertEqual(len(row.generated_urls), 2007)
        self.assertNotIn(self.result_url("older-finish"), row.sample_urls)

    def test_changed_deleted_unused_and_unassociated_white_images(self):
        new_url = self.white_url("new")
        self.add_white(image_url=new_url)
        self.add_white(2)
        self.add_task(1, [self.result_url("old")])
        self.add_task(2, [self.result_url("new")], parameters={
            "white_image_id": 1, "white_image_name": "新版白底图", "white_image_url": new_url})
        self.add_task(3, [self.result_url("deleted")], parameters={
            "white_image_id": 77, "white_image_name": "已删除白底图", "white_image_url": self.white_url(77)})
        self.add_task(4, [self.result_url("missing-source")], parameters={"white_image_id": 1})
        report = self.report()
        by_url = {row.white_image_url: row for row in report.rows}
        self.assertEqual(len(report.rows), 4)
        self.assertEqual(report.unassociated_task_count, 1)
        self.assertEqual(len(by_url[self.white_url()].generated_urls), 1)
        self.assertEqual(by_url[self.white_url()].white_image_name, "历史白底图1")
        self.assertEqual(by_url[new_url].white_image_name, "新版白底图")
        self.assertEqual(by_url[self.white_url(77)].creator_source, "来源 SKU 任务创作人")
        self.assertEqual(by_url[self.white_url(77)].creator_id, 1)
        self.assertEqual(len(by_url[self.white_url(2)].generated_urls), 0)

    def test_filters_use_current_owner_not_task_creator_and_keep_company_isolation(self):
        self.add_white(user_id=2)
        self.add_white(2, company_id=2, user_id=2, template_id=2, image_url=self.white_url(2, 2))
        self.add_task(1, [self.result_url("a")], created_by=1)
        self.add_task(2, [self.result_url("b", 2)], company_id=2, created_by=2, template_id=2,
                      parameters={"white_image_id": 2, "white_image_url": self.white_url(2, 2)})
        filtered = self.report(company_id=1, creator_id=2, template_id=1, white_image_id=1)
        self.assertEqual(len(filtered.rows), 1)
        self.assertEqual(len(filtered.rows[0].generated_urls), 1)
        self.assertEqual(filtered.rows[0].creator_id, 2)
        self.assertEqual(self.report(company_id=1, creator_id=1).rows, [])
        self.assertEqual([row.company_id for row in self.report(template_id=2).rows], [2])
        self.assertEqual(self.report(white_image_id=999).rows, [])

    def test_source_url_without_id_is_preserved_and_missing_names_keep_ids(self):
        self.add_task(1, [self.result_url("legacy")], company_id=99, created_by=88, template_id=77,
                      parameters={"white_image_url": self.white_url("legacy", 99)})
        row = self.report().rows[0]
        self.assertIsNone(row.white_image_id)
        self.assertEqual(row.company_name, "历史公司信息缺失")
        self.assertEqual(row.creator_name, "历史人员信息缺失")
        self.assertEqual(row.template_name, "历史模板信息缺失")
        self.assertEqual(row.cells()[2], "—")
        self.assertEqual(row.creator_id, 88)

    def test_r2_pagination_known_samples_only_missing_non_r2_and_zero_size(self):
        self.add_white()
        urls = [self.result_url("zero"), self.result_url("large"), self.result_url("missing"),
                "https://external.example.com/a.png", self.result_url("foreign", 2)]
        self.add_task(1, urls)
        rows, progress = self.report().rows, StringIO()
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"Contents": [{"Key": "template-white/company/1/1.png", "Size": 512}]},
                              self.request("template-white/company/1/"))
            stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "next",
                              "Contents": [{"Key": "generated/task-1/company/1/zero.png", "Size": 0},
                                           {"Key": "generated/task-99/company/1/not-sampled.png", "Size": 999999}]},
                              self.request("generated/"))
            stub.add_response("list_objects_v2", {"IsTruncated": False,
                              "Contents": [{"Key": "generated/task-1/company/1/large.png", "Size": 2048}]},
                              self.request("generated/", ContinuationToken="next"))
            with patch("scripts.white_image_generation_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings, progress=progress)
            stub.assert_no_pending_responses()
        row = rows[0]
        self.assertEqual(row.white_size, 512)
        self.assertEqual((row.successful_count, row.sample_total_bytes), (2, 2048))
        self.assertEqual(row.cells()[12:17], ("5", "5", "2", "3", "1.00 KiB"))
        self.assertIn("R2 对象不存在：1", row.sample_status)
        self.assertIn("链接不属于当前 R2：1", row.sample_status)
        self.assertIn("图片目录或公司不匹配：1", row.sample_status)
        self.assertIn("已读取 3 页", progress.getvalue())
        self.assertIn("统计完成", progress.getvalue())

    def test_shared_object_size_reused_and_scanning_stops_early(self):
        self.add_white()
        self.add_white(2)
        shared = self.result_url("shared")
        self.add_task(1, [shared])
        self.add_task(2, [shared], parameters={"white_image_id": 2, "white_image_url": self.white_url(2)})
        rows = self.report().rows
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "unused-white",
                              "Contents": [{"Key": f"template-white/company/1/{index}.png", "Size": 1024} for index in (1, 2)]},
                              self.request("template-white/company/1/"))
            stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "unused-generated",
                              "Contents": [{"Key": "generated/task-1/company/1/shared.png", "Size": 3072}]},
                              self.request("generated/"))
            with patch("scripts.white_image_generation_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings)
            stub.assert_no_pending_responses()
        self.assertEqual([row.cells()[16] for row in rows], ["3.00 KiB"] * 2)

    def test_sample_failures_do_not_backfill_from_older_results(self):
        results = [self.result_url(index) for index in range(2001)]
        self.add_task(1, results)
        rows = self.report().rows
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": False}, self.request("template-white/company/1/"))
            stub.add_response("list_objects_v2", {"IsTruncated": False,
                              "Contents": [{"Key": "generated/task-1/company/1/2000.png", "Size": 4096}]},
                              self.request("generated/"))
            with patch("scripts.white_image_generation_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings)
        self.assertEqual(rows[0].cells()[12:17], ("2001", "2000", "0", "2000", "—"))

    def test_no_results_and_all_zero_samples(self):
        self.add_white()
        rows = self.report().rows
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"Contents": [{"Key": "template-white/company/1/1.png", "Size": 1024}]},
                              self.request("template-white/company/1/"))
            with patch("scripts.white_image_generation_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings)
        self.assertEqual(rows[0].cells()[12:18], ("0", "0", "0", "0", "—", "无生成结果"))
        self.add_task(1, [self.result_url("zero-a"), self.result_url("zero-b")])
        rows = self.report().rows
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": False}, self.request("template-white/company/1/"))
            stub.add_response("list_objects_v2", {"Contents": [
                {"Key": "generated/task-1/company/1/zero-a.png", "Size": 0},
                {"Key": "generated/task-1/company/1/zero-b.png", "Size": 0},
            ]}, self.request("generated/"))
            with patch("scripts.white_image_generation_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings)
        self.assertEqual(rows[0].successful_count, 2)
        self.assertEqual(rows[0].sample_status, "全部成功")
        self.assertEqual(rows[0].cells()[16], "0.00 KiB")

    def test_two_company_white_prefixes_and_one_generated_scan(self):
        self.add_white()
        self.add_white(2, company_id=2, user_id=2, template_id=2, image_url=self.white_url(2, 2))
        self.add_task(1, [self.result_url("one")])
        self.add_task(2, [self.result_url("two", 2)], company_id=2, created_by=2, template_id=2,
                      parameters={"white_image_id": 2, "white_image_url": self.white_url(2, 2)})
        rows = self.report().rows
        with Stubber(self.client) as stub:
            for company_id, image_id in ((1, 1), (2, 2)):
                stub.add_response("list_objects_v2", {"Contents": [
                    {"Key": f"template-white/company/{company_id}/{image_id}.png", "Size": 1024},
                ]}, self.request(f"template-white/company/{company_id}/"))
            stub.add_response("list_objects_v2", {"Contents": [
                {"Key": "generated/task-1/company/1/one.png", "Size": 2048},
                {"Key": "generated/task-1/company/2/two.png", "Size": 4096},
            ]}, self.request("generated/"))
            with patch("scripts.white_image_generation_statistics.create_client", return_value=self.client):
                read_sizes(rows, self.settings)
            stub.assert_no_pending_responses()
        self.assertEqual([row.cells()[16] for row in rows], ["2.00 KiB", "4.00 KiB"])

    def test_cli_csv_and_table_values_progress_and_closed_database(self):
        self.add_white(name='白底图,"一"')
        self.add_task(1, [self.result_url("a")], parameters={
            "white_image_id": 1, "white_image_name": '白底图,"一"', "white_image_url": self.white_url()})
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"Contents": [{"Key": "template-white/company/1/1.png", "Size": 1024}]},
                              self.request("template-white/company/1/"))
            stub.add_response("list_objects_v2", {"Contents": [{"Key": "generated/task-1/company/1/a.png", "Size": 1024 ** 2}]},
                              self.request("generated/"))
            session = self.sessions()
            original_read_sizes = read_sizes
            with patch.object(session, "close", wraps=session.close) as close:
                def checked_read(rows, settings, **kwargs):
                    self.assertTrue(close.called)
                    return original_read_sizes(rows, settings, **kwargs)

                with patch("scripts.white_image_generation_statistics.SessionLocal", return_value=session), \
                        patch("scripts.white_image_generation_statistics.get_settings", return_value=self.settings), \
                        patch("scripts.white_image_generation_statistics.create_client", return_value=self.client), \
                        patch("scripts.white_image_generation_statistics.read_sizes", side_effect=checked_read), \
                        redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as progress:
                    self.assertEqual(run(["--format", "csv", "--company-id", "1", "--creator-id", "1",
                                          "--template-id", "1", "--white-image-id", "1"]), 0)
        csv_rows = list(csv.reader(StringIO(output.getvalue())))
        self.assertEqual(csv_rows[1][3], '白底图,"一"')
        self.assertEqual(csv_rows[1][16], "1.00 MiB")
        self.assertNotIn("字节", output.getvalue())
        self.assertNotIn("最大", output.getvalue())
        self.assertIn("数据库读取完成：1 个 SKU 任务", progress.getvalue())
        self.assertIn("统计完成", progress.getvalue())
        self.assertNotIn("统计完成", output.getvalue())
        report = self.report()
        report.rows[0].white_size, report.rows[0].white_status = 1024, "正常"
        report.rows[0].successful_count, report.rows[0].sample_total_bytes = 1, 1024 ** 2
        report.rows[0].sample_status = "全部成功"
        table_output = StringIO()
        write_report(report.rows, table_output, "table")
        self.assertEqual([line.split("\t") for line in table_output.getvalue().splitlines()], csv_rows)

    def test_no_progress_unassociated_warning_and_empty_report(self):
        with patch("scripts.white_image_generation_statistics.SessionLocal", self.sessions), \
                patch("scripts.white_image_generation_statistics.create_client") as client, \
                redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as errors:
            self.assertEqual(run(["--no-progress", "--format", "csv"]), 0)
        client.assert_not_called()
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(len(list(csv.reader(StringIO(output.getvalue())))), 1)
        self.add_task(1, [self.result_url("unknown")], parameters={"white_image_id": 1})
        with patch("scripts.white_image_generation_statistics.SessionLocal", self.sessions), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()) as errors:
            self.assertEqual(run(["--no-progress"]), 0)
        self.assertIn("未关联任务：1", errors.getvalue())
        self.assertNotIn("扫描", errors.getvalue())

    def test_invalid_filters_and_missing_configuration(self):
        for option in ("company-id", "creator-id", "template-id", "white-image-id"):
            with self.subTest(option=option), patch("scripts.white_image_generation_statistics.SessionLocal") as db, \
                    redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                run([f"--{option}", "0"])
            db.assert_not_called()
        self.add_white()
        with self.assertRaisesRegex(StorageError, "R2_PUBLIC_BASE_URL"):
            read_sizes(self.report().rows, self.settings.model_copy(update={"r2_public_base_url": None}))

    def test_partial_r2_failure_no_report_no_completion_no_secret(self):
        self.add_task(1, [self.result_url("a")])
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": False}, self.request("template-white/company/1/"))
            stub.add_client_error("list_objects_v2", service_error_code="AccessDenied", service_message="private-secret",
                                  expected_params=self.request("generated/"))
            with patch("scripts.white_image_generation_statistics.SessionLocal", self.sessions), \
                    patch("scripts.white_image_generation_statistics.get_settings", return_value=self.settings), \
                    patch("scripts.white_image_generation_statistics.create_client", return_value=self.client), \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as errors:
                self.assertEqual(run(["--format", "csv"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("AccessDenied", errors.getvalue())
        self.assertNotIn("统计完成", errors.getvalue())
        self.assertNotIn("private-secret", errors.getvalue())

    def test_database_and_connection_failure_no_report(self):
        with patch("scripts.white_image_generation_statistics.SessionLocal", side_effect=OperationalError(
                "SELECT", {}, Exception("private-secret"))), redirect_stdout(StringIO()) as output, \
                redirect_stderr(StringIO()) as errors:
            self.assertEqual(run([]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private-secret", errors.getvalue())
        self.add_white()
        with patch("scripts.white_image_generation_statistics.SessionLocal", self.sessions), \
                patch("scripts.white_image_generation_statistics.get_settings", return_value=self.settings), \
                patch("scripts.white_image_generation_statistics.create_client", side_effect=EndpointConnectionError(
                    endpoint_url="https://private-secret.example.com")), \
                redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as errors:
            self.assertEqual(run([]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private-secret", errors.getvalue())

    def test_database_reads_only_and_does_not_mutate_business_data(self):
        self.add_white()
        self.add_task(1, [self.result_url("a")])
        with self.engine.connect() as connection:
            before = [connection.execute(select(table)).all() for table in self.tables]
        statements = []

        def record_statement(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_statement)
        try:
            self.report()
        finally:
            event.remove(self.engine, "before_cursor_execute", record_statement)
        self.assertEqual(len(statements), 2)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in statements))
        with self.engine.connect() as connection:
            self.assertEqual(before, [connection.execute(select(table)).all() for table in self.tables])


if __name__ == "__main__":
    unittest.main()
