"""跨平台 HubStudio 本地执行器。

以当前登录用户运行；不以 Windows Service 运行，因为 HubStudio 浏览器属于该用户桌面会话。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import time
from contextlib import suppress
import platform
import socket
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

import httpx
import keyring
from hubstudio import HubstudioClient
from workbench import LocalStatusServer, ERPRequestError
from runtime_settings import validate_erp_url, debug_scope
from local_auth import authorize_computer
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

SERVICE_NAME = "haitoo-hub-agent"
TOKEN_KEY = "agent-token"
if platform.system() == "Darwin":
    APP_SUPPORT_PATH = Path.home() / "Library" / "Application Support" / "HaitooHubAgent"
    LOG_DIRECTORY = Path.home() / "Library" / "Logs" / "HaitooHubAgent"
else:
    APP_SUPPORT_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "HaitooHubAgent"
    LOG_DIRECTORY = APP_SUPPORT_PATH
if os.environ.get("HAITOO_AGENT_DATA_DIR"):
    APP_SUPPORT_PATH = LOG_DIRECTORY = Path(os.environ["HAITOO_AGENT_DATA_DIR"])
CONFIG_PATH = APP_SUPPORT_PATH / "config.json"
LOG_PATH = LOG_DIRECTORY / "agent.log"
POLL_SECONDS = 5
# API 仅用于执行器与服务器通信；PORTAL_URL 仅用于员工在浏览器登录 ERP。
LOCAL_DEBUG = os.environ.get("HAITOO_LOCAL_DEBUG") == "1"
API_URL = validate_erp_url(os.environ.get("HAITOO_API_URL", "https://api.haitorok.com"), local_debug=LOCAL_DEBUG)
PORTAL_URL = validate_erp_url(os.environ.get("HAITOO_PORTAL_URL", "https://erp.haitorok.com"), local_debug=LOCAL_DEBUG)
if LOCAL_DEBUG:
    # 测试库的授权不能覆盖正式库的钥匙串凭证或配置。
    scope = debug_scope(API_URL)
    SERVICE_NAME += "-" + scope
    if not os.environ.get("HAITOO_AGENT_DATA_DIR"):
        APP_SUPPORT_PATH = APP_SUPPORT_PATH / scope
        LOG_DIRECTORY = LOG_DIRECTORY / scope
        CONFIG_PATH = APP_SUPPORT_PATH / "config.json"
        LOG_PATH = LOG_DIRECTORY / "agent.log"
STATUS_HOST = "127.0.0.1"
STATUS_PORT = 45679

APP_SUPPORT_PATH.mkdir(parents=True, exist_ok=True)
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
# HTTP 默认信息日志会包含领取凭证查询串，禁止写入本机可见日志。
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def enable_console_logging() -> None:
    """仅在 .command 排错入口输出日志，日常托盘启动保持安静。"""
    root_logger = logging.getLogger()
    if any(isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout for handler in root_logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    # 部署环境显式指定 API 时覆盖旧配置，便于同一执行器包连接腾讯云域名。
    if os.environ.get("HAITOO_API_URL"):
        config["erp_url"] = API_URL
    # 旧版本把前端域名误用为 API 地址；无须用户删除配置即可自动修正。
    if config.get("erp_url") == PORTAL_URL:
        config["erp_url"] = API_URL
        save_config(config)
    if config.get("erp_url"):
        config["erp_url"] = validate_erp_url(config["erp_url"], local_debug=LOCAL_DEBUG)
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2))


class ERPClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = validate_erp_url(base_url, local_debug=LOCAL_DEBUG)
        self.headers = {"X-Hub-Agent-Token": token, "X-Hub-Protocol": "3"}

    async def request(self, method, path, **kwargs):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, self.base_url + path, headers=self.headers, **kwargs)
            if response.is_error:
                try:
                    message = response.json().get("detail")
                except ValueError:
                    message = None
                raise ERPRequestError(response.status_code, message if isinstance(message, str) else "ERP 请求失败，请检查连接和版本")
            return response.json()

    async def post(self, path, **kwargs):
        return await self.request("POST", path, **kwargs)

    async def download(self, task_id, claim_token, destination):
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(f"{self.base_url}/hub-agent/tasks/{task_id}/file", headers=self.headers, params={"claim_token": claim_token})
            if response.is_error:
                raise ERPRequestError(response.status_code, "任务文件下载失败或领取已失效")
            destination.write_bytes(response.content)

    async def report(self, task_id, claim_token, status, stage, message=None):
        return await self.post(f"/hub-agent/tasks/{task_id}/report", params={"claim_token": claim_token}, json={"status": status, "stage": stage, "message": message})


async def upload_and_submit(debug_port: int, xlsx_path: Path, before_submit=None) -> None:
    """明确控件与提交成功提示；未知页面或结果交由人工核对。"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
        try:
            if not browser.contexts:
                raise RuntimeError("HubStudio 浏览器没有可用上下文")
            context = browser.contexts[0]
            page = await context.new_page()
            await page.goto("https://seller.tiktokglobalshop.com/products/bulk-upload", wait_until="domcontentloaded")
            if "login" in page.url.lower() or await page.get_by_text(re.compile(r"^Log in$", re.I)).count():
                raise RuntimeError("TikTok 登录已失效，请在 HubStudio 环境中重新登录")
            file_input = page.locator("input[type=file]")
            await file_input.wait_for(state="attached", timeout=30_000)
            if await file_input.count() != 1 or not await file_input.is_enabled():
                raise RuntimeError("无法唯一识别可用的 TikTok 批量上传控件")
            await file_input.set_input_files(str(xlsx_path))
            submit = page.get_by_role("button", name=re.compile(r"^(submit|提交|publish|发布)$", re.I))
            await submit.wait_for(state="visible", timeout=45_000)
            if await submit.count() != 1 or not await submit.is_enabled():
                raise RuntimeError("提交按钮不唯一或尚不可用，请核对文件校验结果")
            # 先持久化将要点击提交的阶段，网络失败时不执行点击。
            if before_submit:
                await before_submit()
            success = page.get_by_text(re.compile(r"^(submitted successfully|successfully submitted|upload successful|uploaded successfully|提交成功|上传成功)[.!。！]?$", re.I))
            if await success.count():
                raise RuntimeError("页面已有成功提示，无法确认它属于本次提交")
            await submit.click()
            await success.wait_for(state="visible", timeout=60_000)
            errors = page.get_by_role("alert").filter(has_text=re.compile(r"error|failed|invalid|失败|错误", re.I))
            if await errors.count() and await errors.first.is_visible():
                raise RuntimeError("平台同时返回错误，请人工核对本次提交结果")
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("未识别到明确的控件或本次提交成功结果，请核对 TikTok 页面") from exc
        finally:
            # CDP 关闭连接，不调用 HubStudio 的关闭环境接口，保留页面供人工核对。
            await browser.close()


