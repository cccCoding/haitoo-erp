"""统一商品图片有序列表

Revision ID: 20260912_03
Revises: 20260911_02
Create Date: 2026-09-12
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260912_03"
down_revision: Union[str, None] = "20260911_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _list_value(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("product_drafts")}
    if "main_image_url" not in columns:
        return

    drafts = sa.table(
        "product_drafts",
        sa.column("id", sa.Integer()),
        sa.column("main_image_url", sa.String(length=500)),
        sa.column("carousel_items", sa.JSON()),
        sa.column("sku_items", sa.JSON()),
        sa.column("image_urls", sa.JSON()),
    )
    rows = list(connection.execute(sa.select(
        drafts.c.id,
        drafts.c.main_image_url,
        drafts.c.carousel_items,
        drafts.c.sku_items,
    )).mappings())
    for row in rows:
        main_url = str(row["main_image_url"] or "").strip()
        if not main_url:
            continue
        carousel_items = [dict(item) for item in _list_value(row["carousel_items"]) if isinstance(item, dict) and item.get("image_url")]
        if not carousel_items:
            seen_skus: set[str] = set()
            seen_urls: set[str] = set()
            for raw in _list_value(row["sku_items"]):
                if not isinstance(raw, dict):
                    continue
                sku = str(raw.get("sku") or "").strip()
                image_url = str(raw.get("image_url") or "").strip()
                if not sku or not image_url or sku in seen_skus or image_url in seen_urls:
                    continue
                seen_skus.add(sku)
                seen_urls.add(image_url)
                carousel_items.append({"sku": sku, "image_url": image_url, "task_id": None, "source_type": "sku"})
                if len(carousel_items) == 9:
                    break
        carousel_items = [item for item in carousel_items if item.get("image_url") != main_url]
        ordered_items = [{
            "sku": None,
            "image_url": main_url,
            "task_id": None,
            "source_type": "main_image",
        }, *carousel_items[:8]]
        connection.execute(
            drafts.update().where(drafts.c.id == row["id"]).values(
                carousel_items=ordered_items,
                image_urls=[item["image_url"] for item in ordered_items],
            )
        )

    op.drop_column("product_drafts", "main_image_url")


def downgrade() -> None:
    op.add_column("product_drafts", sa.Column("main_image_url", sa.String(length=500), nullable=True))
