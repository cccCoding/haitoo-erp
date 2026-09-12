"""移除商品草稿来源任务字段

Revision ID: 20260912_04
Revises: 20260912_03
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260912_04"
down_revision: Union[str, None] = "20260912_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("product_drafts")}
    if "source_task_id" in columns:
        op.drop_column("product_drafts", "source_task_id")


def downgrade() -> None:
    op.add_column("product_drafts", sa.Column("source_task_id", sa.Integer(), nullable=True))
