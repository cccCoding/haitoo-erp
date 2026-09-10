import asyncio
from io import BytesIO
import unittest

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import Role, TiktokCategoryCatalog, User
from app.schemas import TiktokCategoryCatalogUpdate
from app.tiktok_export import TEMPLATE_PATH


class TiktokCategoryCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                User(id=1, company_id=1, email="admin1@example.com", name="Admin 1", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=2, company_id=2, email="admin2@example.com", name="Admin 2", password_hash="x", role=Role.COMPANY_ADMIN),
            ])
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def create_catalog(self, db):
        upload = UploadFile(filename="shop-template.xlsx", file=BytesIO(TEMPLATE_PATH.read_bytes()))
        return asyncio.run(main.create_tiktok_category_catalog("穆斯林服装", upload, user=db.get(User, 1), db=db))

    def test_upload_parses_named_catalog_and_attribute_input_modes(self) -> None:
        with self.session_factory() as db:
            result = self.create_catalog(db)
            self.assertEqual(result["name"], "穆斯林服装")
            self.assertEqual(result["template_version"], "V5.0.2")
            self.assertEqual(result["category_count"], 47)
            options = result["options"]
            robe_fields = options["attributes_by_category"]["Women's Islamic Clothing/Robes"]
            self.assertEqual(next(item for item in robe_fields if item["label"] == "Season")["input_mode"], "select")
            self.assertEqual(next(item for item in robe_fields if item["label"] == "Pattern")["input_mode"], "select_or_text")
            self.assertEqual(next(item for item in robe_fields if item["label"] == "Malaysia Product Safety & Quality Certification")["input_mode"], "text")
            self.assertEqual(db.get(TiktokCategoryCatalog, result["id"]).template_blob, TEMPLATE_PATH.read_bytes())

    def test_admin_can_change_input_mode_and_other_company_cannot_read(self) -> None:
        with self.session_factory() as db:
            result = self.create_catalog(db)
            catalog_id = result["id"]
            fields = result["options"]["attributes_by_category"]["Women's Islamic Clothing/Robes"]
            pattern = next(item for item in fields if item["label"] == "Pattern")
            updated = main.update_tiktok_category_catalog(
                catalog_id,
                TiktokCategoryCatalogUpdate(attribute_input_modes=[{
                    "category": "Women's Islamic Clothing/Robes", "field": pattern["field"], "input_mode": "select",
                }]),
                user=db.get(User, 1), db=db,
            )
            updated_pattern = next(item for item in updated["options"]["attributes_by_category"]["Women's Islamic Clothing/Robes"] if item["field"] == pattern["field"])
            self.assertEqual(updated_pattern["input_mode"], "select")
            with self.assertRaisesRegex(HTTPException, "不存在"):
                main.get_tiktok_export_options(catalog_id, user=db.get(User, 2), db=db)

    def test_invalid_workbook_is_rejected_without_creating_catalog(self) -> None:
        with self.session_factory() as db:
            upload = UploadFile(filename="broken.xlsx", file=BytesIO(b"not an xlsx"))
            with self.assertRaisesRegex(HTTPException, "解析失败"):
                asyncio.run(main.create_tiktok_category_catalog("错误模板", upload, user=db.get(User, 1), db=db))
            self.assertEqual(db.query(TiktokCategoryCatalog).count(), 0)


if __name__ == "__main__":
    unittest.main()
