"""Grsai 候选存储、无哈希正式文件和持久化复制队列。"""
from alembic import op
import sqlalchemy as sa

revision = "20261104_62"
down_revision = "20261103_61"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("companies", sa.Column("grsai_storage_id", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("grsai_storage_mode", sa.String(16), nullable=False, server_default="inherit"))
    op.add_column("users", sa.Column("grsai_storage_id", sa.String(120), nullable=True))
    op.add_column("pod_tasks", sa.Column("storage_context", sa.JSON(), nullable=True))
    op.add_column("pod_tasks", sa.Column("provider_result_urls", sa.JSON(), nullable=True))
    with op.batch_alter_table("image_files") as batch:
        batch.alter_column("sha256", existing_type=sa.String(64), nullable=True)
        batch.add_column(sa.Column("source_type", sa.String(30), nullable=False, server_default="content"))
        batch.add_column(sa.Column("source_ref", sa.String(120), nullable=True))
        batch.add_column(sa.Column("validation_method", sa.String(30), nullable=False, server_default="full_decode"))
        batch.create_unique_constraint("uq_image_file_source", ["company_id", "source_type", "source_ref"])
    op.create_table("ai_image_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False, index=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("bucket", sa.String(120), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("etag", sa.String(160), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(40), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("image_file_id", sa.Integer(), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(32), nullable=True),
        sa.Column("lease_epoch", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("task_id", "run_id", "url_hash", name="uq_ai_candidate_result"))
    op.create_index("ix_ai_candidate_queue", "ai_image_candidates", ["state", "available_at", "lease_expires_at"])
    op.create_index("ix_ai_candidate_task", "ai_image_candidates", ["company_id", "task_id", "run_id"])
    op.create_index("ix_ai_candidate_address", "ai_image_candidates", ["company_id", "url_hash"])
    op.create_table("ai_image_preparations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "user_id", "request_key", name="uq_ai_preparation_request"))
    op.create_table("ai_image_preparation_items",
        sa.Column("job_id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), primary_key=True, index=True))


def downgrade():
    # 无哈希记录无法恢复到旧约束；拒绝会丢失正式图片索引的降级。
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM image_files WHERE sha256 IS NULL")).scalar():
        raise RuntimeError("存在无哈希正式图片，请关闭新提交直存，勿降级到旧版文件索引")
    for table in ("ai_image_preparation_items", "ai_image_preparations", "ai_image_candidates"):
        op.drop_table(table)
    with op.batch_alter_table("image_files") as batch:
        batch.drop_constraint("uq_image_file_source", type_="unique")
        for name in ("source_type", "source_ref", "validation_method"):
            batch.drop_column(name)
        batch.alter_column("sha256", existing_type=sa.String(64), nullable=False)
    op.drop_column("pod_tasks", "provider_result_urls")
    op.drop_column("pod_tasks", "storage_context")
    op.drop_column("users", "grsai_storage_id")
    op.drop_column("users", "grsai_storage_mode")
    op.drop_column("companies", "grsai_storage_id")
