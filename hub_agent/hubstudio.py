"""HubStudio Local API：使用客户端当前登录用户/团队，不登录或切换公司凭据。

契约：https://api-docs.hubstudio.cn/380052376e0（列表）、380052361e0（启动）。
"""
import httpx


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
                # 不保存代理凭据、平台账号、IP，也不把 IP 国家伪装成店铺站点。
                if "tagName" in item:
                    metadata["group"] = item["tagName"]
                if "serialNumber" in item:
                    metadata["serial_number"] = item["serialNumber"]
                if "labels" in item:
                    metadata["labels"] = item["labels"]
                result.append({"container_code": code, "name": item.get("containerName") or code, "metadata_fields": metadata})
            if len(result) == total:
                return result
            if not items or len(result) > total:
                raise RuntimeError("HubStudio 环境分页不完整，未更新环境快照")
        raise RuntimeError("HubStudio 环境超过同步上限，未更新环境快照")

    async def start(self, container_code: str) -> int:
        data = await self.post("/api/v1/browser/start", {"containerCode": container_code, "shouldCloseTabsOnOpen": False})
        if data.get("statusCode", "0") not in (0, "0") or not data.get("debuggingPort"):
            raise RuntimeError("HubStudio 未成功启动环境或未返回 debuggingPort")
        port = int(data["debuggingPort"])
        if not 1 <= port <= 65535:
            raise RuntimeError("HubStudio 返回无效调试端口")
        return port
