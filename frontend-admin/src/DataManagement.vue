<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import axios from 'axios'
import { summarizeShopSales } from './shop-sales'

const props = defineProps<{ token: string; companies: { id: number; name: string }[] }>()
const emit = defineEmits<{ unauthorized: [] }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001' })
const tab = ref<'materials' | 'products'>('materials')
const companyId = ref<number | null>(null)
const templates = ref<any[]>([]), members = ref<any[]>([]), shops = ref<any[]>([])
const templateId = ref(''), creatorId = ref(''), usageStatus = ref('unused')
const category = ref('products'), sourceIds = ref<number[]>([]), sku = ref(''), shopSearch = ref('')
const rows = ref<any[]>([]), total = ref(0), page = ref(1), pageSize = ref(20)
const loading = ref(false), error = ref(''), snapshotDate = ref<string | null>(null), throughDate = ref('')
const preview = ref<{ url: string; title: string } | null>(null)
const orderProduct = ref<any>(null), orders = ref<any[]>([]), orderTotal = ref(0), orderCount = ref(0), orderPage = ref(1)
const orderLoading = ref(false), orderError = ref('')
const appliedSourceIds = ref<number[]>([])
let requestId = 0, orderRequestId = 0
const categories = [
  ['products', '排行榜'], ['top7', '7天热销TOP50'], ['top15', '15天热销TOP50'], ['top30', '30天热销TOP50'],
  ['potential', '潜力款'], ['hot', '热销款'], ['booming', '旺款'], ['stagnant', '滞销款'], ['new_images', '新图'], ['shops', '店铺数据'],
]
const descriptions: Record<string, string> = { stagnant: '素材创建超过 90 天且历史累计 0 订单', new_images: '近 5 天新增的素材', potential: '近7天销量大于30', hot: '近7天销量大于70', booming: '近7天销量大于130' }
const isMaterial = computed(() => tab.value === 'materials' || ['stagnant', 'new_images'].includes(category.value))
const isShops = computed(() => tab.value === 'products' && category.value === 'shops')
const isRanking = computed(() => tab.value === 'products' && !isMaterial.value && !isShops.value && category.value !== 'products')
const isTop = computed(() => isRanking.value && ['top7', 'top15', 'top30'].includes(category.value))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const shopOptions = computed(() => shops.value.filter(item => item.label.toLowerCase().includes(shopSearch.value.toLowerCase())))
const headers = computed(() => ({ Authorization: `Bearer ${props.token}` }))
function imageUrl(url: string) { return url?.startsWith('/') ? `${api.defaults.baseURL}${url}` : url }
function date(value: number | null) { return value == null ? '—' : new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }
function message(e: any, fallback: string) {
  if (e.response?.status === 401) emit('unauthorized')
  return typeof e.response?.data?.detail === 'string' ? e.response.data.detail : fallback
}
function resetFilters() {
  templateId.value = ''; creatorId.value = ''; sourceIds.value = []; sku.value = ''; shopSearch.value = ''
  usageStatus.value = tab.value === 'materials' ? 'unused' : 'all'
  page.value = 1; preview.value = null; closeOrders()
}
function closeOrders() { orderRequestId++; orderProduct.value = null; orders.value = []; orderError.value = ''; orderLoading.value = false }
async function refresh(withFilters = true) {
  const id = ++requestId
  rows.value = []; total.value = 0; snapshotDate.value = null; error.value = ''
  if (!companyId.value) { loading.value = false; return }
  loading.value = true
  const selectedCompany = companyId.value
  const params: Record<string, any> = { company_id: selectedCompany, page: isTop.value ? 1 : page.value, page_size: isTop.value ? 50 : pageSize.value }
  if (tab.value === 'materials') Object.assign(params, { usage_status: usageStatus.value, creator_id: creatorId.value || undefined, template_id: templateId.value || undefined })
  else if (!isShops.value) {
    params.category = category.value
    if (isMaterial.value) Object.assign(params, { creator_id: creatorId.value || undefined, usage_status: usageStatus.value })
    else {
      params.source_ids = sourceIds.value.length ? sourceIds.value : undefined
      if (!isRanking.value) Object.assign(params, { sku: sku.value.trim() || undefined, template_id: templateId.value && templateId.value !== 'unmatched' ? templateId.value : undefined, unmatched: templateId.value === 'unmatched' || undefined })
    }
  }
  try {
    const [list, filters] = await Promise.all([
      api.get(`/admin/data/${tab.value === 'materials' ? 'materials' : isShops.value ? 'shops' : 'products'}`, { headers: headers.value, params, paramsSerializer: { indexes: null } }),
      withFilters ? api.get('/admin/data/filters', { headers: headers.value, params: { company_id: selectedCompany } }) : Promise.resolve(null),
    ])
    if (id !== requestId) return
    rows.value = isShops.value ? list.data : list.data.items.map((row: any) => ({ ...row, shop_sales: summarizeShopSales(row.shop_data) }))
    appliedSourceIds.value = [...(params.source_ids || [])]
    total.value = isShops.value ? list.data.length : list.data.total
    page.value = list.data.page ?? 1
    snapshotDate.value = list.data.snapshot_date ?? null; throughDate.value = list.data.through_date ?? ''
    if (filters) { templates.value = filters.data.templates; members.value = filters.data.members; shops.value = filters.data.shops }
  } catch (e: any) { if (id === requestId) error.value = message(e, '加载数据失败，请重试') }
  finally { if (id === requestId) loading.value = false }
}
function search() { page.value = 1; closeOrders(); void refresh(false) }
function changePage(next: number) { page.value = next; void refresh(false) }
function changeTab(next: 'materials' | 'products') { if (tab.value === next) return; tab.value = next; category.value = 'products'; resetFilters(); void refresh() }
function changeCategory() { resetFilters(); void refresh() }
watch(companyId, () => { templates.value = []; members.value = []; shops.value = []; resetFilters(); void refresh() })
watch(() => props.companies, (companies) => {
  if (!companies.some(item => item.id === companyId.value)) companyId.value = companies[0]?.id ?? null
}, { immediate: true })
async function loadOrders() {
  const id = ++orderRequestId
  orderLoading.value = true; orderError.value = ''; orders.value = []
  try {
    const { data } = await api.get(`/admin/data/products/${orderProduct.value.id}/orders`, { headers: headers.value, params: {
      company_id: companyId.value, page: orderPage.value, page_size: 20, source_ids: appliedSourceIds.value.length ? appliedSourceIds.value : undefined,
      category: isRanking.value ? category.value : undefined, snapshot_date: isRanking.value ? snapshotDate.value : undefined,
    }, paramsSerializer: { indexes: null } })
    if (id !== orderRequestId) return
    orders.value = data.items; orderTotal.value = data.total; orderCount.value = data.order_count
  } catch (e: any) { if (id === orderRequestId) orderError.value = message(e, '加载订单失败') }
  finally { if (id === orderRequestId) orderLoading.value = false }
}
function openOrders(row: any) { orderProduct.value = row; orderPage.value = 1; orderTotal.value = 0; orderCount.value = 0; void loadOrders() }
function changeOrderPage(next: number) { orderPage.value = next; void loadOrders() }
onBeforeUnmount(() => { requestId++; orderRequestId++ })
defineExpose({ refresh })
</script>

