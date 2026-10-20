import enum
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Role(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    MEMBER = "member"
    TEAM_LEADER = "team_leader"
    SUPPLY_USER = "supply_user"


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
    cross_company_collect_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    miaoshou_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    miaoshou_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    hubstudio_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hubstudio_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    hubstudio_group_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supply_ai_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    supply_ai_model: Mapped[str | None] = mapped_column(String(120), default="deepseek-chat", server_default="deepseek-chat", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OperatorGroup(Base):
    __tablename__ = "operator_groups"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_operator_groups_company_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(80))
    leader_user_id: Mapped[int] = mapped_column(Integer)
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
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    supply_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    supply_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    supply_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime().with_variant(MYSQL_DATETIME(fsp=6), "mysql"), nullable=False, index=True)


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        # 妙手跨境店以 company_id + external_shop_id + shop_type 作为外部身份。
        # 本土店没有 external_shop_id；MySQL/MariaDB 允许该唯一键中的多个 NULL。
        UniqueConstraint(
            "company_id", "external_shop_id", "shop_type",
            name="uq_shops_company_external_shop_type",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(20), default="MY")
    external_shop_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    auth_status: Mapped[str] = mapped_column(String(30), default="not_connected")
    auth_expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 妙手店铺使用此表；旧手工本土店仅为保留历史记录。HubStudio 使用独立环境表。
    shop_type: Mapped[str] = mapped_column(String(20), default="cross_border", index=True)
    hubstudio_container_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hub_agent_id: Mapped[int | None] = mapped_column(nullable=True, index=True)


