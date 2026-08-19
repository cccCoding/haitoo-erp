from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, inspect, or_, select, text
from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, engine, get_db
from .models import Company, PointAccount, PointLedger, PodTask, ProductDraft, ProductTemplate, Role, Shop, TaskStatus, TemplateGroup, User, UserShop
from .schemas import LedgerOut, LoginInput, PodTaskCreate, RechargeInput, SelectResult, ShopOut, TemplateCreate, TemplateGroupCreate, TemplateUpdate, UserOut
from .security import create_access_token, current_user, hash_password, require_roles, verify_password


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

    # 开发演示数据清理：移除旧版默认模板与已废弃类别，仅保留服装模板。
    db.execute(delete(ProductTemplate).where(ProductTemplate.name.in_(["白色马克杯正面", "M05L"])))
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
    """轻量兼容迁移，后续会替换为 Alembic 正式迁移。"""
    columns = {column["name"] for column in inspect(engine).get_columns("product_templates")}
    with engine.begin() as connection:
        if "description" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN description TEXT"))
        for column in ("package_weight", "package_length", "package_width", "package_height"):
            if column not in columns:
                connection.execute(text(f"ALTER TABLE product_templates ADD COLUMN {column} FLOAT"))
        if "sku_specifications" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN sku_specifications JSON"))


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
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": UserOut.model_validate(user)}


@app.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id) if user.company_id else None
    return {"user": UserOut.model_validate(user), "company": {"id": company.id, "name": company.name} if company else None}


@app.get("/shops", response_model=list[ShopOut])
def list_shops(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Shop).where(Shop.id.in_(allowed_shop_ids(db, user))).order_by(Shop.id)).all()


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


@app.post("/tasks")
def create_task(payload: PodTaskCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    shop = ensure_shop(db, user, payload.shop_id)
    template = db.get(ProductTemplate, payload.template_id)
    if not template or not (template.is_platform or template.company_id == user.company_id):
        raise HTTPException(404, "产品模板不存在")
    account = db.get(PointAccount, user.company_id)
    estimated = 20 if payload.quality == "2K" else 12
    if not account or account.available < estimated:
        raise HTTPException(400, "可用积分不足，无法创建 AI 任务")
    account.available -= estimated; account.frozen += estimated
    task = PodTask(company_id=shop.company_id, shop_id=shop.id, template_id=template.id, created_by=user.id, status=TaskStatus.AWAITING_SELECTION, parameters=payload.model_dump(), estimated_points=estimated, result_urls=["https://placehold.co/720x960/EDE9FE/5B3FD6?text=POD+Result+1", "https://placehold.co/720x960/F3E8FF/5B3FD6?text=POD+Result+2"])
    db.add(task); db.flush()
    db.add(PointLedger(company_id=shop.company_id, actor_id=user.id, task_id=task.id, entry_type="ai_freeze", amount=-estimated, balance_after=account.available, note="AI 创作预冻结"))
    db.commit(); db.refresh(task)
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
        raise HTTPException(400, "超级管理员请在平台端选择公司")
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
