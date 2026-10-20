"""公司公开货盘 API。素材公开不涉及图片搬运或自动探测。"""
import copy
import secrets
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, PositiveInt, field_validator
from sqlalchemy import case, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .ai_providers import DEEPSEEK_TITLE_MODEL
from .credentials import decrypt_secret, encrypt_secret
from .database import get_db
from .models import (Company, MaterialAsset, OperatorGroup, ProductTemplate, Role, SupplyAgent, SupplyAudit,
                     SupplyJob, SupplyJobMaterial, SupplyStrategy,
                     TemplateGroup, TiktokCategoryCatalog, User)
from .security import current_user, hash_password
from .supply_accounts import add_calendar_months, supply_user_is_expired
from .supply_common import (ACTIVE_STATES, audit, cancel_user_jobs,
    digest, eligible_materials, is_manager, job_payload,
    lock_company, now, require_admin, require_manager, sizes, template_snapshot,
    template_version, timestamp, user_can_run, validate_fallback, validate_strategy, validate_template)

router = APIRouter(prefix="/supply", tags=["公开货盘"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentInput(Input):
    name: str = Field(min_length=1, max_length=120)


class UserCreate(Input):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    agent_id: int = Field(gt=0)
    months: int = Field(default=12, gt=0, le=1200)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode()) > 72:
            raise ValueError("密码最多 72 个 UTF-8 字节")
        return value


class UserPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    agent_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if value is not None and len(value.encode()) > 72:
            raise ValueError("密码最多 72 个 UTF-8 字节")
        return value


class RenewInput(Input):
    months: int = Field(default=12, gt=0, le=1200)


class GrantInput(Input):
    enabled: bool


class TemplatePatch(Input):
    supply_public: bool | None = None
    supply_fallback_title: str | None = Field(default=None, max_length=220)


class ListingInput(Input):
    supply_listed: bool


class BatchListingInput(ListingInput):
    material_ids: list[PositiveInt] = Field(min_length=1, max_length=1500)


class StrategyInput(Input):
    infringement_filter: Literal["exclude", "include", "only"] = "exclude"
    name: str = Field(min_length=1, max_length=120)
    category_catalog_id: int = Field(gt=0)
    category_name: str = Field(min_length=1, max_length=255)
    template_id: int = Field(gt=0)
    price: Decimal = Field(gt=0, le=999999, decimal_places=2)
    stock: int = Field(default=999, ge=0, le=999999)
    cod: Literal["Y", "N"] = "Y"
    attributes: dict[str, str | list[str]] = Field(default_factory=dict)
    sku_count: int = Field(ge=5, le=9)
    link_count: int = Field(ge=10, le=50)
    title_requirements: str = Field(default="", max_length=2000)


class JobInput(Input):
    strategy_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


class AIConfig(Input):
    api_key: str | None = Field(default=None, min_length=1, max_length=2048)


def supply_actor(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.company_id is None or user.role not in (Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER, Role.SUPPLY_USER):
        raise HTTPException(403, "当前账号不能访问公司货盘")
    company = db.get(Company, user.company_id)
    if not user_can_run(user, company):
        raise HTTPException(403, "账号或公司不可用")
    user._supply_token_version = user.token_version
    return user


def supply_material_actor(user: User = Depends(supply_actor)):
    if user.role == Role.SUPPLY_USER:
        raise HTTPException(403, "货盘用户不能查看货盘素材")
    return user


def lock_actor(db, user, *, admin=False, manager=False):
    version = getattr(user, "_supply_token_version", user.token_version)
    company = lock_company(db, user.company_id)
    actor = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not user_can_run(actor, company) or actor.token_version != version:
        raise HTTPException(403, "账号权限已变更，请重新登录")
    if admin:
        require_admin(actor)
    if manager:
        require_manager(actor)
    return company


def owned(db, model, identity, user):
    item = db.scalar(select(model).where(model.id == identity, model.company_id == user.company_id))
    if item is None:
        raise HTTPException(404, "记录不存在")
    return item


def commit_unique(db, message):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, message) from exc


def user_payload(db, user):
    agent = db.get(SupplyAgent, user.supply_agent_id) if user.supply_agent_id else None
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value,
        "is_active": user.is_active, "supply_admin": user.supply_admin, "agent_id": user.supply_agent_id,
        "agent_name": agent.name if agent and agent.company_id == user.company_id else None,
        "agent_created_at": timestamp(agent.created_at) if agent and agent.company_id == user.company_id else None,
        "supply_expires_at": timestamp(user.supply_expires_at),
        "expired": user.role == Role.SUPPLY_USER and supply_user_is_expired(user),
        "created_at": timestamp(user.created_at)}


