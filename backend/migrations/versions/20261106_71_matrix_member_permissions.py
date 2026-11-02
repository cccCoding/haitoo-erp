"""矩阵成员授权；保留现有连接器使用者权限，新成员默认未授权。"""
from alembic import op
import sqlalchemy as sa

revision = "20261106_71"
down_revision = "20261106_70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("matrix_member_permissions",
        sa.Column("user_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("collect_enabled", sa.Boolean(), nullable=False),
        sa.Column("listing_enabled", sa.Boolean(), nullable=False),
        sa.Column("view_scope", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_index("ix_matrix_member_permissions_company_id", "matrix_member_permissions", ["company_id"])
    op.execute(sa.text("""INSERT INTO matrix_member_permissions
        (user_id, company_id, enabled, collect_enabled, listing_enabled, view_scope, revision, updated_at)
        SELECT u.id, u.company_id, 1, 1, 1, 'own', 1, CURRENT_TIMESTAMP
        FROM users u WHERE u.company_id IS NOT NULL AND u.role IN ('MEMBER', 'TEAM_LEADER')
        AND (EXISTS (SELECT 1 FROM hub_agents a WHERE a.user_id=u.id AND a.company_id=u.company_id)
             OR EXISTS (SELECT 1 FROM matrix_plans p WHERE p.owner_id=u.id AND p.company_id=u.company_id))"""))


def downgrade():
    op.drop_index("ix_matrix_member_permissions_company_id", table_name="matrix_member_permissions")
    op.drop_table("matrix_member_permissions")
