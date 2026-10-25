"""基础 SKU 成本按店铺隔离，保留现有店铺的核算价格。"""
from alembic import op
import sqlalchemy as sa

revision = "20261026_49"
down_revision = "20261026_48"
branch_labels = None
depends_on = None


def upgrade():
    binary_sku = sa.String(120).with_variant(sa.String(120, collation="utf8mb4_bin"), "mysql", "mariadb")
    op.create_table("finance_shop_sku_costs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("base_sku", binary_sku, nullable=False), sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("shop_id", "base_sku", name="uq_finance_shop_sku_cost"))
    op.create_index("ix_finance_shop_sku_costs_company_id", "finance_shop_sku_costs", ["company_id"])
    op.create_index("ix_finance_shop_sku_costs_shop_id", "finance_shop_sku_costs", ["shop_id"])
    # 仅将已有价格复制到实际使用该 SKU 的店铺；不向未来新店传播。
    # 旧公司级价格表完整留档，运行时不再读取。
    costs = sa.table("finance_sku_costs", sa.column("company_id"), sa.column("base_sku"),
                     sa.column("unit_cost", sa.Numeric(18, 2)))
    items = sa.table("finance_erp_items", sa.column("order_id"), sa.column("base_sku"))
    orders = sa.table("finance_orders", sa.column("id"), sa.column("company_id"), sa.column("shop_id"))
    shops = sa.table("finance_shops", sa.column("id"), sa.column("company_id"))
    target = sa.table("finance_shop_sku_costs", sa.column("company_id"), sa.column("shop_id"),
                     sa.column("base_sku"), sa.column("unit_cost", sa.Numeric(18, 2)))
    query = sa.select(orders.c.company_id, orders.c.shop_id, items.c.base_sku, costs.c.unit_cost).select_from(
        orders.join(items, items.c.order_id == orders.c.id).join(shops,
            (shops.c.id == orders.c.shop_id) & (shops.c.company_id == orders.c.company_id)).join(costs,
            (costs.c.company_id == orders.c.company_id) & (costs.c.base_sku == items.c.base_sku))).distinct()
    op.get_bind().execute(target.insert().from_select(["company_id", "shop_id", "base_sku", "unit_cost"], query))


def downgrade():
    # 不合并不同店铺的价格，旧公司级配置始终保留。
    op.drop_table("finance_shop_sku_costs")
