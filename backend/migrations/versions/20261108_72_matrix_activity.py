"""矩阵环境人工活跃状态。"""
from alembic import op
import sqlalchemy as sa

revision = "20261108_72"
down_revision = "20261106_71"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("matrix_environments", sa.Column("activity_status", sa.String(16), nullable=True))


def downgrade():
    op.drop_column("matrix_environments", "activity_status")
