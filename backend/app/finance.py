"""公司管理员财务导入、按下单时间查询和人民币核算。"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .finance_import import MAX_BYTES, SheetChoice, decimal_value, parse_workbook
from .finance_export import export_workbook
from .models import (Company, FinanceBill, FinanceErpItem, FinanceExchangeRate, FinanceImport,
    FinanceOrder, FinanceShop, FinanceShopSkuCost, Role, User)
from .security import require_roles

router = APIRouter(prefix='/finance', tags=['finance'])
admin = require_roles(Role.COMPANY_ADMIN)
CENT = Decimal('.01')


def money(value):
    with localcontext() as context:
        context.prec = 64
        return str(value.quantize(CENT, rounding=ROUND_HALF_UP)) if value is not None else None


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def lock_company(db, user):
    company_id = user.company_id
    # 认证及店铺校验已经进行只读查询。结束其快照，再取得公司锁，确保 MySQL
    # REPEATABLE READ 下等待前次导入完成后能读到最新明细；此调用必须早于任何写入。
    db.rollback()
    if company_id is None or db.scalar(select(Company.id).where(Company.id == company_id).with_for_update()) is None:
        raise HTTPException(403, '当前账号没有有效公司')


def shops_for(db, user, shop_ids):
    ids = set(shop_ids)
    if not ids or any(identity <= 0 for identity in ids) or len(ids) > 500:
        raise HTTPException(400, '必须选择店铺，最多选择 500 个')
    shops = db.scalars(select(FinanceShop).where(FinanceShop.company_id == user.company_id,
        FinanceShop.id.in_(ids)).order_by(FinanceShop.id)).all()
    if len(shops) != len(ids):
        raise HTTPException(404, '店铺不存在或无权访问')
    return shops


def commit(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '数据发生冲突，请刷新后重试') from exc


class ShopInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    shop_type: Literal['cross_border', 'local'] = 'cross_border'


class ShopTypeInput(BaseModel):
    shop_type: Literal['cross_border', 'local']


class ShopUpdateInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    shop_type: Literal['cross_border', 'local']


def shop_payload(shop, has_platform_data=False):
    return {'id': shop.id, 'name': shop.name, 'shop_type': shop.shop_type,
            'created_at': timestamp(shop.created_at), 'has_platform_data': has_platform_data}


@router.get('/shops')
def list_shops(user: User = Depends(admin), db: Session = Depends(get_db)):
    has_bills = exists().where(FinanceOrder.shop_id == FinanceShop.id, FinanceBill.order_id == FinanceOrder.id)
    return [shop_payload(shop, has_data) for shop, has_data in db.execute(select(FinanceShop, has_bills).where(
        FinanceShop.company_id == user.company_id).order_by(FinanceShop.id))]


@router.post('/shops')
def create_shop(payload: ShopInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, '请输入店铺名称')
    lock_company(db, user)
    if db.scalar(select(FinanceShop.id).where(FinanceShop.company_id == user.company_id, FinanceShop.name == name)):
        raise HTTPException(409, '已有同名店铺，请直接选择')
    shop = FinanceShop(company_id=user.company_id, name=name, shop_type=payload.shop_type)
    db.add(shop)
    commit(db)
    return shop_payload(shop)


def update_shop_details(db, user, shop_id, *, name=None, shop_type):
    shops_for(db, user, [shop_id])
    lock_company(db, user)
    shop = shops_for(db, user, [shop_id])[0]
    name = shop.name if name is None else name.strip()
    if not name:
        raise HTTPException(400, '请输入店铺名称')
    if db.scalar(select(FinanceShop.id).where(FinanceShop.company_id == user.company_id,
            FinanceShop.name == name, FinanceShop.id != shop_id)):
        raise HTTPException(409, '已有同名店铺，请使用其他名称')
    has_data = db.scalar(select(exists().where(FinanceOrder.shop_id == shop_id,
        FinanceBill.order_id == FinanceOrder.id)))
    if shop.shop_type != shop_type:
        if has_data:
            raise HTTPException(409, '已导入后台账单的店铺不能修改类型，请新建对应类型的店铺')
        shop.shop_type = shop_type
    shop.name = name
    commit(db)
    return shop_payload(shop, has_data)


@router.patch('/shops/{shop_id}')
def update_shop(shop_id: int, payload: ShopUpdateInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    return update_shop_details(db, user, shop_id, name=payload.name, shop_type=payload.shop_type)


@router.patch('/shops/{shop_id}/type')
def change_shop_type(shop_id: int, payload: ShopTypeInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    return update_shop_details(db, user, shop_id, shop_type=payload.shop_type)


@router.post('/shops/{shop_id}/imports/{kind}')
def import_file(shop_id: int, kind: Literal['platform', 'erp'], file: UploadFile = File(...),
                sheet_name: str | None = Form(None), user: User = Depends(admin), db: Session = Depends(get_db)):
    shop_type = shops_for(db, user, [shop_id])[0].shop_type
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(400, '仅支持 XLSX 文件')
    data = file.file.read(MAX_BYTES + 1)
    try:
        parsed = parse_workbook(data, kind, sheet_name, shop_type=shop_type)
    except SheetChoice as exc:
        raise HTTPException(409, {'message': str(exc), 'sheets': exc.sheets}) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    lock_company(db, user)
    if shops_for(db, user, [shop_id])[0].shop_type != shop_type:
        raise HTTPException(409, '店铺类型已变更，请重新导入')
    order_numbers = set(parsed['orders']) | {key[0] for key in parsed['bills']}
    existing_orders = {}
    numbers = sorted(order_numbers)
    for offset in range(0, len(numbers), 400):
        existing_orders.update({o.order_number: o for o in db.scalars(select(FinanceOrder).where(
            FinanceOrder.shop_id == shop_id, FinanceOrder.company_id == user.company_id,
            FinanceOrder.order_number.in_(numbers[offset:offset + 400])))})
    for number in numbers:
        if number not in existing_orders:
            order = FinanceOrder(company_id=user.company_id, shop_id=shop_id, order_number=number)
            db.add(order)
            existing_orders[number] = order
    db.flush()
    counts = {key: 0 for key in ('created', 'updated', 'unchanged')}
    counts.update(source_rows=parsed['source_rows'], ignored=parsed['ignored'], sheet=parsed['sheet'])
    order_ids = [o.id for o in existing_orders.values()]
    if kind == 'platform':
        bills = {}
        for offset in range(0, len(order_ids), 400):
            bills.update({(b.order_id, b.settlement_id, b.sku_id): b for b in db.scalars(select(FinanceBill).where(
                FinanceBill.order_id.in_(order_ids[offset:offset + 400])))})
        if shop_type == 'cross_border':
            # 旧版本允许缺少 SKU 的汇总记录，仅在完整组金额相同时安全补回明细。
            incoming_groups = defaultdict(list)
            for (number, settlement_id, _), values in parsed['bills'].items():
                incoming_groups[(existing_orders[number].id, settlement_id)].append(values)
            removed = False
            for order_id, settlement_id, sku_id in list(bills):
                group = (order_id, settlement_id)
                if sku_id or group not in incoming_groups:
                    continue
                keys = [key for key in bills if key[:2] == group]
                previous = [(bills[key].currency, bills[key].settlement, bills[key].revenue) for key in keys]
                incoming = incoming_groups[group]
                with localcontext() as context:
                    context.prec = 64
                    same = {v[0] for v in previous} == {v[0] for v in incoming} and len({v[0] for v in previous}) == 1 and all(
                        sum(v[i] for v in previous) == sum(v[i] for v in incoming) for i in (1, 2))
                if not same:
                    raise HTTPException(409, '历史结算记录缺少 SKU ID，请先导入金额一致的完整 SKU 明细，再更新金额')
                for key in keys:
                    db.delete(bills.pop(key))
                removed = True
            if removed:
                db.flush()
        for (number, settlement_id, sku_id), values in parsed['bills'].items():
            key = (existing_orders[number].id, settlement_id, sku_id)
            bill = bills.get(key)
            if bill is None:
                bill = FinanceBill(order_id=key[0], settlement_id=settlement_id, sku_id=sku_id)
                db.add(bill)
                counts['created'] += 1
            elif (bill.currency, bill.settlement, bill.revenue) == values:
                counts['unchanged'] += 1
                bill.source_details = parsed['bill_sources'][(number, settlement_id, sku_id)]
                continue
            else:
                counts['updated'] += 1
            bill.currency, bill.settlement, bill.revenue = values
            bill.source_details = parsed['bill_sources'][(number, settlement_id, sku_id)]
        counts['unit'] = '账单明细' if shop_type == 'cross_border' else '订单账单'
    else:
        items_by_order = defaultdict(dict)
        for offset in range(0, len(order_ids), 400):
            for item in db.scalars(select(FinanceErpItem).where(FinanceErpItem.order_id.in_(order_ids[offset:offset + 400]))):
                items_by_order[item.order_id][item.platform_sku] = item
        for number, imported in parsed['orders'].items():
            order = existing_orders[number]
            previous = items_by_order[order.id]
            same = order.paid_at == imported['ordered_at'] and {
                sku: (item.base_sku, item.quantity) for sku, item in previous.items()} == imported['items']
            counts['unchanged' if same else 'updated' if order.paid_at else 'created'] += 1
            if same:
                continue
            order.paid_at = imported['ordered_at']
            for sku, item in previous.items():
                if sku not in imported['items']:
                    db.delete(item)
            for sku, (base, quantity) in imported['items'].items():
                item = previous.get(sku)
                if item is None:
                    item = FinanceErpItem(order_id=order.id, platform_sku=sku)
                    db.add(item)
                item.base_sku, item.quantity = base, quantity
        counts['unit'] = '订单'
    db.add(FinanceImport(company_id=user.company_id, shop_id=shop_id, created_by=user.id,
        kind=kind, filename=(file.filename or '')[:255], counts=counts))
    commit(db)
    return counts


@router.get('/imports')
def import_history(user: User = Depends(admin), db: Session = Depends(get_db)):
    return [{'id': i.id, 'shop_id': i.shop_id, 'shop_name': name, 'kind': i.kind, 'filename': i.filename,
             'created_by': i.created_by, 'created_at': timestamp(i.created_at), 'counts': i.counts}
        for i, name in db.execute(select(FinanceImport, FinanceShop.name).join(FinanceShop, FinanceShop.id == FinanceImport.shop_id)
            .where(FinanceImport.company_id == user.company_id).order_by(FinanceImport.id.desc()).limit(100))]


@router.get('/settings')
def get_settings(user: User = Depends(admin), db: Session = Depends(get_db)):
    rates = {(r.shop_id, r.currency): r.rate for r in db.scalars(select(FinanceExchangeRate).join(
        FinanceShop, FinanceShop.id == FinanceExchangeRate.shop_id).where(FinanceShop.company_id == user.company_id))}
    currencies = db.execute(select(FinanceOrder.shop_id, FinanceBill.currency).join(
        FinanceBill, FinanceBill.order_id == FinanceOrder.id).where(FinanceOrder.company_id == user.company_id).distinct()).all()
    return {'rates': [{'shop_id': shop, 'currency': currency,
                       'rate': str(Decimal(1) if currency == 'CNY' else rates[(shop, currency)])
                       if currency == 'CNY' or (shop, currency) in rates else None}
                      for shop, currency in sorted(currencies)]}


class RateInput(BaseModel):
    shop_id: int = Field(gt=0)
    currency: str = Field(pattern='^[A-Z]{3}$')
    rate: str = Field(max_length=40)


class RatesInput(BaseModel):
    items: list[RateInput] = Field(min_length=1, max_length=500)


@router.put('/exchange-rates')
def save_rates(payload: RatesInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    shops_for(db, user, [item.shop_id for item in payload.items])
    values = []
    try:
        for item in payload.items:
            rate = decimal_value(item.rate, '汇率', places=8, maximum=Decimal('9999999999.99999999'), positive=True)
            if item.currency == 'CNY' and rate != 1:
                raise ValueError('人民币汇率固定为 1')
            values.append((item, rate))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if len({(i.shop_id, i.currency) for i, _ in values}) != len(values):
        raise HTTPException(400, '同店铺同币种不能重复提交')
    lock_company(db, user)
    for item, rate in values:
        row = db.scalar(select(FinanceExchangeRate).where(FinanceExchangeRate.shop_id == item.shop_id,
            FinanceExchangeRate.currency == item.currency))
        if row is None:
            row = FinanceExchangeRate(shop_id=item.shop_id, currency=item.currency)
            db.add(row)
        row.rate = rate
    commit(db)
    return {'updated': len(values)}


class ShopSkuInput(BaseModel):
    shop_id: int
    base_sku: str = Field(min_length=1, max_length=120)


class SkuCostsInput(BaseModel):
    items: list[ShopSkuInput] = Field(min_length=1, max_length=1000)
    unit_cost: str = Field(max_length=40)


@router.put('/sku-costs')
def save_sku_costs(payload: SkuCostsInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    keys = {(item.shop_id, item.base_sku.strip()) for item in payload.items}
    if any(not sku for _, sku in keys):
        raise HTTPException(400, '基础 SKU 无效')
    try:
        cost = decimal_value(payload.unit_cost, '单件衣服成本', places=2, maximum=Decimal('9999999999999999.99'))
        if cost < 0:
            raise ValueError('单件衣服成本不能为负数')
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    lock_company(db, user)
    shop_ids = {shop_id for shop_id, _ in keys}
    shops_for(db, user, list(shop_ids))
    bases = {sku for _, sku in keys}
    known = set(db.execute(select(FinanceOrder.shop_id, FinanceErpItem.base_sku).join(FinanceOrder,
        FinanceOrder.id == FinanceErpItem.order_id).where(FinanceOrder.company_id == user.company_id,
        FinanceOrder.shop_id.in_(shop_ids), FinanceErpItem.base_sku.in_(bases)).distinct()))
    if not keys.issubset(known):
        raise HTTPException(400, '所选 SKU 不存在或无权访问')
    existing = {(row.shop_id, row.base_sku): row for row in db.scalars(select(FinanceShopSkuCost).where(
        FinanceShopSkuCost.company_id == user.company_id, FinanceShopSkuCost.shop_id.in_(shop_ids),
        FinanceShopSkuCost.base_sku.in_(bases)))}
    for shop_id, sku in sorted(keys):
        row = existing.get((shop_id, sku))
        if row is None:
            row = FinanceShopSkuCost(company_id=user.company_id, shop_id=shop_id, base_sku=sku)
            db.add(row)
        row.unit_cost = cost
    commit(db)
    return {'updated': len(keys)}


def query_scope(shop_ids: list[int] = Query(..., min_length=1, max_length=500),
                paid_from: datetime = Query(...), paid_to: datetime = Query(...),
                user: User = Depends(admin), db: Session = Depends(get_db)):
    shops = shops_for(db, user, shop_ids)
    if paid_from.tzinfo is None or paid_to.tzinfo is None:
        raise HTTPException(400, '开始和结束时间必须包含时区')
    start, end = [value.astimezone(timezone.utc).replace(tzinfo=None) for value in (paid_from, paid_to)]
    if start >= end or end - start > timedelta(days=365):
        raise HTTPException(400, '开始时间须早于结束时间，且查询范围不能超过一年（365 天）')
    return shops, start, end


def calculate(db, user, shops, start, end):
    with localcontext() as context:
        context.prec = 64
        return _calculate(db, user, shops, start, end)


def _calculate(db, user, shops, start, end):
    shop_names = {s.id: s.name for s in shops}
    shop_types = {s.id: s.shop_type for s in shops}
    query = select(FinanceOrder).where(FinanceOrder.company_id == user.company_id,
        FinanceOrder.shop_id.in_(shop_names), FinanceOrder.paid_at >= start, FinanceOrder.paid_at <= end)
    orders = db.scalars(query.order_by(FinanceOrder.paid_at.desc(), FinanceOrder.id.desc())).all()
    scoped_ids = query.with_only_columns(FinanceOrder.id).order_by(None)
    bills, items = defaultdict(list), defaultdict(list)
    for bill in db.scalars(select(FinanceBill).where(FinanceBill.order_id.in_(scoped_ids))):
        bills[bill.order_id].append(bill)
    for item in db.scalars(select(FinanceErpItem).where(FinanceErpItem.order_id.in_(scoped_ids)).order_by(FinanceErpItem.platform_sku)):
        items[item.order_id].append(item)
    costs = {(c.shop_id, c.base_sku): c.unit_cost for c in db.scalars(select(FinanceShopSkuCost).where(
        FinanceShopSkuCost.company_id == user.company_id, FinanceShopSkuCost.shop_id.in_(shop_names)))}
    rates = {(r.shop_id, r.currency): r.rate for r in db.scalars(select(FinanceExchangeRate).where(
        FinanceExchangeRate.shop_id.in_(shop_names)))}
    summaries = {s.id: {'shop_id': s.id, 'shop_name': s.name, 'order_count': 0, 'converted_count': 0,
        'calculated_count': 0, 'erp_only_count': 0, 'sales': Decimal(0), 'settlement': Decimal(0),
        'cost': Decimal(0), 'profit': Decimal(0)} for s in shops}
    rows, sku_rows = [], {}
    for order in orders:
        statuses, currencies, details = [], {}, []
        settlement, revenue, cost = Decimal(0), Decimal(0), Decimal(0)
        for bill in bills[order.id]:
            raw = currencies.setdefault(bill.currency, {'settlement': Decimal(0), 'revenue': Decimal(0)})
            raw['settlement'] += bill.settlement
            raw['revenue'] += bill.revenue
        converted = bool(currencies)
        currency_rows = []
        for currency, raw in sorted(currencies.items()):
            rate = Decimal(1) if currency == 'CNY' else rates.get((order.shop_id, currency))
            if rate is None:
                converted = False
                statuses.append('缺汇率')
            else:
                settlement += raw['settlement'] * rate
                revenue += raw['revenue'] * rate
            currency_rows.append({'currency': currency, 'settlement': str(raw['settlement']),
                'revenue': str(raw['revenue']), 'rate': str(rate) if rate is not None else None})
        cost_known = bool(items[order.id])
        for item in items[order.id]:
            unit_cost = costs.get((order.shop_id, item.base_sku))
            if unit_cost is None:
                statuses.append('缺成本')
                cost_known = False
            else:
                cost += unit_cost * item.quantity
            detail = {'platform_sku': item.platform_sku, 'base_sku': item.base_sku, 'quantity': item.quantity,
                'unit_cost': money(unit_cost), 'line_cost': money(unit_cost * item.quantity) if unit_cost is not None else None}
            details.append(detail)
            sku_row = sku_rows.setdefault((order.shop_id, item.base_sku), {'shop_id': order.shop_id,
                'shop_name': shop_names[order.shop_id], 'base_sku': item.base_sku, 'quantity': 0, 'order_count': 0,
                'unit_cost': detail['unit_cost'],
                '_orders': set()})
            sku_row['quantity'] += item.quantity
            sku_row['_orders'].add(order.id)
        if not currencies:
            statuses.append('缺后台账单')
        if not items[order.id]:
            statuses.append('缺 ERP')
        ready = converted and cost_known
        settlement = settlement.quantize(CENT, rounding=ROUND_HALF_UP) if converted else None
        revenue = revenue.quantize(CENT, rounding=ROUND_HALF_UP) if converted else None
        cost = cost if cost_known else None
        profit = settlement - cost if ready else None
        summary = summaries[order.shop_id]
        if currencies:
            summary['order_count'] += 1
            if converted:
                summary['converted_count'] += 1
                summary['sales'] += revenue
                summary['settlement'] += settlement
            if ready:
                summary['calculated_count'] += 1
                summary['cost'] += cost
                summary['profit'] += profit
        else:
            summary['erp_only_count'] += 1
        rows.append({'id': order.id, 'shop_id': order.shop_id, 'shop_name': shop_names[order.shop_id], 'shop_type': shop_types[order.shop_id],
            'order_number': order.order_number, 'paid_at': timestamp(order.paid_at), 'has_bill': bool(currencies),
            'statuses': sorted(set(statuses)) or ['已核算'], 'sales': money(revenue), 'settlement': money(settlement),
            'cost': money(cost), 'profit': money(profit), 'currencies': currency_rows, 'items': details,
            'bills': [{'settlement_id': b.settlement_id, 'sku_id': b.sku_id or None, 'currency': b.currency,
                      'settlement': str(b.settlement), 'revenue': str(b.revenue),
                      'source_details': b.source_details or []} for b in bills[order.id]]})
    total = {'shop_id': None, 'shop_name': '合计', **{key: sum(s[key] for s in summaries.values()) for key in (
        'order_count', 'converted_count', 'calculated_count', 'erp_only_count', 'sales', 'settlement', 'cost', 'profit')}}
    output_summaries = []
    for summary in [*summaries.values(), total]:
        output_summaries.append({**summary, 'pending_count': summary['order_count'] - summary['calculated_count'],
            'sales': money(summary['sales']) if summary['converted_count'] or not summary['order_count'] else None,
            'settlement': money(summary['settlement']) if summary['converted_count'] or not summary['order_count'] else None,
            'cost': money(summary['cost']) if summary['calculated_count'] or not summary['order_count'] else None,
            'profit': money(summary['profit']) if summary['calculated_count'] or not summary['order_count'] else None})
    for row in sku_rows.values():
        row['order_count'] = len(row.pop('_orders'))
        unit_cost = costs.get((row['shop_id'], row['base_sku']))
        row['total_cost'] = money(unit_cost * row['quantity']) if unit_cost is not None else None
    return rows, sorted(sku_rows.values(), key=lambda row: (row['base_sku'], row['shop_id'])), output_summaries


@router.get('/results')
def results(scope=Depends(query_scope), order_page: int = Query(1, ge=1), sku_page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=1000), sku_search: str = Query('', max_length=120),
            sku_page_size: int = Query(20, ge=1, le=1000),
            sku_cost_status: Literal['all', 'set', 'unset'] = Query('all'),
            order_status: Literal['all', 'calculated', 'pending'] = Query('all'),
            user: User = Depends(admin), db: Session = Depends(get_db)):
    shops, start, end = scope
    rows, skus, summaries = calculate(db, user, shops, start, end)
    if order_status == 'calculated':
        rows = [row for row in rows if '已核算' in row['statuses']]
    elif order_status == 'pending':
        rows = [row for row in rows if '已核算' not in row['statuses']]
    skus = [s for s in skus if s['base_sku'].startswith(sku_search.strip())]
    if sku_cost_status != 'all':
        skus = [s for s in skus if (s['unit_cost'] is not None) == (sku_cost_status == 'set')]
    return {'query': {'shop_ids': [s.id for s in shops], 'paid_from': timestamp(start), 'paid_to': timestamp(end)},
        'summaries': summaries[:-1], 'total': summaries[-1],
        'orders': {'items': rows[(order_page - 1) * page_size:order_page * page_size], 'total': len(rows)},
        'skus': {'items': skus[(sku_page - 1) * sku_page_size:sku_page * sku_page_size], 'total': len(skus)}}


@router.get('/pending-payment-time')
def pending_time(shop_ids: list[int] = Query(..., min_length=1, max_length=500), page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=1000), user: User = Depends(admin), db: Session = Depends(get_db)):
    shops = shops_for(db, user, shop_ids)
    names = {s.id: s.name for s in shops}
    query = pending_order_query(user, shops)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(FinanceOrder.id.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()
    return {'total': total, 'items': [{'id': r.id, 'shop_name': names[r.shop_id], 'order_number': r.order_number} for r in rows]}


def pending_order_query(user, shops):
    return select(FinanceOrder).where(FinanceOrder.company_id == user.company_id,
        FinanceOrder.shop_id.in_([s.id for s in shops]), FinanceOrder.paid_at.is_(None),
        exists().where(FinanceBill.order_id == FinanceOrder.id))


@router.get('/exports/missing-bills')
def export_missing_bills(scope=Depends(query_scope), user: User = Depends(admin), db: Session = Depends(get_db)):
    shops, start, end = scope
    rows, _, _ = calculate(db, user, shops, start, end)
    rows = [row for row in rows if not row['has_bill']]
    def beijing(value):
        return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
    orders = [(row['shop_name'], row['order_number'], beijing(row['paid_at']),
               Decimal(row['cost']) if row['cost'] is not None else None, '缺后台账单') for row in rows]
    items = [(row['shop_name'], row['order_number'], item['platform_sku'], item['base_sku'], item['quantity'],
              Decimal(item['unit_cost']) if item['unit_cost'] is not None else None,
              Decimal(item['line_cost']) if item['line_cost'] is not None else None) for row in rows for item in row['items']]
    return export_workbook('缺后台账单订单.xlsx', [
        ('订单汇总', ['店铺', '订单编号', '下单时间（北京时间）', '衣服成本（人民币）', '状态'], orders),
        ('商品明细', ['店铺', '订单编号', '平台 SKU', '基础 SKU', '商品数量', '单件成本（人民币）', '商品成本（人民币）'], items)])


@router.get('/exports/pending-order-time')
def export_pending_time(shop_ids: list[int] = Query(..., min_length=1, max_length=500),
                        user: User = Depends(admin), db: Session = Depends(get_db)):
    shops = shops_for(db, user, shop_ids)
    names = {s.id: s.name for s in shops}
    query = pending_order_query(user, shops)
    orders = db.scalars(query.order_by(FinanceOrder.id.desc())).all()
    lookup = {row.id: row for row in orders}
    bills = db.scalars(select(FinanceBill).where(FinanceBill.order_id.in_(
        query.with_only_columns(FinanceOrder.id))).order_by(FinanceBill.order_id.desc(), FinanceBill.id))
    details = [(names[lookup[b.order_id].shop_id], lookup[b.order_id].order_number, b.settlement_id,
        b.sku_id, b.currency, b.revenue, b.settlement) for b in bills]
    return export_workbook('下单时间待补订单.xlsx', [
        ('订单汇总', ['店铺', '订单编号', '待处理'],
            [(names[row.shop_id], row.order_number, '补导 ERP 商品及下单时间') for row in orders]),
        ('账单明细', ['店铺', '订单编号', '结算单 ID', 'SKU ID', '货币', '总收入（原币）', '结算金额（原币）'], details)])
