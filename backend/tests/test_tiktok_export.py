from io import BytesIO
import unittest

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.models import MaterialAsset, ProductTemplate, Role, User
from app.schemas import TiktokBatchExportInput
from app.database import Base
from app.tiktok_export import TEMPLATE_PATH, listing_options


class TiktokExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                ProductTemplate(
                    id=1, company_id=1, name="Y1", product_description="Shared product description",
                    size_chart_url="https://img.example/size-chart.jpg", package_weight=0.28,
                    package_length=30, package_width=16, package_height=2,
                    sku_specifications={"size": {"name": "尺码", "options": ["S", "M"]}},
                ),
                User(id=1, company_id=1, email="operator@example.com", name="Operator", user_code="AA", password_hash="x", role=Role.MEMBER),
                MaterialAsset(id=1, company_id=1, template_id=1, url="https://img.example/one.jpg", name="One", sku="Y1AA000001", claimed_by=1),
                MaterialAsset(id=2, company_id=1, template_id=1, url="https://img.example/two.jpg", name="Two", sku="Y1AA000002", claimed_by=1),
                MaterialAsset(id=3, company_id=1, template_id=1, url="https://img.example/three.jpg", name="Three", sku="Y1AA000003", claimed_by=1),
            ])
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def payload(self) -> TiktokBatchExportInput:
        return TiktokBatchExportInput(
            template_id=1,
            category="Women's Islamic Clothing/Robes",
            product_description="Shared product description",
            default_price=10,
            cod="N",
            attributes={"product_property/100198": "Floral"},
            products=[
                {"asset_ids": [1, 2], "title": "First unique TikTok product title", "price_override": 12.5},
                {"asset_ids": [3], "title": "Second unique TikTok product title"},
            ],
        )

    def test_options_are_read_from_bundled_template(self) -> None:
        options = listing_options()
        self.assertEqual(options["template_version"], "V5.0.2")
        self.assertEqual(len(options["categories"]), 47)
        robe_fields = {item["field"]: item for item in options["attributes_by_category"]["Women's Islamic Clothing/Robes"]}
        self.assertIn("product_property/100198", robe_fields)
        self.assertTrue(robe_fields["product_property/100198"]["allow_custom"])

    def test_export_preserves_template_and_expands_images_by_sizes(self) -> None:
        source = load_workbook(TEMPLATE_PATH, data_only=False)
        with self.session_factory() as db:
            response = main.export_material_assets_to_tiktok(self.payload(), user=db.get(User, 1), db=db)
        exported = load_workbook(BytesIO(response.body), data_only=False)
        self.assertEqual(exported.sheetnames, source.sheetnames)
        self.assertEqual([sheet.sheet_state for sheet in exported], [sheet.sheet_state for sheet in source])
        self.assertEqual(exported["TemplateConfig"]["A2"].value, source["TemplateConfig"]["A2"].value)
        self.assertEqual(len(exported["Template"].data_validations.dataValidation), len(source["Template"].data_validations.dataValidation))
        self.assertEqual(len(exported["Template"].conditional_formatting), len(source["Template"].conditional_formatting))

        sheet = exported["Template"]
        self.assertEqual([sheet.cell(row, 26).value for row in range(7, 13)], [
            "Y1AA000001-S", "Y1AA000001-M", "Y1AA000002-S", "Y1AA000002-M", "Y1AA000003-S", "Y1AA000003-M",
        ])
        self.assertEqual([sheet.cell(row, 5).value for row in range(7, 13)], [
            "https://img.example/one.jpg", "https://img.example/one.jpg", "https://img.example/one.jpg", "https://img.example/one.jpg",
            "https://img.example/three.jpg", "https://img.example/three.jpg",
        ])
        self.assertEqual([sheet.cell(row, 24).value for row in range(7, 13)], [12.5, 12.5, 12.5, 12.5, 10, 10])
        self.assertTrue(all(sheet.cell(row, 2).value is None for row in range(7, 13)))
        self.assertTrue(all(sheet.cell(row, 25).value == 999 for row in range(7, 13)))
        self.assertTrue(all(sheet.cell(row, 19).value == 280 for row in range(7, 13)))
        self.assertTrue(all(sheet.cell(row, 29).value == "Floral" for row in range(7, 13)))
        self.assertIsNone(sheet["A13"].value)

    def test_export_rejects_duplicate_asset_across_groups(self) -> None:
        payload = self.payload()
        payload.products[1].asset_ids = [2, 3]
        with self.session_factory() as db, self.assertRaisesRegex(Exception, "不能出现在多个商品组"):
            main.export_material_assets_to_tiktok(payload, user=db.get(User, 1), db=db)


if __name__ == "__main__":
    unittest.main()
