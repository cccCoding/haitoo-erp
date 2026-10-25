"""独立财务店铺、累计账单和核算设置。"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_45"
down_revision = "20261025_44"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("finance_shops", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "name", name="uq_finance_shop_name"))
    op.create_index("ix_finance_shops_company_id", "finance_shops", ["company_id"])
    op.create_table("finance_orders", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(120), nullable=False), sa.Column("paid_at", sa.DateTime()),
        sa.UniqueConstraint("shop_id", "order_number", name="uq_finance_order"))
    op.create_index("ix_finance_order_scope_time", "finance_orders", ["company_id", "shop_id", "paid_at"])
    op.create_table("finance_bills", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False), sa.Column("settlement_id", sa.String(120), nullable=False),
        sa.Column("sku_id", sa.String(120), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("settlement", sa.Numeric(24, 6), nullable=False), sa.Column("revenue", sa.Numeric(24, 6), nullable=False),
        sa.UniqueConstraint("order_id", "settlement_id", "sku_id", name="uq_finance_bill"))
    op.create_index("ix_finance_bills_order_id", "finance_bills", ["order_id"])
    op.create_table("finance_erp_items", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False), sa.Column("platform_sku", sa.String(120), nullable=False),
        sa.Column("base_sku", sa.String(120), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("order_id", "platform_sku", name="uq_finance_erp_item"))
    op.create_index("ix_finance_erp_items_order_id", "finance_erp_items", ["order_id"])
    op.create_index("ix_finance_erp_items_base_sku", "finance_erp_items", ["base_sku"])
    op.create_table("finance_sku_mappings", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("base_sku", sa.String(120), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("company_id", "base_sku", name="uq_finance_sku_mapping"))
    op.create_index("ix_finance_sku_mappings_company_id", "finance_sku_mappings", ["company_id"])
    op.create_table("finance_template_costs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("company_id", "template_id", name="uq_finance_template_cost"))
    op.create_index("ix_finance_template_costs_company_id", "finance_template_costs", ["company_id"])
    op.create_table("finance_exchange_rates", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.UniqueConstraint("shop_id", "currency", name="uq_finance_exchange_rate"))
    op.create_index("ix_finance_exchange_rates_shop_id", "finance_exchange_rates", ["shop_id"])
    op.create_table("finance_imports", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False), sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_finance_imports_company_id", "finance_imports", ["company_id"])
    op.create_index("ix_finance_imports_shop_id", "finance_imports", ["shop_id"])


def downgrade():
    for table in ("finance_imports", "finance_exchange_rates", "finance_template_costs", "finance_sku_mappings",
                  "finance_erp_items", "finance_bills", "finance_orders", "finance_shops"):
        op.drop_table(table)
