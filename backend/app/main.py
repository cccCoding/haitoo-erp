from contextlib import asynccontextmanager
import hashlib
import hmac
from io import BytesIO
import json
import logging
import mimetypes
import re
import secrets
import string
import time
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4
import zipfile
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, inspect, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .database import engine, get_db
from .models import AIProviderSetting, Company, MaterialAsset, PodTask, ProductDraft, ProductTemplate, Role, Shop, TaskQueueSetting, TaskStatus, TemplateGroup, TiktokCategoryCatalog, User, UserAIProviderCredential, UserShop, UserTemplatePrompt, UserTemplateWhiteImage
from .schemas import AdminCompanyCreate, AIProviderCredentialUpdate, AIProviderSettingUpdate, ClaimMaterials, DraftTitleGenerate, DraftUpdate, ImageUploadPresignInput, LoginInput, MaterialDownloadInput, MaterialDraftCreate, MaterialUploadCommitInput, MaterialUploadPresignInput, MemberCreate, MemberUpdate, MiaoshouAccountUpdate, MiaoshouShopQuery, MyUserCodeUpdate, PodTaskCreate, ShopManagerUpdate, ShopOut, TaskQueueSettingUpdate, TemplateCreate, TemplateGroupCreate, TemplateUpdate, TiktokCategoryCatalogUpdate, TiktokDraftExportInput, UploadPresignInput, UserOut, UserTemplatePromptCreate, UserTemplatePromptUpdate, UserTemplateWhiteImageCreate, UserTemplateWhiteImageUpdate
from .security import create_access_token, current_user, hash_password, require_roles, verify_password
from .ai_providers import ProviderError, generate_draft_title, provider_supports_user_credentials
from .credentials import decrypt_secret, encrypt_secret
from .storage import StorageError, create_image_upload_url, is_company_r2_url, is_public_r2_url, upload_image_bytes_async
from .logging_config import configure_logging
from .tiktok_export import build_workbook as build_tiktok_workbook, category_base_requirements, parse_listing_options, validate_attributes
import httpx


configure_logging()
logger = logging.getLogger(__name__)


def initialize_system_defaults(db: Session) -> None:
    """幂等补齐平台运行所需配置，不创建任何公司或用户。"""
    if not db.get(AIProviderSetting, "seedream"):
        db.add(AIProviderSetting(provider="seedream", display_name="Seedream", model="doubao-seedream-4-0-250828", enabled=True, is_default=False))
    if not db.get(AIProviderSetting, "qwen"):
        db.add(AIProviderSetting(provider="qwen", display_name="千问图像编辑", model="qwen-image-edit", enabled=True, is_default=False))
    if not db.get(AIProviderSetting, "gemini"):
        db.add(AIProviderSetting(provider="gemini", display_name="Gemini 图像生成", model="gemini-2.5-flash-image", enabled=True, is_default=False))
    # 印花贴合生产默认使用 Nano Banana Fast；保留其他适配器供后台切换。
    grsai_setting = db.get(AIProviderSetting, "grsai")
    if not grsai_setting:
        db.execute(update(AIProviderSetting).where(AIProviderSetting.is_default.is_(True)).values(is_default=False))
        db.add(AIProviderSetting(provider="grsai", display_name="Grsai", model="nano-banana-fast", enabled=True, is_default=True))
    elif grsai_setting.display_name == "Nano Banana Fast":
        grsai_setting.display_name = "Grsai"
    if not db.get(TaskQueueSetting, 1):
        db.add(TaskQueueSetting(id=1, submit_interval_seconds=1, result_interval_seconds=5))
    # 类目库全部由公司管理员上传创建；清理早期版本自动生成的全局默认类目库。
    db.execute(delete(TiktokCategoryCatalog).where(TiktokCategoryCatalog.company_id.is_(None)))
    # 启动时只补齐必要的系统配置，绝不创建业务账号或公司。
    db.commit()


