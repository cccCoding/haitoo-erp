"""图片文件去重、短时上传授权和素材创建；不保存图片状态。"""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .credentials import decrypt_secret, encrypt_secret
from .image_download import MAX_IMAGE_BYTES, ImageDownloadError, decode_image, download_image
from .models import Company, ImageAddress, ImageFile, MaterialAsset, ProductLibraryProduct, ProductLibrarySource
from .storage import (StorageError, create_temporary_image_upload, r2_object_key,
    read_image_object, save_content_image)


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def by_content(db, company_id: int, sha256: str, *, current: bool = False):
    stmt = select(ImageFile).where(ImageFile.company_id == company_id, ImageFile.sha256 == sha256)
    return db.scalar(stmt.with_for_update() if current else stmt)


def by_url(db, company_id: int, url: str, *, current: bool = False):
    stmt = select(ImageAddress).where(ImageAddress.company_id == company_id, ImageAddress.url_hash == digest(url))
    address = db.scalar(stmt.with_for_update() if current else stmt)
    if address:
        if address.url != url:
            raise HTTPException(409, "图片地址摘要冲突")
        stmt = select(ImageFile).where(ImageFile.id == address.image_file_id, ImageFile.company_id == company_id)
        return db.scalar(stmt.with_for_update() if current else stmt)
    return None


def add_address(db, company_id: int, url: str, image_file: ImageFile):
    existing = by_url(db, company_id, url)
    if existing:
        return existing
    try:
        with db.begin_nested():
            db.add(ImageAddress(company_id=company_id, url=url, url_hash=digest(url), image_file_id=image_file.id))
            db.flush()
    except IntegrityError:
        existing = by_url(db, company_id, url, current=True)
        if not existing:
            raise
        return existing
    return image_file


def register_bytes(db, company_id: int, content: bytes, *, source_url: str | None = None,
                   preserve_url: str | None = None, max_bytes: int | None = MAX_IMAGE_BYTES) -> ImageFile:
    try:
        mime = decode_image(content, max_bytes=max_bytes)
        sha = digest(content)
        image_file = by_content(db, company_id, sha)
        if image_file is None:
            key = r2_object_key(preserve_url) if preserve_url else None
            # 临时区会过期，创作素材区仍可由浏览器 PUT；均不能充当正式文件。
            if key and (key.startswith(("image-upload-tmp/", "creative/"))
                    or f"/company/{company_id}/" not in f"/{key}"):
                key = None
            if key:
                url = preserve_url
            else:
                key, url = save_content_image(content, mime, company_id, sha)
            try:
                with db.begin_nested():
                    image_file = ImageFile(company_id=company_id, sha256=sha, object_key=key,
                        url=url, mime_type=mime, size_bytes=len(content), created_at=datetime.utcnow())
                    db.add(image_file)
                    db.flush()
            except IntegrityError:
                image_file = by_content(db, company_id, sha, current=True)
                if image_file is None:
                    raise
        add_address(db, company_id, image_file.url, image_file)
        if preserve_url:
            add_address(db, company_id, preserve_url, image_file)
        if source_url:
            image_file = add_address(db, company_id, source_url, image_file)
        db.commit()
        return image_file
    except (ImageDownloadError, StorageError) as exc:
        db.rollback()
        raise HTTPException(400 if isinstance(exc, ImageDownloadError) else 503, str(exc)) from exc


def ingest_url(db, company_id: int, url: str, *, max_r2_bytes: int | None = MAX_IMAGE_BYTES) -> ImageFile:
    url = url.strip()
    existing = by_url(db, company_id, url)
    if existing:
        return existing
    # 网络请求前释放只读事务，不持有业务行锁。
    db.commit()
    try:
        key = r2_object_key(url)
        content = read_image_object(key, max_bytes=max_r2_bytes) if key else asyncio.run(download_image(url))
        owned = key and f"/company/{company_id}/" in f"/{key}"
        return register_bytes(db, company_id, content, source_url=url, preserve_url=url if owned else None,
            max_bytes=max_r2_bytes if key else MAX_IMAGE_BYTES)
    except (ImageDownloadError, StorageError) as exc:
        raise HTTPException(400 if isinstance(exc, ImageDownloadError) else 503, str(exc)) from exc


