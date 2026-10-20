"""公开货盘共享规则；所有检查均为数据库检查，不在创建阶段探测图片。"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, update

from .models import (Company, ImageFile, MaterialAsset, ProductTemplate, Role, SupplyAudit,
                     SupplyJob, User)
from .ai_providers import ProviderError, validate_generated_title
from .supply_accounts import supply_user_is_expired
from .tiktok_export import category_base_requirements, validate_attributes

ACTIVE_STATES = ("queued", "running", "retry_wait")
TEMPLATE_FIELDS = ("id", "name", "sku_specifications", "product_description", "size_chart_url",
                   "package_weight", "package_length", "package_width", "package_height",
                   "title_template", "supply_fallback_title")


def now():
    return datetime.utcnow()


def timestamp(value):
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000) if value else None


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def is_manager(user):
    return user.role == Role.COMPANY_ADMIN or (
        user.role in (Role.MEMBER, Role.TEAM_LEADER) and user.supply_admin)


def require_manager(user):
    if not is_manager(user):
        raise HTTPException(403, "没有货盘管理权限")


def require_admin(user):
    if user.role != Role.COMPANY_ADMIN:
        raise HTTPException(403, "仅公司管理员可执行此操作")


def audit(db, user, action, target_type, target_id=None, details=None):
    db.add(SupplyAudit(company_id=user.company_id, user_id=user.id, action=action,
                       target_type=target_type, target_id=target_id, details=details or {}))


def lock_company(db, company_id):
    # 认证依赖先做普通 SELECT。MySQL REPEATABLE READ 下须结束该只读事务，
    # 再获取公司锁，否则等待锁后的候选查询可能仍读取旧的公开状态。
    if db.new or db.dirty or db.deleted:
        raise RuntimeError("公司协调锁必须在业务写入之前获取")
    db.rollback()
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if not company or not company.is_active:
        raise HTTPException(403, "公司已停用或不存在")
    return company


def user_can_run(user, company, at=None):
    return bool(user and company and company.is_active and user.is_active
                and user.company_id == company.id
                and user.role in (Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER, Role.SUPPLY_USER)
                and (user.role != Role.SUPPLY_USER or not supply_user_is_expired(user, at)))


def cancel_user_jobs(db, user_id, reason):
    db.execute(update(SupplyJob).where(SupplyJob.user_id == user_id,
        SupplyJob.state.in_(ACTIVE_STATES)).values(state="cancelled", stage="cancelled",
        error=reason, completed_at=now(), lease_owner=None, lease_expires_at=None,
        export_blob=None,
        lease_epoch=SupplyJob.lease_epoch + 1))


def template_snapshot(template):
    return {field: getattr(template, field) for field in TEMPLATE_FIELDS}


def template_version(snapshot):
    return digest({key: value for key, value in snapshot.items()
                   if key not in {"name", "title_template", "supply_fallback_title"}})


def sizes(snapshot):
    return list(dict.fromkeys(str(value).strip() for value in (
        (snapshot.get("sku_specifications") or {}).get("size", {}).get("options", [])) if str(value).strip())) or ["Default"]


def validate_fallback(title):
    value = " ".join(str(title or "").split())
    if not 25 <= len(value) <= 220 or not re.search(r"[A-Za-z]", value):
        raise HTTPException(400, "货盘基础标题须为 25–220 个字符的英文商品描述")
    try:
        validate_generated_title(value)
    except ProviderError as exc:
        raise HTTPException(400, "货盘基础标题必须是英文单行商品描述") from exc
    return value


def validate_template(template):
    snapshot = template_snapshot(template)
    validate_fallback(snapshot["supply_fallback_title"])
    if not (snapshot["product_description"] or "").strip():
        raise HTTPException(400, "模板缺少产品描述")
    for key in ("package_weight", "package_length", "package_width", "package_height"):
        if snapshot[key] is None or not Decimal(str(snapshot[key])).is_finite() or snapshot[key] <= 0:
            raise HTTPException(400, "模板须填写有效的包裹重量和长宽高")
    return snapshot


def material_snapshot(asset, version, url=None):
    value = {"id": asset.id, "template_id": asset.template_id, "sku": (asset.sku or "").strip(),
             "url": (url if url is not None else asset.url or "").strip(), "name": asset.name, "template_version": version,
             "is_infringing": bool(asset.is_infringing), "style_id": asset.style_id}
    value["version_hash"] = digest(value)
    return value


def eligible_materials(db, company_id, template_id, version, infringement_filter="include"):
    query = select(MaterialAsset).where(MaterialAsset.company_id == company_id,
        MaterialAsset.template_id == template_id, MaterialAsset.supply_listed.is_(True))
    if infringement_filter not in ("exclude", "include", "only"):
        raise HTTPException(422, "不支持的侵权筛选条件")
    if infringement_filter != "include":
        query = query.where(MaterialAsset.is_infringing.is_(infringement_filter == "only"))
    assets = db.scalars(query.order_by(MaterialAsset.id)).all()
    files = {}
    ids = list({asset.image_file_id for asset in assets if asset.image_file_id})
    for offset in range(0, len(ids), 400):
        files.update({item.id: item.url for item in db.scalars(select(ImageFile).where(
            ImageFile.company_id == company_id, ImageFile.id.in_(ids[offset:offset + 400])))})
    return [material_snapshot(asset, version, files.get(asset.image_file_id)) for asset in assets if asset.sku and asset.sku.strip()
            and asset.url and asset.url.strip()]


def validate_strategy(db, user, parameters):
    from .models import TiktokCategoryCatalog
    template = db.get(ProductTemplate, parameters["template_id"])
    if not template or template.company_id != user.company_id or not template.supply_public:
        raise HTTPException(400, "请选择本公司已公开的产品模板")
    snapshot = validate_template(template)
    catalog = db.get(TiktokCategoryCatalog, parameters["category_catalog_id"])
    if not catalog or catalog.company_id != user.company_id or catalog.template_type not in ("tiktok_local", "tiktok_cross_border"):
        raise HTTPException(400, "请选择本公司 TikTok 类目库")
    options = catalog.parsed_options
    try:
        parameters["attributes"] = validate_attributes(parameters["category_name"], parameters["attributes"], options)
        requirements = category_base_requirements(parameters["category_name"], options)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if requirements.get("size_chart") == "Mandatory" and not snapshot["size_chart_url"]:
        raise HTTPException(400, "所选类目要求尺码图，请完善模板")
    price = Decimal(parameters["price"])
    limits = options.get("price_limits", {"min": "0.01", "max": "999999"})
    if not price.is_finite() or not Decimal(str(limits["min"])) <= price <= Decimal(str(limits["max"])):
        raise HTTPException(400, "售价超出 TikTok 模板允许范围")
    if options.get("capabilities", {}).get("supports_cod", True) and parameters["cod"] not in options.get("cod_options", ["Y", "N"]):
        raise HTTPException(400, "COD 选项无效")
    rows = parameters["sku_count"] * parameters["link_count"] * len(sizes(snapshot))
    if rows > 4994:
        raise HTTPException(400, f"预计 {rows} 行，超过 4,994 行限制")
    return template, catalog, snapshot, rows


def unique_title(value, fallback, link_index):
    base = unicodedata.normalize("NFKC", " ".join(str(value or "").split())).strip('"\' ')
    try:
        validate_generated_title(base)
    except ProviderError:
        base = validate_fallback(fallback)
    suffix = f" - L{link_index + 1:02d}"
    return base[:255 - len(suffix)].rstrip() + suffix


def normalize_title(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def job_payload(job, user_name=None):
    return {"id": job.id, "strategy_id": job.strategy_id, "user_id": job.user_id,
        "user_name": user_name or job.snapshot.get("user_name"), "agent_name": job.agent_name,
        "state": job.state, "stage": job.stage, "progress": job.progress or {}, "error": job.error,
        "created_at": timestamp(job.created_at), "completed_at": timestamp(job.completed_at),
        "output_expires_at": timestamp(job.output_expires_at),
        "filename": f"TikTok货盘_{job.id}.xlsx", "file_expired": bool(job.output_deleted_at or (
            job.output_expires_at and job.output_expires_at <= now()))}
