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
from contextlib import suppress, AsyncExitStack
import platform
import socket
import sys
import subprocess
import tempfile
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import keyring
from hubstudio import HubstudioClient, seller_url
from connector import ConnectorServer, ERPRequestError
from runtime_settings import validate_erp_url, debug_scope
from matrix_runtime import MatrixRuntime
from playwright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

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
STATUS_PORT = 45679

APP_SUPPORT_PATH.mkdir(parents=True, exist_ok=True)
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG_PATH, encoding="utf-8", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
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
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_PATH)


class ERPClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = validate_erp_url(base_url, local_debug=LOCAL_DEBUG)
        self.headers = {"X-Hub-Agent-Token": token, "X-Hub-Protocol": "4"}

    async def request(self, method, path, **kwargs):
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {**self.headers, "X-Hub-Protocol": "5" if path.startswith("/hub-v5/") else "4"}
            response = await client.request(method, self.base_url + path, headers=headers, **kwargs)
            if response.is_error:
                try:
                    message = response.json().get("detail")
                except ValueError:
                    message = None
                raise ERPRequestError(response.status_code, message if isinstance(message, str) else "ERP 请求失败，请检查连接和版本")
            return response.json()

    async def post(self, path, **kwargs):
        return await self.request("POST", path, **kwargs)

    async def matrix_download(self, path, payload, destination, expected_size):
        await self._matrix_stream("POST", path, destination, expected_size, json=payload)

    async def matrix_download_release(self, identity, destination, expected_size):
        await self._matrix_stream("GET", f"/hub-v5/agent/releases/{identity}/file", destination, expected_size)

    async def connector_download_release(self, identity, destination, expected_size, on_progress=None):
        await self._matrix_stream("GET", f"/hub-v5/agent/connector-releases/{identity}/file", destination, expected_size, on_progress=on_progress)

    async def _matrix_stream(self, method, path, destination, expected_size, on_progress=None, **kwargs):
        if not 0 < expected_size <= 250 * 1024 * 1024:
            raise RuntimeError("下载文件超过本机上限")
        temporary = destination.with_suffix(".download")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(method, self.base_url + path, headers={**self.headers, "X-Hub-Protocol": "5"}, **kwargs) as response:
                    if response.is_error:
                        raise ERPRequestError(response.status_code, "固定文件不可用或领取已失效")
                    size = 0
                    with temporary.open("wb") as stream:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > expected_size:
                                raise RuntimeError("下载文件大小不一致")
                            stream.write(chunk)
                            if on_progress:
                                on_progress(size, expected_size)
                    if size != expected_size:
                        raise RuntimeError("下载文件不完整")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    async def download(self, task_id, claim_token, destination):
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(f"{self.base_url}/hub-agent/tasks/{task_id}/file", headers=self.headers, params={"claim_token": claim_token})
            if response.is_error:
                raise ERPRequestError(response.status_code, "任务文件下载失败或领取已失效")
            destination.write_bytes(response.content)

    async def report(self, task_id, claim_token, status, stage, message=None):
        return await self.post(f"/hub-agent/tasks/{task_id}/report", params={"claim_token": claim_token}, json={"status": status, "stage": stage, "message": message})


BULK_UPLOAD_URL = "https://seller-my.tiktok.com/product/batch/publish?entry-from=hub&shop_region=MY&step=2"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LOGIN_WAIT_SECONDS = 600
IMPORT_RECEIPT_PATTERN = re.compile(
    r'^\s*(?:成功导入\s*(\d+(?:,\d{3})*)\s*[款个件](?:商品)?(?:[，,]\s*导入成功)?'
    r'|(\d+(?:,\d{3})*)\s*[款个件](?:商品)?\s*导入成功)\s*[！!。.]?\s*$')


class DuplicateUploadError(RuntimeError):
    pass


class ImportDataError(RuntimeError):
    pass


async def check_import_data_error(page):
    """检查当前页弹窗、可见 iframe 和由当前页打开的独立弹窗。"""
    pages = [page]
    for popup in list(page.context.pages):
        if popup is not page and not popup.is_closed() and await popup.opener() is page:
            pages.append(popup)
    pattern = re.compile(r"出错\s*(?:的\s*)?商品")
    for candidate_page in pages:
        scopes = [candidate_page]
        for frame in candidate_page.frames:
            if frame is candidate_page.main_frame or frame.is_detached():
                continue
            ancestor = frame
            visible = True
            try:
                while ancestor.parent_frame is not None:
                    element = await ancestor.frame_element()
                    try:
                        if not await element.is_visible():
                            visible = False
                            break
                    finally:
                        await element.dispose()
                    ancestor = ancestor.parent_frame
            except PlaywrightError:
                # iframe 在解析或弹窗切换期间可能被移除，下轮重新检查。
                continue
            if visible:
                scopes.append(frame)
        for scope in scopes:
            try:
                error = scope.get_by_text(pattern)
                count = await error.count()
                for index in range(count):
                    control = error if count == 1 else error.nth(index)
                    if await control.is_visible():
                        raise ImportDataError("上传成功，添加商品失败（数据错误）；请人工查看 TikTok 在线编辑器中的出错商品并处理")
            except PlaywrightError:
                if scope is candidate_page:
                    raise
                # iframe 跳转时只跳过本轮，不阻塞主页面检测。
                continue


async def wait_import_result(page, success, check_stop=None):
    """同时等待导入成功或明确的数据错误；结束时清理监控协程。"""
    async def watch_errors():
        while True:
            if check_stop:await check_stop()
            await check_import_data_error(page)
            await asyncio.sleep(0.5)

    await check_import_data_error(page)
    success_wait = asyncio.create_task(success.wait_for(state="visible", timeout=60_000))
    error_wait = asyncio.create_task(watch_errors())
    try:
        done, _ = await asyncio.wait((success_wait, error_wait), return_when=asyncio.FIRST_COMPLETED)
        if error_wait in done:
            await error_wait
        await success_wait
        # 同时出现部分成功和错误时，整项任务按数据错误处理。
        await check_import_data_error(page)
    finally:
        for task in (success_wait, error_wait):
            if not task.done():
                task.cancel()
        await asyncio.gather(success_wait, error_wait, return_exceptions=True)


