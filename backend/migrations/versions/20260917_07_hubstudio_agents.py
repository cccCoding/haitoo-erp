"""新增 HubStudio 本地执行器及上品任务

Revision ID: 20260917_07
Revises: 20260916_06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260917_07"
down_revision: Union[str, None] = "20260916_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("hubstudio_app_id", sa.String(255)))
        batch.add_column(sa.Column("hubstudio_secret_encrypted", sa.Text()))
        batch.add_column(sa.Column("hubstudio_group_code", sa.String(120)))
    with op.batch_alter_table("shops") as batch:
        batch.add_column(sa.Column("hubstudio_container_code", sa.String(120)))
        batch.add_column(sa.Column("hub_agent_id", sa.Integer()))
        batch.create_index("ix_shops_hub_agent_id", ["hub_agent_id"])
    op.create_table("hub_agents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("last_seen_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("company_id", "name", name="uq_hub_agents_company_name"),
        sa.UniqueConstraint("token_hash"))
    op.create_index("ix_hub_agents_company_id", "hub_agents", ["company_id"])
    op.create_index("ix_hub_agents_user_id", "hub_agents", ["user_id"])
    op.create_table("hub_upload_tasks",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False), sa.Column("agent_id", sa.Integer(), nullable=False), sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("draft_ids", sa.JSON(), nullable=False), sa.Column("export_filename", sa.String(255), nullable=False), sa.Column("export_blob", sa.LargeBinary(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("failure_reason", sa.String(500)), sa.Column("logs", sa.JSON(), nullable=False), sa.Column("claim_token", sa.String(64)),
        sa.Column("claimed_at", sa.DateTime()), sa.Column("submitted_at", sa.DateTime()), sa.Column("completed_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_hub_upload_tasks_company_id", "hub_upload_tasks", ["company_id"])
    op.create_index("ix_hub_upload_tasks_shop_id", "hub_upload_tasks", ["shop_id"])
    op.create_index("ix_hub_upload_tasks_agent_id", "hub_upload_tasks", ["agent_id"])
    op.create_index("ix_hub_upload_tasks_agent_status", "hub_upload_tasks", ["agent_id", "status", "created_at"])
    op.create_index("ix_hub_upload_tasks_shop_status", "hub_upload_tasks", ["shop_id", "status"])


def downgrade() -> None:
    op.drop_table("hub_upload_tasks"); op.drop_table("hub_agents")
    with op.batch_alter_table("shops") as batch:
        batch.drop_index("ix_shops_hub_agent_id"); batch.drop_column("hub_agent_id"); batch.drop_column("hubstudio_container_code")
    with op.batch_alter_table("companies") as batch:
        batch.drop_column("hubstudio_group_code"); batch.drop_column("hubstudio_secret_encrypted"); batch.drop_column("hubstudio_app_id")
