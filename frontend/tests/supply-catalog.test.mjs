import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSupplyRequestScope, createSupplySubmissionKeys, emptySupplyStrategy, supplyExpiryInput, supplyExpiryPayload, supplyFileStatus, supplyStrategyPayload, supplyTime, unfinishedSupplyJob, validateSupplyStrategy } from '../src/supply-catalog.ts'
const valid = () => ({ ...emptySupplyStrategy(), name: '日常女装', category_catalog_id: 1, category_name: 'Dresses', template_id: 1, price: '39.90' })

test('Expiry editing uses Hong Kong time across day boundaries and validates calendar dates', () => {
  const expiry = Date.parse('2027-01-31T16:00:37Z')
  assert.equal(supplyExpiryInput(expiry), '2027-02-01T00:00:37')
  assert.equal(supplyExpiryPayload(supplyExpiryInput(expiry)), '2027-01-31T16:00:37.000Z')
  assert.equal(supplyExpiryPayload('2028-02-29T12:30'), '2028-02-29T04:30:00.000Z')
  assert.equal(supplyExpiryInput(null), '')
  for (const value of ['', 'not a date', '2027-02-29T12:30', '2027-04-31T12:30', '2027-01-01T24:00', '0000-01-01T00:00']) {
    assert.equal(supplyExpiryPayload(value), null, value)
  }
})

test('New strategies filter infringement and legacy payloads preserve unrestricted selection', () => {
  assert.equal(emptySupplyStrategy().infringement_filter, 'exclude')
  const legacy = valid()
  delete legacy.infringement_filter
  assert.equal(supplyStrategyPayload(legacy).infringement_filter, 'include')
  for (const mode of ['exclude', 'include', 'only']) {
    const form = {...valid(), infringement_filter: mode}
    assert.equal(supplyStrategyPayload(form).infringement_filter, mode)
    assert.equal(validateSupplyStrategy(form, 2), '')
  }
  assert.match(validateSupplyStrategy({...valid(), infringement_filter:'invalid'}, 2), /侵权筛选/)
})

test('Statistics refreshes and closed dialogs reject late responses independently', async () => {
  const statistics = createSupplyRequestScope(), detail = createSupplyRequestScope()
  const oldStatistics = statistics.start(), activeDetail = detail.start()
  let resolveOld
  const lateResponse = new Promise(resolve => { resolveOld = resolve }).then(() => oldStatistics.isCurrent())
  const newStatistics = statistics.start()
  resolveOld()
  assert.equal(await lateResponse, false)
  assert.equal(oldStatistics.signal.aborted, true)
  assert.equal(newStatistics.isCurrent(), true)
  assert.equal(activeDetail.isCurrent(), true)
  detail.invalidate()
  assert.equal(activeDetail.signal.aborted, true)
  assert.equal(activeDetail.isCurrent(), false)
  assert.equal(newStatistics.isCurrent(), true)
  statistics.invalidate()
  assert.equal(newStatistics.isCurrent(), false)
})

test('Supply quantities and expanded row capacity are independently enforced', () => {
  assert.equal(validateSupplyStrategy({ ...valid(), sku_count: 9, link_count: 50 }, 8), '')
  assert.match(validateSupplyStrategy({ ...valid(), link_count: 51 }, 1), /10–50/)
  assert.match(validateSupplyStrategy({ ...valid(), sku_count: 4 }, 1), /5–9/)
  assert.match(validateSupplyStrategy({ ...valid(), sku_count: 9, link_count: 50 }, 12), /4,994/)
  assert.equal(validateSupplyStrategy({ ...valid(), sku_count: 9, link_count: 50 }, 11), '')
})
test('Supply prices, inventory, and mandatory category attributes are checked', () => {
  assert.match(validateSupplyStrategy({ ...valid(), price: 'NaN' }, 8), /售价/)
  assert.match(validateSupplyStrategy({ ...valid(), stock: 0.5 }, 8), /库存/)
  assert.match(validateSupplyStrategy(valid(), 8, [{ field: 'material', label: '材质', required: true }]), /材质/)
  assert.equal(validateSupplyStrategy({ ...valid(), attributes: { material: 'Cotton' } }, 8, [{ field: 'material', required: true }]), '')
})
test('Uncertain submit retries reuse an idempotency key, successful submissions do not', () => {
  let value = 0
  const keys = createSupplySubmissionKeys(() => `key-${++value}`)
  assert.equal(keys.forStrategy(1), 'key-1')
  assert.equal(keys.forStrategy(1), 'key-1')
  assert.equal(keys.forStrategy(2), 'key-2')
  keys.complete()
  assert.equal(keys.forStrategy(2), 'key-3')
})
test('Editing a persisted strategy does not send read-only metadata to a strict API', () => {
  const payload = supplyStrategyPayload({ ...valid(), name: ' 策略 ', id: 12, created_at: 1234, user_id: 9 })
  assert.equal(payload.name, '策略')
  assert.equal(payload.price, '39.90')
  assert.equal('id' in payload, false)
  assert.equal('created_at' in payload, false)
  assert.equal('user_id' in payload, false)
})
test('Download status distinguishes expiry, completion, and unfinished states', () => {
  const now = Date.parse('2026-10-14T00:00:00Z')
  assert.equal(supplyFileStatus({ state: 'completed', file_expired: true }, now), '文件已过期')
  assert.equal(supplyFileStatus({ state: 'completed', output_expires_at: '2026-10-13T00:00:00Z' }, now), '文件已过期')
  assert.equal(supplyFileStatus({ state: 'completed', output_expires_at: '2026-10-15T00:00:00Z' }, now), '可下载')
  assert.equal(supplyFileStatus({ state: 'running' }, now), '')
  assert.equal(unfinishedSupplyJob({ state: 'retry_wait' }), true)
  assert.equal(unfinishedSupplyJob({ state: 'cancelled' }), false)
  assert.equal(supplyTime(null), '—')
  assert.equal(supplyTime('not a date'), '—')
})
