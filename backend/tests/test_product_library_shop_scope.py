from datetime import date, datetime
from unittest import TestCase

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, product_library_rankings
from app.database import Base, get_db
from app.models import (Company, MaterialAsset, OperatorGroup, ProductLibraryDailySnapshot, ProductLibraryDailySnapshotItem,
    ProductLibraryOrder, ProductLibraryOrderProduct, ProductLibraryProduct, ProductLibrarySource, Role, User)
from app.security import create_access_token


class ProductLibraryShopScopeTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name="First"), Company(id=2, name="Second"),
                OperatorGroup(id=1, company_id=1, name="Group A", leader_user_id=2),
                OperatorGroup(id=2, company_id=1, name="Group B", leader_user_id=4),
                User(id=1, company_id=1, email="admin@example.com", name="Admin", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=2, company_id=1, email="leader@example.com", name="Leader", password_hash="x", role=Role.TEAM_LEADER, group_id=1),
                User(id=3, company_id=1, email="member@example.com", name="Member", password_hash="x", role=Role.MEMBER, group_id=1),
                User(id=4, company_id=1, email="other-leader@example.com", name="Other Leader", password_hash="x", role=Role.TEAM_LEADER, group_id=2),
                User(id=5, company_id=1, email="ungrouped@example.com", name="Ungrouped", password_hash="x", role=Role.MEMBER),
                User(id=6, company_id=2, email="outsider@example.com", name="Outsider", password_hash="x", role=Role.MEMBER),
            ])
            for source_id, assigned_user_id in ((1, 2), (2, 3), (3, 4), (4, 5), (5, None)):
                db.add(ProductLibrarySource(id=source_id, company_id=1, platform="TikTok", site="MY",
                    shop_name=f"Shop {source_id}", assigned_user_id=assigned_user_id))
            db.add(ProductLibrarySource(id=6, company_id=2, platform="TikTok", site="MY", shop_name="Outside", assigned_user_id=6))
            db.commit()
        self.snapshot_date = date(2026, 10, 3)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def add_product(self, product_id: int, source_id: int, count: int):
        company_id = 2 if source_id == 6 else 1
        with self.sessions() as db:
            db.add(ProductLibraryProduct(id=product_id, company_id=company_id, source_id=source_id,
                external_product_id=f"P-{product_id}", sku=f"SKU-{product_id}", title="Product", image_url=""))
            for index in range(count):
                order_id = product_id * 100 + index
                db.add(ProductLibraryOrder(id=order_id, company_id=company_id, source_id=source_id,
                    order_number=f"O-{order_id}", ordered_at=datetime(2026, 10, 2, 8)))
                db.add(ProductLibraryOrderProduct(order_id=order_id, product_id=product_id))
            db.commit()

    def snapshot(self):
        with self.sessions() as db:
            product_library_rankings.create_daily_snapshot(db, 1, self.snapshot_date)
            product_library_rankings.create_daily_snapshot(db, 2, self.snapshot_date)

    def ranking(self, user_id: int, category="top7", group_id=None, member_id=None):
        with self.sessions() as db:
            return main.list_product_library_rankings(category=category, page=1, page_size=50,
                group_id=group_id, member_id=member_id, user=db.get(User, user_id), db=db)

    def test_top50_reorders_within_selected_members_and_windows(self):
        for product_id, source_id, count in ((1, 1, 2), (2, 2, 1), (3, 3, 4),
                                             (4, 4, 3), (5, 5, 5), (6, 6, 8)):
            self.add_product(product_id, source_id, count)
        self.snapshot()
        for category in ("top7", "top15", "top30"):
            def ids(user_id, **scope):
                result = self.ranking(user_id, category, **scope)
                self.assertEqual([item["rank"] for item in result["items"]], list(range(1, result["total"] + 1)))
                return [item["id"] for item in result["items"]]
            self.assertEqual(ids(1), [5, 3, 4, 1, 2])
            self.assertEqual(ids(1, group_id=1), [1, 2])
            self.assertEqual(ids(1, group_id=1, member_id=3), [2])
            self.assertEqual(ids(2), [1, 2])
            self.assertEqual(ids(2, member_id=2), [1])
            self.assertEqual(ids(2, member_id=3), [2])
            self.assertEqual(ids(3), [2])
        with self.assertRaises(HTTPException):
            self.ranking(2, group_id=2)
        with self.assertRaises(HTTPException):
            self.ranking(3, member_id=2)
        with self.assertRaises(HTTPException):
            self.ranking(1, member_id=3)
        with self.assertRaises(HTTPException):
            self.ranking(1, group_id=1, member_id=4)

    def test_current_group_and_assignment_drive_visibility(self):
        self.add_product(1, 1, 1)
        self.add_product(2, 2, 1)
        self.snapshot()
        with self.sessions() as db:
            db.get(User, 3).group_id = 2
            db.commit()
        self.assertEqual([item["id"] for item in self.ranking(2)["items"]], [1])
        self.assertEqual([item["id"] for item in self.ranking(4)["items"]], [2])
        with self.sessions() as db:
            main.delete_operator_group(1, user=db.get(User, 1), db=db)
        self.assertEqual([item["id"] for item in self.ranking(2)["items"]], [1])
        self.assertEqual([item["id"] for item in self.ranking(3)["items"]], [2])

    def test_classified_rankings_follow_assigned_shops(self):
        self.add_product(1, 2, 31)
        self.add_product(2, 3, 31)
        self.add_product(3, 5, 31)
        self.snapshot()
        self.assertEqual([item["id"] for item in self.ranking(2, "potential")["items"]], [1])
        self.assertEqual([item["id"] for item in self.ranking(3, "potential")["items"]], [1])
        self.assertEqual([item["id"] for item in self.ranking(1, "potential")["items"]], [1, 2, 3])

    def test_assignment_endpoints_and_product_access(self):
        self.add_product(1, 1, 1)
        self.add_product(2, 5, 1)
        self.snapshot()
        def override_db():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[get_db] = override_db
        with self.sessions() as db:
            headers = {user_id: {"Authorization": f"Bearer {create_access_token(db.get(User, user_id))}"}
                       for user_id in (1, 2, 3, 6)}
        client = TestClient(main.app)
        self.assertEqual(client.get("/product-library/shops", headers=headers[2]).status_code, 403)
        self.assertEqual(client.get("/product-library/shops", headers=headers[1]).json()[0]["assigned_user_id"], 2)
        self.assertEqual(len(client.get("/product-library/ranking-scope-options", headers=headers[1]).json()["groups"]), 2)
        self.assertEqual([member["id"] for member in client.get("/product-library/ranking-scope-options",
            headers=headers[2]).json()["members"]], [2, 3])
        url = "/product-library/shops/5/assignment"
        for target in (1, 6):
            self.assertEqual(client.put(url, json={"assigned_user_id": target}, headers=headers[1]).status_code, 400)
        self.assertEqual(client.put("/product-library/shops/6/assignment", json={"assigned_user_id": 3},
            headers=headers[1]).status_code, 404)
        self.assertEqual(client.get("/product-library", headers=headers[3]).json()["total"], 0)
        self.assertEqual(client.get("/product-library/2/orders", headers=headers[3]).status_code, 404)
        self.assertEqual(client.put(url, json={"assigned_user_id": 3}, headers=headers[1]).status_code, 200)
        self.assertEqual(client.get("/product-library", headers=headers[3]).json()["total"], 1)
        self.assertEqual(client.get("/product-library/rankings", params={"category": "top7"},
            headers=headers[3]).json()["items"][0]["id"], 2)
        self.assertEqual(client.get("/product-library/rankings", params={"category": "top7"},
            headers=headers[2]).json()["total"], 2)
        self.assertEqual(client.get("/product-library/2/orders", headers=headers[3]).status_code, 200)
        self.assertEqual(client.put(url, json={"assigned_user_id": None}, headers=headers[1]).status_code, 200)
        self.assertEqual(client.get("/product-library", headers=headers[3]).json()["total"], 0)
        self.assertEqual(client.get("/product-library/filters", headers=headers[3]).json()["shops"], [{"id": 2, "label": "TikTok-MY-Shop 2-Member"}])
        self.assertIn({"id": 5, "label": "TikTok-MY-Shop 5-未分配"},
            client.get("/product-library/filters", headers=headers[1]).json()["shops"])
        self.assertEqual(client.get("/product-library/rankings", params={"category": "top7"},
            headers=headers[3]).json()["total"], 0)
        self.assertEqual(client.get("/product-library/filters", headers=headers[3]).json()["shop_names"], ["Shop 2"])

    def test_old_snapshot_rebuilds_before_filtered_top50(self):
        for index in range(50):
            self.add_product(index + 1, 3, 2)
        self.add_product(51, 2, 1)
        self.snapshot()
        with self.sessions() as db:
            snapshot = db.scalar(select(ProductLibraryDailySnapshot).where(ProductLibraryDailySnapshot.company_id == 1))
            snapshot.is_complete = False
            db.execute(delete(ProductLibraryDailySnapshotItem).where(
                ProductLibraryDailySnapshotItem.snapshot_id == snapshot.id,
                ProductLibraryDailySnapshotItem.product_id == 51))
            db.commit()
        result = self.ranking(2, member_id=3)
        self.assertEqual([item["id"] for item in result["items"]], [51])
        with self.sessions() as db:
            snapshot = db.scalar(select(ProductLibraryDailySnapshot).where(ProductLibraryDailySnapshot.company_id == 1))
            self.assertTrue(snapshot.is_complete)

    def test_stagnant_and_new_images_include_current_group_creators(self):
        with self.sessions() as db:
            for asset_id, creator_id in ((1, 2), (2, 3), (3, 4)):
                db.add(MaterialAsset(id=asset_id, company_id=1, url=f"https://example.com/{asset_id}.jpg",
                    name="Asset", sku=f"ASSET-{asset_id}", claimed_by=creator_id,
                    created_at=datetime(2026, 1, 1)))
                db.add(MaterialAsset(id=asset_id + 3, company_id=1,
                    url=f"https://example.com/recent-{asset_id}.jpg", name="Recent",
                    sku=f"RECENT-{asset_id}", claimed_by=creator_id, created_at=datetime.utcnow()))
            db.commit()
            leader = db.get(User, 2)
            self.assertEqual(main.list_stagnant_materials(page=1, page_size=20, creator_id=None,
                user=leader, db=db)["total"], 2)
            self.assertEqual(main.list_new_images(page=1, page_size=20, creator_id=None,
                usage_status="all", user=leader, db=db)["total"], 2)
            db.get(User, 3).group_id = 2
            db.commit()
            self.assertEqual(main.list_stagnant_materials(page=1, page_size=20, creator_id=None,
                user=leader, db=db)["total"], 1)
            self.assertEqual(main.list_new_images(page=1, page_size=20, creator_id=None,
                usage_status="all", user=leader, db=db)["total"], 1)