def file_ticket(user, image_file: ImageFile) -> str:
    return encrypt_secret(json.dumps({"user": user.id, "company": user.company_id,
        "file": image_file.id, "exp": int(time.time()) + 1800, "purpose": "image-file"}))


def _ticket(user, token: str, purpose: str) -> dict:
    try:
        value = json.loads(decrypt_secret(token))
        if (value.get("user") != user.id or value.get("company") != user.company_id
                or value.get("purpose") != purpose or value.get("exp", 0) <= time.time()):
            raise ValueError()
        return value
    except Exception as exc:
        raise HTTPException(400, "图片授权无效或已过期，请重新选择文件") from exc


def ticket_file(db, user, token: str) -> ImageFile:
    value = _ticket(user, token, "image-file")
    image_file = db.scalar(select(ImageFile).where(ImageFile.id == value["file"], ImageFile.company_id == user.company_id))
    if image_file is None:
        raise HTTPException(400, "图片文件不存在")
    return image_file


def prepare_upload(db, user, *, sha256: str, mime_type: str, size: int, category: str = "material") -> dict:
    existing = by_content(db, user.company_id, sha256)
    if existing:
        duplicate = db.scalar(select(MaterialAsset.id).where(MaterialAsset.company_id == user.company_id,
            MaterialAsset.image_file_id == existing.id).limit(1)) if category == "material" else None
        return {"file_token": file_ticket(user, existing), "url": existing.url, "duplicate": bool(duplicate)}
    try:
        target = create_temporary_image_upload(mime_type, size, user.company_id)
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc
    token = encrypt_secret(json.dumps({"user": user.id, "company": user.company_id, "purpose": "image-upload",
        "key": r2_object_key(target["url"]), "sha256": sha256, "size": size,
        "mime": mime_type, "category": category, "exp": int(time.time()) + 900}))
    return {"upload_url": target["upload_url"], "upload_token": token, "duplicate": False}


def finish_upload(db, user, *, upload_token: str | None, file_token: str | None,
                  category: str = "material") -> ImageFile:
    if bool(file_token) == bool(upload_token):
        raise HTTPException(400, "必须提供一个图片授权")
    if file_token:
        return ticket_file(db, user, file_token)
    value = _ticket(user, upload_token, "image-upload")
    if value.get("category") != category or not value.get("key", "").startswith(f"image-upload-tmp/company/{user.company_id}/"):
        raise HTTPException(400, "图片上传用途不匹配")
    try:
        content = read_image_object(value["key"], min(value["size"], 3 * 1024 * 1024))
        if len(content) != value["size"] or digest(content) != value["sha256"] or decode_image(content) != value["mime"]:
            raise HTTPException(400, "图片实际内容与上传信息不一致")
        return register_bytes(db, user.company_id, content)
    except (StorageError, ImageDownloadError) as exc:
        raise HTTPException(400, str(exc)) from exc


def create_material(db, *, image_file: ImageFile, template, owner, request_key: str,
                    force_create: bool = False, source_type: str = "local_upload",
                    source_task_id: int | None = None, name: str = "素材", commit: bool = True) -> dict:
    from .main import add_material_asset_with_sku
    company_id, file_id = image_file.company_id, image_file.id
    if template.company_id != company_id or owner.company_id != company_id:
        raise HTTPException(403, "不能使用其他公司的图片")
    # 所有入口按文件行串行创建；文件写入完成后才开始业务事务。
    if commit:
        db.commit()
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None or not company.is_active:
        raise HTTPException(403, "公司已停用或不存在")
    locked = db.scalar(select(ImageFile).where(ImageFile.id == file_id,
        ImageFile.company_id == company_id).with_for_update())
    prior = db.scalar(select(MaterialAsset).where(MaterialAsset.company_id == company_id,
        MaterialAsset.creation_request_key == request_key).with_for_update())
    if prior:
        if prior.image_file_id != file_id or prior.template_id != template.id or prior.claimed_by != owner.id:
            raise HTTPException(409, "请求标识已用于不同的素材创建")
        if commit:
            db.commit()
        return {"outcome": "created", "replayed": True, "asset_id": prior.id}
    duplicate = db.scalar(select(MaterialAsset.id).where(MaterialAsset.company_id == company_id,
        MaterialAsset.image_file_id == file_id).limit(1).with_for_update())
    if duplicate and not force_create:
        if commit:
            db.commit()
        return {"outcome": "duplicate"}
    asset = add_material_asset_with_sku(db, template=template, owner=owner, company_id=company_id,
        source_task_id=source_task_id, source_type=source_type, url=locked.url, name=name,
        image_file_id=file_id, creation_request_key=request_key)
    if commit:
        db.commit()
    else:
        db.flush()
    return {"outcome": "created", "asset_id": asset.id}


