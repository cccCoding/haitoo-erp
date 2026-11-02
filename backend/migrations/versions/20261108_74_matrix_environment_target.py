"""矩阵结果按环境归档，不再要求平台店铺身份。"""
from alembic import op
import sqlalchemy as sa

revision = "20261108_74"
down_revision = "20261108_73"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("matrix_shops") as batch:
        batch.alter_column("external_id", existing_type=sa.String(120), nullable=True)
        batch.add_column(sa.Column("environment_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_matrix_shop_environment", ["company_id", "environment_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM matrix_shops WHERE external_id IS NULL")).scalar():
        raise RuntimeError("存在按环境归档的矩阵数据，不能回退为强制平台店铺ID的结构")
    with op.batch_alter_table("matrix_shops") as batch:
        batch.drop_constraint("uq_matrix_shop_environment", type_="unique")
        batch.drop_column("environment_id")
        batch.alter_column("external_id", existing_type=sa.String(120), nullable=False)