def target_user(db, user, identity):
    item = db.scalar(select(User).where(User.id == identity, User.company_id == user.company_id,
        User.role == Role.SUPPLY_USER).with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, "货盘用户不存在")
    return item


@router.get("/context")
def context(user=Depends(supply_actor), db: Session = Depends(get_db)):
    return {"user": user_payload(db, user), "can_manage": is_manager(user),
            "can_admin": user.role == Role.COMPANY_ADMIN, "can_view_materials": user.role != Role.SUPPLY_USER}


@router.get("/agents")
def agents(user=Depends(supply_actor), db: Session = Depends(get_db)):
    require_admin(user)
    return [{"id": item.id, "name": item.name, "created_at": timestamp(item.created_at)} for item in db.scalars(select(SupplyAgent).where(
        SupplyAgent.company_id == user.company_id).order_by(SupplyAgent.id)).all()]


@router.post("/agents")
def create_agent(payload: AgentInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, admin=True)
    item = SupplyAgent(company_id=user.company_id, name=payload.name)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "代理名称已存在") from exc
    audit(db, user, "create_agent", "agent", item.id)
    commit_unique(db, "代理名称已存在")
    return {"id": item.id, "name": item.name, "created_at": timestamp(item.created_at)}


@router.patch("/agents/{identity}")
def edit_agent(identity: int, payload: AgentInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, admin=True)
    item = owned(db, SupplyAgent, identity, user)
    item.name = payload.name
    audit(db, user, "rename_agent", "agent", identity)
    commit_unique(db, "代理名称已存在")
    return {"id": item.id, "name": item.name, "created_at": timestamp(item.created_at)}


@router.get("/users")
def users(user=Depends(supply_actor), db: Session = Depends(get_db)):
    require_manager(user)
    return [user_payload(db, item) for item in db.scalars(select(User).where(
        User.company_id == user.company_id, User.role == Role.SUPPLY_USER).order_by(User.id.desc())).all()]


@router.post("/users")
def create_user(payload: UserCreate, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, admin=True)
    owned(db, SupplyAgent, payload.agent_id, user)
    if db.scalar(select(User.id).where(User.email == str(payload.email).lower())):
        raise HTTPException(409, "邮箱已被使用")
    at = now()
    item = User(company_id=user.company_id, name=payload.name, email=str(payload.email).lower(),
        password_hash=hash_password(payload.password), role=Role.SUPPLY_USER,
        supply_agent_id=payload.agent_id, supply_expires_at=add_calendar_months(at, payload.months), created_at=at)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "邮箱已被使用") from exc
    audit(db, user, "create_user", "user", item.id, {"agent_id": payload.agent_id, "months": payload.months})
    commit_unique(db, "邮箱已被使用")
    return user_payload(db, item)


@router.patch("/users/{identity}")
def edit_user(identity: int, payload: UserPatch, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, admin=True)
    item = target_user(db, user, identity)
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(400, "账号字段不能清空")
    if "agent_id" in changes:
        owned(db, SupplyAgent, changes["agent_id"], user)
        item.supply_agent_id = changes.pop("agent_id")
    if "password" in changes:
        item.password_hash = hash_password(changes.pop("password"))
    for key, value in changes.items():
        setattr(item, key, str(value).lower() if key == "email" else value)
    item.token_version += 1
    if not item.is_active:
        cancel_user_jobs(db, item.id, "账号已停用")
    audit(db, user, "edit_user", "user", identity, {"fields": sorted(payload.model_fields_set)})
    commit_unique(db, "邮箱已被使用")
    return user_payload(db, item)