class AgentRuntime:
    def __init__(self, config):
        self.config = config
        self.state = {"status": "正在启动", "paused": False, "stop": False, "environments": [],
                      "user": None, "erp_connected": False, "hub_connected": False, "sync_at": None, "sync_error": None, "login_required": True}
        self.client = None
        self.current_claim = None
        self.execution = None
        self.last_heartbeat = time.monotonic()
        self.sync_lock = asyncio.Lock()
        self.auth_lock = asyncio.Lock()
        self.selection_lock = asyncio.Lock()
        self.synced_monotonic = None
        self.last_sync_attempt = 0
        self.workbench = LocalStatusServer(self.state, lambda: self.client, self.sync, LOG_PATH, login_callback=self.login, toggle_callback=self.toggle_environment)

    async def toggle_environment(self, code, enabled, confirmed_local):
        async with self.selection_lock:
            if self.current_claim or (self.execution and not self.execution.done()):
                raise ERPRequestError(409, "任务执行中，不能更改自动上品环境")
            if self.synced_monotonic is None or time.monotonic() - self.synced_monotonic >= 300:
                raise ERPRequestError(409, "环境同步已过期，请先同步环境")
            environment = next((e for e in self.state["environments"] if e["container_code"] == code), None)
            if not environment:
                raise ERPRequestError(404, "本机当前不可访问此环境")
            if enabled and not confirmed_local:
                raise ERPRequestError(400, "请确认此环境属于 TikTok 店铺")
            selected = code if enabled else self.config.get("auto_upload_container_code")
            if not enabled and selected == code:
                selected = None
            updated = self.config | {"auto_upload_container_code": selected}
            save_config(updated)
            self.config = updated
            for env in self.state["environments"]:
                env["auto_upload_enabled"] = env["container_code"] == selected
            return dict(environment)

    async def login(self, email, password):
        async with self.auth_lock:
            if self.client or self.current_claim:
                raise ERPRequestError(409, "当前电脑已授权，请先退出执行器后再处理账号授权")
            token = await authorize_computer(API_URL, email, password)
            client = ERPClient(API_URL, token)
            config = await client.request("GET", "/hub-agent/config")
            keyring.set_password(SERVICE_NAME, TOKEN_KEY, token)
            self.config["erp_url"] = API_URL
            save_config(self.config)
            self.state.update(user=config["user"], login_required=False, erp_connected=True, status="已登录，准备同步环境")
            self.client = client
            logger.info("本机工作页已完成电脑授权")

    def require_login(self):
        self.client = None
        self.synced_monotonic = None
        self.state.update(user=None, login_required=True, erp_connected=False, hub_connected=False,
                          environments=[], sync_at=None, sync_error=None, status="请在本地工作页登录 ERP 账号")

    async def sync(self):
        async with self.sync_lock:
            self.last_sync_attempt = time.monotonic()
            try:
                config = await self.client.request("GET", "/hub-agent/config")
                self.state["user"] = config["user"]
                self.state["erp_connected"] = True
                if config.get("configured") is False:
                    raise RuntimeError("请联系管理员配置 HubStudio API")
                # Local API 使用当前客户端登录态，不通过公司凭据切换用户/团队。
                items = await HubstudioClient(self.config.get("hubstudio_url", "http://127.0.0.1:6873")).environments()
                self.state["hub_connected"] = True
                selected = self.config.get("auto_upload_container_code")
                self.state["environments"] = [e | {"id": e["container_code"], "auto_upload_enabled": e["container_code"] == selected} for e in items]
                self.state["sync_at"], self.state["sync_error"] = int(time.time() * 1000), None
                self.synced_monotonic = time.monotonic()
            except Exception as exc:
                self.state["sync_error"] = str(exc) if isinstance(exc, (ERPRequestError, RuntimeError)) else "同步失败，请检查 ERP 和 HubStudio Local API 连接"
                self.state["hub_connected"] = False
                logger.error("环境同步失败（保留上次完整快照）")

    async def execute(self, claim):
        task, token = claim["task"], claim["claim_token"]
        task_id = task["id"]
        try:
            self.state["status"] = f"任务 #{task_id}：正在启动环境"
            await self.client.report(task_id, token, "running", "starting_environment", "正在启动 HubStudio 环境")
            hub = HubstudioClient(self.config.get("hubstudio_url", "http://127.0.0.1:6873"))
            port = await hub.start(claim["hubstudio"]["container_code"])
            with tempfile.TemporaryDirectory(prefix="haitoo-hub-") as directory:
                file_path = Path(directory) / Path(task["export_filename"]).name
                await self.client.download(task_id, token, file_path)
                self.state["status"] = f"任务 #{task_id}：正在上传 XLSX"
                await self.client.report(task_id, token, "running", "uploading", "正在上传 TikTok XLSX")
                async def before_submit():
                    self.state["status"] = f"任务 #{task_id}：正在提交"
                    await self.client.report(task_id, token, "running", "submitting", "准备点击提交；之后结果不明确时必须人工核对")
                await upload_and_submit(port, file_path, before_submit)
            await self.client.report(task_id, token, "completed", "submitted", "TikTok 已明确接受批量提交；不代表商品已上架")
            self.state["status"] = f"任务 #{task_id}：已提交"
        except asyncio.CancelledError:
            self.state["status"] = f"任务 #{task_id}：连接或领取失效，请人工核对"
            raise
        except Exception as exc:
            message = str(exc)[:500] if isinstance(exc, (RuntimeError, ERPRequestError)) else "执行失败，提交结果未知，请核对 TikTok 页面"
            logger.error("任务 #%s 需要人工处理：%s", task_id, message)
            try:
                await self.client.report(task_id, token, "awaiting_attention", "manual_attention", message)
            except Exception:
                logger.error("任务 #%s 异常报告未送达；等待租约超时后人工核对", task_id)
            self.state["status"] = f"任务 #{task_id}：需要人工处理"

    async def heartbeat_loop(self):
        while not self.state["stop"]:
            if not self.client:
                await asyncio.sleep(1)
                continue
            try:
                params = {}
                claim = self.current_claim
                if claim and self.execution and not self.execution.done():
                    params = {"task_id": claim["task"]["id"], "claim_token": claim["claim_token"]}
                await self.client.post("/hub-agent/heartbeat", params=params)
                self.last_heartbeat = time.monotonic()
                self.state["erp_connected"] = True
            except Exception as exc:
                self.state["erp_connected"] = False
                revoked = isinstance(exc, ERPRequestError) and exc.status in {401, 409, 426}
                if self.execution and not self.execution.done() and (revoked or time.monotonic() - self.last_heartbeat >= 60):
                    self.execution.cancel()
                if isinstance(exc, ERPRequestError) and exc.status == 401:
                    self.state["login_required"] = True
                logger.error("ERP 心跳失败，正在重试")
            await asyncio.sleep(15)

    async def sync_loop(self):
        while not self.state["stop"]:
            if self.client and not self.state["login_required"] and time.monotonic() - self.last_sync_attempt >= 60:
                await self.sync()
            await asyncio.sleep(5)

    async def run(self):
        await self.workbench.start()
        webbrowser.open(f"http://{STATUS_HOST}:{STATUS_PORT}")
        background = []
        try:
            async with self.auth_lock:
                token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
                if token:
                    client = ERPClient(self.config.get("erp_url", API_URL), token)
                    try:
                        config = await client.request("GET", "/hub-agent/config")
                    except ERPRequestError as exc:
                        if exc.status != 401:
                            self.client = client
                            self.state.update(login_required=False, status="等待 ERP 连接恢复")
                    except Exception:
                        self.client = client
                        self.state.update(login_required=False, status="等待 ERP 连接恢复")
                    else:
                        self.client = client
                        self.state.update(user=config["user"], login_required=False, erp_connected=True)
                if not self.client:
                    self.require_login()
            background = [asyncio.create_task(self.heartbeat_loop()), asyncio.create_task(self.sync_loop())]
            while not self.state["stop"]:
                if self.state["login_required"]:
                    if self.client:
                        self.require_login()
                    await asyncio.sleep(1)
                    continue
                fresh = self.synced_monotonic is not None and time.monotonic() - self.synced_monotonic < 300
                if self.state["paused"]:
                    self.state["status"] = "已暂停领取"
                elif fresh:
                    try:
                        async with self.selection_lock:
                            selected = next((e for e in self.state["environments"] if e["auto_upload_enabled"]), None)
                            claim = await self.client.post("/hub-agent/claim", json={"container_code": selected["container_code"], "environment_name": selected["name"], "confirmed_local": True}) if selected else {"task": None}
                            if claim.get("task"):
                                self.current_claim = claim
                        if claim.get("task"):
                            self.last_heartbeat = time.monotonic()
                            self.execution = asyncio.create_task(self.execute(claim))
                            try:
                                await self.execution
                            except asyncio.CancelledError:
                                if asyncio.current_task().cancelling():
                                    raise
                                if self.state["stop"]:
                                    break
                            finally:
                                self.current_claim, self.execution = None, None
                        else:
                            self.state["status"] = "在线，等待任务" if selected else "请选择一个本机环境开启自动上品"
                    except Exception as exc:
                        self.state["status"] = "连接失败，正在重试"
                        self.state["erp_connected"] = False
                        if isinstance(exc, ERPRequestError) and exc.status == 401:
                            self.state["login_required"] = True
                        logger.error("任务领取失败，正在重试")
                else:
                    self.state["status"] = "等待成功同步环境"
                await asyncio.sleep(POLL_SECONDS)
        except Exception as exc:
            self.state["status"] = str(exc) if isinstance(exc, RuntimeError) else "启动失败，请检查连接并重新启动"
            logger.error("本地执行器启动失败")
            # 保留工作页和错误状态，便于查看，不因暂时连接错误关闭窗口。
            while not self.state["stop"]:
                await asyncio.sleep(1)
        finally:
            for task in background:
                task.cancel()
            for task in background:
                with suppress(asyncio.CancelledError):
                    await task
            await self.workbench.close()


