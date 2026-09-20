"""移除历史妙手采集箱来源字段

Revision ID: 20260920_15
Revises: 20260920_14
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260920_15"
down_revision: Union[str, None] = "20260920_14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("miaoshou_collect_box_items")}
    for name in ("source_list", "owner_sub_account_alias_name"):
        if name in columns:
            op.drop_column("miaoshou_collect_box_items", name)


def downgrade() -> None:
    # 来源字段按最新产品要求永久移除，不恢复历史来源数据。
    pass
