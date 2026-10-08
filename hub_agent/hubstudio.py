"""HubStudio Local API：使用客户端当前登录用户/团队，不登录或切换公司凭据。

契约：https://api-docs.hubstudio.cn/380052376e0（列表）、380052361e0（启动）。
"""
import httpx
from dataclasses import dataclass, field
from urllib.parse import urlsplit
import re


@dataclass
class HubAccount:
    account_name: str = field(repr=False)
    password: str | None = field(repr=False)
    otp_secret: str | None = field(repr=False)
    login_url: str


def seller_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return (parsed.scheme == "https" and not parsed.username and not parsed.password
            and parsed.port in (None, 443) and bool(re.fullmatch(
                r"seller(?:-[a-z]{2})?\.tiktok\.com|seller\.tiktokglobalshop\.com|seller\.tiktokshopglobalselling\.com", host)))


class HubstudioClient:
    def __init__(self, endpoint: str, credentials: dict | None = None):
        self.endpoint = endpoint.rstrip("/")

    async def post(self, path, body):
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(self.endpoint + path, json=body, headers={"Accept-Language": "zh-CN"})
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") not in (0, "0") or not isinstance(payload.get("data"), dict):
            raise RuntimeError("HubStudio Local API 请求失败，请检查客户端登录及 API 服务")
        return payload["data"]

    async def environments(self):
        result, seen, total = [], set(), None
        for current in range(1, 101):
            data = await self.post("/api/v1/env/list", {"current": current, "size": 200})
            items, count = data.get("list"), data.get("total")
            if not isinstance(items, list) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise RuntimeError("HubStudio 环境分页响应格式不正确，未更新环境快照")
            if total is None:
                total = count
            if count != total:
                raise RuntimeError("分页期间环境列表发生变化，请重新同步")
            for item in items:
                if not isinstance(item, dict) or item.get("containerCode") is None:
                    raise RuntimeError("HubStudio 环境缺少 ID，未更新环境快照")
                code = str(item["containerCode"]).strip()
                if not code or code in seen:
                    raise RuntimeError("环境分页包含空 ID 或重复记录，请重新同步")
                seen.add(code)
                metadata = {}
                # 仅显示绑定账号名称；密码、密钥、代理凭据和 IP 不进入快照。
                if "tagName" in item:
                    metadata["group"] = item["tagName"]
                if "serialNumber" in item:
                    metadata["serial_number"] = item["serialNumber"]
                if "labels" in item:
                    metadata["labels"] = item["labels"]
                bound = item.get("accounts")
                account_names = list(dict.fromkeys(a["accountName"].strip() for a in bound
                    if isinstance(a, dict) and isinstance(a.get("accountName"), str) and a["accountName"].strip())) if isinstance(bound, list) else []
                result.append({"container_code": code, "name": item.get("containerName") or code, "account_names": account_names, "metadata_fields": metadata})
            if len(result) == total:
                return result
            if not items or len(result) > total:
                raise RuntimeError("HubStudio 环境分页不完整，未更新环境快照")
        raise RuntimeError("HubStudio 环境超过同步上限，未更新环境快照")

    async def bound_account(self, container_code: str) -> HubAccount:
        """只查询任务环境绑定的唯一账号；凭据仅供本机登录，不进入环境快照。"""
        data = await self.post("/api/v1/env/list", {"containerCodes": [container_code], "current": 1, "size": 200})
        environments = data.get("list")
        if not isinstance(environments, list):
            raise RuntimeError("HubStudio 环境账号响应格式不正确")
        matches = [e for e in environments if isinstance(e, dict) and str(e.get("containerCode")) == container_code]
        if len(matches) != 1:
            raise RuntimeError("无法唯一确认任务环境，未读取账号凭据")
        bound = matches[0].get("accounts")
        if not isinstance(bound, list) or len(bound) != 1 or not isinstance(bound[0], dict):
            raise RuntimeError("任务环境没有唯一绑定账号，请核对 HubStudio 绑定关系")
        account_name, name = bound[0].get("accountName"), bound[0].get("name")
        if not isinstance(account_name, str) or not account_name.strip() or not isinstance(name, str):
            raise RuntimeError("环境绑定账号缺少明确的账号及名称，未读取凭据")
        accounts, total = [], None
        for current in range(1, 101):
            data = await self.post("/api/v1/account/list", {"accountName": account_name, "name": name, "current": current, "size": 200})
            items, count = data.get("list"), data.get("total")
            if not isinstance(items, list) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise RuntimeError("HubStudio 平台账号分页响应不完整")
            if total is None:
                total = count
            if count != total or (not items and len(accounts) != total):
                raise RuntimeError("HubStudio 平台账号分页发生变化或不完整")
            accounts.extend(items)
            if len(accounts) == total:
                break
            if len(accounts) > total:
                raise RuntimeError("HubStudio 平台账号分页响应不完整")
        else:
            raise RuntimeError("HubStudio 平台账号超过查询上限")
        exact = [a for a in accounts if isinstance(a, dict) and a.get("accountName") == account_name and a.get("name") == name]
        if len(exact) != 1:
            raise RuntimeError("无法唯一匹配环境绑定的平台账号，未使用凭据")
        account = exact[0]
        domain = account.get("domainName")
        if domain:
            if not isinstance(domain, str) or not seller_url(domain):
                raise RuntimeError("环境绑定账号的网址不是受支持的 TikTok 卖家地址，未使用凭据")
            login_url = domain
        elif "tiktok" in str(account.get("siteName", "")).lower():
            login_url = "https://seller.tiktokglobalshop.com/"
        else:
            raise RuntimeError("无法确认绑定账号属于 TikTok 卖家平台，未使用凭据")
        password, otp = account.get("accountPassword"), account.get("otpSecret")
        return HubAccount(account_name, password if isinstance(password, str) and password else None,
                          otp if isinstance(otp, str) and otp else None, login_url)

    async def start(self, container_code: str) -> int:
        data = await self.post("/api/v1/browser/start", {"containerCode": container_code, "shouldCloseTabsOnOpen": False})
        if data.get("statusCode", "0") not in (0, "0") or not data.get("debuggingPort"):
            raise RuntimeError("HubStudio 未成功启动环境或未返回 debuggingPort")
        port = int(data["debuggingPort"])
        if not 1 <= port <= 65535:
            raise RuntimeError("HubStudio 返回无效调试端口")
        return port