async def run_forever(config):
    await AgentRuntime(config).run()


async def pair_with_erp() -> None:
    """通过 ERP 网页的现有账号完成终端授权，无需人工复制 Token。"""
    platform_name = "macos" if platform.system() == "Darwin" else "windows"
    name = f"{socket.gethostname()[:100]} · {secrets.token_hex(6)}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API_URL + "/hub-agent/pairings", json={"name": name, "platform": platform_name})
        if response.status_code == 404:
            raise RuntimeError(
                "ERP 服务器尚未部署 Hub 执行器配对接口（/hub-agent/pairings）。"
                "请先发布 ERP 后端并执行数据库迁移到 20261007_30；这不是账号授权失败。"
            )
        response.raise_for_status(); code = response.json()["code"]
    webbrowser.open(f"{PORTAL_URL}/?hub_agent_pair={code}")
    for _ in range(120):
        await asyncio.sleep(5)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{API_URL}/hub-agent/pairings/{code}")
        if response.status_code == 404:
            raise RuntimeError("配对已过期，请重新打开本地执行器")
        response.raise_for_status(); result = response.json()
        if result["status"] == "completed":
            keyring.set_password(SERVICE_NAME, TOKEN_KEY, result["agent_token"])
            save_config({"erp_url": API_URL, "hubstudio_url": "http://127.0.0.1:6873"})
            logger.info("终端已通过 ERP 网页授权 | name=%s", name)
            return

    raise RuntimeError("配对超时，请重新启动执行器")


