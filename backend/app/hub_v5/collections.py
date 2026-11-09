"""采集包暂存和原子发布；真实0、未知和旧数据分别处理。"""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from .models import MatrixCollection, MatrixPart, MatrixShop, MatrixItem
from .service import checked_attempt, fail, utcnow, event
from ..supply_common import digest

# orders 与快照窗口一致，表示最近7个完整自然日的订单数；缺失时保持未知。
METRICS = {"gmv", "visitors7d", "orders", "orders_to_ship", "violations_score", "shop_status"}


def part(db, kind, parent_id, number, count, values):
    if not 0 <= number < count: fail("分片编号越界", 422)
    checksum = digest(values)
    old = db.scalar(select(MatrixPart).where(MatrixPart.kind == kind, MatrixPart.parent_id == parent_id, MatrixPart.number == number))
    if old:
        if old.digest != checksum: fail("分片重传内容不一致")
    else:
        db.add(MatrixPart(kind=kind, parent_id=parent_id, number=number, digest=checksum, payload=values))
    return checksum


def parts(db, kind, parent_id, count):
    rows = db.scalars(select(MatrixPart).where(MatrixPart.kind == kind, MatrixPart.parent_id == parent_id).order_by(MatrixPart.number)).all()
    if [r.number for r in rows] != list(range(count)): fail("采集包缺少分片")
    return [value for row in rows for value in row.payload]


