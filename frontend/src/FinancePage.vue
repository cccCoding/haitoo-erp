<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { defaultFinanceShop, financeDefaults, financeInstant, financeOverviewAmounts, financeQueryKey, validateFinanceQuery, validateFinanceUnitCost } from './finance'
import { dialogFocus as vDialogFocus } from './dialog-focus'
import SearchableSelect from './SearchableSelect.vue'
import FinanceDateRangePicker from './FinanceDateRangePicker.vue'

type ShopType = 'cross_border'|'local'
type Shop = {id:number; name:string; shop_type:ShopType; has_platform_data:boolean}
type Rate = {shop_id:number; currency:string; rate:string|null}
type Sku = {shop_id:number; shop_name:string; base_sku:string; quantity:number; order_count:number; unit_cost:string|null; total_cost:string|null}
type Order = {id:number; shop_id:number; shop_name:string; shop_type:ShopType; order_number:string; paid_at:string; sales:string|null; settlement:string|null; cost:string|null; profit:string|null; statuses:string[]; currencies:any[]; items:any[]; bills:any[]}
type Summary = {shop_id:number|null; shop_name:string; order_count:number; converted_count:number; calculated_count:number; pending_count:number; erp_only_count:number; sales:string|null; settlement:string|null; cost:string|null; profit:string|null}
type Results = {summaries:Summary[]; total:Summary; orders:{items:Order[]; total:number}; skus:{items:Sku[]; total:number}}
const props = defineProps<{token:string; user:any}>()
const emit = defineEmits<{unauthorized:[]}>()
const api = axios.create({baseURL:import.meta.env.VITE_API_URL || 'http://localhost:8000'})
const auth = () => ({headers:{Authorization:`Bearer ${props.token}`}})
const storageKey = `haitoro_finance_shop_${props.user.company_id}_${props.user.id}`
const shops = ref<Shop[]>([]), selectedShopIds = ref<number[]>([]), shopSearch = ref('')
const shopDropdown = ref<HTMLDetailsElement|null>(null)
function closeShopDropdownOutside(event: PointerEvent) {
  const dropdown = shopDropdown.value
  if (dropdown?.open && event.target instanceof Node && !dropdown.contains(event.target)) dropdown.open=false
}
const defaults = financeDefaults(), start = ref(defaults.start), end = ref(defaults.end)
const applied = ref<{ids:number[]; start:string; end:string}|null>(null)
const results = ref<Results|null>(null), pending = ref<{items:any[];total:number}>({items:[],total:0})
const orderPage = ref(1), skuPage = ref(1), pendingPage = ref(1)
const orderPageSize = ref(20), skuPageSize = ref(20), pendingPageSize = ref(20), pageSizes = [20,50,100,500,1000]
const skuSearch = ref(''), appliedSkuSearch = ref(''), selectedSkus = ref<string[]>([])
const skuCostStatus = ref('all'), appliedSkuCostStatus = ref('all')
const orderStatus = ref('all'), appliedOrderStatus = ref('all')
const orderStatuses = [['all','全部'],['calculated','已核算'],['pending','待核算']]
const rates = ref<Rate[]>([]), rateInputs = ref<Record<string,string>>({})
const loading = ref(false), saving = ref(false), initializing = ref(true), error = ref(''), notice = ref('')
const tab = ref('orders'), detail = ref<Order|null>(null), showShopSettings = ref(false)
const managedShopSearch = ref(''), editingShopId = ref<number|null>(null), shopNameInput = ref<HTMLInputElement|null>(null)
const shopDraftName = ref(''), shopDraftType = ref<ShopType>('cross_border'), shopFormError = ref(''), shopFormNotice = ref('')
const showImport = ref(false), importShopId = ref<number|null>(null), importKind = ref<'platform'|'erp'>('platform'), importFile = ref<File|null>(null)
const importSheets = ref<string[]>([]), importSheet = ref(''), importError = ref(''), fileInputKey = ref(0)
const history = ref<any[]>([])
const showCostDialog = ref(false), costDialogSkus = ref<{shop_id:number; base_sku:string}[]>([]), unitCost = ref(''), costFormError = ref('')
const otherCostInputs = ref<Record<number,string>>({}), exporting = ref('')
let generation = 0, disposed = false
const shopOptions = computed(() => shops.value.filter(s => s.name.toLowerCase().includes(shopSearch.value.trim().toLowerCase())))
const managedShops = computed(() => shops.value.filter(s => s.name.toLowerCase().includes(managedShopSearch.value.trim().toLowerCase())))
const editingShop = computed(() => shops.value.find(s => s.id===editingShopId.value))
const shopFormChanged = computed(() => !editingShop.value || shopDraftName.value.trim()!==editingShop.value.name || shopDraftType.value!==editingShop.value.shop_type)
const queryError = computed(() => validateFinanceQuery(selectedShopIds.value, start.value, end.value))
const dirty = computed(() => !!applied.value && financeQueryKey(selectedShopIds.value,start.value,end.value) !== financeQueryKey(applied.value.ids,applied.value.start,applied.value.end))
const summaryRows = computed(() => results.value ? [...results.value.summaries, ...(results.value.summaries.length>1 ? [results.value.total] : [])].map(row=>({
  ...row, ...financeOverviewAmounts(row.profit,row.shop_id===null ? results.value!.summaries.map(s=>otherCostInputs.value[s.shop_id!] || '') : [otherCostInputs.value[row.shop_id] || ''])
})) : [])
const allPageSelected = computed(() => !!results.value?.skus.items.length && results.value.skus.items.every(s => selectedSkus.value.includes(skuKey(s))))
const selectedRates = computed(() => rates.value.filter(r => (applied.value?.ids || selectedShopIds.value).includes(r.shop_id)))
const importShop = computed(() => shops.value.find(shop => shop.id===importShopId.value))
const importShopOptions = computed(() => shops.value.map(shop => ({value:shop.id,label:`${shop.name} · ${shopTypeLabel(shop.shop_type)}`})))
const importRule = computed(() => importKind.value==='erp' ? '同订单重复 SKU 数量相加；重导将替换该订单全部商品。' :
  importShop.value?.shop_type==='local' ? '仅读取订单交易。同店铺、同订单的行先汇总；重导覆盖该订单金额，其他订单保留。重导须包含该订单的完整账单。' :
  '同一订单、结算单、SKU 的订单交易逐行汇总，金额相同的行也计入。重导覆盖对应组，其他组保留；重导须包含对应组的全部记录。')
