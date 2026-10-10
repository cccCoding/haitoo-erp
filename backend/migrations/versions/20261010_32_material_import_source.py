"""记录导入素材来源，历史素材保持原有来源识别方式。"""
from alembic import op
import sqlalchemy as sa

revision = "20261010_32"
down_revision = "20261008_31"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("material_assets") as batch:
        batch.add_column(sa.Column("source_type", sa.String(20), nullable=True))


def downgrade():
    with op.batch_alter_table("material_assets") as batch:
        batch.drop_column("source_type")
