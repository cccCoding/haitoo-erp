"""财务改为基础 SKU 成本，保留原始大小写及已生效成本。"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_46"
down_revision = "20261025_45"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    binary_sku = sa.String(120).with_variant(sa.String(120, collation="utf8mb4_bin"), "mysql", "mariadb")
    op.create_table("finance_sku_costs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("base_sku", binary_sku, nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("company_id", "base_sku", name="uq_finance_sku_cost"))
    op.create_index("ix_finance_sku_costs_company_id", "finance_sku_costs", ["company_id"])
    if connection.dialect.name in {"mysql", "mariadb"}:
        for column in ("platform_sku", "base_sku"):
            op.alter_column("finance_erp_items", column, existing_type=sa.String(120),
                            type_=binary_sku, existing_nullable=False)
    mapping = sa.table("finance_sku_mappings", sa.column("company_id"), sa.column("base_sku"), sa.column("template_id"))
    old_cost = sa.table("finance_template_costs", sa.column("company_id"), sa.column("template_id"), sa.column("unit_cost", sa.Numeric(18, 2)))
    template = sa.table("product_templates", sa.column("id"), sa.column("company_id"), sa.column("is_platform"))
    items = sa.table("finance_erp_items", sa.column("id"), sa.column("order_id"), sa.column("platform_sku"), sa.column("base_sku"))
    orders = sa.table("finance_orders", sa.column("id"), sa.column("company_id"))
    target = sa.table("finance_sku_costs", sa.column("company_id"), sa.column("base_sku"), sa.column("unit_cost", sa.Numeric(18, 2)))
    legacy = {(company, sku): cost for company, sku, cost in connection.execute(
        sa.select(mapping.c.company_id, mapping.c.base_sku, old_cost.c.unit_cost).select_from(mapping.join(old_cost,
            (old_cost.c.company_id == mapping.c.company_id) & (old_cost.c.template_id == mapping.c.template_id))
        .join(template, (template.c.id == mapping.c.template_id) & sa.or_(
            template.c.company_id == mapping.c.company_id, template.c.is_platform.is_(True))))) }
    # 留存历史上已配置、目前不在订单中的 SKU 成本；恢复各商品的原始大小写。
    restored = dict(legacy)
    rows = connection.execute(sa.select(items.c.id, items.c.platform_sku, items.c.base_sku, orders.c.company_id)
                             .select_from(items.join(orders, orders.c.id == items.c.order_id))).all()
    for identity, platform_sku, old_base, company_id in rows:
        base = platform_sku.split('-', 1)[0].strip()
        connection.execute(items.update().where(items.c.id == identity).values(base_sku=base))
        if (company_id, old_base) in legacy:
            restored[(company_id, base)] = legacy[(company_id, old_base)]
    values = [{'company_id': company, 'base_sku': sku, 'unit_cost': cost} for (company, sku), cost in restored.items()]
    for offset in range(0, len(values), 500):
        connection.execute(target.insert(), values[offset:offset + 500])


def downgrade():
    # 保留区分大小写的商品列，避免降级时合并已导入的大小写不同 SKU。
    # 旧配置表始终保留，降级不会删除此前的配置。
    op.drop_table("finance_sku_costs")
