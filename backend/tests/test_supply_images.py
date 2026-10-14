import asyncio
from io import BytesIO
import socket
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from PIL import Image

from app import supply_images


def image_bytes(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (3, 3), "red").save(output, format=format)
    return output.getvalue()


class SupplyImageTests(unittest.IsolatedAsyncioTestCase):
    async def run_check(self, handler, url="https://images.example/item.png"):
        transport = httpx.MockTransport(handler)
        with patch.object(supply_images, "PublicImageTransport", return_value=transport):
            return await supply_images.check_image(url)

    async def test_decodes_supported_content_instead_of_trusting_mime(self):
        for format in ("PNG", "JPEG", "WEBP"):
            result = await self.run_check(lambda request: httpx.Response(200, content=image_bytes(format), headers={"content-type": "text/plain"}))
            self.assertEqual(result["status"], "available")
        result = await self.run_check(lambda request: httpx.Response(200, content=b"<html>not an image</html>", headers={"content-type": "image/png"}))
        self.assertEqual(result["status"], "invalid")
        result = await self.run_check(lambda request: httpx.Response(200, content=image_bytes("GIF")))
        self.assertEqual(result["status"], "invalid")

    async def test_missing_and_temporary_statuses_have_different_health_states(self):
        for status in (404, 410):
            self.assertEqual((await self.run_check(lambda request: httpx.Response(status)))["status"], "invalid")
        for status in (403, 429, 500, 502):
            self.assertEqual((await self.run_check(lambda request: httpx.Response(status)))["status"], "check_failed")

    async def test_rejects_content_length_and_streamed_overflow(self):
        result = await self.run_check(lambda request: httpx.Response(200, content=b"", headers={"content-length": str(supply_images.MAX_IMAGE_BYTES + 1)}))
        self.assertEqual(result["status"], "invalid")
        with patch.object(supply_images, "MAX_IMAGE_BYTES", 8):
            result = await self.run_check(lambda request: httpx.Response(200, content=b"ninebytes"))
        self.assertEqual(result["status"], "invalid")

    async def test_blocked_initial_urls_never_issue_requests(self):
        handler = Mock()
        for url in ("http://127.0.0.1/a", "http://10.1.2.3/a", "http://[::1]/a", "http://169.254.169.254/a", "http://[::ffff:127.0.0.1]/a", "http://localhost/a", "https://images.example:8080/a", "https://user:pass@images.example/a", "file:///etc/passwd"):
            result = await self.run_check(handler, url)
            self.assertEqual(result["status"], "check_failed", url)
        handler.assert_not_called()

    async def test_safe_relative_redirect_and_blocked_private_redirect(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"location": "/final.png"}) if request.url.path == "/item.png" else httpx.Response(200, content=image_bytes())
        self.assertEqual((await self.run_check(handler))["status"], "available")
        self.assertEqual(len(calls), 2)
        handler = Mock(return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/a"}))
        self.assertEqual((await self.run_check(handler))["status"], "check_failed")
        self.assertEqual(handler.call_count, 1)

    async def test_redirect_loops_are_bounded_and_requests_are_not_retried(self):
        handler = Mock(return_value=httpx.Response(302, headers={"location": "/item.png"}))
        self.assertEqual((await self.run_check(handler))["status"], "check_failed")
        self.assertEqual(handler.call_count, supply_images.MAX_REDIRECTS + 1)
        handler = Mock(side_effect=httpx.ConnectError("temporary"))
        self.assertEqual((await self.run_check(handler))["status"], "check_failed")
        self.assertEqual(handler.call_count, 1)

    async def test_dns_mixed_with_private_address_rejected_before_connect(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))]
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=records)), patch.object(asyncio, "open_connection", AsyncMock()) as connect:
            with self.assertRaises(supply_images.UnsafeImageAddress):
                await supply_images.PublicImageNetworkBackend().connect_tcp("rebind.example", 443, timeout=1)
        connect.assert_not_called()

    async def test_connection_pins_resolved_ip_and_checks_actual_peer(self):
        loop = asyncio.get_running_loop()
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        writer = Mock()
        writer.get_extra_info.return_value = ("8.8.8.8", 443)
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=records)), patch.object(asyncio, "open_connection", AsyncMock(return_value=(Mock(), writer))) as connect:
            await supply_images.PublicImageNetworkBackend().connect_tcp("rebind.example", 443, timeout=1)
        connect.assert_awaited_once_with("8.8.8.8", 443)
        writer.get_extra_info.return_value = ("127.0.0.1", 443)
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=records)), patch.object(asyncio, "open_connection", AsyncMock(return_value=(Mock(), writer))):
            with self.assertRaises(supply_images.UnsafeImageAddress):
                await supply_images.PublicImageNetworkBackend().connect_tcp("rebind.example", 443, timeout=1)
        writer.close.assert_called_once()

    async def test_real_http_transport_uses_pinned_backend_and_original_host(self):
        content = image_bytes()
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: " + str(len(content)).encode() + b"\r\nConnection: close\r\n\r\n" + content)
        reader.feed_eof()
        writer = Mock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        writer.get_extra_info.side_effect = lambda name: ("8.8.8.8", 80) if name == "peername" else None
        loop = asyncio.get_running_loop()
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=records)), patch.object(asyncio, "open_connection", AsyncMock(return_value=(reader, writer))) as connect:
            result = await supply_images.check_image("http://images.example/item.png")
        self.assertEqual(result["status"], "available")
        connect.assert_awaited_once_with("8.8.8.8", 80)
        request_bytes = b"".join(call.args[0] for call in writer.write.call_args_list)
        self.assertIn(b"Host: images.example\r\n", request_bytes)
