"""上传及外链转存工具；不保存图片状态。"""
from __future__ import annotations

import asyncio
from io import BytesIO
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit
import warnings

import httpcore
import httpx
from PIL import Image, UnidentifiedImageError

from .config import get_settings


MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5
CHECK_TIMEOUT_SECONDS = 30
# 本机 Clash / Mihomo 的 Fake-IP 网段；不放行其他私网或保留地址。
FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"), ipaddress.ip_network("2001:2::/48"))


class UnsafeImageAddress(ValueError):
    """图片请求尝试访问非公网地址。"""


def _public_address(value: str, *, allow_fake_ip: bool = False) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise UnsafeImageAddress("图片连接地址无法识别") from exc
    if allow_fake_ip and any(address in network for network in FAKE_IP_NETWORKS):
        return address
    effective = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
    if not effective.is_global or effective.is_multicast or effective.is_reserved:
        raise UnsafeImageAddress("图片地址必须位于公网")
    # IPv6 转换地址可能将公网外观的地址路由到内网 IPv4。
    if isinstance(address, ipaddress.IPv6Address) and (address.sixtofour or address.teredo or address in ipaddress.ip_network("64:ff9b::/96")):
        raise UnsafeImageAddress("不支持 IPv6 转换地址")
    return address


def _validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise UnsafeImageAddress("图片 URL 不合法") from exc
    if len(url) > 4096 or parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeImageAddress("图片必须使用 HTTP 或 HTTPS 公网 URL")
    if parsed.username is not None or parsed.password is not None or port not in {None, 80, 443}:
        raise UnsafeImageAddress("图片 URL 不支持凭据或非标准端口")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "%" in host:
        raise UnsafeImageAddress("图片地址必须位于公网")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # 域名在实际建连时解析、检查并固定目标 IP。
    else:
        _public_address(host)
    return url


class _PinnedStream(httpcore.AsyncNetworkStream):
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        try:
            return await asyncio.wait_for(self.reader.read(max_bytes), timeout)
        except TimeoutError as exc:
            raise httpcore.ReadTimeout() from exc
        except (OSError, ssl.SSLError) as exc:
            raise httpcore.ReadError() from exc

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        try:
            self.writer.write(buffer)
            await asyncio.wait_for(self.writer.drain(), timeout)
        except TimeoutError as exc:
            raise httpcore.WriteTimeout() from exc
        except (OSError, ssl.SSLError) as exc:
            raise httpcore.WriteError() from exc

    async def aclose(self) -> None:
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            pass

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        try:
            await asyncio.wait_for(self.writer.start_tls(ssl_context, server_hostname=server_hostname, ssl_handshake_timeout=timeout), timeout)
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout() from exc
        except (OSError, ssl.SSLError) as exc:
            raise httpcore.ConnectError() from exc
        return self

    def get_extra_info(self, info: str):
        if info == "server_addr":
            return self.writer.get_extra_info("peername")
        if info == "client_addr":
            return self.writer.get_extra_info("sockname")
        if info in {"ssl_object", "socket"}:
            return self.writer.get_extra_info(info)
        return None


