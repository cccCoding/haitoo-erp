"""执行器连接地址校验与本机调试身份隔离。"""
import hashlib
from urllib.parse import urlsplit


def validate_erp_url(value: str, *, local_debug: bool = False) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("ERP 地址端口无效") from exc
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("ERP 地址必须是无凭据、查询参数和片段的服务地址")
    if port == 0:
        raise RuntimeError("ERP 地址端口无效")
    if parsed.scheme == "https":
        return value
    if local_debug and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return value
    raise RuntimeError("ERP 地址必须使用 HTTPS；本机 HTTP 调试需设置 HAITOO_LOCAL_DEBUG=1，且只允许回环地址")


def debug_scope(api_url: str) -> str:
    return "local-debug-" + hashlib.sha256(api_url.encode()).hexdigest()[:16]
