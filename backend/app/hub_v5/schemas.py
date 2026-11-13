"""协议5输入白名单；秘密、代码和任意执行地址不属于业务参数。"""
from datetime import datetime
import json
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator, field_serializer


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyInput(Input):
    enabled: bool
    listing_enabled: bool = False


class MemberPermissionInput(Input):
    enabled: bool
    # 兼容旧客户端；采集和上品权限统一由 enabled 决定。
    collect_enabled: bool = False
    listing_enabled: bool = False
    # 兼容旧客户端字段；实际数据范围及保存值统一为 own。
    view_scope: Literal["own", "company"] = "own"
    expected_revision: int = Field(ge=0)


class Heartbeat(Input):
    install_uuid: UUID
    version: str = Field(min_length=1, max_length=40)
    hub_identity: str | None = Field(default=None, min_length=1, max_length=120)
    hub_connected: bool
    local_paused: bool = False
    capabilities: dict[Literal["shop.collect", "listing.catalog", "promotion.flash_sale.renew", "promotion.flash_sale.collect"], list[Literal["MY", "ID"]]] = Field(default_factory=dict)
    update_state: dict = Field(default_factory=dict)


class ConnectionInput(Input):
    hub_identity: str = Field(min_length=1, max_length=120)


class SyncInput(Input):
    snapshot_key: str = Field(min_length=8, max_length=64)
    hub_identity: str = Field(min_length=1, max_length=120)
    version: int = Field(gt=0, le=9223372036854775807)
    expected_count: int = Field(ge=0, le=20000)
    part_count: int = Field(ge=1, le=100)


class DirectoryEntry(Input):
    container_code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    group_name: str = Field(default="", max_length=255)
    serial: str = Field(default="", max_length=120)
    account_names: list[str] = Field(default_factory=list, max_length=20)
    site: Literal["MY", "ID"] | None = None

    @field_validator("account_names")
    @classmethod
    def accounts(cls, value):
        if any(len(v) > 255 for v in value):
            raise ValueError("账号名称过长")
        return value


class DirectoryPart(Input):
    entries: list[DirectoryEntry] = Field(max_length=250)


class Override(Input):
    expected_revision: int = Field(ge=1)
    site: Literal["MY", "ID"] | None
    reason: str = Field(min_length=1, max_length=500)


class OverrideTarget(Input):
    id: int = Field(gt=0)
    expected_revision: int = Field(ge=1)


class BatchOverride(Input):
    environments: list[OverrideTarget] = Field(min_length=1, max_length=1000)
    site: Literal["MY", "ID"] | None = None
    activity_status: Literal["normal", "closed", "unchecked"] | None = None
    reason: str = Field(default="", max_length=500)


class FlashRenewalConfig(Input):
    threshold_hours: int = Field(default=12, ge=6, le=36)


