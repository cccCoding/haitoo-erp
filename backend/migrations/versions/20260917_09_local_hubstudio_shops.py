"""区分妙手跨境店与 HubStudio 本土店

Revision ID: 20260917_09
Revises: 20260917_08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_09"
down_revision: Union[str, None] = "20260917_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 所有历史店铺来自妙手同步，默认归入跨境店；不迁移或删除现有数据。
    with op.batch_alter_table("shops") as batch:
        batch.add_column(sa.Column("shop_type", sa.String(20), nullable=False, server_default="cross_border"))
        batch.create_index("ix_shops_shop_type", ["shop_type"])


def downgrade() -> None:
    with op.batch_alter_table("shops") as batch:
        batch.drop_index("ix_shops_shop_type")
        batch.drop_column("shop_type")