function shopTypeLabel(value:ShopType) { return value==='local' ? '本土店' : '跨境店' }
function shopName(id:number) { return shops.value.find(s => s.id===id)?.name || '店铺已删除' }
function amount(value:string|null) { if(value===null) return '—'; const [whole, cents='00']=value.split('.'); return `¥ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${cents.padEnd(2,'0')}` }
function date(value:string) { return new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Hong_Kong',hour12:false}) }
function rateKey(rate:Rate) { return `${rate.shop_id}:${rate.currency}` }
function fail(e:any) {
  if (e.response?.status===401) emit('unauthorized')
  const value = e.response?.data?.detail
  const message = typeof value==='string' ? value : value?.message || '操作失败，请重试'
  error.value = message
  return message
}
async function settings() {
  const {data} = await api.get('/finance/settings',auth())
  if (disposed) return
  rates.value = data.rates
  rateInputs.value = Object.fromEntries(rates.value.map(r => [rateKey(r),r.rate ?? '']))
}
async function loadHistory() { const {data} = await api.get('/finance/imports',auth()); if (!disposed) history.value=data }
async function loadShops() {
  const {data}=await api.get('/finance/shops',auth()); if (disposed) return
  shops.value=data
}
function closeShopSettings() { if (!saving.value) showShopSettings.value=false }
async function setShopDraft(shop?:Shop) {
  editingShopId.value=shop?.id ?? null; shopDraftName.value=shop?.name ?? ''; shopDraftType.value=shop?.shop_type ?? 'cross_border'
  shopFormError.value=''; shopFormNotice.value=''
  await nextTick(); shopNameInput.value?.focus()
}
function openShopSettings() {
  managedShopSearch.value=''; showShopSettings.value=true; setShopDraft()
}
async function loadResults(next = applied.value): Promise<boolean> {
  if (!next) return false
  const id = ++generation, query = {...next, ids:[...next.ids]}
  loading.value=true; error.value=''
  try {
    const params = new URLSearchParams()
    query.ids.forEach(s => params.append('shop_ids',String(s)))
    params.set('paid_from',financeInstant(query.start)); params.set('paid_to',financeInstant(query.end,'end'))
    params.set('order_page',String(orderPage.value)); params.set('sku_page',String(skuPage.value)); params.set('sku_search',appliedSkuSearch.value)
    params.set('sku_page_size',String(skuPageSize.value))
    params.set('sku_cost_status',appliedSkuCostStatus.value)
    params.set('order_status',appliedOrderStatus.value)
    params.set('page_size',String(orderPageSize.value))
    const pendingParams = new URLSearchParams()
    query.ids.forEach(s => pendingParams.append('shop_ids',String(s)))
    pendingParams.set('page',String(pendingPage.value))
    pendingParams.set('page_size',String(pendingPageSize.value))
    const [response, missing] = await Promise.all([api.get(`/finance/results?${params}`,auth()),api.get(`/finance/pending-payment-time?${pendingParams}`,auth())])
    if (id!==generation || disposed) return false
    const orderLast=Math.max(1,Math.ceil(response.data.orders.total/orderPageSize.value)), skuLast=Math.max(1,Math.ceil(response.data.skus.total/skuPageSize.value)), pendingLast=Math.max(1,Math.ceil(missing.data.total/pendingPageSize.value))
    if (orderPage.value>orderLast || skuPage.value>skuLast || pendingPage.value>pendingLast) {
      orderPage.value=Math.min(orderPage.value,orderLast); skuPage.value=Math.min(skuPage.value,skuLast); pendingPage.value=Math.min(pendingPage.value,pendingLast)
      return await loadResults(query)
    }
    results.value=response.data; pending.value=missing.data; applied.value=query
    return true
  } catch(e:any) { if (id===generation && !disposed) fail(e); return false }
  finally { if (id===generation && !disposed) loading.value=false }
}
async function search() {
  if (queryError.value) { error.value=queryError.value; return }
  const next={ids:[...selectedShopIds.value],start:start.value,end:end.value}
  const previous={order:orderPage.value,sku:skuPage.value,pending:pendingPage.value,search:appliedSkuSearch.value,status:appliedSkuCostStatus.value}
  orderPage.value=skuPage.value=pendingPage.value=1; selectedSkus.value=[]; detail.value=null
  skuSearch.value=appliedSkuSearch.value=''
  skuCostStatus.value=appliedSkuCostStatus.value='all'
  if (selectedShopIds.value.length===1) localStorage.setItem(storageKey,String(selectedShopIds.value[0]))
  if (!await loadResults(next)) { orderPage.value=previous.order; skuPage.value=previous.sku; pendingPage.value=previous.pending; appliedSkuSearch.value=previous.search; appliedSkuCostStatus.value=previous.status }
  else otherCostInputs.value={}
}
async function exportOrders(kind:'missing-bills'|'pending-order-time',shopId:number|null=null) {
  if (!applied.value || exporting.value) return
  const key=`${kind}:${shopId ?? 'all'}`, params=new URLSearchParams()
  ;(shopId===null ? applied.value.ids : [shopId]).forEach(id=>params.append('shop_ids',String(id)))
  if (kind==='missing-bills') {
    params.set('paid_from',financeInstant(applied.value.start)); params.set('paid_to',financeInstant(applied.value.end,'end'))
  }
  exporting.value=key; error.value=''
  try {
    const {data}=await api.get(`/finance/exports/${kind}?${params}`,{...auth(),responseType:'blob'})
    const url=URL.createObjectURL(data), link=document.createElement('a')
    link.href=url; link.download=kind==='missing-bills' ? '缺后台账单订单.xlsx' : '下单时间待补订单.xlsx'
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000)
  } catch(e:any) {
    if (e.response?.data instanceof Blob) {
      try { e.response.data=JSON.parse(await e.response.data.text()) } catch {}
    }
    fail(e)
  } finally { exporting.value='' }
}
async function paginate(kind:string, delta:number) {
  const page = kind==='orders' ? orderPage : kind==='skus' ? skuPage : pendingPage
  const previous=page.value
  page.value+=delta; selectedSkus.value=[]; if (!await loadResults()) page.value=previous
}
async function searchSkus() { appliedSkuSearch.value=skuSearch.value; appliedSkuCostStatus.value=skuCostStatus.value; skuPage.value=1; selectedSkus.value=[]; await loadResults() }
async function filterOrders() {
  const previous={status:appliedOrderStatus.value,page:orderPage.value}
  appliedOrderStatus.value=orderStatus.value; orderPage.value=1; detail.value=null
  if (!await loadResults()) {
    orderStatus.value=appliedOrderStatus.value=previous.status; orderPage.value=previous.page
  }
}
async function changePageSize(kind:string, event:Event) {
  const page = kind==='orders' ? orderPage : kind==='skus' ? skuPage : pendingPage
  const size = kind==='orders' ? orderPageSize : kind==='skus' ? skuPageSize : pendingPageSize
  const previous={size:size.value,page:page.value}
  size.value=Number((event.target as HTMLSelectElement).value)
  page.value=1; selectedSkus.value=[]
  if (!await loadResults()) { size.value=previous.size; page.value=previous.page }
}
function skuKey(sku:Pick<Sku,'shop_id'|'base_sku'>) { return JSON.stringify([sku.shop_id,sku.base_sku]) }
function toggleAll() { selectedSkus.value=allPageSelected.value ? [] : results.value?.skus.items.map(s => skuKey(s)) || [] }
async function saveShop() {
  if (saving.value || !shopFormChanged.value) return
  const name=shopDraftName.value.trim(), editing=editingShop.value
  shopFormError.value=''; shopFormNotice.value=''
  if (!name) { shopFormError.value='请输入店铺名称'; shopNameInput.value?.focus(); return }
  if (shops.value.some(s => s.id!==editing?.id && s.name===name)) { shopFormError.value='已有同名店铺，请使用其他名称'; return }
  saving.value=true
  let saved=false
  try {
    const payload={name,shop_type:shopDraftType.value}
    const {data}=editing ? await api.patch(`/finance/shops/${editing.id}`,payload,auth()) : await api.post('/finance/shops',payload,auth())
    shops.value=editing ? shops.value.map(s=>s.id===data.id ? data : s) : [...shops.value,data]
    editingShopId.value=data.id; shopDraftName.value=data.name; shopDraftType.value=data.shop_type
    if (!managedShops.value.some(s=>s.id===data.id)) managedShopSearch.value=''
    if (detail.value && detail.value.shop_id===data.id) detail.value={...detail.value,shop_name:data.name,shop_type:data.shop_type}
    saved=true
    shopFormNotice.value=editing ? '店铺信息已保存' : '店铺已新增，可在导入数据时选择此店铺'
    if (!selectedShopIds.value.length) { selectedShopIds.value=[data.id]; await search() }
    else if (editing && !await loadResults()) shopFormError.value='店铺已保存，查询结果刷新失败，请关闭弹窗后重新查询'
    if (editing) await loadHistory()
  } catch(e:any) {
    if (e.response?.status===401) emit('unauthorized')
    shopFormError.value=saved ? '店铺已保存，部分数据刷新失败，请关闭弹窗后重新查询' : typeof e.response?.data?.detail==='string' ? e.response.data.detail : '保存失败，请重试'
  } finally { saving.value=false }
}
function openImport() {
  importShopId.value=null
  importFile.value=null; importSheets.value=[]; importSheet.value=''; importError.value=''; fileInputKey.value++; showImport.value=true
}
function selectImportShop(value:string|number|null) {
  importShopId.value=typeof value==='number' ? value : null
  importSheets.value=[]; importSheet.value=''; importError.value=''
}
function fileChanged(event:Event) {
  importFile.value=(event.target as HTMLInputElement).files?.[0] || null
  importSheets.value=[]; importSheet.value=''; importError.value=''
}
async function upload() {
  importError.value=''
  if (!importShopId.value || !importFile.value) { importError.value='请选择目标店铺和 XLSX 文件'; return }
  if (!/\.xlsx$/i.test(importFile.value.name) || importFile.value.size>20*1024*1024) { importError.value='仅支持不超过 20MB 的 XLSX 文件'; return }
  if (importSheets.value.length && !importSheet.value) { importError.value='请选择需要导入的工作表'; return }
  saving.value=true; error.value=''
  try {
    const data = new FormData(); data.append('file',importFile.value); if (importSheet.value) data.append('sheet_name',importSheet.value)
    const response = await api.post(`/finance/shops/${importShopId.value}/imports/${importKind.value}`,data,auth())
    const c=response.data
    notice.value=`导入成功：新增 ${c.created}，更新 ${c.updated}，未变化 ${c.unchanged} ${c.unit}；忽略非订单行 ${c.ignored}。`
    showImport.value=false; selectedSkus.value=[]
    await Promise.all([settings(),loadHistory(),loadResults(),loadShops()])
  } catch(e:any) {
    const sheets=e.response?.data?.detail?.sheets
    if (sheets) { importSheets.value=sheets; importSheet.value=''; importError.value='检测到多个订单工作表，请选择后重新导入' }
    else importError.value=fail(e)
  } finally { saving.value=false }
}
function openCostDialog() {
  if (!selectedSkus.value.length) return
  costDialogSkus.value=(results.value?.skus.items || []).filter(s => selectedSkus.value.includes(skuKey(s))).map(s => ({shop_id:s.shop_id,base_sku:s.base_sku})); unitCost.value=''; costFormError.value=''; showCostDialog.value=true
}
async function saveSkuCosts() {
  costFormError.value=validateFinanceUnitCost(unitCost.value)
  if (costFormError.value || saving.value) return
  saving.value=true; error.value=''
  try {
    const {data}=await api.put('/finance/sku-costs',{items:costDialogSkus.value,unit_cost:unitCost.value.trim()},auth())
    notice.value=`已保存 ${data.updated} 条店铺 SKU 的单件衣服成本，相关历史订单已重新核算。`
    showCostDialog.value=false; selectedSkus.value=[]; await loadResults()
  } catch(e:any) { costFormError.value=fail(e) } finally { saving.value=false }
}
async function saveRates() {
  const changedRates=selectedRates.value.filter(r=>r.currency!=='CNY' && rateInputs.value[rateKey(r)]!=='' && rateInputs.value[rateKey(r)]!==r.rate)
  const items=changedRates.map(r=>({shop_id:r.shop_id,currency:r.currency,rate:rateInputs.value[rateKey(r)]}))
  if (!items.length) { notice.value='没有需要保存的修改'; return }
  saving.value=true; error.value=''
  try {
    await api.put('/finance/exchange-rates',{items},auth())
    notice.value='汇率已保存，相关历史订单已重新核算。'
    await Promise.all([settings(),loadResults()])
  } catch(e:any) { fail(e) } finally { saving.value=false }
}
onMounted(async () => {
  document.addEventListener('pointerdown',closeShopDropdownOutside,true)
  try {
    await loadShops(); if (disposed) return
    const last=Number(localStorage.getItem(storageKey)) || null
    selectedShopIds.value=defaultFinanceShop(shops.value,last)
    await Promise.all([settings(),loadHistory()])
    if (!disposed && selectedShopIds.value.length) await search()
  } catch(e:any) { if (!disposed) fail(e) } finally { if (!disposed) initializing.value=false }
})
onUnmounted(() => { document.removeEventListener('pointerdown',closeShopDropdownOutside,true); disposed=true; generation++ })
</script>