class OperationInput(Input):
    name: str = Field(min_length=1, max_length=120)
    tasks: list[Literal["shop.collect", "listing.catalog", "promotion.flash_sale.renew", "promotion.flash_sale.collect"]] = Field(min_length=1, max_length=4)
    strategies: dict[Literal["MY"], int] = Field(default_factory=dict)
    flash_sale: FlashRenewalConfig = Field(default_factory=FlashRenewalConfig)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("tasks")
    @classmethod
    def distinct_tasks(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("不能重复选择")
        return value


class PlanInput(Input):
    name: str = Field(min_length=1, max_length=120)
    agent_id: int = Field(gt=0)
    operation_id: int = Field(gt=0)
    environment_ids: list[int] = Field(min_length=1, max_length=1000)
    scheduled: bool = False
    schedule_mode: Literal["daily", "interval"] = "daily"
    interval_hours: Literal[2, 4, 6] = 2
    time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("timezone")
    @classmethod
    def beijing_timezone(cls, value):
        return "Asia/Shanghai"

    @field_validator("environment_ids")
    @classmethod
    def distinct(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("不能重复选择")
        return value


class EnvironmentFilters(Input):
    q: str = Field(default="", max_length=200)
    site: Literal["", "MY", "ID", "unknown"] = ""
    executable: Literal["", "ready", "blocked"] = ""
    group: str = Field(default="", max_length=255)
    ungrouped: bool = False
    collected: bool | None = None
    agent_id: int | None = Field(default=None, gt=0)
    status: str = Field(default="", max_length=32)
    collection: str = Field(default="", max_length=32)
    exact: str | list[str] = ""

    @field_validator("agent_id", mode="before")
    @classmethod
    def blank_agent(cls, value):
        return None if value == "" else value

    @field_validator("exact")
    @classmethod
    def exact_limit(cls, value):
        values = value.splitlines() if isinstance(value, str) else value
        if len(values) > 500 or any(len(v)>255 for v in values): raise ValueError("批量匹配最多500行，每行255字符")
        return value


class PreviewInput(Input):
    environment_ids: list[int] = Field(default_factory=list, max_length=1000)
    filters: EnvironmentFilters = Field(default_factory=EnvironmentFilters)
    all_filtered: bool = False


class OperationPreviewInput(PreviewInput):
    agent_id: int = Field(gt=0)


class ManualPreviewInput(PreviewInput):
    tasks: list[Literal["shop.collect", "listing.catalog", "promotion.flash_sale.renew", "promotion.flash_sale.collect"]] = Field(min_length=1, max_length=4)
    strategies: dict[Literal["MY"], int] = Field(default_factory=dict)
    flash_sale: FlashRenewalConfig = Field(default_factory=FlashRenewalConfig)

    @field_validator("tasks", "environment_ids")
    @classmethod
    def distinct(cls, value):
        if len(value) != len(set(value)): raise ValueError("不能重复选择")
        return value


class RunInput(Input):
    preview_token: str = Field(min_length=20, max_length=100)
    expected_revision: int = Field(ge=1)


class ManualRunsInput(Input):
    previews: list[RunInput] = Field(min_length=1, max_length=1000)

    @field_validator("previews")
    @classmethod
    def distinct(cls, value):
        if len({p.preview_token for p in value}) != len(value): raise ValueError("不能重复提交预览")
        return value


class AttemptInput(Input):
    claim_token: str = Field(min_length=20, max_length=100)
    fencing: int = Field(gt=0)


class EventInput(AttemptInput):
    source_id: str = Field(min_length=1, max_length=64)
    stage: str = Field(min_length=1, max_length=80)
    message: str = Field(max_length=500)


class Identity(Input):
    site: Literal["MY", "ID"]
    external_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)


class IdentityInput(AttemptInput):
    identity: Identity


class EnvironmentIdentity(Input):
    site: Literal["MY"]
    environment_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)


class ListingResult(AttemptInput):
    accepted_count: int | None = Field(default=None, strict=True, gt=0, le=50)
    imported_count: int | None = Field(default=None, strict=True, gt=0, le=50)
    accepted: list[int] = Field(default_factory=list, max_length=50)
    rejected: list[int] = Field(default_factory=list, max_length=50)
    receipt: str = Field(min_length=1, max_length=500)


class Report(AttemptInput):
    status: Literal["succeeded", "partial_success", "failed", "cancelled", "awaiting_attention"]
    message: str = Field(default="", max_length=500)


class Resolve(Input):
    action: Literal["confirm-submitted", "confirm-not-submitted", "retry", "retransmit", "cancel"]
    evidence: str = Field(default="", max_length=1000)


class CollectionHeader(Input):
    identity: Identity | EnvironmentIdentity
    observed_at: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    timezone: str
    expected_count: int = Field(ge=0, le=100000)
    complete: bool
    empty_verified: bool = False
    total_verified: bool = False
    sections: dict[Literal["identity", "products", "traffic", "metrics", "health"], Literal["completed", "failed", "unsupported"]]
    metrics: dict[str, int | str | None] = Field(default_factory=dict)
    reasons: dict[Literal["identity", "products", "traffic", "metrics", "health"], str] = Field(default_factory=dict)

    @field_validator('timezone')
    @classmethod
    def known_timezone(cls,value):
        try:ZoneInfo(value)
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('快照时区必须是有效IANA时区')
        return value

    @field_serializer("observed_at", "window_start", "window_end")
    def serialize_instant(self, value):
        return value.isoformat() if value is not None else None

    @field_validator("reasons")
    @classmethod
    def reason_lengths(cls, value):
        if any(len(v) > 500 for v in value.values()): raise ValueError("分区说明过长")
        return value


class ProductManagementHeader(CollectionHeader):
    collection_kind: Literal["product_management"]
    product_scope: Literal["on_sale"]
    on_sale_count: int = Field(ge=0, le=100000)
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None


