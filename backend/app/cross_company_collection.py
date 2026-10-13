"""仅公司管理员可用的跨公司只读选品与事务入库。"""
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .material_import import validate_image_link
from .models import (Company, CrossCompanyCollectionBatch, CrossCompanyCollectionItem,
    CrossCompanyCollectionPermissionLog, MaterialAsset, ProductLibraryProduct,
    ProductTemplate, Role, User)
from .security import current_user, require_roles

router = APIRouter()
Library = Literal["material", "product"]
Category = Literal["products", "top7", "top15", "top30", "potential", "hot", "booming"]


class PermissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class CollectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_company_id: PositiveInt
    source_library: Library
    record_ids: list[PositiveInt] = Field(min_length=1, max_length=1000)
    template_id: PositiveInt
    allow_recollect: bool = False

    @field_validator("record_ids")
    @classmethod
    def distinct_ids(cls, values):
        values = sorted(set(values))
        if len(values) > 100:
            raise ValueError("每批最多采集 100 条不同记录")
        return values


def authorized_company(user, db, *, lock=False):
    if user.role != Role.COMPANY_ADMIN or user.company_id is None:
        raise HTTPException(403, "仅获授权公司的公司管理员可采集")
    stmt = select(Company).where(Company.id == user.company_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update()
    company = db.scalar(stmt)
    if not company or not company.is_active or not company.cross_company_collect_enabled:
        raise HTTPException(403, "本公司未开启采集或已停用")
    return company


def source_company(db, target_id, source_id, *, lock=False):
    stmt = select(Company).where(Company.id == source_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update()
    company = db.scalar(stmt)
    if not company or not company.is_active or company.id == target_id:
        raise HTTPException(404, "来源公司不存在、已停用或为本公司")
    return company


@router.put("/admin/companies/{company_id}/cross-company-collection")
def set_permission(company_id: int, payload: PermissionInput,
                   user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update().execution_options(populate_existing=True))
    if not company:
        raise HTTPException(404, "公司不存在")
    if company.cross_company_collect_enabled != payload.enabled:
        db.add(CrossCompanyCollectionPermissionLog(company_id=company.id, changed_by=user.id,
            previous_enabled=company.cross_company_collect_enabled, enabled=payload.enabled))
        company.cross_company_collect_enabled = payload.enabled
    db.commit()
    return {"enabled": company.cross_company_collect_enabled}


@router.get("/cross-company-collection/capability")
def capability(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        authorized_company(user, db)
    except HTTPException:
        return {"enabled": False}
    return {"enabled": True}


@router.get("/cross-company-collection/companies")
def companies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = authorized_company(user, db)
    return [{"id": c.id, "name": c.name} for c in db.scalars(select(Company).where(
        Company.id != target.id, Company.is_active.is_(True)).order_by(Company.name, Company.id))]


@router.get("/cross-company-collection/filters")
def filters(source_company_id: int = Query(ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = authorized_company(user, db)
    source_company(db, target.id, source_company_id)
    return {"templates": [{"id": t.id, "name": t.name} for t in db.scalars(select(ProductTemplate).where(
        ProductTemplate.company_id == source_company_id).order_by(ProductTemplate.name))]}


@router.get("/cross-company-collection/items")
def items(source_company_id: int = Query(ge=1), source_library: Library = "material",
          page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
          template_id: int | None = Query(None, ge=1), unmatched: bool = False,
          source_type: Literal["", "ai_created", "local_upload", "imported", "cross_company"] = "",
          usage_status: Literal["all", "unused", "used"] = "all",
          created_from: datetime | None = None, created_to: datetime | None = None,
          sku: str | None = None, category: Category = "products",
          user: User = Depends(current_user), db: Session = Depends(get_db)):
    from . import main
    target = authorized_company(user, db)
    source_company(db, target.id, source_company_id)
    if template_id is not None:
        if unmatched:
            raise HTTPException(400, "不能同时选择已匹配模板和未匹配")
        template = db.get(ProductTemplate, template_id)
        if not template or template.company_id != source_company_id:
            raise HTTPException(404, "筛选模板不属于来源公司")
    scope = SimpleNamespace(company_id=source_company_id, role=Role.COMPANY_ADMIN)
    if source_library == "material":
        result = main.list_material_assets(page=page, page_size=page_size, creator_id=None,
            template_id=template_id, usage_status=usage_status, source_type=source_type,
            created_from=created_from, created_to=created_to, user=scope, db=db)
        allowed = ("id", "sku", "name", "url", "template_id", "template_name", "source_type", "usage_status", "created_at")
    else:
        if category == "products":
            result = main.list_product_library(page=page, page_size=page_size,
                platform=None, site=None, shop_name=None, sku=sku, template_id=template_id,
                unmatched=unmatched, source_ids=None, creator_id=None, user=scope, db=db)
        else:
            # 在聚合前应用模板/SKU条件，保持销量、代表记录与榜单的一致范围。
            from datetime import timedelta
            from .models import ProductLibraryDailySnapshot
            from .product_library_statistics import sku_statistics, order_facts
            snapshot = db.scalar(select(ProductLibraryDailySnapshot).where(
                ProductLibraryDailySnapshot.company_id == source_company_id,
                ProductLibraryDailySnapshot.is_complete.is_(True)).order_by(ProductLibraryDailySnapshot.snapshot_date.desc()).limit(1))
            if snapshot is None:
                result = {"items": [], "total": 0, "page": page, "page_size": page_size, "snapshot_date": None, "through_date": None}
            else:
                conditions = main.product_library_statistics_scope(scope)
                if template_id is not None:
                    conditions.append(ProductLibraryProduct.template_id == template_id)
                elif unmatched:
                    conditions.append(ProductTemplate.id.is_(None))
                if sku and sku.strip():
                    prefix = func.substr(ProductLibraryProduct.sku, 1, len(sku.strip()))
                    if db.get_bind().dialect.name in {"mysql", "mariadb"}:
                        prefix = prefix.collate("utf8mb4_bin")
                    conditions.append(prefix == sku.strip())
                result = sku_statistics(db, conditions, order_facts(snapshot, category), page=page, page_size=page_size, category=category)
                result.update(snapshot_date=snapshot.snapshot_date.isoformat(), through_date=(snapshot.snapshot_date - timedelta(days=1)).isoformat())
        allowed = ("id", "sku", "title", "image_url", "template_id", "template", "sales_quantity", "rank")
    urls = [r.get("url", r.get("image_url", "")) for r in result["items"]]
    # MySQL 的默认字符排序规则会忽略大小写；最终使用 Python 精确匹配。
    existing = set(db.scalars(select(MaterialAsset.url).where(MaterialAsset.company_id == target.id, MaterialAsset.url.in_(urls)))) if urls else set()
    return {k: result[k] for k in ("total", "page", "page_size", "snapshot_date", "through_date") if k in result} | {
        "items": [{k: row.get(k) for k in allowed} | {"already_collected": url in existing} for row, url in zip(result["items"], urls)]}


def replay(batch, fingerprint):
    if batch.request_hash != fingerprint:
        raise HTTPException(409, "相同请求标识不能用于不同采集内容")
    return batch.result


@router.post("/cross-company-collection/collect")
def collect(payload: CollectionInput, idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    from . import main
    # 两家公司按 ID 顺序锁定，避免相互采集时死锁；撤销权限共用公司行锁。
    authorized_company(user, db)
    db.scalars(select(Company).where(Company.id.in_(sorted({user.company_id, payload.source_company_id})))
        .order_by(Company.id).with_for_update().execution_options(populate_existing=True)).all()
    # MySQL REPEATABLE READ 下必须用当前读重查授权，不能读事务开始时的旧快照。
    target = authorized_company(user, db, lock=True)
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
    batch_stmt = select(CrossCompanyCollectionBatch).where(CrossCompanyCollectionBatch.company_id == target.id,
        CrossCompanyCollectionBatch.request_key == idempotency_key).with_for_update()
    batch = db.scalar(batch_stmt)
    if batch:
        return replay(batch, fingerprint)
    source = source_company(db, target.id, payload.source_company_id, lock=True)
    template = main.get_company_template(db, user, payload.template_id)
    main.validate_material_sku_source(template, user)
    model = MaterialAsset if payload.source_library == "material" else ProductLibraryProduct
    records = list(db.scalars(select(model).where(model.company_id == source.id, model.id.in_(payload.record_ids))
        .order_by(model.id).with_for_update().execution_options(populate_existing=True)))
    found = {r.id for r in records}
    missing = [i for i in payload.record_ids if i not in found]
    if missing:
        raise HTTPException(400, f"来源记录不存在或不属于来源公司：{missing}")
    entries = []
    invalid = []
    for record in records:
        raw_url = record.url if payload.source_library == "material" else record.image_url
        try:
            validate_image_link(raw_url, record.id)
        except ValueError:
            invalid.append(record.id)
        entries.append((record, raw_url))
    if invalid:
        raise HTTPException(400, f"来源图片链接无效，请取消选择后重试：{invalid}")
    existing = set(db.scalars(select(MaterialAsset.url).where(MaterialAsset.company_id == target.id,
        MaterialAsset.url.in_([url for _, url in entries])).with_for_update()))
    duplicate = [r.id for r, url in entries if url in existing]
    if duplicate and not payload.allow_recollect:
        raise HTTPException(409, f"图片已存在，请明确选择再次采集：{duplicate}")
    try:
        # SQLite 首个 SKU 保存点同样必须位于整批事务内。
        with db.begin_nested():
            batch = CrossCompanyCollectionBatch(company_id=target.id, created_by=user.id, template_id=template.id,
                request_key=idempotency_key, request_hash=fingerprint, result={})
            db.add(batch)
            db.flush()
            asset_ids = []
            for record, url in entries:
                name = (record.name if payload.source_library == "material" else record.title) or record.sku or "采集素材"
                asset = main.add_material_asset_with_sku(db, template=template, owner=user, company_id=target.id,
                    source_task_id=None, url=url, name=name[:180], source_type="cross_company")
                asset_ids.append(asset.id)
                db.add(CrossCompanyCollectionItem(batch_id=batch.id, company_id=target.id, material_asset_id=asset.id,
                    source_company_id=source.id, source_company_name=source.name, source_library=payload.source_library,
                    source_record_id=record.id, source_sku=record.sku, source_url=url, source_name=name[:500]))
            batch.result = {"batch_id": batch.id, "collected": len(asset_ids), "material_asset_ids": asset_ids}
        db.commit()
        return batch.result
    except IntegrityError:
        db.rollback()
        batch = db.scalar(batch_stmt)
        if batch:
            return replay(batch, fingerprint)
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/cross-company-collection/history")
def history(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
            template_id: int | None = Query(None, gt=0),
            user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    from .main import timestamp_ms
    company = db.get(Company, user.company_id)
    if not company or not company.is_active:
        raise HTTPException(403, "本公司已停用")
    # 历史为本公司自有数据，撤销采集授权后仍可查阅。
    stmt = select(CrossCompanyCollectionItem, CrossCompanyCollectionBatch, User.name).join(
        CrossCompanyCollectionBatch, CrossCompanyCollectionBatch.id == CrossCompanyCollectionItem.batch_id).outerjoin(
        User, User.id == CrossCompanyCollectionBatch.created_by).where(CrossCompanyCollectionItem.company_id == company.id)
    if template_id is not None:
        template = db.scalar(select(ProductTemplate).where(ProductTemplate.id == template_id,
            ProductTemplate.company_id == company.id))
        if not template:
            raise HTTPException(404, "目标模板不存在或不属于本公司")
        stmt = stmt.where(CrossCompanyCollectionBatch.template_id == template_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(CrossCompanyCollectionItem.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"id": item.id, "batch_id": batch.id, "material_asset_id": item.material_asset_id,
         "source_company_name": item.source_company_name, "source_library": item.source_library,
         "source_sku": item.source_sku, "source_name": item.source_name, "source_url": item.source_url,
         "template_id": batch.template_id, "created_by_name": name or "历史账号已删除", "created_at": timestamp_ms(item.created_at)}
        for item, batch, name in rows]}
