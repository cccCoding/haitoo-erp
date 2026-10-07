import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_auth import authorize_computer
from workbench import ERPRequestError


class LocalAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_token_only_used_for_registration(self):
        requests = []
        def handler(request):
            requests.append(request)
            if request.url.path == "/auth/login":
                return httpx.Response(200, json={"access_token": "user-secret"})
            self.assertEqual(request.headers["Authorization"], "Bearer user-secret")
            self.assertNotIn(b"password", request.content)
            return httpx.Response(200, json={"agent_token": "agent-secret"})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("local_auth.httpx.AsyncClient", return_value=client):
            self.assertEqual(await authorize_computer("https://test.example", "a@b.com", "password"), "agent-secret")
        self.assertEqual([r.url.path for r in requests], ["/auth/login", "/hub-agents/register"])

    async def test_bad_password_does_not_register_or_echo_server_body(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(401, json={"detail": "sensitive-body"})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("local_auth.httpx.AsyncClient", return_value=client):
            with self.assertRaisesRegex(ERPRequestError, "邮箱或密码错误"):
                await authorize_computer("https://test.example", "a@b.com", "password")
        self.assertEqual(len(requests), 1)
