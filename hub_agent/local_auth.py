"""在本地程序内完成 ERP 登录与电脑授权，不向工作页返回令牌。"""
import platform
import secrets
import socket

import httpx
from workbench import ERPRequestError


async def authorize_computer(api_url, email, password):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(api_url + "/auth/login", json={"email": email, "password": password})
        if response.is_error:
            messages = {401: "邮箱或密码错误", 403: "账号不可用，请联系管理员", 429: "登录尝试过于频繁，请稍后重试"}
            raise ERPRequestError(response.status_code, messages.get(response.status_code, "ERP 登录失败，请检查服务器状态"))
        access_token = response.json()["access_token"]
        name = f"{socket.gethostname()[:100]} · {secrets.token_hex(6)}"
        response = await client.post(api_url + "/hub-agents/register",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"name": name, "platform": "macos" if platform.system() == "Darwin" else "windows"})
        if response.is_error:
            raise ERPRequestError(response.status_code, "电脑授权失败，请确认使用所属公司的 ERP 账号，且服务器已升级")
        return response.json()["agent_token"]
