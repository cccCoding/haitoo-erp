"""素材 SKU 侵权标记，历史素材默认不侵权。"""
from alembic import op
import sqlalchemy as sa

revision = "20261020_41"
down_revision = "20261017_40"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("material_assets", sa.Column("is_infringing", sa.Boolean(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("material_assets", "is_infringing")