@router.post("/users/{identity}/renew")
def renew_user(identity: int, payload: RenewInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, admin=True)
    item = target_user(db, user, identity)
    if supply_user_is_expired(item):
        cancel_user_jobs(db, item.id, "原账号期限已结束")
    item.supply_expires_at = add_calendar_months(max(item.supply_expires_at or now(), now()), payload.months)
    item.token_version += 1
    audit(db, user, "renew_user", "user", identity, {"months": payload.months})
    db.commit()
    return user_payload(db, item)


@router.get("/internal-users")
def internal_users(user=Depends(supply_actor), db: Session = Depends(get_db)):
    require_admin(user)
    return [user_payload(db, item) for item in db.scalars(select(User).where(
        User.company_id == user.company_id, User.role.in_((Role.MEMBER, Role.TEAM_LEADER))).order_by(User.id)).all()]


@router.get("/managers")
def managers(user=Depends(supply_actor), db: Session = Depends(get_db)):
    require_manager(user)
    rows = db.execute(select(User, OperatorGroup.name).outerjoin(OperatorGroup,
        (OperatorGroup.id == User.group_id) & (OperatorGroup.company_id == user.company_id)).where(
        User.company_id == user.company_id, User.role.in_((Role.MEMBER, Role.TEAM_LEADER)),
        User.supply_admin.is_(True)).order_by(User.id)).all()
    return [{"id": member.id, "name": member.name, "group_name": group_name,
             "email": member.email} for member, group_name in rows]


@router.post("/grants/{identity}")
def grant(identity: int, payload: GrantInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, admin=True)
    item = owned(db, User, identity, user)
    if item.role not in (Role.MEMBER, Role.TEAM_LEADER):
        raise HTTPException(400, "只能向本公司成员或组长分配货盘管理权限")
    item.supply_admin = payload.enabled
    audit(db, user, "grant_manager", "user", identity, {"enabled": payload.enabled})
    db.commit()
    return user_payload(db, item)


@router.get("/template-groups")
def template_groups(user=Depends(supply_actor), db: Session = Depends(get_db)):
    groups = db.scalars(select(TemplateGroup).where(
        or_(TemplateGroup.company_id == user.company_id, TemplateGroup.is_platform.is_(True)))
        .order_by(TemplateGroup.is_platform.desc(), TemplateGroup.name, TemplateGroup.id)).all()
    return [{"id": group.id, "name": group.name} for group in groups]


@router.get("/templates")
def templates(user=Depends(supply_actor), db: Session = Depends(get_db)):
    query = select(ProductTemplate).where(ProductTemplate.company_id == user.company_id)
    if not is_manager(user):
        query = query.where(ProductTemplate.supply_public.is_(True))
    groups = {group.id: group.name for group in db.scalars(select(TemplateGroup).where(
        or_(TemplateGroup.company_id == user.company_id, TemplateGroup.is_platform.is_(True)))).all()}
    items = []
    for item in db.scalars(query.order_by(ProductTemplate.id)).all():
        snapshot = template_snapshot(item)
        available = eligible_materials(db, user.company_id, item.id, template_version(snapshot))
        items.append({"id": item.id, "name": item.name, "cover_url": item.cover_url,
            "group_id": item.group_id if item.group_id in groups else None, "group_name": groups.get(item.group_id),
            "description": item.description, "supply_public": item.supply_public,
            "supply_fallback_title": item.supply_fallback_title if is_manager(user) else None,
            "sizes": sizes(snapshot), "available_count": len(available)})
    return items


@router.patch("/templates/{identity}")
def edit_template(identity: int, payload: TemplatePatch, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, manager=True)
    item = owned(db, ProductTemplate, identity, user)
    if "supply_fallback_title" in payload.model_fields_set:
        require_admin(user)
        item.supply_fallback_title = validate_fallback(payload.supply_fallback_title)
    if "supply_public" in payload.model_fields_set:
        if payload.supply_public is None:
            raise HTTPException(400, "公开状态不能为空")
        if payload.supply_public:
            validate_template(item)
        item.supply_public = payload.supply_public
    audit(db, user, "template_publication", "template", identity,
          {"supply_public": item.supply_public, "fields": sorted(payload.model_fields_set)})
    db.commit()
    return {"id": identity, "supply_public": item.supply_public, "supply_fallback_title": item.supply_fallback_title}


