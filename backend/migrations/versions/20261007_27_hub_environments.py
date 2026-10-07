"""HubStudio 环境同步、账号任务及执行租约；保留历史店铺和任务。

Revision ID: 20261007_27
Revises: 20261006_26
"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "20261007_27"
down_revision = "20261006_26"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("hub_environments",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("container_code", sa.String(120), nullable=False), sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metadata_fields", sa.JSON(), nullable=False), sa.Column("auto_upload_enabled", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime()), sa.UniqueConstraint("company_id", "container_code", name="uq_hub_environment_identity"))
    op.create_index("ix_hub_environments_company_id", "hub_environments", ["company_id"])
    op.create_table("hub_environment_access",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False), sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("agent_id", "environment_id", name="uq_hub_environment_access"))
    for column in ("company_id", "user_id", "agent_id", "environment_id"):
        op.create_index(f"ix_hub_environment_access_{column}", "hub_environment_access", [column])
    op.create_table("hub_environment_locks",
        sa.Column("environment_id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("task_id", sa.Integer()))
    op.create_index("ix_hub_environment_locks_company_id", "hub_environment_locks", ["company_id"])
    op.create_table("hub_upload_attempts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer()), sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("logs", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("completed_at", sa.DateTime()))
    op.create_index("ix_hub_upload_attempts_task_id", "hub_upload_attempts", ["task_id"])
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.alter_column("shop_id", existing_type=sa.Integer(), existing_nullable=False, nullable=True)
        batch.alter_column("agent_id", existing_type=sa.Integer(), existing_nullable=False, nullable=True)
        for name, kind in (("environment_id", sa.Integer()), ("environment_name", sa.String(255)),
                           ("lease_expires_at", sa.DateTime()), ("attempt_id", sa.Integer()),
                           ("resolved_by", sa.Integer()), ("resolved_at", sa.DateTime())):
            batch.add_column(sa.Column(name, kind))
        batch.create_index("ix_hub_upload_tasks_environment_id", ["environment_id"])
        batch.create_index("ix_hub_upload_tasks_owner_queue", ["company_id", "created_by", "status", "environment_id"])
    connection = op.get_bind()
    environments = sa.table("hub_environments", sa.column("id"), sa.column("company_id"), sa.column("container_code"), sa.column("name"), sa.column("metadata_fields", sa.JSON()), sa.column("auto_upload_enabled"))
    guards = sa.table("hub_environment_locks", sa.column("environment_id"), sa.column("company_id"), sa.column("task_id"))
    tasks = sa.table("hub_upload_tasks", sa.column("id"), sa.column("environment_id"), sa.column("environment_name"), sa.column("status"), sa.column("stage"), sa.column("failure_reason"), sa.column("claim_token"))
    identities = {}
    shops = connection.execute(sa.text("SELECT id, company_id, hubstudio_container_code, name FROM shops WHERE hubstudio_container_code IS NOT NULL")).mappings().all()
    for shop in shops:
        code = shop["hubstudio_container_code"].strip()
        if not code:
            continue
        identity = (shop["company_id"], code)
        if identity not in identities:
            result = connection.execute(environments.insert().values(company_id=identity[0], container_code=code, name=shop["name"], metadata_fields={}, auto_upload_enabled=False))
            env_id = result.lastrowid
            identities[identity] = env_id
            connection.execute(guards.insert().values(environment_id=env_id, company_id=identity[0]))
        env_id = identities[identity]
        connection.execute(sa.text("UPDATE hub_upload_tasks SET environment_id = :env_id, environment_name = :name WHERE shop_id = :shop_id"), {"env_id": env_id, "name": shop["name"], "shop_id": shop["id"]})
    # 不允许旧执行器继续报告；结果未知的历史任务必须人工核对。
    connection.execute(tasks.update().where(tasks.c.status == "queued").values(status="awaiting_attention", stage="upgrade_review", failure_reason="执行器升级：请核对平台后重新排队或取消"))
    connection.execute(tasks.update().where(tasks.c.status.in_(["running", "awaiting_attention"])).values(claim_token=None))
    connection.execute(sa.text("UPDATE hub_upload_tasks SET lease_expires_at = :now WHERE status = 'running'"), {"now": datetime.utcnow()})
    active = connection.execute(sa.text("SELECT id, company_id, environment_id FROM hub_upload_tasks WHERE status IN ('running', 'awaiting_attention') AND environment_id IS NOT NULL ORDER BY id")).mappings().all()
    for task in active:
        connection.execute(guards.update().where(guards.c.environment_id == task["environment_id"], guards.c.task_id.is_(None)).values(task_id=task["id"]))


def downgrade():
    # 旧协议无法表示环境任务，不自动丢弃新任务或伪造店铺关联。
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM hub_upload_tasks WHERE shop_id IS NULL OR agent_id IS NULL")):
        raise RuntimeError("存在新环境任务，不能安全降级；请保留当前版本")
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.drop_index("ix_hub_upload_tasks_environment_id")
        batch.drop_index("ix_hub_upload_tasks_owner_queue")
        for name in ("environment_id", "environment_name", "lease_expires_at", "attempt_id", "resolved_by", "resolved_at"):
            batch.drop_column(name)
        batch.alter_column("shop_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("agent_id", existing_type=sa.Integer(), nullable=False)
    for table in ("hub_upload_attempts", "hub_environment_locks", "hub_environment_access", "hub_environments"):
        op.drop_table(table)