async def check_duplicate_upload(page):
    duplicate = page.get_by_text(re.compile(r"此文件已存在|文件已存在|(?:this\s+)?file\s+already\s+exists", re.I))
    for index in range(await duplicate.count()):
        if await duplicate.nth(index).is_visible():
            raise DuplicateUploadError("此文件已存在。请上传其他文件或查看上传记录核对已有结果；本次已停止。")


async def wait_upload_control(page, control, timeout, check_stop=None):
    """上传后持续检测重复文件及数据错误，覆盖文件名、就绪提示与导入按钮等待。"""
    deadline = time.monotonic() + timeout / 1000
    while True:
        if check_stop:await check_stop()
        await check_import_data_error(page)
        await check_duplicate_upload(page)
        try:
            await control.wait_for(state="visible", timeout=min(1000, max(1, int((deadline - time.monotonic()) * 1000))))
            await check_import_data_error(page)
            await check_duplicate_upload(page)
            return
        except PlaywrightTimeoutError:
            if time.monotonic() >= deadline:
                await check_import_data_error(page)
                await check_duplicate_upload(page)
                raise


async def open_bulk_upload(page, upload_url=BULK_UPLOAD_URL):
    try:
        await page.goto(upload_url, wait_until="domcontentloaded")
    except PlaywrightError:
        # 登录重定向可能中断 goto；只有明确进入登录地址才交给登录等待。
        if "login" not in page.url.lower():
            raise


async def unique_visible(control):
    """返回唯一可见的匹配项，忽略隐藏的菜单和表单副本。"""
    count = await control.count()
    visible = []
    for index in range(count):
        candidate = control if count == 1 else control.nth(index)
        if await candidate.is_visible():
            visible.append(candidate)
    return visible[0] if len(visible) == 1 else None


async def login_page_language(page):
    """登录页只识别语言，不切换语言。"""
    language = page.get_by_text(re.compile(r"^\s*(简体中文|US English|UK English)\s*$", re.I))
    await language.wait_for(state="visible", timeout=30_000)
    control = await unique_visible(language)
    if control is None:
        raise RuntimeError("无法唯一识别登录页语言，请人工核对；尚未上传")
    text = (await control.inner_text()).strip()
    return "zh" if text == "简体中文" else "en"


async def toggle_account_menu(page):
    """根据顶部右侧账号控件的布局定位，支持不同店铺名称。"""
    handle = await page.evaluate_handle("""() => {
        const candidates = [...document.querySelectorAll('button, [role="button"], a, div, span')]
          .filter(el => {
            const r = el.getBoundingClientRect(), style = getComputedStyle(el);
            const text = (el.innerText || '').trim();
            return r.top >= 0 && r.top < 100 && r.bottom <= 130
              && r.right >= innerWidth - 80 && r.width >= 80 && r.width <= 360
              && r.height >= 24 && r.height <= 96 && text.length > 0 && text.length <= 100
              && style.visibility !== 'hidden' && style.cursor === 'pointer';
          }).sort((a,b) => b.getBoundingClientRect().right-a.getBoundingClientRect().right
                           || a.getBoundingClientRect().width-b.getBoundingClientRect().width);
        return candidates[0] || null;
    }""")
    try:
        control = handle.as_element()
        if control is None:
            raise RuntimeError("未识别到右上角账号菜单入口，请人工打开账号菜单；尚未上传")
        await control.click(timeout=10_000)
    finally:
        await handle.dispose()


LANGUAGE_PATTERN = re.compile(
    r"^\s*(?:简体中文|(?:US |UK )?English(?:\s*\([^)]*\))?|繁體中文|繁体中文|Bahasa Malaysia|Bahasa Melayu|Bahasa Indonesia|ไทย|Tiếng Việt|日本語|한국어|Español|Português|Français|Deutsch)\s*$", re.I)


async def progress(on_progress, stage, message):
    logger.info("[%s] %s", stage, message)
    if on_progress:
        await on_progress(stage, message)


async def account_menu_visible(page):
    # 退出登录行可能同时包含邮箱和主账号说明，不能要求整行完全匹配。
    for marker in (page.get_by_text(LANGUAGE_PATTERN),
                   page.get_by_text(re.compile(r"退出登录|log\s*out|sign\s*out", re.I))):
        count = await marker.count()
        for index in range(count):
            candidate = marker if count == 1 else marker.nth(index)
            if await candidate.is_visible():
                return True
    return False


async def wait_account_menu_hidden(page, timeout):
    deadline = time.monotonic() + timeout
    while await account_menu_visible(page):
        if time.monotonic() >= deadline:
            raise PlaywrightTimeoutError("账号菜单仍然可见")
        await asyncio.sleep(0.2)


async def close_account_menu(page):
    if not await account_menu_visible(page):
        return
    await page.keyboard.press("Escape")
    try:
        await wait_account_menu_hidden(page, 2)
    except PlaywrightTimeoutError:
        # Escape 不受支持时点击账号控件关闭，确认关闭后再继续。
        await toggle_account_menu(page)
        await wait_account_menu_hidden(page, 10)


async def confirm_chinese_after_switch(page, on_progress=None, timeout=30):
    """切换语言后页面可能刷新，菜单丢失时重新打开；总等待时间有上限。"""
    chinese = page.get_by_text(re.compile(r"^\s*简体中文\s*$"))
    attempts = 0
    try:
        async with asyncio.timeout(timeout):
            while True:
                try:
                    if await unique_visible(chinese):
                        return
                    if not await account_menu_visible(page):
                        attempts += 1
                        await progress(on_progress, "verifying_language", f"切换后账号菜单未展开，正在重新打开核对（第 {attempts} 次）")
                        await toggle_account_menu(page)
                    if await unique_visible(chinese):
                        return
                except PlaywrightError:
                    # 刷新期间旧 DOM 或元素句柄可能失效，下轮重新获取。
                    logger.info("[verifying_language] 页面刷新或账号控件暂不可用，继续核对简体中文")
                await asyncio.sleep(1)
    except TimeoutError as exc:
        raise PlaywrightTimeoutError("切换后 30 秒内未能确认账号菜单中的简体中文") from exc