<template>
  <section class="page finance-page">
    <header class="finance-title"><div class="finance-actions"><button class="primary" @click="openImport" :disabled="!shops.length || saving">导入数据</button><button class="primary" @click="openShopSettings" :disabled="initializing || saving">店铺管理</button></div></header>
    <p v-if="error" class="finance-alert finance-error" role="alert">{{error}}</p>
    <p v-if="notice" class="finance-alert finance-success" role="status">{{notice}}<button aria-label="关闭提示" @click="notice=''">×</button></p>
    <section class="finance-panel finance-filters" aria-label="财务查询条件">
      <div class="finance-filter-fields">
        <div class="finance-shop-field"><label id="finance-shop-label">店铺 <b>*</b></label><details ref="shopDropdown" class="finance-shop-select"><summary aria-labelledby="finance-shop-label">{{selectedShopIds.length ? `已选择 ${selectedShopIds.length} 个店铺` : '请选择店铺'}}<span>⌄</span></summary><div class="finance-shop-options"><input v-model="shopSearch" aria-label="搜索店铺" placeholder="搜索店铺名称"/><label v-for="shop in shopOptions" :key="shop.id"><input v-model="selectedShopIds" type="checkbox" :value="shop.id" :aria-label="shop.name"/>{{shop.name}}</label><p v-if="!shopOptions.length">暂无店铺</p></div></details><div class="finance-shop-tags"><span v-for="id in selectedShopIds" :key="id">{{shopName(id)}}</span></div></div>
        <FinanceDateRangePicker v-model:start="start" v-model:end="end" :disabled="saving || initializing"/>
        <button class="primary finance-query" :disabled="loading || saving || initializing || !!queryError" @click="search">{{loading ? '查询中…' : '查询'}}</button>
      </div>
      <div class="finance-filter-note"><span v-if="queryError" class="finance-invalid">{{queryError}}</span><strong v-else-if="dirty">筛选条件未应用，请点击查询</strong></div>
    </section>
    <p v-if="initializing" class="empty">正在加载财务数据…</p>
    <section v-else-if="!shops.length" class="finance-panel finance-empty"><h2>先添加一个店铺</h2><p>在店铺管理中新增店铺后，即可导入后台账单和 ERP 商品明细。</p><button class="primary" @click="openShopSettings">打开店铺管理</button></section>
    <template v-if="results">
      <section class="finance-panel" :aria-busy="loading"><div class="finance-section-title"><h2>店铺核算概览</h2><span v-if="loading">正在更新查询结果…</span><span v-else>本次查询 {{results.total.order_count}} 个后台订单</span></div>
        <p v-if="applied" class="finance-applied-range">下单日期：{{applied.start}} 至 {{applied.end}}（北京时间，含开始和结束当天）</p><div class="finance-table-scroll"><table class="finance-table finance-summary"><thead><tr><th>店铺</th><th>订单数</th><th>销售额</th><th>结算金额</th><th>衣服成本</th><th>其他成本</th><th>利润</th><th>核算进度</th></tr></thead><tbody><tr v-for="row in summaryRows" :key="row.shop_id ?? 'total'" :class="{'finance-total':row.shop_id===null}"><td><strong>{{row.shop_name}}</strong></td><td>{{row.order_count}}</td><td>{{amount(row.sales)}}<small>已换算 {{row.converted_count}} / {{row.order_count}} 单</small></td><td>{{amount(row.settlement)}}<small>已换算 {{row.converted_count}} / {{row.order_count}} 单</small></td><td>{{amount(row.cost)}}<small>已核算 {{row.calculated_count}} 单</small></td><td class="finance-other-cost"><template v-if="row.shop_id!==null"><input v-model="otherCostInputs[row.shop_id]" type="text" inputmode="decimal" :aria-label="`${row.shop_name}其他成本`" :aria-invalid="!!row.error" placeholder="输入金额"/><small v-if="row.error" class="finance-invalid">{{row.error}}</small><small v-else>人民币 · 临时计算</small></template><strong v-else>{{amount(row.otherCost)}}</strong></td><td :class="{'finance-negative':row.profit!==null && Number(row.profit)<0}"><strong>{{amount(row.profit)}}</strong><small>已核算 {{row.calculated_count}} 单</small></td><td><span class="finance-badge" :class="row.pending_count ? 'warning' : 'complete'">{{row.pending_count ? `${row.pending_count} 单待核算` : '核算完整'}}</span><div v-if="row.erp_only_count" class="finance-missing-bill-export"><span>另有 {{row.erp_only_count}} 单缺后台账单</span><button :aria-label="`导出${row.shop_name}缺后台账单订单`" :disabled="loading || !!exporting" @click="exportOrders('missing-bills',row.shop_id)">{{exporting===`missing-bills:${row.shop_id ?? 'all'}` ? '导出中…' : '导出'}}</button></div></td></tr></tbody></table></div>
        <p class="finance-footnote">销售额按后台总收入计算；概览利润＝已核算订单利润 − 其他成本。其他成本仅用于本次查询，不保存；重新查询后清空。衣服成本与订单利润仅汇总资料齐全的订单，缺失数据不按零计算。</p>
      </section>
      <section class="finance-panel finance-workspace" :aria-busy="loading">
        <nav class="finance-tabs" aria-label="财务明细"><button v-for="item in [['orders','订单明细'],['skus','成本输入'],['settings','汇率设置'],['history','导入记录']]" :key="item[0]" :class="{active:tab===item[0]}" @click="tab=item[0]">{{item[1]}}</button></nav>
        <template v-if="tab==='orders'"><div class="finance-section-title finance-order-toolbar"><select v-model="orderStatus" aria-label="订单状态" :disabled="loading || saving" @change="filterOrders"><option v-for="item in orderStatuses" :key="item[0]" :value="item[0]">{{item[1]}}</option></select><span>当前筛选条件下共 {{results.orders.total}} 单</span></div><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th>店铺 / 订单编号</th><th>下单时间</th><th>销售额</th><th>结算金额</th><th>衣服成本</th><th>利润</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in results.orders.items" :key="row.id"><td>{{row.shop_name}}<small class="finance-order-id">{{row.order_number}}</small></td><td>{{date(row.paid_at)}}</td><td>{{amount(row.sales)}}</td><td>{{amount(row.settlement)}}</td><td>{{amount(row.cost)}}</td><td :class="{'finance-negative':row.profit!==null && Number(row.profit)<0}">{{amount(row.profit)}}</td><td><span v-for="status in row.statuses" :key="status" class="finance-badge" :class="status==='已核算' ? 'complete' : 'warning'">{{status}}</span></td><td><button @click="detail=row">明细</button></td></tr><tr v-if="!results.orders.total"><td colspan="8" class="finance-empty-cell">当前筛选条件下暂无订单</td></tr></tbody></table></div><div class="finance-pagination"><span>共 {{results.orders.total}} 单 · 第 {{orderPage}} 页</span><label>每页<select aria-label="订单明细每页数量" :value="orderPageSize" :disabled="loading || saving" @change="changePageSize('orders',$event)"><option v-for="size in pageSizes" :key="size" :value="size">{{size}} 条</option></select></label><button :disabled="orderPage<=1 || loading" @click="paginate('orders',-1)">上一页</button><button :disabled="orderPage*orderPageSize>=results.orders.total || loading" @click="paginate('orders',1)">下一页</button></div></template>
        <template v-else-if="tab==='skus'">
          <div class="finance-sku-toolbar">
            <div class="finance-actions"><select v-model="skuCostStatus" aria-label="成本设置状态" :disabled="loading || saving" @change="searchSkus"><option value="all">全部状态</option><option value="set">已设置</option><option value="unset">未设置</option></select><input v-model="skuSearch" placeholder="输入基础 SKU 前缀" aria-label="搜索基础 SKU" @keyup.enter="searchSkus"/><button :disabled="loading" @click="searchSkus">搜索</button></div>
            <div class="finance-actions"><template v-if="selectedSkus.length"><span>已选 {{selectedSkus.length}} 项</span><button class="primary" :disabled="saving || loading" @click="openCostDialog">批量设置成本</button></template></div>
          </div>
          <p class="finance-footnote">按基础 SKU 前缀区分大小写搜索，数量仅涵盖当前查询。单件衣服成本以人民币保存，同一基础 SKU 仅在同一店铺内共用成本，不同店铺独立设置。</p>
          <div class="finance-table-scroll"><table class="finance-table"><thead><tr><th><input type="checkbox" aria-label="选择本页所有 SKU" :checked="allPageSelected" :disabled="loading" @change="toggleAll"/></th><th>店铺</th><th>基础 SKU</th><th>订单数</th><th>商品数量</th><th>单件衣服成本</th><th>总成本</th><th>状态</th></tr></thead><tbody><tr v-for="sku in results.skus.items" :key="skuKey(sku)"><td><input v-model="selectedSkus" type="checkbox" :value="skuKey(sku)" :aria-label="`选择 ${sku.shop_name} ${sku.base_sku}`" :disabled="loading"/></td><td>{{sku.shop_name}}</td><td><strong>{{sku.base_sku}}</strong></td><td>{{sku.order_count}}</td><td>{{sku.quantity}}</td><td>{{amount(sku.unit_cost)}}</td><td>{{amount(sku.total_cost)}}</td><td><span class="finance-badge" :class="sku.unit_cost!==null ? 'complete' : 'warning'">{{sku.unit_cost===null ? '未设置' : '已设置'}}</span></td></tr><tr v-if="!results.skus.total"><td colspan="8" class="finance-empty-cell">暂无符合条件的 SKU</td></tr></tbody></table></div>
          <div class="finance-pagination"><span>共 {{results.skus.total}} 项 · 第 {{skuPage}} 页</span><label>每页<select aria-label="成本输入每页数量" :value="skuPageSize" :disabled="loading || saving" @change="changePageSize('skus',$event)"><option v-for="size in pageSizes" :key="size" :value="size">{{size}} 条</option></select></label><button :disabled="skuPage<=1 || loading" @click="paginate('skus',-1)">上一页</button><button :disabled="skuPage*skuPageSize>=results.skus.total || loading" @click="paginate('skus',1)">下一页</button></div>
        </template>
        <div v-else-if="tab==='settings'" class="finance-settings"><section><div class="finance-section-title"><h3>店铺汇率</h3><button class="primary" :disabled="saving" @click="saveRates">保存汇率</button></div><p class="finance-footnote">1 单位外币＝输入值人民币；保存后重算该店铺历史数据。</p><label v-for="rate in selectedRates" :key="rateKey(rate)" class="finance-rate-row"><span>{{shopName(rate.shop_id)}}<small>1 {{rate.currency}} =</small></span><input v-model="rateInputs[rateKey(rate)]" type="text" inputmode="decimal" :disabled="rate.currency==='CNY' || saving" :aria-label="`${shopName(rate.shop_id)} ${rate.currency} 汇率`" placeholder="输入人民币汇率"/><span>人民币</span></label><p v-if="!selectedRates.length" class="empty">导入后台账单后显示需要配置的币种。</p></section></div>
        <template v-else-if="tab==='history'"><p class="finance-footnote">最近 100 次导入记录，覆盖本公司全部财务店铺，不受查询时间筛选。</p><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th>导入时间</th><th>店铺</th><th>数据类型 / 文件</th><th>新增</th><th>更新</th><th>未变化</th></tr></thead><tbody><tr v-for="item in history" :key="item.id"><td>{{date(item.created_at)}}</td><td>{{item.shop_name}}</td><td>{{item.kind==='erp' ? 'ERP 数据' : '店铺后台数据'}}<small>{{item.filename}}</small></td><td>{{item.counts.created}}</td><td>{{item.counts.updated}}</td><td>{{item.counts.unchanged}}</td></tr><tr v-if="!history.length"><td colspan="6" class="finance-empty-cell">暂无导入记录</td></tr></tbody></table></div></template>
      </section>
      <section class="finance-panel finance-pending"><div class="finance-section-title"><div class="finance-pending-export-title"><h2>下单时间待补 <span>{{pending.total}} 单</span></h2><button v-if="pending.total" aria-label="导出下单时间待补订单" :disabled="loading || !!exporting" @click="exportOrders('pending-order-time')">{{exporting==='pending-order-time:all' ? '导出中…' : '导出'}}</button></div><span>所选店铺全部待补订单 · 不受时间筛选 · 未计入上方统计</span></div><p class="finance-footnote">这些后台订单尚未匹配 ERP，无法确定下单时间。补导 ERP 后将自动归入对应查询时段。</p><details v-if="pending.total"><summary>查看待补订单</summary><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th>店铺</th><th>订单编号</th><th>待处理</th></tr></thead><tbody><tr v-for="row in pending.items" :key="row.id"><td>{{row.shop_name}}</td><td>{{row.order_number}}</td><td>补导 ERP 商品及下单时间</td></tr></tbody></table></div><div class="finance-pagination"><span>共 {{pending.total}} 单 · 第 {{pendingPage}} 页</span><label>每页<select aria-label="下单时间待补每页数量" :value="pendingPageSize" :disabled="loading || saving" @change="changePageSize('pending',$event)"><option v-for="size in pageSizes" :key="size" :value="size">{{size}} 条</option></select></label><button :disabled="pendingPage<=1 || loading" @click="paginate('pending',-1)">上一页</button><button :disabled="pendingPage*pendingPageSize>=pending.total || loading" @click="paginate('pending',1)">下一页</button></div></details><p v-else class="finance-footnote">当前所选店铺没有待补下单时间的订单。</p></section>
    </template>
    <div v-if="showCostDialog" class="modal-backdrop" @click.self="!saving && (showCostDialog=false)"><section v-dialog-focus class="modal-card finance-modal" role="dialog" aria-modal="true" aria-labelledby="finance-cost-title"><h2 id="finance-cost-title">批量设置成本</h2><p class="finance-footnote">为已选 {{costDialogSkus.length}} 条店铺 SKU 设置人民币单件衣服成本，仅影响所选店铺的对应 SKU，保存后会重新核算相关订单。</p><label>单件衣服成本<input v-model="unitCost" type="text" inputmode="decimal" aria-label="单件衣服成本" placeholder="输入单件衣服成本" :disabled="saving" @keyup.enter="saveSkuCosts"/></label><p v-if="costFormError" class="finance-invalid" role="alert">{{costFormError}}</p><div class="modal-actions"><button :disabled="saving" @click="showCostDialog=false">取消</button><button class="primary" :disabled="saving || !unitCost.trim()" @click="saveSkuCosts">{{saving ? '保存中…' : '确定'}}</button></div></section></div>
    <div v-if="showShopSettings" class="modal-backdrop" @click.self="closeShopSettings">
      <section v-dialog-focus="{close:closeShopSettings,busy:saving}" class="modal-card finance-shop-manager" role="dialog" aria-modal="true" aria-labelledby="finance-shop-settings-title">
        <div class="finance-section-title"><div><h2 id="finance-shop-settings-title">财务店铺管理</h2><p>管理店铺名称与类型，便于导入和查询财务数据。</p></div><button class="finance-shop-close" aria-label="关闭店铺管理" :disabled="saving" @click="closeShopSettings">×</button></div>
        <div class="finance-shop-manager-layout">
          <section class="finance-managed-shops" aria-label="店铺列表">
            <div class="finance-shop-manager-toolbar"><span>全部店铺 <b>{{shops.length}}</b></span><button :disabled="saving" @click="setShopDraft()">＋ 新增店铺</button></div>
            <input v-model="managedShopSearch" aria-label="搜索管理店铺" placeholder="搜索店铺名称" :disabled="saving"/>
            <div class="finance-managed-shop-list">
              <button v-for="shop in managedShops" :key="shop.id" class="finance-managed-shop" :class="{active:editingShopId===shop.id}" :aria-label="`编辑店铺 ${shop.name}`" :aria-pressed="editingShopId===shop.id" :disabled="saving" @click="setShopDraft(shop)">
                <span class="finance-managed-shop-name">{{shop.name}}<small>{{shop.has_platform_data ? '已导入后台账单' : '尚未导入后台账单'}}</small></span><span class="finance-managed-shop-type">{{shopTypeLabel(shop.shop_type)}}<span aria-hidden="true">›</span></span>
              </button>
              <div v-if="!managedShops.length" class="finance-shop-list-empty"><strong>{{shops.length ? '未找到相关店铺' : '还没有财务店铺'}}</strong><p>{{shops.length ? '试试其他店铺名称。' : '填写店铺信息，新增第一个店铺。'}}</p></div>
            </div>
          </section>
          <form class="finance-shop-editor" @submit.prevent="saveShop">
            <h3>{{editingShop ? '编辑店铺' : '新增店铺'}}</h3><p>{{editingShop ? '更新名称后，查询和导入页面会同步显示。' : '选择店铺类型后，即可开始导入财务数据。'}}</p>
            <label for="finance-shop-draft-name">店铺名称 <b>*</b></label><input id="finance-shop-draft-name" ref="shopNameInput" v-model="shopDraftName" maxlength="120" placeholder="输入店铺名称" :disabled="saving" :aria-invalid="!!shopFormError" @input="shopFormError='';shopFormNotice=''"/>
            <label for="finance-shop-draft-type">店铺类型 <b>*</b></label><select id="finance-shop-draft-type" v-model="shopDraftType" :disabled="saving || editingShop?.has_platform_data" @change="shopFormError='';shopFormNotice=''"><option value="cross_border">跨境店</option><option value="local">本土店</option></select>
            <p class="finance-shop-type-hint">{{editingShop?.has_platform_data ? '已导入后台账单，店铺类型已固定。店铺名称仍可修改。' : '跨境店按结算单和 SKU 区分账单明细；本土店按订单汇总。导入后台账单后，店铺类型将固定。'}}</p>
            <p v-if="shopFormError" class="finance-shop-form-error" role="alert">{{shopFormError}}</p><p v-if="shopFormNotice" class="finance-shop-form-success" role="status">{{shopFormNotice}}</p>
            <div class="modal-actions"><button type="button" :disabled="saving" @click="editingShop ? setShopDraft(editingShop) : setShopDraft()">{{editingShop ? '重置修改' : '清空'}}</button><button class="primary" type="submit" :disabled="saving || !shopDraftName.trim() || !shopFormChanged">{{saving ? '保存中…' : editingShop ? '保存修改' : '新增店铺'}}</button></div>
          </form>
        </div>
      </section>
    </div>
    <div v-if="showImport" class="modal-backdrop" @click.self="!saving && (showImport=false)"><section v-dialog-focus class="modal-card finance-modal" role="dialog" aria-modal="true" aria-labelledby="finance-import-title"><h2 id="finance-import-title">导入财务数据</h2><div class="finance-import-shop-field"><span>目标店铺 <b>*</b></span><SearchableSelect :model-value="importShopId" :options="importShopOptions" aria-label="目标店铺" placeholder="请选择一个目标店铺" search-placeholder="搜索店铺名称" empty-label="暂无店铺，请先在店铺管理中新增" no-match-label="没有匹配的店铺" :disabled="saving" @update:model-value="selectImportShop"/></div><label>数据类型<select v-model="importKind" @change="importSheets=[];importSheet='';importError=''"><option value="platform">店铺后台数据</option><option value="erp">ERP 数据</option></select></label><div class="finance-import-columns" aria-live="polite"><strong>{{importKind==='erp' ? 'ERP 数据' : importShop ? shopTypeLabel(importShop.shop_type)+'后台数据' : '店铺后台数据'}}必填列</strong><p v-if="importKind==='erp'">订单编号、平台 SKU、商品数量、下单时间。</p><template v-else-if="importShop"><p v-if="importShop.shop_type==='cross_border'">交易类型、订单 ID、货币、结算总金额、总收入、结算单 ID、SKU ID。</p><p v-else>交易类型、订单 ID、货币、结算总金额、总收入。</p></template><p v-else>请先选择目标店铺，以确定后台数据必填列。</p></div><label>XLSX 文件<input :key="fileInputKey" type="file" accept=".xlsx" @change="fileChanged"/></label><label v-if="importSheets.length">选择工作表<select v-model="importSheet"><option value="">请选择工作表</option><option v-for="name in importSheets" :key="name">{{name}}</option></select></label><p class="finance-footnote">最多 20MB、50,000 行。{{importRule}}</p><p v-if="importError" class="finance-invalid" role="alert">{{importError}}</p><div class="modal-actions"><button :disabled="saving" @click="showImport=false">取消</button><button class="primary" :disabled="saving || !importShopId || !importFile" @click="upload">{{saving ? '正在导入…' : '导入并保存'}}</button></div></section></div>
    <div v-if="detail" class="modal-backdrop" @click.self="detail=null"><section v-dialog-focus class="modal-card finance-detail" role="dialog" aria-modal="true" aria-labelledby="finance-detail-title"><div class="finance-section-title"><h2 id="finance-detail-title">订单核算明细</h2><button aria-label="关闭明细" @click="detail=null">关闭</button></div><p>{{detail.shop_name}} · {{detail.order_number}}<br/>下单时间：{{date(detail.paid_at)}}</p><div class="finance-detail-metrics"><span>销售额<strong>{{amount(detail.sales)}}</strong></span><span>结算金额<strong>{{amount(detail.settlement)}}</strong></span><span>衣服成本<strong>{{amount(detail.cost)}}</strong></span><span>利润<strong>{{amount(detail.profit)}}</strong></span></div><h3>原币汇总与汇率</h3><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th>币种</th><th>总收入</th><th>结算总金额</th><th>人民币汇率</th></tr></thead><tbody><tr v-for="c in detail.currencies" :key="c.currency"><td>{{c.currency}}</td><td>{{c.revenue}}</td><td>{{c.settlement}}</td><td>{{c.rate ?? '待设置'}}</td></tr></tbody></table></div><h3>商品成本</h3><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th>平台 SKU</th><th>数量</th><th>单件成本</th><th>商品成本</th></tr></thead><tbody><tr v-for="item in detail.items" :key="item.platform_sku"><td>{{item.platform_sku}}</td><td>{{item.quantity}}</td><td>{{amount(item.unit_cost)}}</td><td>{{amount(item.line_cost)}}</td></tr></tbody></table></div><h3>订单结算记录</h3><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th v-if="detail.shop_type==='cross_border'">结算单 ID</th><th v-if="detail.shop_type==='cross_border'">SKU ID</th><th>币种</th><th>结算金额</th><th>总收入</th></tr></thead><tbody><tr v-for="(b,index) in detail.bills" :key="index"><td v-if="detail.shop_type==='cross_border'">{{b.settlement_id}}</td><td v-if="detail.shop_type==='cross_border'">{{b.sku_id || '历史待补'}}</td><td>{{b.currency}}</td><td>{{b.settlement}}</td><td>{{b.revenue}}</td></tr></tbody></table></div><details v-for="(b,index) in detail.bills" :key="`source-${index}`" class="finance-bill-sources"><summary>{{detail.shop_type==='cross_border' ? '结算单 '+b.settlement_id : '本土店订单账单'}} · 查看原始明细（{{b.source_details?.length || 0}} 条）</summary><div class="finance-table-scroll"><table class="finance-table"><thead><tr><th v-if="detail.shop_type==='cross_border'">SKU ID</th><th>币种</th><th>结算金额</th><th>总收入</th></tr></thead><tbody><tr v-for="(source,sourceIndex) in b.source_details" :key="sourceIndex"><td v-if="detail.shop_type==='cross_border'">{{source.sku_id || '—'}}</td><td>{{source.currency}}</td><td>{{source.settlement}}</td><td>{{source.revenue}}</td></tr></tbody></table></div></details></section></div>
  </section>
