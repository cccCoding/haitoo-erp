import { titleMarkets } from './title-markets'

export const categorySites = Object.values(titleMarkets).map(market => ({
  code: market.site,
  name: market.siteName,
}))

export function categorySiteLabel(site: string) {
  return categorySites.find(item => item.code === site)?.name || site
}
