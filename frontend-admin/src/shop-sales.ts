type ShopSales = { source_id: number; shop_name: string; sales_quantity: number }

// 按店铺来源汇总，同名但属于不同平台或站点的店铺保持独立。
export function summarizeShopSales(items: ShopSales[] = []): ShopSales[] {
  const shops = new Map<number, ShopSales>()
  for (const item of items) {
    const shop = shops.get(item.source_id)
    if (shop) shop.sales_quantity += item.sales_quantity
    else shops.set(item.source_id, { source_id: item.source_id, shop_name: item.shop_name, sales_quantity: item.sales_quantity })
  }
  return [...shops.values()]
}
