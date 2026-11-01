import type { PersistentTitleGroup } from './persistent-title-generation.ts'

export const titleMarkets = {
  MY: { site: 'MY', language: 'ms', siteName: '马来西亚', languageName: '马来语' },
  ID: { site: 'ID', language: 'id', siteName: '印尼', languageName: '印尼语' },
} as const
export type TitleSite = keyof typeof titleMarkets
export const titleMarket = (site: TitleSite) => titleMarkets[site]
export const titleMarketParams = (site: TitleSite) => ({ site, language: titleMarkets[site].language })

// 保留标题文本；旧词库生成结果必须重新生成或由运营明确手动确认。
export function invalidateTitleMarket(groups: PersistentTitleGroup[]) {
  for (const group of groups) {
    if (!group.manualTitle && (group.generation_id || group.titleMarketStale)) {
      group.titleMarketStale = true
      group.titleStatus = 'idle'
      group.titleError = '站点已切换，请重新生成词库标题或手动编辑确认'
    }
    group.generation_id = undefined
    group.titleWarnings = []
    group.titleKeywords = []
  }
}
