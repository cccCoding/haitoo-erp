"""财务店铺区分跨境和本土；现有店铺按用户指定保留为跨境店。"""
from decimal import Decimal, localcontext
from itertools import groupby

from alembic import op
import sqlalchemy as sa

revision = '20261026_48'
down_revision = '20261026_47'
branch_labels = None
depends_on = None
LIMIT = Decimal('999999999999999999.999999')


def bill_table():
    return sa.table('finance_bills', sa.column('id', sa.Integer()), sa.column('order_id', sa.Integer()),
        sa.column('settlement_id', sa.String(120)), sa.column('sku_id', sa.String(120)),
        sa.column('currency', sa.String(3)), sa.column('settlement', sa.Numeric(24, 6)),
        sa.column('revenue', sa.Numeric(24, 6)), sa.column('source_details', sa.JSON()))


def total(values):
    with localcontext() as context:
        context.prec = 64
        result = sum(values, Decimal(0))
    if abs(result) > LIMIT:
        raise RuntimeError('历史账单合计超出金额范围，未修改账单')
    return result


def source_rows(row):
    records = row['source_details'] or [{'sku_id': row['sku_id'] or None, 'currency': row['currency'],
        'settlement': str(row['settlement']), 'revenue': str(row['revenue'])}]
    return [{**record, 'settlement_id': record.get('settlement_id') or row['settlement_id'] or None} for record in records]


def upgrade():
    connection = op.get_bind()
    bill = bill_table()
    plans = []
    for row in connection.execute(sa.select(bill)).mappings():
        records = source_rows(row)
        # 只有原始明细确实对应当前金额时才恢复 SKU；无法识别的历史汇总保留为空 SKU。
        exact = all(r['currency'] == row['currency'] for r in records) and all(
            total(Decimal(r[key]) for r in records) == row[key] for key in ('settlement', 'revenue'))
        grouped = {}
        if exact:
            for record in records:
                sku = str(record.get('sku_id') or '').strip()
                if len(sku) > 120 or sku.startswith('='):
                    sku = ''
                grouped.setdefault(sku, []).append(record)
        else:
            grouped[''] = records
        values = [dict(order_id=row['order_id'], settlement_id=row['settlement_id'], sku_id=sku,
            currency=row['currency'], settlement=total(Decimal(r['settlement']) for r in entries) if exact else row['settlement'],
            revenue=total(Decimal(r['revenue']) for r in entries) if exact else row['revenue'], source_details=entries)
            for sku, entries in grouped.items()]
        plans.append((row['id'], values))
    op.add_column('finance_shops', sa.Column('shop_type', sa.String(20), nullable=False, server_default='cross_border'))
    if connection.dialect.name in {'mysql', 'mariadb'}:
        op.alter_column('finance_bills', 'sku_id', existing_type=sa.String(120), existing_nullable=False,
            type_=sa.String(120, collation='utf8mb4_bin'))
    with op.batch_alter_table('finance_bills') as batch:
        batch.drop_constraint('uq_finance_bill', type_='unique')
        batch.create_unique_constraint('uq_finance_bill', ['order_id', 'settlement_id', 'sku_id'])
    for identity, values in plans:
        connection.execute(bill.update().where(bill.c.id == identity).values(**values[0]))
        for offset in range(1, len(values), 400):
            connection.execute(bill.insert(), values[offset:offset + 400])


def downgrade():
    connection = op.get_bind()
    bill = bill_table()
    group_id = sa.func.min(bill.c.id).over(partition_by=[bill.c.order_id, bill.c.settlement_id]).label('group_id')
    rows = connection.execute(sa.select(bill, group_id).order_by(group_id, bill.c.id)).mappings().all()
    plans = []
    for identity, entries in groupby(rows, key=lambda row: row['group_id']):
        entries = list(entries)
        if len({r['currency'] for r in entries}) != 1:
            raise RuntimeError('同一订单结算单包含多个币种，无法降级合并，未修改账单')
        plans.append((identity, [r['id'] for r in entries[1:]], total(r['settlement'] for r in entries),
            total(r['revenue'] for r in entries), [source for r in entries for source in source_rows(r)]))
    for identity, removed, settlement, revenue, sources in plans:
        for offset in range(0, len(removed), 400):
            connection.execute(bill.delete().where(bill.c.id.in_(removed[offset:offset + 400])))
        connection.execute(bill.update().where(bill.c.id == identity).values(
            sku_id='', settlement=settlement, revenue=revenue, source_details=sources))
    with op.batch_alter_table('finance_bills') as batch:
        batch.drop_constraint('uq_finance_bill', type_='unique')
        batch.create_unique_constraint('uq_finance_bill', ['order_id', 'settlement_id'])
    with op.batch_alter_table('finance_shops') as batch:
        batch.drop_column('shop_type')
