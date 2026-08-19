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

    class Config:
        from_attributes = True


class ShopOut(BaseModel):
    id: int
    name: str
    region: str
    auth_status: str

    class Config:
        from_attributes = True


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    group_id: int | None = None
    cover_url: str | None = None
    description: str | None = Field(default=None, max_length=500)
    color_count: int = 1
    sku_count: int = 1
    print_areas: list[dict] = []


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    group_id: int | None = None
    cover_url: str | None = None
    description: str | None = Field(default=None, max_length=500)


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


class SelectResult(BaseModel):
    result_url: str


class RechargeInput(BaseModel):
    company_id: int
    amount: int = Field(gt=0)
    note: str = Field(min_length=1, max_length=255)


class LedgerOut(BaseModel):
    id: int
    entry_type: str
    amount: int
    balance_after: int
    note: str
    created_at: datetime

    class Config:
        from_attributes = True
