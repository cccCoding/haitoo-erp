import assert from 'node:assert/strict'
import { test } from 'node:test'
import { financeDatePresets, financeMonth, financeMonthGrid, financeRangePreset, financeRangeSpan, shiftFinanceDate } from '../src/finance.ts'
import { validateFinanceDateRange } from '../src/finance.ts'

const now=new Date('2026-10-25T16:15:00Z')
test('Shortcuts use Beijing calendar days and inclusive rolling windows',()=>{
  const expected={today:['2026-10-26','2026-10-26'],yesterday:['2026-10-25','2026-10-25'],
    last7:['2026-10-20','2026-10-26'],last30:['2026-09-27','2026-10-26'],last90:['2026-07-29','2026-10-26'],
    last180:['2026-04-30','2026-10-26'],last365:['2025-10-27','2026-10-26'],
    thisWeek:['2026-10-26','2026-10-26'],lastWeek:['2026-10-19','2026-10-25'],
    thisMonth:['2026-10-01','2026-10-26'],lastMonth:['2026-09-01','2026-09-30']}
  assert.equal(financeDatePresets.length,11)
  for (const {key} of financeDatePresets) {
    const range=financeRangePreset(key,now)
    assert.deepEqual([range.start,range.end],expected[key])
    assert.equal(validateFinanceDateRange(range.start,range.end),'')
  }
})
test('Half-year and year shortcuts preserve inclusive spans across leap days',()=>{
  const leapNow=new Date('2024-03-01T00:00:00Z')
  for (const [key,days,start] of [['last180',180,'2023-09-04'],['last365',365,'2023-03-03']]) {
    const range=financeRangePreset(key,leapNow)
    assert.deepEqual(range,{start,end:'2024-03-01'})
    assert.equal(financeRangeSpan(range.start,range.end),days)
    assert.equal(validateFinanceDateRange(range.start,range.end),'')
  }
})
test('Week and month shortcuts cross year and leap-month boundaries',()=>{
  assert.deepEqual(financeRangePreset('lastWeek',new Date('2026-01-01T00:00:00Z')),
    {start:'2025-12-22',end:'2025-12-28'})
  assert.deepEqual(financeRangePreset('thisWeek',new Date('2026-01-01T00:00:00Z')),
    {start:'2025-12-29',end:'2026-01-01'})
  assert.deepEqual(financeRangePreset('lastMonth',new Date('2026-01-01T00:00:00Z')),
    {start:'2025-12-01',end:'2025-12-31'})
  assert.deepEqual(financeRangePreset('lastMonth',new Date('2024-03-01T00:00:00Z')),
    {start:'2024-02-01',end:'2024-02-29'})
})
test('Calendar grids align weekdays, include leap days and preserve month navigation',()=>{
  const grid=financeMonthGrid('2026-09-01')
  assert.equal(grid.length,6)
  assert.equal(grid[0][0].date,'2026-08-30')
  assert.equal(grid.flat().filter(day=>day.inMonth).length,30)
  assert.equal(financeMonthGrid('2024-02-01').flat().filter(day=>day.inMonth).length,29)
  assert.equal(financeMonth('2026-01-31',-1),'2025-12-01')
  assert.equal(shiftFinanceDate('2024-02-28',1),'2024-02-29')
  assert.equal(shiftFinanceDate('2025-12-31',1),'2026-01-01')
  assert.equal(financeRangeSpan('2026-01-01','2026-06-29'),180)
  assert.equal(financeRangeSpan('2026-06-29','2026-01-01'),180)
  assert.equal(financeRangeSpan('2026-01-01','2026-06-30'),181)
})
