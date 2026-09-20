"""补充妙手采集箱清理游标

Revision ID: 20260920_14
Revises: 20260920_13
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260920_14"
down_revision: Union[str, None] = "20260920_13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("companies")}
    if "miaoshou_collect_box_last_pruned_at" not in columns:
        op.add_column("companies", sa.Column("miaoshou_collect_box_last_pruned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("companies")}
    if "miaoshou_collect_box_last_pruned_at" in columns:
        op.drop_column("companies", "miaoshou_collect_box_last_pruned_at")
