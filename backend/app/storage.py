"""Cloudflare R2 图片存储。

R2 兼容 S3 API。业务数据库只保存 ``public_url``，对象 key 由本模块生成，
不再依赖 API 容器本地磁盘或 ``/media`` 静态目录。
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
import logging
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import Settings, get_settings


logger = logging.getLogger(__name__)


class StorageError(Exception):
    """对象存储不可用或配置不完整。"""


IMAGE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _required(value: str | None, name: str) -> str:
    if not value:
        raise StorageError(f"未配置 {name}，无法上传图片到 Cloudflare R2")
    return value


@lru_cache
def _r2_client(endpoint: str, access_key_id: str, secret_access_key: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _configuration(settings: Settings) -> tuple[str, str, str, str, str]:
    endpoint = settings.r2_endpoint
    if not endpoint and settings.r2_account_id:
        endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    return (
        _required(endpoint, "R2_ENDPOINT 或 R2_ACCOUNT_ID").rstrip("/"),
        _required(settings.r2_access_key_id, "R2_ACCESS_KEY_ID"),
        _required(settings.r2_secret_access_key, "R2_SECRET_ACCESS_KEY"),
        _required(settings.r2_bucket, "R2_BUCKET"),
        _required(settings.r2_public_base_url, "R2_PUBLIC_BASE_URL").rstrip("/"),
    )


def is_public_r2_url(url: str, settings: Settings | None = None) -> bool:
    base_url = (settings or get_settings()).r2_public_base_url
    return bool(base_url and url.startswith(f"{base_url.rstrip('/')}/"))


def r2_object_key(url: str, settings: Settings | None = None) -> str | None:
    """从当前 R2 公网 URL 提取对象 key，拒绝相似域名和路径穿越。"""
    base_url = (settings or get_settings()).r2_public_base_url
    if not base_url:
        return None
    base = urlsplit(base_url.rstrip("/"))
    candidate = urlsplit(url)
    if candidate.scheme != base.scheme or candidate.netloc != base.netloc:
        return None
    base_path = unquote(base.path).rstrip("/")
    candidate_path = unquote(candidate.path)
    prefix = f"{base_path}/"
    if not candidate_path.startswith(prefix):
        return None
    key = candidate_path[len(prefix):]
    if not key or any(part in {"", ".", ".."} for part in key.split("/")):
        return None
    return key


def is_company_r2_url(url: str, company_id: int, category: str) -> bool:
    """确认直传对象属于当前公司和指定业务目录。"""
    key = r2_object_key(url)
    return bool(key and key.startswith(f"{category}/company/{company_id}/"))


def _log_r2_failure(
    operation: str,
    exc: Exception,
    *,
    endpoint: str | None,
    bucket: str | None,
    key: str | None = None,
) -> None:
    """记录 R2 故障上下文，但不输出访问密钥或请求签名。"""
    context = {
        "operation": operation,
        "endpoint": endpoint,
        "bucket": bucket,
        "key": key,
        "exception_type": type(exc).__name__,
        "exception": str(exc),
    }
    if isinstance(exc, ClientError):
        # ClientError.response 是 boto3 保留的第三方响应，包含 HTTP 状态码、
        # Cloudflare/S3 错误码与消息、RequestId 和响应头，不包含客户端密钥。
        context["response"] = exc.response
    logger.error("Cloudflare R2 请求失败：%r", context, exc_info=True)


def upload_image_bytes(content: bytes, mime_type: str, company_id: int | None, category: str) -> str:
    """同步写入 R2，并返回可被 AI、妙手和浏览器读取的完整 HTTPS URL。"""
    suffix = IMAGE_SUFFIXES.get(mime_type)
    if not suffix:
        raise StorageError("仅支持 JPG、PNG 或 WebP 图片")
    owner = str(company_id) if company_id is not None else "platform"
    # 类型置于 key 首段，便于在 R2 生命周期规则中按 generated/、material/ 等前缀清理。
    key = f"{category}/company/{owner}/{uuid4().hex}{suffix}"
    settings = get_settings()
    endpoint_hint = settings.r2_endpoint
    if not endpoint_hint and settings.r2_account_id:
        endpoint_hint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    try:
        endpoint, access_key_id, secret_access_key, bucket, public_base_url = _configuration(settings)
        _r2_client(endpoint, access_key_id, secret_access_key).put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=mime_type,
            CacheControl="public, max-age=31536000, immutable",
            ContentDisposition="inline",
        )
    except Exception as exc:  # botocore 的异常类型覆盖网络、鉴权与服务端错误。
        _log_r2_failure(
            "put_object",
            exc,
            endpoint=endpoint_hint,
            bucket=settings.r2_bucket,
            key=key,
        )
        if isinstance(exc, StorageError):
            raise
        raise StorageError(f"上传图片到 Cloudflare R2 失败：{exc}") from exc
    return f"{public_base_url}/{quote(key, safe='/')}"


def create_image_upload_url(mime_type: str, content_length: int, company_id: int | None, category: str) -> dict[str, str]:
    """创建单对象、短时有效的 R2 PUT URL，避免大批图片经 API 容器中转。"""
    suffix = IMAGE_SUFFIXES.get(mime_type)
    if not suffix:
        raise StorageError("仅支持 JPG、PNG 或 WebP 图片")
    endpoint, access_key_id, secret_access_key, bucket, public_base_url = _configuration(get_settings())
    owner = str(company_id) if company_id is not None else "platform"
    key = f"{category}/company/{owner}/{uuid4().hex}{suffix}"
    try:
        upload_url = _r2_client(endpoint, access_key_id, secret_access_key).generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": mime_type, "ContentLength": content_length},
            ExpiresIn=900,
        )
    except Exception as exc:
        raise StorageError(f"创建 R2 直传地址失败：{exc}") from exc
    return {"upload_url": upload_url, "url": f"{public_base_url}/{quote(key, safe='/')}"}


async def upload_image_bytes_async(content: bytes, mime_type: str, company_id: int | None, category: str) -> str:
    """在异步请求/任务中避免阻塞事件循环。"""
    return await asyncio.to_thread(upload_image_bytes, content, mime_type, company_id, category)
