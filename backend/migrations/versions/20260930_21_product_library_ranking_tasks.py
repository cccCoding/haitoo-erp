"""产品库手动统计任务状态

Revision ID: 20260930_21
Revises: 20260930_20
"""
from alembic import op
import sqlalchemy as sa

revision = "20260930_21"
down_revision = "20260930_20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_library_ranking_tasks",
        sa.Column("company_id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("task_id", name="uq_product_library_ranking_task_id"),
    )
    op.create_index("ix_product_library_ranking_tasks_status", "product_library_ranking_tasks", ["status"])


def downgrade():
    op.drop_index("ix_product_library_ranking_tasks_status", table_name="product_library_ranking_tasks")
    op.drop_table("product_library_ranking_tasks")
