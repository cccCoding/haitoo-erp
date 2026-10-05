"""产品库店铺负责人及完整销量快照标记。

Revision ID: 20261003_24
Revises: 20261002_23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261003_24"
down_revision: Union[str, None] = "20261002_23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_library_sources", sa.Column("assigned_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_product_library_sources_assigned_user_id", "product_library_sources", ["assigned_user_id"])
    # 旧快照只包含全公司 TOP50 和分类商品，需要在首次读取时按原日期补算。
    op.add_column("product_library_daily_snapshots", sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("product_library_daily_snapshots", "is_complete")
    op.drop_index("ix_product_library_sources_assigned_user_id", table_name="product_library_sources")
    op.drop_column("product_library_sources", "assigned_user_id")
