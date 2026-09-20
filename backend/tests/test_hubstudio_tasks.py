import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import Company, HubAgent, HubUploadTask, ProductDraft, ProductTemplate, Role, Shop, TiktokCategoryCatalog, User, UserShop
from app.schemas import HubUploadTaskCreate, HubstudioAccountUpdate
from app.tiktok_export import TEMPLATE_PATH, listing_options


class HubstudioTaskTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            db.add_all([
                Company(id=1, name="Company"),
                User(id=1, company_id=1, email="admin@example.com", name="Admin", password_hash="x", role=Role.COMPANY_ADMIN),
                HubAgent(id=1, company_id=1, user_id=1, name="Mac", platform="macos", token_hash="a" * 64),
                Shop(id=1, company_id=1, name="Local Shop", shop_type="local", hubstudio_container_code="env-1", hub_agent_id=1),
                UserShop(user_id=1, shop_id=1),
                ProductTemplate(id=1, company_id=1, name="Y1", product_description="Description", size_chart_url="https://x/chart.jpg", package_weight=.2, package_length=20, package_width=10, package_height=2),
                TiktokCategoryCatalog(id=1, company_id=1, name="Catalog", source_filename=TEMPLATE_PATH.name, template_blob=TEMPLATE_PATH.read_bytes(), parsed_options=listing_options()),
                ProductDraft(id=1, company_id=1, template_id=1, title="A valid title for automated TikTok listing", product_description="Description", image_urls=["https://x/a.jpg"], sku_items=[{"image_url":"https://x/a.jpg", "sku":"Y1AA000001"}], created_by=1, updated_by=1),
            ])
            db.commit()

    def tearDown(self): self.engine.dispose()

    def test_creates_immutable_export_snapshot_only_when_hub_configured(self):
        with self.Session() as db:
            admin = db.get(User, 1)
            main.update_hubstudio_account(HubstudioAccountUpdate(app_id="id", app_secret="secret", group_code="group"), admin, db)
            payload = HubUploadTaskCreate(shop_id=1, draft_ids=[1], category_catalog_id=1, category="女士上装/女士衬衫", default_price=10, default_quantity=3, attributes={"product_property/100198":"花朵"})
            result = main.create_hubstudio_upload_task(payload, admin, db)
            task = db.get(HubUploadTask, result["id"])
            self.assertEqual(task.status, "queued")
            self.assertTrue(task.export_blob.startswith(b"PK"))
            self.assertNotIn("export_blob", result)


if __name__ == "__main__": unittest.main()
