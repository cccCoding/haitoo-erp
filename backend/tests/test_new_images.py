from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import Company, MaterialAsset, ProductTemplate, Role, User
from app.security import create_access_token


class NewImagesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.end = datetime(2026, 9, 30, 12, 0)
        self.start = self.end - timedelta(days=5)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name="First"), Company(id=2, name="Second"),
                User(id=1, company_id=1, email="admin@example.com", name="Admin", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=2, company_id=1, email="member@example.com", name="Member", password_hash="x", role=Role.MEMBER),
                User(id=3, company_id=1, email="other@example.com", name="Other", password_hash="x", role=Role.MEMBER),
                User(id=4, company_id=2, email="foreign@example.com", name="Foreign", password_hash="x", role=Role.MEMBER),
                ProductTemplate(id=1, company_id=1, name="M06L"),
            ])
            db.commit()

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def asset(self, db, sku, *, creator=2, when=None, status="unused", company=1):
        item = MaterialAsset(company_id=company, url=f"https://example.com/{sku or 'legacy'}.jpg",
                             name=sku or "legacy", sku=sku, template_id=1 if company == 1 else None,
                             claimed_by=creator, created_at=when or self.end, usage_status=status)
        db.add(item)
        db.flush()
        return item.id

    def listing(self, user_id=1, *, page=1, page_size=20, creator_id=None, usage_status="all"):
        with self.sessions() as db, patch.object(main, "new_images_window", return_value=(self.start, self.end)):
            return main.list_new_images(page=page, page_size=page_size, creator_id=creator_id,
                                        usage_status=usage_status, user=db.get(User, user_id), db=db)

    def test_five_day_boundary_status_filter_and_status_change(self):
        with self.sessions() as db:
            boundary = self.asset(db, "BOUNDARY", when=self.start)
            self.asset(db, "TOO_OLD", when=self.start - timedelta(microseconds=1))
            used = self.asset(db, "USED", when=self.end, status="used")
            self.asset(db, "FUTURE", when=self.end + timedelta(microseconds=1))
            legacy = self.asset(db, None, when=self.end - timedelta(days=1))
            self.asset(db, "OTHER_COMPANY", creator=4, company=2)
            db.commit()

        result = self.listing()
        self.assertEqual([item["sku"] for item in result["items"]], ["USED", None, "BOUNDARY"])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["items"][0], {
            "id": used, "image_url": "https://example.com/USED.jpg", "sku": "USED",
            "template": "M06L", "created_by_id": 2, "created_by_name": "Member",
            "created_at": main.timestamp_ms(self.end), "usage_status": "used",
        })
        self.assertEqual([item["id"] for item in self.listing(usage_status="unused")["items"]], [legacy, boundary])
        with self.sessions() as db:
            db.get(MaterialAsset, boundary).usage_status = "used"
            db.commit()
        self.assertEqual([item["id"] for item in self.listing(usage_status="used")["items"]], [used, boundary])

    def test_creator_permissions_order_and_pagination(self):
        with self.sessions() as db:
            first = self.asset(db, "FIRST", creator=2, when=self.end - timedelta(days=1))
            tied_first = self.asset(db, "TIED_FIRST", creator=3, when=self.end)
            tied_second = self.asset(db, "TIED_SECOND", creator=2, when=self.end)
            self.asset(db, "FOREIGN", creator=4, company=2)
            db.commit()

        self.assertEqual([item["id"] for item in self.listing(page_size=2)["items"]], [tied_second, tied_first])
        self.assertEqual([item["id"] for item in self.listing(page=2, page_size=2)["items"]], [first])
        self.assertEqual(self.listing(page=9, page_size=2)["page"], 2)
        self.assertEqual([item["id"] for item in self.listing(creator_id=3)["items"]], [tied_first])
        self.assertEqual([item["id"] for item in self.listing(user_id=2, creator_id=3)["items"]], [tied_second, first])
        self.assertEqual([item["sku"] for item in self.listing(user_id=4)["items"]], ["FOREIGN"])

    def test_http_auth_and_usage_validation(self):
        with self.sessions() as db:
            self.asset(db, "NEW")
            db.commit()
            token = create_access_token(db.get(User, 1))

        def override_db():
            with self.sessions() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_db
        with patch.object(main, "new_images_window", return_value=(self.start, self.end)):
            client = TestClient(main.app)
            self.assertEqual(client.get("/product-library/new-images").status_code, 403)
            result = client.get("/product-library/new-images", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual((result.status_code, result.json()["total"]), (200, 1))
            invalid = client.get("/product-library/new-images", params={"usage_status": "invalid"},
                                 headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()
