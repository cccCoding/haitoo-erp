"""类目库区分站点，历史类目归为马来西亚。"""
from alembic import op
import sqlalchemy as sa

revision = "20261110_76"
down_revision = "20261110_75"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tiktok_category_catalogs", sa.Column("site", sa.String(2), nullable=False, server_default="MY"))


def downgrade():
    op.drop_column("tiktok_category_catalogs", "site")
