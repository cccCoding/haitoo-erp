"""产品库数量明细及快照明细；一次性清空旧产品库数据。

升级前须停止 API 和 Worker，避免旧导入或统计事务继续写入。
Revision ID: 20261005_25
Revises: 20261003_24
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_25"
down_revision = "20261003_24"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("product_library_ranking_tasks", "product_library_daily_snapshot_items",
                  "product_library_daily_snapshots", "product_library_order_products",
                  "product_library_orders", "product_library_products", "product_library_sources"):
        op.execute(sa.text(f"DELETE FROM {table}"))
    op.add_column("product_library_order_products", sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"))
    op.create_table("product_library_order_sku_quantities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_product_id", sa.Integer(), nullable=False),
        sa.Column("platform_sku", sa.String(120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("order_product_id", "platform_sku", name="uq_product_library_order_sku_quantity"))
    op.create_index("ix_product_library_order_sku_quantities_order_product_id", "product_library_order_sku_quantities", ["order_product_id"])
    op.create_table("product_library_snapshot_order_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(120), nullable=False),
        sa.Column("ordered_at", sa.DateTime(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "order_id", "product_id", name="uq_product_library_snapshot_order_product"))
    op.create_index("ix_product_library_snapshot_order_products_snapshot_id", "product_library_snapshot_order_products", ["snapshot_id"])
    op.create_index("ix_product_library_snapshot_order_product", "product_library_snapshot_order_products", ["snapshot_id", "product_id"])


def downgrade():
    op.drop_table("product_library_snapshot_order_products")
    op.drop_table("product_library_order_sku_quantities")
    op.drop_column("product_library_order_products", "quantity")