async def ensure_simplified_chinese(page, on_progress=None):
    """确认上传控件显示中文，其他语言通过账号菜单切换。"""
    if not seller_url(page.url):
        raise RuntimeError("当前页面不是 TikTok 卖家网站，无法切换语言；尚未上传")
    step = "打开右上角账号菜单"
    try:
        if urlsplit(page.url).hostname == 'seller.tiktokshopglobalselling.com':
            step = "核对跨境上传页中文控件"
            upload_step = page.get_by_role('button', name=re.compile(r'^\s*第\s*2\s*步\s*[:：]\s*上传电子表格\s*$'))
            attachment = page.get_by_text(UPLOAD_ATTACHMENT_PATTERN)
            if await unique_visible(upload_step) is not None and await unique_visible(attachment) is not None:
                await progress(on_progress, 'language_ready', '已通过“第2步：上传电子表格”和附件上传控件确认页面为简体中文')
                step = "关闭账号菜单"
                await close_account_menu(page)
                await progress(on_progress, 'account_menu_closed', '账号菜单已关闭，语言检查完成，准备上传')
                return
        step = "打开右上角账号菜单"
        await progress(on_progress, "checking_language", "正在打开右上角账号菜单，检查上传页语言；尚未上传")
        if not await account_menu_visible(page):
            await toggle_account_menu(page)
        step = "读取账号菜单当前语言"
        language = page.get_by_text(LANGUAGE_PATTERN)
        await language.wait_for(state="visible", timeout=10_000)
        current = await unique_visible(language)
        if current is None:
            raise RuntimeError("账号菜单语言无法唯一识别")
        current_language = (await current.inner_text()).strip()
        await progress(on_progress, "checking_language", f"账号菜单当前语言：{current_language}")
        if current_language != "简体中文":
            step = "展开语言选项并选择简体中文"
            await progress(on_progress, "switching_language", "正在切换为简体中文；尚未上传")
            await current.click()
            option = page.get_by_text(re.compile(r"^\s*(?:简体中文|中文[（(]简体[）)]|Chinese\s*[（(]Simplified[）)]|Simplified Chinese)\s*$", re.I))
            await option.wait_for(state="visible", timeout=10_000)
            choice = await unique_visible(option)
            if choice is None:
                raise RuntimeError("无法唯一识别简体中文选项")
            await choice.click()
            step = "关闭语言选择菜单"
            await close_account_menu(page)
            # 等待语言切换后的上传页就绪，避免刷新中点击账号控件导致菜单再次关闭。
            step = "等待语言切换后的上传页"
            await page.locator("input[type=file]").wait_for(state="attached", timeout=30_000)
            step = "重新打开账号菜单核对简体中文"
            await progress(on_progress, "verifying_language", "正在核对切换后的语言，最多等待 30 秒；刷新后会重新打开账号菜单")
            await confirm_chinese_after_switch(page, on_progress)
            await progress(on_progress, "language_ready", "语言切换成功，账号菜单已确认简体中文")
        else:
            await progress(on_progress, "language_ready", "上传页语言已是简体中文，无需切换")
        step = "关闭账号菜单"
        await progress(on_progress, "closing_account_menu", "正在关闭账号菜单；尚未上传")
        await close_account_menu(page)
        await progress(on_progress, "account_menu_closed", "账号菜单已关闭，语言检查完成，准备上传")
    except (PlaywrightError, RuntimeError) as exc:
        reason = "超时" if isinstance(exc, PlaywrightTimeoutError) else "失败"
        message = f"语言检查{reason}：{step}；尚未上传，请核对账号菜单和页面"
        await progress(on_progress, "language_failed", message)
        raise RuntimeError(message) from exc


async def attempt_account_login(page, account):
    """仅在明确的卖家登录表单中使用当前环境凭据；失败日志只记录步骤。"""
    def failed(reason):
        logger.warning("TikTok 自动登录未完成：%s；请在当前环境手动登录", reason)
        return False

    if not account.password:
        return failed("环境绑定账号没有可用密码")
    if not seller_url(page.url):
        return failed("当前页面不是 TikTok 卖家网站")
    if "@" not in account.account_name:
        return failed("环境绑定账号不是邮箱")
    step = "识别邮箱登录表单"
    try:
        step = "检查登录页语言"
        language = await login_page_language(page)
        # 登录方式切换时可能保留隐藏表单，只定位可见输入框。
        email = page.locator('input[type="email"]:visible, input[placeholder*="email" i]:visible, input[placeholder*="邮箱"]:visible')
        if await unique_visible(email) is None:
            step = "切换使用邮箱登录"
            email_switch = page.get_by_text(re.compile(r"^\s*(?:使用邮箱登录|邮箱登录)\s*$" if language == "zh" else r"^\s*Log in with email\s*$", re.I))
            switch = await unique_visible(email_switch)
            if switch is None:
                return failed("邮箱输入框与使用邮箱登录入口无法唯一识别")
            await switch.click()
            logger.info("TikTok 已点击使用邮箱登录，等待邮箱表单")
        step = "等待可见邮箱输入框"
        await email.wait_for(state="visible", timeout=30_000)
        step = "等待可见密码输入框"
        password = page.locator('input[type="password"]:visible, input[placeholder*="密码"]:visible, input[autocomplete="current-password"]:visible')
        await password.wait_for(state="visible", timeout=30_000)
        step = "识别登录按钮"
        login_candidates = page.get_by_role("button", name=re.compile(r"^\s*(log\s*in|sign\s*in|登\s*录)\s*$", re.I))
        login = await unique_visible(login_candidates)
        for name, control in (("邮箱输入框", email), ("密码输入框", password)):
            count = await control.count()
            if count != 1:
                return failed(f"可见{name}匹配数量为 {count}，需要唯一控件")
        if login is None:
            return failed("可见登录按钮无法唯一识别")
        step = "填充邮箱"
        await email.fill(account.account_name)
        step = "填充密码"
        await password.fill(account.password)
        step = "点击登录按钮"
        # click 自动等待按钮启用，避免输入后状态更新尚未完成就放弃。
        await login.click(timeout=30_000)
        logger.info("已使用当前环境绑定账号提交 TikTok 登录表单，等待平台确认或人工验证")
        return True
    except PlaywrightError as exc:
        # fill 的错误可能包含凭据，仅记录固定步骤及异常类型。
        return failed(f"{step}失败（{type(exc).__name__}）")


