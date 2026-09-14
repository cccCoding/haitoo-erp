"""商品草稿制作流程

Revision ID: 20260914_05
Revises: 20260912_04
Create Date: 2026-09-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260914_05"
down_revision: Union[str, None] = "20260912_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    draft_columns = {item["name"] for item in sa.inspect(connection).get_columns("product_drafts")}
    task_columns = {item["name"] for item in sa.inspect(connection).get_columns("pod_tasks")}
    if "workflow_stage" not in draft_columns:
        op.add_column("product_drafts", sa.Column("workflow_stage", sa.String(length=30), nullable=False, server_default="carousel_pending"))
        op.create_index("ix_product_drafts_workflow_stage", "product_drafts", ["workflow_stage"])
    if "draft_id" not in task_columns:
        op.add_column("pod_tasks", sa.Column("draft_id", sa.Integer(), nullable=True))
        op.create_index("ix_pod_tasks_draft_id", "pod_tasks", ["draft_id"])
    if "failure_ignored" not in task_columns:
        op.add_column("pod_tasks", sa.Column("failure_ignored", sa.Boolean(), nullable=False, server_default=sa.false()))

    # 兼容历史任务：draft_id 原先存放在 JSON parameters 中。
    dialect = connection.dialect.name
    if dialect == "mysql":
        connection.execute(sa.text("UPDATE pod_tasks SET draft_id = CAST(JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.draft_id')) AS UNSIGNED) WHERE draft_id IS NULL AND JSON_EXTRACT(parameters, '$.draft_id') IS NOT NULL"))
    elif dialect == "sqlite":
        connection.execute(sa.text("UPDATE pod_tasks SET draft_id = CAST(json_extract(parameters, '$.draft_id') AS INTEGER) WHERE draft_id IS NULL AND json_extract(parameters, '$.draft_id') IS NOT NULL"))

    # 已发布优先；其余按可可靠推断的图片状态进入新的工作队列。
    connection.execute(sa.text("UPDATE product_drafts SET workflow_stage = CASE WHEN tiktok_collect_box_id IS NOT NULL THEN 'published' WHEN image_urls IS NOT NULL AND image_urls <> '[]' THEN 'ready_to_publish' WHEN carousel_items IS NOT NULL AND carousel_items <> '[]' THEN 'main_image_pending' ELSE 'carousel_pending' END"))


def downgrade() -> None:
    op.drop_column("pod_tasks", "failure_ignored")
    op.drop_index("ix_pod_tasks_draft_id", table_name="pod_tasks")
    op.drop_column("pod_tasks", "draft_id")
    op.drop_index("ix_product_drafts_workflow_stage", table_name="product_drafts")
    op.drop_column("product_drafts", "workflow_stage")
