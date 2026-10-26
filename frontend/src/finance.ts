// 财务日期固定解释为 UTC+8，不能依赖运行浏览器的系统时区。
export const financeWindowSeconds = 180 * 24 * 60 * 60
export function beijingInput(value: Date): string {
  return new Date(value.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10)
}
export function financeDefaults(now = new Date()) {
  return { start: beijingInput(new Date(now.getTime() - 29 * 86400000)), end: beijingInput(now) }
}
export function financeInstant(value: string, boundary:'start'|'end'='start'): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('请选择有效的开始和结束日期')
  const time = new Date(`${value}T00:00:00+08:00`)
  if (!Number.isFinite(time.getTime()) || beijingInput(time) !== value) throw new Error('开始或结束日期无效')
  // 后端查询包含结束时刻，覆盖结束日期的最后一微秒。
  return boundary==='end' ? new Date(time.getTime()+86400000-1).toISOString().replace('.999Z','.999999Z') : time.toISOString()
}
export function validateFinanceQuery(shopIds: number[], start: string, end: string): string {
  if (!shopIds.length) return '请至少选择一个店铺'
  return validateFinanceDateRange(start,end)
}
export function validateFinanceDateRange(start: string, end: string): string {
  if (!start || !end) return '请选择开始和结束日期'
  try {
    const delta = (Date.parse(financeInstant(end,'end')) - Date.parse(financeInstant(start))) / 1000
    if (delta <= 0) return '开始日期不能晚于结束日期'
    if (delta > financeWindowSeconds) return '查询范围最多 180 天（含开始和结束当天）'
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

// 金额按整数分运算，避免临时成本和大额利润发生浮点误差。
export function financeOverviewAmounts(profit: string|null, costs: string[]) {
  const error = costs.map(value => value.trim() ? validateFinanceUnitCost(value) : '').find(Boolean) || ''
  if (error) return {otherCost:null, profit:null, error}
  function cents(value:string):bigint {
    const text=value.trim() || '0', negative=text.startsWith('-')
    const [whole, fraction='']=text.replace(/^-/, '').split('.')
    const result=BigInt(whole)*100n + BigInt(fraction.padEnd(2,'0'))
    return negative ? -result : result
  }
  function money(value:bigint):string {
    const absolute=value<0n ? -value : value
    return `${value<0n ? '-' : ''}${absolute/100n}.${String(absolute%100n).padStart(2,'0')}`
  }
  const total=costs.reduce((sum,value)=>sum+cents(value),0n)
  return {otherCost:money(total),profit:profit===null ? null : money(cents(profit)-total),error:''}
}


export const financeDatePresets = [
  {key:'today',label:'今天'}, {key:'yesterday',label:'昨天'},
  {key:'last7',label:'近7天'}, {key:'last30',label:'近30天'}, {key:'last90',label:'近90天'},
  {key:'thisWeek',label:'本周'}, {key:'lastWeek',label:'上周'},
  {key:'thisMonth',label:'本月'}, {key:'lastMonth',label:'上月'},
] as const
export type FinanceDatePreset = typeof financeDatePresets[number]['key']

export function shiftFinanceDate(value:string, days:number):string {
  financeInstant(value)
  return new Date(Date.parse(`${value}T00:00:00Z`)+days*86400000).toISOString().slice(0,10)
}
export function financeMonth(value:string, offset=0):string {
  financeInstant(value)
  const [year,month]=value.split('-').map(Number)
  return new Date(Date.UTC(year,month-1+offset,1)).toISOString().slice(0,10)
}
export function financeMonthGrid(month:string) {
  const first=financeMonth(month), weekday=new Date(`${first}T00:00:00Z`).getUTCDay()
  return Array.from({length:6},(_,week)=>Array.from({length:7},(_,day)=>{
    const date=shiftFinanceDate(first,week*7+day-weekday)
    return {date,day:Number(date.slice(-2)),inMonth:date.slice(0,7)===first.slice(0,7)}
  }))
}
export function financeRangePreset(key:FinanceDatePreset, now=new Date()) {
  const today=beijingInput(now)
  let start=today,end=today
  if (key==='yesterday') start=end=shiftFinanceDate(today,-1)
  if (key==='last7' || key==='last30' || key==='last90') start=shiftFinanceDate(today,-(Number(key.slice(4))-1))
  if (key==='thisWeek' || key==='lastWeek') {
    // 自然周按周一到周日；本周截至今天，上周为完整一周。
    const weekday=(new Date(`${today}T00:00:00Z`).getUTCDay()+6)%7
    start=shiftFinanceDate(today,-weekday-(key==='lastWeek' ? 7 : 0))
    if (key==='lastWeek') end=shiftFinanceDate(start,6)
  }
  if (key==='thisMonth') start=financeMonth(today)
  if (key==='lastMonth') {
    start=financeMonth(today,-1)
    end=shiftFinanceDate(financeMonth(today),-1)
  }
  return {start,end}
}
export function financeRangeSpan(start:string,end:string):number {
  return Math.abs(Date.parse(financeInstant(end))-Date.parse(financeInstant(start)))/86400000+1
}
