"""图片文件索引与素材创建幂等；移除图片健康状态。"""
from alembic import op
import sqlalchemy as sa

revision = "20261017_40"
down_revision = "20261016_39"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("image_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False, index=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "sha256", name="uq_image_file_content"))
    op.create_table("image_addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False, index=True),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("image_file_id", sa.Integer(), nullable=False, index=True),
        sa.UniqueConstraint("company_id", "url_hash", name="uq_image_address_url"))
    with op.batch_alter_table("material_assets") as batch:
        batch.add_column(sa.Column("image_file_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("creation_request_key", sa.String(128), nullable=True))
        batch.create_index("ix_material_assets_image_file_id", ["image_file_id"])
        batch.create_unique_constraint("uq_material_creation_request", ["company_id", "creation_request_key"])
    op.drop_table("supply_image_health")


def downgrade():
    op.create_table("supply_image_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False, index=True),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unchecked", index=True),
        sa.Column("check_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("company_id", "url_hash", name="uq_supply_image_health_company_url"))
    with op.batch_alter_table("material_assets") as batch:
        batch.drop_constraint("uq_material_creation_request", type_="unique")
        batch.drop_index("ix_material_assets_image_file_id")
        batch.drop_column("creation_request_key")
        batch.drop_column("image_file_id")
    op.drop_table("image_addresses")
    op.drop_table("image_files")
