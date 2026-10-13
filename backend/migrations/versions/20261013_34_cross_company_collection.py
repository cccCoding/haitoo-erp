"""采集授权、批次及来源快照。"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_34"
down_revision = "20261011_33"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("companies", sa.Column("cross_company_collect_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("cross_company_collection_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "request_key", name="uq_collection_company_request"))
    op.create_index("ix_cross_company_collection_batches_company_id", "cross_company_collection_batches", ["company_id"])
    op.create_table("cross_company_collection_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("material_asset_id", sa.Integer(), nullable=False),
        sa.Column("source_company_id", sa.Integer(), nullable=False),
        sa.Column("source_company_name", sa.String(120), nullable=False),
        sa.Column("source_library", sa.String(12), nullable=False),
        sa.Column("source_record_id", sa.Integer(), nullable=False),
        sa.Column("source_sku", sa.String(120), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_name", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    for column in ("batch_id", "company_id", "material_asset_id"):
        op.create_index(f"ix_cross_company_collection_items_{column}", "cross_company_collection_items", [column])
    op.create_table("cross_company_collection_permission_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column("previous_enabled", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_cross_company_collection_permission_logs_company_id", "cross_company_collection_permission_logs", ["company_id"])


def downgrade():
    for table in ("cross_company_collection_permission_logs", "cross_company_collection_items", "cross_company_collection_batches"):
        op.drop_table(table)
    op.drop_column("companies", "cross_company_collect_enabled")
