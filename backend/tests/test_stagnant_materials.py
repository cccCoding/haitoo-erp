import asyncio
from datetime import datetime, timedelta
from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi import UploadFile
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import (
    Company, MaterialAsset, ProductLibraryOrder, ProductLibraryOrderProduct,
    ProductLibraryProduct, ProductLibrarySource, ProductTemplate, Role, User,
)
from app.security import create_access_token


class StagnantMaterialTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.cutoff = datetime(2026, 6, 1, 12, 0)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name="First"), Company(id=2, name="Second"),
                User(id=1, company_id=1, email="admin@example.com", name="Admin", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=2, company_id=1, email="member@example.com", name="Member", password_hash="x", role=Role.MEMBER),
                User(id=3, company_id=1, email="other@example.com", name="Other", password_hash="x", role=Role.MEMBER),
                User(id=4, company_id=2, email="foreign@example.com", name="Foreign", password_hash="x", role=Role.MEMBER),
                ProductTemplate(id=1, company_id=1, name="M06L"),
                ProductLibrarySource(id=1, company_id=1, platform="TikTok", site="MY", shop_name="Shop A"),
                ProductLibrarySource(id=2, company_id=1, platform="TikTok", site="MY", shop_name="Shop B"),
                ProductLibrarySource(id=3, company_id=2, platform="TikTok", site="MY", shop_name="Foreign Shop"),
            ])
            db.commit()

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def asset(self, db, sku, *, creator=2, when=None, company=1):
        asset = MaterialAsset(company_id=company, url=f"https://example.com/{sku or 'legacy'}.jpg",
                              name=sku or "legacy", sku=sku, template_id=1 if company == 1 else None,
                              claimed_by=creator, created_at=when or self.cutoff - timedelta(days=1))
        db.add(asset)
        db.flush()
        return asset.id

    def order(self, db, sku, *, source=1, company=1):
        product = ProductLibraryProduct(company_id=company, source_id=source,
            external_product_id=f"product-{source}-{sku}", sku=sku, title="", image_url="")
        db.add(product)
        db.flush()
        order = ProductLibraryOrder(company_id=company, source_id=source,
            order_number=f"order-{source}-{sku}", ordered_at=self.cutoff - timedelta(days=100))
        db.add(order)
        db.flush()
        db.add(ProductLibraryOrderProduct(order_id=order.id, product_id=product.id))

    def listing(self, user_id=1, *, page=1, page_size=20, creator_id=None):
        with self.sessions() as db, patch.object(main, "stagnant_material_cutoff", return_value=self.cutoff):
            return main.list_stagnant_materials(page=page, page_size=page_size, creator_id=creator_id,
                                                user=db.get(User, user_id), db=db)

    def test_older_than_90_days_and_historical_zero_orders(self):
        with self.sessions() as db:
            eligible = self.asset(db, "NO_IMPORT", when=self.cutoff - timedelta(seconds=1))
            self.asset(db, "AT_BOUNDARY", when=self.cutoff)
            self.asset(db, "TOO_NEW", when=self.cutoff + timedelta(seconds=1))
            self.asset(db, None)
            self.asset(db, "ORDERED_OTHER_SHOP")
            self.asset(db, "FOREIGN_ORDER_ONLY")
            self.order(db, "ORDERED_OTHER_SHOP", source=2)
            self.order(db, "FOREIGN_ORDER_ONLY", source=3, company=2)
            db.commit()

        result = self.listing()
        self.assertEqual([item["sku"] for item in result["items"]], ["FOREIGN_ORDER_ONLY", "NO_IMPORT"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][1], {
            "id": eligible, "source_type": "material", "template_id": 1, "title": "", "image_url": "https://example.com/NO_IMPORT.jpg", "sku": "NO_IMPORT",
            "template": "M06L", "created_by_id": 2, "created_by_name": "Member",
            "created_at": main.timestamp_ms(self.cutoff - timedelta(seconds=1)),
        })

    def test_creator_filter_member_visibility_order_and_pagination(self):
        with self.sessions() as db:
            oldest = self.asset(db, "OLDEST", creator=2, when=self.cutoff - timedelta(days=3))
            tied_first = self.asset(db, "TIED_FIRST", creator=3, when=self.cutoff - timedelta(days=2))
            tied_second = self.asset(db, "TIED_SECOND", creator=2, when=self.cutoff - timedelta(days=2))
            self.asset(db, "OTHER_COMPANY", creator=4, company=2)
            db.commit()

        self.assertEqual([item["id"] for item in self.listing(page=1, page_size=2)["items"]], [oldest, tied_first])
        self.assertEqual([item["id"] for item in self.listing(page=2, page_size=2)["items"]], [tied_second])
        self.assertEqual([item["id"] for item in self.listing(page=9, page_size=2)["items"]], [tied_second])
        self.assertEqual(self.listing(page=9, page_size=2)["page"], 2)
        self.assertEqual([item["id"] for item in self.listing(creator_id=3)["items"]], [tied_first])
        self.assertEqual([item["id"] for item in self.listing(user_id=2, creator_id=3)["items"]], [oldest, tied_second])
        self.assertEqual([item["sku"] for item in self.listing(user_id=4)["items"]], ["OTHER_COMPANY"])

    def test_imported_order_removes_material_without_statistics_task(self):
        with self.sessions() as db:
            self.asset(db, "M06LZERO123")
            db.commit()
        self.assertEqual(self.listing()["total"], 1)

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["店铺名称", "站点", "平台", "订单编号", "下单时间", "标题", "平台SKU", "产品图片链接", "产品ID"])
        sheet.append(["Shop A", "马来西亚", "TikTok", "imported-1", "2026-01-01 12:00:00",
                      "Product", "M06LZERO123-M", "https://example.com/product.jpg", "external-1"])
        output = BytesIO()
        workbook.save(output)
        with self.sessions() as db:
            result = asyncio.run(main.import_product_library(
                file=UploadFile(filename="orders.xlsx", file=BytesIO(output.getvalue())),
                user=db.get(User, 1), db=db))
        self.assertEqual(result["created_orders"], 1)
        self.assertEqual(self.listing()["total"], 0)

    def test_http_auth_and_query_validation(self):
        with self.sessions() as db:
            self.asset(db, "OWNER_A", creator=2)
            self.asset(db, "OWNER_B", creator=3)
            db.commit()
            admin_token = create_access_token(db.get(User, 1))
            member_token = create_access_token(db.get(User, 2))

        def override_db():
            with self.sessions() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_db
        with patch.object(main, "stagnant_material_cutoff", return_value=self.cutoff):
            client = TestClient(main.app)
            self.assertEqual(client.get("/product-library/stagnant").status_code, 403)
            admin = client.get("/product-library/stagnant", params={"creator_id": 3},
                               headers={"Authorization": f"Bearer {admin_token}"})
            self.assertEqual((admin.status_code, admin.json()["items"][0]["sku"]), (200, "OWNER_B"))
            member = client.get("/product-library/stagnant", params={"creator_id": 3},
                                headers={"Authorization": f"Bearer {member_token}"})
            self.assertEqual((member.status_code, member.json()["items"][0]["sku"]), (200, "OWNER_A"))
            invalid = client.get("/product-library/stagnant", params={"page_size": 101},
                                 headers={"Authorization": f"Bearer {admin_token}"})
            self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()