class PublicImageNetworkBackend(httpcore.AsyncNetworkBackend):
    """先验证所有 DNS 结果，再连接固定 IP；TLS 仍验证原域名证书。"""
    def __init__(self, *, allow_fake_ip: bool = False):
        self.allow_fake_ip = allow_fake_ip

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port not in {80, 443}:
            raise UnsafeImageAddress("图片 URL 不支持非标准端口")
        # 兼容开关仅用于域名解析；直接提供 IP 的 URL 始终走严格公网校验。
        try:
            ipaddress.ip_address(host)
        except ValueError:
            allow_fake_ip = self.allow_fake_ip
        else:
            allow_fake_ip = False
        try:
            records = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout)
            addresses = list(dict.fromkeys(str(_public_address(record[4][0], allow_fake_ip=allow_fake_ip)) for record in records))
            if not addresses:
                raise httpcore.ConnectError("图片域名没有可用地址")
            # 将经验证的 IP 直接传给建连函数，防止再次解析时 DNS 重绑定。
            reader, writer = await asyncio.wait_for(asyncio.open_connection(addresses[0], port), timeout)
            peer = writer.get_extra_info("peername")
            try:
                if not peer or str(_public_address(peer[0], allow_fake_ip=allow_fake_ip)) != addresses[0]:
                    raise UnsafeImageAddress("图片实际连接地址与已验证地址不一致")
            except Exception:
                writer.close()
                raise
            for option in socket_options or []:
                writer.get_extra_info("socket").setsockopt(*option)
            return _PinnedStream(reader, writer)
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout() from exc
        except OSError as exc:
            raise httpcore.ConnectError() from exc

    async def connect_unix_socket(self, *args, **kwargs):
        raise UnsafeImageAddress("禁止访问本地套接字")

    async def sleep(self, seconds: float):
        await asyncio.sleep(seconds)


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        async for chunk in self.stream:
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class PublicImageTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        backend = PublicImageNetworkBackend(allow_fake_ip=get_settings().image_download_allow_fake_ip)
        self.pool = httpcore.AsyncConnectionPool(network_backend=backend, max_connections=1, max_keepalive_connections=0, retries=0)

    async def handle_async_request(self, request):
        response = await self.pool.handle_async_request(httpcore.Request(
            method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path),
            headers=request.headers.raw, content=request.stream, extensions=request.extensions,
        ))
        return httpx.Response(response.status, headers=response.headers, stream=_ResponseStream(response.stream), extensions=response.extensions)

    async def aclose(self):
        await self.pool.aclose()


class ImageDownloadError(ValueError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def decode_image(content: bytes, *, max_bytes: int | None = MAX_IMAGE_BYTES) -> str:
    if not content:
        raise ImageDownloadError("图片为空")
    if max_bytes is not None and len(content) > max_bytes:
        raise ImageDownloadError(f"图片超过 {max_bytes / (1024 * 1024):g} MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as picture:
                mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(picture.format)
                if not mime:
                    raise ImageDownloadError("仅支持 JPEG、PNG 或 WebP 图片")
                picture.verify()
            with Image.open(BytesIO(content)) as picture:
                picture.load()
        return mime
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageDownloadError("图片内容损坏或不是有效图片") from exc


async def _download_once(url: str) -> bytes:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(transport=PublicImageTransport(), trust_env=False,
                    timeout=httpx.Timeout(10, connect=8), follow_redirects=False) as client:
                current = _validate_url(url)
                for redirect in range(MAX_REDIRECTS + 1):
                    async with client.stream("GET", current, headers={"Accept": "image/jpeg,image/png,image/webp", "Accept-Encoding": "identity"}) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location or redirect == MAX_REDIRECTS:
                                raise ImageDownloadError("图片重定向过多或缺少目标地址")
                            current = _validate_url(urljoin(current, location))
                            continue
                        if response.status_code != 200:
                            raise ImageDownloadError(f"下载图片失败（HTTP {response.status_code}）",
                                response.status_code in {403, 408, 429} or response.status_code >= 500)
                        length = response.headers.get("content-length", "")
                        if length.isdecimal() and int(length) > MAX_IMAGE_BYTES:
                            raise ImageDownloadError("图片超过 3 MiB")
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_IMAGE_BYTES:
                                raise ImageDownloadError("图片超过 3 MiB")
                        return bytes(content)
    except ImageDownloadError:
        raise
    except UnsafeImageAddress as exc:
        raise ImageDownloadError(str(exc)) from exc
    except (httpx.HTTPError, httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError, OSError, TimeoutError, ValueError) as exc:
        raise ImageDownloadError("图片源网络或响应异常，请稍后重试", True) from exc
    raise ImageDownloadError("无法下载图片")


async def download_image(url: str) -> bytes:
    for attempt in range(3):
        try:
            return await _download_once(url)
        except ImageDownloadError as exc:
            if not exc.retryable or attempt == 2:
                raise
            await asyncio.sleep((2, 5)[attempt])
    raise ImageDownloadError("无法下载图片")