<template>
  <section class="data-management panel">
    <div class="heading"><h2>平台数据</h2><p>按公司查看素材库与产品库数据，仅供查阅。</p></div>
    <div class="data-tabs" role="tablist" aria-label="数据管理">
      <button v-for="item in [{key:'materials' as const,label:'素材库'},{key:'products' as const,label:'产品库'}]" :id="`data-tab-${item.key}`" :key="item.key" role="tab" :aria-selected="tab===item.key" aria-controls="data-tab-panel" :class="{active:tab===item.key}" @click="changeTab(item.key)">{{item.label}}</button>
    </div>
    <div id="data-tab-panel" role="tabpanel" :aria-labelledby="`data-tab-${tab}`">
      <form class="data-filters" @submit.prevent="search">
        <label>公司<select v-model="companyId" :disabled="!companies.length"><option :value="null" disabled>请选择公司</option><option v-for="company in companies" :key="company.id" :value="company.id">{{company.name}}</option></select></label>
        <label v-if="tab==='products'">数据分类<select v-model="category" @change="changeCategory"><option v-for="item in categories" :key="item[0]" :value="item[0]">{{item[1]}}</option></select></label>
        <template v-if="isMaterial">
          <label v-if="tab==='materials' || category==='new_images'">使用状态<select v-model="usageStatus"><option v-if="category==='new_images' && tab==='products'" value="all">全部状态</option><option value="unused">未使用</option><option value="used">已使用</option></select></label>
          <label v-if="tab==='materials'">产品模板<select v-model="templateId"><option value="">全部模板</option><option v-for="item in templates" :key="item.id" :value="String(item.id)">{{item.name}}</option></select></label>
          <label>创作人<select v-model="creatorId"><option value="">全部创作人</option><option v-for="item in members" :key="item.id" :value="String(item.id)">{{item.name}}</option></select></label>
        </template>
        <template v-else-if="!isShops">
          <div class="data-shop-filter"><span>店铺名称</span><details><summary>{{sourceIds.length ? `已选 ${sourceIds.length} 家店铺` : '全部店铺'}} ▾</summary><div class="data-shop-options"><input v-model="shopSearch" type="search" placeholder="搜索平台、站点或店铺" aria-label="搜索店铺"/><button type="button" class="secondary" @click="sourceIds=[]">清空选择</button><label v-for="shop in shopOptions" :key="shop.id"><input v-model="sourceIds" type="checkbox" :value="shop.id"/>{{shop.label}}</label><p v-if="!shopOptions.length">没有匹配的店铺</p></div></details></div>
          <template v-if="!isRanking"><label>模板<select v-model="templateId"><option value="">全部模板</option><option value="unmatched">未匹配</option><option v-for="item in templates" :key="item.id" :value="String(item.id)">{{item.name}}</option></select></label><label>SKU<input v-model="sku" type="search" placeholder="输入 SKU 前缀"/></label></template>
        </template>
        <button class="primary" type="submit" :disabled="loading || !companyId">搜索</button>
      </form>
      <p v-if="tab==='products' && descriptions[category]" class="data-note">{{descriptions[category]}}</p>
      <p v-if="isRanking && snapshotDate" class="data-note">{{snapshotDate}} 榜单 · 统计截至 {{throughDate}}</p>
      <p v-if="error" class="error data-note" role="alert">{{error}}</p>
      <div class="data-table-scroll" :aria-busy="loading">
        <table class="data-table">
          <thead><tr v-if="isShops"><th>平台</th><th>站点</th><th>店铺名称</th><th>负责人</th></tr><tr v-else><th v-if="isRanking">名次</th><th>缩略图</th><th>SKU</th><th>模板</th><template v-if="isMaterial"><th v-if="tab==='materials'">类型</th><th v-if="category==='new_images' && tab==='products'">使用状态</th><th>创建时间</th><th>创作人</th></template><template v-else><th>标题</th><th>店铺数据（店铺-销量）</th><th>创作人</th><th>创建时间</th><th>订单数</th><th>销量</th><th>订单详情</th></template></tr></thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <template v-if="isShops"><td>{{row.platform}}</td><td>{{row.site}}</td><td>{{row.shop_name}}</td><td>{{row.assigned_user_name || '未分配'}}</td></template>
              <template v-else><td v-if="isRanking">#{{row.rank}}</td><td><button v-if="row.url || row.image_url" class="data-thumbnail" type="button" :aria-label="`预览 ${row.sku || row.name}`" @click="preview={url:imageUrl(row.url || row.image_url), title:row.name || row.title || row.sku}"><img :src="imageUrl(row.url || row.image_url)" :alt="row.name || row.title || row.sku" loading="lazy"/></button><span v-else>暂无图片</span></td><td><code>{{row.sku || '无 SKU'}}</code></td><td>{{row.template_name || row.template || '—'}}</td>
                <template v-if="isMaterial"><td v-if="tab==='materials'">{{row.source_type==='ai_created'?'AI创作':'本地上传'}}<small v-if="row.source_task_id">任务 #{{row.source_task_id}}</small></td><td v-if="category==='new_images' && tab==='products'">{{row.usage_status==='used'?'已使用':'未使用'}}</td><td>{{date(row.created_at)}}</td><td>{{row.created_by_name || '历史记录缺失'}}</td></template>
                <template v-else><td class="data-title">{{row.title || '—'}}</td><td><small v-for="shop in row.shop_sales" :key="shop.source_id">{{shop.shop_name}}-{{shop.sales_quantity}}</small></td><td>{{row.material_created_by_name || '—'}}</td><td>{{date(row.material_created_at)}}</td><td>{{row.order_count}}</td><td>{{row.sales_quantity}}</td><td><button class="secondary" type="button" @click="openOrders(row)">查看</button></td></template>
              </template>
            </tr>
          </tbody>
        </table>
        <p v-if="loading" class="data-empty" role="status">正在加载数据…</p>
        <p v-else-if="!companyId" class="data-empty">{{companies.length?'请选择公司查看数据。':'暂无公司。'}}</p>
        <p v-else-if="!rows.length && !error" class="data-empty">{{isRanking && !snapshotDate?'该公司暂无榜单快照。':'没有符合筛选条件的数据。'}}</p>
      </div>
      <footer class="data-pagination"><span>共 {{total}} 条</span><template v-if="!isShops && !isTop"><label>每页 <select v-model.number="pageSize" :disabled="loading" @change="search"><option v-for="size in [20,50,100,200]" :key="size" :value="size">{{size}}</option></select> 条</label><button class="secondary" :disabled="loading || page<=1" @click="changePage(page-1)">上一页</button><span>第 {{page}} / {{pageCount}} 页</span><button class="secondary" :disabled="loading || page>=pageCount" @click="changePage(page+1)">下一页</button></template></footer>
    </div>
  </section>
  <div v-if="preview" class="modal-backdrop" @click.self="preview=null"><section class="data-preview" role="dialog" aria-modal="true" aria-label="图片预览"><button class="secondary" autofocus @click="preview=null">关闭</button><img :src="preview.url" :alt="preview.title"/><p>{{preview.title}}</p></section></div>
  <div v-if="orderProduct" class="modal-backdrop" @click.self="closeOrders"><section class="data-orders" role="dialog" aria-modal="true" aria-labelledby="data-orders-title"><button class="secondary" @click="closeOrders">关闭</button><h2 id="data-orders-title">订单详情</h2><p>{{orderProduct.sku}}</p><p v-if="orderError" class="error" role="alert">{{orderError}}</p><div class="data-table-scroll"><table class="data-table"><thead><tr><th>下单时间</th><th>订单编号</th><th>店铺</th><th>产品 ID</th><th>数量</th></tr></thead><tbody><tr v-for="(order,index) in orders" :key="index"><td>{{date(order.ordered_at)}}</td><td>{{order.order_number}}</td><td>{{order.shop_name}}</td><td>{{order.product_id}}</td><td>{{order.quantity}}</td></tr></tbody></table><p v-if="orderLoading" role="status">正在加载订单…</p><p v-else-if="!orders.length && !orderError">暂无订单。</p></div><footer class="data-pagination"><span>共 {{orderCount}} 单 · {{orderTotal}} 条明细</span><button class="secondary" :disabled="orderLoading || orderPage<=1" @click="changeOrderPage(orderPage-1)">上一页</button><span>第 {{orderPage}} / {{Math.max(1,Math.ceil(orderTotal/20))}} 页</span><button class="secondary" :disabled="orderLoading || orderPage>=Math.ceil(orderTotal/20)" @click="changeOrderPage(orderPage+1)">下一页</button></footer></section></div>
