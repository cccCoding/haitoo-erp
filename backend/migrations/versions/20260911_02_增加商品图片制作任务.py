"""增加商品图片制作任务

Revision ID: 20260911_02
Revises: 20260911_01
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260911_02"
down_revision: Union[str, None] = "20260911_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    task_columns = {column["name"] for column in sa.inspect(connection).get_columns("pod_tasks")}
    if "task_type" not in task_columns:
        op.add_column("pod_tasks", sa.Column("task_type", sa.String(length=30), nullable=True))
    op.execute("UPDATE pod_tasks SET task_type = 'sku_image' WHERE task_type IS NULL")
    op.alter_column("pod_tasks", "task_type", existing_type=sa.String(length=30), nullable=False)
    task_indexes = {index["name"] for index in sa.inspect(connection).get_indexes("pod_tasks")}
    if "ix_pod_tasks_task_type" not in task_indexes:
        op.create_index("ix_pod_tasks_task_type", "pod_tasks", ["task_type"], unique=False)

    draft_columns = {column["name"] for column in sa.inspect(connection).get_columns("product_drafts")}
    if "carousel_items" not in draft_columns:
        op.add_column("product_drafts", sa.Column("carousel_items", sa.JSON(), nullable=True))
    if connection.dialect.name in {"mysql", "mariadb"}:
        op.execute("UPDATE product_drafts SET carousel_items = JSON_ARRAY() WHERE carousel_items IS NULL")
    else:
        op.execute("UPDATE product_drafts SET carousel_items = '[]' WHERE carousel_items IS NULL")
    op.alter_column("product_drafts", "carousel_items", existing_type=sa.JSON(), nullable=False)
    if "main_image_url" not in draft_columns:
        op.add_column("product_drafts", sa.Column("main_image_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("product_drafts", "main_image_url")
    op.drop_column("product_drafts", "carousel_items")
    op.drop_index("ix_pod_tasks_task_type", table_name="pod_tasks")
    op.drop_column("pod_tasks", "task_type")
