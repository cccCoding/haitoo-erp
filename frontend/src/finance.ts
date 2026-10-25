// 财务时间输入固定解释为 UTC+8，不能依赖运行浏览器的系统时区。
export const financeWindowSeconds = 90 * 24 * 60 * 60
export function beijingInput(value: Date): string {
  return new Date(value.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 19)
}
export function financeDefaults(now = new Date()) {
  const end = new Date(Math.floor(now.getTime() / 1000) * 1000)
  return { start: beijingInput(new Date(end.getTime() - 30 * 86400000)), end: beijingInput(end) }
}
export function financeInstant(value: string): string {
  // datetime-local 会省略值为 00 的秒，仍应按整秒解释。
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) value += ':00'
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(value)) throw new Error('请填写精确到秒的开始和结束时间')
  const time = new Date(`${value}+08:00`)
  if (!Number.isFinite(time.getTime()) || beijingInput(time) !== value) throw new Error('开始或结束时间无效')
  return time.toISOString()
}
export function validateFinanceQuery(shopIds: number[], start: string, end: string): string {
  if (!shopIds.length) return '请至少选择一个店铺'
  if (!start || !end) return '请填写开始和结束时间'
  try {
    const delta = (Date.parse(financeInstant(end)) - Date.parse(financeInstant(start))) / 1000
    if (delta <= 0) return '开始时间必须早于结束时间'
    if (delta > financeWindowSeconds) return '查询范围不能超过 90×24 小时'
  } catch (error) { return (error as Error).message }
  return ''
}
export function defaultFinanceShop(shops: {id: number}[], last: number | null): number[] {
  if (!shops.length) return []
  return [shops.some(shop => shop.id === last) ? last! : shops[0].id]
}
export function financeQueryKey(ids: number[], start: string, end: string) {
  return JSON.stringify([[...ids].sort((a,b) => a-b), start, end])
}

export function validateFinanceUnitCost(value: string): string {
  const text=value.trim()
  if (!text) return '请输入单件衣服成本'
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return '成本须为非负数字，最多两位小数'
  if (text.split('.')[0].replace(/^0+/, '').length>16) return '成本超出支持范围'
  return ''
}
