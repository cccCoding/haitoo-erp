"""浏览器回归测试：HAITOO_BROWSER_TESTS=1，可用 HAITOO_BROWSER_CHANNEL 指定浏览器。"""
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse

from playwright.async_api import async_playwright


@unittest.skipUnless(os.environ.get("HAITOO_BROWSER_TESTS") == "1", "需启用浏览器回归测试")
class PolicyPickerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            channel=os.environ.get("HAITOO_BROWSER_CHANNEL") or None,
        )
        self.page = await self.browser.new_page(viewport={"width": 1280, "height": 1000})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.environments = [
            {"container_code": "env-b", "name": "同名环境", "metadata_fields": {"group": "MY", "serial_number": 12}, "account_names": ["B@Shop.test"]},
            {"container_code": "env-a", "name": "同名环境", "metadata_fields": {"group": "MY", "serial_number": 11}, "account_names": ["A@Shop.test"]},
            {"container_code": "env-c", "name": "印尼店铺", "metadata_fields": {"group": "ID"}},
            {"container_code": "env-d", "name": "未分组店铺", "metadata_fields": {"group": "  "}},
            {"container_code": "env-e", "name": "真实分组同名", "metadata_fields": {"group": "不可用环境"}},
        ]
        self.policies = [{"template_id": 1, "template_name": "M05L", "mode": "round_robin", "container_codes": ["env-c", "missing"]}]
        self.active = None
        self.saved = None
        await self.page.route("http://policy.test/**", self.route)
        await self.page.goto("http://policy.test/")
        await self.page.get_by_role("button", name="编辑", exact=True).click()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()
        self.assertEqual(self.errors, [])

    async def route(self, route):
        path = urlparse(route.request.url).path
        static = Path(__file__).resolve().parents[1] / "static"
        if path == "/":
            await route.fulfill(path=str(static / "index.html"), content_type="text/html")
            return
        if path.startswith("/assets/"):
            await route.fulfill(path=str(static / path.removeprefix("/assets/")))
            return
        if path == "/api/status":
            data = {"csrf": "test", "user": {"name": "测试"}, "active_task_id": self.active}
        elif path == "/api/environments":
            data = self.environments
        elif path == "/api/policies":
            data = {"templates": [{"id": 1, "name": "M05L"}], "policies": self.policies}
        elif path == "/api/policies/1":
            self.saved = route.request.post_data_json
            self.policies[0].update(self.saved)
            data = {"ok": True}
        elif path == "/api/tasks":
            data = {"items": [], "total": 0}
        else:
            data = {"lines": []}
        await route.fulfill(json=data)

    async def group(self, name):
        await self.page.locator("#policy-group-label").click()
        await self.page.locator("#policy-group-options").get_by_role("button", name=name, exact=True).click()

    async def codes(self):
        return await self.page.evaluate("[...policyCodes]")

    async def visible_codes(self):
        return await self.page.locator("#policy-environments input").evaluate_all("items => items.map(item => item.value)")

    async def test_cross_group_search_and_save_order(self):
        await self.group("未分组（1）")
        self.assertEqual(await self.visible_codes(), ["env-d"])
        await self.group("MY（2）")
        await self.page.locator('input[value="env-b"]').click()
        await self.page.locator('input[value="env-a"]').click()
        self.assertEqual(await self.codes(), ["env-c", "missing", "env-b", "env-a"])
        for query, expected in [("b@SHOP", ["env-b"]), ("11", ["env-a"]), ("ENV-A", ["env-a"]), ("同名", ["env-b", "env-a"]), ("印尼", [])]:
            await self.page.locator("#policy-search").fill(query)
            self.assertEqual(await self.visible_codes(), expected)
        await self.page.locator("#policy-search").fill("11")
        await self.page.locator('input[value="env-a"]').click()
        self.assertEqual(await self.codes(), ["env-c", "missing", "env-b"])
        await self.page.locator("#policy-search").fill("ENV-A")
        await self.page.locator('input[value="env-a"]').click()
        self.assertEqual(await self.codes(), ["env-c", "missing", "env-b", "env-a"])
        self.assertEqual(await self.page.evaluate("document.activeElement.value"), "env-a")
        await self.page.keyboard.press("Space")
        self.assertEqual(await self.codes(), ["env-c", "missing", "env-b"])
        await self.page.locator("#policy-search").fill("")
        await self.group("全部分组（6）")
        await self.page.locator("#policy-selected-only").check()
        self.assertEqual(await self.visible_codes(), ["env-b", "env-c", "missing"])
        await self.page.locator('input[value="missing"]').click()
        self.assertEqual(await self.visible_codes(), ["env-b", "env-c"])
        await self.page.locator("#save-policy").click()
        self.assertEqual(self.saved, {"template_id": 1, "mode": "round_robin", "container_codes": ["env-c", "env-b"]})
        await self.page.get_by_role("button", name="编辑", exact=True).click()
        self.assertEqual(await self.codes(), ["env-c", "env-b"])
        self.assertEqual(await self.visible_codes(), ["env-b", "env-a", "env-c", "env-d", "env-e"])
        self.assertFalse(await self.page.locator("#policy-selected-only").is_checked())

    async def test_group_search_unavailable_and_refresh(self):
        await self.page.locator("#policy-group-label").click()
        await self.page.locator("#policy-group-search").fill("my")
        await self.page.keyboard.press("Enter")
        self.assertIsNone(self.saved)
        self.assertEqual(await self.page.locator("#policy-group-options button").all_text_contents(), ["全部分组（6）", "MY（2）"])
        await self.page.keyboard.press("Escape")
        self.assertTrue(await self.page.locator("#policy-dialog").evaluate("el => el.open"))
        await self.page.locator("#policy-group-label").click()
        await self.page.locator("#policy-group-search").fill("不可用")
        # 真实分组和不可用项名称相同也不会合并。
        self.assertEqual(await self.page.locator("#policy-group-options button").count(), 3)
        await self.page.keyboard.press("Escape")
        await self.page.locator("#policy-search").fill("missing")
        await self.page.keyboard.press("Enter")
        self.assertIsNone(self.saved)
        self.assertEqual(await self.visible_codes(), ["missing"])
        await self.page.locator('input[value="missing"]').click()
        await self.page.locator("#policy-search").fill("")
        self.environments = [e for e in self.environments if e["container_code"] != "env-c"]
        self.environments.append({"container_code": "new-my", "name": "新环境", "metadata_fields": {"group": "MY"}})
        await self.page.evaluate("refresh()")
        self.assertIn("env-c", await self.visible_codes())
        self.assertIn("不可用", await self.page.locator('label:has(input[value="env-c"])').inner_text())
        self.assertEqual(await self.codes(), ["env-c"])
        self.active = 10
        await self.page.evaluate("refresh()")
        self.assertTrue(await self.page.locator("#save-policy").is_disabled())
        self.assertTrue(await self.page.locator('input[value="env-c"]').is_disabled())

    async def test_many_environments_mobile_and_empty_results(self):
        self.environments += [{"container_code": f"extra-{i}", "name": "很长的环境名称" * 12, "metadata_fields": {"group": f"分组{i % 30}"}} for i in range(500)]
        await self.page.evaluate("refresh()")
        self.assertEqual(len(await self.visible_codes()), 506)
        await self.page.set_viewport_size({"width": 375, "height": 812})
        geometry = await self.page.locator("#policy-dialog").evaluate("el => ({width:el.getBoundingClientRect().width, scroll:el.scrollWidth, client:el.clientWidth})")
        self.assertLessEqual(geometry["width"], 343)
        self.assertLessEqual(geometry["scroll"], geometry["client"])
        await self.page.locator("#policy-search").fill("不存在的环境")
        self.assertEqual(await self.visible_codes(), [])
        self.assertIn("没有匹配", await self.page.locator("#policy-environments").inner_text())
        await self.page.locator("#close-policy").click()
        self.environments = []
        self.policies = []
        await self.page.evaluate("refresh()")
        await self.page.locator("#add-policy").click()
        self.assertIn("暂无可用", await self.page.locator("#policy-environments").inner_text())


if __name__ == "__main__":
    unittest.main()
