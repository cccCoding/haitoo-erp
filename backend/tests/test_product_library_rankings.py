from datetime import date, datetime, time, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import (
    Company, MaterialAsset, ProductLibraryDailySnapshot, ProductLibraryDailySnapshotItem, ProductLibraryRankingTask,
    ProductLibraryOrder, ProductLibraryOrderProduct, ProductLibraryProduct, ProductLibrarySource,
    Role, User,
)
from app import product_library_rankings as rankings
from app.security import create_access_token


HK = ZoneInfo("Asia/Hong_Kong")


def local_utc(day: date, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour), HK).astimezone(timezone.utc).replace(tzinfo=None)


def due(day: date) -> datetime:
    return datetime.combine(day, time(2), HK)


class ProductLibraryRankingTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name="First"), Company(id=2, name="Second"),
                User(id=1, company_id=1, email="a@example.com", name="A", password_hash="x", role=Role.MEMBER),
                User(id=2, company_id=2, email="b@example.com", name="B", password_hash="x", role=Role.MEMBER),
                ProductLibrarySource(id=1, company_id=1, platform="TikTok", site="马来", shop_name="First Shop"),
                ProductLibrarySource(id=2, company_id=2, platform="Shopee", site="马来", shop_name="Second Shop"),
            ])
            db.commit()
        self.day = date(2026, 9, 30)
        self.next_product_id = 1
        self.next_order_id = 1

    def tearDown(self):
        self.engine.dispose()

    def add_product(self, count: int, order_day: date, company_id: int = 1, hour: int = 12) -> int:
        product_id = self.next_product_id
        self.next_product_id += 1
        with self.sessions() as db:
            db.add(ProductLibraryProduct(id=product_id, company_id=company_id, source_id=company_id,
                external_product_id=f"external-{product_id}", sku=f"SKU-{product_id}",
                title=f"Product {product_id}", image_url=""))
            for _ in range(count):
                order_id = self.next_order_id
                self.next_order_id += 1
                db.add(ProductLibraryOrder(id=order_id, company_id=company_id, source_id=company_id,
                    order_number=f"order-{order_id}", ordered_at=local_utc(order_day, hour)))
                db.add(ProductLibraryOrderProduct(order_id=order_id, product_id=product_id))
            db.commit()
        return product_id

    def listing(self, category: str, company_id: int = 1, page: int = 1, page_size: int = 100):
        with self.sessions() as db:
            return main.list_product_library_rankings(category=category, page=page, page_size=page_size,
                user=db.get(User, company_id), db=db)

    def seed_snapshots(self, day: date | None = None):
        with self.sessions() as db:
            for company_id in (1, 2):
                rankings.create_daily_snapshot(db, company_id, day or self.day)

    def test_natural_day_windows_and_company_isolation(self):
        inside = self.add_product(2, self.day - timedelta(days=1), hour=23)
        self.add_product(1, self.day, hour=0)  # 今天的订单不计入昨日快照
        boundary_7 = self.add_product(1, self.day - timedelta(days=7), hour=0)
        boundary_15 = self.add_product(1, self.day - timedelta(days=15), hour=0)
        boundary_30 = self.add_product(1, self.day - timedelta(days=30), hour=0)
        self.add_product(1, self.day - timedelta(days=31), hour=23)
        other = self.add_product(5, self.day - timedelta(days=1), company_id=2)
        self.seed_snapshots()
        self.assertEqual([(row["id"], row["order_count"]) for row in self.listing("top7")["items"]],
            [(inside, 2), (boundary_7, 1)])
        self.assertEqual([row["id"] for row in self.listing("top15")["items"]], [inside, boundary_7, boundary_15])
        self.assertEqual([row["id"] for row in self.listing("top30")["items"]],
            [inside, boundary_7, boundary_15, boundary_30])
        self.assertEqual([row["id"] for row in self.listing("top7", company_id=2)["items"]], [other])
        self.assertEqual(self.listing("top7")["through_date"], "2026-09-29")

    def test_top50_ties_thresholds_and_pagination(self):
        ids = [self.add_product(1, self.day - timedelta(days=1)) for _ in range(52)]
        boundary = {count: self.add_product(count, self.day - timedelta(days=1))
                    for count in (30, 31, 70, 71, 130, 131)}
        self.seed_snapshots()
        top = self.listing("top7", page_size=100)
        self.assertEqual(top["total"], 50)
        self.assertEqual([row["id"] for row in top["items"][:6]],
                         [boundary[count] for count in (131, 130, 71, 70, 31, 30)])
        self.assertEqual([row["id"] for row in top["items"][6:]], ids[:44])
        self.assertEqual([row["rank"] for row in self.listing("top7", page=2, page_size=20)["items"]], list(range(21, 41)))
        self.assertEqual([row["id"] for row in self.listing("potential")["items"]], [boundary[70], boundary[31]])
        self.assertEqual([row["id"] for row in self.listing("hot")["items"]], [boundary[130], boundary[71]])
        self.assertEqual([row["id"] for row in self.listing("booming")["items"]], [boundary[131]])

    def test_empty_snapshot_is_saved_and_manual_refresh_rewrites_it(self):
        self.assertIsNone(self.listing("top7")["snapshot_date"])
        self.seed_snapshots()
        self.assertEqual(self.listing("top7")["items"], [])
        self.add_product(1, self.day - timedelta(days=1))
        self.assertEqual(self.listing("top7")["items"], [])
        with self.sessions() as db:
            rankings.refresh_company_snapshot(db, 1, due(self.day))
        self.assertEqual(self.listing("top7")["total"], 1)

    def test_snapshot_cleanup_keeps_only_recent_30_statistical_days(self):
        first = self.day
        with self.sessions() as db:
            for offset in range(32):
                rankings.create_daily_snapshot(db, 1, first + timedelta(days=offset))
        rankings.cleanup_expired_snapshots(self.sessions, due(first + timedelta(days=31)))
        with self.sessions() as db:
            dates = db.scalars(select(ProductLibraryDailySnapshot.snapshot_date).where(
                ProductLibraryDailySnapshot.company_id == 1).order_by(ProductLibraryDailySnapshot.snapshot_date)).all()
            self.assertEqual(len(dates), 30)
            self.assertEqual((dates[0], dates[-1]), (first + timedelta(days=2), first + timedelta(days=31)))
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductLibraryDailySnapshotItem)), 0)

    def test_category_is_not_capped(self):
        for _ in range(51):
            self.add_product(31, self.day - timedelta(days=1))
        self.seed_snapshots()
        self.assertEqual(self.listing("potential")["total"], 51)
        self.assertEqual(len(self.listing("potential", page_size=20)["items"]), 20)
        self.assertEqual(self.listing("potential", page=3, page_size=20)["items"][-1]["rank"], 51)

    def test_ranking_lists_include_material_creator_and_time(self):
        matched = self.add_product(31, self.day - timedelta(days=1))
        missing = self.add_product(1, self.day - timedelta(days=1))
        created_at = datetime(2026, 9, 20, 8, 30)
        with self.sessions() as db:
            db.add(MaterialAsset(company_id=1, url="https://example.com/a.jpg", name="A",
                                 sku=f"SKU-{matched}", claimed_by=1, created_at=created_at))
            db.commit()
        self.seed_snapshots()
        for category in ("top7", "potential"):
            item = self.listing(category)["items"][0]
            self.assertEqual(item["material_created_by_name"], "A")
            self.assertEqual(item["material_created_at"], main.timestamp_ms(created_at))
        absent = next(item for item in self.listing("top7")["items"] if item["id"] == missing)
        self.assertIsNone(absent["material_created_by_name"])
        self.assertIsNone(absent["material_created_at"])

    def test_manual_first_run_does_not_backfill(self):
        self.add_product(1, self.day - timedelta(days=1))
        later = self.day + timedelta(days=10)
        with self.sessions() as db:
            rankings.enqueue_ranking_task(db, 1, due(later))
        self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
        with self.sessions() as db:
            dates = db.scalars(select(ProductLibraryDailySnapshot.snapshot_date)).all()
            self.assertEqual(dates, [later])
        self.assertEqual(self.listing("potential")["total"], 0)

    def test_manual_refresh_replaces_only_current_company_and_rolls_back_on_failure(self):
        first = self.add_product(1, self.day - timedelta(days=1))
        other = self.add_product(1, self.day - timedelta(days=1), company_id=2)
        self.seed_snapshots()
        second = self.add_product(2, self.day - timedelta(days=1))
        with self.sessions() as db:
            self.assertEqual(rankings.refresh_company_snapshot(db, 1, due(self.day) + timedelta(hours=1)), self.day)
        self.assertEqual([row["id"] for row in self.listing("top7")["items"]], [second, first])
        self.assertEqual([row["id"] for row in self.listing("top7", company_id=2)["items"]], [other])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductLibraryDailySnapshot)), 2)

        third = self.add_product(3, self.day - timedelta(days=1))
        original = rankings.create_daily_snapshot

        def fail_after_build(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("temporary failure")

        with self.sessions() as db, patch.object(rankings, "create_daily_snapshot", side_effect=fail_after_build):
            with self.assertRaises(RuntimeError):
                rankings.refresh_company_snapshot(db, 1, due(self.day) + timedelta(hours=2))
        self.assertEqual([row["id"] for row in self.listing("top7")["items"]], [second, first])
        self.assertNotIn(third, [row["id"] for row in self.listing("top7")["items"]])

    def test_manual_refresh_rejects_existing_database_lock(self):
        class LockedSession:
            def __init__(self):
                self.rolled_back = False

            def scalar(self, _statement):
                raise OperationalError("SELECT", {}, Exception(3572, "NOWAIT lock conflict"))

            def rollback(self):
                self.rolled_back = True

        db = LockedSession()
        with self.assertRaises(rankings.SnapshotAlreadyRunning):
            rankings.create_daily_snapshot(db, 1, self.day, replace_existing=True, fail_if_running=True)
        self.assertTrue(db.rolled_back)

    def test_company_task_lock_blocks_duplicate_runs(self):
        with self.sessions() as db, rankings.company_run_lock(db, 1):
            with self.assertRaises(rankings.SnapshotAlreadyRunning):
                rankings.refresh_company_snapshot(db, 1, due(self.day))
        self.seed_snapshots()
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductLibraryDailySnapshot)), 2)

    def test_rankings_endpoint_requires_auth_and_company_scope(self):
        self.add_product(1, self.day - timedelta(days=1), company_id=2)
        self.seed_snapshots()

        def override_db():
            with self.sessions() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_db
        try:
            with self.sessions() as db:
                token_a = create_access_token(db.get(User, 1))
                token_b = create_access_token(db.get(User, 2))
            client = TestClient(main.app)
            self.assertEqual(client.get("/product-library/rankings", params={"category": "top7"}).status_code, 403)
            self.assertEqual(client.get("/product-library/rankings", params={"category": "unknown"},
                headers={"Authorization": f"Bearer {token_a}"}).status_code, 422)
            first = client.get("/product-library/rankings", params={"category": "top7"},
                headers={"Authorization": f"Bearer {token_a}"}).json()
            second = client.get("/product-library/rankings", params={"category": "top7"},
                headers={"Authorization": f"Bearer {token_b}"}).json()
            self.assertEqual(first["total"], 0)
            self.assertEqual(second["total"], 1)
            self.assertEqual(second["items"][0]["shop_name"], "Second Shop")
            self.assertEqual(client.post("/product-library/rankings/refresh").status_code, 403)
            busy = client.post("/product-library/rankings/refresh", headers={"Authorization": f"Bearer {token_a}"})
            self.assertEqual(busy.status_code, 202)
            self.assertEqual(busy.json()["task"]["status"], "queued")
            duplicate = TestClient(main.app).post("/product-library/rankings/refresh", headers={"Authorization": f"Bearer {token_a}"})
            self.assertEqual(duplicate.status_code, 202)
            self.assertTrue(duplicate.json()["existing"])
            self.assertEqual(duplicate.json()["task"]["task_id"], busy.json()["task"]["task_id"])
            with self.sessions() as db:
                task = db.get(ProductLibraryRankingTask, 1)
                task.status = "running"
                db.commit()
            running_duplicate = TestClient(main.app).post("/product-library/rankings/refresh", headers={"Authorization": f"Bearer {token_a}"})
            self.assertEqual(running_duplicate.status_code, 202)
            self.assertTrue(running_duplicate.json()["existing"])
            self.assertEqual(running_duplicate.json()["task"]["task_id"], busy.json()["task"]["task_id"])
            with self.sessions() as db:
                task = db.get(ProductLibraryRankingTask, 1)
                task.status = "queued"
                db.commit()
            status = client.get("/product-library/rankings/refresh/status", headers={"Authorization": f"Bearer {token_a}"})
            self.assertEqual(status.json()["task"]["task_id"], busy.json()["task"]["task_id"])
            self.assertEqual(client.get("/product-library/rankings/refresh/status").status_code, 403)
            other_status = client.get("/product-library/rankings/refresh/status", headers={"Authorization": f"Bearer {token_b}"})
            self.assertIsNone(other_status.json()["task"])
            other_task = client.post("/product-library/rankings/refresh", headers={"Authorization": f"Bearer {token_b}"})
            self.assertEqual(other_task.status_code, 202)
            self.assertNotEqual(other_task.json()["task"]["task_id"], busy.json()["task"]["task_id"])
            self.add_product(1, self.day - timedelta(days=1))
            self.assertEqual(self.listing("top7")["total"], 0)  # POST 返回时尚未计算
            # 固定日期由请求生成；测试中把任务日期设为固定的 2026-09-30。
            with self.sessions() as db:
                task = db.get(ProductLibraryRankingTask, 1)
                task.snapshot_date = self.day
                db.commit()
            self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
            updated = client.get("/product-library/rankings/refresh/status", headers={"Authorization": f"Bearer {token_a}"})
            self.assertEqual(updated.json()["task"]["status"], "succeeded")
            self.assertEqual(updated.json()["task"]["through_date"], "2026-09-29")
            self.assertEqual(self.listing("top7")["total"], 1)
            self.assertEqual(self.listing("top7", company_id=2)["total"], 1)
        finally:
            main.app.dependency_overrides.pop(get_db, None)

    def test_task_date_is_fixed_and_company_tasks_are_independent(self):
        first = self.add_product(1, self.day - timedelta(days=1))
        second = self.add_product(1, self.day - timedelta(days=1), company_id=2)
        before_midnight = datetime.combine(self.day, time(23, 59), HK)
        after_midnight = before_midnight + timedelta(minutes=2)
        with self.sessions() as db:
            a = rankings.enqueue_ranking_task(db, 1, before_midnight)
        with self.sessions() as db:
            same = rankings.enqueue_ranking_task(db, 1, after_midnight)
            b = rankings.enqueue_ranking_task(db, 2, after_midnight)
        self.assertEqual(a["task"]["task_id"], same["task"]["task_id"])
        self.assertEqual(same["task"]["snapshot_date"], self.day.isoformat())
        self.assertNotEqual(a["task"]["task_id"], b["task"]["task_id"])
        self.assertEqual(b["task"]["snapshot_date"], (self.day + timedelta(days=1)).isoformat())
        self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
        self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
        self.assertFalse(rankings.run_ranking_task_cycle(self.sessions))
        self.assertEqual(self.listing("top7")["items"][0]["id"], first)
        self.assertEqual(self.listing("top7", company_id=2)["items"][0]["id"], second)

    def test_failed_task_keeps_snapshot_and_retry_replaces_it(self):
        original = self.add_product(1, self.day - timedelta(days=1))
        with self.sessions() as db:
            rankings.create_daily_snapshot(db, 1, self.day)
            first = rankings.enqueue_ranking_task(db, 1, due(self.day))
        added = self.add_product(2, self.day - timedelta(days=1))
        with patch.object(rankings, "create_daily_snapshot", side_effect=RuntimeError("测试失败")):
            self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
        self.assertEqual(self.listing("top7")["items"][0]["id"], original)
        with self.sessions() as db:
            failed = db.get(ProductLibraryRankingTask, 1)
            self.assertEqual(failed.status, "failed")
            self.assertIn("测试失败", failed.error)
            retry = rankings.enqueue_ranking_task(db, 1, due(self.day))
        self.assertNotEqual(first["task"]["task_id"], retry["task"]["task_id"])
        self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
        self.assertEqual(self.listing("top7")["items"][0]["id"], added)

    def test_restart_recovers_running_task_without_automatic_snapshot(self):
        self.add_product(1, self.day - timedelta(days=1))
        self.assertFalse(rankings.run_ranking_task_cycle(self.sessions))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(ProductLibraryDailySnapshot.id))), 0)
            rankings.enqueue_ranking_task(db, 1, due(self.day))
            task = db.get(ProductLibraryRankingTask, 1)
            task.status = "running"
            db.commit()
        self.assertEqual(rankings.recover_interrupted_tasks(self.sessions), 1)
        self.assertTrue(rankings.run_ranking_task_cycle(self.sessions))
        self.assertEqual(self.listing("top7")["total"], 1)

    def test_idle_cleanup_removes_old_snapshots(self):
        old = self.day - timedelta(days=31)
        with self.sessions() as db:
            rankings.create_daily_snapshot(db, 1, old)
        rankings.cleanup_expired_snapshots(self.sessions, due(self.day))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(ProductLibraryDailySnapshot.id))), 0)
