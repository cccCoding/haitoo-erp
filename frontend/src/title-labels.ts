// 界面统一使用“面料”；保留旧数据字段，避免改写历史任务和词条编码。
export function titleTagLabel(value: string | null | undefined): string {
  return value === '材质' ? '面料' : value || ''
}
