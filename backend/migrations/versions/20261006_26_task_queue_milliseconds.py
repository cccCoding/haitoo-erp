"""任务提交和取结果间隔改为毫秒，保留现有等待时长。

Revision ID: 20261006_26
Revises: 20261005_25
"""
from alembic import op
import sqlalchemy as sa

revision = "20261006_26"
down_revision = "20261005_25"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task_queue_settings") as batch:
        for kind in ("submit", "result"):
            batch.alter_column(f"{kind}_interval_seconds", new_column_name=f"{kind}_interval_ms",
                               existing_type=sa.Integer(), existing_nullable=False)
    op.execute(sa.text("UPDATE task_queue_settings SET submit_interval_ms = submit_interval_ms * 1000, "
                       "result_interval_ms = result_interval_ms * 1000"))


def downgrade():
    # 旧版只支持整数秒；不足一秒时恢复为一秒。
    table = sa.table("task_queue_settings", sa.column("submit_interval_ms"), sa.column("result_interval_ms"))
    op.execute(table.update().values(**{
        f"{kind}_interval_ms": sa.case(
            (table.c[f"{kind}_interval_ms"] < 1000, 1),
            else_=sa.cast(table.c[f"{kind}_interval_ms"] / 1000, sa.Integer()),
        ) for kind in ("submit", "result")
    }))
    with op.batch_alter_table("task_queue_settings") as batch:
        for kind in ("submit", "result"):
            batch.alter_column(f"{kind}_interval_ms", new_column_name=f"{kind}_interval_seconds",
                               existing_type=sa.Integer(), existing_nullable=False)
