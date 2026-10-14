import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import supply_internal_export
from app.database import Base
from app.models import Company, SupplyImageHealth
from app.supply_common import begin_check, digest, finish_check


class InternalExportImageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1, name="公司一"), Company(id=2, name="公司二")])
            db.commit()
        self.products = [{"image_urls": ["https://img.example/main.png", "https://img.example/shared.png"],
            "sku_images": [{"image_url": "https://img.example/sku.png", "sku": "SOURCE1"}, {"image_url": "https://img.example/shared.png", "sku": "SOURCE2"}],
            "size_chart_url": "https://img.example/sizes.png"},
            {"image_urls": ["https://img.example/shared.png"], "sku_images": [{"image_url": "https://img.example/sku.png", "sku": "SOURCE1"}],
             "size_chart_url": "https://img.example/sizes.png"}]

    def tearDown(self):
        self.engine.dispose()

    def test_deduplicates_every_exported_image_and_shares_health_without_replacement(self):
        original = copy.deepcopy(self.products)
        async def check(url):
            with self.sessions() as db:
                self.assertEqual(db.scalar(select(SupplyImageHealth).where(SupplyImageHealth.url == url)).check_sequence, 1)
            self.assertFalse(export_session.in_transaction())
            return {"status": "available", "reason": ""}
        with self.sessions() as export_session, patch.object(supply_internal_export, "check_image", AsyncMock(side_effect=check)) as probe:
            supply_internal_export.validate_export_images(export_session, 1, self.products)
        self.assertEqual(probe.await_count, 4)
        self.assertEqual(self.products, original)
        with self.sessions() as db:
            records = db.scalars(select(SupplyImageHealth)).all()
            self.assertEqual(len(records), 4)
            self.assertTrue(all(record.company_id == 1 and record.status == "available" and record.checked_at for record in records))

    def test_temporary_failures_retry_three_times_and_report_urls(self):
        calls = {}
        async def check(url):
            calls[url] = calls.get(url, 0) + 1
            return {"status": "invalid" if url.endswith("sizes.png") else "check_failed", "reason": "source unavailable"}
        with self.sessions() as db, patch.object(supply_internal_export, "check_image", AsyncMock(side_effect=check)), patch.object(supply_internal_export, "RETRY_DELAYS", (0, 0)):
            with self.assertRaises(HTTPException) as error:
                supply_internal_export.validate_export_images(db, 1, self.products)
            self.assertEqual(error.exception.status_code, 400)
            for url in supply_internal_export._export_urls(self.products):
                self.assertIn(url, error.exception.detail)
            records = {item.url: item for item in db.scalars(select(SupplyImageHealth)).all()}
            self.assertEqual(records["https://img.example/sizes.png"].status, "invalid")
            self.assertEqual(records["https://img.example/main.png"].status, "check_failed")
        self.assertEqual(calls["https://img.example/sizes.png"], 1)
        self.assertEqual(calls["https://img.example/main.png"], 3)

    def test_concurrency_is_bounded_and_timeout_marks_unfinished_images(self):
        active = 0
        peak = 0
        async def check(url):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            try:
                await asyncio.sleep(.1)
                return {"status": "available", "reason": ""}
            finally:
                active -= 1
        products = [{"image_urls": [f"https://img.example/{index}.png" for index in range(8)]}]
        with self.sessions() as db, patch.object(supply_internal_export, "check_image", AsyncMock(side_effect=check)), patch.object(supply_internal_export, "EXPORT_CHECK_TIMEOUT", .01):
            with self.assertRaisesRegex(HTTPException, "时间预算"):
                supply_internal_export.validate_export_images(db, 1, products)
            self.assertTrue(all(record.status == "check_failed" for record in db.scalars(select(SupplyImageHealth)).all()))
        self.assertEqual(peak, 4)
        self.assertEqual(active, 0)

    def test_old_result_does_not_overwrite_newer_manual_check(self):
        url = "https://img.example/main.png"
        async def check(_):
            with self.sessions() as db:
                sequence = begin_check(db, 1, url)
                finish_check(db, 1, url, sequence, {"status": "available", "reason": "newer check"})
            return {"status": "invalid", "reason": "older request result"}
        with self.sessions() as db, patch.object(supply_internal_export, "check_image", AsyncMock(side_effect=check)):
            with self.assertRaises(HTTPException):
                supply_internal_export.validate_export_images(db, 1, [{"image_urls": [url]}])
            db.expire_all()
            record = db.scalar(select(SupplyImageHealth).where(SupplyImageHealth.url_hash == digest(url)))
            self.assertEqual(record.check_sequence, 2)
            self.assertEqual(record.status, "available")
            self.assertEqual(record.reason, "newer check")

    def test_empty_products_do_not_touch_health_or_network(self):
        with self.sessions() as db, patch.object(supply_internal_export, "check_image", AsyncMock()) as probe:
            supply_internal_export.validate_export_images(db, 1, [])
            self.assertFalse(db.in_transaction())
        probe.assert_not_called()

    def test_transient_recovery_restores_health_only_in_current_company(self):
        url = "https://img.example/main.png"
        with self.sessions() as db:
            db.add_all([SupplyImageHealth(company_id=1, url=url, url_hash=digest(url), status="invalid", check_sequence=4),
                SupplyImageHealth(company_id=2, url=url, url_hash=digest(url), status="invalid", check_sequence=8)])
            db.commit()
        probe = AsyncMock(side_effect=[{"status": "check_failed", "reason": "temporary"}, {"status": "available", "reason": ""}])
        with self.sessions() as db, patch.object(supply_internal_export, "check_image", probe), patch.object(supply_internal_export, "RETRY_DELAYS", (0, 0)):
            supply_internal_export.validate_export_images(db, 1, [{"image_urls": [url]}])
            records = {record.company_id: record for record in db.scalars(select(SupplyImageHealth)).all()}
            self.assertEqual((records[1].status, records[1].check_sequence), ("available", 5))
            self.assertEqual((records[2].status, records[2].check_sequence), ("invalid", 8))
        self.assertEqual(probe.await_count, 2)

    def test_async_caller_rejected_before_database_mutation(self):
        async def call():
            with self.sessions() as db, patch.object(supply_internal_export, "check_image", AsyncMock()) as probe:
                with self.assertRaisesRegex(RuntimeError, "同步导出"):
                    supply_internal_export.validate_export_images(db, 1, self.products)
                self.assertFalse(db.in_transaction())
                probe.assert_not_called()
        asyncio.run(call())
