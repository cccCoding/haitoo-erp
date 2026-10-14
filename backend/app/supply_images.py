"""货盘最终导出阶段的单次图片检查；重试次数由持久化任务管理。"""
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


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
CHECK_TIMEOUT_SECONDS = 30


class UnsafeImageAddress(ValueError):
    """图片请求尝试访问非公网地址。"""


def _public_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise UnsafeImageAddress("图片连接地址无法识别") from exc
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
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port not in {80, 443}:
            raise UnsafeImageAddress("图片 URL 不支持非标准端口")
        try:
            records = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout)
            addresses = list(dict.fromkeys(str(_public_address(record[4][0])) for record in records))
            if not addresses:
                raise httpcore.ConnectError("图片域名没有可用地址")
            # 将经验证的 IP 直接传给建连函数，防止再次解析时 DNS 重绑定。
            reader, writer = await asyncio.wait_for(asyncio.open_connection(addresses[0], port), timeout)
            peer = writer.get_extra_info("peername")
            try:
                if not peer or str(_public_address(peer[0])) != addresses[0]:
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
        self.pool = httpcore.AsyncConnectionPool(network_backend=PublicImageNetworkBackend(), max_connections=1, max_keepalive_connections=0, retries=0)

    async def handle_async_request(self, request):
        response = await self.pool.handle_async_request(httpcore.Request(
            method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path),
            headers=request.headers.raw, content=request.stream, extensions=request.extensions,
        ))
        return httpx.Response(response.status, headers=response.headers, stream=_ResponseStream(response.stream), extensions=response.extensions)

    async def aclose(self):
        await self.pool.aclose()


def _decode_image(content: bytes) -> dict:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as picture:
                if picture.format not in {"JPEG", "PNG", "WEBP"}:
                    return {"status": "invalid", "reason": "仅支持 JPEG、PNG 或 WebP 图片"}
                picture.verify()
            # verify 检查文件结构；load 确认像素可以真实解码。
            with Image.open(BytesIO(content)) as picture:
                picture.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return {"status": "invalid", "reason": "图片内容损坏或不是有效图片"}
    return {"status": "available", "reason": ""}


async def check_image(url: str) -> dict:
    """执行一次检查（允许安全重定向），不在此处自动重试。"""
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(transport=PublicImageTransport(), trust_env=False, timeout=httpx.Timeout(10, connect=8), follow_redirects=False) as client:
                current = _validate_url(url)
                for redirect in range(MAX_REDIRECTS + 1):
                    async with client.stream("GET", current, headers={"Accept": "image/jpeg,image/png,image/webp", "Accept-Encoding": "identity"}) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location or redirect == MAX_REDIRECTS:
                                return {"status": "check_failed", "reason": "图片重定向过多或缺少目标地址"}
                            current = _validate_url(urljoin(current, location))
                            continue
                        if response.status_code in {404, 410}:
                            return {"status": "invalid", "reason": f"图片已不存在（HTTP {response.status_code}）"}
                        if response.status_code != 200:
                            return {"status": "check_failed", "reason": f"图片源暂不可访问（HTTP {response.status_code}）"}
                        length = response.headers.get("content-length", "")
                        if length.isdecimal() and int(length) > MAX_IMAGE_BYTES:
                            return {"status": "invalid", "reason": "图片超过 20 MB"}
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_IMAGE_BYTES:
                                return {"status": "invalid", "reason": "图片超过 20 MB"}
                        return await asyncio.to_thread(_decode_image, bytes(content))
    except UnsafeImageAddress as exc:
        return {"status": "check_failed", "reason": str(exc)}
    except (httpx.HTTPError, httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError, OSError, TimeoutError, ValueError):
        return {"status": "check_failed", "reason": "图片源网络或响应异常，请稍后重新检查"}
    return {"status": "check_failed", "reason": "无法完成图片检查"}
