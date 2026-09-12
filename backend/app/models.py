import enum
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, Float, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Role(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    MEMBER = "member"


class TaskStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_SELECTION = "awaiting_selection"
    COMPLETED = "completed"
    FAILED = "failed"


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    miaoshou_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    miaoshou_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("company_id", "user_code", name="uq_users_company_user_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    user_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(20), default="MY")
    external_shop_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    auth_status: Mapped[str] = mapped_column(String(30), default="not_connected")
    auth_expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class UserShop(Base):
    __tablename__ = "user_shops"
    __table_args__ = (UniqueConstraint("user_id", "shop_id", name="uq_user_shop"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    shop_id: Mapped[int] = mapped_column(index=True)


class TiktokCategoryCatalog(Base):
    """一套具名 TikTok 店铺类目及其原始批量上传模板。"""
    __tablename__ = "tiktok_category_catalogs"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_tiktok_category_catalog_company_name"),
        Index("ix_tiktok_category_catalog_company", "company_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    source_filename: Mapped[str] = mapped_column(String(255))
    template_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    template_blob: Mapped[bytes] = mapped_column(
        LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb")
    )
    parsed_options: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TemplateGroup(Base):
    __tablename__ = "template_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductTemplate(Base):
    __tablename__ = "product_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    group_id: Mapped[int | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_template: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_chart_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    package_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    sku_specifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 印花贴合场景可复用的命名 AI 提示词。
    ai_prompts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="published")
    color_count: Mapped[int] = mapped_column(Integer, default=1)
    sku_count: Mapped[int] = mapped_column(Integer, default=1)


class UserTemplateWhiteImage(Base):
    """员工针对产品模板保存的白底图。"""
    __tablename__ = "user_template_white_images"
    __table_args__ = (
        UniqueConstraint("user_id", "template_id", "name", name="uq_user_template_white_image_name"),
        Index("ix_user_template_white_images_owner_template", "user_id", "template_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(80))
    image_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserTemplatePrompt(Base):
    """员工针对产品模板保存的印花贴合创作要求。"""
    __tablename__ = "user_template_prompts"
    __table_args__ = (
        UniqueConstraint("user_id", "template_id", "name", name="uq_user_template_prompt_name"),
        Index("ix_user_template_prompts_owner_template", "user_id", "template_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PodTask(Base):
    __tablename__ = "pod_tasks"
    __table_args__ = (Index("ix_pod_tasks_provider_model", "provider", "provider_model"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column()
    created_by: Mapped[int] = mapped_column()
    # 稳定的内部任务类型：sku_image、carousel、main_image。
    task_type: Mapped[str] = mapped_column(String(30), default="sku_image", index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.QUEUED)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result_urls: Mapped[dict] = mapped_column(JSON, default=list)
    selected_result_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 外部异步 AI 任务的标识，例如 Grsai 返回的 id。
    provider_task_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_map: Mapped[list] = mapped_column(JSON, default=list)
    submit_attempts: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MaterialAsset(Base):
    """公司级素材库中的 AI 领取或本地上传图片。"""
    __tablename__ = "material_assets"
    __table_args__ = (UniqueConstraint("sku", name="uq_material_assets_sku"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    source_task_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    template_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(180))
    sku: Mapped[str | None] = mapped_column(String(24), nullable=True)
    claimed_by: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductDraft(Base):
    __tablename__ = "product_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    # 素材库创建的草稿会直接进入公共采集箱，不需要绑定投放店铺。
    shop_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    # 创建公共采集箱产品需要使用模板中的包装与规格信息。
    template_id: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_chart_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_publish")
    image_urls: Mapped[dict] = mapped_column(JSON, default=list)
    # 最终商品图片的完整有序列表；第 1 张是首图，为空时回退 SKU 图。
    carousel_items: Mapped[list] = mapped_column(JSON, default=list)
    # 每个图片 × 模板尺码对应一条 SKU 明细：{image_url, size, sku}。
    sku_items: Mapped[dict] = mapped_column(JSON, default=list)
    miaoshou_collect_box_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 公共采集箱商品认领至 TikTok 后的采集箱详情 ID，用于幂等重试。
    tiktok_collect_box_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 成功生成并返回 TikTok 批量上传表格的累计次数。
    export_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 审计字段用于在待发布列表中显示草稿的创建与最后修改信息。
    created_by: Mapped[int | None] = mapped_column(nullable=True)
    updated_by: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIProviderSetting(Base):
    __tablename__ = "ai_provider_settings"
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    images_per_task: Mapped[int] = mapped_column(Integer, default=1)


class UserAIProviderCredential(Base):
    """员工自己的模型平台密钥；密文仅由任务 Worker 解密使用。"""
    __tablename__ = "user_ai_provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_ai_provider_credential"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    secret_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskQueueSetting(Base):
    """平台级串行任务节奏配置；固定使用主键 1。"""
    __tablename__ = "task_queue_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    submit_interval_seconds: Mapped[int] = mapped_column(Integer, default=1)
    result_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
