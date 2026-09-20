"""新增妙手公共采集箱同步缓存

Revision ID: 20260920_13
Revises: 20260920_12
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260920_13"
down_revision: Union[str, None] = "20260920_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("miaoshou_collect_box_initial_synced_at", sa.DateTime(), nullable=True))
    op.add_column("companies", sa.Column("miaoshou_collect_box_last_synced_at", sa.DateTime(), nullable=True))
    op.add_column("companies", sa.Column("miaoshou_collect_box_last_pruned_at", sa.DateTime(), nullable=True))
    op.create_table(
        "miaoshou_collect_box_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("common_collect_box_detail_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("thumbnail", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("remote_created_at", sa.DateTime(), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "common_collect_box_detail_id", name="uq_miaoshou_collect_box_company_detail"),
    )
    op.create_index(op.f("ix_miaoshou_collect_box_items_company_id"), "miaoshou_collect_box_items", ["company_id"], unique=False)
    op.create_index(op.f("ix_miaoshou_collect_box_items_common_collect_box_detail_id"), "miaoshou_collect_box_items", ["common_collect_box_detail_id"], unique=False)
    op.create_index(op.f("ix_miaoshou_collect_box_items_status"), "miaoshou_collect_box_items", ["status"], unique=False)
    op.create_index(op.f("ix_miaoshou_collect_box_items_remote_created_at"), "miaoshou_collect_box_items", ["remote_created_at"], unique=False)
    op.create_index(op.f("ix_miaoshou_collect_box_items_remote_updated_at"), "miaoshou_collect_box_items", ["remote_updated_at"], unique=False)


def downgrade() -> None:
    for name in ("remote_updated_at", "remote_created_at", "status", "common_collect_box_detail_id", "company_id"):
        op.drop_index(op.f(f"ix_miaoshou_collect_box_items_{name}"), table_name="miaoshou_collect_box_items")
    op.drop_table("miaoshou_collect_box_items")
    op.drop_column("companies", "miaoshou_collect_box_last_pruned_at")
    op.drop_column("companies", "miaoshou_collect_box_last_synced_at")
    op.drop_column("companies", "miaoshou_collect_box_initial_synced_at")
