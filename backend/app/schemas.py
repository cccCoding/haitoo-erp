from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator
from .models import Role, TaskStatus


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    user_code: str | None
    email: EmailStr
    role: Role
    company_id: int | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("created_at", return_type=int)
    def serialize_created_at(self, value: datetime) -> int:
        return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


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
    title_template: str | None = Field(default=None, max_length=500)
    product_description: str | None = Field(default=None, max_length=5000)
    size_chart_url: str | None = None
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
    title_template: str | None = Field(default=None, max_length=500)
    product_description: str | None = Field(default=None, max_length=5000)
    size_chart_url: str | None = None
    package_weight: float | None = Field(default=None, gt=0)
    package_length: float | None = Field(default=None, gt=0)
    package_width: float | None = Field(default=None, gt=0)
    package_height: float | None = Field(default=None, gt=0)
    sku_specifications: dict | None = None


class TemplateGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PodTaskCreate(BaseModel):
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


class NonAIPointRuleCreate(BaseModel):
    operation_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=120)
    points: int = Field(ge=0, le=1000000)
    enabled: bool = True
    description: str | None = Field(default=None, max_length=255)


class NonAIPointRuleUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    points: int = Field(ge=0, le=1000000)
    enabled: bool = True
    description: str | None = Field(default=None, max_length=255)


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


class DraftCreate(BaseModel):
    shop_id: int


class DraftSkuItem(BaseModel):
    image_url: str = Field(min_length=1, max_length=500)
    size: str | None = Field(default=None, max_length=50)
    sku: str = Field(min_length=1, max_length=32)


class MaterialDraftCreate(DraftCreate):
    template_id: int
    material_asset_ids: list[int] = Field(min_length=1, max_length=100)
    sku_items: list[DraftSkuItem] = Field(default_factory=list, max_length=1000)
    title: str = Field(min_length=1, max_length=180)
    product_description: str | None = Field(default=None, max_length=5000)
    size_chart_url: str | None = Field(default=None, max_length=500)


class DraftTitleGenerate(BaseModel):
    image_url: str = Field(min_length=1, max_length=500)


class DraftUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    shop_id: int


class RechargeInput(BaseModel):
    company_id: int
    amount: int = Field(gt=0)
    note: str = Field(min_length=1, max_length=255)


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    user_code: str | None = Field(default=None, min_length=2, max_length=2)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("user_code")
    @classmethod
    def validate_user_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) != 2:
            raise ValueError("用户代码必须恰好为两个字符")
        return value


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    user_code: str | None = Field(default=None, min_length=2, max_length=2)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None

    @field_validator("user_code")
    @classmethod
    def validate_user_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) != 2:
            raise ValueError("用户代码必须恰好为两个字符")
        return value


class MyUserCodeUpdate(BaseModel):
    """当前登录账号仅可更新自己的用户代码。"""
    user_code: str | None = Field(..., min_length=2, max_length=2)

    @field_validator("user_code")
    @classmethod
    def validate_user_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) != 2:
            raise ValueError("用户代码必须恰好为两个字符")
        return value


class MiaoshouShopQuery(BaseModel):
    site: str | None = Field(default=None, max_length=20)
    page_no: int = Field(default=1, ge=1, alias="pageNo")
    page_size: int = Field(default=100, ge=1, le=100, alias="pageSize")


class LedgerOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str
    entry_type: str
    amount: int
    balance_after: int
    note: str
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("created_at", return_type=int)
    def serialize_created_at(self, value: datetime) -> int:
        return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)