UPLOAD_ATTACHMENT_PATTERN = re.compile(r'^\s*(?:在这里添加表格附件|Add (?:your )?spreadsheet(?: attachment)? here)\s*$', re.I)


async def expand_upload_steps(page, check_stop=None):
    """根据跨境页面的展开状态收起模板步骤、展开表格上传步骤。"""
    first = page.get_by_role('button', name=re.compile(r'第\s*1\s*步\s*[:：]\s*下载模板|Step\s*1\s*[:：]\s*Download', re.I))
    second = page.get_by_role('button', name=re.compile(r'第\s*2\s*步\s*[:：]\s*上传电子表格|Step\s*2\s*[:：]\s*Upload', re.I))
    if not await second.count():return False
    if await first.count()!=1 or await second.count()!=1:
        raise RuntimeError('无法唯一识别批量上传页的步骤控件')
    for control, expanded in ((first, 'false'), (second, 'true')):
        if check_stop:await check_stop()
        state = await control.get_attribute('aria-expanded')
        if state not in ('true', 'false'):
            raise RuntimeError('无法确认批量上传步骤的展开状态')
        if state!=expanded:
            await control.click()
            await expect(control).to_have_attribute('aria-expanded', expanded, timeout=10000)
    return True


async def wait_for_upload_page(page, on_login_required=None, account=None, upload_url=BULK_UPLOAD_URL, check_stop=None):
    """等待人工登录；在明确出现上传控件前不上传或提交。"""
    login_deadline = None
    return_to_upload = False
    page_deadline = time.monotonic() + 30
    login_attempted = False
    while True:
        if check_stop:await check_stop()
        if login_deadline is not None and time.monotonic() >= login_deadline:
            raise RuntimeError("等待 TikTok 登录超时（10 分钟），尚未上传或提交；请登录后核对并重试")
        try:
            is_login = "login" in page.url.lower() or bool(await page.get_by_role(
                "button", name=re.compile(r"^(log\s*in|sign\s*in|登录)$", re.I)
            ).count())
            if is_login:
                return_to_upload = True
                if login_deadline is None:
                    login_deadline = time.monotonic() + LOGIN_WAIT_SECONDS
                    await page.bring_to_front()
                    if on_login_required:
                        await on_login_required()
                if account and not login_attempted:
                    login_attempted = True
                    await attempt_account_login(page, account)
                await asyncio.sleep(1)
                continue
            if return_to_upload:
                # 登录后可能落在首页，重新进入批量上传；仍未上传文件。
                await open_bulk_upload(page, upload_url)
                return_to_upload = False
                page_deadline = time.monotonic() + 30
                continue
            await expand_upload_steps(page, check_stop)
            attachment = await unique_visible(page.get_by_text(UPLOAD_ATTACHMENT_PATTERN))
            if attachment is not None:return
            await page.locator("input[type=file]").wait_for(state="attached", timeout=1_000)
            return
        except PlaywrightTimeoutError:
            if time.monotonic() >= page_deadline:
                raise RuntimeError("未找到 TikTok 批量上传控件，尚未上传或提交；请核对页面和登录状态")
        except PlaywrightError as exc:
            # 登录或客户端路由跳转时 DOM 上下文会短暂失效。
            if "Execution context was destroyed" not in str(exc):
                raise
            if time.monotonic() >= (login_deadline or page_deadline):
                raise RuntimeError("TikTok 页面持续跳转，尚未上传或提交；请核对登录状态") from exc
        await asyncio.sleep(1)


