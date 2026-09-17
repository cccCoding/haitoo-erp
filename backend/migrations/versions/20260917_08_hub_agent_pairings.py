"""新增 Hub 执行器网页登录配对

Revision ID: 20260917_08
Revises: 20260917_07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260917_08"
down_revision: Union[str, None] = "20260917_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("hub_agent_pairings",
        sa.Column("code_hash", sa.String(64), primary_key=True), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False), sa.Column("agent_id", sa.Integer()),
        sa.Column("token_encrypted", sa.Text()), sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_hub_agent_pairings_agent_id", "hub_agent_pairings", ["agent_id"])
    op.create_index("ix_hub_agent_pairings_expires_at", "hub_agent_pairings", ["expires_at"])


def downgrade() -> None:
    op.drop_table("hub_agent_pairings")
