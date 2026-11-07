"""Grsai 受控对象的元数据检查与 R2 服务端复制；禁止读取图片正文。"""
from datetime import datetime, timezone
import json
import logging
import time
from urllib.parse import quote, unquote, urlsplit

from botocore.exceptions import ClientError

from .config import get_settings
from .storage import IMAGE_SUFFIXES, StorageError, _r2_client, _required

logger = logging.getLogger(__name__)
MAX_BYTES = 5 * 1024 * 1024


class InvalidCandidate(StorageError):
    def __init__(self, message, state="invalid"):
        super().__init__(message)
        self.state = state


def configuration(settings=None):
    settings = settings or get_settings()
    endpoint = settings.r2_endpoint or (f"https://{settings.r2_account_id}.r2.cloudflarestorage.com" if settings.r2_account_id else None)
    pending = _required(settings.r2_ai_pending_bucket, "R2_AI_PENDING_BUCKET")
    bucket = _required(settings.r2_bucket, "R2_BUCKET")
    if pending == bucket:
        raise StorageError("AI pending 桶必须与正式图片桶分开")
    base = _required(settings.r2_ai_pending_public_base_url, "R2_AI_PENDING_PUBLIC_BASE_URL").rstrip("/")
    formal = _required(settings.r2_public_base_url, "R2_PUBLIC_BASE_URL").rstrip("/")
    for value in (base, formal):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise StorageError("R2 图片公网地址必须为不带凭据和查询参数的 HTTPS 地址")
    if urlsplit(base).netloc == urlsplit(formal).netloc:
        raise StorageError("AI pending 桶必须使用独立图片域名")
    client = _r2_client(_required(endpoint, "R2_ENDPOINT 或 R2_ACCOUNT_ID"),
        _required(settings.r2_ai_storage_access_key_id, "R2_AI_STORAGE_ACCESS_KEY_ID"),
        _required(settings.r2_ai_storage_secret_access_key, "R2_AI_STORAGE_SECRET_ACCESS_KEY"))
    return client, pending, bucket, base, formal


def key_from_url(url, base):
    """精确匹配公开地址，拒绝查询参数、路径穿越与二次编码。"""
    try:
        target, root = urlsplit(url), urlsplit(base.rstrip("/"))
        if (target.scheme != "https" or target.netloc != root.netloc or target.username or target.password
                or target.query or target.fragment):
            return None
        path, prefix = unquote(target.path), unquote(root.path).rstrip("/") + "/"
        if not path.startswith(prefix):
            return None
        key = path[len(prefix):]
        if not key or len(key) > 500 or "%" in key or "\\" in key or any(part in {"", ".", ".."} for part in key.split("/")):
            return None
        return key
    except (TypeError, ValueError):
        return None


def is_pending_url(url):
    base = get_settings().r2_ai_pending_public_base_url
    if not base:
        return False
    try:
        return urlsplit(url).netloc == urlsplit(base).netloc
    except ValueError:
        return False


def missing(exc):
    return isinstance(exc, ClientError) and (str(exc.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}
        or exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404)


def failure_context(exc):
    """仅取诊断字段，不输出异常原文、第三方消息、响应头或签名信息。"""
    current, seen = exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ClientError):
            response = current.response
            meta = response.get("ResponseMetadata", {})
            return {"operation": current.operation_name, "error_code": response.get("Error", {}).get("Code"),
                "http_status": meta.get("HTTPStatusCode"), "request_id": meta.get("RequestId"),
                "retry_attempts": meta.get("RetryAttempts")}
        current = current.__cause__
    return dict(operation=None, error_code=None, http_status=None, request_id=None, retry_attempts=None)


def _request(operation, stage, request, *, source_bucket=None, source_key=None, target_bucket=None,
             target_key=None, missing_ok=False):
    started = time.monotonic()
    try:
        return request()
    except Exception as exc:
        context = {**failure_context(exc), "operation": operation, "stage": stage,
            "source_bucket": source_bucket, "source_key": source_key,
            "target_bucket": target_bucket, "target_key": target_key,
            "exception_type": type(exc).__name__, "duration_ms": round((time.monotonic() - started) * 1000, 2)}
        # 新对象的目标 HEAD 返回 404 是正常路径，不作为失败告警。
        log = logger.debug if missing_ok and missing(exc) else logger.warning
        log("AI R2 请求失败 | %s", json.dumps(context, ensure_ascii=False))
        raise


