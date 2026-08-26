from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import re
import secrets
import string
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, engine, get_db
from .models import AIProviderSetting, Company, MaterialAsset, NonAIPointRule, PointAccount, PointLedger, PodTask, ProductDraft, ProductTemplate, Role, Shop, TaskStatus, TemplateGroup, User, UserShop
from .schemas import AdminCompanyCreate, AIProviderSettingUpdate, DraftCreate, DraftTitleGenerate, DraftUpdate, LedgerOut, LoginInput, MaterialDraftCreate, MemberCreate, MemberUpdate, MiaoshouAccountUpdate, MiaoshouShopQuery, MyUserCodeUpdate, NonAIPointRuleCreate, NonAIPointRuleUpdate, PodTaskCreate, RechargeInput, SelectResult, ShopManagerUpdate, ShopOut, TemplateCreate, TemplateGroupCreate, TemplateUpdate, UserOut
from .security import create_access_token, current_user, hash_password, require_roles, verify_password
from .ai_providers import GenerationRequest, ProviderError, build_prompt, generate, generate_draft_title, provider_credential_env
from .credentials import decrypt_secret, encrypt_secret
from .storage import StorageError, is_public_r2_url, upload_image_bytes_async
import httpx


def seed(db: Session) -> None:
    company = db.scalar(select(Company).where(Company.name == "星潮跨境有限公司"))
    if not company:
        company = Company(name="星潮跨境有限公司")
        db.add(company); db.flush()

    def ensure_demo_user(email: str, name: str, role: Role, company_id: int | None = None) -> User:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(company_id=company_id, email=email, name=name, password_hash=hash_password("ChangeMe123!"), role=role)
            db.add(user); db.flush()
        return user

    ensure_demo_user("owner@haitoo-demo.com", "平台超级管理员", Role.SUPER_ADMIN)
    ensure_demo_user("admin@haitoo-demo.com", "演示公司管理员", Role.COMPANY_ADMIN, company.id)
    ensure_demo_user("operator@haitoo-demo.com", "陈宁", Role.MEMBER, company.id)
    # 仅清理无业务记录的早期内置演示店铺；实际店铺统一由妙手同步创建。
    builtin_shop = db.scalar(select(Shop).where(
        Shop.company_id == company.id, Shop.name == "MY TikTok Shop", Shop.external_shop_id.is_(None)
    ))
    if builtin_shop and not db.scalar(select(PodTask.id).where(PodTask.shop_id == builtin_shop.id).limit(1)) and not db.scalar(select(ProductDraft.id).where(ProductDraft.shop_id == builtin_shop.id).limit(1)):
        db.execute(delete(UserShop).where(UserShop.shop_id == builtin_shop.id))
        db.delete(builtin_shop)
    if not db.get(PointAccount, company.id):
        db.add(PointAccount(company_id=company.id, available=1280, frozen=120))
    if not db.get(AIProviderSetting, "seedream"):
        db.add(AIProviderSetting(provider="seedream", display_name="Seedream", model="doubao-seedream-4-0-250828", enabled=True, is_default=True))
    if not db.get(AIProviderSetting, "qwen"):
        db.add(AIProviderSetting(provider="qwen", display_name="千问图像编辑", model="qwen-image-edit", enabled=True, is_default=False))
    if not db.get(AIProviderSetting, "gemini"):
        db.add(AIProviderSetting(provider="gemini", display_name="Gemini 图像生成", model="gemini-2.5-flash-image", enabled=True, is_default=False))
    for operation_code, display_name, points, description in (
        ("product_draft_create", "创建商品草稿", 0, "从已选定的创作结果创建商品草稿"),
        ("product_publish", "发布商品", 0, "将商品发布到已授权店铺"),
        ("shop_sync", "同步店铺", 0, "从妙手同步店铺信息"),
    ):
        if not db.scalar(select(NonAIPointRule.id).where(NonAIPointRule.operation_code == operation_code)):
            db.add(NonAIPointRule(operation_code=operation_code, display_name=display_name, points=points, description=description))

    # 启动时只补齐必要的演示配置，绝不删除用户的模板、分类或历史数据。
    db.commit()


