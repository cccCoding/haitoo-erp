import enum
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(20), default="MY")
    external_shop_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    auth_status: Mapped[str] = mapped_column(String(30), default="not_connected")
    miaoshou_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    miaoshou_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserShop(Base):
    __tablename__ = "user_shops"
    __table_args__ = (UniqueConstraint("user_id", "shop_id", name="uq_user_shop"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)


class TemplateGroup(Base):
    __tablename__ = "template_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductTemplate(Base):
    __tablename__ = "product_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("template_groups.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    sku_specifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="published")
    color_count: Mapped[int] = mapped_column(Integer, default=1)
    sku_count: Mapped[int] = mapped_column(Integer, default=1)
    print_areas: Mapped[dict] = mapped_column(JSON, default=list)


class PodTask(Base):
    __tablename__ = "pod_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("product_templates.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.QUEUED)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result_urls: Mapped[dict] = mapped_column(JSON, default=list)
    selected_result_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estimated_points: Mapped[int] = mapped_column(Integer)
    actual_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductDraft(Base):
    __tablename__ = "product_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    source_task_id: Mapped[int] = mapped_column(ForeignKey("pod_tasks.id"))
    title: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), default="pending_publish")
    image_urls: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PointAccount(Base):
    __tablename__ = "point_accounts"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    available: Mapped[int] = mapped_column(Integer, default=0)
    frozen: Mapped[int] = mapped_column(Integer, default=0)


class PointLedger(Base):
    __tablename__ = "point_ledgers"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("pod_tasks.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(40))
    amount: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
