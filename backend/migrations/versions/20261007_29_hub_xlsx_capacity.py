"""扩容 Hub 任务固定 XLSX，修复 MySQL 普通 BLOB 的 64 KB 限制。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BLOB, MEDIUMBLOB

revision = "20261007_29"
down_revision = "20261007_28"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name in {"mysql", "mariadb"}:
        op.alter_column("hub_upload_tasks", "export_blob", existing_type=BLOB(),
                        type_=MEDIUMBLOB(), existing_nullable=False)


def downgrade():
    db = op.get_bind()
    if db.dialect.name in {"mysql", "mariadb"}:
        if db.scalar(sa.text("SELECT COUNT(*) FROM hub_upload_tasks WHERE OCTET_LENGTH(export_blob) > 65535")):
            raise RuntimeError("存在超过 64 KB 的任务 XLSX，不能安全缩小字段")
        op.alter_column("hub_upload_tasks", "export_blob", existing_type=MEDIUMBLOB(),
                        type_=BLOB(), existing_nullable=False)
