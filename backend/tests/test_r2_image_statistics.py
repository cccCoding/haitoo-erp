import csv
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from app.config import Settings
from app.storage import _r2_client
from scripts.r2_image_statistics import collect_statistics, create_client, readable_size, run, write_report


class R2ImageStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(_env_file=None, r2_endpoint="https://r2.example.invalid",
                                 r2_access_key_id="test-access", r2_secret_access_key="test-secret",
                                 r2_bucket="images")
        self.client = _r2_client(self.settings.r2_endpoint, "test-access", "test-secret")

    def test_pagination_counts_bytes_and_groups_images_by_directory(self):
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {
                "IsTruncated": True, "NextContinuationToken": "page2",
                "Contents": [
                    {"Key": "generated/task-1/company/3/a.png", "Size": 1024},
                    {"Key": "generated/task-2/company/3/b.JPG", "Size": 3072},
                    {"Key": "material/company/3/zero.webp", "Size": 0},
                    {"Key": "report.csv", "Size": 200},
                ],
            }, {"Bucket": "images", "Prefix": "", "MaxKeys": 1000})
            stub.add_response("list_objects_v2", {
                "IsTruncated": False, "Contents": [
                    {"Key": "material/company/3/c.jpeg", "Size": 2048},
                    {"Key": "root.avif", "Size": 512},
                    {"Key": "folder.png/", "Size": 0},
                    {"Key": "unknown-image", "Size": 100},
                ],
            }, {"Bucket": "images", "Prefix": "", "MaxKeys": 1000, "ContinuationToken": "page2"})
            rows = collect_statistics(self.client, "images")
            stub.assert_no_pending_responses()
        groups = dict(rows)
        self.assertEqual((groups["全部对象"].count, groups["全部对象"].total_bytes), (8, 6956))
        self.assertEqual((groups["图片合计"].count, groups["图片合计"].total_bytes), (5, 6656))
        self.assertEqual((groups["非图片对象"].count, groups["非图片对象"].total_bytes), (3, 300))
        self.assertEqual(groups["generated/"].cells("generated/")[3], "2.00 KiB")
        self.assertEqual((groups["图片合计"].min_bytes, groups["图片合计"].max_bytes), (0, 3072))
        self.assertEqual([label for label, _ in rows[:3]], ["全部对象", "图片合计", "非图片对象"])
        self.assertEqual([label for label, _ in rows[3:]], sorted(groups.keys() - {"全部对象", "图片合计", "非图片对象"}))

    def test_prefix_passed_exactly_and_empty_page_returns_zero_rows(self):
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"IsTruncated": False},
                              {"Bucket": "images", "Prefix": "generated/task-1/", "MaxKeys": 1000})
            rows = collect_statistics(self.client, "images", "generated/task-1/")
        self.assertEqual(len(rows), 3)
        for _, stats in rows:
            self.assertEqual((stats.count, stats.total_bytes, stats.min_bytes, stats.max_bytes), (0, 0, 0, 0))
            self.assertEqual(stats.cells("empty")[2:], ("0.00 KiB",) * 4)

    def test_readable_size_uses_binary_units(self):
        self.assertEqual(readable_size(0), "0.00 KiB")
        self.assertEqual(readable_size(512), "0.50 KiB")
        self.assertEqual(readable_size(1024), "1.00 KiB")
        self.assertEqual(readable_size(1024 ** 2), "1.00 MiB")
        self.assertEqual(readable_size(1.5 * 1024 ** 3), "1.50 GiB")
        self.assertEqual(readable_size(1024 ** 4), "1.00 TiB")
        self.assertEqual(readable_size(1024 ** 5), "1024.00 TiB")

    def test_client_uses_account_endpoint_and_does_not_require_public_url(self):
        settings = self.settings.model_copy(update={"r2_endpoint": None, "r2_account_id": "account",
                                                   "r2_public_base_url": None})
        with patch("scripts.r2_image_statistics._r2_client") as client:
            create_client(settings)
        client.assert_called_once_with("https://account.r2.cloudflarestorage.com", "test-access", "test-secret")

    def test_missing_configuration_fails_without_request(self):
        for field in ("r2_endpoint", "r2_access_key_id", "r2_secret_access_key", "r2_bucket"):
            with self.subTest(field=field), patch("scripts.r2_image_statistics.get_settings", return_value=
                    self.settings.model_copy(update={field: None, "r2_account_id": None})), \
                    patch("scripts.r2_image_statistics._r2_client") as client, \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as errors:
                self.assertEqual(run([]), 1)
            client.assert_not_called()
            self.assertEqual(output.getvalue(), "")
            self.assertIn("未配置", errors.getvalue())

    def test_cli_csv_contains_only_report_and_matches_table_values(self):
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"Contents": [{"Key": "generated/a.png", "Size": 1500}]},
                              {"Bucket": "images", "Prefix": "generated/", "MaxKeys": 1000})
            with patch("scripts.r2_image_statistics.get_settings", return_value=self.settings), \
                    patch("scripts.r2_image_statistics.create_client", return_value=self.client), \
                    redirect_stdout(StringIO()) as output:
                self.assertEqual(run(["--prefix", "generated/", "--format", "csv"]), 0)
        csv_rows = list(csv.reader(StringIO(output.getvalue())))
        self.assertEqual(csv_rows[0], ["统计范围", "文件数量", "总大小", "平均大小", "最小大小", "最大大小"])
        self.assertEqual(csv_rows[2], ["图片合计", "1", "1.46 KiB", "1.46 KiB", "1.46 KiB", "1.46 KiB"])
        self.assertNotIn("字节", output.getvalue())
        self.assertNotIn("1500", output.getvalue())
        # CSV 中目录名称包含特殊字符时，仍可正确读取。
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {"Contents": [{"Key": 'dir,"one"/a.png', "Size": 1500}]},
                              {"Bucket": "images", "Prefix": "", "MaxKeys": 1000})
            rows = collect_statistics(self.client, "images")
        table_output, csv_output = StringIO(), StringIO()
        write_report(rows, table_output, "table")
        write_report(rows, csv_output, "csv")
        self.assertEqual([line.split("\t") for line in table_output.getvalue().splitlines()],
                         list(csv.reader(StringIO(csv_output.getvalue()))))

    def test_later_page_failure_does_not_print_partial_summary(self):
        with Stubber(self.client) as stub:
            stub.add_response("list_objects_v2", {
                "IsTruncated": True, "NextContinuationToken": "page2",
                "Contents": [{"Key": "a.png", "Size": 1024}],
            }, {"Bucket": "images", "Prefix": "", "MaxKeys": 1000})
            stub.add_client_error("list_objects_v2", service_error_code="AccessDenied",
                                  service_message="private secret", http_status_code=403,
                                  expected_params={"Bucket": "images", "Prefix": "", "MaxKeys": 1000,
                                                   "ContinuationToken": "page2"})
            with patch("scripts.r2_image_statistics.get_settings", return_value=self.settings), \
                    patch("scripts.r2_image_statistics.create_client", return_value=self.client), \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as errors:
                self.assertEqual(run(["--format", "csv"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("AccessDenied", errors.getvalue())
        self.assertNotIn("secret", errors.getvalue())

    def test_connection_failure_does_not_expose_endpoint_or_credentials(self):
        with patch("scripts.r2_image_statistics.get_settings", return_value=self.settings), \
                patch("scripts.r2_image_statistics.create_client", side_effect=EndpointConnectionError(
                    endpoint_url="https://test-secret.example.com")), \
                redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as errors:
            self.assertEqual(run([]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("R2 连接失败", errors.getvalue())
        self.assertNotIn("test-secret", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
