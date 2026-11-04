export type ConfirmedKeyword = {
  id: number; phrase: string; translation: string; categories: string[]; semantic_tag: string
}
export type LegacyAttribute = { tag: string; value: string }
const normalized = (value: string) => value.normalize('NFKC').trim().toLowerCase().replace(/\s+/g, ' ')

// 旧确认值只做原词、中文释义的精确匹配；有冲突或无匹配时交由人工处理。
export function resolveConfirmedChoice(ids: number[], legacy: LegacyAttribute[], options: ConfirmedKeyword[]) {
  if (ids.length || !legacy.length) return { ids: [...new Set(ids)], warning: '' }
  const values = new Set(legacy.map(item => normalized(item.value)))
  const matches = options.filter(word => [word.phrase, word.translation].some(value => values.has(normalized(value))))
  if (values.size === 1 && matches.length) return { ids: matches.map(word => word.id), warning: '' }
  return { ids: [], warning: legacy.map(item => `${item.tag}：${item.value}`).join('；') }
}
