import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from app import supply_files
from app.storage import ExportMissingError, StorageError


class SupplyFileTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        for target, value in (("_export_configuration", ("https://r2.invalid", "access", "secret", "private")), ("_r2_client", self.client)):
            patched = patch.object(supply_files, target, return_value=value)
            patched.start()
            self.addCleanup(patched.stop)
        self.data = b"PK fixed Excel"
        self.checksum = hashlib.sha256(self.data).hexdigest()
        self.client.head_object.return_value = {"ContentLength": len(self.data), "Metadata": {"sha256": self.checksum}}
        self.client.get_object.side_effect = lambda **kwargs: {"Body": BytesIO(self.data)}

    def test_upload_private_key_uses_company_job_execution_and_verifies_content(self):
        result = supply_files.upload_supply_export(1, 2, 3, "中文.xlsx", self.data)
        self.assertTrue(result["key"].startswith("supply-exports/company/1/jobs/2/3/"))
        self.assertEqual(result["sha256"], self.checksum)
        self.assertEqual(result["size"], len(self.data))
        call = self.client.put_object.call_args.kwargs
        self.assertEqual(call["Bucket"], "private")
        self.assertEqual(call["Body"], self.data)
        self.assertEqual(call["CacheControl"], "private, no-store")
        self.client.head_object.assert_called_once()
        body = BytesIO(self.data)
        self.client.get_object.side_effect = None
        self.client.get_object.return_value = {"Body": body}
        self.assertEqual(supply_files.read_supply_export(result["key"], self.checksum, len(self.data)), self.data)
        self.assertTrue(body.closed)
        supply_files.delete_supply_export(result["key"])
        self.client.delete_object.assert_called_once()

    def test_invalid_keys_rejected_before_sdk_access(self):
        for key in ("https://evil.invalid/a.xlsx", "hub-exports/company/1/a.xlsx", "supply-exports/company/1/jobs/2/3/../a.xlsx", "supply-exports/company/1/jobs/2/3/" + "a" * 32 + ".xlsx?download=1"):
            with self.assertRaises(StorageError):
                supply_files.read_supply_export(key, self.checksum, len(self.data))
            with self.assertRaises(StorageError):
                supply_files.delete_supply_export(key)
        self.client.get_object.assert_not_called()
        self.client.delete_object.assert_not_called()

    def test_failed_upload_verification_cleans_up_object(self):
        self.client.head_object.return_value = {"ContentLength": 1, "Metadata": {"sha256": self.checksum}}
        with self.assertRaisesRegex(StorageError, "校验失败"):
            supply_files.upload_supply_export(1, 2, 3, "file.xlsx", self.data)
        self.client.delete_object.assert_called_once()

    def test_download_checks_bytes_not_metadata_and_closes_stream(self):
        key = "supply-exports/company/1/jobs/2/3/" + "a" * 32 + ".xlsx"
        body = BytesIO(b"changed")
        self.client.get_object.side_effect = None
        self.client.get_object.return_value = {"Body": body}
        with self.assertRaisesRegex(StorageError, "校验失败"):
            supply_files.read_supply_export(key, self.checksum, len(self.data))
        self.assertTrue(body.closed)
        self.client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        with self.assertRaises(ExportMissingError):
            supply_files.read_supply_export(key, self.checksum, len(self.data))

    def test_new_uploads_have_unique_object_keys(self):
        first = supply_files.upload_supply_export(1, 2, 3, "file.xlsx", self.data)
        second = supply_files.upload_supply_export(1, 2, 3, "file.xlsx", self.data)
        self.assertNotEqual(first["key"], second["key"])

    def test_upload_checksum_verifies_actual_stored_bytes(self):
        self.client.get_object.side_effect = lambda **kwargs: {"Body": BytesIO(b"changed bytes!")}
        with self.assertRaisesRegex(StorageError, "校验失败"):
            supply_files.upload_supply_export(1, 2, 3, "file.xlsx", self.data)
        self.client.delete_object.assert_called_once()

    def test_orphan_listing_paginates_and_filters_age_and_key_namespace(self):
        cutoff = datetime(2026, 10, 14, tzinfo=timezone.utc)
        old_key = "supply-exports/company/1/jobs/2/3/" + "a" * 32 + ".xlsx"
        next_key = "supply-exports/company/2/jobs/3/4/" + "b" * 32 + ".xlsx"
        paginator = self.client.get_paginator.return_value
        paginator.paginate.return_value = [
            {"Contents": [
                {"Key": old_key, "LastModified": cutoff - timedelta(days=2)},
                {"Key": old_key.replace("a" * 32, "c" * 32), "LastModified": cutoff + timedelta(hours=1)},
                {"Key": "hub-exports/company/1/a.xlsx", "LastModified": cutoff - timedelta(days=2)},
                {"Key": "supply-exports/company/1/jobs/2/3/../a.xlsx", "LastModified": cutoff - timedelta(days=2)},
            ]},
            {},
            {"Contents": [{"Key": next_key, "LastModified": (cutoff - timedelta(hours=2)).astimezone(timezone(timedelta(hours=8)))}]},
        ]
        self.assertEqual(list(supply_files.list_supply_exports(cutoff)), [old_key, next_key])
        self.client.get_paginator.assert_called_once_with("list_objects_v2")
        paginator.paginate.assert_called_once_with(Bucket="private", Prefix="supply-exports/")
        self.client.delete_object.assert_not_called()

    def test_orphan_listing_treats_naive_database_time_as_utc_and_reports_failures(self):
        cutoff = datetime(2026, 10, 14)
        key = "supply-exports/company/1/jobs/2/3/" + "a" * 32 + ".xlsx"
        paginator = self.client.get_paginator.return_value
        paginator.paginate.return_value = [{"Contents": [{"Key": key, "LastModified": cutoff - timedelta(days=2)}]}]
        self.assertEqual(list(supply_files.list_supply_exports(cutoff)), [key])
        paginator.paginate.side_effect = RuntimeError("storage unavailable")
        with self.assertRaisesRegex(StorageError, "列举货盘"):
            list(supply_files.list_supply_exports(cutoff))
