"""产品库按可见来源聚合基础 SKU；统计与详情使用相同事实数据。"""
from datetime import timedelta

from sqlalchemy import func, select

from .models import (ProductLibraryOrder, ProductLibraryOrderProduct, ProductLibraryProduct,
                     ProductLibrarySource, ProductLibrarySnapshotOrderProduct, ProductTemplate)
from .product_library_rankings import _utc_boundary


def order_facts(snapshot=None, category=None):
    if snapshot is None:
        return select(
            ProductLibraryOrderProduct.product_id.label("product_id"),
            ProductLibraryOrderProduct.order_id.label("order_id"),
            ProductLibraryOrderProduct.quantity.label("quantity"),
            ProductLibraryOrder.order_number.label("order_number"),
            ProductLibraryOrder.ordered_at.label("ordered_at"),
            ProductLibraryOrder.company_id.label("company_id"),
        ).join(ProductLibraryOrder, ProductLibraryOrder.id == ProductLibraryOrderProduct.order_id).subquery()
    days = {"top7": 7, "top15": 15, "top30": 30}.get(category, 7)
    fact = ProductLibrarySnapshotOrderProduct
    return select(fact.product_id, fact.order_id, fact.quantity, fact.order_number, fact.ordered_at).where(
        fact.snapshot_id == snapshot.id,
        fact.ordered_at >= _utc_boundary(snapshot.snapshot_date - timedelta(days=days)),
        fact.ordered_at < _utc_boundary(snapshot.snapshot_date),
    ).subquery()


def sku_statistics(db, conditions, facts, *, page, page_size, category=None):
    product, source = ProductLibraryProduct, ProductLibrarySource
    summary = select(
        product.sku.label("sku"), func.min(product.id).label("id"),
        func.count(func.distinct(facts.c.order_id)).label("order_count"),
        func.coalesce(func.sum(facts.c.quantity), 0).label("sales_quantity"),
    ).join(source, source.id == product.source_id).outerjoin(
        ProductTemplate, ProductTemplate.id == product.template_id).outerjoin(
        facts, facts.c.product_id == product.id).where(*conditions).group_by(product.sku).subquery()
    query = select(summary)
    quantity = summary.c.sales_quantity
    if category and category.startswith("top"):
        query = query.where(quantity > 0)
    elif category:
        low, high = {"potential": (30, 70), "hot": (70, 130), "booming": (130, None)}[category]
        query = query.where(quantity > low)
        if high is not None:
            query = query.where(quantity <= high)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    if category and category.startswith("top"):
        total = min(total, 50)
    limit = min(page_size, max(0, total - (page - 1) * page_size))
    rows = db.execute(query.order_by(quantity.desc(), summary.c.sku.asc())
                      .offset((page - 1) * page_size).limit(limit)).mappings().all()
    ids = [row["id"] for row in rows]
    representatives = {p.id: (p, template_name) for p, template_name in db.execute(
        select(product, ProductTemplate.name).outerjoin(ProductTemplate, ProductTemplate.id == product.template_id)
        .where(product.id.in_(ids))).all()}
    selected_skus = [row["sku"] for row in rows]
    shops = db.execute(select(product.sku, source.id, source.shop_name, product.external_product_id,
        func.coalesce(func.sum(facts.c.quantity), 0))
        .join(source, source.id == product.source_id)
        .outerjoin(ProductTemplate, ProductTemplate.id == product.template_id)
        .outerjoin(facts, facts.c.product_id == product.id)
        .where(*conditions, product.sku.in_(selected_skus))
        .group_by(product.sku, source.id, source.shop_name, product.external_product_id)
        .order_by(source.platform, source.site, source.shop_name, product.external_product_id)).all()
    shop_data = {}
    for sku, source_id, shop_name, external_id, sales in shops:
        shop_data.setdefault(sku, []).append({"source_id": source_id, "shop_name": shop_name,
            "product_id": external_id, "sales_quantity": int(sales)})
    items = []
    for index, row in enumerate(rows, start=(page - 1) * page_size + 1):
        p, template = representatives[row["id"]]
        items.append({"id": p.id, "source_type": "product", "sku": p.sku,
            "template_id": p.template_id, "template": template or "未匹配", "title": p.title,
            "image_url": p.image_url, "order_count": int(row["order_count"]),
            "sales_quantity": int(row["sales_quantity"]), "shop_data": shop_data.get(p.sku, []),
            **({"rank": index} if category else {})})
    return {"total": total, "page": page, "page_size": page_size, "items": items}
