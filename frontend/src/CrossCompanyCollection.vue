<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { dialogFocus as vDialogFocus } from './dialog-focus'

const props = defineProps<{token:string; templates:any[]; user:any; historyOnly?:boolean}>()
const emit = defineEmits<{back:[]; revoked:[]; unauthorized:[]; account:[]}>()
const api = axios.create({baseURL:import.meta.env.VITE_API_URL || 'http://localhost:8000'})
const headers = computed(() => ({Authorization:`Bearer ${props.token}`}))
const enabled = ref(false), checking = ref(true), companies = ref<any[]>([]), sourceTemplates = ref<any[]>([])
const companyId = ref<number | null>(null), library = ref('material'), tab = ref(props.historyOnly ? 'history' : 'collect')
const templateId = ref(''), sourceType = ref(''), usage = ref('all'), from = ref(''), to = ref(''), sku = ref(''), category = ref('products')
const historyTemplateId = ref<number | null>(null), appliedHistoryTemplateId = ref<number | null>(null)
const appliedFilters = ref(filterValues())
const rows = ref<any[]>([]), total = ref(0), page = ref(1), pageSize = ref(20), loading = ref(false), error = ref(''), success = ref('')
const snapshot = ref<string | null>(null), through = ref<string | null>(null)
const selected = ref<Record<number,any>>({}), count = computed(() => Object.keys(selected.value).length)
const preview = ref<any>(null), confirming = ref(false), targetTemplate = ref<number | null>(null), saving = ref(false), formError = ref(''), recollect = ref(false)
const usableTemplates = computed(() => props.templates.filter(t => !t.is_platform))
const selectedTemplate = computed(() => usableTemplates.value.find(t => t.id === targetTemplate.value))
const preflight = computed(() => {
  if (!props.user?.user_code || props.user.user_code.trim().length !== 2) return '请先在账号设置中填写两位用户代码。'
  if (!usableTemplates.value.length) return '请先在产品模板中创建本公司的模板。'
  if (!selectedTemplate.value) return '请选择本公司的产品模板。'
  if (!/^[A-Z0-9]{1,5}$/.test(selectedTemplate.value.name.trim().toUpperCase())) return '模板名称须为 1–5 位字母或数字，请先修改模板。'
  return ''
})
const hasExisting = computed(() => Object.values(selected.value).some(row => row.already_collected))
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const categories = [['products','全部产品'],['top7','7天热销 TOP50'],['top15','15天热销 TOP50'],['top30','30天热销 TOP50'],['potential','潜力款'],['hot','热销款'],['booming','爆款']]
const sourceLabels:Record<string,string> = {ai_created:'AI创作',local_upload:'本地上传',imported:'导入',cross_company:'采集'}
let generation = 0, filterGeneration = 0
let pendingRequest: {signature:string; key:string} | null = null
function image(row:any) { return row.url || row.image_url || row.source_url || '' }
function name(row:any) { return row.name || row.title || row.source_name || row.sku || '素材图片' }
function date(value:number) { return new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Hong_Kong'}) }
function fail(e:any) {
  const status = e.response?.status
  if (status === 401) emit('unauthorized')
  if (status === 403) {
    enabled.value = false; selected.value = {}; confirming.value = false; preview.value = null
    rows.value = []; total.value = 0; snapshot.value = null; through.value = null; emit('revoked')
  }
  const detail = e.response?.data?.detail
  error.value = typeof detail === 'string' ? detail : '请求失败，请重试。'
}
function clearSelection() { selected.value = {}; pendingRequest = null }
function toggle(row:any) {
  if (selected.value[row.id]) { delete selected.value[row.id]; return }
  if (!image(row) || count.value >= 100) return
  selected.value[row.id] = row
}
function selectNew() {
  for (const row of rows.value) if (!row.already_collected && image(row) && !selected.value[row.id] && count.value < 100) selected.value[row.id] = row
}
function filterValues() {
  return {source_company_id:companyId.value,source_library:library.value,
    template_id:templateId.value && templateId.value !== 'unmatched' ? Number(templateId.value) : undefined,
    unmatched:templateId.value === 'unmatched',source_type:sourceType.value,usage_status:usage.value,
    created_from:from.value ? new Date(from.value).toISOString() : undefined,
    created_to:to.value ? new Date(to.value).toISOString() : undefined,sku:sku.value || undefined,category:category.value}
}
async function load() {
  const id = ++generation
  loading.value = false
  if (tab.value === 'collect' && (!enabled.value || !appliedFilters.value.source_company_id)) return
  loading.value = true; error.value = ''
  try {
    const {data} = await api.get(tab.value === 'history' ? '/cross-company-collection/history' : '/cross-company-collection/items',
      {headers:headers.value,params:{page:page.value,page_size:pageSize.value,...(tab.value === 'history'
        ? {template_id:appliedHistoryTemplateId.value ?? undefined} : appliedFilters.value)}})
    if (id !== generation) return
    rows.value = data.items; total.value = data.total; snapshot.value = data.snapshot_date; through.value = data.through_date
    if (data.page) page.value = data.page
    for (const row of rows.value) if (selected.value[row.id]) selected.value[row.id] = row
  } catch(e:any) { if (id === generation) fail(e) }
  finally { if (id === generation) loading.value = false }
}
async function changeSource() {
  const id = ++filterGeneration
  sourceTemplates.value = []
  resetFilters()
  if (!companyId.value) return
  try {
    const {data} = await api.get('/cross-company-collection/filters',{headers:headers.value,params:{source_company_id:companyId.value}})
    if (id !== filterGeneration) return
    sourceTemplates.value = data.templates
  } catch(e:any) { if (id === filterGeneration) fail(e) }
}
function resetFilters() { templateId.value = ''; sourceType.value = ''; usage.value = 'all'; from.value = ''; to.value = ''; sku.value = ''; category.value = 'products' }
function search() {
  if (loading.value || saving.value) return
  if (tab.value === 'collect') {
    if (!enabled.value || !companyId.value) return
    appliedFilters.value = filterValues(); clearSelection(); success.value = ''
  } else appliedHistoryTemplateId.value = historyTemplateId.value
  page.value = 1; void load()
}
function changePageSize() { page.value = 1; void load() }
function changePage(target:number) { page.value = target; void load() }
function changeTab(value:string) {
  if (tab.value === value || saving.value) return
  tab.value = value; page.value = 1; clearSelection(); success.value = ''
  rows.value = []; total.value = 0; snapshot.value = null; through.value = null
  void load()
}
function closeConfirm() { if (!saving.value) confirming.value = false }
function openConfirm() { formError.value = ''; recollect.value = false; targetTemplate.value = usableTemplates.value[0]?.id ?? null; confirming.value = true }
async function submit() {
  if (saving.value || preflight.value || !count.value || (hasExisting.value && !recollect.value)) return
  const payload = {source_company_id:appliedFilters.value.source_company_id,source_library:appliedFilters.value.source_library,record_ids:Object.keys(selected.value).map(Number).sort((a,b)=>a-b),template_id:targetTemplate.value,allow_recollect:recollect.value}
  const signature = JSON.stringify(payload)
  if (!pendingRequest || pendingRequest.signature !== signature) pendingRequest = {signature,key:crypto.randomUUID()}
  saving.value = true; formError.value = ''
  try {
    const {data} = await api.post('/cross-company-collection/collect',payload,{headers:{...headers.value,'Idempotency-Key':pendingRequest.key}})
    confirming.value = false; clearSelection(); success.value = `已采集 ${data.collected} 张图片到素材库。`; await load()
  } catch(e:any) {
    if (e.response?.status === 401 || e.response?.status === 403) fail(e)
    const detail = e.response?.data?.detail
    formError.value = typeof detail === 'string' ? detail : '采集失败，请重试；网络重试不会重复创建素材。'
    // 明确拒绝的请求没有写入；刷新重复标记后允许用户重新确认。
    if (e.response?.status === 409) { await load(); recollect.value = false }
  } finally { saving.value = false }
}
onMounted(async () => {
  try {
    const {data} = await api.get('/cross-company-collection/capability',{headers:headers.value})
    enabled.value = data.enabled
    if (enabled.value) companies.value = (await api.get('/cross-company-collection/companies',{headers:headers.value})).data
    if (tab.value === 'history') await load()
  } catch(e:any) { fail(e) }
  finally { checking.value = false }
})
</script>

<template>
  <section class="page collection-page">
    <div class="collection-heading"><p>从其他公司选图，采集到素材库并生成新的永久 SKU。</p><button class="secondary" @click="emit('back')">返回素材库</button></div>
    <div class="collection-tabs" role="navigation" aria-label="采集"><button :class="{active:tab==='collect'}" :disabled="saving" @click="changeTab('collect')">采集</button><button :class="{active:tab==='history'}" :disabled="saving" @click="changeTab('history')">采集记录</button></div>
    <p v-if="checking" role="status">正在检查采集权限…</p>
    <p v-else-if="tab==='collect' && !enabled" class="error" role="alert">当前账号没有采集权限，请联系平台管理员开通。已有采集记录仍可查看。</p>
    <form v-if="tab==='collect' && enabled" class="collection-filters" @submit.prevent="search">
      <label>来源公司<select v-model="companyId" :disabled="saving" @change="changeSource"><option :value="null">请选择公司</option><option v-for="c in companies" :key="c.id" :value="c.id">{{c.name}}</option></select></label>
      <label>来源库<select v-model="library" :disabled="saving" @change="changeSource"><option value="material">素材库</option><option value="product">产品库</option></select></label>
      <label>来源模板<select v-model="templateId"><option value="">全部模板</option><option v-if="library==='product'" value="unmatched">未匹配</option><option v-for="t in sourceTemplates" :key="t.id" :value="String(t.id)">{{t.name}}</option></select></label>
      <template v-if="library==='material'">
        <label>素材类型<select v-model="sourceType"><option value="">全部类型</option><option v-for="(label,key) in sourceLabels" :key="key" :value="key">{{label}}</option></select></label>
        <label>使用状态<select v-model="usage"><option value="all">全部状态</option><option value="unused">未使用</option><option value="used">已使用</option></select></label>
        <label>创建开始时间<input v-model="from" type="datetime-local" /></label><label>创建结束时间<input v-model="to" type="datetime-local" /></label>
      </template>
      <template v-else><label>SKU 前缀<input v-model="sku" type="search" /></label><label>产品分类<select v-model="category"><option v-for="c in categories" :key="c[0]" :value="c[0]">{{c[1]}}</option></select></label></template>
      <button class="primary" :disabled="!companyId || loading || saving">{{loading?'加载中…':'搜索'}}</button><button class="secondary" type="button" :disabled="!companyId || loading || saving" @click="resetFilters">重置筛选</button>
    </form>
    <form v-if="tab==='history'" class="collection-filters collection-history-filters" @submit.prevent="search">
      <label>目标模板<select v-model="historyTemplateId"><option :value="null">全部模板</option><option v-for="t in usableTemplates" :key="t.id" :value="t.id">{{t.name}}</option></select></label>
      <button class="primary" :disabled="loading">{{loading?'加载中…':'搜索'}}</button><button class="secondary" type="button" :disabled="loading" @click="historyTemplateId=null">重置筛选</button>
    </form>
    <p v-if="snapshot">{{snapshot}} 榜单 · 统计截至 {{through}}</p>
    <p v-if="error" class="error" role="alert">{{error}} <button class="secondary" @click="load">重试</button></p>
    <p v-if="success" class="collection-success" role="status">{{success}}</p>
    <div v-if="tab==='collect' && enabled" class="collection-actions"><strong>已选 {{count}} / 100 张</strong><button class="secondary" :disabled="loading || !rows.length" @click="selectNew">选择本页新图片</button><button class="secondary" :disabled="!count" @click="clearSelection">取消选择</button><button class="primary" :disabled="!count || loading" @click="openConfirm">采集</button></div>
    <p v-if="loading" role="status">正在加载…</p>
    <div v-else class="collection-grid">
      <article v-for="row in rows" :key="row.id" class="collection-card" :class="{selected:tab==='collect' && selected[row.id]}">
        <label v-if="tab==='collect'" class="collection-checkbox"><input type="checkbox" :checked="!!selected[row.id]" :disabled="!image(row) || (!selected[row.id] && count>=100)" :aria-label="`选择 ${row.sku || name(row)}`" @change="toggle(row)" />{{row.already_collected?'已采集，可再次选择':'新图片'}}</label>
        <button v-if="image(row)" class="collection-image" :aria-label="`预览 ${name(row)}`" @click="preview=row"><img :src="image(row)" :alt="name(row)" loading="lazy" /></button><p v-else>暂无图片链接</p>
        <div class="collection-card-body"><strong :title="name(row)">{{name(row)}}</strong><code>{{row.sku || row.source_sku || '无 SKU'}}</code>
          <template v-if="tab==='collect'"><small>模板：{{row.template_name || row.template || '未匹配'}}</small><small v-if="appliedFilters.source_library==='material'">{{sourceLabels[row.source_type]}} · {{row.usage_status==='used'?'已使用':'未使用'}} · {{date(row.created_at)}}</small><small v-else>销量：{{row.sales_quantity ?? 0}}<span v-if="row.rank"> · 排名 #{{row.rank}}</span></small></template>
          <template v-else><small>来源：{{row.source_company_name}} · {{row.source_library==='material'?'素材库':'产品库'}}</small><small>目标模板：{{props.templates.find(t=>t.id===row.template_id)?.name || `历史模板 #${row.template_id}`}}</small><small>采集人：{{row.created_by_name}}</small><small>{{date(row.created_at)}} · 素材 #{{row.material_asset_id}}</small></template>
        </div>
      </article>
    </div>
    <p v-if="!loading && !checking && !rows.length && !error && (tab==='history' || (enabled && appliedFilters.source_company_id))" class="empty">{{appliedFilters.category!=='products' && tab==='collect' && appliedFilters.source_library==='product' && !snapshot?'来源公司暂无可用榜单快照。':'没有符合条件的记录。'}}</p>
    <footer v-if="total" class="collection-pagination"><span>共 {{total}} 条</span><label>每页 <select v-model.number="pageSize" :disabled="loading" @change="changePageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select> 条</label><button :disabled="loading || page<=1" @click="changePage(page-1)">上一页</button><span>{{page}} / {{pages}}</span><button :disabled="loading || page>=pages" @click="changePage(page+1)">下一页</button></footer>
    <div v-if="confirming" v-dialog-focus="{close:closeConfirm,busy:saving}" class="modal-backdrop" @click.self="closeConfirm"><form class="modal-card collection-modal" role="dialog" aria-modal="true" aria-labelledby="collect-title" @submit.prevent="submit">
      <h2 id="collect-title">采集到素材库</h2><p>已选 {{count}} 张；统一绑定目标模板并生成新 SKU。图片引用原链接。</p>
      <label>目标产品模板<select v-model="targetTemplate" required :disabled="saving" @change="formError=''"><option :value="null" disabled>请选择模板</option><option v-for="t in usableTemplates" :key="t.id" :value="t.id">{{t.name}}</option></select></label>
      <p v-if="preflight" class="error">{{preflight}} <button v-if="!props.user?.user_code" class="secondary" type="button" @click="closeConfirm();emit('account')">账号设置</button></p>
      <label v-if="hasExisting" class="collection-recollect"><input v-model="recollect" type="checkbox" :disabled="saving" />我确认再次采集已存在的图片，生成新的素材和 SKU</label>
      <p v-if="formError" class="error" role="alert">{{formError}}</p><div class="modal-actions"><button class="secondary" type="button" :disabled="saving" @click="closeConfirm">取消</button><button class="primary" :disabled="saving || !!preflight || (hasExisting && !recollect)">{{saving?'采集中…':'确认采集'}}</button></div>
    </form></div>
    <div v-if="preview" v-dialog-focus="{close:()=>{preview=null}}" class="modal-backdrop" @click.self="preview=null"><section class="modal-card collection-modal" role="dialog" aria-modal="true" aria-label="图片预览"><h2>{{name(preview)}}</h2><img class="collection-preview" :src="image(preview)" :alt="name(preview)" /><button class="secondary" @click="preview=null">关闭预览</button></section></div>
  </section>
</template>

<style scoped>
.collection-heading,.collection-actions,.collection-tabs,.collection-pagination{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.collection-heading{justify-content:space-between}.collection-tabs{margin:18px 0}.collection-tabs button{padding:10px 16px;border:1px solid #ddd;border-radius:8px;background:white}.collection-tabs .active{background:#ede9fe;color:#5545ca;border-color:#5545ca}.collection-filters{display:flex;gap:12px;align-items:end;flex-wrap:wrap;padding:20px;background:white;border:1px solid #e3e5ed;border-radius:12px}.collection-filters label,.collection-modal>label{display:grid;grid-template-columns:minmax(0,1fr);gap:6px;font-size:13px}.collection-filters input,.collection-filters select,.collection-modal select{height:40px;border:1px solid #d8dce5;border-radius:7px;padding:0 10px;max-width:100%;background:white}.collection-filters label{flex:1 1 160px;min-width:0}.collection-actions{margin:18px 0}.collection-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}.collection-card{background:white;border:1px solid #e1e4ed;border-radius:12px;overflow:hidden;min-width:0}.collection-card.selected{border-color:#5545ca;box-shadow:0 0 0 1px #5545ca}.collection-checkbox{display:flex;align-items:center;gap:8px;padding:12px;font-size:13px}.collection-image{display:block;width:100%;padding:0;border:0;background:#f5f6fa;cursor:zoom-in}.collection-image img{display:block;width:100%;height:220px;object-fit:contain}.collection-card-body{display:grid;gap:7px;padding:14px;overflow-wrap:anywhere}.collection-card-body strong{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.collection-card-body small{color:#637083}.collection-pagination{margin-top:20px}.collection-pagination button{padding:8px 12px}.collection-success{padding:14px;background:#edf8f1;border-radius:8px}.collection-modal{max-width:560px;width:calc(100vw - 32px);max-height:90vh;overflow:auto}.collection-modal .collection-recollect{display:flex;align-items:start;margin-top:18px}.collection-preview{width:100%;max-height:65vh;object-fit:contain}.collection-page{min-width:0}.collection-heading p{margin:0;max-width:620px}@media(max-width:600px){.collection-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.collection-image img{height:180px}.collection-filters{padding:12px}.collection-card-body{padding:10px}.collection-actions button{flex:1}.collection-checkbox{font-size:12px;padding:10px}.collection-pagination{justify-content:center}}

.collection-tabs button{font-size:14px;width:auto;text-align:center}
.collection-filters select,.collection-filters input,.collection-modal select{margin:0;width:100%;min-width:0}
.collection-history-filters label{flex:0 1 240px}
.collection-pagination label{display:flex;align-items:center;gap:6px}.collection-pagination select{width:70px;margin:0;padding:8px}
@media(max-width:600px){.collection-actions strong{flex-basis:100%}.collection-actions button{flex:1 1 120px;white-space:nowrap;min-height:40px}.collection-page{padding:20px 16px}.collection-filters label{flex-basis:120px}.collection-filters label:first-child{flex-basis:100%}.collection-tabs{gap:8px}.collection-tabs button{flex:1}.collection-filters>button{flex:1}.collection-checkbox{align-items:start;line-height:1.5}.collection-image img{height:180px}.collection-card-body{font-size:13px}}
</style>