def ingest_cross_url(db, target_company_id: int, source_company_id: int, url: str) -> ImageFile:
    existing = by_url(db, target_company_id, url)
    if existing:
        return existing
    source_file = by_url(db, source_company_id, url)
    if source_file:
        existing = by_content(db, target_company_id, source_file.sha256)
        if existing:
            add_address(db, target_company_id, url, existing)
            db.commit()
            return existing
    db.commit()
    try:
        key = source_file.object_key if source_file else r2_object_key(url)
        content = read_image_object(key) if key else asyncio.run(download_image(url))
        return register_bytes(db, target_company_id, content, source_url=url)
    except (StorageError, ImageDownloadError) as exc:
        raise HTTPException(400 if isinstance(exc, ImageDownloadError) else 503, str(exc)) from exc


def product_library_image_urls(db, company_id: int, urls: list[str]) -> set[str]:
    """订单产品图片保留来源链接，仅认可当前公司的产品记录。"""
    found = set()
    for offset in range(0, len(urls), 400):
        found.update(db.scalars(select(ProductLibraryProduct.image_url).join(
            ProductLibrarySource, ProductLibrarySource.id == ProductLibraryProduct.source_id).where(
            ProductLibraryProduct.company_id == company_id, ProductLibrarySource.company_id == company_id,
            ProductLibraryProduct.image_url.in_(urls[offset:offset + 400]))))
    return found


def resolve_export_images(db, company_id: int, products: list[dict]) -> None:
    """只读取数据库映射；不在导出路径下载、复制或探测图片。"""
    urls = list(dict.fromkeys(url for product in products for url in [
        *(product.get("image_urls") or []),
        *(item.get("image_url") for item in product.get("sku_images") or []),
        product.get("size_chart_url")] if url))
    mappings = {}
    for offset in range(0, len(urls), 400):
        records = db.execute(select(ImageAddress, ImageFile).join(ImageFile, ImageFile.id == ImageAddress.image_file_id).where(
            ImageAddress.company_id == company_id, ImageFile.company_id == company_id,
            ImageAddress.url_hash.in_([digest(url) for url in urls[offset:offset + 400]]))).all()
        mappings.update({address.url: image_file.url for address, image_file in records})
    missing = [url for url in urls if url not in mappings]
    # 订单导入只存原链接；允许这些已登记业务来源直接导出，不触发图片转存。
    mappings.update({url: url for url in product_library_image_urls(db, company_id, missing)})
    # 草稿保留创建时的订单图片快照，后续重新导入换图不影响已有草稿。
    original_urls = {url for product in products for url in product.pop("original_image_urls", [])}
    mappings.update({url: url for url in missing if url in original_urls})
    missing = [url for url in missing if url not in mappings]
    if missing:
        raise HTTPException(400, "以下图片尚未保存到图片存储，请重新上传或导入：\n" + "\n".join(missing))
    for product in products:
        product["image_urls"] = [mappings[url] for url in product.get("image_urls") or []]
        product["sku_images"] = [{**item, "image_url": mappings[item["image_url"]]} for item in product.get("sku_images") or []]
        if product.get("size_chart_url"):
            product["size_chart_url"] = mappings[product["size_chart_url"]]
        if product.get("base_sku_by_image"):
            product["base_sku_by_image"] = {mappings[url]: sku for url, sku in product["base_sku_by_image"].items()}
