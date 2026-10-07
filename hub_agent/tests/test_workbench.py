import asyncio
import importlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp.test_utils import TestClient, TestServer
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hubstudio import HubstudioClient
from workbench import LocalStatusServer


class HubstudioClientTests(unittest.IsolatedAsyncioTestCase):
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
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
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

    def controls(self, count=1, success=True):
        file_input = AsyncMock(); file_input.count.return_value = count; file_input.is_enabled.return_value = True
        submit = AsyncMock(); submit.count.return_value = 1; submit.is_enabled.return_value = True
        success_control = AsyncMock(); success_control.count.return_value = 0
        if not success: success_control.wait_for.side_effect = self.agent.PlaywrightTimeoutError("unknown result")
        login = AsyncMock(); login.count.return_value = 0
        errors = AsyncMock(); errors.count.return_value = 0
        page = MagicMock(); page.url = "https://seller.tiktokglobalshop.com/products/bulk-upload"; page.goto = AsyncMock(); page.locator.return_value = file_input
        page.get_by_text.side_effect = [login, success_control]
        alert = MagicMock(); alert.filter.return_value = errors
        page.get_by_role.side_effect = [submit, alert]
        context = MagicMock(); context.new_page = AsyncMock(return_value=page)
        browser = MagicMock(); browser.contexts = [context]; browser.close = AsyncMock()
        playwright = MagicMock(); playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        manager = MagicMock(); manager.__aenter__ = AsyncMock(return_value=playwright); manager.__aexit__ = AsyncMock(return_value=False)
        return manager, submit, file_input, page

    async def test_explicit_success_and_regex(self):
        manager, submit, file_input, page = self.controls()
        before_submit = AsyncMock()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            await self.agent.upload_and_submit(1234, Path("test.xlsx"), before_submit)
        before_submit.assert_awaited_once(); submit.click.assert_awaited_once(); file_input.set_input_files.assert_awaited_once()
        self.assertIsInstance(page.get_by_role.call_args_list[0].kwargs["name"], re.Pattern)

    async def test_unknown_result_never_counts_as_completed(self):
        manager, submit, _, _ = self.controls(success=False)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "明确"): await self.agent.upload_and_submit(1234, Path("test.xlsx"))
        submit.click.assert_awaited_once()

    async def test_ambiguous_upload_control_does_not_click(self):
        manager, submit, _, _ = self.controls(count=2)
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "唯一"): await self.agent.upload_and_submit(1234, Path("test.xlsx"))
        submit.click.assert_not_awaited()

    async def test_failed_pre_submit_report_prevents_click(self):
        manager, submit, _, _ = self.controls()
        with patch.object(self.agent, "async_playwright", return_value=manager):
            with self.assertRaises(RuntimeError): await self.agent.upload_and_submit(1234, Path("test.xlsx"), AsyncMock(side_effect=RuntimeError("offline")))
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
