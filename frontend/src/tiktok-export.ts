export type ShippingInsurance = 'Optional' | 'Mandatory'

export interface ShippingInsuranceOptions {
  capabilities?: { supports_shipping_insurance?: boolean }
  shipping_insurance_options?: ShippingInsurance[]
  shipping_insurance_default?: ShippingInsurance | null
}

export function shippingInsuranceSelection(options: ShippingInsuranceOptions | null, saved?: ShippingInsurance | null): ShippingInsurance | null {
  if (!options?.capabilities?.supports_shipping_insurance) return null
  const values = options.shipping_insurance_options || []
  if (saved && values.includes(saved)) return saved
  const fallback = options.shipping_insurance_default
  return fallback && values.includes(fallback) ? fallback : null
}

export function shippingInsuranceError(value: ShippingInsurance | null, options: ShippingInsuranceOptions | null): string {
  if (!options?.capabilities?.supports_shipping_insurance) return ''
  return value && options.shipping_insurance_options?.includes(value) ? '' : '请选择模板支持的运输保险选项'
}
