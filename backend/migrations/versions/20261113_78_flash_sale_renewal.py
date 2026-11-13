"""秒杀活动候选及续期台账。"""
from alembic import op
import sqlalchemy as sa

revision = "20261113_78"
down_revision = "20261111_77"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("matrix_flash_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("dismissed_by", sa.JSON(), nullable=False),
        sa.UniqueConstraint("company_id", "environment_id", "external_id", name="uq_matrix_flash_activity"))
    for column in ("company_id", "environment_id", "ends_at", "source_item_id"):
        op.create_index(f"ix_matrix_flash_activities_{column}", "matrix_flash_activities", [column])
    op.create_table("matrix_flash_renewals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("new_activity_id", sa.String(120), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("terminated", sa.Boolean(), nullable=False),
        sa.Column("evidence", sa.String(1000), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("activity_id", name="uq_matrix_flash_renewal"))
    for column in ("company_id", "item_id"):
        op.create_index(f"ix_matrix_flash_renewals_{column}", "matrix_flash_renewals", [column])


def downgrade():
    op.drop_table("matrix_flash_renewals")
    op.drop_table("matrix_flash_activities")
