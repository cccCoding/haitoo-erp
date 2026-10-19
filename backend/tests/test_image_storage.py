from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, ReadTimeoutError

from app import storage


class ImageStorageDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        settings = SimpleNamespace(r2_endpoint="https://r2.invalid", r2_account_id=None,
            r2_access_key_id="private-access", r2_secret_access_key="private-secret",
            r2_bucket="images", r2_public_base_url="https://images.invalid")
        self.enterContext(patch.object(storage, "get_settings", return_value=settings))
        self.enterContext(patch.object(storage, "_r2_client", return_value=self.client))

    def test_download_reports_headers_and_body_separately_and_closes_stream(self):
        body = BytesIO(b"private-image-body")
        self.client.get_object.return_value = {"Body": body, "ContentLength": 18,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RetryAttempts": 2}}
        with self.assertLogs("app.storage", level="INFO") as logs:
            self.assertEqual(storage.read_image_object("image-upload-tmp/company/1/a.png"),
                b"private-image-body")
        output = "\n".join(logs.output)
        self.assertIn("请求完成 | operation=get_object", output)
        self.assertIn("请求完成 | operation=read_body", output)
        self.assertIn("retry_attempts=2", output)
        self.assertNotIn("private-image-body", output)
        self.assertNotIn("private-secret", output)
        self.assertTrue(body.closed)

    def test_save_reports_put_and_head_retries_and_preserves_verification(self):
        self.client.put_object.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200, "RetryAttempts": 1}}
        self.client.head_object.return_value = {"ContentLength": 3, "Metadata": {"sha256": "abc"},
            "ResponseMetadata": {"HTTPStatusCode": 200, "RetryAttempts": 0}}
        with self.assertLogs("app.storage", level="INFO") as logs:
            key, url = storage.save_content_image(b"png", "image/png", 1, "abc")
        self.assertEqual(key, "images/company/1/abc.png")
        self.assertEqual(url, "https://images.invalid/images/company/1/abc.png")
        output = "\n".join(logs.output)
        self.assertIn("请求完成 | operation=put_object", output)
        self.assertIn("请求完成 | operation=head_object", output)
        self.assertIn("retry_attempts=1", output)
        self.client.head_object.return_value["ContentLength"] = 4
        with self.assertRaisesRegex(storage.StorageError, "图片保存核验失败"):
            storage.save_content_image(b"png", "image/png", 1, "abc")

    def test_storage_failure_identifies_stage_without_logging_signed_url_or_error_text(self):
        signed_url = "https://r2.invalid/images?X-Amz-Signature=private-signature"
        self.client.put_object.return_value = {}
        self.client.head_object.side_effect = ClientError({
            "Error": {"Code": "AccessDenied", "Message": signed_url},
            "ResponseMetadata": {"HTTPStatusCode": 403, "RetryAttempts": 3}}, "HeadObject")
        with self.assertLogs("app.storage", level="INFO") as logs:
            with self.assertRaisesRegex(storage.StorageError, "保存图片到 R2 失败"):
                storage.save_content_image(b"png", "image/png", 1, "abc")
        output = "\n".join(logs.output)
        self.assertIn("请求失败 | operation=head_object", output)
        self.assertIn("exception_type=ClientError error_code=AccessDenied status=403 retry_attempts=3", output)
        self.assertNotIn(signed_url, output)
        self.assertNotIn("private-signature", output)
        self.assertTrue(all(record.exc_info is None for record in logs.records))

    def test_stream_timeout_logs_before_failure_and_still_closes_body(self):
        body = Mock()
        self.client.get_object.return_value = {"Body": body}
        with self.assertLogs("app.storage", level="INFO") as logs:
            def fail_read(*args):
                self.assertTrue(any("请求开始 | operation=read_body" in line for line in logs.output))
                raise ReadTimeoutError(endpoint_url="https://r2.invalid/?private-signature")
            body.read.side_effect = fail_read
            with self.assertRaisesRegex(storage.StorageError, "读取已上传图片失败"):
                storage.read_image_object("image-upload-tmp/company/1/a.png")
        output = "\n".join(logs.output)
        self.assertIn("请求失败 | operation=read_body", output)
        self.assertIn("exception_type=ReadTimeoutError", output)
        self.assertNotIn("private-signature", output)
        body.close.assert_called_once()