async def upload_and_import(debug_port: int, xlsx_path: Path, before_import=None, on_login_required=None, on_upload_ready=None, account=None, on_progress=None, expected_count=None, site=None, page=None, upload_url=None, check_stop=None):
    """上传后点击一次导入，明确导入成功才完成；未知结果交由人工核对。"""
    if xlsx_path.suffix.lower() != ".xlsx":
        raise RuntimeError("TikTok 批量上传仅支持 .xlsx 文件，尚未上传")
    if xlsx_path.stat().st_size > MAX_UPLOAD_BYTES:
        raise RuntimeError("TikTok 上传页面文件上限为 20 MB，请减少商品数量重新生成任务；尚未上传")
    async with AsyncExitStack() as stack:
        if page is None:
            playwright = await stack.enter_async_context(async_playwright())
            browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
            stack.push_async_callback(browser.close)
            if not browser.contexts:
                raise RuntimeError("HubStudio 浏览器没有可用上下文")
            page = await browser.contexts[0].new_page()
        operation = "检查 TikTok 登录"
        import_started = False
        try:
            if upload_url is None:
                upload_url = BULK_UPLOAD_URL
                if account and urlsplit(account.login_url).hostname != "seller-my.tiktok.com":
                    origin = urlsplit(account.login_url)
                    upload_url = f"{origin.scheme}://{origin.netloc}/products/bulk-upload"
                if site == "ID":
                    upload_url = "https://seller-id.tokopedia.com/product/batch/publish?entry-from=hub&shop_region=ID&step=2"
            await progress(on_progress, 'opening_upload', '正在打开所选环境的批量上传页')
            await open_bulk_upload(page, upload_url)
            await wait_for_upload_page(page, on_login_required, account, upload_url, check_stop)
            await progress(on_progress, "logged_in", "TikTok 已登录，批量上传页已就绪；尚未上传")
            operation = "通过账号菜单检查上传页语言"
            await ensure_simplified_chinese(page, on_progress)
            await wait_for_upload_page(page, on_login_required, account, upload_url, check_stop)
            if on_upload_ready:
                await on_upload_ready()
            operation = "上传 XLSX"
            attachment = await unique_visible(page.get_by_text(UPLOAD_ATTACHMENT_PATTERN))
            if attachment is not None:
                async with page.expect_file_chooser(timeout=10000) as pending:
                    await attachment.click()
                chooser = await pending.value
                await chooser.set_files(str(xlsx_path))
            else:
                file_input = page.locator("input[type=file]")
                await file_input.wait_for(state="attached", timeout=30_000)
                if await file_input.count() != 1 or not await file_input.is_enabled():
                    raise RuntimeError("无法唯一识别可用的 TikTok 批量上传控件")
                await file_input.set_input_files(str(xlsx_path))
            await progress(on_progress, "upload_parsing", "XLSX 已交给页面，正在等待文件上传解析和商品准备就绪")
            operation = "等待表格上传解析和商品准备就绪"
            await wait_upload_control(page, page.get_by_text(xlsx_path.name, exact=True), 120_000, check_stop)
            ready = page.get_by_text(re.compile(r"^\s*[1-9]\d*\s*款商品准备就绪\s*$"))
            await wait_upload_control(page, ready, 120_000, check_stop)
            if expected_count is not None:
                if await ready.count() != 1 or int(re.search(r"\d+", await ready.inner_text()).group()) != expected_count:
                    raise RuntimeError("平台解析商品数量与固定文件不一致，尚未导入")
            import_button = page.get_by_role("button", name=re.compile(r"^(导入|import)$", re.I))
            await wait_upload_control(page, import_button, 30_000, check_stop)
            if await import_button.count() != 1 or not await import_button.is_enabled():
                raise RuntimeError("导入按钮不唯一或尚不可用，尚未导入；请核对文件解析结果")
            success = page.get_by_text(re.compile("导入成功"))
            for index in range(await success.count()):
                if await success.nth(index).is_visible():
                    raise RuntimeError("页面已有导入成功提示，无法确认它属于本次导入；尚未点击导入")
            await check_duplicate_upload(page)
            # 先持久化导入阶段，报告失败时不执行点击。
            if before_import:
                await before_import()
            operation = "点击导入并等待导入成功"
            import_started = True
            await import_button.click()
            await wait_import_result(page, success, check_stop)
            errors = page.get_by_role("alert").filter(has_text=re.compile(r"error|failed|invalid|失败|错误", re.I))
            if await errors.count() and await errors.first.is_visible():
                raise RuntimeError("平台同时返回错误，请人工核对本次导入结果")
            if expected_count is not None:
                receipt = page.get_by_text(IMPORT_RECEIPT_PATTERN)
                count = await receipt.count()
                counts = {}
                for index in range(count):
                    control = receipt if count == 1 else receipt.nth(index)
                    if not await control.is_visible():continue
                    text = (await control.inner_text()).strip()
                    match = IMPORT_RECEIPT_PATTERN.fullmatch(text)
                    if match:
                        accepted = int((match.group(1) or match.group(2)).replace(',', ''))
                        counts[accepted] = text
                if not counts:
                    raise RuntimeError("平台只有笼统成功提示，无法核对全部商品；请人工核对")
                if len(counts) != 1:
                    raise RuntimeError(f"平台导入回执数量冲突（{sorted(counts)}），预期 {expected_count} 个商品，请人工核对")
                accepted, text = next(iter(counts.items()))
                await progress(on_progress, 'listing_receipt', f'导入回执核对：预期 {expected_count} 个商品，平台确认 {accepted} 个商品')
                if accepted != expected_count:
                    raise RuntimeError(f"平台受理数量不一致：预期 {expected_count} 个商品，实际 {accepted} 个商品，请人工核对部分提交")
                return {"accepted": list(range(expected_count)), "rejected": [], "receipt": text[:500]}
        except PlaywrightTimeoutError as exc:
            result = "导入结果未知，请核对 TikTok 页面" if import_started else "尚未点击导入，请核对 TikTok 页面"
            raise RuntimeError(f"{operation}超时：未识别到明确的控件或本次导入成功结果；{result}") from exc
        except PlaywrightError as exc:
            logger.exception("TikTok 自动上品在%s发生 Playwright 异常（仅本机日志）", operation)
            result = "导入结果未知，请核对 TikTok 页面" if import_started else "尚未点击导入，请核对登录状态和页面"
            raise RuntimeError(f"{operation}失败（{type(exc).__name__}）；{result}，详细原因见本机日志") from exc


