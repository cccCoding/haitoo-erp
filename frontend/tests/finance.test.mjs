import assert from 'node:assert/strict'
import { test } from 'node:test'
import { defaultFinanceShop, financeDefaults, financeInstant, financeOverviewAmounts, financeQueryKey, validateFinanceQuery, validateFinanceUnitCost } from '../src/finance.ts'

test('Default range is exactly thirty days and displayed in Beijing time',()=>{
  const range=financeDefaults(new Date('2026-10-25T04:15:16.900Z'))
  assert.deepEqual(range,{start:'2026-09-25T12:15:16',end:'2026-10-25T12:15:16'})
  assert.equal(financeInstant(range.end),'2026-10-25T04:15:16.000Z')
  assert.equal(financeInstant('2026-10-25T12:15'),'2026-10-25T04:15:00.000Z')
})
test('A shop and both dates are required, and the inclusive window is limited to ninety days',()=>{
  assert.ok(validateFinanceQuery([],'2026-01-01T00:00:00','2026-04-01T00:00:00'))
  assert.ok(validateFinanceQuery([1],'','2026-04-01T00:00:00'))
  assert.equal(validateFinanceQuery([1],'2026-01-01T00:00:00','2026-04-01T00:00:00'),'')
  assert.ok(validateFinanceQuery([1],'2026-01-01T00:00:00','2026-04-01T00:00:01'))
  assert.ok(validateFinanceQuery([1],'2026-01-01T00:00:00','2026-01-01T00:00:00'))
  assert.ok(validateFinanceQuery([1],'2026-02-30T00:00:00','2026-04-01T00:00:00'))
})
test('Exactly one valid shop is restored, otherwise the earliest shop is selected',()=>{
  const shops=[{id:1},{id:5}]
  assert.deepEqual(defaultFinanceShop(shops,5),[5])
  assert.deepEqual(defaultFinanceShop(shops,99),[1])
  assert.deepEqual(defaultFinanceShop([],1),[])
  assert.equal(financeQueryKey([5,1],'s','e'),financeQueryKey([1,5],'s','e'))
})
test('SKU unit cost distinguishes missing input from zero and accepts at most two decimals',()=>{
  for(const value of ['0','0.00','18.25',' 25 ','9999999999999999.99']) assert.equal(validateFinanceUnitCost(value),'')
  for(const value of ['', ' ', '-1','NaN','Infinity','0.001','10000000000000000']) assert.ok(validateFinanceUnitCost(value))
})

test('Temporary other costs subtract exact cents, sum shops and preserve unavailable profit',()=>{
  assert.deepEqual(financeOverviewAmounts('100.00',['0.10','0.20']),{otherCost:'0.30',profit:'99.70',error:''})
  assert.equal(financeOverviewAmounts('0.00',['1.01']).profit,'-1.01')
  assert.equal(financeOverviewAmounts('-2.00',['3']).profit,'-5.00')
  assert.deepEqual(financeOverviewAmounts(null,['0','']),{otherCost:'0.00',profit:null,error:''})
  assert.equal(financeOverviewAmounts('9999999999999999.99',['0.01']).profit,'9999999999999999.98')
  for(const cost of ['-1','1.001','NaN','10000000000000000']) {
    const result=financeOverviewAmounts('10.00',[cost])
    assert.ok(result.error)
    assert.equal(result.profit,null)
    assert.equal(result.otherCost,null)
  }
})
