"""只保存货盘最终 Excel 的私有 R2 文件，素材图片保持原 URL。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

from botocore.exceptions import ClientError

from .storage import ExportMissingError, StorageError, _export_configuration, _r2_client


_KEY_PATTERN = re.compile(r"supply-exports/company/[1-9][0-9]*/jobs/[1-9][0-9]*/[1-9][0-9]*/[a-f0-9]{32}\.xlsx\Z")


def _location(key: str):
    if not isinstance(key, str) or not _KEY_PATTERN.fullmatch(key):
        raise StorageError("货盘任务文件路径不合法")
    endpoint, access, secret, bucket = _export_configuration()
    return _r2_client(endpoint, access, secret), bucket


def upload_supply_export(company_id: int, job_id: int, epoch: int, filename: str, content: bytes) -> dict:
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (company_id, job_id, epoch)):
        raise StorageError("货盘任务文件归属不合法")
    if not content:
        raise StorageError("不能上传空货盘 Excel")
    key = f"supply-exports/company/{company_id}/jobs/{job_id}/{epoch}/{uuid4().hex}.xlsx"
    client, bucket = _location(key)
    checksum = hashlib.sha256(content).hexdigest()
    try:
        client.put_object(Bucket=bucket, Key=key, Body=content,
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            CacheControl="private, no-store", Metadata={"sha256": checksum})
        response = client.head_object(Bucket=bucket, Key=key)
        if response.get("ContentLength") != len(content) or response.get("Metadata", {}).get("sha256") != checksum:
            raise StorageError("上传后的货盘 Excel 校验失败")
        # Metadata 由客户端提供，不能代替对存储后的实际字节做校验。
        read_supply_export(key, checksum, len(content))
    except Exception as exc:
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except Exception:
            pass
        if isinstance(exc, StorageError):
            raise
        raise StorageError("上传货盘 Excel 到 R2 失败") from exc
    return {"key": key, "sha256": checksum, "size": len(content)}


def read_supply_export(key: str, expected_sha256: str, expected_size: int) -> bytes:
    client, bucket = _location(key)
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size <= 0 or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256 or ""):
        raise StorageError("货盘任务文件校验信息不合法")
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            content = body.read(expected_size + 1)
        finally:
            body.close()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "NotFound", "404"}:
            raise ExportMissingError("货盘 Excel 已删除或过期") from exc
        raise StorageError("读取货盘 Excel 失败，请稍后重试") from exc
    except Exception as exc:
        raise StorageError("读取货盘 Excel 失败，请稍后重试") from exc
    if len(content) != expected_size or hashlib.sha256(content).hexdigest() != expected_sha256:
        raise StorageError("货盘 Excel 文件校验失败")
    return content


def delete_supply_export(key: str) -> None:
    client, bucket = _location(key)
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise StorageError("清理货盘 Excel 失败") from exc


def list_supply_exports(before: datetime) -> Iterator[str]:
    """分页列出超过指定年龄的货盘对象；调用者核对数据库引用后再删除。"""
    if not isinstance(before, datetime):
        raise StorageError("货盘文件清理时间不合法")
    cutoff = before.replace(tzinfo=timezone.utc) if before.tzinfo is None else before.astimezone(timezone.utc)
    endpoint, access, secret, bucket = _export_configuration()
    client = _r2_client(endpoint, access, secret)
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="supply-exports/"):
            for item in page.get("Contents", []):
                key = item.get("Key")
                modified = item.get("LastModified")
                if not isinstance(key, str) or not _KEY_PATTERN.fullmatch(key) or not isinstance(modified, datetime):
                    continue
                modified = modified.replace(tzinfo=timezone.utc) if modified.tzinfo is None else modified.astimezone(timezone.utc)
                if modified < cutoff:
                    yield key
    except Exception as exc:
        raise StorageError("列举货盘 Excel 失败，请稍后重试") from exc
