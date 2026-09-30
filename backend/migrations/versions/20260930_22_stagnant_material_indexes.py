"""为滞销素材实时筛选增加组合索引。

Revision ID: 20260930_22
Revises: 20260930_21
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260930_22"
down_revision: Union[str, None] = "20260930_21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_material_assets_company_created_id", "material_assets", ["company_id", "created_at", "id"])
    op.create_index("ix_material_assets_company_creator_created_id", "material_assets", ["company_id", "claimed_by", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_material_assets_company_creator_created_id", table_name="material_assets")
    op.drop_index("ix_material_assets_company_created_id", table_name="material_assets")
