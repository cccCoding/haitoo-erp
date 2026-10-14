"""记录素材上架历史，区分从未上架与已下架素材。"""

from alembic import op
import sqlalchemy as sa


revision = "20261016_39"
down_revision = "20261016_38"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("material_assets", sa.Column("supply_listed_at", sa.DateTime(), nullable=True))
    assets = sa.table("material_assets", sa.column("id", sa.Integer()),
        sa.column("company_id", sa.Integer()), sa.column("supply_listed", sa.Boolean()),
        sa.column("supply_listed_at", sa.DateTime()))
    audits = sa.table("supply_audits", sa.column("company_id", sa.Integer()),
        sa.column("target_id", sa.Integer()), sa.column("target_type", sa.String()),
        sa.column("action", sa.String()), sa.column("details", sa.JSON()),
        sa.column("created_at", sa.DateTime()))
    first_listing = sa.select(sa.func.min(audits.c.created_at)).where(
        audits.c.company_id == assets.c.company_id, audits.c.target_id == assets.c.id,
        audits.c.target_type == "material", audits.c.action == "material_listing",
        audits.c.details["listed"].as_boolean().is_(True)).scalar_subquery()
    op.execute(assets.update().values(supply_listed_at=first_listing))
    op.execute(assets.update().where(assets.c.supply_listed.is_(True),
        assets.c.supply_listed_at.is_(None)).values(supply_listed_at=sa.func.current_timestamp()))
    op.create_index("ix_material_assets_supply_listing", "material_assets",
        ["company_id", "supply_listed", "supply_listed_at"])


def downgrade():
    op.drop_index("ix_material_assets_supply_listing", table_name="material_assets")
    op.drop_column("material_assets", "supply_listed_at")
