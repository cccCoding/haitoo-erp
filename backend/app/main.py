from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import time
from pathlib import Path
from uuid import uuid4
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, inspect, or_, select, text
from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, engine, get_db
from .models import AIProviderSetting, Company, PointAccount, PointLedger, PodTask, ProductDraft, ProductTemplate, Role, Shop, TaskStatus, TemplateGroup, User, UserShop
from .schemas import AdminCompanyCreate, AIProviderSettingUpdate, LedgerOut, LoginInput, MemberCreate, MemberUpdate, MiaoshouAccountUpdate, MiaoshouShopQuery, PodTaskCreate, RechargeInput, SelectResult, ShopOut, TemplateCreate, TemplateGroupCreate, TemplateUpdate, UserOut
from .security import create_access_token, current_user, hash_password, require_roles, verify_password
from .ai_providers import GenerationRequest, ProviderError, build_prompt, generate
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
    member = ensure_demo_user("operator@haitoo-demo.com", "陈宁", Role.MEMBER, company.id)
    shop = db.scalar(select(Shop).where(Shop.company_id == company.id, Shop.name == "MY TikTok Shop"))
    if not shop:
        shop = Shop(company_id=company.id, name="MY TikTok Shop", region="MY", auth_status="not_connected")
        db.add(shop); db.flush()
    if not db.scalar(select(UserShop).where(UserShop.user_id == member.id, UserShop.shop_id == shop.id)):
        db.add(UserShop(user_id=member.id, shop_id=shop.id))
    if not db.get(PointAccount, company.id):
        db.add(PointAccount(company_id=company.id, available=1280, frozen=120))
    if not db.get(AIProviderSetting, "seedream"):
        db.add(AIProviderSetting(provider="seedream", display_name="Seedream", model="doubao-seedream-4-0-250828", enabled=True, is_default=True))
    if not db.get(AIProviderSetting, "qwen"):
        db.add(AIProviderSetting(provider="qwen", display_name="千问图像编辑", model="qwen-image-edit", enabled=True, is_default=False))

    # 开发演示数据清理：仅移除没有历史任务引用的旧模板，避免破坏既有任务。
    db.execute(
        delete(ProductTemplate).where(
            ProductTemplate.name.in_(["白色马克杯正面", "M05L"]),
            ProductTemplate.id.not_in(select(PodTask.template_id)),
        )
    )
    db.execute(delete(TemplateGroup).where(TemplateGroup.name.in_(["杯壶", "数码配件", "M05L"])))
    group = db.scalar(select(TemplateGroup).where(TemplateGroup.company_id == company.id, TemplateGroup.name == "服装"))
    if not group:
        group = TemplateGroup(company_id=company.id, name="服装")
        db.add(group); db.flush()
    template = db.scalar(select(ProductTemplate).where(ProductTemplate.is_platform.is_(True), ProductTemplate.name == "白色 T恤正面"))
    if not template:
        db.add(ProductTemplate(company_id=None, group_id=group.id, name="白色 T恤正面", is_platform=True, color_count=1, sku_count=1, print_areas=[{"name":"居中印花"}]))
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
        company_columns = {column["name"] for column in inspect(engine).get_columns("companies")}
        if "miaoshou_app_id" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN miaoshou_app_id VARCHAR(255)"))
        if "miaoshou_secret_encrypted" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN miaoshou_secret_encrypted TEXT"))
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


def ensure_shop(db: Session, user: User, shop_id: int) -> Shop:
    shop = db.get(Shop, shop_id)
    if not shop or shop_id not in allowed_shop_ids(db, user):
        raise HTTPException(403, "没有该店铺的访问权限")
    return shop


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
    return result.get("data") or {"shopList": []}


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
def list_tasks(shop_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(PodTask).where(PodTask.shop_id.in_(allowed_shop_ids(db, user)))
    if shop_id:
        ensure_shop(db, user, shop_id); stmt = stmt.where(PodTask.shop_id == shop_id)
    return db.scalars(stmt.order_by(PodTask.id.desc())).all()


@app.get("/admin/ai-providers")
def list_ai_providers(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    return db.scalars(select(AIProviderSetting).order_by(AIProviderSetting.provider)).all()


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
            "created_at": company.created_at,
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
    return [LedgerOut.model_validate(row) for row in rows]


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
    return setting


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
    shop = ensure_shop(db, user, payload.shop_id)
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
    task = PodTask(company_id=shop.company_id, shop_id=shop.id, template_id=template.id, created_by=user.id, status=TaskStatus.QUEUED, parameters=payload.model_dump(), estimated_points=estimated, result_urls=[], provider=provider.provider, provider_model=provider.model)
    db.add(task); db.flush()
    db.add(PointLedger(company_id=shop.company_id, actor_id=user.id, task_id=task.id, entry_type="ai_freeze", amount=-estimated, balance_after=account.available, note="AI 创作预冻结"))
    db.commit(); db.refresh(task)
    background_tasks.add_task(run_generation, task.id)
    return task


@app.post("/tasks/{task_id}/select")
def select_result(task_id: int, payload: SelectResult, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not task or task.shop_id not in allowed_shop_ids(db, user):
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
    db.commit(); db.refresh(task); return task


@app.post("/tasks/{task_id}/draft")
def create_draft(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not task or task.shop_id not in allowed_shop_ids(db, user) or task.status != TaskStatus.COMPLETED:
        raise HTTPException(400, "请先完成任务并选择产品图")
    template = db.get(ProductTemplate, task.template_id)
    draft = ProductDraft(company_id=task.company_id, shop_id=task.shop_id, source_task_id=task.id, title=f"{template.name} POD 商品", image_urls=[task.selected_result_url])
    db.add(draft); db.commit(); db.refresh(draft); return draft


@app.get("/drafts")
def list_drafts(shop_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(ProductDraft).where(ProductDraft.shop_id.in_(allowed_shop_ids(db, user)))
    if shop_id:
        ensure_shop(db, user, shop_id); stmt = stmt.where(ProductDraft.shop_id == shop_id)
    return db.scalars(stmt.order_by(ProductDraft.id.desc())).all()


@app.get("/points")
def points(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.company_id:
        return {"available": 0, "frozen": 0, "ledger": []}
    account = db.get(PointAccount, user.company_id)
    rows = db.scalars(select(PointLedger).where(PointLedger.company_id == user.company_id).order_by(PointLedger.id.desc()).limit(50)).all()
    return {"available": account.available, "frozen": account.frozen, "ledger": [LedgerOut.model_validate(row) for row in rows]}


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