def ensure_schema(connection=None) -> None:
    """首个 Alembic 基线版本专用的旧数据库兼容逻辑，请勿用于应用启动。"""
    if connection is None:
        with engine.begin() as owned_connection:
            ensure_schema(owned_connection)
        return
    if connection is not None:
        # 一次性清理已经下线的旧计费数据结构；重复启动时无副作用。
        inspector = inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("product_templates")}
        quote = connection.dialect.identifier_preparer.quote
        table_names = set(inspector.get_table_names())
        for table_name in ("non_ai_point_rules", "point_ledgers", "point_accounts"):
            if table_name in table_names:
                connection.execute(text(f"DROP TABLE {quote(table_name)}"))
        for table_name, obsolete_columns in (
            ("pod_tasks", ("estimated_points", "actual_points", "refunded_points")),
        ):
            if table_name not in table_names:
                continue
            existing_columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
            for column_name in obsolete_columns:
                if column_name in existing_columns:
                    connection.execute(text(f"ALTER TABLE {quote(table_name)} DROP COLUMN {quote(column_name)}"))
        # `print_areas` 已从产品模板定义中移除。旧库中若仍保留 NOT NULL 的
        # 无默认值列，会导致 ORM 新建模板时 INSERT 失败（MySQL 1364）。
        if "print_areas" in columns:
            connection.execute(text("ALTER TABLE product_templates DROP COLUMN print_areas"))
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
        if "ai_prompts" not in columns:
            connection.execute(text("ALTER TABLE product_templates ADD COLUMN ai_prompts JSON"))
        draft_columns = {column["name"] for column in inspect(connection).get_columns("product_drafts")}
        draft_title_column = next(
            (column for column in inspect(connection).get_columns("product_drafts") if column["name"] == "title"),
            None,
        )
        if (
            draft_title_column
            and getattr(draft_title_column["type"], "length", None) != 255
            and connection.dialect.name in {"mysql", "mariadb"}
        ):
            connection.execute(text("ALTER TABLE product_drafts MODIFY COLUMN title VARCHAR(255) NOT NULL"))
        if "sku_items" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN sku_items JSON"))
        if "template_id" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN template_id INTEGER"))
        if "miaoshou_collect_box_id" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN miaoshou_collect_box_id VARCHAR(120)"))
        if "tiktok_collect_box_id" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN tiktok_collect_box_id VARCHAR(120)"))
        if "export_count" not in draft_columns:
            connection.execute(text("ALTER TABLE product_drafts ADD COLUMN export_count INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("UPDATE product_drafts SET export_count = 0 WHERE export_count IS NULL"))
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
        # 旧批次结构只在首次升级时存在。按已确认的迁移策略清空历史任务，
        # 并先解除素材和草稿引用，避免新任务复用旧 ID 后产生错误关联。
        if "pod_task_batches" in table_names:
            connection.execute(text("UPDATE material_assets SET source_task_id = NULL WHERE source_task_id IS NOT NULL"))
            connection.execute(text("UPDATE product_drafts SET source_task_id = NULL WHERE source_task_id IS NOT NULL"))
            connection.execute(text("DELETE FROM pod_tasks"))
            connection.execute(text(f"DROP TABLE {quote('pod_task_batches')}"))
        task_columns = {column["name"] for column in inspect(connection).get_columns("pod_tasks")}
        for column, definition in (
            ("provider", "VARCHAR(40)"), ("provider_model", "VARCHAR(120)"),
            ("provider_task_id", "VARCHAR(160)"), ("failure_reason", "VARCHAR(500)"),
            ("result_map", "JSON"), ("submit_attempts", "INTEGER DEFAULT 0"),
            ("submitted_at", "DATETIME"), ("completed_at", "DATETIME"),
        ):
            if column not in task_columns:
                connection.execute(text(f"ALTER TABLE pod_tasks ADD COLUMN {column} {definition}"))
        task_columns = {column["name"] for column in inspect(connection).get_columns("pod_tasks")}
        for obsolete_column in ("total_prints", "total_batches", "completed_batches", "failed_batches"):
            if obsolete_column in task_columns:
                connection.execute(text(f"ALTER TABLE pod_tasks DROP COLUMN {obsolete_column}"))
        provider_columns = {column["name"] for column in inspect(connection).get_columns("ai_provider_settings")}
        if "images_per_task" not in provider_columns:
            connection.execute(text("ALTER TABLE ai_provider_settings ADD COLUMN images_per_task INTEGER DEFAULT 1"))
            if "batch_size" in provider_columns:
                connection.execute(text("UPDATE ai_provider_settings SET images_per_task = batch_size"))
        provider_columns = {column["name"] for column in inspect(connection).get_columns("ai_provider_settings")}
        for obsolete_column in ("batch_size", "max_concurrency"):
            if obsolete_column in provider_columns:
                connection.execute(text(f"ALTER TABLE ai_provider_settings DROP COLUMN {obsolete_column}"))
        task_indexes = {index["name"] for index in inspect(connection).get_indexes("pod_tasks")}
        if "ix_pod_tasks_provider_model" not in task_indexes:
            connection.execute(text("CREATE INDEX ix_pod_tasks_provider_model ON pod_tasks (provider, provider_model)"))
        if "shop_id" in task_columns:
            connection.execute(text("ALTER TABLE pod_tasks DROP COLUMN shop_id"))
        company_columns = {column["name"] for column in inspect(connection).get_columns("companies")}
        if "miaoshou_app_id" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN miaoshou_app_id VARCHAR(255)"))
        if "miaoshou_secret_encrypted" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN miaoshou_secret_encrypted TEXT"))
        user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "user_code" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN user_code VARCHAR(2)"))
        if "token_version" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
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
        shop_columns = {column["name"] for column in inspect(connection).get_columns("shops")}
        for column, definition in (("nickname", "VARCHAR(120)"), ("platform", "VARCHAR(40)"), ("auth_expires_at", "VARCHAR(50)")):
            if column not in shop_columns:
                connection.execute(text(f"ALTER TABLE shops ADD COLUMN {column} {definition}"))
        material_columns = {column["name"]: column for column in inspect(connection).get_columns("material_assets")}
        if "template_id" not in material_columns:
            connection.execute(text("ALTER TABLE material_assets ADD COLUMN template_id INTEGER"))
        if "sku" not in material_columns:
            connection.execute(text("ALTER TABLE material_assets ADD COLUMN sku VARCHAR(24)"))
        material_indexes = inspect(connection).get_indexes("material_assets")
        material_constraints = inspect(connection).get_unique_constraints("material_assets")
        has_material_sku_unique_index = any(
            index.get("name") == "uq_material_assets_sku" or (
                index.get("unique") and index.get("column_names") == ["sku"]
            )
            for index in material_indexes
        ) or any(
            constraint.get("name") == "uq_material_assets_sku" or constraint.get("column_names") == ["sku"]
            for constraint in material_constraints
        )
        if not has_material_sku_unique_index:
            connection.execute(text("CREATE UNIQUE INDEX uq_material_assets_sku ON material_assets (sku)"))
        if connection.dialect.name == "mysql" and not material_columns["source_task_id"]["nullable"]:
            connection.execute(text("ALTER TABLE material_assets MODIFY COLUMN source_task_id INTEGER NULL"))
        # AI 生成素材归属任务创作人；本地上传素材继续归属上传人。
        # 同步修正历史上由管理员代为领取、但任务实际由员工创作的素材。
        connection.execute(text("""
            UPDATE material_assets
            SET claimed_by = (
                SELECT created_by FROM pod_tasks
                WHERE pod_tasks.id = material_assets.source_task_id
            )
            WHERE source_task_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM pod_tasks
                  WHERE pod_tasks.id = material_assets.source_task_id
              )
        """))
        draft_columns = {column["name"]: column for column in inspect(connection).get_columns("product_drafts")}
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
    logger.info("应用初始化开始")
    from .schema_version import assert_schema_current

    assert_schema_current(engine)
    logger.info("应用初始化完成")
    try:
        yield
    finally:
        logger.info("应用关闭")


app = FastAPI(title="Haitoro POD API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def log_request(request: Request, call_next):
    """为每个 HTTP 请求记录可关联的结果和耗时。"""
    supplied_request_id = request.headers.get("x-request-id", "")
    request_id = supplied_request_id if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied_request_id) else uuid4().hex
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.exception(
            "HTTP 请求异常 | request_id=%s method=%s path=%s duration_ms=%.2f",
            request_id, request.method, request.url.path, duration_ms,
        )
        raise
    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "HTTP 请求完成 | request_id=%s method=%s path=%s status=%s duration_ms=%.2f client=%s",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
        request.client.host if request.client else "unknown",
    )
    return response


def allowed_shop_ids(db: Session, user: User) -> set[int]:
    if user.role == Role.SUPER_ADMIN:
        return set(db.scalars(select(Shop.id)).all())
    if user.role == Role.COMPANY_ADMIN:
        return set(db.scalars(select(Shop.id).where(Shop.company_id == user.company_id)).all())
    return set(db.scalars(select(UserShop.shop_id).where(UserShop.user_id == user.id)).all())


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
    return bool(task and (
        user.role == Role.SUPER_ADMIN
        or task.company_id == user.company_id
        and (user.role == Role.COMPANY_ADMIN or task.created_by == user.id)
    ))


def can_access_draft(draft: ProductDraft | None, user: User) -> bool:
    """普通员工仅可访问自己的草稿，公司管理员可访问本公司全部草稿。"""
    return bool(draft and (
        user.role == Role.SUPER_ADMIN
        or draft.company_id == user.company_id
        and (user.role == Role.COMPANY_ADMIN or draft.created_by == user.id)
    ))


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
    return {
        "user": UserOut.model_validate(user),
        "company": {
            "id": company.id,
            "name": company.name,
            "miaoshou_configured": bool(company.miaoshou_app_id and company.miaoshou_secret_encrypted),
        } if company else None,
    }


@app.patch("/me", response_model=UserOut)
def update_my_user_code(payload: MyUserCodeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """当前账号只能设置自己的名称和用户代码。"""
    if payload.user_code and user_code_in_use(db, user.company_id, payload.user_code, user.id):
        raise HTTPException(400, "该用户代码已被使用")
    if payload.name is not None:
        user.name = payload.name
    if payload.user_code is not None:
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


def mask_api_key(api_key: str) -> str:
    """生成仅供管理员辨认密钥的脱敏预览，不向前端返回原文。"""
    if len(api_key) <= 11:
        return f"{api_key[:3]}...{api_key[-2:]}"
    return f"{api_key[:6]}...{api_key[-5:]}"


@app.get("/members")
def list_members(user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    members = db.scalars(
        select(User).where(
            User.company_id == user.company_id,
            User.role.in_([Role.COMPANY_ADMIN, Role.MEMBER]),
        ).order_by(User.role, User.id.desc())
    ).all()
    member_ids = [member.id for member in members]
    credential_rows = db.scalars(select(UserAIProviderCredential).where(
        UserAIProviderCredential.company_id == user.company_id,
        UserAIProviderCredential.user_id.in_(member_ids),
    )).all() if member_ids else []
    configured = {
        (row.user_id, row.provider)
        for row in credential_rows
    }
    credential_previews = {
        (row.user_id, row.provider): mask_api_key(decrypt_secret(row.secret_encrypted))
        for row in credential_rows
    }
    enabled_providers = db.scalars(
        select(AIProviderSetting).where(AIProviderSetting.enabled.is_(True)).order_by(AIProviderSetting.provider)
    ).all()
    return [
        UserOut.model_validate(member).model_dump() | {
            "ai_provider_credentials": {
                provider.provider: (member.id, provider.provider) in configured
                for provider in enabled_providers
            },
            "ai_provider_credential_previews": {
                provider.provider: credential_previews.get((member.id, provider.provider))
                for provider in enabled_providers
                if (member.id, provider.provider) in configured
            }
        }
        for member in members
    ]


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
        if not payload.user_code:
            raise HTTPException(400, "用户代码不能为空")
        if payload.user_code and user_code_in_use(db, user.company_id, payload.user_code, member.id):
            raise HTTPException(400, "该用户代码已被使用")
        member.user_code = payload.user_code
    if payload.password is not None:
        member.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        member.is_active = payload.is_active
    commit_user_code_change(db); db.refresh(member)
    return member


def get_company_credential_user(db: Session, user: User, member_id: int) -> User:
    member = db.get(User, member_id)
    if not member or member.company_id != user.company_id or member.role not in {Role.COMPANY_ADMIN, Role.MEMBER}:
        raise HTTPException(404, "公司用户不存在")
    return member


@app.put("/members/{member_id}/ai-provider-credentials/{provider}")
def update_member_ai_provider_credential(
    member_id: int,
    provider: str,
    payload: AIProviderCredentialUpdate,
    user: User = Depends(require_roles(Role.COMPANY_ADMIN)),
    db: Session = Depends(get_db),
):
    """公司管理员为本公司成员保存独立模型密钥；接口永不返回密钥内容。"""
    member = get_company_credential_user(db, user, member_id)
    setting = db.get(AIProviderSetting, provider)
    if not setting or not setting.enabled:
        raise HTTPException(400, "模型平台不存在或未启用")
    if not provider_supports_user_credentials(provider):
        raise HTTPException(400, "该模型平台不支持独立密钥")
    credential = db.scalar(select(UserAIProviderCredential).where(
        UserAIProviderCredential.user_id == member.id,
        UserAIProviderCredential.provider == provider,
    ))
    if credential:
        credential.secret_encrypted = encrypt_secret(payload.api_key)
        credential.updated_at = datetime.utcnow()
    else:
        credential = UserAIProviderCredential(
            company_id=user.company_id,
            user_id=member.id,
            provider=provider,
            secret_encrypted=encrypt_secret(payload.api_key),
        )
        db.add(credential)
    db.commit()
    return {"member_id": member.id, "provider": provider, "configured": True}


@app.delete("/members/{member_id}/ai-provider-credentials/{provider}")
def delete_member_ai_provider_credential(
    member_id: int,
    provider: str,
    user: User = Depends(require_roles(Role.COMPANY_ADMIN)),
    db: Session = Depends(get_db),
):
    member = get_company_credential_user(db, user, member_id)
    credential = db.scalar(select(UserAIProviderCredential).where(
        UserAIProviderCredential.user_id == member.id,
        UserAIProviderCredential.provider == provider,
    ))
    if credential:
        db.delete(credential)
        db.commit()
    return {"member_id": member.id, "provider": provider, "configured": False}


@app.post("/miaoshou/shops")
async def list_miaoshou_shops(payload: MiaoshouShopQuery, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id)
    if not company or not company.miaoshou_app_id or not company.miaoshou_secret_encrypted:
        raise HTTPException(400, "尚未配置妙手 API Key，请先在店铺管理中完成配置")

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


@app.put("/miaoshou/account")
def update_miaoshou_account(
    payload: MiaoshouAccountUpdate,
    user: User = Depends(require_roles(Role.COMPANY_ADMIN)),
    db: Session = Depends(get_db),
):
    """公司管理员配置本公司的妙手凭据；接口永不返回密钥内容。"""
    company = db.get(Company, user.company_id)
    if not company:
        raise HTTPException(404, "公司不存在")
    company.miaoshou_app_id = payload.app_id
    company.miaoshou_secret_encrypted = encrypt_secret(payload.app_secret)
    db.commit()
    return {"company_id": company.id, "configured": True}


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
    data = payload.model_dump()
    data["cover_url"] = validate_template_image_url(data["cover_url"], user.company_id, None)
    data["size_chart_url"] = validate_template_image_url(data["size_chart_url"], user.company_id, None)
    template = ProductTemplate(company_id=user.company_id, **data)
    db.add(template); db.commit(); db.refresh(template)
    return template


def get_company_template(db: Session, user: User, template_id: int) -> ProductTemplate:
    template = db.get(ProductTemplate, template_id)
    if not template or template.company_id != user.company_id or template.is_platform:
        raise HTTPException(404, "公司模板不存在或不可修改")
    return template


def get_usable_template(db: Session, user: User, template_id: int) -> ProductTemplate:
    template = db.get(ProductTemplate, template_id)
    if not template or not (template.is_platform or template.company_id == user.company_id):
        raise HTTPException(404, "产品模板不存在")
    return template


def get_resource_owner(db: Session, user: User, requested_user_id: int | None) -> User:
    owner_id = requested_user_id or user.id
    if owner_id != user.id and user.role != Role.COMPANY_ADMIN:
        raise HTTPException(403, "只能管理自己的模板资源")
    owner = db.get(User, owner_id)
    if not owner or owner.company_id != user.company_id or owner.role not in {Role.COMPANY_ADMIN, Role.MEMBER}:
        raise HTTPException(404, "公司用户不存在")
    return owner


def commit_template_resource(db: Session, duplicate_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, duplicate_message) from exc


@app.get("/user-template-resources")
def list_user_template_resources(
    template_id: int | None = None,
    user_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    owner = get_resource_owner(db, user, user_id)
    white_image_query = select(UserTemplateWhiteImage).where(
        UserTemplateWhiteImage.company_id == user.company_id,
        UserTemplateWhiteImage.user_id == owner.id,
    )
    prompt_query = select(UserTemplatePrompt).where(
        UserTemplatePrompt.company_id == user.company_id,
        UserTemplatePrompt.user_id == owner.id,
    )
    if template_id is not None:
        template = get_usable_template(db, user, template_id)
        white_image_query = white_image_query.where(UserTemplateWhiteImage.template_id == template.id)
        prompt_query = prompt_query.where(UserTemplatePrompt.template_id == template.id)
    white_images = db.scalars(white_image_query.order_by(UserTemplateWhiteImage.id.desc())).all()
    prompts = db.scalars(prompt_query.order_by(UserTemplatePrompt.id.desc())).all()
    return {
        "user_id": owner.id,
        "template_id": template_id,
        "white_images": [serialize_record(item) for item in white_images],
        "prompts": [serialize_record(item) for item in prompts],
    }


@app.post("/user-template-white-images")
def create_user_template_white_image(
    payload: UserTemplateWhiteImageCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    template = get_usable_template(db, user, payload.template_id)
    owner = get_resource_owner(db, user, payload.user_id)
    count = db.scalar(select(func.count()).select_from(UserTemplateWhiteImage).where(
        UserTemplateWhiteImage.user_id == owner.id,
        UserTemplateWhiteImage.template_id == template.id,
    )) or 0
    if count >= 50:
        raise HTTPException(400, "每个模板最多保存 50 张白底图")
    if not is_company_r2_url(payload.image_url, user.company_id, "template-white"):
        raise HTTPException(400, "白底图必须通过当前公司的专用上传接口上传")
    item = UserTemplateWhiteImage(
        company_id=user.company_id, user_id=owner.id, template_id=template.id,
        name=payload.name, image_url=payload.image_url,
    )
    db.add(item); commit_template_resource(db, "该模板下已有同名白底图"); db.refresh(item)
    return serialize_record(item)


def get_managed_white_image(db: Session, user: User, item_id: int) -> UserTemplateWhiteImage:
    item = db.get(UserTemplateWhiteImage, item_id)
    if not item or item.company_id != user.company_id or (item.user_id != user.id and user.role != Role.COMPANY_ADMIN):
        raise HTTPException(404, "白底图不存在或无权操作")
    return item


@app.put("/user-template-white-images/{item_id}")
def update_user_template_white_image(
    item_id: int, payload: UserTemplateWhiteImageUpdate,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    item = get_managed_white_image(db, user, item_id)
    if payload.image_url is not None and not is_company_r2_url(payload.image_url, user.company_id, "template-white"):
        raise HTTPException(400, "白底图必须通过当前公司的专用上传接口上传")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.utcnow()
    commit_template_resource(db, "该模板下已有同名白底图"); db.refresh(item)
    return serialize_record(item)


@app.delete("/user-template-white-images/{item_id}")
def delete_user_template_white_image(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = get_managed_white_image(db, user, item_id)
    db.delete(item); db.commit()
    return {"deleted": True}


@app.post("/user-template-prompts")
def create_user_template_prompt(
    payload: UserTemplatePromptCreate,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    template = get_usable_template(db, user, payload.template_id)
    owner = get_resource_owner(db, user, payload.user_id)
    count = db.scalar(select(func.count()).select_from(UserTemplatePrompt).where(
        UserTemplatePrompt.user_id == owner.id,
        UserTemplatePrompt.template_id == template.id,
    )) or 0
    if count >= 50:
        raise HTTPException(400, "每个模板最多保存 50 条创作要求")
    item = UserTemplatePrompt(
        company_id=user.company_id, user_id=owner.id, template_id=template.id,
        name=payload.name, content=payload.content,
    )
    db.add(item); commit_template_resource(db, "该模板下已有同名创作要求"); db.refresh(item)
    return serialize_record(item)


def get_managed_template_prompt(db: Session, user: User, item_id: int) -> UserTemplatePrompt:
    item = db.get(UserTemplatePrompt, item_id)
    if not item or item.company_id != user.company_id or (item.user_id != user.id and user.role != Role.COMPANY_ADMIN):
        raise HTTPException(404, "创作要求不存在或无权操作")
    return item


@app.put("/user-template-prompts/{item_id}")
def update_user_template_prompt(
    item_id: int, payload: UserTemplatePromptUpdate,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    item = get_managed_template_prompt(db, user, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.utcnow()
    commit_template_resource(db, "该模板下已有同名创作要求"); db.refresh(item)
    return serialize_record(item)


@app.delete("/user-template-prompts/{item_id}")
def delete_user_template_prompt(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = get_managed_template_prompt(db, user, item_id)
    db.delete(item); db.commit()
    return {"deleted": True}


SKU_TEMPLATE_PATTERN = re.compile(r"^[A-Z0-9]{1,5}$")
SKU_ALPHABET = string.ascii_uppercase + string.digits


def validate_material_sku_source(template: ProductTemplate, owner: User) -> tuple[str, str]:
    """校验素材入库时生成永久 SKU 所需的模板名称和用户代码。"""
    template_name = (template.name or "").strip().upper()
    if not SKU_TEMPLATE_PATTERN.fullmatch(template_name):
        raise HTTPException(400, "模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字，请先修改模板名称")
    if not owner.user_code or len(owner.user_code.strip()) != 2:
        raise HTTPException(400, "请先在账号设置中填写两位用户代码，再上传或领取素材")
    return template_name, owner.user_code.strip().upper()


def add_material_asset_with_sku(
    db: Session, *, template: ProductTemplate, owner: User, company_id: int,
    source_task_id: int | None, url: str, name: str,
) -> MaterialAsset:
    """写入带永久 SKU 的素材；唯一索引冲突时在保存点内重新生成。"""
    template_name, user_code = validate_material_sku_source(template, owner)
    for _ in range(10):
        random_part = "".join(secrets.choice(SKU_ALPHABET) for _ in range(6))
        asset = MaterialAsset(
            company_id=company_id, source_task_id=source_task_id, template_id=template.id,
            url=url, name=name, sku=f"{template_name}{user_code}{random_part}", claimed_by=owner.id,
        )
        try:
            with db.begin_nested():
                db.add(asset)
                db.flush()
            return asset
        except IntegrityError as exc:
            if "sku" not in str(exc.orig).lower():
                raise
    raise HTTPException(503, "SKU 生成失败，请重试")


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


async def miaoshou_post(company: Company, path: str, body: dict) -> dict:
    """调用妙手开放平台，并统一处理鉴权和传输错误。"""
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
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"妙手接口调用失败：{exc}") from exc


async def create_common_collect_box_detail(draft: ProductDraft, company: Company, template: ProductTemplate) -> str:
    if draft.miaoshou_collect_box_id:
        return draft.miaoshou_collect_box_id
    result = await miaoshou_post(company, "/open/v1/product/common_collect_box/common_collect_box/add_common_collect_box_detail", build_common_collect_box_payload(draft, template))
    if result.get("code") != "success" and result.get("result") != "success":
        raise HTTPException(400, result.get("message") or result.get("code") or "妙手公共采集箱接口返回失败")
    collect_box_id = (result.get("data") or {}).get("commonCollectBoxDetailId")
    if collect_box_id is None:
        raise HTTPException(502, "妙手公共采集箱接口未返回商品编号")
    draft.miaoshou_collect_box_id = str(collect_box_id)
    return draft.miaoshou_collect_box_id


async def claim_common_collect_box_to_tiktok(draft: ProductDraft, company: Company) -> str:
    if draft.tiktok_collect_box_id:
        return draft.tiktok_collect_box_id
    if not draft.miaoshou_collect_box_id:
        raise HTTPException(400, "请先创建公共采集箱商品")
    result = await miaoshou_post(company, "/open/v1/product/common_collect_box/common_collect_box/claimed", {
        "detailSerialNumberPlatformList": [{"detailId": int(draft.miaoshou_collect_box_id), "platform": "tiktok", "serialNumber": 1}],
    })
    if result.get("code") != "success" and result.get("result") != "success":
        raise HTTPException(400, result.get("message") or result.get("code") or "妙手 TikTok 认领接口返回失败")
    mappings = ((result.get("data") or {}).get("platformCollectBoxDetailIdMap") or {})
    tiktok_mapping = mappings.get("tiktok") or mappings.get("TK") or mappings.get("TikTok") or {}
    tiktok_detail_id = tiktok_mapping.get(str(draft.miaoshou_collect_box_id)) or tiktok_mapping.get(draft.miaoshou_collect_box_id)
    if tiktok_detail_id is None:
        raise HTTPException(502, "妙手 TikTok 认领接口未返回采集箱商品编号")
    draft.tiktok_collect_box_id = str(tiktok_detail_id)
    return draft.tiktok_collect_box_id


@app.put("/templates/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    template = get_company_template(db, user, template_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "cover_url":
            value = validate_template_image_url(value, user.company_id, template.cover_url)
        elif field == "size_chart_url":
            value = validate_template_image_url(value, user.company_id, template.size_chart_url)
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


# 允许前端直传的业务目录；值即 R2 对象 key 首段。签名始终绑定调用方公司，
# 越权写到其他公司目录不可行，这里只限制可写入的业务类型。
DIRECT_UPLOAD_CATEGORIES = frozenset({"template", "template-size-chart", "template-white"})
TEMPLATE_IMAGE_CATEGORIES = ("template", "template-size-chart")
SUPPORTED_UPLOAD_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.post("/uploads/presign")
def presign_image_upload(payload: ImageUploadPresignInput, user: User = Depends(current_user)):
    """按业务目录批量签发 R2 直传地址，单张图片不再经 API 容器中转。"""
    if payload.category not in DIRECT_UPLOAD_CATEGORIES:
        raise HTTPException(400, "不支持的上传目录")
    if any(item.content_type not in SUPPORTED_UPLOAD_MIME_TYPES for item in payload.files):
        raise HTTPException(400, "请上传 JPG、PNG 或 WebP 图片")
    try:
        return [
            create_image_upload_url(item.content_type, item.content_length, user.company_id, payload.category)
            for item in payload.files
        ]
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc


def validate_template_image_url(url: str | None, company_id: int, current: str | None) -> str | None:
    """直传后地址由前端提交：只接受本公司模板目录的 R2 对象，或保持不变的历史值。"""
    if url is None or url == current:
        return url
    if not any(is_company_r2_url(url, company_id, category) for category in TEMPLATE_IMAGE_CATEGORIES):
        raise HTTPException(400, "模板图片和尺码图必须通过上传接口上传")
    return url


@app.post("/uploads/creative-asset/presign")
def presign_creative_asset(payload: UploadPresignInput, user: User = Depends(current_user)):
    if payload.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(400, "请上传 JPG、PNG 或 WebP 图片")
    try:
        return create_image_upload_url(payload.content_type, payload.content_length, user.company_id, "creative")
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc


MATERIAL_UPLOAD_CATEGORY = "material"


@app.post("/material-assets/presign")
def presign_material_assets(payload: MaterialUploadPresignInput, user: User = Depends(current_user)):
    """批量签发 R2 直传地址，让本地素材不经过 API 容器中转。"""
    for item in payload.files:
        if item.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(400, "请上传 JPG、PNG 或 WebP 图片")
    try:
        return [
            create_image_upload_url(item.content_type, item.content_length, user.company_id, MATERIAL_UPLOAD_CATEGORY)
            for item in payload.files
        ]
    except StorageError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/material-assets/commit")
def commit_material_assets(payload: MaterialUploadCommitInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """直传完成后批量登记素材；地址必须是本次签发到本公司素材目录的 R2 对象。"""
    template = get_company_template(db, user, payload.template_id)
    validate_material_sku_source(template, user)
    for item in payload.items:
        if not is_company_r2_url(item.url, user.company_id, MATERIAL_UPLOAD_CATEGORY):
            raise HTTPException(400, "素材地址无效，请重新上传")
    assets = [
        add_material_asset_with_sku(
            db, template=template, owner=user, company_id=user.company_id,
            source_task_id=None, url=item.url, name=(Path(item.name or "本地素材").name.rsplit(".", 1)[0] or "本地素材")[:180],
        )
        for item in payload.items
    ]
    db.commit()
    for asset in assets:
        db.refresh(asset)
    return [serialize_record(asset) for asset in assets]


def serialize_task_view(task: PodTask, creator_name: str, template_name: str, viewer: User, *, include_details: bool) -> dict:
    """任务列表只返回首图摘要；详情返回完整印花和结果映射。"""
    parameters = dict(task.parameters or {})
    print_urls = list(parameters.get("print_urls") or ([parameters["print_url"]] if parameters.get("print_url") else []))
    result_urls = list(task.result_urls or [])
    if not include_details:
        parameters.pop("print_urls", None)
        parameters["print_url"] = print_urls[0] if print_urls else None
    if viewer.role not in {Role.COMPANY_ADMIN, Role.SUPER_ADMIN} and viewer.id != task.created_by:
        for key in ("white_image_id", "white_image_url", "white_image_name", "personal_prompt_id", "personal_prompt_name"):
            parameters.pop(key, None)
        parameters["creative_requirement"] = None
        parameters["private_creative_configuration"] = True
    result = serialize_record(task) | {
        "parameters": parameters,
        "result_urls": result_urls if include_details else result_urls[:1],
        "result_count": len(result_urls),
        "created_by_name": creator_name,
        "template_name": template_name,
        "progress": {
            "total_prints": len(print_urls),
            "result_count": len(result_urls),
            "percent": 100 if task.status in (TaskStatus.AWAITING_SELECTION, TaskStatus.COMPLETED, TaskStatus.FAILED) else 0,
        },
    }
    return result


@app.get("/tasks")
def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    creator_id: int | None = Query(default=None, ge=1),
    status: TaskStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    normalized_created_from = created_from.astimezone(timezone.utc).replace(tzinfo=None) if created_from and created_from.tzinfo else created_from
    normalized_created_to = created_to.astimezone(timezone.utc).replace(tzinfo=None) if created_to and created_to.tzinfo else created_to
    if normalized_created_from and normalized_created_to and normalized_created_from > normalized_created_to:
        raise HTTPException(400, "创建开始时间不能晚于结束时间")
    filters = []
    if user.role != Role.SUPER_ADMIN:
        filters.append(PodTask.company_id == user.company_id)
    if user.role == Role.MEMBER:
        filters.append(PodTask.created_by == user.id)
    elif creator_id is not None:
        filters.append(PodTask.created_by == creator_id)
    if status is not None:
        filters.append(PodTask.status == status)
    if normalized_created_from is not None:
        filters.append(PodTask.created_at >= normalized_created_from)
    if normalized_created_to is not None:
        filters.append(PodTask.created_at <= normalized_created_to)
    total_stmt = select(func.count()).select_from(PodTask)
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = db.scalar(total_stmt) or 0
    page_count = max(1, (total + page_size - 1) // page_size)
    page = min(page, page_count)
    stmt = select(PodTask)
    if filters:
        stmt = stmt.where(*filters)
    tasks = db.scalars(stmt.order_by(PodTask.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    creator_ids = {task.created_by for task in tasks}
    creator_names = {member.id: member.name for member in db.scalars(select(User).where(User.id.in_(creator_ids))).all()} if creator_ids else {}
    template_ids = {task.template_id for task in tasks}
    template_names = {template.id: template.name for template in db.scalars(select(ProductTemplate).where(ProductTemplate.id.in_(template_ids))).all()} if template_ids else {}
    status_stmt = select(PodTask.status, func.count()).group_by(PodTask.status)
    if filters:
        status_stmt = status_stmt.where(*filters)
    status_counts = {status.value: count for status, count in db.execute(status_stmt).all()}
    active_stmt = select(func.count()).select_from(PodTask).where(PodTask.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))
    if filters:
        active_stmt = active_stmt.where(*filters)
    return {
        "items": [
            serialize_task_view(task, creator_names.get(task.created_by, "历史记录缺失"), template_names.get(task.template_id, "历史模板已删除"), user, include_details=False)
            for task in tasks
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "status_counts": status_counts,
        "active_count": db.scalar(active_stmt) or 0,
    }


@app.get("/tasks/{task_id}")
def get_task_detail(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not can_access_task(task, user):
        raise HTTPException(404, "任务不存在")
    creator = db.get(User, task.created_by)
    template = db.get(ProductTemplate, task.template_id)
    return serialize_task_view(task, creator.name if creator else "历史记录缺失", template.name if template else "历史模板已删除", user, include_details=True)


@app.get("/material-assets")
def list_material_assets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    creator_id: int | None = Query(default=None, ge=1),
    template_id: int | None = Query(default=None, ge=1),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    filters = []
    if user.role != Role.SUPER_ADMIN:
        filters.append(MaterialAsset.company_id == user.company_id)
    if user.role == Role.MEMBER:
        filters.append(MaterialAsset.claimed_by == user.id)
    elif creator_id is not None:
        filters.append(MaterialAsset.claimed_by == creator_id)
    if template_id is not None:
        filters.append(MaterialAsset.template_id == template_id)
    total_stmt = select(func.count()).select_from(MaterialAsset)
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = db.scalar(total_stmt) or 0
    page_count = max(1, (total + page_size - 1) // page_size)
    page = min(page, page_count)
    stmt = select(MaterialAsset)
    if filters:
        stmt = stmt.where(*filters)
    assets = db.scalars(stmt.order_by(MaterialAsset.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    creator_ids = {asset.claimed_by for asset in assets}
    creator_names = {
        creator.id: creator.name
        for creator in db.scalars(select(User).where(User.id.in_(creator_ids))).all()
    } if creator_ids else {}
    template_ids = {asset.template_id for asset in assets if asset.template_id is not None}
    template_names = {
        template.id: template.name
        for template in db.scalars(select(ProductTemplate).where(ProductTemplate.id.in_(template_ids))).all()
    } if template_ids else {}
    return {
        "items": [
            serialize_record(asset) | {
                "created_by": asset.claimed_by,
                "created_by_name": creator_names.get(asset.claimed_by, "历史记录缺失"),
                "template_name": template_names.get(asset.template_id, "未设置模板" if asset.template_id is None else "历史模板已删除"),
                "source_type": "ai_created" if asset.source_task_id is not None else "local_upload",
            }
            for asset in assets
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.delete("/material-assets/{asset_id}")
def delete_material_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """从当前公司的素材库移除一张图片。"""
    stmt = select(MaterialAsset).where(MaterialAsset.id == asset_id)
    if user.role != Role.SUPER_ADMIN:
        stmt = stmt.where(MaterialAsset.company_id == user.company_id)
    if user.role == Role.MEMBER:
        stmt = stmt.where(MaterialAsset.claimed_by == user.id)
    asset = db.scalar(stmt)
    if not asset:
        raise HTTPException(404, "素材不存在或无权删除")

    db.delete(asset)
    db.commit()
    return {"deleted": True}


def _download_filename(asset: MaterialAsset, content_type: str | None = None) -> str:
    """使用永久唯一的素材 SKU 生成下载文件名。"""
    name = re.sub(r'[^A-Za-z0-9_-]', "_", asset.sku or "") or f"material-{asset.id}"
    url_suffix = Path(unquote(urlsplit(asset.url).path)).suffix
    guessed_suffix = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ""
    suffix = url_suffix if url_suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else guessed_suffix
    return f"{name}{suffix or '.jpg'}"


@app.post("/material-assets/download")
async def download_material_assets(
    payload: MaterialDownloadInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """下载有权限访问的素材；单张返回原图，多张打包为 ZIP。"""
    requested_ids = list(dict.fromkeys(payload.material_asset_ids))
    stmt = select(MaterialAsset).where(MaterialAsset.id.in_(requested_ids))
    if user.role != Role.SUPER_ADMIN:
        stmt = stmt.where(MaterialAsset.company_id == user.company_id)
    if user.role == Role.MEMBER:
        stmt = stmt.where(MaterialAsset.claimed_by == user.id)
    assets_by_id = {asset.id: asset for asset in db.scalars(stmt).all()}
    if len(assets_by_id) != len(requested_ids):
        raise HTTPException(404, "素材不存在或无权下载")
    assets = [assets_by_id[asset_id] for asset_id in requested_ids]

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            downloads = []
            for asset in assets:
                remote = await client.get(asset.url)
                remote.raise_for_status()
                downloads.append((asset, remote.content, remote.headers.get("content-type")))
    except httpx.HTTPError as exc:
        logger.warning("下载素材源文件失败：%s", exc)
        raise HTTPException(502, "读取素材源文件失败，请稍后重试") from exc

    if len(downloads) == 1:
        asset, content, content_type = downloads[0]
        filename = _download_filename(asset, content_type)
        return Response(
            content=content,
            media_type=(content_type or "application/octet-stream").split(";", 1)[0],
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for asset, content, content_type in downloads:
            bundle.writestr(_download_filename(asset, content_type), content)
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=haitoro-materials.zip"},
    )


@app.get("/admin/ai-providers")
def list_ai_providers(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    return [serialize_record(setting) for setting in db.scalars(select(AIProviderSetting).order_by(AIProviderSetting.provider)).all()]


@app.get("/admin/overview")
def admin_overview(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    settings = get_settings()
    now = datetime.utcnow()
    queued_tasks = db.scalar(select(func.count()).select_from(PodTask).where(PodTask.status == TaskStatus.QUEUED)) or 0
    running_tasks = db.scalar(select(func.count()).select_from(PodTask).where(PodTask.status == TaskStatus.RUNNING)) or 0
    failed_tasks = db.scalar(select(func.count()).select_from(PodTask).where(PodTask.status == TaskStatus.FAILED)) or 0
    retrying_tasks = db.scalar(select(func.count()).select_from(PodTask).where(PodTask.status == TaskStatus.QUEUED, PodTask.submit_attempts > 0)) or 0
    oldest = db.scalar(select(func.min(PodTask.created_at)).where(PodTask.status == TaskStatus.QUEUED))
    backlog_minutes = int((now - oldest).total_seconds() / 60) if oldest else 0
    terminal_hour = db.scalars(select(PodTask).where(
        PodTask.status.in_([TaskStatus.AWAITING_SELECTION, TaskStatus.COMPLETED, TaskStatus.FAILED]),
        PodTask.completed_at >= now - timedelta(hours=1),
    )).all()
    terminal_15m = [task for task in terminal_hour if task.completed_at and task.completed_at >= now - timedelta(minutes=15)]
    completed_hour = [task for task in terminal_hour if task.status != TaskStatus.FAILED]
    failed_hour = [task for task in terminal_hour if task.status == TaskStatus.FAILED]
    failed_15m = sum(task.status == TaskStatus.FAILED for task in terminal_15m)
    failure_rate_15m = round(failed_15m * 100 / len(terminal_15m), 1) if terminal_15m else 0.0
    model_rows = db.execute(
        select(PodTask.provider, PodTask.provider_model, PodTask.status, func.count())
        .where(PodTask.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.FAILED]))
        .group_by(PodTask.provider, PodTask.provider_model, PodTask.status)
    ).all()
    model_backlog: dict[tuple[str, str], dict] = {}
    for provider, model, status, count in model_rows:
        key = (provider or "unknown", model or "unknown")
        item = model_backlog.setdefault(key, {"provider": key[0], "model": key[1], "queued": 0, "running": 0, "failed": 0})
        item[status.value] = count
    queue_alert = queued_tasks > 200 or backlog_minutes > 10 or (len(terminal_15m) > 0 and failure_rate_15m > 10)
    return {
        "companies": db.scalar(select(func.count()).select_from(Company)) or 0,
        "shops": db.scalar(select(func.count()).select_from(Shop)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "tasks": db.scalar(select(func.count()).select_from(PodTask)) or 0,
        "running_tasks": queued_tasks + running_tasks,
        "queue": {
            "queued": queued_tasks,
            "running": running_tasks,
            "retrying": retrying_tasks,
            "failed": failed_tasks,
            "oldest_wait_minutes": backlog_minutes,
            "completed_tasks_last_hour": len(completed_hour),
            "completed_prints_last_hour": sum(len((task.parameters or {}).get("print_urls") or []) for task in completed_hour),
            "failed_tasks_last_hour": len(failed_hour),
            "failure_rate_15m": failure_rate_15m,
            "model_backlog": sorted(model_backlog.values(), key=lambda item: (-item["queued"], item["provider"], item["model"])),
            "alert": queue_alert,
        },
        "storage_ready": bool(
            settings.r2_access_key_id
            and settings.r2_secret_access_key
            and settings.r2_bucket
            and (settings.r2_endpoint or settings.r2_account_id)
            and settings.r2_public_base_url
        ),
    }


@app.get("/admin/companies")
def list_admin_companies(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    companies = db.scalars(select(Company).order_by(Company.id.desc())).all()
    result = []
    for company in companies:
        result.append({
            "id": company.id,
            "name": company.name,
            "is_active": company.is_active,
            "created_at": timestamp_ms(company.created_at),
            "admin_users": [UserOut.model_validate(item) for item in db.scalars(select(User).where(User.company_id == company.id, User.role == Role.COMPANY_ADMIN).order_by(User.id)).all()],
        })
    return result


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
    db.commit(); db.refresh(company)
    return {"id": company.id, "name": company.name}


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
    setting.images_per_task = payload.images_per_task
    if setting.is_default is False and not db.scalar(select(AIProviderSetting).where(AIProviderSetting.is_default.is_(True), AIProviderSetting.provider != provider)) and payload.enabled:
        setting.is_default = True
    db.commit(); db.refresh(setting)
    return serialize_record(setting)


@app.get("/admin/task-queue-settings")
def get_task_queue_settings(user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    setting = db.get(TaskQueueSetting, 1)
    if not setting:
        setting = TaskQueueSetting(id=1, submit_interval_seconds=1, result_interval_seconds=5)
        db.add(setting); db.commit(); db.refresh(setting)
    return serialize_record(setting)


@app.put("/admin/task-queue-settings")
def update_task_queue_settings(payload: TaskQueueSettingUpdate, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    setting = db.get(TaskQueueSetting, 1) or TaskQueueSetting(id=1)
    setting.submit_interval_seconds = payload.submit_interval_seconds
    setting.result_interval_seconds = payload.result_interval_seconds
    db.add(setting); db.commit(); db.refresh(setting)
    return serialize_record(setting)


def map_task_results(task: PodTask, urls: list[str]) -> list[dict]:
    """按任务内印花顺序映射第三方结果，拒绝无法无歧义对应的响应。"""
    parameters = task.parameters or {}
    print_urls = list(parameters.get("print_urls") or ([parameters["print_url"]] if parameters.get("print_url") else []))
    if not print_urls or not urls:
        raise ProviderError("模型未返回可映射的印花结果")
    if len(print_urls) == 1:
        return [{"print_url": print_urls[0], "result_urls": urls}]
    if len(urls) % len(print_urls) != 0:
        raise ProviderError("模型返回结果数无法与任务印花逐一对应，请将单个任务印花图数量设为 1")
    per_print = len(urls) // len(print_urls)
    return [
        {"print_url": print_url, "result_urls": urls[index * per_print:(index + 1) * per_print]}
        for index, print_url in enumerate(print_urls)
    ]
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
def create_task(payload: PodTaskCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    template = get_usable_template(db, user, payload.template_id)
    white_image = db.scalar(select(UserTemplateWhiteImage).where(
        UserTemplateWhiteImage.id == payload.white_image_id,
        UserTemplateWhiteImage.company_id == user.company_id,
        UserTemplateWhiteImage.user_id == user.id,
        UserTemplateWhiteImage.template_id == template.id,
    ))
    if not white_image:
        raise HTTPException(400, "请选择当前模板下自己的产品白底图")
    if not is_company_r2_url(white_image.image_url, user.company_id, "template-white"):
        raise HTTPException(400, "所选产品白底图地址无效，请重新上传")
    raw_print_urls = payload.print_urls or ([payload.print_url] if payload.print_url else [])
    print_urls = list(dict.fromkeys(url for url in raw_print_urls if url))
    if not print_urls:
        raise HTTPException(400, "请至少上传一张印花图")
    if len(print_urls) > 500:
        raise HTTPException(400, "单次印花贴合最多支持 500 张图片")
    if any(not is_company_r2_url(url, user.company_id, "creative") for url in print_urls):
        raise HTTPException(400, "印花图必须通过当前公司的 R2 直传地址上传")
    provider = None
    if payload.provider:
        provider = db.get(AIProviderSetting, payload.provider)
        if not provider or not provider.enabled:
            raise HTTPException(400, "所选 AI 模型不存在或未启用")
    else:
        provider = db.scalar(select(AIProviderSetting).where(AIProviderSetting.is_default.is_(True), AIProviderSetting.enabled.is_(True)))
    if not provider:
        raise HTTPException(400, "暂无已启用的默认 AI 模型，请联系超级管理员配置")
    credential = db.scalar(select(UserAIProviderCredential).where(
        UserAIProviderCredential.company_id == user.company_id,
        UserAIProviderCredential.user_id == user.id,
        UserAIProviderCredential.provider == provider.provider,
    ))
    if not credential:
        raise HTTPException(400, f"尚未配置个人 {provider.display_name} 平台密钥，请联系公司管理员配置")
    images_per_task = max(1, provider.images_per_task or 1)
    chunks = [print_urls[start:start + images_per_task] for start in range(0, len(print_urls), images_per_task)]
    common_parameters = payload.model_dump(exclude={"print_urls", "print_url", "white_image_id"}) | {
        "white_image_id": white_image.id,
        "white_image_name": white_image.name,
        "white_image_url": white_image.image_url,
    }
    tasks = [
        PodTask(
            company_id=user.company_id,
            template_id=template.id,
            created_by=user.id,
            status=TaskStatus.QUEUED,
            parameters=common_parameters | {"print_urls": chunk, "print_url": chunk[0]},
            result_urls=[],
            result_map=[],
            provider=provider.provider,
            provider_model=provider.model,
        )
        for chunk in chunks
    ]
    db.add_all(tasks); db.commit()
    for task in tasks:
        db.refresh(task)
    return {"items": [serialize_record(task) for task in tasks], "total": len(tasks)}


@app.get("/ai-providers")
def list_available_ai_providers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """运营端查看可用模型及个人密钥配置状态，不暴露任何凭据内容。"""
    configured_providers = set(db.scalars(select(UserAIProviderCredential.provider).where(
        UserAIProviderCredential.company_id == user.company_id,
        UserAIProviderCredential.user_id == user.id,
    )).all())
    return [
        {
            "provider": setting.provider,
            "display_name": setting.display_name,
            "model": setting.model,
            "is_default": setting.is_default,
            "images_per_task": setting.images_per_task,
            "credential_configured": setting.provider in configured_providers,
        }
        for setting in db.scalars(select(AIProviderSetting).where(AIProviderSetting.enabled.is_(True)).order_by(AIProviderSetting.provider)).all()
    ]


@app.post("/tasks/{task_id}/retry")
def retry_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """将一条失败任务完整重置为待提交状态。"""
    task = db.get(PodTask, task_id)
    if not can_access_task(task, user):
        raise HTTPException(404, "任务不存在")
    if task.status != TaskStatus.FAILED:
        raise HTTPException(400, "只有失败任务可以重试")
    task.status = TaskStatus.QUEUED
    task.provider_task_id = None
    task.failure_reason = None
    task.result_urls = []
    task.result_map = []
    task.selected_result_url = None
    task.submit_attempts = 0
    task.submitted_at = None
    task.completed_at = None
    db.commit(); db.refresh(task)
    return serialize_record(task)


@app.post("/tasks/{task_id}/claim-materials")
def claim_task_materials(task_id: int, payload: ClaimMaterials, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.get(PodTask, task_id)
    if not can_access_task(task, user):
        raise HTTPException(404, "任务不存在")
    if task.status not in (TaskStatus.AWAITING_SELECTION, TaskStatus.COMPLETED) or not task.result_urls:
        raise HTTPException(400, "任务尚未生成可领取的图片")
    selected_urls = list(dict.fromkeys(payload.result_urls))
    if any(url not in task.result_urls for url in selected_urls):
        raise HTTPException(400, "包含不属于该任务的图片")
    template = db.get(ProductTemplate, task.template_id)
    owner = db.get(User, task.created_by)
    if not template or not owner:
        raise HTTPException(400, "任务缺少产品模板或创作人信息")
    validate_material_sku_source(template, owner)
    existing_urls = set(db.scalars(select(MaterialAsset.url).where(MaterialAsset.company_id == task.company_id, MaterialAsset.source_task_id == task.id)).all())
    claimed_count = 0
    for index, url in enumerate(selected_urls, start=1):
        if url not in existing_urls:
            add_material_asset_with_sku(
                db, template=template, owner=owner, company_id=task.company_id,
                source_task_id=task.id, url=url, name=f"AI 创作 #{task.id} · 结果 {index}",
            )
            claimed_count += 1
    # 首次领取同时完成任务，并保留第一张领取图作为任务的已选结果。
    if task.status == TaskStatus.AWAITING_SELECTION:
        task.selected_result_url = selected_urls[0]
        task.status = TaskStatus.COMPLETED
    db.commit()
    return {"claimed": claimed_count, "message": "已领取到素材库"}


@app.post("/drafts/from-material-assets")
def create_draft_from_material_assets(payload: MaterialDraftCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """用素材库中选定的一张或多张图片创建商品草稿。"""
    asset_ids = list(dict.fromkeys(payload.material_asset_ids))
    assets = db.scalars(select(MaterialAsset).where(
        MaterialAsset.company_id == user.company_id,
        MaterialAsset.id.in_(asset_ids),
        *([MaterialAsset.claimed_by == user.id] if user.role == Role.MEMBER else []),
    )).all()
    if len(assets) != len(asset_ids):
        raise HTTPException(400, "包含不存在或无权使用的素材")
    assets_by_id = {asset.id: asset for asset in assets}
    assets = [assets_by_id[asset_id] for asset_id in asset_ids]
    if any(not asset.sku for asset in assets):
        raise HTTPException(400, "包含无 SKU 的历史素材，请重新上传或领取后再创建商品草稿")
    template = get_company_template(db, user, payload.template_id)
    if any(asset.template_id != template.id for asset in assets):
        raise HTTPException(400, "创建商品草稿时只能使用属于所选产品模板的素材")
    source_task_ids = {asset.source_task_id for asset in assets}
    source_task_id = source_task_ids.pop() if len(source_task_ids) == 1 else None
    image_urls = [asset.url for asset in assets]
    sku_items = [{"image_url": asset.url, "size": None, "sku": asset.sku} for asset in assets]
    draft = ProductDraft(
        company_id=user.company_id,
        shop_id=None,
        template_id=template.id,
        source_task_id=source_task_id,
        title=payload.title,
        product_description=payload.product_description.strip() if payload.product_description else None,
        size_chart_url=template.size_chart_url,
        image_urls=image_urls,
        sku_items=sku_items,
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
    asset_filters = [MaterialAsset.company_id == user.company_id, MaterialAsset.url == payload.image_url]
    if user.role == Role.MEMBER:
        asset_filters.append(MaterialAsset.claimed_by == user.id)
    asset = db.scalar(select(MaterialAsset).where(*asset_filters))
    if not asset:
        raise HTTPException(400, "请使用当前公司素材库中的首图生成标题")
    try:
        return {"title": await generate_draft_title(template.title_template, payload.image_url)}
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.put("/drafts/{draft_id}")
def update_draft(draft_id: int, payload: DraftUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    draft = db.get(ProductDraft, draft_id)
    if not can_access_draft(draft, user) or (draft.shop_id is not None and draft.shop_id not in allowed_shop_ids(db, user)):
        raise HTTPException(404, "商品草稿不存在")
    draft.title = payload.title
    draft.product_description = payload.product_description.strip() if payload.product_description else None
    draft.updated_by = user.id
    db.commit(); db.refresh(draft)
    return serialize_record(draft)


def visible_tiktok_catalog(db: Session, user: User, catalog_id: int | None = None) -> TiktokCategoryCatalog | None:
    if catalog_id is None:
        return None
    return db.scalar(select(TiktokCategoryCatalog).where(
        TiktokCategoryCatalog.id == catalog_id, TiktokCategoryCatalog.company_id == user.company_id,
    ))


def serialize_tiktok_catalog(catalog: TiktokCategoryCatalog, *, include_options: bool = False) -> dict:
    result = {
        "id": catalog.id, "name": catalog.name, "source_filename": catalog.source_filename,
        "template_version": catalog.template_version, "category_count": len((catalog.parsed_options or {}).get("categories", [])),
        "created_at": timestamp_ms(catalog.created_at), "updated_at": timestamp_ms(catalog.updated_at),
    }
    if include_options:
        result["options"] = catalog.parsed_options
    return result


@app.get("/tiktok-category-catalogs")
def list_tiktok_category_catalogs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    catalogs = db.scalars(select(TiktokCategoryCatalog).where(
        TiktokCategoryCatalog.company_id == user.company_id,
    ).order_by(TiktokCategoryCatalog.id.desc())).all()
    return [serialize_tiktok_catalog(item) for item in catalogs]


@app.post("/tiktok-category-catalogs")
async def create_tiktok_category_catalog(
    name: str = Form(..., min_length=1, max_length=120),
    file: UploadFile = File(...),
    user: User = Depends(require_roles(Role.COMPANY_ADMIN)),
    db: Session = Depends(get_db),
):
    catalog_name = name.strip()
    if not catalog_name:
        raise HTTPException(400, "类目库名称不能为空")
    source_filename = Path(file.filename or "").name
    if not source_filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式的 TikTok 模板")
    template_bytes = await file.read(10 * 1024 * 1024 + 1)
    if not template_bytes or len(template_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "TikTok 模板大小须在 10MB 以内")
    try:
        with zipfile.ZipFile(BytesIO(template_bytes)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError("解压后内容过大")
        options = parse_listing_options(template_bytes)
    except (ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(400, f"TikTok 模板解析失败：{exc}") from exc
    if not options.get("categories"):
        raise HTTPException(400, "TikTok 模板中没有可用类目")
    catalog = TiktokCategoryCatalog(
        company_id=user.company_id, name=catalog_name, source_filename=source_filename,
        template_version=options.get("template_version"), template_blob=template_bytes,
        parsed_options=options, created_by=user.id,
    )
    db.add(catalog)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, "本公司已存在同名 TK 类目库") from exc
    db.refresh(catalog)
    return serialize_tiktok_catalog(catalog, include_options=True)


@app.patch("/tiktok-category-catalogs/{catalog_id}")
def update_tiktok_category_catalog(
    catalog_id: int, payload: TiktokCategoryCatalogUpdate,
    user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db),
):
    catalog = db.get(TiktokCategoryCatalog, catalog_id)
    if not catalog or catalog.company_id != user.company_id:
        raise HTTPException(404, "TK 类目库不存在")
    if payload.name is not None:
        catalog.name = payload.name
    options = json.loads(json.dumps(catalog.parsed_options or {}))
    for change in payload.attribute_input_modes:
        fields = options.get("attributes_by_category", {}).get(change.category)
        if fields is None:
            raise HTTPException(400, f"类目不存在：{change.category}")
        field = next((item for item in fields if item.get("field") == change.field), None)
        if not field:
            raise HTTPException(400, f"属性不存在：{change.field}")
        if change.input_mode in {"select", "select_or_text"} and not field.get("options"):
            raise HTTPException(400, f"{field.get('label') or change.field} 没有候选属性值，只能设为手动填写")
        field["input_mode"] = change.input_mode
    catalog.parsed_options = options
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, "本公司已存在同名 TK 类目库") from exc
    db.refresh(catalog)
    return serialize_tiktok_catalog(catalog, include_options=True)


@app.delete("/tiktok-category-catalogs/{catalog_id}", status_code=204)
def delete_tiktok_category_catalog(
    catalog_id: int, user: User = Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db),
):
    catalog = db.get(TiktokCategoryCatalog, catalog_id)
    if not catalog or catalog.company_id != user.company_id:
        raise HTTPException(404, "TK 类目库不存在")
    db.delete(catalog)
    db.commit()


@app.get("/tiktok-export/options")
def get_tiktok_export_options(
    category_catalog_id: int = Query(ge=1),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """返回指定具名类目库中实际可用的类目、属性和输入范围。"""
    catalog = visible_tiktok_catalog(db, user, category_catalog_id)
    if not catalog:
        raise HTTPException(404, "TK 类目库不存在")
    return {**catalog.parsed_options, "category_catalog": serialize_tiktok_catalog(catalog)}


@app.post("/drafts/export-tiktok")
def export_drafts_to_tiktok(payload: TiktokDraftExportInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """将同一产品模板下的商品草稿导出为 TikTok Seller Center 批量上传表格。"""
    if len(set(payload.draft_ids)) != len(payload.draft_ids):
        raise HTTPException(400, "商品草稿不能重复选择")
    if len({item.draft_id for item in payload.product_overrides}) != len(payload.product_overrides):
        raise HTTPException(400, "同一商品草稿只能设置一组售价和库存覆盖值")

    drafts = db.scalars(select(ProductDraft).where(ProductDraft.id.in_(payload.draft_ids))).all()
    drafts_by_id = {draft.id: draft for draft in drafts}
    if len(drafts_by_id) != len(payload.draft_ids) or any(not can_access_draft(drafts_by_id.get(draft_id), user) for draft_id in payload.draft_ids):
        raise HTTPException(404, "包含不存在或无权导出的商品草稿")
    drafts = [drafts_by_id[draft_id] for draft_id in payload.draft_ids]

    template_ids = {draft.template_id for draft in drafts}
    if None in template_ids or len(template_ids) != 1:
        raise HTTPException(400, "一次只能导出属于同一产品模板的商品草稿")
    template = db.get(ProductTemplate, next(iter(template_ids)))
    if not template:
        raise HTTPException(400, "商品草稿关联的产品模板不存在")
    missing_logistics = [
        label for label, value in (
            ("包裹重量", template.package_weight), ("包裹长度", template.package_length),
            ("包裹宽度", template.package_width), ("包裹高度", template.package_height),
        ) if value is None or float(value) <= 0
    ]
    if missing_logistics:
        raise HTTPException(400, f"产品模板缺少有效物流信息：{', '.join(missing_logistics)}")

    catalog = visible_tiktok_catalog(db, user, payload.category_catalog_id)
    if not catalog:
        raise HTTPException(404, "TK 类目库不存在或无权使用")
    try:
        attributes = validate_attributes(payload.category, payload.attributes, catalog.parsed_options)
        base_requirements = category_base_requirements(payload.category, catalog.parsed_options)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    overrides = {item.draft_id: item for item in payload.product_overrides}
    unknown_override_ids = sorted(set(overrides) - set(payload.draft_ids))
    if unknown_override_ids:
        raise HTTPException(400, "售价或库存覆盖项包含未选择的商品草稿")

    products = []
    for draft in drafts:
        title = (draft.title or "").strip()
        if not 25 <= len(title) <= 255:
            raise HTTPException(400, f"商品草稿 #{draft.id} 的标题长度须为 25-255 个字符")
        description = (draft.product_description or template.product_description or "").strip()
        if not description:
            raise HTTPException(400, f"商品草稿 #{draft.id} 缺少产品描述")
        image_urls = list(dict.fromkeys(str(url).strip() for url in (draft.image_urls or []) if str(url).strip()))
        if not image_urls:
            raise HTTPException(400, f"商品草稿 #{draft.id} 没有商品图片")
        if any(not url.lower().startswith(("http://", "https://")) for url in image_urls):
            raise HTTPException(400, f"商品草稿 #{draft.id} 包含非公网 HTTP(S) 图片地址")
        base_sku_by_image = {}
        for item in draft.sku_items or []:
            image_url = str(item.get("image_url") or "").strip()
            sku = str(item.get("sku") or "").strip()
            if image_url and sku:
                base_sku_by_image.setdefault(image_url, sku)
        missing_sku_images = [url for url in image_urls if not base_sku_by_image.get(url)]
        if missing_sku_images:
            raise HTTPException(400, f"商品草稿 #{draft.id} 的图片缺少基础 SKU")
        size_chart_url = (draft.size_chart_url or template.size_chart_url or "").strip()
        if base_requirements.get("size_chart") == "Mandatory" and not size_chart_url:
            raise HTTPException(400, f"商品草稿 #{draft.id} 在所选类目下必须提供尺码图")
        if size_chart_url and not size_chart_url.lower().startswith(("http://", "https://")):
            raise HTTPException(400, f"商品草稿 #{draft.id} 的尺码图必须是公网 HTTP(S) 地址")
        override = overrides.get(draft.id)
        products.append({
            "title": title,
            "description": description,
            "image_urls": image_urls,
            "base_sku_by_image": base_sku_by_image,
            "size_chart_url": size_chart_url or None,
            "price": override.price if override and override.price is not None else payload.default_price,
            "quantity": override.quantity if override and override.quantity is not None else payload.default_quantity,
        })

    try:
        workbook_bytes = build_tiktok_workbook(
            template=template, category=payload.category, cod=payload.cod,
            attributes=attributes, products=products, template_bytes=catalog.template_blob,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    db.execute(
        update(ProductDraft)
        .where(ProductDraft.id.in_(payload.draft_ids))
        .values(export_count=ProductDraft.export_count + 1)
    )
    db.commit()
    filename = f"TikTok批量上传_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.post("/drafts/{draft_id}/publish-to-miaoshou")
async def publish_draft_to_miaoshou(draft_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """将商品草稿创建到妙手公共采集箱，避免重复创建。"""
    draft = db.get(ProductDraft, draft_id)
    if not can_access_draft(draft, user) or (draft.shop_id is not None and draft.shop_id not in allowed_shop_ids(db, user)):
        raise HTTPException(404, "商品草稿不存在")
    if draft.miaoshou_collect_box_id:
        return {"draft_id": draft.id, "common_collect_box_detail_id": draft.miaoshou_collect_box_id, "already_published": True}
    company = db.get(Company, draft.company_id)
    if not company or not company.miaoshou_app_id or not company.miaoshou_secret_encrypted:
        raise HTTPException(400, "尚未配置妙手 API Key，请联系公司管理员在店铺管理中配置")
    template = db.get(ProductTemplate, draft.template_id) if draft.template_id else None
    if not template:
        raise HTTPException(400, "该商品草稿缺少产品模板信息，无法生成公共采集箱商品")

    await create_common_collect_box_detail(draft, company, template)
    draft.status = "published_to_miaoshou"
    draft.updated_by = user.id
    db.commit()
    return {"draft_id": draft.id, "common_collect_box_detail_id": draft.miaoshou_collect_box_id, "already_published": False}


@app.post("/drafts/{draft_id}/claim-to-tiktok")
async def claim_draft_to_tiktok(draft_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """商品先进入公共草稿箱，再认领到 TikTok 采集箱；任一步失败均可安全重试。"""
    draft = db.get(ProductDraft, draft_id)
    if not can_access_draft(draft, user) or (draft.shop_id is not None and draft.shop_id not in allowed_shop_ids(db, user)):
        raise HTTPException(404, "商品草稿不存在")
    if draft.tiktok_collect_box_id:
        return {"draft_id": draft.id, "common_collect_box_detail_id": draft.miaoshou_collect_box_id, "tiktok_collect_box_detail_id": draft.tiktok_collect_box_id, "already_claimed": True}
    company = db.get(Company, draft.company_id)
    if not company or not company.miaoshou_app_id or not company.miaoshou_secret_encrypted:
        raise HTTPException(400, "尚未配置妙手 API Key，请联系公司管理员在店铺管理中配置")
    template = db.get(ProductTemplate, draft.template_id) if draft.template_id else None
    if not template:
        raise HTTPException(400, "该商品草稿缺少产品模板信息，无法生成公共采集箱商品")
    await create_common_collect_box_detail(draft, company, template)
    # 公共草稿箱创建成功后立即持久化编号。后续 TikTok 认领失败时，
    # 重试只会继续认领，不会在妙手重复创建商品。
    draft.status = "published_to_miaoshou"
    draft.updated_by = user.id
    db.commit()
    await claim_common_collect_box_to_tiktok(draft, company)
    draft.status = "claimed_to_tiktok"
    draft.updated_by = user.id
    db.commit()
    return {"draft_id": draft.id, "common_collect_box_detail_id": draft.miaoshou_collect_box_id, "tiktok_collect_box_detail_id": draft.tiktok_collect_box_id, "already_claimed": False}


@app.get("/drafts")
def list_drafts(
    shop_id: int | None = None,
    creator_id: int | None = Query(default=None, ge=1),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(ProductDraft).where(
        ProductDraft.company_id == user.company_id,
        or_(ProductDraft.shop_id.is_(None), ProductDraft.shop_id.in_(allowed_shop_ids(db, user))),
    )
    if user.role == Role.MEMBER:
        stmt = stmt.where(ProductDraft.created_by == user.id)
    elif creator_id is not None:
        stmt = stmt.where(ProductDraft.created_by == creator_id)
    if shop_id:
        ensure_shop(db, user, shop_id); stmt = stmt.where(ProductDraft.shop_id == shop_id)
    drafts = db.scalars(stmt.order_by(ProductDraft.id.desc())).all()
    user_ids = {
        user_id
        for draft in drafts
        for user_id in (draft.created_by, draft.updated_by)
        if user_id is not None
    }
    user_names = {
        record.id: record.name
        for record in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    return [
        serialize_record(draft) | {
            "created_by_name": user_names.get(draft.created_by, "历史记录缺失"),
            "updated_by_name": user_names.get(draft.updated_by, "历史记录缺失"),
        }
        for draft in drafts
    ]
