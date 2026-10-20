export interface SupplyUsageTask {
  job_id: number; user_id: number; user_name: string | null; agent_name: string | null;
  link_count: number; completed_at: number | null;
}
// 请求取消与序号校验同时使用，已完成但尚未处理的旧响应也不能回写。
export function createSupplyRequestScope() {
  let version = 0
  let controller: AbortController | undefined
  function invalidate() { version++; controller?.abort(); controller = undefined }
  return {
    invalidate,
    start() {
      invalidate()
      const current = version
      controller = new AbortController()
      return { signal: controller.signal, isCurrent: () => current === version }
    },
  }
}
export const supplyJobLabels: Record<string, string> = {
  queued: '排队中', running: '运行中', retry_wait: '等待重试', completed: '已完成', failed: '失败', cancelled: '已取消',
}
export const supplyStageLabels: Record<string, string> = {
  queued: '等待处理', allocating: '组织商品草稿', drafts: '组织商品草稿', titles: '生成标题',
  excel: '生成 Excel', exporting: '生成 Excel',
  upload: '上传 Excel', uploading: '上传 Excel', completed: '已完成', cancelled: '已取消', failed: '失败',
}
export function unfinishedSupplyJob(job: { state: string }): boolean {
  return ['queued', 'running', 'retry_wait'].includes(job.state)
}
export function supplyTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const date = new Date(typeof value === 'string' && !/[zZ]|[+-]\d\d:\d\d$/.test(value) && value.includes('T') ? `${value}Z` : value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { timeZone: 'Asia/Hong_Kong' })
}
export function supplyFileStatus(job: { state: string; file_expired?: boolean; output_expires_at?: string | number | null }, now = Date.now()): string {
  if (job.file_expired) return '文件已过期'
  if (job.output_expires_at) {
    const parsed = new Date(job.output_expires_at).getTime()
    if (Number.isFinite(parsed) && parsed <= now) return '文件已过期'
  }
  return job.state === 'completed' ? '可下载' : ''
}
export interface SupplyStrategyForm {
  infringement_filter: 'exclude' | 'include' | 'only';
  name: string; category_catalog_id: number | null; category_name: string; template_id: number | null;
  price: string | number; stock: number; cod: string; attributes: Record<string, string>; sku_count: number;
  link_count: number; title_requirements: string;
}
export function emptySupplyStrategy(): SupplyStrategyForm {
  return { infringement_filter: 'exclude', name: '', category_catalog_id: null, category_name: '', template_id: null, price: '', stock: 999,
    cod: 'Y', attributes: {}, sku_count: 5, link_count: 10, title_requirements: '' }
}
export function supplyStrategyPayload(form: SupplyStrategyForm): SupplyStrategyForm {
  return {
    infringement_filter: form.infringement_filter ?? 'include',
    name: form.name.trim(), category_catalog_id: form.category_catalog_id, category_name: form.category_name,
    template_id: form.template_id, price: String(form.price), stock: form.stock, cod: form.cod,
    attributes: { ...form.attributes }, sku_count: form.sku_count, link_count: form.link_count,
    title_requirements: form.title_requirements,
  }
}
export function validateSupplyStrategy(form: SupplyStrategyForm, sizeCount: number, attributes: { field: string; label?: string; required?: boolean }[] = []): string {
  if (!['exclude', 'include', 'only'].includes(form.infringement_filter)) return '请选择有效的侵权筛选条件'
  if (!form.name.trim()) return '请填写策略名称'
  if (!form.category_catalog_id || !form.category_name) return '请选择类目库和商品类目'
  if (!form.template_id) return '请选择公开产品模板'
  if (!Number.isFinite(Number(form.price)) || Number(form.price) <= 0) return '售价必须大于零'
  if (!Number.isInteger(form.stock) || form.stock < 0) return '库存必须为非负整数'
  if (!Number.isInteger(form.sku_count) || form.sku_count < 5 || form.sku_count > 9) return '每个链接须使用 5–9 个素材 SKU'
  if (!Number.isInteger(form.link_count) || form.link_count < 10 || form.link_count > 50) return '链接数量须为 10–50 个'
  if (Math.max(1, sizeCount) * form.sku_count * form.link_count > 4994) return '预计数据行数超过 4,994 行，请减少链接数量或每个链接的 SKU 数量'
  const missing = attributes.find(field => field.required && !form.attributes[field.field]?.trim())
  return missing ? `请填写必填属性：${missing.label || missing.field}` : ''
}
// A retry of an uncertain submission must reuse the same key; changing strategy means a new intent.
export function createSupplySubmissionKeys(createKey: () => string) {
  let pending: { strategyId: number; key: string } | null = null
  return {
    forStrategy(strategyId: number): string {
      if (!pending || pending.strategyId !== strategyId) pending = { strategyId, key: createKey() }
      return pending.key
    },
    complete() { pending = null },
  }
}