</template>

<style scoped>
.data-tabs{display:flex;gap:24px;padding:0 24px;border-bottom:1px solid #e4e8f0}.data-tabs button{padding:18px 4px;background:none;color:#778195;font-weight:700;border-bottom:3px solid transparent}.data-tabs button.active{color:#2167e8;border-bottom-color:#2167e8}.data-filters{display:flex;align-items:end;flex-wrap:wrap;gap:16px;padding:24px}.data-filters>label,.data-shop-filter{display:grid;gap:8px;font-size:13px;font-weight:600;color:#596273;min-width:150px}.data-filters select,.data-filters input[type=search],summary{padding:10px 12px;border:1px solid #d8deea;background:#fff;border-radius:8px;font:inherit;min-height:40px;max-width:260px}.data-filters>button{min-height:40px}.data-filters select{width:100%}.data-shop-filter details{position:relative}summary{cursor:pointer}.data-shop-options{position:absolute;top:46px;left:0;z-index:10;background:#fff;border:1px solid #d8deea;border-radius:10px;box-shadow:0 10px 30px #15203320;width:330px;max-width:80vw;max-height:340px;overflow:auto;padding:12px;display:grid;gap:12px}.data-shop-options label{display:flex;align-items:center;gap:8px;font-weight:400}.data-note{padding:0 24px;color:#778195;font-size:13px}.data-note.error{color:#c43f56}.data-table-scroll{overflow:auto}.data-table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}.data-table th{background:#f6f8fc;color:#778195;font-size:12px;white-space:nowrap}.data-table td,.data-table th{padding:14px 18px;border-bottom:1px solid #edf0f5}.data-table td{vertical-align:middle;min-width:90px}.data-table code{white-space:nowrap}.data-table small{display:block;line-height:1.6;min-width:120px}.data-table td.data-title{min-width:230px;max-width:330px;overflow-wrap:anywhere}.data-thumbnail{display:block;padding:0;width:64px;height:80px;border:1px solid #e4e8f0;border-radius:7px;background:#f6f8fc;overflow:hidden}.data-thumbnail img{width:100%;height:100%;object-fit:contain}.data-empty{text-align:center;padding:40px;color:#778195}.data-pagination{display:flex;justify-content:flex-end;align-items:center;flex-wrap:wrap;gap:14px;padding:20px 24px;color:#778195;font-size:13px}.data-pagination>span:first-child{margin-right:auto}.data-pagination select{border:1px solid #d8deea;padding:6px;border-radius:6px}.data-preview,.data-orders{background:#fff;padding:24px;border-radius:14px;max-height:90vh;overflow:auto;width:min(1100px,calc(100vw - 40px))}.data-preview{width:auto;max-width:calc(100vw - 40px);text-align:center}.data-preview img{display:block;max-width:100%;max-height:70vh;margin:16px auto;object-fit:contain}.data-preview>button,.data-orders>button{float:right}.data-orders h2{margin-top:0}button:disabled{opacity:.5;cursor:not-allowed}button:focus-visible,summary:focus-visible{outline:2px solid #2167e8;outline-offset:3px}@media(max-width:620px){.data-filters>label,.data-shop-filter{flex:1;min-width:130px}.data-filters{padding:20px;gap:12px}.data-filters select,.data-filters input{max-width:100%}.data-pagination{justify-content:center}.data-pagination>span:first-child{margin-right:0}}
</style>
