"""跨平台 HubStudio 本地执行器。

以当前登录用户运行；不以 Windows Service 运行，因为 HubStudio 浏览器属于该用户桌面会话。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import socket
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Callable

import httpx
import keyring
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

SERVICE_NAME = "haitoo-hub-agent"
TOKEN_KEY = "agent-token"
if platform.system() == "Darwin":
    APP_SUPPORT_PATH = Path.home() / "Library" / "Application Support" / "HaitooHubAgent"
    LOG_DIRECTORY = Path.home() / "Library" / "Logs" / "HaitooHubAgent"
else:
    APP_SUPPORT_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "HaitooHubAgent"
    LOG_DIRECTORY = APP_SUPPORT_PATH
CONFIG_PATH = APP_SUPPORT_PATH / "config.json"
LOG_PATH = LOG_DIRECTORY / "agent.log"
POLL_SECONDS = 5
# API 仅用于执行器与服务器通信；PORTAL_URL 仅用于员工在浏览器登录 ERP。
API_URL = os.environ.get("HAITOO_API_URL", "https://api.haitoro.com").strip().rstrip("/")
PORTAL_URL = os.environ.get("HAITOO_PORTAL_URL", "https://erp.haitoro.com").strip().rstrip("/")
if not API_URL.startswith("https://") or not PORTAL_URL.startswith("https://"):
    raise RuntimeError("HAITOO_API_URL 和 HAITOO_PORTAL_URL 必须使用 https:// 地址")
STATUS_HOST = "127.0.0.1"
STATUS_PORT = 45679

APP_SUPPORT_PATH.mkdir(parents=True, exist_ok=True)
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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


class LocalStatusServer:
    """仅供本机查看的最小状态页，不提供控制接口，也不监听局域网。"""

    def __init__(self, state: dict):
        self.state = state
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, STATUS_HOST, STATUS_PORT)
        logger.info("本机状态页已启动：http://%s:%s", STATUS_HOST, STATUS_PORT)

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1", "replace")
            path = request.split(" ", 2)[1] if request else "/"
            payload = {
                "status": self.state.get("status", "正在启动"),
                "paused": bool(self.state.get("paused")),
                "erp_url": self.state.get("erp_url", API_URL),
                "portal_url": self.state.get("portal_url", PORTAL_URL),
                "hubstudio_url": self.state.get("hubstudio_url", "http://127.0.0.1:6873"),
                "log_path": str(LOG_PATH),
            }
            if path == "/health":
                body, content_type = json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8"
            else:
                body = ("<!doctype html><meta charset=utf-8><title>Haitoo Hub 执行器</title>"
                        "<style>body{font:16px -apple-system,sans-serif;max-width:680px;margin:48px auto;color:#202124}"
                        "code{background:#f4f4f5;padding:3px 6px;border-radius:4px}</style>"
                        "<h1>Haitoo Hub 执行器</h1>"
                        f"<p>状态：<strong>{payload['status']}</strong></p>"
                        f"<p>ERP 登录页：<code>{payload['portal_url']}</code></p>"
                        f"<p>ERP API：<code>{payload['erp_url']}</code></p>"
                        f"<p>HubStudio：<code>{payload['hubstudio_url']}</code></p>"
                        f"<p>日志：<code>{payload['log_path']}</code></p>"
                        "<p>此页面仅监听本机，不能从局域网访问。</p>").encode()
                content_type = "text/html; charset=utf-8"
            writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
            await writer.drain()
        except (asyncio.IncompleteReadError, IndexError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()


def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    # 部署环境显式指定 API 时覆盖旧配置，便于同一执行器包连接腾讯云域名。
    if os.environ.get("HAITOO_API_URL"):
        config["erp_url"] = API_URL
    # 旧版本把前端域名误用为 API 地址；无须用户删除配置即可自动修正。
    if config.get("erp_url") == PORTAL_URL:
        config["erp_url"] = API_URL
        save_config(config)
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2))


class ERPClient:
    def __init__(self, base_url: str, token: str):
        self.base_url, self.headers = base_url.rstrip("/"), {"X-Hub-Agent-Token": token}

    async def post(self, path: str, **kwargs):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.base_url + path, headers=self.headers, **kwargs)
            response.raise_for_status()
            return response.json()

    async def claim(self) -> dict | None:
        return await self.post("/hub-agent/claim")

    async def download(self, task_id: int, claim_token: str, destination: Path) -> None:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(f"{self.base_url}/hub-agent/tasks/{task_id}/file", headers=self.headers, params={"claim_token": claim_token})
            response.raise_for_status(); destination.write_bytes(response.content)

    async def report(self, task_id: int, claim_token: str, status: str, stage: str, message: str | None = None) -> None:
        await self.post(f"/hub-agent/tasks/{task_id}/report", params={"claim_token": claim_token}, json={"status": status, "stage": stage, "message": message})


class HubstudioClient:
    def __init__(self, endpoint: str, credentials: dict):
        self.endpoint, self.credentials = endpoint.rstrip("/"), credentials

    async def start(self) -> int:
        # 兼容 HubStudio 本地 API 的常见鉴权字段；生产验证时以当前 Hub 文档的字段为准。
        body = {"containerCode": self.credentials["container_code"], "groupCode": self.credentials["group_code"],
                "appId": self.credentials["app_id"], "appSecret": self.credentials["app_secret"], "shouldCloseTabsOnOpen": "true"}
        headers = {"App-Id": self.credentials["app_id"], "App-Secret": self.credentials["app_secret"]}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self.endpoint + "/api/v1/browser/start", json=body, headers=headers)
            response.raise_for_status(); payload = response.json()
        data = payload.get("data") or {}
        port = data.get("debuggingPort")
        if payload.get("code") not in (0, "0") or not port:
            raise RuntimeError(payload.get("msg") or data.get("err") or "HubStudio 未返回 debuggingPort")
        return int(port)


async def upload_and_submit(debug_port: int, xlsx_path: Path) -> None:
    """只在明确识别到批量上传与提交控件后才提交，未知页面交由人工处理。"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://seller.tiktokglobalshop.com/products/bulk-upload", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        if "login" in page.url.lower() or await page.get_by_text("Log in", exact=False).count():
            raise RuntimeError("TikTok 登录已失效，请在已打开的 HubStudio 环境中重新登录")
        file_input = page.locator("input[type=file]")
        if await file_input.count() == 0:
            raise RuntimeError("未识别到 TikTok 批量上传文件控件，请人工检查页面")
        await file_input.first.set_input_files(str(xlsx_path))
        # TikTok 页面文案可能随站点语言变化；未找到确定的提交动作绝不猜测点击。
        submit = page.get_by_role("button", name=r"(?i)submit|提交|publish|发布")
        try:
            await submit.first.wait_for(state="visible", timeout=45_000)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("文件已上传，但未检测到可提交按钮，请人工核对校验结果") from exc
        await submit.first.click()
        await page.wait_for_timeout(2000)
        if await page.get_by_text(r"(?i)error|失败|invalid", exact=False).count():
            raise RuntimeError("TikTok 返回上传或提交错误，请在浏览器中核对")
        await browser.close()


