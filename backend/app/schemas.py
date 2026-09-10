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


class TemplateAiPrompt(BaseModel):
    """产品模板中可复用的印花贴合提示词。"""
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1000)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=5)
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
    ai_prompts: list[TemplateAiPrompt] = Field(default_factory=list, max_length=50)
    color_count: int = 1
    sku_count: int = 1

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or not value.isascii() or not value.isalnum():
            raise ValueError("模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字")
        return value


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=5)
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
    ai_prompts: list[TemplateAiPrompt] | None = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not value or not value.isascii() or not value.isalnum():
            raise ValueError("模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字")
        return value


class TemplateGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PodTaskCreate(BaseModel):
    template_id: int
    white_image_id: int
    # 不传时沿用平台后台配置的默认模型。
    provider: str | None = Field(default=None, max_length=40)
    task_type: str = Field(default="替换印花", min_length=1, max_length=80)
    ratio: Literal["1:1", "3:4"] = "1:1"
    quality: Literal["1K", "2K"] = "1K"
    print_url: str | None = None
    print_urls: list[str] = Field(default_factory=list, max_length=500)
    creative_requirement: str = Field(min_length=1, max_length=1000)


class UserTemplateWhiteImageCreate(BaseModel):
    template_id: int
    user_id: int | None = None
    name: str = Field(min_length=1, max_length=80)
    image_url: str = Field(min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("白底图名称不能为空")
        return value


class UserTemplateWhiteImageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    image_url: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("白底图名称不能为空")
        return value


class UserTemplatePromptCreate(BaseModel):
    template_id: int
    user_id: int | None = None
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("name", "content")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称和创作要求不能为空")
        return value


class UserTemplatePromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    content: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("name", "content")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("名称和创作要求不能为空")
        return value


class UploadPresignInput(BaseModel):
    content_type: str
    content_length: int = Field(gt=0, le=5 * 1024 * 1024)


class ImageUploadPresignItem(BaseModel):
    """直传单张图片的元信息；签名绑定大小与类型，防止中途替换文件。"""
    content_type: str
    content_length: int = Field(gt=0, le=5 * 1024 * 1024)


class ImageUploadPresignInput(BaseModel):
    """按业务目录批量签发 R2 直传地址；目录由服务端白名单限制。"""
    category: str = Field(min_length=1, max_length=40)
    files: list[ImageUploadPresignItem] = Field(min_length=1, max_length=20)


class MaterialUploadPresignInput(BaseModel):
    files: list[ImageUploadPresignItem] = Field(min_length=1, max_length=100)


class MaterialUploadCommitItem(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    name: str = Field(default="本地素材", max_length=180)


class MaterialUploadCommitInput(BaseModel):
    template_id: int
    items: list[MaterialUploadCommitItem] = Field(min_length=1, max_length=100)


class MaterialDownloadInput(BaseModel):
    material_asset_ids: list[int] = Field(min_length=1, max_length=100)


class AIProviderSettingUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    enabled: bool
    is_default: bool = False
    images_per_task: int = Field(default=1, ge=1, le=100)


class TaskQueueSettingUpdate(BaseModel):
    submit_interval_seconds: int = Field(default=1, ge=1, le=3600)
    result_interval_seconds: int = Field(default=5, ge=1, le=3600)


class AdminCompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    admin_name: str = Field(min_length=1, max_length=80)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)


class MiaoshouAccountUpdate(BaseModel):
    app_id: str = Field(min_length=1, max_length=255)
    app_secret: str = Field(min_length=1, max_length=500)

    @field_validator("app_id", "app_secret")
    @classmethod
    def validate_credentials(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("妙手 API Key 不能为空")
        return value


class AIProviderCredentialUpdate(BaseModel):
    api_key: str = Field(min_length=1, max_length=2000)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("平台密钥不能为空")
        return value


class ClaimMaterials(BaseModel):
    result_urls: list[str] = Field(min_length=1, max_length=1000)


class MaterialDraftCreate(BaseModel):
    """尺码图不再随草稿提交，一律沿用所选产品模版的尺码图。"""
    template_id: int
    material_asset_ids: list[int] = Field(min_length=1, max_length=100)
    title: str = Field(min_length=25, max_length=255)
    product_description: str | None = Field(default=None, max_length=5000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not 25 <= len(value) <= 255:
            raise ValueError("商品标题长度须为 25-255 个字符")
        return value


class DraftTitleGenerate(BaseModel):
    image_url: str = Field(min_length=1, max_length=500)


class DraftUpdate(BaseModel):
    title: str = Field(min_length=25, max_length=255)
    product_description: str | None = Field(default=None, max_length=5000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not 25 <= len(value) <= 255:
            raise ValueError("商品标题长度须为 25-255 个字符")
        return value


class TiktokDraftProductOverride(BaseModel):
    draft_id: int = Field(ge=1)
    price: float | None = Field(default=None, ge=0.01, le=999999)
    quantity: int | None = Field(default=None, ge=0, le=999999)


class TiktokDraftExportInput(BaseModel):
    draft_ids: list[int] = Field(min_length=1, max_length=50)
    category_catalog_id: int = Field(ge=1)
    category: str = Field(min_length=1, max_length=255)
    default_price: float = Field(ge=0.01, le=999999)
    default_quantity: int = Field(default=999, ge=0, le=999999)
    cod: Literal["Y", "N"] = "Y"
    attributes: dict[str, str | list[str]] = Field(default_factory=dict, max_length=14)
    product_overrides: list[TiktokDraftProductOverride] = Field(default_factory=list, max_length=50)


class TiktokCategoryAttributeInputModeUpdate(BaseModel):
    category: str = Field(min_length=1, max_length=255)
    field: str = Field(min_length=1, max_length=255)
    input_mode: Literal["text", "select", "select_or_text"]


class TiktokCategoryCatalogUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    attribute_input_modes: list[TiktokCategoryAttributeInputModeUpdate] = Field(default_factory=list, max_length=1000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("类目库名称不能为空")
        return value


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    user_code: str = Field(min_length=2, max_length=2)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("user_code", mode="before")
    @classmethod
    def validate_user_code(cls, value: str) -> str:
        value = value.strip() if isinstance(value, str) else value
        if not value or len(value) != 2:
            raise ValueError("用户代码必须恰好为两个字符")
        return value


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    user_code: str | None = Field(default=None, min_length=2, max_length=2)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None

    @field_validator("user_code", mode="before")
    @classmethod
    def validate_user_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip() if isinstance(value, str) else value
        if not value:
            return None
        if len(value) != 2:
            raise ValueError("用户代码必须恰好为两个字符")
        return value


class MyUserCodeUpdate(BaseModel):
    """当前登录账号仅可更新自己的名称和用户代码。"""
    name: str | None = Field(default=None, min_length=1, max_length=80)
    user_code: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("user_code")
    @classmethod
    def validate_user_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) != 2:
            raise ValueError("用户代码必须恰好为两个字符")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class MiaoshouShopQuery(BaseModel):
    site: str | None = Field(default=None, max_length=20)
    page_no: int = Field(default=1, ge=1, alias="pageNo")
    page_size: int = Field(default=100, ge=1, le=100, alias="pageSize")