def head(client, bucket, key, *, target_bucket=None, target_key=None):
    try:
        return _request("HeadObject", "source_head", lambda: client.head_object(Bucket=bucket, Key=key),
            source_bucket=bucket, source_key=key, target_bucket=target_bucket, target_key=target_key)
    except ClientError as exc:
        if missing(exc):
            raise InvalidCandidate("候选图片不存在或已被清理", "expired") from exc
        raise


def metadata(info, key):
    size = info.get("ContentLength")
    if not isinstance(size, int) or not 0 < size <= MAX_BYTES:
        raise InvalidCandidate("图片为空或超过 5 MiB")
    mime = str(info.get("ContentType") or "").split(";", 1)[0].strip().lower()
    if mime in {"", "application/octet-stream", "binary/octet-stream"}:
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(key.rsplit(".", 1)[-1].lower())
    if mime not in IMAGE_SUFFIXES:
        raise InvalidCandidate("图片类型声明不支持，仅允许 JPEG、PNG、WebP")
    modified, etag = info.get("LastModified"), info.get("ETag")
    if not isinstance(modified, datetime) or not isinstance(etag, str) or not etag:
        raise InvalidCandidate("R2 对象缺少上传时间或版本信息")
    modified = modified.astimezone(timezone.utc).replace(tzinfo=None) if modified.tzinfo else modified
    return size, mime, modified, etag


def copy_object(*, source_bucket, source_key, etag, size, mime, target_key, source_type, source_ref, expires_at=None):
    """先核对已有目标以恢复未知结果；整个方法只有 HEAD 和 CopyObject。"""
    client, _, bucket, _, formal = configuration()
    proof = {"source-type": source_type, "source-ref": str(source_ref), "source-etag": etag, "source-size": str(size)}
    context = dict(source_bucket=source_bucket, source_key=source_key, target_bucket=bucket, target_key=target_key)

    def matches(info):
        return (info.get("ContentLength") == size and info.get("ContentType") == mime
            and all(info.get("Metadata", {}).get(k) == v for k, v in proof.items()))

    try:
        previous = _request("HeadObject", "target_head", lambda: client.head_object(Bucket=bucket, Key=target_key),
            missing_ok=True, **context)
    except ClientError as exc:
        if not missing(exc):
            raise
    else:
        if not matches(previous):
            raise InvalidCandidate("正式图片路径已有不匹配的对象，已停止复制")
        logger.info("AI 图片复制目标复用 | source_type=%s source_ref=%s reused=1", source_type, source_ref)
        return target_key, f"{formal}/{quote(target_key, safe='/')}"
    if expires_at and expires_at <= datetime.utcnow():
        raise InvalidCandidate("候选图片已超过 30 天，无法采用", "expired")
    source = head(client, source_bucket, source_key, target_bucket=bucket, target_key=target_key)
    if source.get("ETag") != etag or source.get("ContentLength") != size:
        raise InvalidCandidate("候选图片已发生变化，请重新检查")
    try:
        _request("CopyObject", "copy", lambda: client.copy_object(Bucket=bucket, Key=target_key,
            CopySource={"Bucket": source_bucket, "Key": source_key}, CopySourceIfMatch=etag,
            MetadataDirective="REPLACE", Metadata=proof, ContentType=mime,
            CacheControl="public, max-age=31536000, immutable", ContentDisposition="inline"), **context)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code"))
        if code in {"PreconditionFailed", "412"}:
            raise InvalidCandidate("候选图片版本已变化，未采用") from exc
        if missing(exc):
            raise InvalidCandidate("候选图片不存在或已被清理", "expired") from exc
        raise
    result = _request("HeadObject", "verify_target", lambda: client.head_object(Bucket=bucket, Key=target_key), **context)
    if not matches(result):
        raise StorageError("正式图片复制结果核验失败，请重试")
    logger.info("AI 图片服务端复制完成 | source_bucket=%s target_bucket=%s bytes=%s", source_bucket, bucket, size)
    return target_key, f"{formal}/{quote(target_key, safe='/')}"
