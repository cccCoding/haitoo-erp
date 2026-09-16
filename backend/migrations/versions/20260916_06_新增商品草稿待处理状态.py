"""新增商品草稿待处理状态

Revision ID: 20260916_06
Revises: 20260914_05
Create Date: 2026-09-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260916_06"
down_revision: Union[str, None] = "20260914_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 仅修改新记录的默认状态；既有草稿继续保留当前制作阶段。
    with op.batch_alter_table("product_drafts") as batch_op:
        batch_op.alter_column(
            "workflow_stage",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default="pending",
        )


def downgrade() -> None:
    with op.batch_alter_table("product_drafts") as batch_op:
        batch_op.alter_column(
            "workflow_stage",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default="carousel_pending",
        )
