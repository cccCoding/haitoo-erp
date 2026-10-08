import asyncio
import importlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp.test_utils import TestClient, TestServer
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hubstudio import HubstudioClient, HubAccount
from workbench import LocalStatusServer


class HubstudioClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_environment_snapshot_shows_accounts_without_credentials(self):
        client = HubstudioClient("local")
        client.post = AsyncMock(return_value={"list": [{"containerCode": 10, "accounts": [
            {"accountName": "shop@example.com", "accountPassword": "private", "otpSecret": "private-otp"},
            {"accountName": "shop@example.com"}, {"accountName": ""}]}], "total": 1})
        result = await client.environments()
        self.assertEqual(result[0]["account_names"], ["shop@example.com"])
        self.assertNotIn("private", json.dumps(result))
    async def test_bound_account_is_exactly_matched_and_secrets_are_not_in_repr(self):
        client = HubstudioClient("http://127.0.0.1:6873")
        client.post = AsyncMock(side_effect=[
            {"list": [{"containerCode": 10, "accounts": [{"name": "Shop", "accountName": "shop@example.com"}]}]},
            {"list": [{"name": "Shop", "accountName": "shop@example.com", "accountPassword": "private-password", "otpSecret": "private-otp", "domainName": "https://seller-my.tiktok.com/"}], "total": 1}])
        account = await client.bound_account("10")
        self.assertEqual(account.password, "private-password")
        self.assertEqual(account.login_url, "https://seller-my.tiktok.com/")
        self.assertNotIn("private", repr(account))
        self.assertNotIn("shop@example.com", repr(account))
        self.assertEqual(client.post.await_args_list[0].args[1]["containerCodes"], ["10"])

    async def test_unbound_or_duplicate_or_foreign_accounts_are_rejected(self):
        for bound in ([], [{"name": "Shop", "accountName": "a"}, {"name": "Other", "accountName": "b"}]):
            client = HubstudioClient("local")
            client.post = AsyncMock(return_value={"list": [{"containerCode": 10, "accounts": bound}]})
            with self.assertRaisesRegex(RuntimeError, "唯一绑定"):
                await client.bound_account("10")
            self.assertEqual(client.post.await_count, 1)
        client = HubstudioClient("local")
        client.post = AsyncMock(side_effect=[
            {"list": [{"containerCode": 10, "accounts": [{"name": "Shop", "accountName": "a"}]}]},
            {"list": [{"name": "Shop", "accountName": "a", "accountPassword": "secret", "domainName": "https://seller-my.tiktok.com.evil.example/"}], "total": 1}])
        with self.assertRaisesRegex(RuntimeError, "卖家地址"):
            await client.bound_account("10")

    async def test_password_permission_missing_does_not_invent_credentials(self):
        client = HubstudioClient("local")
        client.post = AsyncMock(side_effect=[
            {"list": [{"containerCode": 10, "accounts": [{"name": "Shop", "accountName": "a"}]}]},
            {"list": [{"name": "Shop", "accountName": "a", "accountPassword": None, "domainName": "https://seller-my.tiktok.com/"}], "total": 1}])
        self.assertIsNone((await client.bound_account("10")).password)
    async def test_paginated_local_scope_and_secret_filter(self):
        client = HubstudioClient("http://127.0.0.1:6873")
        client.post = AsyncMock(side_effect=[{"list": [{"containerCode": i, "containerName": f"Env {i}", "tagName": "Group", "proxyPassword": "private", "lastCountry": "MY"} for i in range(200)], "total": 201}, {"list": [{"containerCode": 200, "containerName": "Last"}], "total": 201}])
        result = await client.environments()
        self.assertEqual(len(result), 201)
        self.assertEqual(client.post.await_args_list[1].args[1], {"current": 2, "size": 200})
        self.assertNotIn("proxyPassword", json.dumps(result))
        self.assertNotIn("MY", json.dumps(result))
        self.assertEqual(result[0]["metadata_fields"], {"group": "Group"})
        self.assertEqual(result[-1]["metadata_fields"], {})

    async def test_incomplete_duplicate_and_changing_snapshot_rejected(self):
        for pages in ([{"list": [], "total": 1}], [{"list": [{"containerCode": 1}, {"containerCode": 1}], "total": 2}], [{"list": [{"containerCode": 1}], "total": 2}, {"list": [{"containerCode": 2}], "total": 3}]):
            client = HubstudioClient("http://127.0.0.1:6873"); client.post = AsyncMock(side_effect=pages)
            with self.assertRaises(RuntimeError): await client.environments()

    async def test_start_uses_local_session_and_boolean_parameter(self):
        client = HubstudioClient("http://127.0.0.1:6873", {"app_secret": "not-sent"})
        client.post = AsyncMock(return_value={"statusCode": "0", "debuggingPort": "1234"})
        self.assertEqual(await client.start("env"), 1234)
        self.assertEqual(client.post.await_args.args[1], {"containerCode": "env", "shouldCloseTabsOnOpen": False})


