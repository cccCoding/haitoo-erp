"""新增产品库与历史订单明细

Revision ID: 20260929_19
Revises: 20260929_18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260929_19"
down_revision: Union[str, None] = "20260929_18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_library_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(80), nullable=False),
        sa.Column("site", sa.String(80), nullable=False),
        sa.Column("shop_name", sa.String(160), nullable=False),
        sa.UniqueConstraint("company_id", "platform", "site", "shop_name", name="uq_product_library_source"),
    )
    op.create_index("ix_product_library_sources_company_id", "product_library_sources", ["company_id"])
    op.create_table(
        "product_library_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_product_id", sa.String(120), nullable=False),
        sa.Column("sku", sa.String(120), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_id", "external_product_id", "sku", name="uq_product_library_product"),
    )
    op.create_index("ix_product_library_products_company_id", "product_library_products", ["company_id"])
    op.create_index("ix_product_library_products_source_id", "product_library_products", ["source_id"])
    op.create_index("ix_product_library_products_template_id", "product_library_products", ["template_id"])
    op.create_index("ix_product_library_products_company_sku", "product_library_products", ["company_id", "sku"])
    op.create_table(
        "product_library_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(120), nullable=False),
        sa.Column("ordered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_id", "order_number", name="uq_product_library_order"),
    )
    op.create_index("ix_product_library_orders_company_id", "product_library_orders", ["company_id"])
    op.create_index("ix_product_library_orders_source_id", "product_library_orders", ["source_id"])
    op.create_index("ix_product_library_orders_company_ordered_at", "product_library_orders", ["company_id", "ordered_at"])
    op.create_table(
        "product_library_order_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("order_id", "product_id", name="uq_product_library_order_product"),
    )
    op.create_index("ix_product_library_order_products_order_id", "product_library_order_products", ["order_id"])
    op.create_index("ix_product_library_order_products_product", "product_library_order_products", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_library_order_products")
    op.drop_table("product_library_orders")
    op.drop_table("product_library_products")
    op.drop_table("product_library_sources")
