from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field
from .models import Role, TaskStatus


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    company_id: int | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ShopOut(BaseModel):
    id: int
    name: str
    region: str
    external_shop_id: str | None
    nickname: str | None
    platform: str | None
    auth_status: str
    auth_expires_at: str | None

    class Config:
        from_attributes = True


class ShopManagerUpdate(BaseModel):
    """店铺普通成员管理员列表；提交的列表会完整覆盖原有分配。"""
    member_ids: list[int] = Field(default_factory=list, max_length=100)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    group_id: int | None = None
    cover_url: str | None = None
    description: str | None = Field(default=None, max_length=500)
    package_weight: float | None = Field(default=None, gt=0)
    package_length: float | None = Field(default=None, gt=0)
    package_width: float | None = Field(default=None, gt=0)
    package_height: float | None = Field(default=None, gt=0)
    sku_specifications: dict | None = None
    color_count: int = 1
    sku_count: int = 1
    print_areas: list[dict] = []


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    group_id: int | None = None
    cover_url: str | None = None
    description: str | None = Field(default=None, max_length=500)
    package_weight: float | None = Field(default=None, gt=0)
    package_length: float | None = Field(default=None, gt=0)
    package_width: float | None = Field(default=None, gt=0)
    package_height: float | None = Field(default=None, gt=0)
    sku_specifications: dict | None = None


class TemplateGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PodTaskCreate(BaseModel):
    shop_id: int
    template_id: int
    placement: Literal["居中印花", "满版印花"] = "居中印花"
    ratio: Literal["1:1", "3:4"] = "1:1"
    quality: Literal["1K", "2K"] = "1K"
    print_url: str | None = None
    print_urls: list[str] = Field(default_factory=list, max_length=1000)
    creative_requirement: str | None = Field(default=None, max_length=1000)


class AIProviderSettingUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    enabled: bool
    is_default: bool = False


class AdminCompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    admin_name: str = Field(min_length=1, max_length=80)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)
    initial_points: int = Field(default=0, ge=0)


class MiaoshouAccountUpdate(BaseModel):
    app_id: str = Field(min_length=1, max_length=255)
    app_secret: str = Field(min_length=1, max_length=500)


class SelectResult(BaseModel):
    result_url: str


class RechargeInput(BaseModel):
    company_id: int
    amount: int = Field(gt=0)
    note: str = Field(min_length=1, max_length=255)


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class MiaoshouShopQuery(BaseModel):
    site: str | None = Field(default=None, max_length=20)
    page_no: int = Field(default=1, ge=1, alias="pageNo")
    page_size: int = Field(default=100, ge=1, le=100, alias="pageSize")


class LedgerOut(BaseModel):
    id: int
    entry_type: str
    amount: int
    balance_after: int
    note: str
    created_at: datetime

    class Config:
        from_attributes = True
