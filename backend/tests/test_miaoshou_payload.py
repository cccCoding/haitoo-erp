import unittest

from app.main import build_common_collect_box_payload
from app.models import ProductDraft, ProductTemplate


class MiaoshouPayloadTests(unittest.TestCase):
    def draft(self):
        return ProductDraft(
            title="A unique product title for publishing",
            image_urls=["https://img.example/main.jpg", "https://img.example/carousel.jpg"],
            sku_items=[
                {"image_url": "https://img.example/one.jpg", "sku": "M05LRKJLCUYC"},
                {"image_url": "https://img.example/two.jpg", "sku": "M05LRABC123"},
                {"image_url": "https://img.example/one.jpg", "sku": "DUPLICATE"},
            ],
        )

    def test_numbered_colors_keep_original_images_and_seller_skus(self):
        draft = self.draft()
        template = ProductTemplate(sku_specifications={"size": {"options": ["S", "M"]}})
        payload = build_common_collect_box_payload(draft, template)
        self.assertEqual(payload["colorMap"], {
            "Color 1": {"name": "Color 1", "imgUrls": ["https://img.example/one.jpg"], "imgUrl": "https://img.example/one.jpg"},
            "Color 2": {"name": "Color 2", "imgUrls": ["https://img.example/two.jpg"], "imgUrl": "https://img.example/two.jpg"},
        })
        self.assertEqual(list(payload["skuMap"]), ["Color 1;S", "Color 1;M", "Color 2;S", "Color 2;M"])
        self.assertEqual([item["itemNum"] for item in payload["skuMap"].values()], ["M05LRKJLCUYC-S", "M05LRKJLCUYC-M", "M05LRABC123-S", "M05LRABC123-M"])
        self.assertEqual(payload["itemNum"], "M05LRKJLCUYC-S")
        self.assertEqual(payload["imgUrls"], draft.image_urls)
        self.assertEqual([item["sku"] for item in draft.sku_items], ["M05LRKJLCUYC", "M05LRABC123", "DUPLICATE"])
        draft.image_urls.reverse()
        reordered = build_common_collect_box_payload(draft, template)
        self.assertEqual(reordered["colorMap"], payload["colorMap"])
        self.assertEqual(reordered["skuMap"], payload["skuMap"])

    def test_default_size_keeps_base_sku_and_each_product_restarts_colors(self):
        template = ProductTemplate(sku_specifications={})
        draft = self.draft()
        for sku_item in draft.sku_items[:2]:
            with self.subTest(sku=sku_item["sku"]):
                draft.sku_items = [sku_item]
                payload = build_common_collect_box_payload(draft, template)
                self.assertEqual(list(payload["colorMap"]), ["Color 1"])
                self.assertEqual(list(payload["skuMap"]), ["Color 1;Default"])
                self.assertEqual(payload["skuMap"]["Color 1;Default"]["itemNum"], sku_item["sku"])


if __name__ == "__main__":
    unittest.main()