async def run_once(client: ERPClient, hubstudio_url: str, on_status: Callable[[str], None] | None = None) -> bool:
    def set_status(message: str) -> None:
        if on_status:
            on_status(message)

    set_status("正在检查 ERP 任务")
    await client.post("/hub-agent/heartbeat")
    # 领取只能调用一次：避免第一个任务已被置为 running 后又领取第二个任务。
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(client.base_url + "/hub-agent/claim", headers=client.headers); response.raise_for_status(); claim = response.json()
    if not claim.get("task"):
        set_status("在线，等待任务")
        return False
    task, claim_token = claim["task"], claim["claim_token"]
    task_id = task["id"]
    try:
        set_status(f"任务 #{task_id}：正在启动 HubStudio 环境")
        await client.report(task_id, claim_token, "running", "starting_environment", "正在启动 HubStudio 环境")
        port = await HubstudioClient(hubstudio_url, claim["hubstudio"]).start()
        with tempfile.TemporaryDirectory(prefix="haitoo-hub-") as directory:
            file_path = Path(directory) / task["export_filename"]
            await client.download(task_id, claim_token, file_path)
            set_status(f"任务 #{task_id}：正在上传 TikTok XLSX")
            await client.report(task_id, claim_token, "running", "uploading", "正在上传 TikTok XLSX")
            await upload_and_submit(port, file_path)
        await client.report(task_id, claim_token, "completed", "submitted", "TikTok 批量上传已提交")
        set_status(f"任务 #{task_id}：已提交，等待下一项任务")
    except Exception as exc:
        logger.exception("Hub 上品任务失败: %s", task_id)
        await client.report(task_id, claim_token, "awaiting_attention", "manual_attention", str(exc)[:500])
        set_status(f"任务 #{task_id}：需要人工处理")
    return True