class AgentRuntime:
    def __init__(self, config):
        self.config = config
        self.state = {"status": "正在启动", "paused": False, "stop": False, "environments": [],
                      "user": None, "erp_connected": False, "hub_connected": False, "sync_at": None, "sync_error": None, "login_required": True,
                      "active_task_id": None, "abort_requested": False}
        self.client = None
        self.current_claim = None
        self.execution = None
        self.last_heartbeat = time.monotonic()
        self.sync_lock = asyncio.Lock()
        self.synced_monotonic = None
        self.last_sync_attempt = 0
        self.import_possible = False
        self.matrix = MatrixRuntime(self, APP_SUPPORT_PATH / "matrix", save_config, upload_and_import)
        self.connector = ConnectorServer(self.state, PORTAL_URL)

    async def abort_task(self, task_id):
        if not self.current_claim or self.current_claim["task"]["id"] != task_id or not self.execution or self.execution.done():
            raise ERPRequestError(409, "此任务未在本机执行或已经结束，请刷新任务")
        self.state["paused"] = True
        if not self.state["abort_requested"]:
            self.state["abort_requested"] = True
            self.state["status"] = f"任务 #{task_id}：正在中止，请等待结果并核对平台"
            self.execution.cancel()
        return {"ok": True, "task_id": task_id, "message": "已请求中止本机执行，并暂停领取新任务"}

    def require_login(self):
        self.client = None
        self.synced_monotonic = None
        self.state.update(user=None, login_required=True, erp_connected=False, hub_connected=False,
                          environments=[], sync_at=None, sync_error=None, status="请在 ERP 的 TK 矩阵页面授权此连接器")

    async def sync(self):
        async with self.sync_lock:
            self.last_sync_attempt = time.monotonic()
            try:
                config = await self.client.request("GET", "/hub-v5/agent/config")
                self.state["user"] = config["user"]
                self.state["erp_connected"] = True
                if config.get("configured") is False:
                    raise RuntimeError("请联系管理员配置 HubStudio API")
                # Local API 使用当前客户端登录态，不通过公司凭据切换用户/团队。
                items = await HubstudioClient(self.config.get("hubstudio_url", "http://127.0.0.1:6873")).environments()
                self.state["hub_connected"] = True
                self.state["environments"] = [e | {"id": e["container_code"]} for e in items]
                uploaded = await self.matrix.sync(items)
                self.state["sync_error"] = None
                if uploaded:
                    self.state["sync_at"] = int(time.time() * 1000)
                    self.synced_monotonic = time.monotonic()
            except Exception as exc:
                self.synced_monotonic = None
                self.state["sync_error"] = str(exc) if isinstance(exc, (ERPRequestError, RuntimeError)) else "同步失败，请检查 ERP 和 HubStudio Local API 连接"
                self.state["hub_connected"] = False
                logger.error("环境同步失败（保留上次完整快照）")

    async def execute(self, claim):
        task, token = claim["task"], claim["claim_token"]
        task_id = task["id"]
        self.import_possible = False
        try:
            self.state["status"] = f"任务 #{task_id}：正在读取环境绑定账号"
            hub = HubstudioClient(self.config.get("hubstudio_url", "http://127.0.0.1:6873"))
            account = None
            await self.client.report(task_id, token, "running", "reading_account", "正在读取当前任务环境绑定的平台账号和凭据")
            try:
                account = await hub.bound_account(claim["hubstudio"]["container_code"])
                available = int(bool(account.password))
                message = f"已成功读取 HubStudio 当前环境绑定账号（本次 {available}/1 个账号有密码；本机可用 {available}）；2FA 密钥{'可用' if account.otp_secret else '为空'}"
            except Exception as exc:
                message = str(exc) if isinstance(exc, RuntimeError) else "HubStudio 绑定账号读取失败，请检查 Local API 连接和权限"
                message += "；未使用凭据，将等待人工登录"
            logger.info("任务 #%s：%s", task_id, message)
            await self.client.report(task_id, token, "running", "reading_account", message)
            self.state["status"] = f"任务 #{task_id}：正在启动环境"
            await self.client.report(task_id, token, "running", "starting_environment", "正在启动 HubStudio 环境")
            port = await hub.start(claim["hubstudio"]["container_code"])
            with tempfile.TemporaryDirectory(prefix="haitoo-hub-") as directory:
                file_path = Path(directory) / Path(task["export_filename"]).name
                await self.client.download(task_id, token, file_path)
                self.state["status"] = f"任务 #{task_id}：正在检查 TikTok 登录"
                await self.client.report(task_id, token, "running", "checking_login", "正在打开 TikTok 批量上传页并检查登录状态，尚未上传")
                async def on_login_required():
                    self.state["status"] = f"任务 #{task_id}：请在 HubStudio 中登录 TikTok（等待最多 10 分钟）"
                    await self.client.report(task_id, token, "running", "waiting_login", "TikTok 未登录，请在打开的 HubStudio 页面完成登录及验证；最多等待 10 分钟，登录后自动继续")
                async def on_upload_ready():
                    self.state["status"] = f"任务 #{task_id}：正在上传 XLSX"
                    await self.client.report(task_id, token, "running", "uploading", "TikTok 上传页已就绪，正在上传 XLSX")
                async def before_import():
                    self.state["status"] = f"任务 #{task_id}：商品准备就绪，正在导入"
                    await self.client.report(task_id, token, "running", "importing", "表格已上传解析，商品准备就绪，准备点击导入并等待导入成功")
                    self.import_possible = True
                async def on_progress(stage, message):
                    self.state["status"] = f"任务 #{task_id}：{message}"
                    await self.client.report(task_id, token, "running", stage, message)
                await upload_and_import(port, file_path, before_import, on_login_required, on_upload_ready, account, on_progress)
            await self.client.report(task_id, token, "completed", "imported", "TikTok 已明确显示本次商品导入成功")
            self.state["status"] = f"任务 #{task_id}：导入成功"
        except asyncio.CancelledError:
            if self.state["abort_requested"]:
                result = "可能已点击导入，结果未知，请核对 TikTok 平台" if self.import_possible else "尚未进入导入阶段；已上传的文件仍可能留在平台，请核对页面"
                message = f"人工中止本机执行；{result}。已暂停领取新任务"
                logger.info("任务 #%s：%s", task_id, message)
                try:
                    await self.client.report(task_id, token, "awaiting_attention", "manually_aborted", message)
                except Exception:
                    logger.error("任务 #%s 中止报告未送达；等待租约超时后人工核对", task_id)
                self.state["status"] = f"任务 #{task_id}：已中止，等待人工核对"
                raise
            self.state["status"] = f"任务 #{task_id}：连接或领取失效，请人工核对"
            raise
        except Exception as exc:
            message = str(exc)[:500] if isinstance(exc, (RuntimeError, ERPRequestError)) else "执行失败，导入结果未知，请核对 TikTok 页面"
            logger.error("任务 #%s 需要人工处理：%s（异常类型：%s）", task_id, message, type(exc).__name__)
            # Playwright 原始错误可能含页面或请求敏感信息，不把完整内容发到 ERP。
            if isinstance(exc, PlaywrightError):
                logger.exception("任务 #%s Playwright 原始异常（仅本机日志）", task_id)
            try:
                duplicate = isinstance(exc, DuplicateUploadError)
                data_error = isinstance(exc, ImportDataError)
                if duplicate:
                    self.state["paused"] = True
                await self.client.report(task_id, token, "failed" if duplicate or data_error else "awaiting_attention", "duplicate_file" if duplicate else "import_data_error" if data_error else "manual_attention", message)
            except Exception:
                logger.error("任务 #%s 异常报告未送达；等待租约超时后人工核对", task_id)
            if isinstance(exc, ImportDataError):
                self.state["status"] = f"任务 #{task_id}：失败：上传成功，添加商品失败（数据错误），请人工查看处理"
            else:
                self.state["status"] = f"任务 #{task_id}：文件已存在，已失败并暂停领取" if isinstance(exc, DuplicateUploadError) else f"任务 #{task_id}：需要人工处理"

    async def heartbeat_loop(self):
        while not self.state["stop"]:
            if not self.client:
                await asyncio.sleep(1)
                continue
            try:
                await self.matrix.heartbeat()
                self.last_heartbeat = time.monotonic()
                self.state["erp_connected"] = True
            except Exception as exc:
                self.state["erp_connected"] = False
                self.matrix.enabled = False
                if self.matrix.claim:
                    self.matrix.lost_lease = True
                revoked = isinstance(exc, ERPRequestError) and exc.status in {401, 409, 426}
                if self.execution and not self.execution.done() and not self.state["abort_requested"] and (revoked or time.monotonic() - self.last_heartbeat >= 60):
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

    async def authorization_loop(self):
        while not self.state["stop"]:
            if self.state["login_required"]:
                try:
                    token = await pair_with_erp(self.config)
                    self.client = ERPClient(API_URL, token)
                    self.state.update(login_required=False, erp_connected=True, status="ERP 已授权，正在同步环境")
                    self.last_sync_attempt = 0
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("ERP 授权暂未完成，一分钟后重试")
                    self.state["status"] = "等待在 ERP 矩阵页面完成授权"
                    await asyncio.sleep(60)
            await asyncio.sleep(1)

    async def update_loop(self):
        while not self.state["stop"]:
            if self.client and not self.state["login_required"]:
                from updater import UpdateManager
                if not self.matrix.updater:
                    self.matrix.updater = UpdateManager(self.matrix.root, self.client)
                self.matrix.updater.client = self.client
                await self.matrix.updater.check(can_activate=False)
            await asyncio.sleep(2)

    async def run(self):
        await self.connector.start()
        background = []
        try:
            token = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
            health_path = os.environ.pop("HAITOO_UPDATE_HEALTH", None)
            if health_path:
                from updater import atomic, VERSION, keys, target
                from plugin_manager import load_plugin
                # 核心模块已加载，验证配置、凭据库和插件可读；远程离线不影响本机健康。
                load_config()
                self.matrix.plugin = load_plugin(self.matrix.root, keys(), *target())
                atomic(Path(health_path), {"ready": True, "version": VERSION})
            if not health_path:
                from update_recovery import confirm_manual_install
                confirm_manual_install(self.matrix.root)
            if token:
                client = ERPClient(self.config.get("erp_url", API_URL), token)
                try:
                    config = await client.request("GET", "/hub-v5/agent/config")
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
            background = [asyncio.create_task(self.heartbeat_loop()), asyncio.create_task(self.sync_loop()),
                          asyncio.create_task(self.authorization_loop()), asyncio.create_task(self.update_loop())]
            while not self.state["stop"]:
                if self.state["login_required"]:
                    if self.client:
                        self.require_login()
                    await asyncio.sleep(1)
                    continue
                if await self.matrix.check_updates():
                    self.state.update(stop=True, update_exit=True)
                    break
                if self.matrix.updater and self.matrix.updater.prepared:
                    self.state["status"] = "更新已准备，正在确认发布状态"
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                if self.state["paused"]:
                    self.state["status"] = "已暂停领取"
                elif self.matrix.enabled and await self.matrix.try_next():
                    continue
                else:
                    self.state["status"] = self.state.get("matrix_status") or "在线，等待 ERP 任务"
                await asyncio.sleep(POLL_SECONDS)
        finally:
            for task in background:
                task.cancel()
            for task in background:
                with suppress(asyncio.CancelledError):
                    await task
            await self.connector.close()
            if self.state.get("update_exit"):
                os._exit(0)


