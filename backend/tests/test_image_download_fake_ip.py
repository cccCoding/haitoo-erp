import asyncio
import os
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app import image_download
from app.config import Settings


def dns_record(address, port=80):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (address, port))


class FakeIPImageDownloadTests(unittest.IsolatedAsyncioTestCase):
    def test_setting_defaults_to_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(Settings(_env_file=None).image_download_allow_fake_ip)

    async def test_download_uses_setting_and_pins_fake_ip_with_original_host(self):
        loop = asyncio.get_running_loop()
        for address in ("198.18.0.21", "198.19.255.254", "2001:2::14"):
            for enabled in (False, True):
                with self.subTest(address=address, enabled=enabled):
                    reader = asyncio.StreamReader()
                    reader.feed_data(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nimage")
                    reader.feed_eof()
                    writer = Mock()
                    writer.drain = AsyncMock()
                    writer.wait_closed = AsyncMock()
                    writer.get_extra_info.side_effect = lambda name: (address, 80) if name == "peername" else None
                    with patch.object(image_download, "get_settings", return_value=SimpleNamespace(image_download_allow_fake_ip=enabled)), \
                            patch.object(loop, "getaddrinfo", AsyncMock(return_value=[dns_record(address)])), \
                            patch.object(asyncio, "open_connection", AsyncMock(return_value=(reader, writer))) as connect:
                        if not enabled:
                            with self.assertRaisesRegex(image_download.ImageDownloadError, "必须位于公网"):
                                await image_download._download_once("http://images.example/item.png")
                            connect.assert_not_called()
                            continue
                        self.assertEqual(await image_download._download_once("http://images.example/item.png"), b"image")
                    connect.assert_awaited_once_with(address, 80)
                    request = b"".join(call.args[0] for call in writer.write.call_args_list)
                    self.assertIn(b"Host: images.example\r\n", request)

    async def test_enabled_mode_rejects_other_unsafe_dns_even_mixed_with_fake_ip(self):
        loop = asyncio.get_running_loop()
        for address in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
                        "0.0.0.0", "192.0.2.1", "224.0.0.1",
                        "::1", "fc00::1", "fe80::1", "2001:2:1::1", "::ffff:198.18.0.21", "64:ff9b::a00:1"):
            with self.subTest(address=address), \
                    patch.object(loop, "getaddrinfo", AsyncMock(return_value=[dns_record("198.18.0.21"), dns_record(address)])), \
                    patch.object(asyncio, "open_connection", AsyncMock()) as connect:
                with self.assertRaises(image_download.UnsafeImageAddress):
                    await image_download.PublicImageNetworkBackend(allow_fake_ip=True).connect_tcp("images.example", 80, timeout=1)
                connect.assert_not_called()

    async def test_enabled_mode_still_checks_peer_and_closes_mismatched_connection(self):
        loop = asyncio.get_running_loop()
        for peer in ("198.18.0.22", "8.8.8.8", "127.0.0.1"):
            writer = Mock()
            writer.get_extra_info.return_value = (peer, 80)
            with self.subTest(peer=peer), \
                    patch.object(loop, "getaddrinfo", AsyncMock(return_value=[dns_record("198.18.0.21")])), \
                    patch.object(asyncio, "open_connection", AsyncMock(return_value=(Mock(), writer))):
                with self.assertRaises(image_download.UnsafeImageAddress):
                    await image_download.PublicImageNetworkBackend(allow_fake_ip=True).connect_tcp("images.example", 80, timeout=1)
                writer.close.assert_called_once()

    async def test_enabled_backend_does_not_allow_literal_fake_ip(self):
        loop = asyncio.get_running_loop()
        for address in ("198.18.0.21", "2001:2::14"):
            with self.subTest(address=address), \
                    patch.object(loop, "getaddrinfo", AsyncMock(return_value=[dns_record(address)])), \
                    patch.object(asyncio, "open_connection", AsyncMock()) as connect:
                with self.assertRaises(image_download.UnsafeImageAddress):
                    await image_download.PublicImageNetworkBackend(allow_fake_ip=True).connect_tcp(address, 80, timeout=1)
                connect.assert_not_called()

    async def test_enabled_mode_rejects_unsafe_initial_urls_and_redirects(self):
        urls = ("http://198.18.0.21/item", "http://[2001:2::14]/item", "http://127.0.0.1/item",
                "http://10.0.0.1/item", "http://localhost/item", "http://service.internal/item",
                "http://images.example:8080/item", "http://user:pass@images.example/item", "file:///etc/passwd")
        for url in urls:
            for redirect in (False, True):
                handler = Mock(return_value=httpx.Response(302, headers={"location": url}))
                with self.subTest(url=url, redirect=redirect), \
                        patch.object(image_download, "get_settings", return_value=SimpleNamespace(image_download_allow_fake_ip=True)), \
                        patch.object(image_download, "PublicImageTransport", return_value=httpx.MockTransport(handler)):
                    with self.assertRaises(image_download.ImageDownloadError):
                        await image_download._download_once("http://images.example/item" if redirect else url)
                    self.assertEqual(handler.call_count, int(redirect))


if __name__ == "__main__":
    unittest.main()