async def run_forever(config: dict) -> None:
    token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if not token:
        raise RuntimeError("尚未注册终端，请先运行 register")
    client = ERPClient(config["erp_url"], token)
    while True:
        try:
            await run_once(client, config.get("hubstudio_url", "http://127.0.0.1:6873"))
        except Exception:
            logger.exception("轮询失败")
        await asyncio.sleep(POLL_SECONDS)


async def pair_with_erp() -> None:
    """通过 ERP 网页的现有账号完成终端授权，无需人工复制 Token。"""
    platform_name = "macos" if platform.system() == "Darwin" else "windows"
    name = socket.gethostname()[:120]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API_URL + "/hub-agent/pairings", json={"name": name, "platform": platform_name})
        if response.status_code == 404:
            raise RuntimeError(
                "ERP 服务器尚未部署 Hub 执行器配对接口（/hub-agent/pairings）。"
                "请先发布 ERP 后端并执行数据库迁移到 20260917_08；这不是账号授权失败。"
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


def run_tray(config: dict) -> None:
    """当前用户会话的最小托盘界面；Windows Service 不会调用此入口。"""
    import pystray
    from PIL import Image, ImageDraw

    state = {"status": "正在启动", "paused": False, "stop": False,
             "erp_url": config.get("erp_url", API_URL), "portal_url": PORTAL_URL,
             "hubstudio_url": config.get("hubstudio_url", "http://127.0.0.1:6873")}

    async def worker() -> None:
        token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
        if not token:
            state["status"] = "请在打开的 ERP 页面登录"
            try:
                await pair_with_erp()
                token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
                state["status"] = "已授权，正在连接"
            except Exception as exc:
                logger.exception("ERP 配对失败"); state["status"] = f"配对失败：{exc}"; return
        client = ERPClient(config["erp_url"], token)
        while not state["stop"]:
            if state["paused"]:
                state["status"] = "已暂停"; await asyncio.sleep(1); continue
            try:
                state["status"] = "在线，等待任务"
                if await run_once(client, config.get("hubstudio_url", "http://127.0.0.1:6873"), lambda message: state.__setitem__("status", message)):
                    state["status"] = "已完成一项任务"
            except Exception:
                logger.exception("托盘执行器轮询失败"); state["status"] = "连接失败，正在重试"
            await asyncio.sleep(POLL_SECONDS)

    def thread_main() -> None: asyncio.run(worker())
    image = Image.new("RGB", (64, 64), "#4d46a5"); ImageDraw.Draw(image).ellipse((18, 18, 46, 46), fill="white")
    def toggle(icon, _): state["paused"] = not state["paused"]
    def quit_app(icon, _): state["stop"] = True; icon.stop()
    menu = pystray.Menu(lambda: pystray.MenuItem(lambda _: state["status"], None, enabled=False),
                        pystray.MenuItem("暂停 / 继续", toggle), pystray.MenuItem("退出", quit_app))
    threading.Thread(target=thread_main, daemon=True).start()
    pystray.Icon("HaitooHubAgent", image, "Haitoo Hub 执行器", menu).run()


async def run_console(config: dict) -> None:
    """给未签名 Mac 包的可见终端入口；保留窗口便于员工截图排错。"""
    enable_console_logging()
    state = {"status": "正在启动", "paused": False, "stop": False,
             "erp_url": config.get("erp_url", API_URL), "portal_url": PORTAL_URL,
             "hubstudio_url": config.get("hubstudio_url", "http://127.0.0.1:6873")}
    status_server = LocalStatusServer(state)
    try:
        await status_server.start()
    except OSError as exc:
        raise RuntimeError(f"本机状态页端口 {STATUS_PORT} 无法启动，可能已有执行器正在运行：{exc}") from exc
    print("\nHaitoo Hub 执行器已启动")
    print(f"本机状态页：http://{STATUS_HOST}:{STATUS_PORT}")
    print("关闭此终端窗口 = 停止执行器。\n")
    try:
        token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
        if not token:
            state["status"] = "请在打开的 ERP 页面登录并授权"
            await pair_with_erp()
            token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
        state["status"] = "在线，等待任务"
        client = ERPClient(config.get("erp_url", API_URL), token)
        while True:
            if await run_once(client, config.get("hubstudio_url", "http://127.0.0.1:6873"), lambda message: state.__setitem__("status", message)):
                state["status"] = "已完成一项任务，等待下一项"
            await asyncio.sleep(POLL_SECONDS)
    except Exception as exc:
        state["status"] = f"启动或连接失败：{exc}"
        logger.error("控制台执行器失败：%s", exc)
        print(f"执行器出错：{exc}")
        raise
    finally:
        await status_server.close()


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
