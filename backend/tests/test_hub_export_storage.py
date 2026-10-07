import hashlib
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from app import storage


class HubExportStorageTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        settings = SimpleNamespace(r2_endpoint="https://r2.invalid", r2_account_id=None, r2_access_key_id="access", r2_secret_access_key="secret", r2_hub_export_bucket="private")
        for target, value in (("get_settings", settings), ("_r2_client", self.client)):
            mock = patch.object(storage, target, return_value=value)
            mock.start(); self.addCleanup(mock.stop)

    def test_private_upload_and_verified_download(self):
        data = b"PK fixed Excel"
        url = storage.upload_hub_export(data, 1)
        self.assertTrue(url.startswith("https://r2.invalid/private/hub-exports/company/1/"))
        self.assertNotIn("?", url)
        self.assertEqual(self.client.put_object.call_args.kwargs["Body"], data)
        body = BytesIO(data)
        self.client.get_object.return_value = {"Body": body}
        self.assertEqual(storage.read_hub_export(url, 1, len(data), hashlib.sha256(data).hexdigest()), data)
        self.assertTrue(body.closed)

    def test_rejects_foreign_company_and_arbitrary_links(self):
        for url in ("https://evil.invalid/file.xlsx", "https://r2.invalid/private/hub-exports/company/2/a.xlsx", "https://r2.invalid/private/hub-exports/company/1/../a.xlsx"):
            with self.assertRaises(storage.StorageError): storage.read_hub_export(url, 1, 10, "x")
        self.client.get_object.assert_not_called()

    def test_checksum_and_size_mismatch_rejected(self):
        url = "https://r2.invalid/private/hub-exports/company/1/a.xlsx"
        for data, size, checksum in ((b"changed", 7, "wrong"), (b"too long", 2, "wrong")):
            self.client.get_object.return_value = {"Body": BytesIO(data)}
            with self.assertRaises(storage.StorageError): storage.read_hub_export(url, 1, size, checksum)

    def test_private_bucket_required(self):
        storage.get_settings().r2_hub_export_bucket = None
        with self.assertRaisesRegex(storage.StorageError, "R2_HUB_EXPORT_BUCKET"):
            storage.upload_hub_export(b"PK", 1)
        self.client.put_object.assert_not_called()