async def run_forever(config):
    await AgentRuntime(config).run()


async def pair_with_erp(config=None):
    """通过 ERP 网页的现有账号完成终端授权，无需人工复制 Token。"""
    platform_name = "macos" if platform.system() == "Darwin" else "windows"
    name = f"{socket.gethostname()[:100]} · {secrets.token_hex(6)}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(API_URL + "/hub-agent/pairings", json={"name": name, "platform": platform_name})
        if response.status_code == 404:
            raise RuntimeError(
                "ERP 服务器尚未部署 Hub 执行器配对接口（/hub-agent/pairings）。"
                "请先更新与连接器匹配的 ERP 后端及数据库。"
            )
        response.raise_for_status(); code = response.json()["code"]
    webbrowser.open(f"{PORTAL_URL}/settings/shops?tab=environments&hub_agent_pair={code}")
    for _ in range(120):
        await asyncio.sleep(5)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{API_URL}/hub-agent/pairings/{code}")
        if response.status_code == 404:
            raise RuntimeError("配对已过期，请重新打开本地执行器")
        response.raise_for_status(); result = response.json()
        if result["status"] == "completed":
            keyring.set_password(SERVICE_NAME, TOKEN_KEY, result["agent_token"])
            config = config if config is not None else load_config()
            config["erp_url"] = API_URL
            config.setdefault("hubstudio_url", "http://127.0.0.1:6873")
            save_config(config)
            logger.info("连接器已通过 ERP 网页授权 | name=%s", name)
            return result["agent_token"]

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
            logger.error("连接器端口被占用，请检查是否已经运行")
    def quit_app(icon, _):
        def stop():
            runtime.state["stop"] = True
            if runtime.execution:
                runtime.execution.cancel()
        loop.call_soon_threadsafe(stop)
        icon.stop()
    def check_updates(*_):
        def request():
            if runtime.matrix.updater:
                runtime.matrix.updater.request_check()
            runtime.state["status"] = "正在检查更新"
        loop.call_soon_threadsafe(request)
    def show_update_help(*_):
        from updater import DISTRIBUTION
        webbrowser.open(f"{PORTAL_URL}/settings/shops?tab=environments&connector_update_help=1&distribution={DISTRIBUTION}")
    def retry_update(*_):
        def request():
            if runtime.matrix.updater and runtime.matrix.updater.retry_failed_update():
                runtime.state["status"] = "已请求重试更新，等待当前任务结束"
            else:
                runtime.state["status"] = "此失败不能直接重试，请查看处理步骤并手动安装新版"
        loop.call_soon_threadsafe(request)
    def can_retry_update(_):
        from update_recovery import RETRYABLE
        state = runtime.matrix.updater.reported_state() if runtime.matrix.updater else {}
        return bool(state.get("manual_required") and state.get("error_code") in RETRYABLE)
    def toggle_startup(*_):
        from startup import configure, bootstrap_command
        try:
            enabled = not runtime.config.get("autostart", True)
            configure(enabled, bootstrap_command())
            runtime.config["autostart"] = enabled; save_config(runtime.config)
        except Exception as exc:
            runtime.state["status"] = str(exc)
    def update_status(_):
        from updater import VERSION
        state = runtime.matrix.updater.reported_state() if runtime.matrix.updater else {}
        labels = {"manual_installed":"已确认手动安装", "manual_required":"更新需要人工处理，当前版本保留", "retry_requested":"已请求重试", "checking":"检查更新", "downloading":"正在下载", "waiting_idle":"等待任务结束后更新", "restart_requested":"正在更新", "retry":"更新失败，稍后重试", "rejected":"更新包校验失败", "no_trusted_keys":"更新公钥未配置", "insufficient_space":"磁盘空间不足", "installer_required":"请在 ERP 下载新版安装程序", "installed":"更新成功", "rolled_back":"已恢复上一版本", "up_to_date":"已是最新版本"}
        progress = f" {state['progress']}%" if state.get('status') == 'downloading' and 'progress' in state else ''
        return f"版本 {VERSION} · {labels.get(state.get('status'), '等待检查')}{progress}"
    image = Image.new("RGB", (64, 64), "#4d46a5")
    ImageDraw.Draw(image).ellipse((18, 18, 46, 46), fill="white")
    menu = pystray.Menu(pystray.MenuItem(lambda _: runtime.state["status"], None, enabled=False),
        pystray.MenuItem(update_status, None, enabled=False),
        pystray.MenuItem("检查更新", check_updates),
        pystray.MenuItem("更新处理步骤与手动安装", show_update_help),
        pystray.MenuItem("处理后重试更新", retry_update, enabled=can_retry_update),
        pystray.MenuItem("登录电脑后自动启动", toggle_startup, checked=lambda _: runtime.config.get("autostart", True), enabled=bool(getattr(sys, "frozen", False))),
        pystray.MenuItem("打开日志目录", lambda *_: subprocess.Popen(["open", str(LOG_DIRECTORY)]) if platform.system() == "Darwin" else os.startfile(str(LOG_DIRECTORY))),
        pystray.MenuItem("打开 ERP 矩阵管理", lambda *_: webbrowser.open(f"{PORTAL_URL}/settings/shops?tab=environments")),
        pystray.MenuItem("退出", quit_app))
    threading.Thread(target=worker, daemon=True).start()
    pystray.Icon("HaitooHubAgent", image, "Haitoo Hub 执行器", menu).run()