</template>

<style scoped>
.finance-other-cost input{width:145px!important;max-width:180px}.finance-other-cost small{white-space:normal;max-width:180px}.finance-summary td small.finance-invalid{color:#b91c1c}.finance-missing-bill-export,.finance-pending-export-title{display:flex;align-items:center;gap:10px}.finance-missing-bill-export{margin-top:5px;font-size:11px;color:#64748b}.finance-missing-bill-export button,.finance-pending-export-title button{font-size:12px;color:#6043d4;border:1px solid #e2dff0;border-radius:7px;padding:5px 10px;background:#fff;white-space:nowrap}
.finance-import-shop-field{display:flex;flex-direction:column;gap:8px;margin-top:16px;font-size:13px;color:#334155}.finance-import-shop-field b{color:#dc2626}.finance-import-shop-field :deep(.search-select-trigger){min-height:42px;border-radius:10px;font-size:13px}.finance-import-shop-field :deep(.search-select-search input){font-size:13px}.finance-import-shop-field :deep(.search-select-search input::placeholder){font-size:12px}
.finance-shop-manager{width:920px;max-width:calc(100vw - 36px);box-sizing:border-box;max-height:88vh;overflow:auto}
.finance-shop-manager .finance-section-title{align-items:flex-start;flex-wrap:nowrap;margin-bottom:24px}.finance-shop-manager .finance-section-title>div{min-width:0}.finance-shop-manager .finance-section-title h2{font-size:21px;margin:0}.finance-shop-manager .finance-section-title p{margin:8px 0 0;line-height:1.6}
.finance-shop-manager .finance-shop-close{border:0;background:#f8fafc;border-radius:50%;width:32px;height:32px;padding:0;font-size:22px;color:#64748b;flex-shrink:0}
.finance-shop-manager-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:26px}.finance-managed-shops{min-width:0}.finance-shop-manager-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;font-size:13px;color:#64748b}.finance-shop-manager-toolbar b{color:#334155;margin-left:4px}.finance-shop-manager-toolbar button{padding:7px 10px;font-size:12px;color:#6043d4;background:#f5f2ff;border:1px solid #e9e2ff;border-radius:8px}
.finance-managed-shops>input{width:100%;margin:0 0 12px}.finance-managed-shop-list{display:flex;flex-direction:column;gap:8px;max-height:380px;overflow:auto;padding:2px}.finance-managed-shop{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;padding:14px;text-align:left;border:1px solid #e2e8f0;border-radius:10px;background:#fff;box-shadow:none}.finance-managed-shop:hover{border-color:#b9a9ef;background:#faf9ff}.finance-managed-shop.active{border-color:#7054e7;background:#f7f4ff}.finance-managed-shop-name{font-size:14px;color:#334155;font-weight:600;overflow-wrap:anywhere;min-width:0}.finance-managed-shop-name small{display:block;font-size:11px;font-weight:400;color:#94a3b8;margin-top:6px}.finance-managed-shop-type{display:flex;gap:12px;align-items:center;flex-shrink:0;font-size:11px;font-weight:400;color:#64748b}.finance-managed-shop-type>span{font-size:20px;color:#94a3b8}
.finance-shop-editor{padding:22px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;min-width:0}.finance-shop-editor h3{font-size:16px;margin:0 0 8px}.finance-shop-editor>p{font-size:12px;line-height:1.7;margin:0 0 18px}.finance-shop-editor>label{margin:16px 0 8px;font-weight:500;color:#334155}.finance-shop-editor>label b{color:#dc2626}.finance-shop-editor>input,.finance-shop-editor>select{display:block;width:100%;margin:0}.finance-shop-editor .finance-shop-type-hint{margin:10px 0 0;font-size:11px;color:#64748b}.finance-shop-editor .finance-shop-form-error{margin:14px 0 0;color:#b91c1c}.finance-shop-editor .finance-shop-form-success{margin:14px 0 0;color:#15803d}.finance-shop-editor .modal-actions{margin-top:22px;flex-wrap:wrap}.finance-shop-editor .modal-actions button{font-size:13px;padding:10px 14px;border-radius:10px}.finance-shop-list-empty{text-align:center;padding:36px 14px;color:#64748b;font-size:13px}.finance-shop-list-empty p{margin:8px 0 0;font-size:12px}
@media(max-width:760px){.finance-shop-manager{padding:20px;max-height:90vh}.finance-shop-manager-layout{grid-template-columns:minmax(0,1fr);gap:20px}.finance-managed-shop-list{max-height:210px}.finance-shop-editor{padding:18px}.finance-shop-manager .finance-section-title{margin-bottom:20px}}
.finance-order-toolbar select{width:160px;min-width:0;margin:0}
.finance-bill-sources{margin-top:14px;font-size:12px;color:#64748b}.finance-bill-sources summary{cursor:pointer;margin-bottom:10px}
.finance-import-columns{margin-top:16px;padding:12px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;font-size:12px;line-height:1.7;color:#64748b}.finance-import-columns strong{color:#334155}.finance-import-columns p{margin:6px 0 0}
.finance-pagination{flex-wrap:wrap}.finance-pagination>label{display:flex;align-items:center;gap:8px;font-size:12px;color:#64748b;white-space:nowrap}
.finance-applied-range{font-size:12px;color:#64748b;margin:0 0 14px}.finance-page button:disabled{opacity:.5;cursor:not-allowed}.finance-page{max-width:1600px;padding-bottom:40px}.finance-title,.finance-section-title,.finance-actions,.finance-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px}.finance-page .finance-title{height:auto;min-height:0;padding:0;background:transparent;border:0;margin-bottom:24px}.finance-title h1{font-size:26px;margin:0 0 7px}.finance-title p,.finance-footnote,.finance-filter-note{color:#64748b;font-size:13px}.finance-title p{margin:0}.finance-actions{justify-content:flex-start;flex-wrap:wrap}.finance-panel{background:white;border:1px solid #e2e8f0;border-radius:12px;margin-bottom:20px;padding:22px;min-width:0}.finance-filter-fields{display:grid;grid-template-columns:minmax(200px,260px) minmax(280px,320px) max-content;gap:16px;align-items:start}.finance-filter-fields>label,.finance-modal label{display:flex;flex-direction:column;gap:8px;font-size:13px;color:#334155}.finance-filter-fields b,.finance-shop-field b,.finance-modal b{color:#dc2626}.finance-filter-fields input{padding:10px 12px;border:1px solid #cbd5e1;border-radius:6px;font:inherit;background:#fff;width:100%;box-sizing:border-box;min-height:40px}.finance-query{margin-top:25px;min-height:40px;min-width:85px}.finance-shop-field>label{display:block;font-size:13px;margin-bottom:8px}.finance-shop-select{position:relative}.finance-shop-select summary{display:flex;justify-content:space-between;border:1px solid #cbd5e1;border-radius:6px;padding:10px 12px;cursor:pointer;list-style:none;font-size:13px;min-height:40px;box-sizing:border-box}.finance-shop-select summary::-webkit-details-marker{display:none}.finance-shop-options{position:absolute;top:44px;left:0;right:0;z-index:8;background:white;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 8px 25px #0f172a18;max-height:260px;overflow:auto;padding:10px;min-width:230px}.finance-shop-options>input{width:100%;box-sizing:border-box;margin-bottom:10px}.finance-shop-options>input::placeholder{font-size:12px}.finance-shop-options>label{display:flex;align-items:center;gap:9px;padding:9px 4px;font-size:13px}.finance-shop-options input[type=checkbox],.finance-table input[type=checkbox]{width:16px;height:16px;min-height:0;accent-color:#2563eb;margin:0}.finance-shop-tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}.finance-shop-tags span{font-size:11px;color:#1d4ed8;background:#eff6ff;border-radius:4px;padding:3px 6px}.finance-filter-note{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:14px}.finance-filter-note strong{color:#b45309;font-weight:500}.finance-invalid,.finance-negative{color:#b91c1c}.finance-section-title{margin-bottom:16px;flex-wrap:wrap}.finance-section-title h2{font-size:17px;margin:0}.finance-section-title h3{font-size:15px;margin:0}.finance-section-title>span{font-size:12px;color:#64748b}.finance-section-title h2>span{font-size:12px;font-weight:400;color:#64748b;margin-left:8px}.finance-table-scroll{overflow-x:auto;max-width:100%;border:1px solid #e2e8f0;border-radius:7px}.finance-table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}.finance-table th{background:#f8fafc;color:#64748b;font-weight:500;text-align:left;padding:12px 14px}.finance-table td{padding:14px;border-top:1px solid #eef2f6;vertical-align:middle}.finance-table td small{display:block;font-size:11px;color:#64748b;margin-top:5px}.finance-table td strong{font-weight:600}.finance-total td{background:#f8fafc;font-weight:600}.finance-summary td{padding:18px 14px}.finance-summary td:nth-child(n+2):nth-child(-n+7){font-size:16px}.finance-badge{display:inline-block;padding:4px 7px;border-radius:5px;font-size:11px;margin:2px 3px 2px 0}.finance-badge.warning{color:#92400e;background:#fff7ed}.finance-badge.complete{color:#166534;background:#f0fdf4}.finance-footnote{line-height:1.7;margin:13px 0 0}.finance-workspace{padding-top:0}.finance-tabs{display:flex;gap:24px;border-bottom:1px solid #e2e8f0;margin-bottom:20px;overflow-x:auto}.finance-tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;box-shadow:none;padding:17px 0;color:#64748b;white-space:nowrap}.finance-tabs button.active{border-bottom-color:#2563eb;color:#2563eb;font-weight:600}.finance-pagination{justify-content:flex-end;margin-top:16px}.finance-pagination>span{font-size:12px;color:#64748b;margin-right:auto}.finance-empty-cell{text-align:center;color:#64748b;padding:36px!important}.finance-sku-toolbar{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}.finance-sku-toolbar input{max-width:190px}.finance-sku-toolbar span{font-size:12px;color:#64748b}.finance-settings{display:block;max-width:760px}.finance-settings>section{min-width:0}.finance-rate-row,.finance-cost-row{display:grid;grid-template-columns:minmax(90px,1fr) 140px 52px;align-items:center;gap:10px;margin-top:15px;font-size:13px}.finance-rate-row small{display:block;color:#64748b;margin-top:5px}.finance-settings input{width:100%;box-sizing:border-box}.finance-pending summary{margin-top:12px;font-size:13px;color:#2563eb;cursor:pointer}.finance-pending details .finance-table-scroll{margin-top:16px}.finance-alert{padding:12px 16px;font-size:13px;border-radius:7px;line-height:1.7}.finance-error{background:#fef2f2;color:#b91c1c}.finance-success{background:#eff6ff;color:#1d4ed8;display:flex;justify-content:space-between;gap:14px}.finance-success button{background:transparent;border:0;color:inherit;padding:0 4px}.finance-empty{text-align:center;padding:50px 20px}.finance-empty h2{font-size:19px}.finance-empty p{color:#64748b;font-size:14px}.finance-modal{width:480px;max-width:calc(100vw - 36px);box-sizing:border-box}.finance-modal h2{font-size:21px;margin:0 0 24px}.finance-modal label{margin-top:16px}.finance-detail{width:1000px;max-width:calc(100vw - 36px);max-height:85vh;overflow:auto;box-sizing:border-box}.finance-detail h3{font-size:15px;margin-top:24px}.finance-detail>p{font-size:13px;line-height:1.8;color:#64748b}.finance-detail-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;background:#f8fafc;border-radius:8px;padding:20px}.finance-detail-metrics span{font-size:12px;color:#64748b}.finance-detail-metrics strong{display:block;color:#0f172a;font-size:19px;margin-top:7px}.finance-order-id{font-family:ui-monospace,monospace}.finance-panel[aria-busy=true]{opacity:.65;pointer-events:none}@media(max-width:1200px){.finance-filter-fields{grid-template-columns:1fr 1fr}.finance-query{margin-top:25px;width:100%}.finance-title{align-items:flex-start}}@media(max-width:760px){.finance-page{padding:18px!important}.finance-title{flex-direction:column;gap:18px}.finance-panel{padding:16px}.finance-filter-fields{grid-template-columns:1fr}.finance-query{margin-top:0}.finance-filter-fields input{padding:10px 12px;border:1px solid #cbd5e1;border-radius:6px;font:inherit;background:#fff;font-size:13px;min-width:0}.finance-filter-note{line-height:1.8}.finance-settings{grid-template-columns:1fr}.finance-tabs{gap:18px}.finance-rate-row,.finance-cost-row{grid-template-columns:minmax(70px,1fr) 120px 48px}.finance-detail-metrics{grid-template-columns:1fr 1fr}.finance-pagination{gap:6px}.finance-pagination button{padding:7px}.finance-modal,.finance-detail{padding:20px}.finance-title h1{font-size:23px}}
/* 财务页面的文本输入、选择框和弹窗使用同一套控件样式。 */
.finance-page input:not([type='checkbox']),
.finance-page select {
  box-sizing: border-box;
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid #dfe3ef;
  border-radius: 10px;
  background: #fff;
  color: #334155;
  font: inherit;
  font-size: 13px;
  line-height: 20px;
  transition: border-color .15s ease, box-shadow .15s ease;
}
.finance-page input:not([type='checkbox'])::placeholder {
  color: #94a3b8;
  font-size: 12px;
}
.finance-page input:not([type='checkbox']):focus,
.finance-page select:focus,
.finance-page .finance-shop-select summary:focus-visible {
  border-color: #7054e7;
  outline: none;
  box-shadow: 0 0 0 3px #7054e71f;
}
.finance-page input:not([type='checkbox']):disabled,
.finance-page select:disabled {
  background: #f8fafc;
  color: #94a3b8;
  cursor: not-allowed;
}
.finance-page .finance-shop-select summary {
  min-height: 42px;
  border-color: #dfe3ef;
  border-radius: 10px;
}
.finance-page .finance-shop-options { top: 46px; }
.finance-page input[type='file'] { padding: 6px 8px; }
.finance-page input[type='file']::file-selector-button {
  padding: 6px 10px;
  margin-right: 10px;
  border: 0;
  border-radius: 6px;
  background: #f1edff;
  color: #6043d4;
  font: inherit;
  cursor: pointer;
}
.finance-sku-toolbar > .finance-actions:first-child { flex: 0 1 470px; }
.finance-sku-toolbar > .finance-actions:last-child { margin-left: auto; justify-content: flex-end; }
.finance-sku-toolbar input { width: 220px; max-width: 100%; }
.finance-sku-toolbar select { width: 140px; min-width: 120px; margin: 0; }
.finance-sku-toolbar button { min-height: 42px; padding: 10px 14px; border-radius: 10px; font-size: 13px; }
.finance-sku-toolbar button:not(.primary) { border: 1px solid #dfe3ef; background: #fff; }
@media (min-width: 761px) and (max-width: 1200px) {
  .finance-filter-fields { grid-template-columns: minmax(160px,240px) minmax(260px,320px) max-content; }
  .finance-query { width: auto; }
}
@media (max-width: 760px) {
  .finance-sku-toolbar > .finance-actions:first-child { flex: 1 1 100%; }
  .finance-sku-toolbar > .finance-actions:last-child { margin-left: 0; justify-content: flex-start; }
  .finance-sku-toolbar input { flex: 1; width: 0; min-width: 0; }
  .finance-sku-toolbar select { flex: 1 1 100%; width: 100%; min-width: 0; }
  .finance-rate-row, .finance-cost-row { grid-template-columns: minmax(0, 1fr) minmax(90px, 120px) auto; }
  .finance-settings input { min-width: 0; }
}
</style>
