"""新增素材使用状态

Revision ID: 20260918_11
Revises: 20260917_10
Create Date: 2026-09-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260918_11"
down_revision: Union[str, None] = "20260917_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("material_assets", sa.Column("usage_status", sa.String(length=12), nullable=False, server_default="unused"))
    op.create_index(op.f("ix_material_assets_usage_status"), "material_assets", ["usage_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_material_assets_usage_status"), table_name="material_assets")
    op.drop_column("material_assets", "usage_status")
