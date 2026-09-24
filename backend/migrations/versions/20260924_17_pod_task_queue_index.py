"""为印花任务队列增加状态顺序索引

Revision ID: 20260924_17
Revises: 20260924_16
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260924_17"
down_revision: Union[str, None] = "20260924_16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ix_pod_tasks_status_created_at_id"


def upgrade() -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("pod_tasks")}
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, "pod_tasks", ["status", "created_at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="pod_tasks")
