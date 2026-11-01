"""按店铺、日期、币种保存广告成本。"""
from alembic import op
import sqlalchemy as sa

revision = "20261031_57"
down_revision = "20261031_56"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finance_ad_costs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("cost_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(24, 6), nullable=False),
        sa.UniqueConstraint("shop_id", "cost_date", "currency", name="uq_finance_ad_cost"))
    op.create_index("ix_finance_ad_cost_scope_date", "finance_ad_costs", ["company_id", "shop_id", "cost_date"])


def downgrade():
    op.drop_table("finance_ad_costs")
