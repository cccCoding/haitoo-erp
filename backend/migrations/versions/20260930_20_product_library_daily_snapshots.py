"""产品库每日销量榜单快照

Revision ID: 20260930_20
Revises: 20260929_19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_20"
down_revision: Union[str, None] = "20260929_19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_library_daily_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "snapshot_date", name="uq_product_library_snapshot_company_date"),
    )
    op.create_index("ix_product_library_daily_snapshots_company_id", "product_library_daily_snapshots", ["company_id"])
    op.create_index("ix_product_library_daily_snapshots_snapshot_date", "product_library_daily_snapshots", ["snapshot_date"])
    op.create_table(
        "product_library_daily_snapshot_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("count_7", sa.Integer(), nullable=False),
        sa.Column("count_15", sa.Integer(), nullable=False),
        sa.Column("count_30", sa.Integer(), nullable=False),
        sa.Column("rank_7", sa.Integer(), nullable=True),
        sa.Column("rank_15", sa.Integer(), nullable=True),
        sa.Column("rank_30", sa.Integer(), nullable=True),
        sa.Column("tier", sa.String(20), nullable=True),
        sa.UniqueConstraint("snapshot_id", "product_id", name="uq_product_library_snapshot_product"),
    )
    op.create_index("ix_product_library_daily_snapshot_items_snapshot_id", "product_library_daily_snapshot_items", ["snapshot_id"])
    op.create_index("ix_product_library_daily_snapshot_items_product_id", "product_library_daily_snapshot_items", ["product_id"])
    op.create_index("ix_product_library_snapshot_items_tier", "product_library_daily_snapshot_items", ["snapshot_id", "tier"])


def downgrade() -> None:
    op.drop_table("product_library_daily_snapshot_items")
    op.drop_table("product_library_daily_snapshots")