def create(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    if "shop.collect" not in run.frozen["config"]["tasks"]: fail("任务不含采集")
    shop = db.get(MatrixShop, item.shop_id) if item.shop_id else None
    h = payload.header
    if hasattr(h.identity, "environment_id"):
        if not shop or shop.site != h.identity.site or shop.environment_id != item.environment_id or h.identity.environment_id != item.environment_id:
            fail("采集包与执行环境不一致")
    elif not shop or shop.environment_id is not None or (shop.site, shop.external_id) != (h.identity.site, h.identity.external_id):
        fail("快照店铺身份未确认")
    header = h.model_dump(mode="json")
    if set(header["metrics"]) - METRICS: fail("快照包含未允许指标", 422)
    for key, val in header["metrics"].items():
        if val is None or key == "shop_status": continue
        try:
            number = Decimal(str(val))
            if not number.is_finite() or number < 0: raise ValueError()
            if key == "orders" and number != number.to_integral_value(): raise ValueError()
        except (ValueError, InvalidOperation): fail("指标值无效", 422)
    if header["metrics"].get("shop_status") not in {None, "normal", "abnormal", "unknown"}: fail("店铺状态无效", 422)
    old = db.scalar(select(MatrixCollection).where(MatrixCollection.item_id == item.id, MatrixCollection.content_hash == payload.content_hash))
    if old:
        if old.header != header or old.part_count != payload.part_count: fail("采集包幂等内容不一致")
        return old
    row = MatrixCollection(company_id=agent.company_id, item_id=item.id, shop_id=shop.id,
        content_hash=payload.content_hash, part_count=payload.part_count, header=header)
    db.add(row); db.flush()
    item.collection_status = "staged"
    return row


def validate_window(header):
    try:
        tz = ZoneInfo(header["timezone"])
        observed = datetime.fromisoformat(header["observed_at"].replace("Z", "+00:00"))
        start = datetime.fromisoformat(header["window_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(header["window_end"].replace("Z", "+00:00"))
        if any(d.tzinfo is None for d in (observed,start,end)): raise ValueError()
        expected_end = observed.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        expected_start = expected_end - timedelta(days=7)
        if start != expected_start or end != expected_end or observed > datetime.now(timezone.utc)+timedelta(minutes=5): raise ValueError()
    except (ValueError, KeyError): fail("统计窗口必须是采集时所在店铺时区的最近7个完整自然日", 422)


def commit(db, agent, item_id, collection_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    row = db.get(MatrixCollection, collection_id)
    if not row or row.company_id != agent.company_id or row.item_id != item.id: fail("采集包不存在", 404)
    if row.status == "committed": return snapshot_view(db, row)
    products = parts(db, "collection", row.id, row.part_count)
    if digest({"header": row.header, "products": products}) != row.content_hash: fail("采集包摘要不一致", 422)
    h = row.header
    management = h.get("collection_kind") == "product_management"
    if management:
        if h["window_start"] is not None or h["window_end"] is not None: fail("商品管理页不能声明流量时间窗口", 422)
        observed = datetime.fromisoformat(h["observed_at"].replace("Z", "+00:00"))
        if observed > datetime.now(timezone.utc) + timedelta(minutes=5): fail("采集时间不能晚于当前时间", 422)
    else:
        validate_window(h)
    issue = None
    required = ("identity", "products") if management else ("identity", "products", "traffic")
    if not h["complete"] or any(h["sections"].get(s) != "completed" for s in required):
        issue = "必需采集分区不完整"
    if len(products) != h["expected_count"] or len({p["external_id"] for p in products}) != len(products): issue = "商品总数或分页完整性不一致"
    if management:
        if h["on_sale_count"] != len(products) or any(not p.get("active") for p in products): issue = "在售商品数量与完整列表不一致"
        if h["sections"].get("traffic") != "unsupported" or any(p.get("impressions") is not None or p.get("clicks") is not None for p in products): issue = "商品管理页浏览次数不能冒充曝光或点击"
        for p in products:
            skus = p.get("skus", [])
            if "views" not in p or p["views"] is None and p.get("views_reason") != "商品管理页未提供浏览次数（--）": issue = "商品浏览次数缺失"
            if p.get("sku_count") != len(skus) or not skus: issue = "SKU 明细与页面数量不一致"
            if len({("id",s["external_id"]) if s.get("external_id") else ("spec",s.get("name"),s.get("seller_sku")) for s in skus}) != len(skus): issue = "商品包含重复 SKU 明细"
    elif any(p.get("impressions") is None or p.get("clicks") is None for p in products if p.get("active", True)):
        issue = "在架商品核心流量缺失"
    shop = db.get(MatrixShop, row.shop_id)
    old = db.get(MatrixCollection, shop.snapshot_id) if shop.snapshot_id else None
    previous = old.header["expected_count"] if old else None
    if not products and not (h["empty_verified"] and h["total_verified"]): issue = "空店缺少完整分页及真实0证明"
    if previous and len(products) < previous * .2 and not h["total_verified"]: issue = "商品数量异常下降，需核对完整性"
    if issue:
        row.status, row.quality = "validation_failed", {"reason": issue, "previous_count": previous, "observed_count": len(products)}
        item.collection_status = "validation_failed"
        event(db, item, "collection.rejected", row.quality)
        db.commit(); fail(issue, 422)
    if old and datetime.fromisoformat(row.header["observed_at"].replace("Z", "+00:00")) < datetime.fromisoformat(old.header["observed_at"].replace("Z", "+00:00")):
        fail("旧采集包不能覆盖更新快照")
    row.status, row.committed_at = "committed", utcnow()
    summary = summarize(products)
    if management:
        summary.update({k: None for k in ("impressions", "clicks", "ctr", "with_impressions", "zero_impressions", "exposure_ratio")})
    row.quality = {"complete": True, "count": len(products), "summary": summary, "optional_errors": [s for s in ("metrics", "health") if h["sections"].get(s) == "failed"]}
    shop.snapshot_id = row.id
    item.collection_status = "committed"
    event(db, item, "collection.committed", {"snapshot_id": row.id, "count": len(products)})
    db.commit()
    return snapshot_view(db, row)


def summarize(products):
    active = [p for p in products if p.get("active", True)]
    imp = sum(p["impressions"] for p in active) if all(p.get("impressions") is not None for p in active) else None
    clicks = sum(p["clicks"] for p in active) if all(p.get("clicks") is not None for p in active) else None
    with_imp = sum(p["impressions"] > 0 for p in active) if imp is not None else None
    # 商品管理页明确返回“--”的商品按无浏览统计。
    views_complete = all(p.get("views") is not None or p.get("views_reason") == "商品管理页未提供浏览次数（--）" for p in active)
    with_views = sum((p.get("views") or 0) > 0 for p in active) if views_complete else None
    with_sales = sum(p["sales_count"] > 0 for p in active) if all(p.get("sales_count") is not None for p in active) else None
    return {"view_counts_version": 2, "with_views": with_views, "zero_views": len(active) - with_views if with_views is not None else None,
        "sell_through_rate": with_sales / len(active) if active and with_sales is not None else None,
        "active": len(active), "views_covered": sum(p.get("views") is not None for p in active), "views": sum(p["views"] for p in active) if all(p.get("views") is not None for p in active) else None,
        "sku_count": sum(p["sku_count"] for p in active) if all(p.get("sku_count") is not None for p in active) else None,
        "with_impressions": with_imp, "zero_impressions": len(active)-with_imp if with_imp is not None else None,
        "impressions": imp, "clicks": clicks, "ctr": clicks / imp if imp and clicks is not None else None,
        "exposure_ratio": with_imp / len(active) if active and with_imp is not None else None}


def snapshot_view(db, row):
    if not row: return None
    summary = row.quality.get("summary")
    if summary is None or summary.get("view_counts_version") != 2:
        calculated = summarize([p for r in db.scalars(select(MatrixPart).where(MatrixPart.kind == "collection", MatrixPart.parent_id == row.id)) for p in r.payload])
        summary = {**calculated, **(summary or {})}
        summary.update({key: calculated[key] for key in ("view_counts_version", "with_views", "zero_views")})
    observed = datetime.fromisoformat(row.header["observed_at"].replace("Z", "+00:00"))
    from .service import instant
    return {"id": row.id, "observed_at": row.header["observed_at"], "committed_at": instant(row.committed_at), "window_start": row.header["window_start"],
        "window_end": row.header["window_end"], "timezone": row.header["timezone"], "site": row.header["identity"]["site"],
        "collection_kind": row.header.get("collection_kind", "analytics"), "on_sale_count": row.header.get("on_sale_count"),
        "currency": "MYR" if row.header["identity"]["site"] == "MY" else "IDR", "quality": row.quality, "sections": row.header["sections"],
        "reasons": row.header["reasons"], "stale": datetime.now(timezone.utc)-observed > timedelta(hours=24),
        **summary, **row.header["metrics"]}
