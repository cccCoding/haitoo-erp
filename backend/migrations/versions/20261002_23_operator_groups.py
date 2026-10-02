"""新增运营组和运营组长角色。

Revision ID: 20261002_23
Revises: 20260930_22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261002_23"
down_revision: Union[str, None] = "20260930_22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


old_roles = mysql.ENUM("SUPER_ADMIN", "COMPANY_ADMIN", "MEMBER")
new_roles = mysql.ENUM("SUPER_ADMIN", "COMPANY_ADMIN", "MEMBER", "TEAM_LEADER")


def upgrade() -> None:
    op.create_table(
        "operator_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("leader_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "name", name="uq_operator_groups_company_name"),
    )
    op.create_index("ix_operator_groups_company_id", "operator_groups", ["company_id"])
    if op.get_bind().dialect.name in {"mysql", "mariadb"}:
        op.alter_column("users", "role", existing_type=old_roles, type_=new_roles, existing_nullable=False)
    op.add_column("users", sa.Column("group_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_group_id", "users", ["group_id"])


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'MEMBER' WHERE role = 'TEAM_LEADER'")
    op.drop_index("ix_users_group_id", table_name="users")
    op.drop_column("users", "group_id")
    if op.get_bind().dialect.name in {"mysql", "mariadb"}:
        op.alter_column("users", "role", existing_type=new_roles, type_=old_roles, existing_nullable=False)
    op.drop_index("ix_operator_groups_company_id", table_name="operator_groups")
    op.drop_table("operator_groups")
