"""新增公司公开货盘、外部账号及可恢复生成任务。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20261014_37"
down_revision = "20261013_36"
branch_labels = None
depends_on = None

old_roles = mysql.ENUM("SUPER_ADMIN", "COMPANY_ADMIN", "MEMBER", "TEAM_LEADER")
new_roles = mysql.ENUM("SUPER_ADMIN", "COMPANY_ADMIN", "MEMBER", "TEAM_LEADER", "SUPPLY_USER")


def blob_type():
    return sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql").with_variant(mysql.MEDIUMBLOB(), "mariadb")


def upgrade():
    if op.get_bind().dialect.name in {"mysql", "mariadb"}:
        op.alter_column("users", "role", existing_type=old_roles, type_=new_roles, existing_nullable=False)
    op.add_column("companies", sa.Column("supply_ai_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("supply_ai_model", sa.String(120), nullable=True, server_default="deepseek-chat"))
    op.add_column("users", sa.Column("supply_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("users", sa.Column("supply_agent_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("supply_expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_users_supply_agent_id", "users", ["supply_agent_id"])
    op.create_index("ix_users_supply_expires_at", "users", ["supply_expires_at"])
    op.add_column("product_templates", sa.Column("supply_public", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("product_templates", sa.Column("supply_fallback_title", sa.String(220), nullable=True))
    op.add_column("material_assets", sa.Column("supply_listed", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "supply_agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "name", name="uq_supply_agents_company_name"),
    )
    op.create_index("ix_supply_agents_company_id", "supply_agents", ["company_id"])
    op.create_table(
        "supply_strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_supply_strategies_company_id", "supply_strategies", ["company_id"])
    op.create_index("ix_supply_strategies_user_id", "supply_strategies", ["user_id"])
    op.create_index("ix_supply_strategies_owner", "supply_strategies", ["company_id", "user_id"])
    op.create_table(
        "supply_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(120), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("category_catalog_id", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("category_blob", blob_type(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("export_blob", blob_type(), nullable=True),
        sa.Column("state", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(80), nullable=False, server_default="queued"),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_epoch", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("available_at", sa.DateTime(), nullable=True),
        sa.Column("upload_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_key", sa.String(1024), nullable=True),
        sa.Column("output_sha256", sa.String(64), nullable=True),
        sa.Column("output_size", sa.Integer(), nullable=True),
        sa.Column("output_expires_at", sa.DateTime(), nullable=True),
        sa.Column("output_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("download_revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("company_id", "user_id", "idempotency_key", name="uq_supply_jobs_owner_request"),
    )
    for column in ("company_id", "user_id", "agent_id", "template_id", "category_catalog_id", "output_expires_at"):
        op.create_index(f"ix_supply_jobs_{column}", "supply_jobs", [column])
    op.create_index("ix_supply_jobs_queue", "supply_jobs", ["state", "available_at", "lease_expires_at", "created_at"])
    op.create_index("ix_supply_jobs_company_state", "supply_jobs", ["company_id", "state"])
    op.create_index("ix_supply_jobs_owner_state", "supply_jobs", ["company_id", "user_id", "state"])
    op.create_table(
        "supply_image_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unchecked"),
        sa.Column("check_sequence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("company_id", "url_hash", name="uq_supply_image_health_company_url"),
    )
    op.create_index("ix_supply_image_health_company_id", "supply_image_health", ["company_id"])
    op.create_index("ix_supply_image_health_status", "supply_image_health", ["status"])
    op.create_table(
        "supply_job_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="snapshot"),
        sa.Column("link_index", sa.Integer(), nullable=False, server_default=sa.text("-1")),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("job_id", "material_id", "version_hash", "link_index", name="uq_supply_job_material_version_link"),
    )
    for column in ("company_id", "job_id", "material_id"):
        op.create_index(f"ix_supply_job_materials_{column}", "supply_job_materials", [column])
    op.create_index("ix_supply_job_materials_usage", "supply_job_materials", ["company_id", "material_id", "successful"])
    op.create_table(
        "supply_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_supply_audits_company_id", "supply_audits", ["company_id"])
    op.create_index("ix_supply_audits_user_id", "supply_audits", ["user_id"])
    op.create_index("ix_supply_audits_company_created", "supply_audits", ["company_id", "created_at"])


def downgrade():
    # 保留账号但停用，不能在回退后把外部账号升级成可登录的内部成员。
    op.execute("UPDATE users SET role = 'MEMBER', is_active = 0, token_version = token_version + 1 WHERE role = 'SUPPLY_USER'")
    for table in ("supply_audits", "supply_job_materials", "supply_image_health", "supply_jobs", "supply_strategies", "supply_agents"):
        op.drop_table(table)
    op.drop_column("material_assets", "supply_listed")
    op.drop_column("product_templates", "supply_fallback_title")
    op.drop_column("product_templates", "supply_public")
    op.drop_index("ix_users_supply_expires_at", table_name="users")
    op.drop_index("ix_users_supply_agent_id", table_name="users")
    op.drop_column("users", "supply_expires_at")
    op.drop_column("users", "supply_agent_id")
    op.drop_column("users", "supply_admin")
    op.drop_column("companies", "supply_ai_model")
    op.drop_column("companies", "supply_ai_secret_encrypted")
    if op.get_bind().dialect.name in {"mysql", "mariadb"}:
        op.alter_column("users", "role", existing_type=new_roles, type_=old_roles, existing_nullable=False)
