"""删除公开货盘撤回专用字段。"""

from alembic import op
import sqlalchemy as sa


revision = "20261016_38"
down_revision = "20261014_37"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("supply_jobs", "download_revoked")


def downgrade():
    op.add_column("supply_jobs", sa.Column("download_revoked", sa.Boolean(), nullable=False,
                                         server_default=sa.text("0")))
