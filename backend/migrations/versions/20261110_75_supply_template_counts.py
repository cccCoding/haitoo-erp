"""货盘模板素材数量快照，由后台首次回填。"""
from alembic import op
import sqlalchemy as sa

revision = "20261110_75"
down_revision = "20261108_74"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("supply_template_counts",
        sa.Column("company_id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), primary_key=True),
        sa.Column("material_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("supply_user_exhausted_counts",
        sa.Column("company_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), primary_key=True),
        sa.Column("exhausted_count", sa.Integer(), nullable=False))
    op.create_index("ix_material_assets_supply_template", "material_assets",
        ["company_id", "supply_listed", "template_id"])


def downgrade():
    op.drop_index("ix_material_assets_supply_template", table_name="material_assets")
    op.drop_table("supply_user_exhausted_counts")
    op.drop_table("supply_template_counts")
