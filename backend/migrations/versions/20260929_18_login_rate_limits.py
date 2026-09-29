"""为登录接口增加共享限流计数

Revision ID: 20260929_18
Revises: 20260924_17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME


revision: str = "20260929_18"
down_revision: Union[str, None] = "20260924_17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime().with_variant(MYSQL_DATETIME(fsp=6), "mysql"), nullable=False),
    )
    op.create_index("ix_login_rate_limits_expires_at", "login_rate_limits", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_login_rate_limits_expires_at", table_name="login_rate_limits")
    op.drop_table("login_rate_limits")