def ensure_schema() -> None:
    """轻量兼容迁移。关系一致性由应用层维护；MySQL 不使用外键。"""
    columns = {column["name"] for column in inspect(engine).get_columns("product_templates")}
    with engine.begin() as connection:
        if "description" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN description TEXT"))
        if "title_template" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN title_template VARCHAR(500)"))
        if "product_description" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN product_description TEXT"))
        if "size_chart_url" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN size_chart_url VARCHAR(500)"))
        for column in ("package_weight", "package_length", "package_width", "package_height"):
            if column not in columns:
                connection.execute(text(f"ALTER TABLE product_templates ADD COLUMN {column} FLOAT"))
        if "sku_specifications" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN sku_specifications JSON"))
        draft_columns = {column["name"] for column in inspect(engine).get_columns("product_drafts")}
        if "sku_items" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN sku_items JSON"))
        if "template_id" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN template_id INTEGER"))
        if "miaoshou_collect_box_id" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN miaoshou_collect_box_id VARCHAR(120)"))
        if "product_description" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN product_description TEXT"))
        if "size_chart_url" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN size_chart_url VARCHAR(500)"))
        if "created_by" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN created_by INTEGER"))
        if "updated_by" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN updated_by INTEGER"))
        if "updated_at" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN updated_at DATETIME"))
            connection.execute(text("UPDATE product_drafts SET updated_at = created_at WHERE updated_at IS NULL"))
        # 历史 AI 任务草稿可从来源任务回填操作人；素材库旧草稿没有可靠来源时保留为空。
        connection.execute(text("""
            UPDATE product_drafts
            SET created_by = (SELECT created_by FROM pod_tasks WHERE pod_tasks.id = product_drafts.source_task_id)
            WHERE created_by IS NULL AND source_task_id IS NOT NULL
        """))
        connection.execute(text("""
            UPDATE product_drafts
            SET updated_by = created_by
            WHERE updated_by IS NULL AND created_by IS NOT NULL
        """))
        # 兼容上线前由 AI 任务创建的商品草稿；素材库旧草稿无法可靠推断模板，发布时会提示重新创建。
        connection.execute(text("""
            UPDATE product_drafts
            SET template_id = (SELECT template_id FROM pod_tasks WHERE pod_tasks.id = product_drafts.source_task_id)
            WHERE template_id IS NULL AND source_task_id IS NOT NULL
        """))
        task_columns = {column["name"] for column in inspect(engine).get_columns("pod_tasks")}
        for column, definition in (("provider", "VARCHAR(40)"), ("provider_model", "VARCHAR(120)"), ("failure_reason", "VARCHAR(500)")):
            if column not in task_columns:
                connection.execute(text(f"ALTER TABLE pod_tasks ADD COLUMN {column} {definition}"))
        if connection.dialect.name == "mysql" and not next(column for column in inspect(engine).get_columns("pod_tasks") if column["name"] == "shop_id")["nullable"]:
            connection.execute(text("ALTER TABLE pod_tasks MODIFY COLUMN shop_id INTEGER NULL"))
        company_columns = {column["name"] for column in inspect(engine).get_columns("companies")}
        if "miaoshou_app_id" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN miaoshou_app_id VARCHAR(255)"))
        if "miaoshou_secret_encrypted" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN miaoshou_secret_encrypted TEXT"))
        user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
        if "user_code" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN user_code VARCHAR(2)"))
        user_indexes = inspect(connection).get_indexes("users")
        user_constraints = inspect(connection).get_unique_constraints("users")
        has_user_code_unique_index = any(
            index.get("name") == "uq_users_company_user_code" or (
                index.get("unique") and index.get("column_names") == ["company_id", "user_code"]
            )
            for index in [*user_indexes, *user_constraints]
        )
        if not has_user_code_unique_index:
            connection.execute(text("CREATE UNIQUE INDEX uq_users_company_user_code ON users (company_id, user_code)"))
        shop_columns = {column["name"] for column in inspect(engine).get_columns("shops")}
        for column, definition in (("nickname", "VARCHAR(120)"), ("platform", "VARCHAR(40)"), ("auth_expires_at", "VARCHAR(50)")):
            if column not in shop_columns:
                connection.execute(text(f"ALTER TABLE shops ADD COLUMN {column} {definition}"))
        material_columns = {column["name"]: column for column in inspect(engine).get_columns("material_assets")}
        if connection.dialect.name == "mysql" and not material_columns["source_task_id"]["nullable"]:
            connection.execute(text("ALTER TABLE material_assets MODIFY COLUMN source_task_id INTEGER NULL"))
        draft_columns = {column["name"]: column for column in inspect(engine).get_columns("product_drafts")}
        if connection.dialect.name == "mysql" and not draft_columns["source_task_id"]["nullable"]:
            connection.execute(text("ALTER TABLE product_drafts MODIFY COLUMN source_task_id INTEGER NULL"))
        if connection.dialect.name == "mysql" and not draft_columns["shop_id"]["nullable"]:
            connection.execute(text("ALTER TABLE product_drafts MODIFY COLUMN shop_id INTEGER NULL"))
        # 项目标准：MySQL 所有关系仅保存 ID，不建立数据库外键。兼容清理旧库。
        if connection.dialect.name == "mysql":
            inspector = inspect(connection)
            quote = connection.dialect.identifier_preparer.quote
            for table_name in inspector.get_table_names():
                for foreign_key in inspector.get_foreign_keys(table_name):
                    constraint_name = foreign_key.get("name")
                    if constraint_name:
                        connection.execute(text(f"ALTER TABLE {quote(table_name)} DROP FOREIGN KEY {quote(constraint_name)}"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = next(get_db())
    try:
        seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="HAITOO POD API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def allowed_shop_ids(db: Session, user: User) -> set[int]:
    if user.role == Role.SUPER_ADMIN:
        return set(db.scalars(select(Shop.id)).all())
    if user.role == Role.COMPANY_ADMIN:
        return set(db.scalars(select(Shop.id).where(Shop.company_id == user.company_id)).all())
    return set(db.scalars(select(UserShop.shop_id).where(UserShop.user_id == user.id)).all())


def serialize_ledger(rows: list[PointLedger], db: Session) -> list[LedgerOut]:
    """积分流水保留操作人 ID，同时返回便于展示的操作人名称。"""
    actor_ids = {row.actor_id for row in rows if row.actor_id is not None}
    actor_names = {
        actor.id: actor.name
        for actor in db.scalars(select(User).where(User.id.in_(actor_ids))).all()
    } if actor_ids else {}
    return [LedgerOut(
        id=row.id, actor_id=row.actor_id, actor_name=actor_names.get(row.actor_id, "系统"),
        entry_type=row.entry_type, amount=row.amount, balance_after=row.balance_after,
        note=row.note, created_at=row.created_at,
    ) for row in rows]


def timestamp_ms(value: datetime) -> int:
    """将数据库中按 UTC 保存的时间统一序列化为 Unix 毫秒时间戳。"""
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def serialize_record(record) -> dict:
    """序列化 ORM 记录，确保所有 datetime 字段均返回 Unix 毫秒时间戳。"""
    return {
        column.name: timestamp_ms(value) if isinstance(value := getattr(record, column.name), datetime)
        else value.value if isinstance(value, Enum) else value
        for column in record.__table__.columns
    }


def ensure_shop(db: Session, user: User, shop_id: int) -> Shop:
    shop = db.get(Shop, shop_id)
    if not shop or shop_id not in allowed_shop_ids(db, user):
        raise HTTPException(403, "没有该店铺的访问权限")
    return shop


def can_access_task(task: PodTask | None, user: User) -> bool:
    return bool(task and (user.role == Role.SUPER_ADMIN or task.company_id == user.company_id))


def user_code_in_use(db: Session, company_id: int | None, user_code: str, excluding_user_id: int | None = None) -> bool:
    """用户代码在公司内唯一；平台账号则在平台账号范围内唯一。"""
    statement = select(User.id).where(User.user_code == user_code)
    statement = statement.where(User.company_id.is_(None)) if company_id is None else statement.where(User.company_id == company_id)
    if excluding_user_id is not None:
        statement = statement.where(User.id != excluding_user_id)
    return db.scalar(statement) is not None


def commit_user_code_change(db: Session) -> None:
    """以唯一索引作为并发写入时的最终兜底，并保留可直接展示的提示。"""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "user_code" in str(exc.orig).lower() or "uq_users_company_user_code" in str(exc.orig).lower():
            raise HTTPException(400, "该用户代码已被使用") from exc
        raise


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(403, "该账号已被停用，请联系管理员")
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": UserOut.model_validate(user)}


@app.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id) if user.company_id else None
    return {"user": UserOut.model_validate(user), "company": {"id": company.id, "name": company.name} if company else None}


@app.patch("/me", response_model=UserOut)
def update_my_user_code(payload: MyUserCodeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """当前账号只能设置自己的用户代码。"""
    if payload.user_code and user_code_in_use(db, user.company_id, payload.user_code, user.id):
        raise HTTPException(400, "该用户代码已被使用")
    user.user_code = payload.user_code
    commit_user_code_change(db)
    db.refresh(user)
    return user


@app.get("/shops", response_model=list[ShopOut])
def list_shops(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Shop).where(Shop.id.in_(allowed_shop_ids(db, user))).order_by(Shop.id)).all()


@app.get("/shops/manage")
def list_managed_shops(user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    """公司管理员查看全部店铺及其被分配的普通成员。"""
    shops = db.scalars(select(Shop).where(Shop.company_id == user.company_id).order_by(Shop.id)).all()
    assignments = db.execute(
        select(UserShop.shop_id, User)
        .join(User, User.id == UserShop.user_id)
        .where(UserShop.shop_id.in_([shop.id for shop in shops]), User.company_id == user.company_id, User.role == Role.MEMBER)
        .order_by(User.name, User.id)
    ).all() if shops else []
    members_by_shop: dict[int, list[UserOut]] = {shop.id: [] for shop in shops}
    for shop_id, member in assignments:
        members_by_shop[shop_id].append(UserOut.model_validate(member))
    return [{
        "id": shop.id, "name": shop.name, "region": shop.region, "auth_status": shop.auth_status,
        "external_shop_id": shop.external_shop_id, "nickname": shop.nickname, "platform": shop.platform,
        "auth_expires_at": shop.auth_expires_at,
        "manager_users": members_by_shop[shop.id],
    } for shop in shops]


@app.put("/shops/{shop_id}/managers")
def update_shop_managers(shop_id: int, payload: ShopManagerUpdate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    """为一个店铺分配多个普通成员；公司管理员天然拥有全部店铺权限，无需分配。"""
    shop = db.get(Shop, shop_id)
    if not shop or shop.company_id != user.company_id:
        raise HTTPException(404, "店铺不存在")
    member_ids = set(payload.member_ids)
    members = db.scalars(select(User).where(
        User.id.in_(member_ids), User.company_id == user.company_id, User.role == Role.MEMBER
    )).all() if member_ids else []
    if len(members) != len(member_ids):
        raise HTTPException(400, "只能分配本公司的普通成员")
    db.execute(delete(UserShop).where(UserShop.shop_id == shop.id))
    db.add_all([UserShop(user_id=member.id, shop_id=shop.id) for member in members])
    db.commit()
    return {"shop_id": shop.id, "member_ids": sorted(member_ids)}


@app.get("/members", response_model=list[UserOut])
def list_members(user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    return db.scalars(
        select(User).where(User.company_id == user.company_id, User.role == Role.MEMBER).order_by(User.id.desc())
    ).all()


@app.post("/members", response_model=UserOut)
def create_member(payload: MemberCreate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(400, "该邮箱已被使用")
    if payload.user_code and user_code_in_use(db, user.company_id, payload.user_code):
        raise HTTPException(400, "该用户代码已被使用")
    member = User(company_id=user.company_id, email=email, name=payload.name.strip(), user_code=payload.user_code, password_hash=hash_password(payload.password), role=Role.MEMBER)
    db.add(member); commit_user_code_change(db); db.refresh(member)
    return member


@app.put("/members/{member_id}", response_model=UserOut)
def update_member(member_id: int, payload: MemberUpdate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    member = db.get(User, member_id)
    if not member or member.company_id != user.company_id or member.role != Role.MEMBER:
        raise HTTPException(404, "成员不存在")
    if payload.email is not None:
        email = str(payload.email).lower()
        duplicate = db.scalar(select(User.id).where(User.email == email, User.id != member.id))
        if duplicate:
            raise HTTPException(400, "该邮箱已被使用")
        member.email = email
    if payload.name is not None:
        member.name = payload.name.strip()
    if "user_code" in payload.model_fields_set:
        if payload.user_code and user_code_in_use(db, user.company_id, payload.user_code, member.id):
            raise HTTPException(400, "该用户代码已被使用")
        member.user_code = payload.user_code
    if payload.password is not None:
        member.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        member.is_active = payload.is_active
    commit_user_code_change(db); db.refresh(member)
    return member


@app.post("/miaoshou/shops")
async def list_miaoshou_shops(payload: MiaoshouShopQuery, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id)
    if not company or not company.miaoshou_app_id or not company.miaoshou_secret_encrypted:
        raise HTTPException(400, "尚未配置妙手账号，请联系平台管理员配置 AppKey 与 AppSecret")

    body = {"platform": "tiktok", "pageNo": payload.page_no, "pageSize": payload.page_size}
    if payload.site:
        body["site"] = payload.site.strip().upper()
    path = "/open/v1/product/shop/shop/get_shop_list"
    timestamp = str(int(time.time()))
    app_key = company.miaoshou_app_id
    app_secret = decrypt_secret(company.miaoshou_secret_encrypted)
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    signature = miaoshou_request_signature(app_secret, path, timestamp, app_key, body_json)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://openapi-erp.91miaoshou.com{path}", content=body_json.encode(), headers={
                    "Content-Type": "application/json", "x-app-key": app_key, "x-timestamp": timestamp, "x-sign": signature,
                },
            )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"妙手店铺接口调用失败：{exc}") from exc
    if result.get("code") != "success" and result.get("result") != "success":
        raise HTTPException(400, result.get("message") or result.get("code") or "妙手店铺接口返回失败")
    data = result.get("data") or {"shopList": []}
    synced_count = 0
    for item in data.get("shopList") or []:
        external_shop_id = str(item.get("shopId") or "").strip()
        if not external_shop_id:
            continue
        shop = db.scalar(select(Shop).where(Shop.company_id == user.company_id, Shop.external_shop_id == external_shop_id))
        if not shop:
            shop = Shop(company_id=user.company_id, external_shop_id=external_shop_id, name=external_shop_id)
            db.add(shop)
        shop.name = str(item.get("platformShopName") or item.get("shopNick") or external_shop_id).strip()[:120]
        shop.nickname = str(item.get("shopNick") or "").strip()[:120] or None
        shop.platform = str(item.get("platform") or "").strip()[:40] or None
        shop.region = str(item.get("siteName") or item.get("site") or "MY").strip()[:20]
        shop.auth_status = str(item.get("status") or "unknown").strip()[:30]
        shop.auth_expires_at = str(item.get("gmtExpire") or "").strip()[:50] or None
        synced_count += 1
    db.commit()
    data["synced_count"] = synced_count
    return data


@app.get("/template-groups")
def list_template_groups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(TemplateGroup).where(or_(TemplateGroup.is_platform.is_(True), TemplateGroup.company_id == user.company_id)).order_by(TemplateGroup.is_platform.desc(), TemplateGroup.name)
    return db.scalars(stmt).all()


@app.post("/template-groups")
def create_template_group(payload: TemplateGroupCreate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    exists = db.scalar(select(TemplateGroup).where(TemplateGroup.company_id == user.company_id, TemplateGroup.name == payload.name))
    if exists:
        raise HTTPException(400, "该模板分类已存在")
    group = TemplateGroup(company_id=user.company_id, name=payload.name)
    db.add(group); db.commit(); db.refresh(group)
    return group


@app.get("/templates")
def list_templates(group_id: int | None = None, q: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    filters = [ProductTemplate.is_platform.is_(True)]
    if user.company_id:
        filters.append(ProductTemplate.company_id == user.company_id)
    stmt = select(ProductTemplate).where(or_(*filters))
    if group_id is not None:
        stmt = stmt.where(ProductTemplate.group_id == group_id)
    if q:
        stmt = stmt.where(ProductTemplate.name.contains(q.strip()))
    return db.scalars(stmt.order_by(ProductTemplate.is_platform.desc(), ProductTemplate.id.desc())).all()


@app.post("/templates")
def create_template(payload: TemplateCreate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    template = ProductTemplate(company_id=user.company_id, **payload.model_dump())
    db.add(template); db.commit(); db.refresh(template)
    return template


def get_company_template(db: Session, user: User, template_id: int) -> ProductTemplate:
    template = db.get(ProductTemplate, template_id)
    if not template or template.company_id != user.company_id or template.is_platform:
        raise HTTPException(404, "公司模板不存在或不可修改")
    return template


def build_draft_sku_items(template: ProductTemplate, user: User, image_urls: list[str]) -> list[dict]:
    """按「每张图片一条」生成草稿基础 SKU；发布时再拼接模板尺码。"""
    if not user.user_code:
        raise HTTPException(400, "请先在账号设置中填写两位用户代码，再创建商品草稿")
    alphabet = string.ascii_uppercase + string.digits
    sku_items, generated_skus = [], set()
    for image_url in image_urls:
        random_part = "".join(secrets.choice(alphabet) for _ in range(6))
        while random_part in generated_skus:
            random_part = "".join(secrets.choice(alphabet) for _ in range(6))
        generated_skus.add(random_part)
        sku_items.append({"image_url": image_url, "size": None, "sku": f"M05L{user.user_code.upper()}{random_part}"})
    return sku_items


def validate_draft_sku_items(template: ProductTemplate, user: User, image_urls: list[str], sku_items: list) -> list[dict]:
    """验证前端预览的 SKU，保证保存内容和弹窗中展示的列表一致。"""
    if not sku_items:
        return build_draft_sku_items(template, user, image_urls)
    if not user.user_code:
        raise HTTPException(400, "请先在账号设置中填写两位用户代码，再创建商品草稿")
    expected_pairs = {(image_url, None) for image_url in image_urls}
    submitted_items = [item.model_dump() for item in sku_items]
    submitted_pairs = {(item["image_url"], item["size"]) for item in submitted_items}
    sku_pattern = re.compile(rf"^M05L{re.escape(user.user_code.upper())}[A-Z0-9]{{6}}$")
    if len(submitted_items) != len(expected_pairs) or submitted_pairs != expected_pairs or len({item["sku"] for item in submitted_items}) != len(submitted_items) or any(not sku_pattern.fullmatch(item["sku"]) for item in submitted_items):
        raise HTTPException(400, "SKU 列表已失效，请重新选择产品模板")
    return submitted_items


def miaoshou_request_signature(app_secret: str, path: str, timestamp: str, app_key: str, body_json: str) -> str:
    """妙手开放平台接口统一使用的 HMAC-SHA256 签名。"""
    source = f"{app_secret}{path}{timestamp}{app_key}{body_json}{app_secret}"
    return hmac.new(app_secret.encode(), source.encode(), hashlib.sha256).hexdigest()


def miaoshou_public_image_url(url: str) -> str:
    """妙手可使用任意能被其服务直接下载的公网 HTTP(S) 图片地址。"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "草稿图片必须是可被妙手访问的公网 HTTP(S) 地址")
    return url


def build_common_collect_box_payload(draft: ProductDraft, template: ProductTemplate) -> dict:
    """按妙手「创建公共采集箱产品」接口组装 POD 草稿。"""
    image_urls = [miaoshou_public_image_url(url) for url in (draft.image_urls or [])]
    if not image_urls:
        raise HTTPException(400, "商品草稿没有可发布的图片")
    sku_items = draft.sku_items or []
    if not sku_items:
        raise HTTPException(400, "商品草稿没有 SKU 信息")

    base_sku_by_image = {}
    for item in sku_items:
        base_sku_by_image.setdefault(item.get("image_url"), item["sku"])

    # Color 的属性值使用每张图片的基础 SKU，便于在妙手中识别图片与 SKU 的关系。
    image_color_keys = {}
    color_map = {}
    for local_url in draft.image_urls or []:
        base_sku = base_sku_by_image.get(local_url)
        if not base_sku:
            raise HTTPException(400, "商品草稿的图片缺少基础 SKU")
        image_color_keys[local_url] = base_sku
        public_url = miaoshou_public_image_url(local_url)
        color_map[base_sku] = {"name": base_sku, "imgUrls": [public_url], "imgUrl": public_url}

    size_names = (template.sku_specifications or {}).get("size", {}).get("options", [])
    size_names = [str(size).strip() for size in size_names if str(size).strip()] or ["Default"]
    size_map = {name: {"name": name} for name in size_names}
    sku_map = {}
    for image_url, color_name in image_color_keys.items():
        base_sku = base_sku_by_image.get(image_url)
        if not base_sku:
            raise HTTPException(400, "商品草稿的图片缺少基础 SKU")
        for size_name in size_names:
            platform_sku = base_sku if size_name == "Default" else f"{base_sku}-{size_name}"
            sku_map[f"{color_name};{size_name}"] = {
                "itemNum": platform_sku, "price": 0.01, "stock": 999,
                "weight": template.package_weight or 0.01,
                "packageLength": template.package_length or 0,
                "packageWidth": template.package_width or 0,
                "packageHeight": template.package_height or 0,
                "oriPrice": 0.01, "oriStock": 999,
            }
    first_sku = next(iter(sku_map.values()))["itemNum"]
    payload = {
        "title": draft.title, "itemNum": first_sku,
        "notes": draft.product_description or template.product_description or template.description or "POD 定制商品",
        "price": 0.01, "stock": 999, "imgUrls": image_urls,
        "weight": template.package_weight or 0.01,
        "packageLength": template.package_length or 0,
        "packageWidth": template.package_width or 0,
        "packageHeight": template.package_height or 0,
        "colorPropName": "Color", "colorMap": color_map,
        "sizePropName": "Size", "sizeMap": size_map, "skuMap": sku_map,
    }
    if draft.size_chart_url:
        payload["sizeChart"] = miaoshou_public_image_url(draft.size_chart_url)
    return payload


@app.put("/templates/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    template = get_company_template(db, user, template_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit(); db.refresh(template)
    return template


@app.delete("/templates/{template_id}")
def delete_template(template_id: int, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    template = get_company_template(db, user, template_id)
    if db.scalar(select(PodTask.id).where(PodTask.template_id == template.id).limit(1)):
        raise HTTPException(400, "该模板已有创作任务，无法删除")
    db.delete(template); db.commit()
    return {"deleted": True}


@app.post("/uploads/template-cover")
async def upload_template_cover(file: UploadFile = File(...), user: User = Depends(require_roles(Role.COMPANY_ADMIN))):
    return await save_image_upload(file, user.company_id, "template")


@app.post("/uploads/draft-size-chart")
async def upload_draft_size_chart(file: UploadFile = File(...), user: User = Depends(current_user)):
    return await save_image_upload(file, user.company_id, "draft-size-chart")


async def save_image_upload(file: UploadFile, company_id: int | None, prefix: str) -> dict:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(400, "请上传 JPG、PNG 或 WebP 图片")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 5MB")
    try:
        return {"url": await upload_image_bytes_async(content, file.content_type, company_id, prefix)}
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/uploads/creative-asset")
async def upload_creative_asset(file: UploadFile = File(...), user: User = Depends(current_user)):
    return await save_image_upload(file, user.company_id, "creative")


@app.post("/material-assets/upload")
async def upload_material_assets(files: list[UploadFile] = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """上传一张或多张本地图片到当前公司的素材库。"""
    if not files:
        raise HTTPException(400, "请至少选择一张图片")
    if len(files) > 100:
        raise HTTPException(400, "单次最多上传 100 张图片")

    assets: list[MaterialAsset] = []
    for file in files:
        uploaded = await save_image_upload(file, user.company_id, "material")
        name = Path(file.filename or "本地素材").name.rsplit(".", 1)[0] or "本地素材"
        asset = MaterialAsset(
            company_id=user.company_id,
            source_task_id=None,
            url=uploaded["url"],
            name=name[:180],
            claimed_by=user.id,
        )
        db.add(asset)
        assets.append(asset)
    db.commit()
    for asset in assets:
        db.refresh(asset)
    return [serialize_record(asset) for asset in assets]


@app.get("/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(PodTask)
    if user.role != Role.SUPER_ADMIN:
        stmt = stmt.where(PodTask.company_id == user.company_id)
    return [serialize_record(task) for task in db.scalars(stmt.order_by(PodTask.id.desc())).all()]


@app.get("/material-assets")
def list_material_assets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(MaterialAsset)
    if user.role != Role.SUPER_ADMIN:
        stmt = stmt.where(MaterialAsset.company_id == user.company_id)
    return [serialize_record(asset) for asset in db.scalars(stmt.order_by(MaterialAsset.id.desc())).all()]


@app.delete("/material-assets/{asset_id}")
def delete_material_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """从当前公司的素材库移除一张图片。"""
    stmt = select(MaterialAsset).where(MaterialAsset.id == asset_id)
    if user.role != Role.SUPER_ADMIN:
        stmt = stmt.where(MaterialAsset.company_id == user.company_id)
    asset = db.scalar(stmt)
    if not asset:
        raise HTTPException(404, "素材不存在或无权删除")

    db.delete(asset)
    db.commit()
    return {"deleted": True}


@app.get("/admin/ai-providers")
def list_ai_providers(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    return [
        {**serialize_record(setting), "credential_env": provider_credential_env(setting.provider)}
        for setting in db.scalars(select(AIProviderSetting).order_by(AIProviderSetting.provider)).all()
    ]


@app.get("/admin/non-ai-point-rules")
def list_non_ai_point_rules(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    return [serialize_record(rule) for rule in db.scalars(select(NonAIPointRule).order_by(NonAIPointRule.id.desc())).all()]


@app.post("/admin/non-ai-point-rules")
def create_non_ai_point_rule(payload: NonAIPointRuleCreate, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    operation_code = payload.operation_code.strip().lower()
    if db.scalar(select(NonAIPointRule.id).where(NonAIPointRule.operation_code == operation_code)):
        raise HTTPException(400, "操作代码已存在")
    rule = NonAIPointRule(operation_code=operation_code, display_name=payload.display_name.strip(), points=payload.points, enabled=payload.enabled, description=payload.description.strip() if payload.description else None)
    db.add(rule); db.commit(); db.refresh(rule)
    return serialize_record(rule)


@app.put("/admin/non-ai-point-rules/{rule_id}")
def update_non_ai_point_rule(rule_id: int, payload: NonAIPointRuleUpdate, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    rule = db.get(NonAIPointRule, rule_id)
    if not rule:
        raise HTTPException(404, "积分消耗配置不存在")
    rule.display_name = payload.display_name.strip(); rule.points = payload.points; rule.enabled = payload.enabled
    rule.description = payload.description.strip() if payload.description else None
    db.commit(); db.refresh(rule)
    return serialize_record(rule)


@app.delete("/admin/non-ai-point-rules/{rule_id}")
def delete_non_ai_point_rule(rule_id: int, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    rule = db.get(NonAIPointRule, rule_id)
    if not rule:
        raise HTTPException(404, "积分消耗配置不存在")
    db.delete(rule); db.commit()
    return {"deleted": True}


@app.get("/admin/overview")
def admin_overview(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    settings = get_settings()
    return {
        "companies": db.scalar(select(func.count()).select_from(Company)) or 0,
        "shops": db.scalar(select(func.count()).select_from(Shop)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "tasks": db.scalar(select(func.count()).select_from(PodTask)) or 0,
        "running_tasks": db.scalar(select(func.count()).select_from(PodTask).where(PodTask.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))) or 0,
        "credential_status": {
            "seedream": bool(settings.seedream_api_key),
            "qwen": bool(settings.qwen_api_key),
            "gemini": bool(settings.gemini_api_key),
            "r2": bool(
                settings.r2_access_key_id
                and settings.r2_secret_access_key
                and settings.r2_bucket
                and (settings.r2_endpoint or settings.r2_account_id)
                and settings.r2_public_base_url
            ),
        },
    }


@app.get("/admin/companies")
def list_admin_companies(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    companies = db.scalars(select(Company).order_by(Company.id.desc())).all()
    result = []
    for company in companies:
        account = db.get(PointAccount, company.id)
        result.append({
            "id": company.id,
            "name": company.name,
            "is_active": company.is_active,
            "miaoshou_configured": bool(company.miaoshou_app_id and company.miaoshou_secret_encrypted),
            "created_at": timestamp_ms(company.created_at),
            "admin_users": [UserOut.model_validate(item) for item in db.scalars(select(User).where(User.company_id == company.id, User.role == Role.COMPANY_ADMIN).order_by(User.id)).all()],
            "points": {"available": account.available if account else 0, "frozen": account.frozen if account else 0},
        })
    return result


@app.put("/admin/companies/{company_id}/miaoshou-account")
def update_company_miaoshou_account(company_id: int, payload: MiaoshouAccountUpdate, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "公司不存在")
    company.miaoshou_app_id = payload.app_id.strip()
    company.miaoshou_secret_encrypted = encrypt_secret(payload.app_secret)
    db.commit()
    return {"company_id": company.id, "configured": True}


@app.post("/admin/companies")
def create_admin_company(payload: AdminCompanyCreate, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    if db.scalar(select(Company.id).where(Company.name == payload.name.strip())):
        raise HTTPException(400, "公司名称已存在")
    if db.scalar(select(User.id).where(User.email == payload.admin_email)):
        raise HTTPException(400, "管理员邮箱已存在")
    company = Company(name=payload.name.strip())
    db.add(company); db.flush()
    admin = User(company_id=company.id, email=str(payload.admin_email), name=payload.admin_name.strip(), password_hash=hash_password(payload.admin_password), role=Role.COMPANY_ADMIN)
    db.add(admin)
    account = PointAccount(company_id=company.id, available=payload.initial_points, frozen=0)
    db.add(account)
    if payload.initial_points:
        db.add(PointLedger(company_id=company.id, actor_id=user.id, entry_type="initial_recharge", amount=payload.initial_points, balance_after=payload.initial_points, note="开通公司初始积分"))
    db.commit(); db.refresh(company)
    return {"id": company.id, "name": company.name}


@app.get("/admin/points/ledger")
def list_admin_point_ledger(company_id: int, limit: int = 100, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(404, "公司不存在")
    rows = db.scalars(select(PointLedger).where(PointLedger.company_id == company_id).order_by(PointLedger.id.desc()).limit(min(max(limit, 1), 500))).all()
    return serialize_ledger(rows, db)


@app.put("/admin/ai-providers/{provider}")
def update_ai_provider(provider: str, payload: AIProviderSettingUpdate, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    setting = db.get(AIProviderSetting, provider)
    if not setting:
        raise HTTPException(404, "模型提供方不存在")
    if payload.is_default and not payload.enabled:
        raise HTTPException(400, "默认模型必须处于启用状态")
    if payload.is_default:
        for item in db.scalars(select(AIProviderSetting)).all():
            item.is_default = False
    setting.model = payload.model.strip(); setting.enabled = payload.enabled; setting.is_default = payload.is_default
    if setting.is_default is False and not db.scalar(select(AIProviderSetting).where(AIProviderSetting.is_default.is_(True), AIProviderSetting.provider != provider)) and payload.enabled:
        setting.is_default = True
    db.commit(); db.refresh(setting)
    return serialize_record(setting)


def settle_failed_task(task_id: int, reason: str) -> None:
    db = next(get_db())
    try:
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return
        account = db.get(PointAccount, task.company_id)
        account.frozen -= task.estimated_points; account.available += task.estimated_points
        task.status = TaskStatus.FAILED; task.failure_reason = reason[:500]
        db.add(PointLedger(company_id=task.company_id, actor_id=task.created_by, task_id=task.id, entry_type="ai_refund", amount=task.estimated_points, balance_after=account.available, note="AI 任务失败，已退回预冻结积分"))
        db.commit()
    finally:
        db.close()


async def run_generation(task_id: int) -> None:
    db = next(get_db())
    try:
        task = db.get(PodTask, task_id)
        template = db.get(ProductTemplate, task.template_id) if task else None
        if not task or not template:
            return
        setting = db.get(AIProviderSetting, task.provider)
        if not setting or not setting.enabled:
            raise ProviderError("任务所选模型已停用")
        task.status = TaskStatus.RUNNING; db.commit()
        urls = await generate(task.provider, GenerationRequest(
            model=task.provider_model,
            prompt=build_prompt(task.parameters, template.name),
            template_url=template.cover_url or "",
            print_urls=task.parameters.get("print_urls") or [],
            ratio=task.parameters["ratio"],
            quality=task.parameters["quality"],
            company_id=task.company_id,
            task_id=task.id,
        ))
        urls = await persist_generated_images(urls, task.company_id, task.id)
        task.result_urls = urls; task.status = TaskStatus.AWAITING_SELECTION; db.commit()
    except Exception as exc:
        db.rollback()
        settle_failed_task(task_id, str(exc))
    finally:
        db.close()


async def persist_generated_images(urls: list[str], company_id: int, task_id: int) -> list[str]:
    """将模型供应商的临时 URL 复制到 R2，任务结果不依赖第三方 URL 的有效期。"""
    if not get_settings().ai_generated_image_upload_to_r2:
        # Gemini 结果已在适配器中上传 R2（接口只返回 base64，无法保存为第三方 URL）。
        # Seedream/千问则保留其供应商 URL，以节省 R2 存储和写入请求。
        return urls
    persisted: list[str] = []
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        for url in urls:
            if is_public_r2_url(url):
                persisted.append(url)
                continue
            response = await client.get(url)
            if response.is_error:
                raise ProviderError(f"下载模型生成图片失败：{response.status_code}")
            mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ProviderError(f"模型生成图片格式不受支持：{mime_type or '未知'}")
            if len(response.content) > 20 * 1024 * 1024:
                raise ProviderError("模型生成图片超过 20MB 上限")
            try:
                persisted.append(await upload_image_bytes_async(response.content, mime_type, company_id, f"generated/task-{task_id}"))
            except StorageError as exc:
                raise ProviderError(str(exc)) from exc
    return persisted


@app.post("/tasks")
def create_task(payload: PodTaskCreate, background_tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    template = db.get(ProductTemplate, payload.template_id)
    if not template or not (template.is_platform or template.company_id == user.company_id):
        raise HTTPException(404, "产品模板不存在")
    if not payload.print_urls or not payload.print_url:
        raise HTTPException(400, "请至少上传一张印花图")
    if not template.cover_url:
        raise HTTPException(400, "产品模板缺少模板图片，无法进行印花贴合")
    provider = db.scalar(select(AIProviderSetting).where(AIProviderSetting.is_default.is_(True), AIProviderSetting.enabled.is_(True)))
    if not provider:
        raise HTTPException(400, "暂无已启用的默认 AI 模型，请联系超级管理员配置")
    account = db.get(PointAccount, user.company_id)
    estimated = 20 if payload.quality == "2K" else 12
    if not account or account.available < estimated:
        raise HTTPException(400, "可用积分不足，无法创建 AI 任务")
    account.available -= estimated; account.frozen += estimated
    task = PodTask(company_id=user.company_id, template_id=template.id, created_by=user.id, status=TaskStatus.QUEUED, parameters=payload.model_dump(), estimated_points=estimated, result_urls=[], provider=provider.provider, provider_model=provider.model)
    db.add(task); db.flush()
    db.add(PointLedger(company_id=user.company_id, actor_id=user.id, task_id=task.id, entry_type="ai_freeze", amount=-estimated, balance_after=account.available, note="AI 创作预冻结"))
    db.commit(); db.refresh(task)
    background_tasks.add_task(run_generation, task.id)
    return serialize_record(task)


@app.post("/tasks/{task_id}/select")
def select_result(task_id: int, payload: SelectResult, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not can_access_task(task, user):
        raise HTTPException(404, "任务不存在")
    if payload.result_url not in task.result_urls:
        raise HTTPException(400, "请选择该任务的生成结果")
    if task.status != TaskStatus.AWAITING_SELECTION:
        raise HTTPException(400, "任务当前不能选图")
    actual = max(1, task.estimated_points - 2)
    account = db.get(PointAccount, task.company_id)
    account.frozen -= task.estimated_points; account.available += task.estimated_points - actual
    task.selected_result_url = payload.result_url; task.actual_points = actual; task.status = TaskStatus.COMPLETED
    db.add(PointLedger(company_id=task.company_id, actor_id=user.id, task_id=task.id, entry_type="ai_settlement", amount=task.estimated_points - actual, balance_after=account.available, note="AI 任务按实际用量结算"))
    db.commit(); db.refresh(task); return serialize_record(task)


@app.post("/tasks/{task_id}/claim-materials")
def claim_task_materials(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not can_access_task(task, user):
        raise HTTPException(404, "任务不存在")
    if task.status not in (TaskStatus.AWAITING_SELECTION, TaskStatus.COMPLETED) or not task.result_urls:
        raise HTTPException(400, "任务尚未生成可领取的图片")
    existing_urls = set(db.scalars(select(MaterialAsset.url).where(MaterialAsset.company_id == task.company_id, MaterialAsset.source_task_id == task.id)).all())
    claimed_count = 0
    for index, url in enumerate(task.result_urls, start=1):
        if url not in existing_urls:
            db.add(MaterialAsset(company_id=task.company_id, source_task_id=task.id, url=url, name=f"AI 创作 #{task.id} · 结果 {index}", claimed_by=user.id))
            claimed_count += 1
    db.commit()
    return {"claimed": claimed_count, "message": "已领取到素材库"}


@app.post("/tasks/{task_id}/draft")
def create_draft(task_id: int, payload: DraftCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not can_access_task(task, user) or task.status != TaskStatus.COMPLETED:
        raise HTTPException(400, "请先完成任务并选择产品图")
    shop = ensure_shop(db, user, payload.shop_id)
    template = db.get(ProductTemplate, task.template_id)
    draft = ProductDraft(company_id=task.company_id, shop_id=shop.id, template_id=template.id, source_task_id=task.id, title=f"{template.name} POD 商品", image_urls=[task.selected_result_url], sku_items=build_draft_sku_items(template, user, [task.selected_result_url]), created_by=user.id, updated_by=user.id)
    db.add(draft); db.commit(); db.refresh(draft); return serialize_record(draft)


@app.post("/drafts/from-material-assets")
def create_draft_from_material_assets(payload: MaterialDraftCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """用素材库中选定的一张或多张图片创建商品草稿。"""
    asset_ids = list(dict.fromkeys(payload.material_asset_ids))
    assets = db.scalars(select(MaterialAsset).where(
        MaterialAsset.company_id == user.company_id,
        MaterialAsset.id.in_(asset_ids),
    )).all()
    if len(assets) != len(asset_ids):
        raise HTTPException(400, "包含不存在或无权使用的素材")
    template = get_company_template(db, user, payload.template_id)
    source_task_ids = {asset.source_task_id for asset in assets}
    source_task_id = source_task_ids.pop() if len(source_task_ids) == 1 else None
    image_urls = [asset.url for asset in assets]
    draft = ProductDraft(
        company_id=user.company_id,
        shop_id=None,
        template_id=template.id,
        source_task_id=source_task_id,
        title=payload.title.strip(),
        product_description=payload.product_description.strip() if payload.product_description else None,
        size_chart_url=payload.size_chart_url,
        image_urls=image_urls,
        sku_items=validate_draft_sku_items(template, user, image_urls, payload.sku_items),
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(draft); db.commit(); db.refresh(draft)
    return serialize_record(draft)


@app.post("/templates/{template_id}/generate-draft-title")
async def generate_material_draft_title(template_id: int, payload: DraftTitleGenerate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    template = get_company_template(db, user, template_id)
    if not template.title_template:
        raise HTTPException(400, "该产品模版尚未填写 AI生成标题约束")
    asset = db.scalar(select(MaterialAsset).where(MaterialAsset.company_id == user.company_id, MaterialAsset.url == payload.image_url))
    if not asset:
        raise HTTPException(400, "请使用当前公司素材库中的首图生成标题")
    try:
        return {"title": await generate_draft_title(template.title_template, payload.image_url)}
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.put("/drafts/{draft_id}")
def update_draft(draft_id: int, payload: DraftUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    draft = db.get(ProductDraft, draft_id)
    if not draft or draft.company_id != user.company_id or (draft.shop_id is not None and draft.shop_id not in allowed_shop_ids(db, user)):
        raise HTTPException(404, "商品草稿不存在")
    draft.title = payload.title.strip()
    draft.product_description = payload.product_description.strip() if payload.product_description else None
    draft.updated_by = user.id
    db.commit(); db.refresh(draft)
    return serialize_record(draft)


@app.post("/drafts/{draft_id}/publish-to-miaoshou")
async def publish_draft_to_miaoshou(draft_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """将商品草稿创建到妙手公共采集箱，避免重复创建。"""
    draft = db.get(ProductDraft, draft_id)
    if not draft or draft.company_id != user.company_id or (draft.shop_id is not None and draft.shop_id not in allowed_shop_ids(db, user)):
        raise HTTPException(404, "商品草稿不存在")
    if draft.miaoshou_collect_box_id:
        return {"draft_id": draft.id, "common_collect_box_detail_id": draft.miaoshou_collect_box_id, "already_published": True}
    company = db.get(Company, draft.company_id)
    if not company or not company.miaoshou_app_id or not company.miaoshou_secret_encrypted:
        raise HTTPException(400, "尚未配置妙手账号，请联系平台管理员配置 AppKey 与 AppSecret")
    template = db.get(ProductTemplate, draft.template_id) if draft.template_id else None
    if not template:
        raise HTTPException(400, "该商品草稿缺少产品模板信息，无法生成公共采集箱商品")

    body = build_common_collect_box_payload(draft, template)
    path = "/open/v1/product/common_collect_box/common_collect_box/add_common_collect_box_detail"
    timestamp, app_key = str(int(time.time())), company.miaoshou_app_id
    app_secret = decrypt_secret(company.miaoshou_secret_encrypted)
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    signature = miaoshou_request_signature(app_secret, path, timestamp, app_key, body_json)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://openapi-erp.91miaoshou.com{path}", content=body_json.encode(), headers={
                    "Content-Type": "application/json", "x-app-key": app_key, "x-timestamp": timestamp, "x-sign": signature,
                },
            )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"妙手公共采集箱接口调用失败：{exc}") from exc
    if result.get("code") != "success" and result.get("result") != "success":
        raise HTTPException(400, result.get("message") or result.get("code") or "妙手公共采集箱接口返回失败")
    collect_box_id = (result.get("data") or {}).get("commonCollectBoxDetailId")
    if collect_box_id is None:
        raise HTTPException(502, "妙手公共采集箱接口未返回商品编号")
    draft.miaoshou_collect_box_id = str(collect_box_id)
    draft.status = "published_to_miaoshou"
    draft.updated_by = user.id
    db.commit()
    return {"draft_id": draft.id, "common_collect_box_detail_id": draft.miaoshou_collect_box_id, "already_published": False}


@app.get("/drafts")
def list_drafts(shop_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(ProductDraft).where(
        ProductDraft.company_id == user.company_id,
        or_(ProductDraft.shop_id.is_(None), ProductDraft.shop_id.in_(allowed_shop_ids(db, user))),
    )
    if shop_id:
        ensure_shop(db, user, shop_id); stmt = stmt.where(ProductDraft.shop_id == shop_id)
    drafts = db.scalars(stmt.order_by(ProductDraft.id.desc())).all()
    editor_ids = {draft.updated_by for draft in drafts if draft.updated_by is not None}
    editors = {
        editor.id: editor.name
        for editor in db.scalars(select(User).where(User.id.in_(editor_ids))).all()
    } if editor_ids else {}
    return [
        serialize_record(draft) | {"updated_by_name": editors.get(draft.updated_by)}
        for draft in drafts
    ]


@app.get("/points")
def points(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.company_id:
        return {"available": 0, "frozen": 0, "ledger": []}
    account = db.get(PointAccount, user.company_id)
    rows = db.scalars(select(PointLedger).where(PointLedger.company_id == user.company_id).order_by(PointLedger.id.desc()).limit(50)).all()
    return {"available": account.available, "frozen": account.frozen, "ledger": serialize_ledger(rows, db)}


@app.post("/points/recharge")
def recharge(payload: RechargeInput, user: User = Depends(require_roles(Role.SUPER_ADMIN, Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    if user.role == Role.COMPANY_ADMIN and payload.company_id != user.company_id:
        raise HTTPException(403, "只能为本公司充值")
    account = db.get(PointAccount, payload.company_id)
    if not account:
        raise HTTPException(404, "积分账户不存在")
    account.available += payload.amount
    db.add(PointLedger(company_id=payload.company_id, actor_id=user.id, entry_type="manual_recharge", amount=payload.amount, balance_after=account.available, note=payload.note))
    db.commit(); return {"available": account.available, "frozen": account.frozen}