async def run_console(config):
    enable_console_logging()
    print(f"Haitoo Hub 连接器：请在 {PORTAL_URL}/settings/shops 管理设备、环境和任务。")
    print("关闭此终端窗口 = 停止执行器。")
    try:
        await AgentRuntime(config).run()
    except OSError as exc:
        logger.error("连接器端口 %s 无法启动，请检查是否已有连接器运行", STATUS_PORT)
        raise RuntimeError("连接器启动失败") from exc


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
    update_parser = commands.add_parser("apply-update")
    update_parser.add_argument("--transaction", required=True)
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--kind", choices=("agent", "plugin"), required=True)
    args = parser.parse_args()
    if args.command == "apply-update":
        from updater import apply_update
        apply_update(args.transaction)
        return
    if args.command == "rollback":
        from updater import rollback
        rollback(APP_SUPPORT_PATH / "matrix", args.kind)
        print("已回滚至上一已验证版本，问题版本已停止自动重试")
        return
    from updater import forward
    if args.command in {None, "tray", "console", "run"} and forward(APP_SUPPORT_PATH / "matrix"):
        return
    if getattr(sys, "frozen", False) and args.command in {None, "tray", "console", "run"}:
        from startup import configure, bootstrap_command, migrate_legacy
        config = load_config()
        try:
            if not config.get("startup_migrated"):
                migrate_legacy()
                config["startup_migrated"] = True; save_config(config)
            configure(config.get("autostart", True), bootstrap_command())
        except Exception:
            logger.warning("登录自启设置失败，请从托盘重试")
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