def run_tray(config):
    import pystray
    from PIL import Image, ImageDraw
    runtime = AgentRuntime(config)
    loop = asyncio.new_event_loop()
    def worker():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(runtime.run())
        except OSError:
            logger.error("本机工作页端口被占用，请打开已有工作页")
    def toggle(icon, _):
        loop.call_soon_threadsafe(lambda: runtime.state.__setitem__("paused", not runtime.state["paused"]))
    def quit_app(icon, _):
        def stop():
            runtime.state["stop"] = True
            if runtime.execution:
                runtime.execution.cancel()
        loop.call_soon_threadsafe(stop)
        icon.stop()
    image = Image.new("RGB", (64, 64), "#4d46a5")
    ImageDraw.Draw(image).ellipse((18, 18, 46, 46), fill="white")
    menu = pystray.Menu(pystray.MenuItem(lambda _: runtime.state["status"], None, enabled=False),
        pystray.MenuItem("打开工作页", lambda *_: webbrowser.open(f"http://{STATUS_HOST}:{STATUS_PORT}")),
        pystray.MenuItem("暂停 / 继续", toggle), pystray.MenuItem("退出", quit_app))
    threading.Thread(target=worker, daemon=True).start()
    pystray.Icon("HaitooHubAgent", image, "Haitoo Hub 执行器", menu).run()


