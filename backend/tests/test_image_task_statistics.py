import csv
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from io import StringIO
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.models import Company, MaterialAsset, PodTask, TaskStatus, User
from scripts.image_task_statistics import collect_statistics, run, write_report


class ImageTaskStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.tables = [Company.__table__, User.__table__, PodTask.__table__, MaterialAsset.__table__]
        for table in self.tables:
            table.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)

    def add_task(self, **values):
        defaults = dict(company_id=1, created_by=1, template_id=1, task_type="sku_image",
                        status=TaskStatus.COMPLETED, created_at=datetime(2026, 10, 10, 12))
        defaults.update(values)
        with self.sessions.begin() as db:
            task = PodTask(**defaults)
            db.add(task)
            db.flush()
            return task.id

    def report(self, **filters):
        with self.sessions() as db:
            return collect_statistics(db, **filters)

    def test_all_types_count_only_nonempty_selection(self):
        for kind in ("sku_image", "carousel", "main_image"):
            for selected in (None, "", "https://example.com/adopted.png"):
                self.add_task(task_type=kind, selected_result_url=selected,
                              result_urls=["https://example.com/one.png", "https://example.com/two.png"],
                              submit_attempts=4)
        self.add_task(task_type="unrelated", selected_result_url="selected")
        rows = self.report()
        self.assertEqual([row.task_type for row in rows[:3]], ["sku_image", "carousel", "main_image"])
        self.assertEqual([(row.total, row.adopted) for row in rows[:3]], [(3, 1)] * 3)
        self.assertEqual([row.cells()[-1] for row in rows[:3]], ["33.33%"] * 3)

    def test_every_status_counts_and_does_not_control_adoption(self):
        for kind in ("sku_image", "carousel", "main_image"):
            for status in TaskStatus:
                self.add_task(task_type=kind, status=status, selected_result_url=None)
                self.add_task(task_type=kind, status=status, selected_result_url="selected")
        self.assertEqual([(row.total, row.adopted) for row in self.report()[:3]], [(10, 5)] * 3)

    def test_materials_do_not_change_adoption_or_duplicate_counts(self):
        task_id = self.add_task(selected_result_url=None)
        with self.sessions.begin() as db:
            for index in range(2):
                db.add(MaterialAsset(company_id=1, source_task_id=task_id, claimed_by=1,
                                     url=f"https://example.com/{index}.png", name="已领取素材"))
        self.assertEqual((self.report()[0].total, self.report()[0].adopted), (1, 0))

    def test_company_creator_filters_names_and_stable_order(self):
        with self.sessions.begin() as db:
            db.add_all([Company(id=1, name="公司一"), Company(id=2, name="公司二")])
            for user_id, company_id in ((1, 1), (2, 1), (3, 2)):
                db.add(User(id=user_id, company_id=company_id, name="同名人员",
                            email=f"{user_id}@example.com", password_hash="unused"))
        for company_id, creator_id, kind in ((99, 88, "sku_image"), (2, 3, "sku_image"),
                                            (1, 2, "main_image"), (1, 1, "main_image"),
                                            (1, 1, "carousel"), (1, 1, "sku_image")):
            self.add_task(company_id=company_id, created_by=creator_id, task_type=kind)
        details = self.report()[3:]
        self.assertEqual([(row.company_id, row.creator_id, row.task_type) for row in details], [
            (1, 1, "sku_image"), (1, 1, "carousel"), (1, 1, "main_image"),
            (1, 2, "main_image"), (2, 3, "sku_image"), (99, 88, "sku_image"),
        ])
        self.assertEqual(details[0].company_name, "公司一")
        self.assertEqual(details[0].creator_name, "同名人员")
        self.assertEqual(details[-1].company_name, "历史公司信息缺失")
        self.assertEqual(details[-1].creator_name, "历史人员信息缺失")
        self.assertEqual(sum(row.total for row in self.report(company_id=1)[:3]), 4)
        self.assertEqual(sum(row.total for row in self.report(creator_id=3)[:3]), 1)
        self.assertEqual(sum(row.total for row in self.report(company_id=1, creator_id=2)[:3]), 1)
        self.assertEqual(len(self.report(company_id=1, creator_id=3)), 3)

    def test_hong_kong_inclusive_dates_use_utc_boundaries(self):
        for timestamp in (
            datetime(2026, 10, 9, 15, 59, 59, 999999),
            datetime(2026, 10, 9, 16),
            datetime(2026, 10, 10, 15, 59, 59, 999999),
            datetime(2026, 10, 10, 16),
            datetime(2026, 10, 11, 15, 59, 59, 999999),
            datetime(2026, 10, 11, 16),
        ):
            self.add_task(created_at=timestamp)
        self.assertEqual(self.report(start_date=date(2026, 10, 10), end_date=date(2026, 10, 10))[0].total, 2)
        self.assertEqual(self.report(start_date=date(2026, 10, 10), end_date=date(2026, 10, 11))[0].total, 4)
        self.assertEqual(self.report(start_date=date(2026, 10, 10))[0].total, 5)
        self.assertEqual(self.report(end_date=date(2026, 10, 10))[0].total, 3)

    def test_empty_report_has_three_zero_summary_rows(self):
        rows = self.report()
        self.assertEqual(len(rows), 3)
        self.assertEqual([(row.total, row.adopted, row.cells()[-1]) for row in rows], [(0, 0, "0.00%")] * 3)

    def test_summary_rate_uses_combined_counts_instead_of_averaging_people(self):
        self.add_task(created_by=1, selected_result_url="selected")
        for _ in range(3):
            self.add_task(created_by=2)
        rows = self.report()
        self.assertEqual((rows[0].total, rows[0].adopted, rows[0].cells()[-1]), (4, 1, "25.00%"))
        self.assertEqual([row.cells()[-1] for row in rows[3:]], ["100.00%", "0.00%"])

    def test_table_csv_and_cli_are_consistent(self):
        with self.sessions.begin() as db:
            db.add(Company(id=1, name="公司,一"))
            db.add(User(id=1, company_id=1, name='人员 "一"', email="one@example.com", password_hash="unused"))
        self.add_task(selected_result_url="selected")
        self.add_task(selected_result_url="")
        table_output, csv_output = StringIO(), StringIO()
        with patch("scripts.image_task_statistics.SessionLocal", self.sessions):
            with redirect_stdout(table_output):
                self.assertEqual(run([]), 0)
            with redirect_stdout(csv_output):
                self.assertEqual(run(["--format", "csv", "--company-id", "1", "--creator-id", "1",
                                      "--start-date", "2026-10-10", "--end-date", "2026-10-10"]), 0)
        csv_rows = list(csv.reader(StringIO(csv_output.getvalue())))
        table_rows = [tuple(cell.strip() for cell in line.split(" | "))
                      for line in table_output.getvalue().splitlines()[2:]]
        self.assertEqual(table_rows, [tuple(row) for row in csv_rows[1:]])
        self.assertEqual(csv_rows[-1][2:5], ["公司,一", "1", '人员 "一"'])
        self.assertEqual(csv_rows[1][-3:], ["2", "1", "50.00%"])

    def test_csv_quotes_multiline_names_and_table_stays_single_line(self):
        with self.sessions.begin() as db:
            db.add(Company(id=1, name="公司\n一"))
        self.add_task()
        output = StringIO()
        write_report(self.report(), output, "csv")
        self.assertEqual(list(csv.reader(StringIO(output.getvalue())))[-1][2], "公司\n一")
        output = StringIO()
        write_report(self.report(), output)
        self.assertEqual(len(output.getvalue().splitlines()), 6)

    def test_invalid_arguments_rejected_before_database_access(self):
        for argv in (
            ["--start-date", "2026-02-30"], ["--end-date", "2026-1-1"],
            ["--start-date", "20261010"], ["--end-date", "9999-12-31"],
            ["--start-date", "2026-10-11", "--end-date", "2026-10-10"],
            ["--company-id", "0"], ["--creator-id", "-1"],
        ):
            with self.subTest(argv=argv), patch("scripts.image_task_statistics.SessionLocal") as sessions, \
                    redirect_stderr(StringIO()), self.assertRaises(SystemExit) as context:
                run(argv)
            self.assertEqual(context.exception.code, 2)
            sessions.assert_not_called()

    def test_query_failure_returns_error_without_leaking_connection_details(self):
        output, errors = StringIO(), StringIO()
        with patch("scripts.image_task_statistics.SessionLocal", side_effect=OperationalError(
            "SELECT", {}, Exception("password=secret"))), redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(run([]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("数据库查询失败", errors.getvalue())
        self.assertNotIn("secret", errors.getvalue())

    def test_statistics_only_execute_selects_and_preserve_business_data(self):
        self.add_task(selected_result_url="selected")
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
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].lstrip().upper().startswith("SELECT"))
        with self.engine.connect() as connection:
            after = [connection.execute(select(table)).all() for table in self.tables]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