@router.get("/materials")
def materials(template_id: int | None = None,
    listed: bool | None = None, search: str = "", page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=1500),
    source: Literal["catalog", "library"] = "catalog",
    user=Depends(supply_material_actor), db: Session = Depends(get_db)):
    query = select(MaterialAsset).where(MaterialAsset.company_id == user.company_id)
    if source == "library":
        require_manager(user)
        query = query.where(MaterialAsset.supply_listed.is_(False))
    elif listed is False:
        query = query.where(MaterialAsset.supply_listed.is_(False), MaterialAsset.supply_listed_at.is_not(None))
    else:
        query = query.where(MaterialAsset.supply_listed.is_(True))
    if template_id is not None:
        query = query.where(MaterialAsset.template_id == template_id)
    if search:
        query = query.where(MaterialAsset.name.contains(search) | MaterialAsset.sku.contains(search))
    if not is_manager(user):
        query = query.join(ProductTemplate, ProductTemplate.id == MaterialAsset.template_id).where(
            ProductTemplate.company_id == user.company_id, ProductTemplate.supply_public.is_(True), MaterialAsset.supply_listed.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    assets = db.scalars(query.order_by(MaterialAsset.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    names = {item.id: item.name for item in db.scalars(select(ProductTemplate).where(
        ProductTemplate.company_id == user.company_id, ProductTemplate.id.in_([asset.template_id for asset in assets]))).all()}
    counts = material_statistics(db, user.company_id, [asset.id for asset in assets],
        None if is_manager(user) else user.id)
    return {"items": [{"id": asset.id, "name": asset.name, "sku": asset.sku, "url": asset.url,
        "template_id": asset.template_id, "template_name": names.get(asset.template_id),
        "is_infringing": asset.is_infringing,
        "supply_listed": asset.supply_listed,
        **counts.get(asset.id, {"use_count": 0, "user_count": 0, "job_count": 0})} for asset in assets],
        "total": total, "page": page, "page_size": page_size}


@router.patch("/materials/batch")
def batch_list_materials(payload: BatchListingInput, user=Depends(supply_material_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, manager=True)
    ids = list(dict.fromkeys(payload.material_ids))
    assets = db.scalars(select(MaterialAsset).where(
        MaterialAsset.company_id == user.company_id, MaterialAsset.id.in_(ids)
    ).order_by(MaterialAsset.id).with_for_update()).all()
    if len(assets) != len(ids):
        raise HTTPException(404, "部分素材不存在或不属于当前公司，整批操作未执行")
    if payload.supply_listed:
        template_ids = set(db.scalars(select(ProductTemplate.id).where(
            ProductTemplate.company_id == user.company_id,
            ProductTemplate.id.in_({item.template_id for item in assets}))))
        invalid = [item for item in assets if item.template_id not in template_ids or not item.sku or not item.url]
        if invalid:
            labels = "、".join(f"{item.sku or item.name or '素材'}（ID {item.id}）" for item in invalid[:10])
            raise HTTPException(400, f"{len(invalid)} 条素材缺少有效模板、SKU 或图片：{labels}。整批操作未执行")
    at = now()
    first_listing = MaterialAsset.supply_listed_at.is_(None)
    if not payload.supply_listed:
        first_listing = first_listing & MaterialAsset.supply_listed.is_(True)
    # MySQL 按 SET 顺序赋值，须先用原上架状态计算首次上架时间。
    db.execute(update(MaterialAsset).where(
        MaterialAsset.company_id == user.company_id, MaterialAsset.id.in_(ids)
    ).ordered_values(
        (MaterialAsset.supply_listed_at, case((first_listing, at), else_=MaterialAsset.supply_listed_at)),
        (MaterialAsset.supply_listed, payload.supply_listed),
    ).execution_options(synchronize_session=False))
    db.execute(insert(SupplyAudit), [
        {"company_id": user.company_id, "user_id": user.id, "action": "material_listing",
         "target_type": "material", "target_id": item.id, "details": {"listed": payload.supply_listed}}
        for item in assets])
    db.commit()
    return {"ids": ids, "count": len(ids), "supply_listed": payload.supply_listed}


@router.patch("/materials/{identity}")
def list_material(identity: int, payload: ListingInput, user=Depends(supply_material_actor), db: Session = Depends(get_db)):
    lock_actor(db, user, manager=True)
    item = owned(db, MaterialAsset, identity, user)
    if payload.supply_listed:
        owned(db, ProductTemplate, item.template_id, user)
        if not item.sku or not item.url:
            raise HTTPException(400, "素材缺少 SKU 或图片地址")
        if item.supply_listed_at is None:
            item.supply_listed_at = now()
    elif item.supply_listed and item.supply_listed_at is None:
        item.supply_listed_at = now()
    item.supply_listed = payload.supply_listed
    audit(db, user, "material_listing", "material", identity, {"listed": payload.supply_listed})
    db.commit()
    return {"id": identity, "supply_listed": item.supply_listed}


@router.get("/catalogs")
def catalogs(user=Depends(supply_actor), db: Session = Depends(get_db)):
    return [{"id": item.id, "name": item.name, "template_type": item.template_type,
        "template_version": item.template_version} for item in db.scalars(select(TiktokCategoryCatalog).where(
            TiktokCategoryCatalog.company_id == user.company_id,
            TiktokCategoryCatalog.template_type.in_(("tiktok_local", "tiktok_cross_border"))).order_by(TiktokCategoryCatalog.id)).all()]


@router.get("/catalogs/{identity}/options")
def catalog_options(identity: int, user=Depends(supply_actor), db: Session = Depends(get_db)):
    item = owned(db, TiktokCategoryCatalog, identity, user)
    if item.template_type not in ("tiktok_local", "tiktok_cross_border"):
        raise HTTPException(400, "类目库不可用于货盘")
    return item.parsed_options


def strategy_payload(item):
    return {"infringement_filter": "include", **item.parameters, "id": item.id, "name": item.name, "created_at": timestamp(item.created_at)}


@router.get("/strategies")
def strategies(user=Depends(supply_actor), db: Session = Depends(get_db)):
    return [strategy_payload(item) for item in db.scalars(select(SupplyStrategy).where(
        SupplyStrategy.company_id == user.company_id, SupplyStrategy.user_id == user.id).order_by(SupplyStrategy.id.desc())).all()]


def save_strategy(payload, user, db, identity=None):
    lock_actor(db, user)
    parameters = payload.model_dump(mode="json")
    item = owned(db, SupplyStrategy, identity, user) if identity else SupplyStrategy(company_id=user.company_id, user_id=user.id)
    if item.user_id != user.id:
        raise HTTPException(404, "策略不存在")
    if identity and "infringement_filter" not in payload.model_fields_set:
        parameters["infringement_filter"] = item.parameters.get("infringement_filter", "include")
    validate_strategy(db, user, parameters)
    item.name, item.parameters = payload.name, parameters
    db.add(item)
    db.commit()
    return strategy_payload(item)


@router.post("/strategies")
def create_strategy(payload: StrategyInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    return save_strategy(payload, user, db)


@router.patch("/strategies/{identity}")
def edit_strategy(identity: int, payload: StrategyInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    return save_strategy(payload, user, db, identity)


@router.delete("/strategies/{identity}")
def delete_strategy(identity: int, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user)
    item = owned(db, SupplyStrategy, identity, user)
    if item.user_id != user.id:
        raise HTTPException(404, "策略不存在")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@router.post("/jobs")
def submit_job(payload: JobInput, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user)
    actor = db.get(User, user.id)
    if not user_can_run(actor, db.get(Company, user.company_id)):
        raise HTTPException(403, "账号不可用")
    request_hash = digest({"strategy_id": payload.strategy_id})
    previous = db.scalar(select(SupplyJob).where(SupplyJob.company_id == user.company_id,
        SupplyJob.user_id == user.id, SupplyJob.idempotency_key == payload.idempotency_key))
    if previous:
        if previous.request_hash != request_hash:
            raise HTTPException(409, "幂等键已用于不同请求")
        return job_payload(previous)
    if db.scalar(select(SupplyJob.id).where(SupplyJob.user_id == user.id, SupplyJob.state.in_(ACTIVE_STATES)).limit(1)):
        raise HTTPException(409, "已有未完成任务，请等待完成或取消")
    strategy = owned(db, SupplyStrategy, payload.strategy_id, user)
    if strategy.user_id != user.id:
        raise HTTPException(404, "策略不存在")
    parameters = copy.deepcopy(strategy.parameters)
    parameters.setdefault("infringement_filter", "include")
    template, catalog, snapshot, rows = validate_strategy(db, user, parameters)
    version = template_version(snapshot)
    candidates = eligible_materials(db, user.company_id, template.id, version, parameters["infringement_filter"])
    # URL 或源 SKU 重复的素材不能用于同一链接，提交时即验证可形成完整组。
    from .supply_worker import distinct_sample
    import random
    if len(distinct_sample(candidates, parameters["sku_count"], random.Random(0))) < parameters["sku_count"]:
        raise HTTPException(400, "当前侵权筛选条件下，可用素材不足以组成指定 SKU 数量")
    agent = db.get(SupplyAgent, actor.supply_agent_id) if actor.role == Role.SUPPLY_USER else None
    if actor.role == Role.SUPPLY_USER and (not agent or agent.company_id != actor.company_id):
        raise HTTPException(400, "货盘账号缺少有效代理，请联系公司管理员")
    job = SupplyJob(company_id=user.company_id, user_id=user.id, strategy_id=strategy.id,
        agent_id=agent.id if agent else None, agent_name=agent.name if agent else None,
        template_id=template.id, category_catalog_id=catalog.id,
        idempotency_key=payload.idempotency_key, request_hash=request_hash,
        snapshot={"strategy": parameters, "template": snapshot, "template_version": version,
            "catalog_options": copy.deepcopy(catalog.parsed_options), "catalog_type": catalog.template_type,
            "candidates": candidates, "seed": secrets.token_hex(16), "user_name": actor.name,
            "internal_usage": actor.role != Role.SUPPLY_USER, "expected_rows": rows},
        category_blob=bytes(catalog.template_blob), checkpoint={}, progress={"links_done": 0, "links_total": parameters["link_count"]})
    db.add(job)
    db.flush()
    db.add_all(SupplyJobMaterial(company_id=user.company_id, job_id=job.id, material_id=item["id"],
        version_hash=item["version_hash"], source="snapshot", link_index=-1, successful=False) for item in candidates)
    audit(db, user, "submit_job", "job", job.id, {"strategy_id": strategy.id})
    db.commit()
    return job_payload(job)


def accessible_job(db, user, identity, lock=False):
    query = select(SupplyJob).where(SupplyJob.id == identity, SupplyJob.company_id == user.company_id)
    if not is_manager(user):
        query = query.where(SupplyJob.user_id == user.id)
    item = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if item is None:
        raise HTTPException(404, "任务不存在")
    return item


@router.get("/jobs")
def jobs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    scope: Literal["own", "company"] = "own",
    user=Depends(supply_actor), db: Session = Depends(get_db)):
    query = select(SupplyJob).where(SupplyJob.company_id == user.company_id)
    if scope == "company":
        require_manager(user)
    else:
        query = query.where(SupplyJob.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(SupplyJob.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [job_payload(item) for item in items], "total": total, "page": page, "page_size": page_size}


@router.get("/jobs/{identity}")
def job_detail(identity: int, user=Depends(supply_actor), db: Session = Depends(get_db)):
    item = accessible_job(db, user, identity)
    return {**job_payload(item), "drafts": item.checkpoint.get("links", []), "strategy": item.snapshot.get("strategy")}


@router.post("/jobs/{identity}/cancel")
def cancel_job(identity: int, user=Depends(supply_actor), db: Session = Depends(get_db)):
    lock_actor(db, user)
    item = accessible_job(db, user, identity, lock=True)
    if item.state not in ACTIVE_STATES:
        raise HTTPException(409, "任务已经结束")
    item.state, item.stage, item.error, item.completed_at = "cancelled", "cancelled", "用户取消", now()
    item.lease_epoch += 1
    item.lease_owner, item.lease_expires_at = None, None
    item.export_blob = None
    audit(db, user, "cancel_job", "job", identity)
    db.commit()
    return job_payload(item)


@router.get("/jobs/{identity}/download")
def download(identity: int, user=Depends(supply_actor), db: Session = Depends(get_db)):
    from .supply_files import read_supply_export
    from .storage import StorageError
    def verify():
        company = lock_actor(db, user)
        actor = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
        if not user_can_run(actor, company):
            raise HTTPException(403, "账号不可用")
        item = accessible_job(db, actor, identity, lock=True)
        if item.state != "completed":
            raise HTTPException(403, "文件尚未生成")
        if item.output_deleted_at or not item.output_expires_at or item.output_expires_at <= now():
            raise HTTPException(410, "文件已过期")
        if not item.output_key or not item.output_key.startswith(f"supply-exports/company/{user.company_id}/jobs/{item.id}/"):
            raise HTTPException(409, "文件归属校验失败")
        return item
    item = verify()
    key, sha, size = item.output_key, item.output_sha256, item.output_size
    db.commit()
    try:
        content = read_supply_export(key, sha, size)
    except StorageError as exc:
        raise HTTPException(502, "文件读取失败，请稍后重试") from exc
    item = verify()
    audit(db, user, "download", "job", identity, {"on_behalf": item.user_id != user.id})
    db.commit()
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'TikTok货盘_{identity}.xlsx')}",
                 "Cache-Control": "private, no-store"})


def successful_material_conditions(company_id):
    return (SupplyJobMaterial.company_id == company_id, SupplyJob.company_id == company_id,
            SupplyJobMaterial.successful.is_(True), SupplyJob.state == "completed")


def material_statistics(db, company_id, ids=None, user_id=None):
    query = select(SupplyJobMaterial.material_id, func.count(SupplyJobMaterial.id),
        func.count(func.distinct(SupplyJob.user_id)), func.count(func.distinct(SupplyJob.id)),
        func.max(SupplyJob.completed_at)).join(SupplyJob, SupplyJob.id == SupplyJobMaterial.job_id).where(
            *successful_material_conditions(company_id))
    if ids is not None:
        query = query.where(SupplyJobMaterial.material_id.in_(ids))
    if user_id is not None:
        query = query.where(SupplyJob.user_id == user_id)
    return {row[0]: {"use_count": row[1], "user_count": row[2], "job_count": row[3],
        "last_used_at": timestamp(row[4])} for row in db.execute(query.group_by(SupplyJobMaterial.material_id))}


@router.get("/materials/{identity}/usage")
def usage(identity: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
          user=Depends(supply_material_actor), db: Session = Depends(get_db)):
    owned(db, MaterialAsset, identity, user)
    query = select(SupplyJobMaterial.job_id.label("job_id"),
        func.count(SupplyJobMaterial.id).label("link_count")).join(
        SupplyJob, SupplyJob.id == SupplyJobMaterial.job_id).where(
        *successful_material_conditions(user.company_id), SupplyJobMaterial.material_id == identity)
    if not is_manager(user):
        query = query.where(SupplyJob.user_id == user.id)
    grouped = query.group_by(SupplyJobMaterial.job_id).subquery()
    total = db.scalar(select(func.count()).select_from(grouped)) or 0
    rows = db.execute(select(SupplyJob.id.label("job_id"), SupplyJob.user_id,
        SupplyJob.snapshot["user_name"].as_string().label("user_name"), SupplyJob.agent_name,
        grouped.c.link_count, SupplyJob.completed_at).join(grouped, grouped.c.job_id == SupplyJob.id)
        .order_by(SupplyJob.completed_at.desc(), SupplyJob.id.desc())
        .offset((page - 1) * page_size).limit(page_size)).mappings().all()
    return {"items": [{**row, "completed_at": timestamp(row["completed_at"])} for row in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/statistics")
def statistics(user=Depends(supply_actor), db: Session = Depends(get_db)):
    require_manager(user)
    completed = SupplyJob.state == "completed"
    summary = dict(db.execute(select(func.count(SupplyJob.id).label("job_count"),
        func.count(case((completed, SupplyJob.id))).label("success_count"),
        func.count(func.distinct(case((completed, SupplyJob.user_id)))).label("user_count"))
        .where(SupplyJob.company_id == user.company_id)).mappings().one())
    agents = (select(SupplyJob.agent_id.label("agent_id"), func.max(SupplyJob.id).label("latest_job_id"),
        func.count(SupplyJob.id).label("job_count"),
        func.count(case((completed, SupplyJob.id))).label("success_count"),
        func.count(func.distinct(case((completed, SupplyJob.user_id)))).label("user_count"))
        .where(SupplyJob.company_id == user.company_id).group_by(SupplyJob.agent_id).subquery())
    # JSON 快照可能包含大量候选素材；不要让它参与代理分组的 filesort。
    # 对每个代理单独求和，无 GROUP BY 的聚合只读取链接数，不排序快照。
    link_count = (select(func.coalesce(func.sum(SupplyJob.snapshot["strategy"]["link_count"].as_integer()), 0))
        .where(SupplyJob.company_id == user.company_id, completed,
            SupplyJob.agent_id.is_not_distinct_from(agents.c.agent_id))
        .correlate(agents).scalar_subquery())
    grouped = {row["agent_id"]: {**row, "agent_name": row["agent_name"] or "内部使用", "download_count": 0}
        for row in db.execute(select(agents.c.agent_id, agents.c.job_count, agents.c.success_count,
            agents.c.user_count, link_count.label("link_count"), SupplyJob.agent_name)
            .join(SupplyJob, SupplyJob.id == agents.c.latest_job_id)).mappings()}
    download_rows = db.execute(select(SupplyJob.agent_id, func.count(SupplyAudit.id)).join(
        SupplyAudit, SupplyAudit.target_id == SupplyJob.id).where(SupplyJob.company_id == user.company_id,
            SupplyAudit.company_id == user.company_id, SupplyAudit.target_type == "job", SupplyAudit.action == "download")
            .group_by(SupplyJob.agent_id)).all()
    for agent_id, count in download_rows:
        if agent_id in grouped:
            grouped[agent_id]["download_count"] = count
    summary["download_count"] = sum(count for _, count in download_rows)
    summary["use_count"] = db.scalar(select(func.count(SupplyJobMaterial.id)).join(
        SupplyJob, SupplyJob.id == SupplyJobMaterial.job_id).where(*successful_material_conditions(user.company_id))) or 0
    return {"summary": summary, "agents": list(grouped.values())}


@router.get("/ai-config")
def ai_config(user=Depends(supply_actor), db: Session = Depends(get_db)):
    require_admin(user)
    company = db.get(Company, user.company_id)
    return {"configured": bool(company.supply_ai_secret_encrypted), "model": DEEPSEEK_TITLE_MODEL}


@router.put("/ai-config")
def save_ai_config(payload: AIConfig, user=Depends(supply_actor), db: Session = Depends(get_db)):
    company = lock_actor(db, user, admin=True)
    if payload.api_key:
        company.supply_ai_secret_encrypted = encrypt_secret(payload.api_key)
    company.supply_ai_model = DEEPSEEK_TITLE_MODEL
    audit(db, user, "ai_config", "company", user.company_id, {"model": DEEPSEEK_TITLE_MODEL})
    db.commit()
    return ai_config(user, db)


@router.post("/ai-config/test")
async def test_ai_config(payload: AIConfig, user=Depends(supply_actor), db: Session = Depends(get_db)):
    from .supply_worker import request_title
    require_admin(user)
    company = db.get(Company, user.company_id)
    key = payload.api_key or (decrypt_secret(company.supply_ai_secret_encrypted) if company.supply_ai_secret_encrypted else None)
    if not key:
        raise HTTPException(400, "请先配置 DeepSeek 密钥")
    try:
        title = await request_title(key,
            {"name": "Printed dress", "product_description": "Printed long sleeve maxi dress"}, "")
    except Exception as exc:
        raise HTTPException(502, "DeepSeek 连接测试失败，请检查 API Key 或稍后重试") from exc
    return {"supported": True, "mode": "text", "title": title}
