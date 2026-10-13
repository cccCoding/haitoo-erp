"""按来源 SKU 或记录 ID 查询采集状态的组合索引。"""
from alembic import op

revision = "20261013_35"
down_revision = "20261013_34"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_collection_items_source_sku", "cross_company_collection_items",
                    ["company_id", "source_company_id", "source_library", "source_sku", "material_asset_id"])
    op.create_index("ix_collection_items_source_record", "cross_company_collection_items",
                    ["company_id", "source_company_id", "source_library", "source_record_id", "material_asset_id"])


def downgrade():
    op.drop_index("ix_collection_items_source_record", table_name="cross_company_collection_items")
    op.drop_index("ix_collection_items_source_sku", table_name="cross_company_collection_items")
