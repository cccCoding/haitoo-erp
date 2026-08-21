from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, inspect, or_, select, text
from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, engine, get_db
from .models import AIProviderSetting, Company, MaterialAsset, NonAIPointRule, PointAccount, PointLedger, PodTask, ProductDraft, ProductTemplate, Role, Shop, TaskStatus, TemplateGroup, User, UserShop
from .schemas import AdminCompanyCreate, AIProviderSettingUpdate, DraftCreate, LedgerOut, LoginInput, MemberCreate, MemberUpdate, MiaoshouAccountUpdate, MiaoshouShopQuery, NonAIPointRuleCreate, NonAIPointRuleUpdate, PodTaskCreate, RechargeInput, SelectResult, ShopManagerUpdate, ShopOut, TemplateCreate, TemplateGroupCreate, TemplateUpdate, UserOut
from .security import create_access_token, current_user, hash_password, require_roles, verify_password
from .ai_providers import GenerationRequest, ProviderError, build_prompt, generate, provider_credential_env
from .credentials import decrypt_secret, encrypt_secret
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

    # 开发演示数据清理：仅移除没有历史任务引用的旧模板，避免破坏既有任务。
    db.execute(
        delete(ProductTemplate).where(
            ProductTemplate.name.in_(["白色马克杯正面", "M05L"]),
            ProductTemplate.id.not_in(select(PodTask.template_id)),
        )
    )
    db.execute(delete(TemplateGroup).where(TemplateGroup.name.in_(["杯壶", "数码配件", "M05L"])))
    # 不再提供平台预置模板；历史上自动生成的默认模板在未被任务引用时予以清理。
    db.execute(
        delete(ProductTemplate).where(
            ProductTemplate.is_platform.is_(True),
            ProductTemplate.name == "白色 T恤正面",
            ProductTemplate.id.not_in(select(PodTask.template_id)),
        )
    )
    db.commit()


def ensure_schema() -> None:
    """轻量兼容迁移。关系一致性由应用层维护；MySQL 不使用外键。"""
    columns = {column["name"] for column in inspect(engine).get_columns("product_templates")}
    with engine.begin() as connection:
        if "description" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN description TEXT"))
        for column in ("package_weight", "package_length", "package_width", "package_height"):
            if column not in columns:
                connection.execute(text(f"ALTER TABLE product_templates ADD COLUMN {column} FLOAT"))
        if "sku_specifications" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN sku_specifications JSON"))
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
        shop_columns = {column["name"] for column in inspect(engine).get_columns("shops")}
        for column, definition in (("nickname", "VARCHAR(120)"), ("platform", "VARCHAR(40)"), ("auth_expires_at", "VARCHAR(50)")):
            if column not in shop_columns:
                connection.execute(text(f"ALTER TABLE shops ADD COLUMN {column} {definition}"))
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
upload_dir = Path(__file__).resolve().parent.parent / "uploads"
upload_dir.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=upload_dir), name="media")
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
    member = User(company_id=user.company_id, email=email, name=payload.name.strip(), password_hash=hash_password(payload.password), role=Role.MEMBER)
    db.add(member); db.commit(); db.refresh(member)
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
    if payload.password is not None:
        member.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        member.is_active = payload.is_active
    db.commit(); db.refresh(member)
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
    signature_source = f"{app_secret}{path}{timestamp}{app_key}{body_json}{app_secret}"
    signature = hmac.new(app_secret.encode(), signature_source.encode(), hashlib.sha256).hexdigest()
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


async def save_image_upload(file: UploadFile, company_id: int | None, prefix: str) -> dict:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(400, "请上传 JPG、PNG 或 WebP 图片")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 5MB")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    filename = f"{prefix}-{company_id or 'platform'}-{uuid4().hex}{suffix}"
    (upload_dir / filename).write_bytes(content)
    return {"url": f"/media/{filename}"}


@app.post("/uploads/creative-asset")
async def upload_creative_asset(file: UploadFile = File(...), user: User = Depends(current_user)):
    return await save_image_upload(file, user.company_id, "creative")


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
            "public_media_base_url": bool(settings.public_media_base_url),
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
        urls = await generate(task.provider, GenerationRequest(model=task.provider_model, prompt=build_prompt(task.parameters, template.name), template_url=template.cover_url or "", print_urls=task.parameters.get("print_urls") or [], ratio=task.parameters["ratio"], quality=task.parameters["quality"]))
        task.result_urls = urls; task.status = TaskStatus.AWAITING_SELECTION; db.commit()
    except Exception as exc:
        db.rollback()
        settle_failed_task(task_id, str(exc))
    finally:
        db.close()


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
    draft = ProductDraft(company_id=task.company_id, shop_id=shop.id, source_task_id=task.id, title=f"{template.name} POD 商品", image_urls=[task.selected_result_url])
    db.add(draft); db.commit(); db.refresh(draft); return serialize_record(draft)


@app.get("/drafts")
def list_drafts(shop_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(ProductDraft).where(ProductDraft.shop_id.in_(allowed_shop_ids(db, user)))
    if shop_id:
        ensure_shop(db, user, shop_id); stmt = stmt.where(ProductDraft.shop_id == shop_id)
    return [serialize_record(draft) for draft in db.scalars(stmt.order_by(ProductDraft.id.desc())).all()]


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
