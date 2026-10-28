import assert from 'node:assert/strict'
import { test } from 'node:test'
import { shippingInsuranceSelection, shippingInsuranceError } from '../src/tiktok-export.ts'
import { emptySupplyStrategy, supplyStrategyPayload } from '../src/supply-catalog.ts'

const both = { capabilities: { supports_shipping_insurance: true }, shipping_insurance_options: ['Optional', 'Mandatory'], shipping_insurance_default: 'Optional' }
const single = { capabilities: { supports_shipping_insurance: false }, shipping_insurance_options: [], shipping_insurance_default: null }

test('New dialogs and switched catalogs reset insurance to the template default', () => {
  assert.equal(shippingInsuranceSelection(both), 'Optional')
  assert.equal(shippingInsuranceSelection(single, 'Mandatory'), null)
  assert.equal(shippingInsuranceSelection(both, null), 'Optional')
  assert.equal(shippingInsuranceSelection(null, 'Mandatory'), null)
})
test('Strategy editing preserves an explicit choice and defaults legacy missing values', () => {
  assert.equal(shippingInsuranceSelection(both, 'Mandatory'), 'Mandatory')
  assert.equal(shippingInsuranceSelection(both, undefined), 'Optional')
  const form = { ...emptySupplyStrategy(), shipping_insurance: 'Mandatory' }
  assert.equal(supplyStrategyPayload(form).shipping_insurance, 'Mandatory')
  delete form.shipping_insurance
  assert.equal(supplyStrategyPayload(form).shipping_insurance, null)
})
test('Insurance validation accepts supported choices and does not guess invalid metadata', () => {
  for (const value of ['Optional', 'Mandatory']) assert.equal(shippingInsuranceError(value, both), '')
  for (const value of [null, 'Invalid']) assert.match(shippingInsuranceError(value, both), /运输保险/)
  assert.equal(shippingInsuranceError(null, single), '')
  assert.equal(shippingInsuranceSelection({ ...both, shipping_insurance_options: ['Mandatory'] }), null)
})
