"""平台统一连接器发布仓；旧公司插件与发布记录原样保留。"""
from alembic import op
import sqlalchemy as sa

revision = "20261111_77"
down_revision = "20261110_76"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("connector_releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("arch", sa.String(16), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("upload_nonce", sa.String(36), nullable=True),
        sa.Column("test_agent_ids", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("version", "platform", "arch", name="uq_connector_release_target"))


def downgrade():
    op.drop_table("connector_releases")
