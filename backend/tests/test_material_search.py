"""素材库 SKU 批量查询、分页、组合筛选和权限回归。"""
from datetime import datetime
import unittest

from app import main
from app.models import MaterialAsset, MaterialStyle, ProductTemplate
from tests.test_supply_catalog import SupplyFixture


class MaterialSearchTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app.include_router(main.app.router)

    def search(self, uid=1, **params):
        response = self.request("GET", "/material-assets", uid=uid, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_multiline_skus_trim_deduplicate_and_paginate_exact_matches(self):
        query = " SOURCE001 \r\n\r\nSOURCE003\nSOURCE001\nMISSING\nSOURCE00 "
        first = self.search(sku_query=query, page_size=1)
        self.assertEqual(first["total"], 2)
        self.assertEqual([row["sku"] for row in first["items"]], ["SOURCE003"])
        second = self.search(sku_query=query, page_size=1, page=2)
        self.assertEqual(second["page"], 2)
        self.assertEqual(second["total"], 2)
        self.assertEqual([row["sku"] for row in second["items"]], ["SOURCE001"])
        self.assertEqual(self.search(sku_query="MISSING\nSOURCE00")["total"], 0)

    def test_empty_queries_leave_existing_filters_active_and_validate_length(self):
        for query in ("", " \r\n\t\n "):
            with self.subTest(query=query):
                self.assertEqual(self.search(sku_query=query)["total"], 20)
                self.assertEqual(self.search(sku_query=query, template_id=999)["total"], 0)
        response = self.request("GET", "/material-assets", params={"sku_query": "A" * 10001})
        self.assertEqual(response.status_code, 422)

    def test_sku_query_keeps_company_and_creator_permissions(self):
        with self.sessions() as db:
            db.get(MaterialAsset, 20).claimed_by = 3
            db.commit()
        query = "SOURCE001\nSOURCE020\nFOREIGN"
        self.assertEqual(self.search(sku_query=query)["total"], 2)
        self.assertEqual([row["id"] for row in self.search(uid=2, sku_query=query, creator_id=3)["items"]], [1])
        self.assertEqual([row["id"] for row in self.search(uid=3, sku_query=query)["items"]], [20])
        self.assertEqual([row["id"] for row in self.search(sku_query=query, creator_id=3)["items"]], [20])
        self.assertEqual([row["id"] for row in self.search(uid=5, sku_query=query)["items"]], [99])

    def test_sku_query_combines_with_material_filters(self):
        with self.sessions() as db:
            db.add(ProductTemplate(id=3, company_id=1, name="Y2"))
            style = MaterialStyle(company_id=1, template_id=1, source_white_image_id=1, created_by=2, name="正面")
            db.add(style)
            db.flush()
            for identity in range(1, 8):
                asset = db.get(MaterialAsset, identity)
                asset.source_type = "local_upload"
                asset.style_id = style.id
                asset.created_at = datetime(2026, 10, 1, 12)
            db.get(MaterialAsset, 2).usage_status = "used"
            db.get(MaterialAsset, 3).source_type = "imported"
            db.get(MaterialAsset, 4).claimed_by = 3
            db.get(MaterialAsset, 5).template_id = 3
            db.get(MaterialAsset, 6).created_at = datetime(2026, 9, 1)
            db.get(MaterialAsset, 7).style_id = None
            db.commit()
            style_id = style.id
        filters = dict(sku_query="\n".join(f"SOURCE{i:03d}" for i in range(1, 8)),
            template_id=1, style_id=style_id, creator_id=2, source_type="local_upload",
            created_from="2026-10-01T00:00:00+08:00", created_to="2026-10-02T00:00:00+08:00")
        for extra, expected in (({}, [1]), ({"usage_status": "used"}, [2]),
                ({"usage_status": "all"}, [2, 1]), ({"source_type": "imported"}, [3]),
                ({"creator_id": 3}, [4]), ({"template_id": 3}, [5]), ({"style_id": 0}, [7])):
            with self.subTest(extra=extra):
                result = self.search(**(filters | extra))
                self.assertEqual([row["id"] for row in result["items"]], expected)
                self.assertEqual(result["total"], len(expected))
