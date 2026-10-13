"""跨来源库按来源公司和原 SKU 查询采集历史。"""
from alembic import op

revision = "20261013_36"
down_revision = "20261013_35"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_collection_items_company_source_sku", "cross_company_collection_items",
                    ["company_id", "source_company_id", "source_sku"])


def downgrade():
    op.drop_index("ix_collection_items_company_source_sku", table_name="cross_company_collection_items")
