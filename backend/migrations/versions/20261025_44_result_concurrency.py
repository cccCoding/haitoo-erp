"""结果查询并发配置，保留已有任务与毫秒间隔。"""
from alembic import op
import sqlalchemy as sa


revision = "20261025_44"
down_revision = "20261020_43"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("task_queue_settings", sa.Column("result_concurrency", sa.Integer(),
                                                nullable=False, server_default="5"))


def downgrade():
    with op.batch_alter_table("task_queue_settings") as batch:
        batch.drop_column("result_concurrency")
