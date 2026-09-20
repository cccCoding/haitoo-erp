"""区分 TikTok 本土店与跨境店类目模板

Revision ID: 20260920_12
Revises: 20260918_11
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260920_12"
down_revision: Union[str, None] = "20260918_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tiktok_category_catalogs", sa.Column("template_type", sa.String(length=32), nullable=False, server_default="tiktok_local"))
    op.create_index(op.f("ix_tiktok_category_catalogs_template_type"), "tiktok_category_catalogs", ["template_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tiktok_category_catalogs_template_type"), table_name="tiktok_category_catalogs")
    op.drop_column("tiktok_category_catalogs", "template_type")