class HubAgent(Base):
    """安装在员工电脑上的 HubStudio 本地执行器。"""
    __tablename__ = "hub_agents"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_hub_agents_company_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HubAgentPairing(Base):
    """一次性终端配对码；原始终端令牌仅在本地 Agent 首次领取时返回。"""
    __tablename__ = "hub_agent_pairings"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(20))
    agent_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HubEnvironment(Base):
    """旧版同步环境的历史表；新版不再写入，与妙手店铺无关。"""
    __tablename__ = "hub_environments"
    __table_args__ = (UniqueConstraint("company_id", "container_code", name="uq_hub_environment_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    container_code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    metadata_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    auto_upload_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HubEnvironmentAccess(Base):
    __tablename__ = "hub_environment_access"
    __table_args__ = (UniqueConstraint("agent_id", "environment_id", name="uq_hub_environment_access"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    agent_id: Mapped[int] = mapped_column(index=True)
    environment_id: Mapped[int] = mapped_column(index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime)


class HubEnvironmentLock(Base):
    __tablename__ = "hub_environment_locks"
    environment_id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class HubUploadAttempt(Base):
    __tablename__ = "hub_upload_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(index=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    environment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="running")
    logs: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HubUploadTask(Base):
    """账号拥有的固定 XLSX 上品任务，电脑在领取时确定。"""
    __tablename__ = "hub_upload_tasks"
    __table_args__ = (
        Index("ix_hub_upload_tasks_agent_status", "agent_id", "status", "created_at"),
        Index("ix_hub_upload_tasks_shop_status", "shop_id", "status"),
        Index("ix_hub_upload_tasks_owner_queue", "company_id", "created_by", "status", "environment_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    shop_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    agent_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(index=True)
    environment_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    environment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    template_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    template_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    draft_ids: Mapped[list] = mapped_column(JSON, default=list)
    export_filename: Mapped[str] = mapped_column(String(255))
    export_blob: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb"), nullable=True)
    export_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    export_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    export_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    export_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    export_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logs: Mapped[list] = mapped_column(JSON, default=list)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HubRuntimeLock(Base):
    """只保存任务运行协调键，不保存同步环境目录或访问关系。"""
    __tablename__ = "hub_runtime_locks"
    __table_args__ = (UniqueConstraint("company_id", "container_code", name="uq_hub_runtime_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    container_code: Mapped[str] = mapped_column(String(120))
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class UserShop(Base):
    __tablename__ = "user_shops"
    __table_args__ = (UniqueConstraint("user_id", "shop_id", name="uq_user_shop"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    shop_id: Mapped[int] = mapped_column(index=True)


class TiktokCategoryCatalog(Base):
    """兼容历史表名的平台类目库，保存原始批量上传模板及解析结果。"""
    __tablename__ = "tiktok_category_catalogs"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_tiktok_category_catalog_company_name"),
        Index("ix_tiktok_category_catalog_company", "company_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    source_filename: Mapped[str] = mapped_column(String(255))
    # tiktok_local / tiktok_cross_border / shopee_basic；用于选择平台解析与导出适配器。
    template_type: Mapped[str] = mapped_column(String(32), default="tiktok_local", nullable=False, index=True)
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
    supply_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    supply_fallback_title: Mapped[str | None] = mapped_column(String(220), nullable=True)


class UserTemplateWhiteImage(Base):
    """员工针对产品模板保存的白底图。"""
    __tablename__ = "user_template_white_images"
    __table_args__ = (
        UniqueConstraint("user_id", "template_id", "name", name="uq_user_template_white_image_name"),
        Index("ix_user_template_white_images_owner_template", "user_id", "template_id"),
        Index("ix_user_template_white_images_company_deleted", "company_id", "deleted_at"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(80))
    image_url: Mapped[str] = mapped_column(String(500))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    __table_args__ = (
        Index("ix_pod_tasks_provider_model", "provider", "provider_model"),
        # Worker 按状态取队列快照，并按创建顺序稳定处理。
        Index("ix_pod_tasks_status_created_at_id", "status", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column()
    # 商品草稿图片任务的可索引归属；普通 SKU 图任务保持为空。
    draft_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
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
    # 已明确忽略的失败不再阻塞商品草稿的制作流程。
    failure_ignored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result_map: Mapped[list] = mapped_column(JSON, default=list)
    submit_attempts: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MaterialStyle(Base):
    """由白底图产生的永久风格；来源删除后仍保留，不设置级联外键。"""
    __tablename__ = "material_styles"
    __table_args__ = (
        UniqueConstraint("source_white_image_id", name="uq_material_styles_white_image"),
        Index("ix_material_styles_company_template", "company_id", "template_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column()
    template_id: Mapped[int] = mapped_column()
    source_white_image_id: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(String(80))
    created_by: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaterialAsset(Base):
    """公司级素材库中的 AI 领取、本地上传或链接导入图片。"""
    __tablename__ = "material_assets"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_material_assets_sku"),
        UniqueConstraint("company_id", "creation_request_key", name="uq_material_creation_request"),
        Index("ix_material_assets_company_created_id", "company_id", "created_at", "id"),
        Index("ix_material_assets_company_creator_created_id", "company_id", "claimed_by", "created_at", "id"),
        Index("ix_material_assets_supply_listing", "company_id", "supply_listed", "supply_listed_at"),
        Index("ix_material_assets_company_template_style", "company_id", "template_id", "style_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    image_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    creation_request_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_task_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    template_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    style_id: Mapped[int | None] = mapped_column(nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(180))
    sku: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # 仅记录是否曾被成功用于创建草稿；已使用素材仍可用于单条草稿复用。
    usage_status: Mapped[str] = mapped_column(String(12), default="unused", nullable=False, index=True)
    is_infringing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    supply_listed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    # 首次上架后保留时间，避免将从未上架的素材视为已下架。
    supply_listed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_by: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplyAgent(Base):
    """公司维护的代理归属记录；代理没有登录权限。"""
    __tablename__ = "supply_agents"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_supply_agents_company_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplyStrategy(Base):
    __tablename__ = "supply_strategies"
    __table_args__ = (Index("ix_supply_strategies_owner", "company_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplyJob(Base):
    """快照与恢复检查点均持久化；租约版本阻止旧执行者覆盖结果。"""
    __tablename__ = "supply_jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", "idempotency_key", name="uq_supply_jobs_owner_request"),
        Index("ix_supply_jobs_queue", "state", "available_at", "lease_expires_at", "created_at"),
        Index("ix_supply_jobs_company_state", "company_id", "state"),
        Index("ix_supply_jobs_owner_state", "company_id", "user_id", "state"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    template_id: Mapped[int] = mapped_column(index=True)
    category_catalog_id: Mapped[int] = mapped_column(index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    category_blob: Mapped[bytes] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb"))
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    export_blob: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb"), nullable=True)
    state: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="queued", server_default="queued")
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_epoch: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    upload_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    output_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImageFile(Base):
    """只登记已校验并保存的图片；不存储检查或入库状态。"""
    __tablename__ = "image_files"
    __table_args__ = (UniqueConstraint("company_id", "sha256", name="uq_image_file_content"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImageAddress(Base):
    """来源地址和历史地址映射，按公司隔离。"""
    __tablename__ = "image_addresses"
    __table_args__ = (UniqueConstraint("company_id", "url_hash", name="uq_image_address_url"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    url_hash: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    image_file_id: Mapped[int] = mapped_column(Integer, index=True)


class SupplyJobMaterial(Base):
    __tablename__ = "supply_job_materials"
    __table_args__ = (
        UniqueConstraint("job_id", "material_id", "version_hash", "link_index", name="uq_supply_job_material_version_link"),
        Index("ix_supply_job_materials_usage", "company_id", "material_id", "successful"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    job_id: Mapped[int] = mapped_column(index=True)
    material_id: Mapped[int] = mapped_column(index=True)
    version_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30), default="snapshot", server_default="snapshot")
    # -1 为候选关联，0 起为实际商品组；避免 MySQL 的 NULL 唯一键漏洞。
    link_index: Mapped[int] = mapped_column(Integer, default=-1, server_default="-1")
    successful: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class SupplyAudit(Base):
    __tablename__ = "supply_audits"
    __table_args__ = (Index("ix_supply_audits_company_created", "company_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CrossCompanyCollectionBatch(Base):
    __tablename__ = "cross_company_collection_batches"
    __table_args__ = (UniqueConstraint("company_id", "request_key", name="uq_collection_company_request"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    created_by: Mapped[int] = mapped_column()
    template_id: Mapped[int] = mapped_column()
    request_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CrossCompanyCollectionItem(Base):
    __tablename__ = "cross_company_collection_items"
    __table_args__ = (Index("ix_collection_items_company_source_sku",
        "company_id", "source_company_id", "source_sku"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(index=True)
    company_id: Mapped[int] = mapped_column(index=True)
    material_asset_id: Mapped[int] = mapped_column(index=True)
    source_company_id: Mapped[int] = mapped_column()
    source_company_name: Mapped[str] = mapped_column(String(120))
    source_library: Mapped[str] = mapped_column(String(12))
    source_record_id: Mapped[int] = mapped_column()
    source_sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500))
    source_name: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CrossCompanyCollectionPermissionLog(Base):
    __tablename__ = "cross_company_collection_permission_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    changed_by: Mapped[int] = mapped_column()
    previous_enabled: Mapped[bool] = mapped_column(Boolean)
    enabled: Mapped[bool] = mapped_column(Boolean)
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
    # 商品图片制作的当前工作阶段；新草稿先进入待处理池，由用户分发后再开始制作。
    workflow_stage: Mapped[str] = mapped_column(String(30), default="pending", index=True)
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


class ProductLibrarySource(Base):
    __tablename__ = "product_library_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "platform", "site", "shop_name", name="uq_product_library_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    platform: Mapped[str] = mapped_column(String(80))
    site: Mapped[str] = mapped_column(String(80))
    shop_name: Mapped[str] = mapped_column(String(160))
    assigned_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class ProductLibraryProduct(Base):
    __tablename__ = "product_library_products"
    __table_args__ = (
        UniqueConstraint("source_id", "external_product_id", "sku", name="uq_product_library_product"),
        Index("ix_product_library_products_company_sku", "company_id", "sku"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    external_product_id: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(120))
    template_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductLibraryOrder(Base):
    __tablename__ = "product_library_orders"
    __table_args__ = (
        UniqueConstraint("source_id", "order_number", name="uq_product_library_order"),
        Index("ix_product_library_orders_company_ordered_at", "company_id", "ordered_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    order_number: Mapped[str] = mapped_column(String(120))
    # 无时区的 Excel 时间按 UTC+8 解析，此处存 UTC naive datetime。
    ordered_at: Mapped[datetime] = mapped_column(DateTime)


class ProductLibraryOrderProduct(Base):
    __tablename__ = "product_library_order_products"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_product_library_order_product"),
        Index("ix_product_library_order_products_product", "product_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(index=True)
    product_id: Mapped[int] = mapped_column()
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ProductLibraryOrderSkuQuantity(Base):
    """完整平台 SKU 数量；重复导入覆盖对应尺码。"""
    __tablename__ = "product_library_order_sku_quantities"
    __table_args__ = (UniqueConstraint("order_product_id", "platform_sku", name="uq_product_library_order_sku_quantity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_product_id: Mapped[int] = mapped_column(index=True)
    platform_sku: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class ProductLibrarySnapshotOrderProduct(Base):
    """冻结统计时的订单商品数量，支持店铺筛选后按 SKU 去重。"""
    __tablename__ = "product_library_snapshot_order_products"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "order_id", "product_id", name="uq_product_library_snapshot_order_product"),
        Index("ix_product_library_snapshot_order_product", "snapshot_id", "product_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(index=True)
    order_id: Mapped[int] = mapped_column()
    product_id: Mapped[int] = mapped_column()
    order_number: Mapped[str] = mapped_column(String(120))
    ordered_at: Mapped[datetime] = mapped_column(DateTime)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class ProductLibraryDailySnapshot(Base):
    __tablename__ = "product_library_daily_snapshots"
    __table_args__ = (UniqueConstraint("company_id", "snapshot_date", name="uq_product_library_snapshot_company_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductLibraryDailySnapshotItem(Base):
    """旧版产品级汇总表，仅保留升级及清理兼容；新快照使用订单商品明细。"""
    __tablename__ = "product_library_daily_snapshot_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "product_id", name="uq_product_library_snapshot_product"),
        Index("ix_product_library_snapshot_items_tier", "snapshot_id", "tier"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(index=True)
    product_id: Mapped[int] = mapped_column(index=True)
    count_7: Mapped[int] = mapped_column(Integer)
    count_15: Mapped[int] = mapped_column(Integer)
    count_30: Mapped[int] = mapped_column(Integer)
    rank_7: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_15: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ProductLibraryRankingTask(Base):
    """每家公司最近一次产品库统计任务。"""
    __tablename__ = "product_library_ranking_tasks"
    __table_args__ = (UniqueConstraint("task_id", name="uq_product_library_ranking_task_id"),)
    company_id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AIProviderSetting(Base):
    __tablename__ = "ai_provider_settings"
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    # 模型配置可共享同一平台凭据，例如多个 Grsai 模型共用一份 API Key。
    credential_provider: Mapped[str] = mapped_column(String(40), default="grsai")
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
    submit_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)
    result_interval_ms: Mapped[int] = mapped_column(Integer, default=5000)
