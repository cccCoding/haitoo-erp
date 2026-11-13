"""矩阵持久化模型：身份、执行权、提交与数据发布分别建模。"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, BigInteger, JSON, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class TenantRow:
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)


class MatrixCompany(Base):
    __tablename__ = "matrix_companies"
    company_id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    listing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class MatrixMemberPermission(Base):
    __tablename__ = "matrix_member_permissions"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    collect_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    listing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    view_scope: Mapped[str] = mapped_column(String(16), default="own")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixDevice(Base):
    __tablename__ = "matrix_devices"
    agent_id: Mapped[int] = mapped_column(primary_key=True)
    install_uuid: Mapped[str] = mapped_column(String(36), unique=True)
    version: Mapped[str] = mapped_column(String(40))
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    hub_identity: Mapped[str] = mapped_column(String(120))
    hub_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    local_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_state: Mapped[dict] = mapped_column(JSON, default=dict)


class MatrixEnvironment(TenantRow, Base):
    __tablename__ = "matrix_environments"
    __table_args__ = (UniqueConstraint("company_id", "hub_identity", "container_code", name="uq_matrix_env_identity"),)
    hub_identity: Mapped[str] = mapped_column(String(120))
    container_code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    group_name: Mapped[str] = mapped_column(String(255), default="")
    serial: Mapped[str] = mapped_column(String(120), default="")
    account_names: Mapped[list] = mapped_column(JSON, default=list)
    observed_site: Mapped[str | None] = mapped_column(String(8), nullable=True)
    override_site: Mapped[str | None] = mapped_column(String(8), nullable=True)
    activity_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    shop_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixAccess(Base):
    __tablename__ = "matrix_access"
    __table_args__ = (UniqueConstraint("agent_id", "environment_id", name="uq_matrix_access"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(index=True)
    environment_id: Mapped[int] = mapped_column(index=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixSync(TenantRow, Base):
    __tablename__ = "matrix_syncs"
    __table_args__ = (UniqueConstraint("agent_id", "snapshot_key", name="uq_matrix_sync"),)
    agent_id: Mapped[int] = mapped_column(index=True)
    snapshot_key: Mapped[str] = mapped_column(String(64))
    hub_identity: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(BigInteger)
    expected_count: Mapped[int] = mapped_column(Integer)
    part_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="staged")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixPart(Base):
    __tablename__ = "matrix_parts"
    __table_args__ = (UniqueConstraint("kind", "parent_id", "number", name="uq_matrix_part"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    parent_id: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    payload: Mapped[list] = mapped_column(JSON)


class MatrixShop(TenantRow, Base):
    __tablename__ = "matrix_shops"
    __table_args__ = (UniqueConstraint("company_id", "site", "external_id", name="uq_matrix_shop"),
        UniqueConstraint("company_id", "environment_id", name="uq_matrix_shop_environment"))
    site: Mapped[str] = mapped_column(String(8))
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    environment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MatrixOperation(TenantRow, Base):
    __tablename__ = "matrix_operations"
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class MatrixPlan(TenantRow, Base):
    __tablename__ = "matrix_plans"
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    agent_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixPlanVersion(Base):
    __tablename__ = "matrix_plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "revision", name="uq_matrix_plan_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class MatrixPreview(TenantRow, Base):
    __tablename__ = "matrix_previews"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class MatrixRun(TenantRow, Base):
    __tablename__ = "matrix_runs"
    __table_args__ = (UniqueConstraint("company_id", "owner_id", "idempotency_key", name="uq_matrix_run_key"),)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    agent_id: Mapped[int] = mapped_column(Integer, index=True)
    plan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    frozen: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MatrixItem(TenantRow, Base):
    __tablename__ = "matrix_items"
    __table_args__ = (UniqueConstraint("run_id", "environment_id", name="uq_matrix_run_env"), Index("ix_matrix_item_queue", "agent_id", "status", "id"))
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    environment_id: Mapped[int] = mapped_column(Integer, index=True)
    agent_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    attempt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supply_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submission: Mapped[str] = mapped_column(String(24), default="not_started")
    collection_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class MatrixAttempt(Base):
    __tablename__ = "matrix_attempts"
    __table_args__ = (UniqueConstraint("item_id", "number", name="uq_matrix_attempt"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(index=True)
    agent_id: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    token_hash: Mapped[str] = mapped_column(String(64))
    fencing: Mapped[int] = mapped_column(Integer)
    lease_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixEvent(Base):
    __tablename__ = "matrix_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_matrix_event_seq"), UniqueConstraint("attempt_id", "source_id", name="uq_matrix_event_source"))
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(index=True)
    attempt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixCommand(TenantRow, Base):
    __tablename__ = "matrix_commands"
    agent_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class MatrixAllocation(TenantRow, Base):
    __tablename__ = "matrix_allocations"
    __table_args__ = (UniqueConstraint("shop_id", "combination_hash", name="uq_matrix_shop_combination"),)
    shop_id: Mapped[int] = mapped_column(Integer)
    combination_hash: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    state: Mapped[str] = mapped_column(String(24), default="reserved")
    payload: Mapped[dict] = mapped_column(JSON)


class MatrixCollection(TenantRow, Base):
    __tablename__ = "matrix_collections"
    __table_args__ = (UniqueConstraint("item_id", "content_hash", name="uq_matrix_collection"),)
    item_id: Mapped[int] = mapped_column(Integer)
    shop_id: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    part_count: Mapped[int] = mapped_column(Integer)
    header: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="staged")
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MatrixFire(Base):
    __tablename__ = "matrix_fires"
    __table_args__ = (UniqueConstraint("plan_id", "revision", "fire_at", name="uq_matrix_fire"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    fire_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32))
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MatrixAudit(TenantRow, Base):
    __tablename__ = "matrix_audits"
    actor_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixRelease(TenantRow, Base):
    __tablename__ = "matrix_releases"
    __table_args__ = (UniqueConstraint("company_id", "kind", "version", "platform", "arch", name="uq_matrix_release"),)
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(40))
    platform: Mapped[str] = mapped_column(String(16))
    arch: Mapped[str] = mapped_column(String(16))
    manifest: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectorRelease(Base):
    """平台连接器发布；不继承租户行，站点插件仍保留公司隔离。"""
    __tablename__ = "connector_releases"
    __table_args__ = (UniqueConstraint("version", "platform", "arch", name="uq_connector_release_target"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(40))
    platform: Mapped[str] = mapped_column(String(16))
    arch: Mapped[str] = mapped_column(String(16))
    manifest: Mapped[dict] = mapped_column(JSON)
    stage: Mapped[str] = mapped_column(String(16), default="draft")
    upload_nonce: Mapped[str | None] = mapped_column(String(36), nullable=True)
    test_agent_ids: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixFlashActivity(TenantRow, Base):
    """完整扫描发现的秒杀活动；忽略提醒不删除活动。"""
    __tablename__ = "matrix_flash_activities"
    __table_args__ = (UniqueConstraint("company_id", "environment_id", "external_id", name="uq_matrix_flash_activity"),)
    environment_id: Mapped[int] = mapped_column(Integer, index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    product_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    source_item_id: Mapped[int] = mapped_column(Integer, index=True)
    dismissed_by: Mapped[list] = mapped_column(JSON, default=list)


class MatrixFlashRenewal(TenantRow, Base):
    """一个来源活动最多创建一个后继；所有副作用前持久化意图。"""
    __tablename__ = "matrix_flash_renewals"
    __table_args__ = (UniqueConstraint("activity_id", name="uq_matrix_flash_renewal"),)
    activity_id: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="pending")
    new_activity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terminated: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[str] = mapped_column(String(1000), default="")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatrixFlashSnapshot(TenantRow, Base):
    """完整扫描的环境级标记，区分未同步与真实空列表。"""
    __tablename__ = "matrix_flash_snapshots"
    __table_args__ = (UniqueConstraint("company_id", "environment_id", name="uq_matrix_flash_snapshot"),)
    environment_id: Mapped[int] = mapped_column(Integer, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    source_item_id: Mapped[int] = mapped_column(Integer)
    activity_count: Mapped[int] = mapped_column(Integer)
