"""环境只在本机同步与选择，数据库保留任务执行目标和运行协调锁。"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "20261007_28"
down_revision = "20261007_27"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("hub_runtime_locks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("container_code", sa.String(120), nullable=False),
        sa.Column("task_id", sa.Integer()),
        sa.UniqueConstraint("company_id", "container_code", name="uq_hub_runtime_identity"))
    op.create_index("ix_hub_runtime_locks_company_id", "hub_runtime_locks", ["company_id"])
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.add_column(sa.Column("container_code", sa.String(120)))
    with op.batch_alter_table("hub_upload_attempts") as batch:
        batch.add_column(sa.Column("container_code", sa.String(120)))
        batch.add_column(sa.Column("environment_name", sa.String(255)))
    db = op.get_bind()
    # 历史环境表不删除、不再同步写入；只将已有任务的执行目标保存为历史记录。
    rows = db.execute(sa.text("SELECT t.id, e.container_code FROM hub_upload_tasks t JOIN hub_environments e ON t.environment_id=e.id")).mappings().all()
    for row in rows:
        db.execute(sa.text("UPDATE hub_upload_tasks SET container_code=:code WHERE id=:id"), {"code": row["container_code"], "id": row["id"]})
    db.execute(sa.text("UPDATE hub_upload_attempts SET container_code=(SELECT container_code FROM hub_upload_tasks WHERE id=hub_upload_attempts.task_id), environment_name=(SELECT environment_name FROM hub_upload_tasks WHERE id=hub_upload_attempts.task_id)"))
    # 旧运行凭证失效，避免旧客户端和本机选择模式同时提交。
    db.execute(sa.text("UPDATE hub_upload_tasks SET status='awaiting_attention', stage='upgrade_review', failure_reason='执行器升级：请核对原环境的平台结果后重试或取消', claim_token=NULL, lease_expires_at=NULL WHERE status IN ('queued','running')"))
    db.execute(sa.text("UPDATE hub_upload_attempts SET status='awaiting_attention', completed_at=:now WHERE status='running'"), {"now": datetime.utcnow()})
    active = db.execute(sa.text("SELECT id, company_id, container_code FROM hub_upload_tasks WHERE status='awaiting_attention' AND container_code IS NOT NULL ORDER BY id")).mappings().all()
    guards = sa.table("hub_runtime_locks", sa.column("company_id"), sa.column("container_code"), sa.column("task_id"))
    seen = set()
    for task in active:
        identity = (task["company_id"], task["container_code"])
        if identity not in seen:
            db.execute(guards.insert().values(company_id=identity[0], container_code=identity[1], task_id=task["id"]))
            seen.add(identity)


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text("SELECT COUNT(*) FROM hub_upload_tasks WHERE environment_id IS NULL")):
        raise RuntimeError("存在本机选择环境的任务，不能安全降级")
    with op.batch_alter_table("hub_upload_attempts") as batch:
        batch.drop_column("environment_name")
        batch.drop_column("container_code")
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.drop_column("container_code")
    op.drop_table("hub_runtime_locks")