async def run_console(config):
    enable_console_logging()
    print(f"Haitoo Hub 工作页：http://{STATUS_HOST}:{STATUS_PORT}")
    print("关闭此终端窗口 = 停止执行器。")
    try:
        await AgentRuntime(config).run()
    except OSError as exc:
        logger.error("本机工作页端口 %s 无法启动，请检查是否已有执行器运行", STATUS_PORT)
        raise RuntimeError("本机工作页启动失败") from exc


async def register(args) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(args.erp_url.rstrip("/") + "/hub-agents/register", headers={"Authorization": f"Bearer {args.user_token}"}, json={"name": args.name, "platform": "macos" if platform.system() == "Darwin" else "windows"})
        response.raise_for_status(); result = response.json()
    keyring.set_password(SERVICE_NAME, TOKEN_KEY, result["agent_token"])
    save_config({"erp_url": args.erp_url.rstrip("/"), "hubstudio_url": args.hubstudio_url})
    print(f"终端已注册：{result['agent']['name']}（令牌已保存至系统凭据库）")


def main() -> None:
    parser = argparse.ArgumentParser(description="Haitoo HubStudio 本地执行器")
    commands = parser.add_subparsers(dest="command")
    register_parser = commands.add_parser("register")
    register_parser.add_argument("--erp-url", required=True); register_parser.add_argument("--user-token", required=True)
    register_parser.add_argument("--name", required=True); register_parser.add_argument("--hubstudio-url", default="http://127.0.0.1:6873")
    commands.add_parser("run"); commands.add_parser("tray"); commands.add_parser("pair"); commands.add_parser("console")
    args = parser.parse_args()
    if args.command == "register":
        asyncio.run(register(args))
    elif args.command == "pair":
        asyncio.run(pair_with_erp())
    elif args.command == "run":
        asyncio.run(run_forever(load_config()))
    elif args.command == "console":
        try:
            asyncio.run(run_console(load_config()))
        except Exception:
            # 错误已由控制台模式用中文说明并写入日志；避免 PyInstaller 再输出一份 Python 堆栈。
            sys.exit(1)
    else:
        # Finder 双击不会传递参数；默认进入托盘，未注册时显示“未注册”状态。
        run_tray(load_config())


if __name__ == "__main__":
    main()
