"""Hub XLSX 存入私有 R2，数据库仅保存链接与有效期。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMBLOB

revision = "20261007_30"
down_revision = "20261007_29"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.alter_column("export_blob", existing_type=sa.LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb"), existing_nullable=False, nullable=True)
        batch.add_column(sa.Column("export_url", sa.String(1024), nullable=True))
        batch.add_column(sa.Column("export_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("export_size", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("export_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("export_deleted_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_hub_upload_tasks_export_expires_at", ["export_expires_at"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM hub_upload_tasks WHERE export_blob IS NULL")):
        raise RuntimeError("存在 R2 文件任务，不能安全回退到数据库文件存储")
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.drop_index("ix_hub_upload_tasks_export_expires_at")
        for name in ("export_url", "export_sha256", "export_size", "export_expires_at", "export_deleted_at"):
            batch.drop_column(name)
        batch.alter_column("export_blob", existing_type=sa.LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb"), existing_nullable=True, nullable=False)