class ProductAnalysisHeader(CollectionHeader):
    collection_kind: Literal["product_analysis"]
    product_scope: Literal["on_sale"]
    on_sale_count: int = Field(ge=0, le=100000)


class CollectionInput(AttemptInput):
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    part_count: int = Field(ge=1, le=500)
    header: ProductAnalysisHeader | ProductManagementHeader | CollectionHeader


class ProductSKU(Input):
    external_id: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=500)
    seller_sku: str | None = Field(default=None, max_length=500)
    stock: int = Field(ge=0)
    price: str = Field(max_length=40, pattern=r"^\d+(?:\.\d{1,4})?$")
    sale_price: str | None = Field(default=None, max_length=40, pattern=r"^\d+(?:\.\d{1,4})?$")
    currency: Literal["MYR"] = "MYR"


class Product(Input):
    external_id: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=500)
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    traffic_reason: Literal["商品分析接口按商品ID查询无记录"] | None = None
    active: bool = True
    views: int | None = Field(default=None, ge=0)
    sales_count: int | None = Field(default=None, ge=0)
    gmv: str | None = Field(default=None, max_length=40, pattern=r"^\d+(?:\.\d{1,4})?$")
    views_reason: str | None = Field(default=None, max_length=255)
    sku_count: int | None = Field(default=None, ge=0, le=5000)
    skus: list[ProductSKU] = Field(default_factory=list, max_length=5000)


class CollectionPart(AttemptInput):
    products: list[Product] = Field(max_length=250)


class DeviceCommand(Input):
    kind: Literal["refresh", "pause", "resume", "revoke", "retry_update"]


class ReleaseInput(Input):
    manifest: dict
    enabled: bool = False


class FlashObservation(Input):
    external_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    activity_type: Literal["商家秒杀活动"]
    status: Literal["ongoing", "expired", "scheduled", "terminated", "unknown"]
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime
    product_count: int | None = Field(default=None, ge=0)


class FlashScan(AttemptInput):
    activities: list[FlashObservation] = Field(max_length=5000)
    complete: Literal[True]
    scope: Literal['all', 'ongoing', 'selected'] = 'all'

    @field_validator("activities")
    @classmethod
    def unique_activities(cls, value):
        if len({a.external_id for a in value}) != len(value):
            raise ValueError("活动ID重复，不能保存残缺扫描")
        return value


class FlashStep(AttemptInput):
    stage: Literal["pending", "prepared", "terminate_intent", "terminated", "copy_intent", "draft_confirmed", "publish_intent", "created", "published", "unknown", "failed", "skipped"]
    new_activity_id: str | None = Field(default=None, min_length=1, max_length=120)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    evidence: str = Field(default="", max_length=1000)
    error: str | None = Field(default=None, max_length=500)
    preparation: dict | None = None
    request_outcome: Literal['not_sent','rejected'] | None = None

    @field_validator('preparation')
    @classmethod
    def bounded_preparation(cls,value):
        if value is None:return value
        allowed={'promotion_name','type_detail','promotion_limit_dimension','effective_time_type','display_channels','pre_launch_day','flash_sale_products','seller_agreement'}
        if set(value)-allowed or value.get('type_detail')!=9 or value.get('promotion_limit_dimension') not in (0,1,4):raise ValueError('不支持的秒杀准备数据')
        products=value.get('flash_sale_products')
        if not isinstance(products,list) or not 1<=len(products)<=5000 or len(json.dumps(value,ensure_ascii=False))>2_000_000:raise ValueError('秒杀准备商品范围无效')
        if not isinstance(value.get('promotion_name'),str) or not 1<=len(value['promotion_name'])<=50:raise ValueError('秒杀准备名称无效')
        return value


class FlashSelection(Input):
    activity_ids: list[int] = Field(min_length=1, max_length=1000)

    @field_validator("activity_ids")
    @classmethod
    def distinct(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("不能重复选择活动")
        return value


class FlashResolve(Input):
    action: Literal["confirm-published", "resume", "cancel"]
    new_activity_id: str | None = Field(default=None, min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=1000)
    # 人工明确核对的平台状态，不能仅点击重试覆盖未知副作用。
    verified_stage: Literal["pending", "terminated", "draft_confirmed"] | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class FlashRecheck(AttemptInput):
    activity: FlashObservation
