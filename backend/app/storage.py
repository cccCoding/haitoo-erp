"""Cloudflare R2 图片存储。

R2 兼容 S3 API。业务数据库只保存 ``public_url``，对象 key 由本模块生成，
不再依赖 API 容器本地磁盘或 ``/media`` 静态目录。
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from urllib.parse import quote
from uuid import uuid4

import boto3
from botocore.config import Config

from .config import Settings, get_settings


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


def upload_image_bytes(content: bytes, mime_type: str, company_id: int | None, category: str) -> str:
    """同步写入 R2，并返回可被 AI、妙手和浏览器读取的完整 HTTPS URL。"""
    suffix = IMAGE_SUFFIXES.get(mime_type)
    if not suffix:
        raise StorageError("仅支持 JPG、PNG 或 WebP 图片")
    endpoint, access_key_id, secret_access_key, bucket, public_base_url = _configuration(get_settings())
    owner = str(company_id) if company_id is not None else "platform"
    # 类型置于 key 首段，便于在 R2 生命周期规则中按 generated/、material/ 等前缀清理。
    key = f"{category}/company/{owner}/{uuid4().hex}{suffix}"
    try:
        _r2_client(endpoint, access_key_id, secret_access_key).put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=mime_type,
            CacheControl="public, max-age=31536000, immutable",
            ContentDisposition="inline",
        )
    except Exception as exc:  # botocore 的异常类型覆盖网络、鉴权与服务端错误。
        raise StorageError(f"上传图片到 Cloudflare R2 失败：{exc}") from exc
    return f"{public_base_url}/{quote(key, safe='/')}"


async def upload_image_bytes_async(content: bytes, mime_type: str, company_id: int | None, category: str) -> str:
    """在异步请求/任务中避免阻塞事件循环。"""
    return await asyncio.to_thread(upload_image_bytes, content, mime_type, company_id, category)
