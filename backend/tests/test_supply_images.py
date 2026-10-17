import asyncio
from io import BytesIO
import socket
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from PIL import Image

from app import image_download as supply_images


def image_bytes(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (3, 3), "red").save(output, format=format)
    return output.getvalue()


class SupplyImageTests(unittest.IsolatedAsyncioTestCase):
    async def run_check(self, handler, url="https://images.example/item.png"):
        transport = httpx.MockTransport(handler)
        with patch.object(supply_images, "PublicImageTransport", return_value=transport):
            return await supply_images._download_once(url)

    async def test_actual_content_and_supported_formats(self):
        from app.image_download import decode_image, ImageDownloadError
        for fmt in ("PNG","JPEG","WEBP"):
            content=await self.run_check(lambda request:httpx.Response(200,content=image_bytes(fmt),headers={"content-type":"text/plain"}))
            self.assertTrue(decode_image(content).startswith("image/"))
        for content in (b"<html>not an image</html>", image_bytes("GIF")):
            with self.assertRaises(ImageDownloadError): decode_image(content)

    async def test_missing_fails_once_temporary_errors_retry(self):
        from app.image_download import download_image, ImageDownloadError
        handler=Mock(return_value=httpx.Response(404))
        with self.assertRaises(ImageDownloadError): await self.run_check(handler)
        self.assertEqual(handler.call_count,1)
        handler=Mock(return_value=httpx.Response(503))
        with patch.object(supply_images,"PublicImageTransport",return_value=httpx.MockTransport(handler)),patch.object(asyncio,"sleep",AsyncMock()):
            with self.assertRaises(ImageDownloadError): await download_image("https://images.example/a")
        self.assertEqual(handler.call_count,3)

    async def test_size_bounds_and_unsafe_redirect(self):
        from app.image_download import ImageDownloadError
        self.assertEqual(supply_images.MAX_IMAGE_BYTES, 3 * 1024 * 1024)
        self.assertEqual(await self.run_check(lambda request: httpx.Response(200, content=b"x" * supply_images.MAX_IMAGE_BYTES)),
            b"x" * supply_images.MAX_IMAGE_BYTES)
        with self.assertRaises(ImageDownloadError):
            await self.run_check(lambda request:httpx.Response(200,headers={"content-length":str(supply_images.MAX_IMAGE_BYTES+1)}))
        with self.assertRaisesRegex(ImageDownloadError, "3 MiB"):
            await self.run_check(lambda request: httpx.Response(200, content=b"x" * (supply_images.MAX_IMAGE_BYTES + 1)))
        with patch.object(supply_images,"MAX_IMAGE_BYTES",8):
            with self.assertRaises(ImageDownloadError): await self.run_check(lambda request:httpx.Response(200,content=b"ninebytes"))
        handler=Mock(return_value=httpx.Response(302,headers={"location":"http://127.0.0.1/a"}))
        with self.assertRaises(ImageDownloadError): await self.run_check(handler)
        self.assertEqual(handler.call_count,1)

    async def test_unsafe_initial_urls_never_request(self):
        from app.image_download import ImageDownloadError
        handler=Mock()
        for url in ("http://127.0.0.1/a","http://10.0.0.1/a","http://localhost/a","file:///etc/passwd","https://user:pass@images.example/a","https://images.example:8080/a"):
            with self.assertRaises(ImageDownloadError): await self.run_check(handler,url)
        handler.assert_not_called()

    async def test_relative_redirect_and_loop_limit(self):
        def handler(request):
            return httpx.Response(302,headers={"location":"/final"}) if request.url.path=="/item.png" else httpx.Response(200,content=image_bytes())
        self.assertEqual(await self.run_check(handler),image_bytes())
        loop=Mock(return_value=httpx.Response(302,headers={"location":"/item.png"}))
        with self.assertRaises(supply_images.ImageDownloadError): await self.run_check(loop)
        self.assertEqual(loop.call_count,6)

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
            result = await supply_images._download_once("http://images.example/item.png")
        self.assertEqual(result, content)
        connect.assert_awaited_once_with("8.8.8.8", 80)
        request_bytes = b"".join(call.args[0] for call in writer.write.call_args_list)
        self.assertIn(b"Host: images.example\r\n", request_bytes)