class WorkbenchTests(unittest.IsolatedAsyncioTestCase):
    async def test_chinese_logs_support_utf8_legacy_windows_and_mixed_files(self):
        old = "2026-10-08 INFO 正在启动环境"
        new = "2026-10-08 INFO [imported] 商品导入成功"
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "agent.log"
            self.workbench.log_path = log
            for encodings in (("utf-8", "utf-8"), ("gbk", "gbk"), ("gbk", "utf-8")):
                with self.subTest(encodings=encodings):
                    log.write_bytes(old.encode(encodings[0]) + b"\r\n" + new.encode(encodings[1]) + b"\r\n")
                    response = await self.client.get("/api/logs")
                    self.assertEqual((await response.json())["lines"], [old, new])

    async def test_log_tail_discards_partial_multibyte_line_and_limits_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "agent.log"
            self.workbench.log_path = log
            expected = [f"中文日志 {i}" for i in range(120)]
            log.write_bytes(("中" * 30000 + "\n" + "\n".join(expected) + "\n").encode("utf-8"))
            response = await self.client.get("/api/logs")
            self.assertEqual((await response.json())["lines"], expected[-100:])

    async def test_clear_logs_requires_csrf_and_preserves_new_appends(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "agent.log"
            log.write_text("previous log\n")
            self.workbench.log_path = log
            response = await self.client.post("/api/logs/clear", json={})
            self.assertEqual(response.status, 403)
            self.assertEqual(log.read_text(), "previous log\n")
            response = await self.client.post("/api/logs/clear", json={}, headers={"Origin": self.workbench.origin, "X-CSRF-Token": self.workbench.csrf})
            self.assertEqual(response.status, 200)
            self.assertEqual(log.read_text(), "")
            with log.open("a") as stream:
                stream.write("new log\n")
            self.assertEqual((await (await self.client.get("/api/logs")).json())["lines"], ["new log"])
        self.backend.request.assert_not_awaited()
    async def test_abort_is_local_and_requires_csrf(self):
        self.workbench.abort_callback = AsyncMock(return_value={"ok": True})
        response = await self.client.post("/api/tasks/12/abort", json={})
        self.assertEqual(response.status, 403)
        self.workbench.abort_callback.assert_not_awaited()
        response = await self.client.post("/api/tasks/12/abort", json={}, headers={"Origin": self.workbench.origin, "X-CSRF-Token": self.workbench.csrf})
        self.assertEqual(response.status, 200)
        self.workbench.abort_callback.assert_awaited_once_with(12)
        self.backend.request.assert_not_awaited()
    async def asyncSetUp(self):
        self.backend = MagicMock(); self.backend.request = AsyncMock(return_value={"items": [], "total": 0})
        self.state = {"user": {"id": 1, "name": "User"}, "paused": False, "environments": []}
        self.sync = AsyncMock()
        self.workbench = LocalStatusServer(self.state, lambda: self.backend, self.sync)
        self.server = TestServer(self.workbench.app())
        self.client = TestClient(self.server, cookie_jar=aiohttp.CookieJar(unsafe=True))
        await self.client.start_server()
        self.workbench.port = self.server.port
        self.workbench.origin = f"http://127.0.0.1:{self.server.port}"
        await self.client.get("/")

    async def asyncTearDown(self): await self.client.close()

    async def test_csrf_origin_host_and_session(self):
        for headers in ({}, {"Origin": "https://evil.example", "X-CSRF-Token": self.workbench.csrf}, {"Origin": self.workbench.origin, "X-CSRF-Token": "wrong"}):
            response = await self.client.post("/api/pause", json={"paused": True}, headers=headers)
            self.assertEqual(response.status, 403)
        response = await self.client.post("/api/pause", json={"paused": True}, headers={"Origin": self.workbench.origin, "X-CSRF-Token": self.workbench.csrf})
        self.assertEqual(response.status, 200)
        self.assertTrue(self.state["paused"])
        self.assertEqual((await self.client.get("/api/status", headers={"Host": "evil.example"})).status, 403)
        self.client.session.cookie_jar.clear()
        self.assertEqual((await self.client.get("/api/status")).status, 403)

    async def test_status_allowlist_and_task_scope(self):
        self.state.update({"token": "private", "app_secret": "secret"})
        response = await self.client.get("/api/status"); data = await response.json()
        self.assertNotIn("token", data); self.assertNotIn("app_secret", data)
        await self.client.get("/api/tasks?user_id=99&page=2&status=completed")
        self.backend.request.assert_awaited_once_with("GET", "/hub-agent/tasks", params={"page": "2", "status": "completed"})
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    async def test_reopening_page_does_not_start_execution_or_sync(self):
        await self.client.get("/"); await self.client.get("/")
        self.sync.assert_not_awaited()
        self.backend.request.assert_not_awaited()

    async def test_login_requires_csrf_and_never_returns_credentials(self):
        self.workbench.login_callback = AsyncMock(return_value={"token": "must-not-return"})
        response = await self.client.post("/api/login", json={"email": "a@b.com", "password": "secret"})
        self.assertEqual(response.status, 403)
        self.workbench.login_callback.assert_not_awaited()
        response = await self.client.post("/api/login", json={"email": "a@b.com", "password": "secret"},
            headers={"Origin": self.workbench.origin, "X-CSRF-Token": self.workbench.csrf})
        self.assertEqual(await response.json(), {"ok": True})
        self.workbench.login_callback.assert_awaited_once_with("a@b.com", "secret")

    async def test_environment_list_and_selection_never_call_erp(self):
        self.state["environments"] = [{"container_code": "env-1", "name": "Local", "auto_upload_enabled": False}]
        response = await self.client.get("/api/environments")
        self.assertEqual((await response.json())[0]["name"], "Local")
        self.workbench.toggle_callback = AsyncMock(return_value={"auto_upload_enabled": True})
        response = await self.client.put("/api/environments/env-1/auto-upload", json={"enabled": True, "confirmed_local": True},
            headers={"Origin": self.workbench.origin, "X-CSRF-Token": self.workbench.csrf})
        self.assertEqual(response.status, 200)
        self.workbench.toggle_callback.assert_awaited_once_with("env-1", True, True)
        self.backend.request.assert_not_awaited()


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_log_writer_uses_utf8_with_windows_default_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-c", "import locale; locale.getencoding = lambda: 'cp936'; "
                 "import haitoo_hub_agent as agent; agent.logger.info('商品导入成功'); "
                 "import logging; logging.shutdown()"],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "HAITOO_AGENT_DATA_DIR": directory},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("商品导入成功", (Path(directory) / "agent.log").read_text(encoding="utf-8"))

    async def test_abort_stops_execution_reports_attention_and_pauses_queue(self):
        for submitting in (False, True):
            with self.subTest(submitting=submitting):
                runtime = self.agent.AgentRuntime({})
                runtime.client = MagicMock(); runtime.client.report = AsyncMock(); runtime.client.download = AsyncMock()
                claim = {"task": {"id": 12, "export_filename": "test.xlsx"}, "claim_token": "token", "hubstudio": {"container_code": "env"}}
                runtime.current_claim = claim
                started = asyncio.Event()
                async def upload(port, path, before_import, *args):
                    if submitting:
                        await before_import()
                    started.set()
                    await asyncio.Event().wait()
                with patch.object(self.agent.HubstudioClient, "start", AsyncMock(return_value=1234)), \
                     patch.object(self.agent.HubstudioClient, "bound_account", AsyncMock(side_effect=RuntimeError("manual login"))), \
                     patch.object(self.agent, "upload_and_import", side_effect=upload):
                    runtime.execution = asyncio.create_task(runtime.execute(claim))
                    await started.wait()
                    await runtime.abort_task(12)
                    await runtime.abort_task(12)  # 重复请求不能二次打断中止报告。
                    with self.assertRaises(asyncio.CancelledError):
                        await runtime.execution
                self.assertTrue(runtime.state["paused"])
                reports = [call.args for call in runtime.client.report.await_args_list]
                self.assertEqual(reports[-1][2:4], ("awaiting_attention", "manually_aborted"))
                self.assertIn("结果未知" if submitting else "尚未进入导入阶段", reports[-1][4])
                self.assertFalse(any(call[2] == "completed" for call in reports))

    async def test_abort_rejects_tasks_not_running_on_this_computer(self):
        runtime = self.agent.AgentRuntime({})
        with self.assertRaises(self.agent.ERPRequestError):
            await runtime.abort_task(99)
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        (Path(cls.temp.name) / "test.xlsx").write_bytes(b"test workbook")
        os.environ["HAITOO_AGENT_DATA_DIR"] = cls.temp.name
        cls.agent = importlib.import_module("haitoo_hub_agent")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("HAITOO_AGENT_DATA_DIR", None)
        import logging
        for handler in list(logging.getLogger().handlers):
            if getattr(handler, "baseFilename", "") == str(Path(cls.temp.name) / "agent.log"):
                logging.getLogger().removeHandler(handler); handler.close()
        cls.temp.cleanup()

    def setUp(self):
        self.login_language_patch = patch.object(self.agent, "login_page_language", AsyncMock(return_value="zh"))
        self.login_language_patch.start(); self.addCleanup(self.login_language_patch.stop)

    def controls(self, count=1, success=True):
        language_patch = patch.object(self.agent, "ensure_simplified_chinese", AsyncMock())
        language_patch.start(); self.addCleanup(language_patch.stop)
        file_input = AsyncMock(); file_input.count.return_value = count; file_input.is_enabled.return_value = True
        submit = AsyncMock(); submit.count.return_value = 1; submit.is_enabled.return_value = True
        success_control = AsyncMock(); success_control.count.return_value = 0
        if not success:
            async def wait_success(**kwargs):
                if kwargs.get("timeout") == 60_000:
                    raise self.agent.PlaywrightTimeoutError("unknown result")
            success_control.wait_for.side_effect = wait_success
        login = AsyncMock(); login.count.return_value = 0
        errors = AsyncMock(); errors.count.return_value = 0
        page = MagicMock(); page.url = "https://seller.tiktokglobalshop.com/products/bulk-upload"; page.goto = AsyncMock(); page.locator.return_value = file_input
        chinese = AsyncMock(); chinese.count.return_value = 1; chinese.is_visible.return_value = True
        page.get_by_text.return_value = success_control
        page.get_by_text.side_effect = lambda text, **kwargs: chinese if isinstance(text, re.Pattern) and text.pattern == r"^\s*简体中文\s*$" else success_control
        alert = MagicMock(); alert.filter.return_value = errors
        import_button = AsyncMock(); import_button.count.return_value = 1; import_button.is_enabled.return_value = True
        page.import_button = import_button
        page.get_by_role.side_effect = lambda role, **kwargs: alert if role == "alert" else (login if "log" in kwargs["name"].pattern else (import_button if "导入" in kwargs["name"].pattern else submit))
        context = MagicMock(); context.new_page = AsyncMock(return_value=page)
        browser = MagicMock(); browser.contexts = [context]; browser.close = AsyncMock()
        playwright = MagicMock(); playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        manager = MagicMock(); manager.__aenter__ = AsyncMock(return_value=playwright); manager.__aexit__ = AsyncMock(return_value=False)
        return manager, submit, file_input, page

    async def test_auto_login_uses_email_form_once_and_never_logs_secrets(self):
        page = MagicMock(); page.url = "https://seller.tiktokshopglobalselling.com/account/login"
        switch = AsyncMock(); switch.count.return_value = 1; switch.is_visible.return_value = True
        page.get_by_text.return_value = switch
        email, password, login = AsyncMock(), AsyncMock(), AsyncMock()
        for control in (email, password, login):
            control.count.return_value = 1; control.is_visible.return_value = True
        login.is_enabled.return_value = True
        page.locator.side_effect = [email, password]
        page.get_by_role.return_value = login
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        with patch.object(self.agent, "logger") as logger:
            self.assertTrue(await self.agent.attempt_account_login(page, account))
        switch.click.assert_not_awaited()
        email.fill.assert_awaited_once_with(account.account_name)
        password.fill.assert_awaited_once_with(account.password)
        login.click.assert_awaited_once()
        self.assertNotIn(account.password, str(logger.mock_calls))

    async def test_phone_form_switches_to_email_before_filling_credentials(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/account/login"
        email, password, login, switch = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        for control in (email, password, login, switch):
            control.count.return_value = 1; control.is_visible.return_value = True
        email.count.return_value = 0
        login.is_enabled.return_value = True
        page.locator.side_effect = [email, password]
        page.get_by_text.return_value = switch; page.get_by_role.return_value = login
        async def switch_email():
            email.fill.assert_not_awaited(); password.fill.assert_not_awaited()
            email.count.return_value = 1
        switch.click.side_effect = switch_email
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        self.assertTrue(await self.agent.attempt_account_login(page, account))
        switch.click.assert_awaited_once()
        email.fill.assert_awaited_once_with(account.account_name)
        password.fill.assert_awaited_once_with(account.password)
        login.click.assert_awaited_once()

    async def test_phone_form_without_email_switch_never_fills_credentials(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/account/login"
        email, switch = AsyncMock(), AsyncMock()
        email.count.return_value = 0; switch.count.return_value = 0
        page.locator.return_value = email; page.get_by_text.return_value = switch
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        self.assertFalse(await self.agent.attempt_account_login(page, account))
        email.fill.assert_not_awaited(); page.get_by_role.assert_not_called()

    async def test_login_page_language_reads_chinese_us_and_uk_without_clicking(self):
        self.login_language_patch.stop()
        for text, expected in (("简体中文", "zh"), ("US English", "en"), ("UK English", "en")):
            page = MagicMock(); language = AsyncMock()
            language.count.return_value = 1; language.is_visible.return_value = True
            language.inner_text.return_value = text; page.get_by_text.return_value = language
            self.assertEqual(await self.agent.login_page_language(page), expected)
            language.click.assert_not_awaited()
            self.assertRegex(text, page.get_by_text.call_args.args[0])

    async def test_english_login_uses_english_email_entry_without_changing_language(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/account/login"
        email, password, login, switch = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        email.count.return_value = 0
        for control in (password, login, switch):
            control.count.return_value = 1; control.is_visible.return_value = True
        email.is_visible.return_value = True
        async def switched():
            email.count.return_value = 1
        switch.click.side_effect = switched
        page.locator.side_effect = [email, password]; page.get_by_role.return_value = login
        page.get_by_text.return_value = switch
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        with patch.object(self.agent, "login_page_language", AsyncMock(return_value="en")), \
             patch.object(self.agent, "ensure_simplified_chinese", AsyncMock()) as change:
            self.assertTrue(await self.agent.attempt_account_login(page, account))
        self.assertRegex("Log in with email", page.get_by_text.call_args.args[0])
        switch.click.assert_awaited_once(); change.assert_not_awaited()

    async def test_upload_language_menu_switches_verifies_and_closes(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/product/batch/publish"
        language, option, chinese = AsyncMock(), AsyncMock(), AsyncMock()
        for control in (language, option, chinese):
            control.count.return_value = 1; control.is_visible.return_value = True
        language.inner_text.return_value = "US English"
        page.get_by_text.side_effect = [language, option, chinese]
        page.locator.return_value.wait_for = AsyncMock()
        events = []
        report = AsyncMock()
        async def opened(_, *args): events.append("open")
        async def closed(_): events.append("close")
        async def choose(): events.append("choose")
        option.click.side_effect = choose
        with patch.object(self.agent, "toggle_account_menu", side_effect=opened), \
             patch.object(self.agent, "close_account_menu", side_effect=closed), \
             patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=False)), \
             patch.object(self.agent, "confirm_chinese_after_switch", AsyncMock(side_effect=opened)):
            await self.agent.ensure_simplified_chinese(page, report)
        self.assertEqual([call.args[0] for call in report.await_args_list], ["checking_language", "checking_language", "switching_language", "verifying_language", "language_ready", "closing_account_menu", "account_menu_closed"])
        self.assertEqual(events, ["open", "choose", "close", "open", "close"])
        language.click.assert_awaited_once()

    async def test_language_verification_reopens_menu_after_refresh(self):
        page = MagicMock(); chinese = AsyncMock()
        chinese.count.return_value = 0; page.get_by_text.return_value = chinese
        report = AsyncMock()
        with patch.object(self.agent, "unique_visible", AsyncMock(side_effect=[None, None, None, chinese])), \
             patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=False)), \
             patch.object(self.agent, "toggle_account_menu", AsyncMock()) as toggle, \
             patch.object(self.agent.asyncio, "sleep", AsyncMock()):
            await self.agent.confirm_chinese_after_switch(page, report)
        self.assertEqual(toggle.await_count, 2)
        self.assertEqual(report.await_count, 2)

    async def test_language_verification_has_total_timeout(self):
        page = MagicMock(); chinese = AsyncMock(); chinese.count.return_value = 0
        page.get_by_text.return_value = chinese
        with patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=True)):
            with self.assertRaises(self.agent.PlaywrightTimeoutError):
                await self.agent.confirm_chinese_after_switch(page, timeout=0.01)

    async def test_upload_language_chinese_still_opens_and_closes_account_menu(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/product/batch/publish"
        chinese = AsyncMock(); chinese.count.return_value = 1; chinese.is_visible.return_value = True
        chinese.inner_text.return_value = "简体中文"; page.get_by_text.return_value = chinese
        with patch.object(self.agent, "toggle_account_menu", AsyncMock()) as opened, \
             patch.object(self.agent, "close_account_menu", AsyncMock()) as closed, \
             patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=False)):
            await self.agent.ensure_simplified_chinese(page)
        opened.assert_awaited_once(); closed.assert_awaited_once(); chinese.click.assert_not_awaited()

    async def test_language_failure_prevents_file_upload(self):
        manager, submit, file_input, page = self.controls()
        with patch.object(self.agent, "async_playwright", return_value=manager), \
             patch.object(self.agent, "ensure_simplified_chinese", AsyncMock(side_effect=RuntimeError("账号菜单语言未确认"))):
            with self.assertRaisesRegex(RuntimeError, "账号菜单语言未确认"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        file_input.set_input_files.assert_not_awaited(); submit.click.assert_not_awaited()

    async def test_language_timeout_reports_exact_step_without_success(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/product/batch/publish"
        language = AsyncMock(); language.wait_for.side_effect = self.agent.PlaywrightTimeoutError("raw page data")
        page.get_by_text.return_value = language
        report = AsyncMock()
        with patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=False)), \
             patch.object(self.agent, "toggle_account_menu", AsyncMock()):
            with self.assertRaisesRegex(RuntimeError, "读取账号菜单当前语言"):
                await self.agent.ensure_simplified_chinese(page, report)
        self.assertEqual(report.await_args.args[0], "language_failed")
        self.assertIn("尚未上传", report.await_args.args[1])
        self.assertNotIn("raw page data", report.await_args.args[1])
        self.assertNotIn("language_ready", [call.args[0] for call in report.await_args_list])

    async def test_runtime_persists_browser_progress_in_task_logs(self):
        runtime = self.agent.AgentRuntime({})
        runtime.client = MagicMock(); runtime.client.report = AsyncMock(); runtime.client.download = AsyncMock()
        claim = {"task": {"id": 12, "export_filename": "test.xlsx"}, "claim_token": "token", "hubstudio": {"container_code": "env"}}
        async def browser(port, path, before_import, login_required, upload_ready, account, on_progress):
            for stage in ("logged_in", "checking_language", "switching_language", "language_ready", "account_menu_closed"):
                await on_progress(stage, "测试阶段")
            await upload_ready()
            await on_progress("upload_parsing", "等待解析")
            await before_import()
        with patch.object(self.agent.HubstudioClient, "start", AsyncMock(return_value=1234)), \
             patch.object(self.agent.HubstudioClient, "bound_account", AsyncMock(side_effect=RuntimeError("manual login"))), \
             patch.object(self.agent, "upload_and_import", side_effect=browser):
            await runtime.execute(claim)
        stages = [call.args[3] for call in runtime.client.report.await_args_list]
        self.assertEqual(stages[-9:], ["logged_in", "checking_language", "switching_language", "language_ready", "account_menu_closed", "uploading", "upload_parsing", "importing", "imported"])

    async def test_account_menu_close_falls_back_to_account_toggle(self):
        page = MagicMock(); page.keyboard.press = AsyncMock()
        with patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=True)), \
             patch.object(self.agent, "wait_account_menu_hidden", AsyncMock(side_effect=[self.agent.PlaywrightTimeoutError("still open"), None])) as wait, \
             patch.object(self.agent, "toggle_account_menu", AsyncMock()) as toggle:
            await self.agent.close_account_menu(page)
        page.keyboard.press.assert_awaited_once_with("Escape")
        toggle.assert_awaited_once_with(page)
        self.assertEqual(wait.await_count, 2)

    async def test_closed_account_menu_is_not_toggled_open_when_closing(self):
        page = MagicMock(); page.keyboard.press = AsyncMock()
        with patch.object(self.agent, "account_menu_visible", AsyncMock(return_value=False)), \
             patch.object(self.agent, "toggle_account_menu", AsyncMock()) as toggle:
            await self.agent.close_account_menu(page)
        toggle.assert_not_awaited(); page.keyboard.press.assert_not_awaited()

    async def test_account_menu_marker_accepts_logout_row_with_email(self):
        page = MagicMock()
        language = AsyncMock(); language.count.return_value = 0
        logout = AsyncMock(); logout.count.return_value = 1; logout.is_visible.return_value = True
        page.get_by_text.side_effect = [language, logout]
        self.assertTrue(await self.agent.account_menu_visible(page))
        self.assertRegex("退出登录 l***c@hotmail.com （主账号）", page.get_by_text.call_args.args[0])

    async def test_language_menu_is_closed_before_upload(self):
        manager, _, file_input, page = self.controls()
        checked = False
        async def check_language(_, callback=None):
            nonlocal checked
            file_input.set_input_files.assert_not_awaited()
            checked = True
        async def upload(_):
            self.assertTrue(checked)
        file_input.set_input_files.side_effect = upload
        with patch.object(self.agent, "async_playwright", return_value=manager), \
             patch.object(self.agent, "ensure_simplified_chinese", side_effect=check_language):
            await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        file_input.set_input_files.assert_awaited_once()

    async def test_password_fill_errors_do_not_leak_credentials(self):
        page = MagicMock(); page.url = "https://seller.tiktokshopglobalselling.com/account/login"
        switch = AsyncMock(); switch.count.return_value = 0; page.get_by_text.return_value = switch
        email, password, login = AsyncMock(), AsyncMock(), AsyncMock()
        for control in (email, password, login):
            control.count.return_value = 1; control.is_visible.return_value = True
        password.fill.side_effect = self.agent.PlaywrightError("value private-password")
        page.locator.side_effect = [email, password]; page.get_by_role.return_value = login
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        with patch.object(self.agent, "logger") as logger:
            self.assertFalse(await self.agent.attempt_account_login(page, account))
        self.assertNotIn(account.password, str(logger.mock_calls))
        login.click.assert_not_awaited()

    async def test_login_timeout_logs_step_and_type_without_raw_error(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/account/login"
        email = AsyncMock(); email.count.return_value = 1; email.is_visible.return_value = True
        email.wait_for.side_effect = self.agent.PlaywrightTimeoutError("private-password page content")
        page.locator.return_value = email
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        with patch.object(self.agent, "logger") as logger:
            self.assertFalse(await self.agent.attempt_account_login(page, account))
        output = str(logger.mock_calls)
        self.assertIn("等待可见邮箱输入框", output)
        self.assertIn("TimeoutError", output)
        self.assertNotIn(account.password, output)
        self.assertNotIn("page content", output)
        email.fill.assert_not_awaited()

    async def test_hidden_login_button_is_ignored(self):
        page = MagicMock(); page.url = "https://seller-my.tiktok.com/account/login"
        email, password, hidden_login, visible_login = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        for control in (email, password):
            control.count.return_value = 1; control.is_visible.return_value = True
        hidden_login.is_visible.return_value = False; visible_login.is_visible.return_value = True
        candidates = MagicMock(); candidates.count = AsyncMock(return_value=2)
        candidates.nth.side_effect = [hidden_login, visible_login]
        page.locator.side_effect = [email, password]; page.get_by_role.return_value = candidates
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        self.assertTrue(await self.agent.attempt_account_login(page, account))
        hidden_login.click.assert_not_awaited(); visible_login.click.assert_awaited_once()
        pattern = page.get_by_role.call_args.kwargs["name"]
        self.assertRegex("登 录", pattern)

    async def test_auto_login_never_fills_foreign_origin_or_missing_password(self):
        page = MagicMock(); page.url = "https://other.example/login"
        account = HubAccount("shop@example.com", "private-password", None, "https://seller-my.tiktok.com/")
        self.assertFalse(await self.agent.attempt_account_login(page, account))
        page.locator.assert_not_called()
        account.password = None
        page.url = account.login_url
        self.assertFalse(await self.agent.attempt_account_login(page, account))
        page.locator.assert_not_called()

    async def test_explicit_success_and_regex(self):
        manager, submit, file_input, page = self.controls()
        before_import = AsyncMock()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            await self.agent.upload_and_import(1234, (Path(self.temp.name) / "test.xlsx"), before_import)
        before_import.assert_awaited_once(); page.import_button.click.assert_awaited_once(); submit.click.assert_not_awaited(); file_input.set_input_files.assert_awaited_once()
        self.assertIsInstance(page.get_by_role.call_args_list[0].kwargs["name"], re.Pattern)

    async def test_import_is_reported_before_click_and_never_publishes(self):
        manager, submit, _, page = self.controls()
        async def importing():
            page.import_button.click.assert_not_awaited()
            submit.click.assert_not_awaited()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx", before_import=importing)
        page.import_button.click.assert_awaited_once()
        submit.click.assert_not_awaited()

    async def test_success_pattern_matches_import_success_anywhere(self):
        manager, _, _, page = self.controls()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        pattern = next(call.args[0] for call in page.get_by_text.call_args_list
                       if isinstance(call.args[0], re.Pattern) and "导入成功" in call.args[0].pattern)
        for text in ("1 件商品导入成功", "14 件商品导入成功", "导入成功", " 2款商品导入成功！ ", "本次商品导入成功，请前往管理商品", "0 件商品导入成功"):
            self.assertRegex(text, pattern)
        for text in ("上传成功", "1 款商品准备就绪", "导入失败", "发布成功"):
            self.assertIsNone(pattern.search(text))

    async def test_existing_visible_import_success_prevents_click(self):
        manager, submit, _, page = self.controls()
        success = MagicMock(); success.count = AsyncMock(return_value=1)
        success.nth.return_value.is_visible = AsyncMock(return_value=True)
        original = page.get_by_text.side_effect
        page.get_by_text.side_effect = lambda text, **kwargs: success if isinstance(text, re.Pattern) and "导入成功" in text.pattern else original(text, **kwargs)
        before_import = AsyncMock()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "已有导入成功"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx", before_import)
        before_import.assert_not_awaited()
        page.import_button.click.assert_not_awaited()
        submit.click.assert_not_awaited()

    async def test_runtime_reports_imported_on_success(self):
        runtime = self.agent.AgentRuntime({})
        runtime.client = MagicMock(); runtime.client.report = AsyncMock(); runtime.client.download = AsyncMock()
        claim = {"task": {"id": 12, "export_filename": "test.xlsx"}, "claim_token": "token", "hubstudio": {"container_code": "env"}}
        with patch.object(self.agent.HubstudioClient, "start", AsyncMock(return_value=1234)), \
             patch.object(self.agent.HubstudioClient, "bound_account", AsyncMock(side_effect=RuntimeError("manual login"))), \
             patch.object(self.agent, "upload_and_import", AsyncMock()):
            await runtime.execute(claim)
        self.assertEqual(runtime.client.report.await_args.args[2:4], ("completed", "imported"))
        self.assertIn("导入成功", runtime.state["status"])

    async def test_import_report_failure_prevents_import_and_publish(self):
        manager, submit, _, page = self.controls()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx", before_import=AsyncMock(side_effect=RuntimeError("offline")))
        page.import_button.click.assert_not_awaited()
        submit.click.assert_not_awaited()

    async def test_ambiguous_import_button_does_not_import_or_publish(self):
        manager, submit, _, page = self.controls()
        page.import_button.count.return_value = 2
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "导入按钮不唯一"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        page.import_button.click.assert_not_awaited()
        submit.click.assert_not_awaited()

    async def test_duplicate_file_stops_without_importing_or_publishing(self):
        manager, submit, _, page = self.controls()
        duplicate = MagicMock(); duplicate.count = AsyncMock(return_value=1)
        duplicate.nth.return_value.is_visible = AsyncMock(return_value=True)
        original = page.get_by_text.side_effect
        page.get_by_text.side_effect = lambda text, **kwargs: duplicate if isinstance(text, re.Pattern) and "文件已存在" in text.pattern else original(text, **kwargs)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(self.agent.DuplicateUploadError, "查看上传记录"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        page.import_button.click.assert_not_awaited()
        submit.click.assert_not_awaited()

    async def test_late_duplicate_is_detected_while_waiting_for_ready(self):
        page = MagicMock()
        duplicate = MagicMock(); duplicate.count = AsyncMock(side_effect=[0, 1])
        duplicate.nth.return_value.is_visible = AsyncMock(return_value=True)
        no_error = AsyncMock(); no_error.count.return_value = 0
        page.get_by_text.side_effect = lambda pattern: duplicate if "文件已存在" in pattern.pattern else no_error
        ready = AsyncMock(); ready.wait_for.side_effect = self.agent.PlaywrightTimeoutError("not ready")
        with self.assertRaises(self.agent.DuplicateUploadError):
            await self.agent.wait_upload_control(page, ready, 120_000)
        ready.wait_for.assert_awaited_once()

    async def test_duplicate_failure_is_reported_and_queue_is_paused(self):
        runtime = self.agent.AgentRuntime({})
        runtime.client = MagicMock(); runtime.client.report = AsyncMock(); runtime.client.download = AsyncMock()
        claim = {"task": {"id": 12, "export_filename": "test.xlsx"}, "claim_token": "token", "hubstudio": {"container_code": "env"}}
        with patch.object(self.agent.HubstudioClient, "start", AsyncMock(return_value=1234)), \
             patch.object(self.agent.HubstudioClient, "bound_account", AsyncMock(side_effect=RuntimeError("manual login"))), \
             patch.object(self.agent, "upload_and_import", AsyncMock(side_effect=self.agent.DuplicateUploadError("此文件已存在，请查看上传记录"))):
            await runtime.execute(claim)
        self.assertTrue(runtime.state["paused"])
        self.assertEqual(runtime.client.report.await_args.args[2:4], ("failed", "duplicate_file"))

    async def test_my_upload_address_keeps_region_and_step_after_login(self):
        manager, _, _, page = self.controls()
        account = HubAccount("shop@example.com", "password", None, "https://seller-my.tiktok.com/")
        with patch.object(self.agent, "async_playwright", return_value=manager):
            await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx", account=account)
        page.goto.assert_awaited_once_with(
            "https://seller-my.tiktok.com/product/batch/publish?entry-from=hub&shop_region=MY&step=2",
            wait_until="domcontentloaded")

    async def test_oversized_workbook_never_connects_or_uploads(self):
        path = Path(self.temp.name) / "oversized.xlsx"
        with path.open("wb") as workbook:
            workbook.truncate(self.agent.MAX_UPLOAD_BYTES + 1)
        try:
            with patch.object(self.agent, "async_playwright") as playwright:
                with self.assertRaisesRegex(RuntimeError, "20 MB"):
                    await self.agent.upload_and_import(1234, path)
            playwright.assert_not_called()
        finally:
            path.unlink()

    async def test_login_redirect_waits_then_resumes_same_upload(self):
        manager, submit, file_input, page = self.controls()
        page.url = "https://seller.tiktokshopglobalselling.com/account/login"
        page.bring_to_front = AsyncMock()
        login_required, upload_ready = AsyncMock(), AsyncMock()
        real_sleep = asyncio.sleep
        async def finish_login(_):
            if "login" not in page.url:
                await real_sleep(0)
                return
            file_input.set_input_files.assert_not_awaited()
            submit.click.assert_not_awaited()
            page.url = self.agent.BULK_UPLOAD_URL
        with patch.object(self.agent, "async_playwright", return_value=manager), \
             patch.object(self.agent.asyncio, "sleep", side_effect=finish_login):
            await self.agent.upload_and_import(1234, (Path(self.temp.name) / "test.xlsx"), on_login_required=login_required, on_upload_ready=upload_ready)
        login_required.assert_awaited_once()
        upload_ready.assert_awaited_once()
        file_input.set_input_files.assert_awaited_once()
        page.import_button.click.assert_awaited_once()
        submit.click.assert_not_awaited()
        self.assertEqual(page.goto.await_count, 2)

    async def test_login_timeout_never_uploads_or_submits(self):
        manager, submit, file_input, page = self.controls()
        page.url = "https://seller.tiktokshopglobalselling.com/account/login"
        page.bring_to_front = AsyncMock()
        login_required = AsyncMock()
        with patch.object(self.agent, "async_playwright", return_value=manager), \
             patch.object(self.agent, "LOGIN_WAIT_SECONDS", 0), \
             patch.object(self.agent.asyncio, "sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, "登录超时"):
                await self.agent.upload_and_import(1234, (Path(self.temp.name) / "test.xlsx"), on_login_required=login_required)
        login_required.assert_awaited_once()
        file_input.set_input_files.assert_not_awaited()
        submit.click.assert_not_awaited()

    async def test_navigation_interrupted_by_login_is_handled(self):
        _, _, _, page = self.controls()
        page.url = "https://seller.tiktokshopglobalselling.com/account/login"
        page.goto.side_effect = self.agent.PlaywrightError("net::ERR_ABORTED")
        await self.agent.open_bulk_upload(page)
        page.url = self.agent.BULK_UPLOAD_URL
        with self.assertRaises(self.agent.PlaywrightError):
            await self.agent.open_bulk_upload(page)

    async def test_upload_error_popup_fails_before_waiting_for_filename_or_import(self):
        manager, submit, file_input, page = self.controls()
        error = AsyncMock(); error.count.return_value = 1; error.is_visible.return_value = True
        original = page.get_by_text.side_effect
        page.get_by_text.side_effect = lambda text, **kwargs: error if isinstance(text, re.Pattern) and "出错" in text.pattern else original(text, **kwargs)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaises(self.agent.ImportDataError):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        file_input.set_input_files.assert_awaited_once()
        page.import_button.click.assert_not_awaited(); submit.click.assert_not_awaited()

    async def test_data_error_appearing_during_upload_wait_stops_on_next_check(self):
        page = MagicMock(); page.context.pages = []; page.frames = []
        error = AsyncMock(); error.count.return_value = 0; error.is_visible.return_value = True
        page.get_by_text.return_value = error
        ready = AsyncMock()
        async def pending(**kwargs):
            error.count.return_value = 1
            raise self.agent.PlaywrightTimeoutError("not ready")
        ready.wait_for.side_effect = pending
        with self.assertRaises(self.agent.ImportDataError):
            await self.agent.wait_upload_control(page, ready, 120_000)
        ready.wait_for.assert_awaited_once()

    async def test_visible_iframe_editor_is_checked_but_hidden_iframe_is_ignored(self):
        for visible in (True, False):
            page = MagicMock(); page.context.pages = []
            main = AsyncMock(); main.count.return_value = 0; page.get_by_text.return_value = main
            frame = MagicMock(); frame.is_detached.return_value = False
            frame.parent_frame = page.main_frame; page.main_frame.parent_frame = None
            element = MagicMock(); element.is_visible = AsyncMock(return_value=visible); element.dispose = AsyncMock()
            frame.frame_element = AsyncMock(return_value=element)
            error = AsyncMock(); error.count.return_value = 1; error.is_visible.return_value = True
            frame.get_by_text.return_value = error; page.frames = [page.main_frame, frame]
            if visible:
                with self.assertRaises(self.agent.ImportDataError):
                    await self.agent.check_import_data_error(page)
            else:
                await self.agent.check_import_data_error(page)
                frame.get_by_text.assert_not_called()
            element.dispose.assert_awaited_once()

    async def test_related_popup_is_checked_and_unrelated_page_is_ignored(self):
        for related in (True, False):
            page = MagicMock(); page.frames = []
            no_error = AsyncMock(); no_error.count.return_value = 0; page.get_by_text.return_value = no_error
            popup = MagicMock(); popup.is_closed.return_value = False; popup.frames = []
            popup.opener = AsyncMock(return_value=page if related else None)
            error = AsyncMock(); error.count.return_value = 1; error.is_visible.return_value = True
            popup.get_by_text.return_value = error; page.context.pages = [page, popup]
            if related:
                with self.assertRaises(self.agent.ImportDataError):
                    await self.agent.check_import_data_error(page)
            else:
                await self.agent.check_import_data_error(page)
                popup.get_by_text.assert_not_called()

    async def test_error_products_popup_after_import_fails_without_publishing(self):
        manager, submit, _, page = self.controls()
        error = AsyncMock(); error.count.return_value = 0; error.is_visible.return_value = True
        async def imported(): error.count.return_value = 1
        page.import_button.click.side_effect = imported
        original = page.get_by_text.side_effect
        page.get_by_text.side_effect = lambda text, **kwargs: error if isinstance(text, re.Pattern) and "出错" in text.pattern else original(text, **kwargs)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(self.agent.ImportDataError, "上传成功，添加商品失败（数据错误）"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        page.import_button.click.assert_awaited_once(); submit.click.assert_not_awaited()
        pattern = next(call.args[0] for call in page.get_by_text.call_args_list
                       if isinstance(call.args[0], re.Pattern) and "出错" in call.args[0].pattern)
        for text in ("无法导入出错商品，请更正。", "修复 1 件出错的商品"):
            self.assertRegex(text, pattern)

    async def test_import_data_error_detected_while_success_is_still_pending(self):
        page = MagicMock(); success = AsyncMock()
        error = AsyncMock(); error.count.return_value = 1; error.is_visible.side_effect = [False, True]
        page.get_by_text.return_value = error
        async def pending(**kwargs):
            await asyncio.Event().wait()
        success.wait_for.side_effect = pending
        with self.assertRaises(self.agent.ImportDataError):
            await self.agent.wait_import_result(page, success)

    async def test_hidden_error_products_does_not_fail_import(self):
        page = MagicMock(); success = AsyncMock()
        error = AsyncMock(); error.count.return_value = 1; error.is_visible.return_value = False
        page.get_by_text.return_value = error
        await self.agent.wait_import_result(page, success)

    async def test_runtime_reports_data_error_as_failed_instead_of_attention(self):
        runtime = self.agent.AgentRuntime({})
        runtime.client = MagicMock(); runtime.client.report = AsyncMock(); runtime.client.download = AsyncMock()
        claim = {"task": {"id": 12, "export_filename": "test.xlsx"}, "claim_token": "token", "hubstudio": {"container_code": "env"}}
        with patch.object(self.agent.HubstudioClient, "start", AsyncMock(return_value=1234)), \
             patch.object(self.agent.HubstudioClient, "bound_account", AsyncMock(side_effect=RuntimeError("manual login"))), \
             patch.object(self.agent, "upload_and_import", AsyncMock(side_effect=self.agent.ImportDataError("上传成功，添加商品失败（数据错误）；请人工查看处理"))):
            await runtime.execute(claim)
        self.assertEqual(runtime.client.report.await_args.args[2:4], ("failed", "import_data_error"))
        self.assertIn("请人工", runtime.client.report.await_args.args[4])
        self.assertFalse(any(call.args[2] == "completed" for call in runtime.client.report.await_args_list))

    async def test_unknown_result_never_counts_as_completed(self):
        manager, submit, _, page = self.controls(success=False)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "导入结果未知"):
                await self.agent.upload_and_import(1234, Path(self.temp.name) / "test.xlsx")
        page.import_button.click.assert_awaited_once()
        submit.click.assert_not_awaited()

    async def test_ambiguous_upload_control_does_not_click(self):
        manager, submit, _, _ = self.controls(count=2)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "唯一"): await self.agent.upload_and_import(1234, (Path(self.temp.name) / "test.xlsx"))
        submit.click.assert_not_awaited()

    async def test_failed_pre_submit_report_prevents_click(self):
        manager, submit, _, _ = self.controls()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaises(RuntimeError): await self.agent.upload_and_import(1234, (Path(self.temp.name) / "test.xlsx"), AsyncMock(side_effect=RuntimeError("offline")))
        submit.click.assert_not_awaited()

    async def test_failed_sync_preserves_previous_snapshot(self):
        runtime = self.agent.AgentRuntime({})
        runtime.client = MagicMock(); runtime.client.request = AsyncMock(return_value={"user": {"id": 1, "name": "U"}})
        runtime.client.post = AsyncMock()
        runtime.state["environments"] = [{"id": 1, "name": "last good"}]
        with patch.object(self.agent.HubstudioClient, "environments", AsyncMock(side_effect=RuntimeError("partial page"))): await runtime.sync()
        self.assertEqual(runtime.state["environments"][0]["name"], "last good")
        self.assertIsNone(runtime.synced_monotonic)
        runtime.client.post.assert_not_awaited()

    async def test_local_login_saves_only_agent_credential_and_rejects_switch(self):
        runtime = self.agent.AgentRuntime({"hubstudio_url": "http://127.0.0.1:6873"})
        client = MagicMock(); client.request = AsyncMock(return_value={"user": {"id": 2, "name": "Employee"}})
        with patch.object(self.agent, "authorize_computer", AsyncMock(return_value="agent-token")), \
             patch.object(self.agent, "ERPClient", return_value=client), \
             patch.object(self.agent.keyring, "set_password") as store, \
             patch.object(self.agent, "save_config") as save:
            await runtime.login("a@b.com", "password-secret")
            self.assertFalse(runtime.state["login_required"])
            self.assertEqual(runtime.state["user"]["id"], 2)
            store.assert_called_once_with(self.agent.SERVICE_NAME, self.agent.TOKEN_KEY, "agent-token")
            self.assertNotIn("password", json.dumps(save.call_args.args[0]))
            with self.assertRaises(self.agent.ERPRequestError):
                await runtime.login("other@b.com", "other-secret")
            runtime.require_login()
            self.assertIsNone(runtime.client)
            self.assertTrue(runtime.state["login_required"])
            self.assertEqual(runtime.state["environments"], [])

    async def test_complete_sync_keeps_directory_in_local_memory(self):
        runtime = self.agent.AgentRuntime({"auto_upload_container_code": "env-2"})
        runtime.client = MagicMock(); runtime.client.request = AsyncMock(return_value={"user": {"id": 1, "name": "User"}})
        runtime.client.post = AsyncMock()
        items = [{"container_code": "env-1", "name": "One", "metadata_fields": {}}, {"container_code": "env-2", "name": "Two", "metadata_fields": {}}]
        with patch.object(self.agent.HubstudioClient, "environments", AsyncMock(return_value=items)), patch.object(self.agent, "save_config") as save:
            await runtime.sync()
        runtime.client.post.assert_not_awaited(); save.assert_not_called()
        self.assertEqual([e["auto_upload_enabled"] for e in runtime.state["environments"]], [False, True])
        self.assertIsNotNone(runtime.synced_monotonic)

    async def test_only_one_selected_environment_and_running_or_stale_blocks_switch(self):
        runtime = self.agent.AgentRuntime({})
        runtime.state["environments"] = [{"container_code": "env-1", "name": "One", "auto_upload_enabled": False}, {"container_code": "env-2", "name": "Two", "auto_upload_enabled": False}]
        runtime.synced_monotonic = self.agent.time.monotonic()
        with patch.object(self.agent, "save_config") as save:
            await runtime.toggle_environment("env-1", True, True)
            await runtime.toggle_environment("env-2", True, True)
            self.assertEqual([e["auto_upload_enabled"] for e in runtime.state["environments"]], [False, True])
            self.assertEqual(save.call_args.args[0], {"auto_upload_container_code": "env-2"})
            runtime.current_claim = {"task": {"id": 1}}
            with self.assertRaises(self.agent.ERPRequestError): await runtime.toggle_environment("env-1", True, True)
            runtime.current_claim = None
            runtime.synced_monotonic -= 301
            with self.assertRaises(self.agent.ERPRequestError): await runtime.toggle_environment("env-1", True, True)

    async def test_runtime_claim_uses_local_selection(self):
        runtime = self.agent.AgentRuntime({})
        runtime.state["environments"] = [{"container_code": "chosen", "name": "Chosen environment", "auto_upload_enabled": True}]
        runtime.synced_monotonic = self.agent.time.monotonic()
        client = MagicMock(); client.request = AsyncMock(return_value={"user": {"id": 1, "name": "User"}})
        async def claim(path, **kwargs):
            runtime.state["stop"] = True
            return {"task": None}
        client.post = AsyncMock(side_effect=claim)
        runtime.workbench.start = AsyncMock(); runtime.workbench.close = AsyncMock()
        runtime.heartbeat_loop = AsyncMock(); runtime.sync_loop = AsyncMock()
        with patch.object(self.agent.keyring, "get_password", return_value="token"), patch.object(self.agent, "ERPClient", return_value=client), \
             patch.object(self.agent.webbrowser, "open"), patch.object(self.agent, "POLL_SECONDS", 0):
            await runtime.run()
        client.post.assert_awaited_once_with("/hub-agent/claim", json={"container_code": "chosen", "environment_name": "Chosen environment", "confirmed_local": True})


if __name__ == "__main__": unittest.main()
