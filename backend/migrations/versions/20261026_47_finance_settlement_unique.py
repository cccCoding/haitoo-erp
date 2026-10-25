"""财务账单以订单和结算单唯一，合并旧 SKU 明细并保留原始记录。"""
from decimal import Decimal, localcontext
from itertools import groupby

from alembic import op
import sqlalchemy as sa

revision = "20261026_47"
down_revision = "20261025_46"
branch_labels = None
depends_on = None

LIMIT = Decimal('999999999999999999.999999')


def bill_table(with_sources=False):
    columns = [sa.column('id', sa.Integer()), sa.column('order_id', sa.Integer()),
        sa.column('settlement_id', sa.String(120)), sa.column('sku_id', sa.String(120)),
        sa.column('currency', sa.String(3)), sa.column('settlement', sa.Numeric(24, 6)),
        sa.column('revenue', sa.Numeric(24, 6))]
    if with_sources:
        columns.append(sa.column('source_details', sa.JSON()))
    return sa.table('finance_bills', *columns)


def checked_sum(values):
    with localcontext() as context:
        context.prec = 64
        result = sum(values, Decimal(0))
    if abs(result) > LIMIT:
        raise RuntimeError('历史账单合计超出金额范围，未修改账单，请先检查数据')
    return result


def upgrade():
    connection = op.get_bind()
    bill = bill_table()
    # 由数据库计算分组，遵守当前数据库对结算单 ID 的排序与大小写规则。
    group_id = sa.func.min(bill.c.id).over(partition_by=[bill.c.order_id, bill.c.settlement_id]).label('group_id')
    rows = connection.execute(sa.select(bill, group_id).order_by(group_id, bill.c.id)).mappings().all()
    plans = []
    for identity, records in groupby(rows, key=lambda row: row['group_id']):
        records = list(records)
        if len({row['currency'] for row in records}) != 1:
            raise RuntimeError('历史账单同一订单、结算单包含不同货币，未修改账单，请先检查数据')
        plans.append((identity, [row['id'] for row in records[1:]],
            checked_sum(row['settlement'] for row in records), checked_sum(row['revenue'] for row in records),
            [{'sku_id': row['sku_id'] or None, 'currency': row['currency'],
              'settlement': str(row['settlement']), 'revenue': str(row['revenue'])} for row in records]))
    op.add_column('finance_bills', sa.Column('source_details', sa.JSON(), nullable=True))
    target = bill_table(with_sources=True)
    for identity, removed, settlement, revenue, sources in plans:
        for offset in range(0, len(removed), 400):
            connection.execute(target.delete().where(target.c.id.in_(removed[offset:offset + 400])))
        connection.execute(target.update().where(target.c.id == identity).values(
            sku_id='', settlement=settlement, revenue=revenue, source_details=sources))
    with op.batch_alter_table('finance_bills') as batch:
        batch.drop_constraint('uq_finance_bill', type_='unique')
        batch.create_unique_constraint('uq_finance_bill', ['order_id', 'settlement_id'])


def downgrade():
    connection = op.get_bind()
    bill = bill_table(with_sources=True)
    plans = []
    for row in connection.execute(sa.select(bill)).mappings():
        sources = row['source_details'] or [{'sku_id': row['sku_id'], 'currency': row['currency'],
            'settlement': str(row['settlement']), 'revenue': str(row['revenue'])}]
        grouped = {}
        for source in sources:
            grouped.setdefault(source['sku_id'] or '', []).append(source)
        values = [dict(order_id=row['order_id'], settlement_id=row['settlement_id'], sku_id=sku,
            currency=row['currency'], settlement=checked_sum(Decimal(s['settlement']) for s in records),
            revenue=checked_sum(Decimal(s['revenue']) for s in records)) for sku, records in grouped.items()]
        plans.append((row['id'], values))
    with op.batch_alter_table('finance_bills') as batch:
        batch.drop_constraint('uq_finance_bill', type_='unique')
        batch.create_unique_constraint('uq_finance_bill', ['order_id', 'settlement_id', 'sku_id'])
    for identity, values in plans:
        connection.execute(bill.update().where(bill.c.id == identity).values(**values[0]))
        if len(values) > 1:
            connection.execute(bill.insert(), values[1:])
    with op.batch_alter_table('finance_bills') as batch:
        batch.drop_column('source_details')
