<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import SearchableSelect from './SearchableSelect.vue'
import { dialogFocus as vDialogFocus } from './dialog-focus'
import { createSupplyRequestScope, createSupplySubmissionKeys, emptySupplyStrategy, supplyFileStatus, supplyHealthLabels, supplyJobLabels, supplyStageLabels, supplyStrategyPayload, supplyTime, unfinishedSupplyJob, validateSupplyStrategy, type SupplyUsageTask, type SupplyStrategyForm } from './supply-catalog'

const props = defineProps<{ token: string; user: any; initialTab?: string }>()
const emit = defineEmits<{ unauthorized: []; changed: [] }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const headers = computed(() => ({ Authorization: `Bearer ${props.token}` }))
const context = ref<any>(null)
const canViewMaterials = computed(() => context.value?.can_view_materials ?? props.user.role !== 'supply_user')
const tab = ref(['materials','templates','strategies','jobs'].includes(props.initialTab || '') && (props.initialTab !== 'materials' || canViewMaterials.value) ? props.initialTab! : 'templates'), loading = ref(true), busy = ref(''), error = ref(''), notice = ref('')
const canManage = computed(() => !!context.value?.can_manage)
const canAdmin = computed(() => !!context.value?.can_admin)
const tabs = computed(() => [
  { key: 'templates', label: '货盘模板' }, ...(canViewMaterials.value ? [{ key: 'materials', label: '货盘素材' }] : []),
  { key: 'strategies', label: '生成策略' }, { key: 'jobs', label: '生成记录' },
  ...(canManage.value ? [{ key: 'users', label: '用户与代理' }, { key: 'statistics', label: '数据统计' }] : []),
  ...(canAdmin.value ? [{ key: 'settings', label: 'AI 设置' }] : []),
])
const templates = ref<any[]>([]), catalogs = ref<any[]>([]), materials = ref<any[]>([]), materialTotal = ref(0), materialPage = ref(1), materialPageSize = ref(20)
const templateFilters = ref({ search: '', publicStatus: '' })
const appliedTemplateFilters = ref({ ...templateFilters.value })
const templateGroups = ref<{ id: number; name: string }[]>([])
const activeTemplateGroupId = ref<number | null>(null)
const activeTemplateGroupName = computed(() => templateGroups.value.find(group => group.id === activeTemplateGroupId.value)?.name || '全部模板')
const filteredTemplates = computed(() => templates.value.filter(item => {
  const { search, publicStatus } = appliedTemplateFilters.value
  return (activeTemplateGroupId.value === null || item.group_id === activeTemplateGroupId.value)
    && item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())
    && (publicStatus === '' || !!item.supply_public === (publicStatus === 'true'))
}))
const materialTemplate = ref<number | null>(null), materialHealth = ref(''), materialListed = ref('true'), materialSearch = ref('')
const appliedMaterialFilters = ref({ templateId: null as number | null, health: '', listed: 'true', search: '' })
const materialResultListed = ref('true')
const materialsLoading = ref(false), materialPages = computed(() => Math.max(1, Math.ceil(materialTotal.value / materialPageSize.value)))
const showListingPicker = ref(false), listingCandidates = ref<any[]>([]), listingTotal = ref(0), listingPage = ref(1)
const listingLoading = ref(false), listingSelectedIds = ref<number[]>([]), listingTemplate = ref<number | null>(null)
const listingSearch = ref(''), listingError = ref(''), listingPageSize = 60
const listingHoverPreview = ref<{ row: any; anchor: DOMRect; left: number; top: number; width: number; height: number } | null>(null)
const listingPages = computed(() => Math.max(1, Math.ceil(listingTotal.value / listingPageSize)))
const canListMaterial = (row: any) => !!row.sku && !!row.url && !!row.template_id
const selectableListingIds = computed<number[]>(() => listingCandidates.value.filter(canListMaterial).map(row => row.id))
const strategies = ref<any[]>([]), jobs = ref<any[]>([]), jobsLoading = ref(false), jobsScope = ref('own')
const jobPage = ref(1), jobPageSize = ref(30), jobTotal = ref(0), jobPages = computed(() => Math.max(1, Math.ceil(jobTotal.value / jobPageSize.value)))
const managers = ref<any[]>([])
const agents = ref<any[]>([]), users = ref<any[]>([]), statistics = ref<any>(null)
const aiConfig = ref({ api_key: '', configured: false }), showAiConfig = ref(false), agentForm = ref({ id: null as number | null, name: '' })
const showAgent = ref(false), showUser = ref(false), userEditing = ref<number | null>(null)
const userForm = ref({ name: '', email: '', password: '', agent_id: null as number | null, months: 12, is_active: true })
const renewUser = ref<any>(null), renewMonths = ref(12), templateEditing = ref<any>(null), fallbackTitle = ref('')
const showStrategy = ref(false), strategyEditing = ref<number | null>(null), strategyForm = ref<SupplyStrategyForm>(emptySupplyStrategy())
const strategyOptions = ref<any>(null), optionsLoading = ref(false), strategyError = ref(''), dialogError = ref('')
const usageMaterial = ref<any>(null), usage = ref<SupplyUsageTask[]>([]), usageLoading = ref(false), jobDetail = ref<any>(null)
const usagePage = ref(1), usageTotal = ref(0), usageError = ref(''), usageRetryPage = ref(1), usagePageSize = 20
const usagePages = computed(() => Math.max(1, Math.ceil(usageTotal.value / usagePageSize)))
const usageScope = createSupplyRequestScope(), statisticsScope = createSupplyRequestScope()
const preview = ref<any>(null), selectedMaterialIds = ref<number[]>([])
const publicTemplates = computed(() => templates.value.filter(item => item.supply_public))
const selectedTemplate = computed(() => templates.value.find(item => item.id === strategyForm.value.template_id))
const categoryAttributes = computed<any[]>(() => strategyOptions.value?.attributes_by_category?.[strategyForm.value.category_name] || [])
const expectedRows = computed(() => Math.max(1, selectedTemplate.value?.sizes?.length || 1) * Number(strategyForm.value.sku_count || 0) * Number(strategyForm.value.link_count || 0))
const myActiveJob = computed(() => jobs.value.some(item => (!item.user_id || item.user_id === props.user.id) && unfinishedSupplyJob(item)))
const submissionKeys = createSupplySubmissionKeys(() => crypto.randomUUID())
let pollTimer: ReturnType<typeof setInterval> | undefined
let managerRequest = 0
let stopped = false, materialRequest = 0, listingRequest = 0, optionsRequest = 0, jobRequest = 0, accessRefreshing = false
const pollingAbort = new AbortController()
const list = (data: any): any[] => Array.isArray(data) ? data : data?.items || []
function fail(e: any, fallback = '请求失败，请重试') {
  if (e.response?.status === 401) emit('unauthorized')
  if (e.response?.status === 403) void reconcileAccess()
  const detail = e.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item:any)=>`${({name:'名称',email:'邮箱',password:'密码',months:'有效期月数',price:'售价',stock:'库存',agent_id:'代理',category_name:'商品类目',template_id:'产品模板'} as Record<string,string>)[item.loc?.at(-1)] || '输入'}：${item.msg}`).join('；')
  return e.message === 'Network Error' ? '网络连接失败，请重试' : e.message || fallback
}
function clearManagementCache() {
  closeUsage(); statisticsScope.invalidate()
  materialRequest++; listingRequest++; jobRequest++; managerRequest++
  showListingPicker.value=false; listingCandidates.value=[]; listingSelectedIds.value=[]; listingTotal.value=0
  managers.value=[]; users.value=[]; agents.value=[]; statistics.value=null; materials.value=[]; jobs.value=[]
  templates.value=[]; templateGroups.value=[]; activeTemplateGroupId.value=null; selectedMaterialIds.value=[]; materialTotal.value=0; jobTotal.value=0
  showUser.value=false; showAgent.value=false; renewUser.value=null; templateEditing.value=null; usageMaterial.value=null; jobDetail.value=null; preview.value=null
  aiConfig.value={api_key:'',configured:false}; showAiConfig.value=false; jobsScope.value='own'; jobPage.value=1
  materialListed.value='true'; appliedMaterialFilters.value.listed='true'; materialResultListed.value='true'; tab.value='templates'
}
watch(canViewMaterials, allowed => {
  if (allowed) return
  materialRequest++; materials.value=[]; materialTotal.value=0; selectedMaterialIds.value=[]; materialsLoading.value=false
  closeUsage(); preview.value=null
  if (tab.value==='materials') tab.value='templates'
})
watch(canManage, allowed => {
  if (!allowed) { closeUsage(); statisticsScope.invalidate(); statistics.value=null }
}, { flush: 'sync' })
watch(() => [props.token, props.user.id, props.user.company_id], () => {
  closeUsage(); statisticsScope.invalidate(); statistics.value=null
}, { flush: 'sync' })
async function reconcileAccess() {
  if (stopped || accessRefreshing) return
  accessRefreshing=true
  try {
    const {data}=await api.get('/supply/context',{headers:headers.value})
    if (stopped) return
    const lostManagement=canManage.value && !data.can_manage
    context.value=data
    if (lostManagement) { clearManagementCache(); await Promise.allSettled([loadTemplates(),loadMaterials(),loadJobs(true)]) }
  } catch(e:any) {
    if (!stopped) { context.value=null; clearManagementCache(); if(e.response?.status===401) emit('unauthorized') }
  } finally { accessRefreshing=false }
}
async function action(key: string, work: () => Promise<void>) {
  if (busy.value) return
  busy.value = key; error.value = ''; notice.value = ''; dialogError.value = ''
  try { await work() } catch (e: any) { error.value = fail(e); dialogError.value = error.value }
  finally { busy.value = '' }
}
function imageUrl(url: string) { return url?.startsWith('/') ? `${api.defaults.baseURL}${url}` : url }
function templateLabel(id: number) { return templates.value.find(item => item.id === id)?.name || `模板 #${id}` }
function catalogLabel(type: string) { return type === 'tiktok_cross_border' ? '跨境店' : '本土店' }
function strategyCatalogLabel(catalogId: number) {
  const catalog = catalogs.value.find(item => item.id === catalogId)
  return catalog ? `${catalog.name}（${catalogLabel(catalog.template_type)}）` : '—'
}
function progressLabel(job: any) {
  if (typeof job.progress === 'string') return job.progress
  if (typeof job.progress === 'number') return `${job.progress}%`
  if (job.progress && typeof job.progress === 'object') {
    if (job.progress.links_total !== undefined) return `链接 ${job.progress.links_done || 0}/${job.progress.links_total}`
    return Object.entries(job.progress).filter(([key]) => !['images', 'images_checked', 'images_total'].includes(key)).map(([key, value]) => `${({links: '链接', titles: '标题', completed: '已处理', total: '总数'} as Record<string,string>)[key] || key} ${value}`).join(' · ')
  }
  return ''
}
function accountStatus(item: any) {
  if (!item.is_active) return '已停用'
  if (item.expired || (item.supply_expires_at && new Date(item.supply_expires_at).getTime() <= Date.now())) return '已到期'
  return '使用中'
}
function canDownload(job: any) { return supplyFileStatus(job) === '可下载' }
async function loadTemplates() {
  const [templateResponse, groupResponse] = await Promise.all([
    api.get('/supply/templates', { headers: headers.value }),
    api.get('/supply/template-groups', { headers: headers.value }),
  ])
  templates.value = list(templateResponse.data)
  templateGroups.value = list(groupResponse.data)
}
async function searchTemplates() {
  const filters = { ...templateFilters.value, search: templateFilters.value.search.trim() }
  await action('template-search', async () => {
    await loadTemplates()
    appliedTemplateFilters.value = filters
  })
}
async function searchMaterials() {
  appliedMaterialFilters.value = { templateId: materialTemplate.value, health: materialHealth.value,
    listed: materialListed.value, search: materialSearch.value.trim() }
  await loadMaterials(true)
}
async function loadMaterials(reset = false) {
  if (!canViewMaterials.value) return
  if (reset) materialPage.value = 1
  const request = ++materialRequest
  const filters = { ...appliedMaterialFilters.value }
  materialsLoading.value = true
  try {
    const { data } = await api.get('/supply/materials', { headers: headers.value, params: {
      template_id: filters.templateId || undefined, health: filters.health || undefined,
      listed: filters.listed === 'true', search: filters.search || undefined,
      page: materialPage.value, page_size: materialPageSize.value,
    } })
    if (stopped || request !== materialRequest || !canViewMaterials.value) return
    materials.value = list(data); materialTotal.value = data.total ?? materials.value.length
    materialResultListed.value = filters.listed
    selectedMaterialIds.value = []
    if (materialPage.value > materialPages.value) { materialPage.value = materialPages.value; await loadMaterials() }
  } catch (e: any) { if (!stopped && request === materialRequest) error.value = fail(e, '加载素材失败') }
  finally { if (request === materialRequest) materialsLoading.value = false }
}
async function loadStrategies() { strategies.value = list((await api.get('/supply/strategies', { headers: headers.value })).data) }
async function loadJobs(silent = false) {
  if (jobsLoading.value || stopped) return
  const request=++jobRequest
  jobsLoading.value = true
  try {
    const { data } = await api.get('/supply/jobs', { headers: headers.value, params: { scope: canManage.value ? jobsScope.value : 'own', page:jobPage.value, page_size:jobPageSize.value }, signal: pollingAbort.signal })
    if (stopped || request!==jobRequest) return
    jobs.value = list(data)
    jobTotal.value = data.total ?? jobs.value.length
    if (jobDetail.value) jobDetail.value = { ...jobDetail.value, ...jobs.value.find(item => item.id === jobDetail.value.id) }
  } catch (e: any) { if (!stopped && (!silent || [401,403].includes(e.response?.status))) error.value = fail(e, '加载生成记录失败') }
  finally { jobsLoading.value = false }
}
async function loadManagers() {
  const request = ++managerRequest
  const { data } = await api.get('/supply/managers', { headers: headers.value })
  if (!stopped && canManage.value && request === managerRequest) managers.value = list(data)
}
async function loadUsersAndManagers() {
  const results = await Promise.allSettled([loadUsers(), loadManagers()])
  const failure = results.find(item => item.status === 'rejected') as PromiseRejectedResult | undefined
  if (failure) throw failure.reason
}
async function loadUsers() {
  if (!canAdmin.value) {
    users.value = list((await api.get('/supply/users', {headers:headers.value})).data)
    agents.value = Array.from(new Map(users.value.filter(item=>item.agent_id).map(item=>[item.agent_id,{id:item.agent_id,name:item.agent_name,created_at:item.agent_created_at}])).values())
    return
  }
  const results = await Promise.allSettled([api.get('/supply/agents', { headers: headers.value }), api.get('/supply/users', { headers: headers.value })])
  if (results[0].status === 'fulfilled') agents.value = list(results[0].value.data)
  if (results[1].status === 'fulfilled') users.value = list(results[1].value.data)
  const failure = results.find(item => item.status === 'rejected') as PromiseRejectedResult | undefined
  if (failure) throw failure.reason
}
async function loadSettings() {
  const { data } = await api.get('/supply/ai-config', { headers: headers.value })
  aiConfig.value = { api_key: '', configured: !!data.configured }
}
async function loadStatistics() {
  const request = statisticsScope.start()
  try {
    const { data } = await api.get('/supply/statistics', { headers: headers.value, signal: request.signal })
    if (request.isCurrent() && !stopped && canManage.value) statistics.value = data
  } catch (e) { if (request.isCurrent() && !stopped) throw e }
}
async function reload() {
  loading.value = true; error.value = ''
  const managedBefore=canManage.value
  try {
    context.value = (await api.get('/supply/context', { headers: headers.value })).data
    if (!canManage.value && (managedBefore || !['materials','templates','strategies','jobs'].includes(tab.value))) clearManagementCache()
    if (!tabs.value.some(item => item.key===tab.value)) tab.value=canViewMaterials.value?'materials':'templates'
    const results = await Promise.allSettled([loadTemplates(), api.get('/supply/catalogs', { headers: headers.value }).then(result => { catalogs.value = list(result.data) }), loadStrategies(), loadJobs(), loadMaterials(), ...(tab.value === 'users' && canManage.value ? [loadUsersAndManagers()] : [])])
    const failure = results.find(result => result.status === 'rejected') as PromiseRejectedResult | undefined
    if (failure) throw failure.reason
  } catch (e: any) { error.value = fail(e) }
  finally { loading.value = false }
}
watch(tab, value => {
  closeUsage(); statisticsScope.invalidate()
  error.value = ''; notice.value = ''
  if (value === 'users') void action('load-users', loadUsersAndManagers)
  if (value === 'statistics') void action('load-statistics', loadStatistics)
  if (value === 'settings') void action('load-settings', loadSettings)
  if (value === 'jobs') void loadJobs()
}, { flush: 'sync' })
async function toggleListing(row: any) {
  await action(`material-${row.id}`, async () => {
    await api.patch(`/supply/materials/${row.id}`, { supply_listed: !row.supply_listed }, { headers: headers.value })
    notice.value = row.supply_listed ? '素材已下架，已提交任务继续使用快照。' : '素材已重新上架。'
    await Promise.all([loadMaterials(), loadTemplates()]); emit('changed')
  })
}
async function batchListing(listed: boolean) {
  await action('batch-listing', async () => {
    const results = await Promise.allSettled(selectedMaterialIds.value.map(id => api.patch(`/supply/materials/${id}`, { supply_listed: listed }, { headers: headers.value })))
    const failed = results.filter(item => item.status === 'rejected')
    await Promise.all([loadMaterials(), loadTemplates()]); emit('changed')
    if (failed.length) { error.value = `${failed.length} 条操作失败，其他素材已处理。${fail((failed[0] as PromiseRejectedResult).reason)}` }
    else notice.value = listed ? '所选素材已重新上架。' : '所选素材已下架，已提交任务继续使用快照。'
  })
}
function closeListingPicker() {
  if (busy.value) return
  showListingPicker.value=false; listingRequest++; listingSelectedIds.value=[]
}
function showListingHoverPreview(row: any, event: PointerEvent) {
  if (event.pointerType !== 'mouse' || !row.url) return
  const target = event.currentTarget as HTMLElement
  const image = target.querySelector('img')
  positionListingHoverPreview(row, target.getBoundingClientRect(), (image?.naturalWidth || 1) / (image?.naturalHeight || 1))
}
function positionListingHoverPreview(row: any, rect: DOMRect, ratio: number) {
  const imageWidth = Math.min(350, window.innerWidth - 34, Math.min(470, window.innerHeight - 34) * ratio)
  const width = imageWidth + 10, height = imageWidth / ratio + 10
  const left = rect.right + 12 + width <= window.innerWidth - 12 ? rect.right + 12 : rect.left - width - 12
  listingHoverPreview.value = { row, anchor: rect, width, height,
    left: Math.max(12, Math.min(left, window.innerWidth - width - 12)),
    top: Math.max(12, Math.min(rect.top, window.innerHeight - height - 12)) }
}
function resizeListingHoverPreview(event: Event) {
  const preview = listingHoverPreview.value, image = event.currentTarget as HTMLImageElement
  if (preview && image.naturalWidth && image.naturalHeight) {
    positionListingHoverPreview(preview.row, preview.anchor, image.naturalWidth / image.naturalHeight)
  }
}
function clearListingHoverPreview() { listingHoverPreview.value = null }
watch(showListingPicker, clearListingHoverPreview)
async function openListingPicker() {
  if (!canManage.value || busy.value) return
  listingTemplate.value=null; listingSearch.value=''
  listingCandidates.value=[]; listingTotal.value=0; listingSelectedIds.value=[]
  listingError.value=''; dialogError.value=''; showListingPicker.value=true
  await loadListingCandidates(true)
}
async function loadListingCandidates(reset = false) {
  if (!showListingPicker.value || !canManage.value) return
  clearListingHoverPreview()
  if (reset) listingPage.value=1
  const request=++listingRequest
  listingLoading.value=true; listingError.value=''; listingSelectedIds.value=[]; listingCandidates.value=[]
  try {
    const {data}=await api.get('/supply/materials',{headers:headers.value,params:{
      source:'library', template_id:listingTemplate.value || undefined,
      search:listingSearch.value.trim() || undefined,
      page:listingPage.value, page_size:listingPageSize,
    }})
    if (stopped || request!==listingRequest || !canManage.value) return
    listingCandidates.value=list(data); listingTotal.value=data.total ?? listingCandidates.value.length
    if (listingPage.value>listingPages.value) { listingPage.value=listingPages.value; await loadListingCandidates() }
  } catch(e:any) {
    if (!stopped && request===listingRequest) listingError.value=fail(e,'加载素材库失败')
  } finally { if (request===listingRequest) listingLoading.value=false }
}
async function listSelectedMaterials() {
  if (!listingSelectedIds.value.length || listingLoading.value) return
  await action('list-selected', async () => {
    listingError.value=''
    const ids=[...listingSelectedIds.value]
    const results=await Promise.allSettled(ids.map(id=>api.patch(`/supply/materials/${id}`,{supply_listed:true},{headers:headers.value})))
    const failedIds=ids.filter((_,index)=>results[index].status==='rejected')
    const succeeded=ids.filter(id=>!failedIds.includes(id))
    listingCandidates.value=listingCandidates.value.filter(row=>!succeeded.includes(row.id))
    listingTotal.value=Math.max(0,listingTotal.value-succeeded.length); listingSelectedIds.value=failedIds
    if (failedIds.length) {
      const failure=results.find(result=>result.status==='rejected') as PromiseRejectedResult
      listingError.value=`${succeeded.length} 条已上架，${failedIds.length} 条失败。${fail(failure.reason)}`
    } else { showListingPicker.value=false; notice.value=`已上架 ${succeeded.length} 条素材。` }
    materialListed.value='true'
    appliedMaterialFilters.value.listed='true'
    await Promise.all([loadMaterials(true),loadTemplates()]); emit('changed')
  })
}
function closeUsage() {
  usageScope.invalidate(); usageMaterial.value=null; usage.value=[]; usageLoading.value=false
  usagePage.value=1; usageTotal.value=0; usageError.value=''; usageRetryPage.value=1
}
async function showUsage(row: any) {
  closeUsage(); usageMaterial.value=row
  await loadUsage(1)
}
async function loadUsage(page: number) {
  if (!usageMaterial.value || usageLoading.value || stopped) return
  const identity = usageMaterial.value.id
  const request = usageScope.start()
  usageLoading.value=true; usageError.value=''; usageRetryPage.value=page
  try {
    const { data } = await api.get(`/supply/materials/${identity}/usage`, {
      headers: headers.value, params: { page, page_size: usagePageSize }, signal: request.signal,
    })
    if (request.isCurrent() && !stopped) {
      usage.value=data.items; usageTotal.value=data.total; usagePage.value=data.page
    }
  } catch (e: any) {
    if (request.isCurrent() && !stopped) usageError.value=fail(e, '加载使用记录失败，请重试')
  } finally { if (request.isCurrent()) usageLoading.value=false }
}
async function togglePublic(row: any) {
  await action(`template-${row.id}`, async () => {
    await api.patch(`/supply/templates/${row.id}`, { supply_public: !row.supply_public }, { headers: headers.value })
    await loadTemplates(); emit('changed'); notice.value = row.supply_public ? '模板已取消公开，已提交任务继续使用快照。' : '模板已公开。'
  })
}
function editFallback(row: any) { templateEditing.value = row; fallbackTitle.value = row.supply_fallback_title || ''; dialogError.value = '' }
async function saveFallback() {
  const title = fallbackTitle.value.trim().replace(/\s+/g, ' ')
  if (title.length < 25 || title.length > 220 || !/^[\x20-\x7E]+$/.test(title)) { dialogError.value = '请填写 25–220 个字符的英文商品基础标题'; return }
  await action('fallback', async () => {
    await api.patch(`/supply/templates/${templateEditing.value.id}`, { supply_fallback_title: title }, { headers: headers.value })
    templateEditing.value = null; await loadTemplates(); emit('changed'); notice.value = '兜底基础标题已保存。'
  })
}
async function loadStrategyOptions(preserve = false) {
  const request = ++optionsRequest
  strategyOptions.value = null; optionsLoading.value = true; strategyError.value = ''
  if (!preserve) { strategyForm.value.category_name = ''; strategyForm.value.attributes = {} }
  const catalogId = strategyForm.value.category_catalog_id
  try {
    if (catalogId) {
      const { data } = await api.get(`/supply/catalogs/${catalogId}/options`, { headers: headers.value })
      if (request === optionsRequest && showStrategy.value) strategyOptions.value = data
    }
  } catch (e: any) { if (request === optionsRequest) strategyError.value = fail(e, '加载类目选项失败') }
  finally { if (request === optionsRequest) optionsLoading.value = false }
}
function editStrategy(row?: any) {
  strategyEditing.value = row?.id || null
  strategyForm.value = row ? supplyStrategyPayload({ ...emptySupplyStrategy(), ...row, attributes: Object.fromEntries(Object.entries(row.attributes || {}).map(([key,value])=>[key, Array.isArray(value) ? value.join(', ') : String(value)])) }) : emptySupplyStrategy()
  strategyError.value = ''; showStrategy.value = true
  if (strategyForm.value.category_catalog_id) void loadStrategyOptions(true)
  else strategyOptions.value = null
}
async function saveStrategy() {
  strategyError.value = validateSupplyStrategy(strategyForm.value, selectedTemplate.value?.sizes?.length || 1, categoryAttributes.value)
  if (strategyError.value) return
  if (!strategyOptions.value?.categories?.some((category: any) => category.name === strategyForm.value.category_name)) { strategyError.value = '商品类目已不可用，请重新选择'; return }
  if (!publicTemplates.value.some(item => item.id === strategyForm.value.template_id)) { strategyError.value = '产品模板已取消公开，请重新选择'; return }
  await action('strategy', async () => {
    const form = { ...supplyStrategyPayload(strategyForm.value), attributes: Object.fromEntries(categoryAttributes.value.filter(field => strategyForm.value.attributes[field.field]?.trim()).map(field => [field.field, strategyForm.value.attributes[field.field].trim()])) }
    try {
      if (strategyEditing.value) await api.patch(`/supply/strategies/${strategyEditing.value}`, form, { headers: headers.value })
      else await api.post('/supply/strategies', form, { headers: headers.value })
    } catch (e: any) { strategyError.value = fail(e); throw e }
    showStrategy.value = false; await loadStrategies(); notice.value = '策略已保存。'
  })
}
async function deleteStrategy(row: any) {
  if (!confirm(`删除策略“${row.name}”？历史任务会保留。`)) return
  await action('delete-strategy', async () => { await api.delete(`/supply/strategies/${row.id}`, { headers: headers.value }); await loadStrategies() })
}
async function submitStrategy(row: any) {
  await action(`submit-${row.id}`, async () => {
    await api.post('/supply/jobs', { strategy_id: row.id, idempotency_key: submissionKeys.forStrategy(row.id) }, { headers: headers.value })
    submissionKeys.complete(); jobPage.value=1; jobsScope.value='own'; await loadJobs(); tab.value = 'jobs'; notice.value = '任务已提交，后台完成后可在这里下载 Excel。'
  })
}
async function cancelJob(row: any) {
  if (!confirm(`取消生成任务 #${row.id}？取消后不会自动恢复。`)) return
  await action(`cancel-${row.id}`, async () => { await api.post(`/supply/jobs/${row.id}/cancel`, {}, { headers: headers.value }); await loadJobs() })
}
async function viewJob(row: any) {
  await action('job-detail', async () => { jobDetail.value = (await api.get(`/supply/jobs/${row.id}`, { headers: headers.value })).data })
}
async function downloadJob(row: any) {
  await action(`download-${row.id}`, async () => {
    try {
      const result = await api.get(`/supply/jobs/${row.id}/download`, { headers: headers.value, responseType: 'blob' })
      const url = URL.createObjectURL(result.data), link = document.createElement('a')
      link.href = url; link.download = row.filename || `TikTok-货盘-${row.id}.xlsx`; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      notice.value = '下载已开始，文件可下载期限为生成后 7 天。'
    } catch (e: any) {
      if (e.response?.data instanceof Blob) {
        try { e.response.data = JSON.parse(await e.response.data.text()) } catch { /* Keep ordinary request error. */ }
      }
      throw e
    }
  })
}
function editAgent(row?: any) { agentForm.value = { id: row?.id || null, name: row?.name || '' }; dialogError.value = ''; showAgent.value = true }
async function saveAgent() {
  if (!agentForm.value.name.trim()) { dialogError.value = '请填写代理名称'; return }
  await action('agent', async () => {
    if (agentForm.value.id) await api.patch(`/supply/agents/${agentForm.value.id}`, { name: agentForm.value.name.trim() }, { headers: headers.value })
    else await api.post('/supply/agents', { name: agentForm.value.name.trim() }, { headers: headers.value })
    showAgent.value = false; await loadUsers(); notice.value = '代理已保存。'
  })
}
function editUser(row?: any) {
  userEditing.value = row?.id || null
  userForm.value = { name: row?.name || '', email: row?.email || '', password: '', agent_id: row?.agent_id || null, months: 12, is_active: row?.is_active ?? true }
  dialogError.value = ''; showUser.value = true
}
async function saveUser() {
  const form = userForm.value
  if (!form.name.trim() || !form.email.trim() || !form.agent_id || (!userEditing.value && !form.password)) { dialogError.value = '请填写姓名、邮箱、密码并选择代理'; return }
  if (!userEditing.value && (!Number.isInteger(form.months) || form.months < 1)) { dialogError.value = '使用有效期必须为正整数月'; return }
  await action('user', async () => {
    if (userEditing.value) await api.patch(`/supply/users/${userEditing.value}`, { name: form.name.trim(), email: form.email.trim(), agent_id: form.agent_id, ...(form.password ? { password: form.password } : {}) }, { headers: headers.value })
    else await api.post('/supply/users', { name: form.name.trim(), email: form.email.trim(), password: form.password, agent_id: form.agent_id, months: form.months }, { headers: headers.value })
    showUser.value = false; userForm.value.password = ''; await loadUsers(); notice.value = '货盘用户已保存。'
  })
}
async function toggleUser(row: any) {
  if (row.is_active && !confirm(`停用“${row.name}”？该用户未完成任务会取消，并禁止下载。`)) return
  await action(`user-${row.id}`, async () => {
    await api.patch(`/supply/users/${row.id}`, { is_active: !row.is_active }, { headers: headers.value })
    await loadUsers(); notice.value = row.is_active ? '账号已停用。' : '账号已恢复；到期时间不变。'
  })
}
async function renew() {
  if (!Number.isInteger(renewMonths.value) || renewMonths.value < 1) { dialogError.value = '续期月数必须为正整数'; return }
  await action('renew', async () => {
    await api.post(`/supply/users/${renewUser.value.id}/renew`, { months: renewMonths.value }, { headers: headers.value })
    renewUser.value = null; await loadUsers(); notice.value = '账号已续期；人工停用状态保持不变。'
  })
}
function openAiConfig() {
  aiConfig.value.api_key = ''; dialogError.value = ''; showAiConfig.value = true
}
function closeAiConfig() {
  showAiConfig.value = false; aiConfig.value.api_key = ''; dialogError.value = ''
}
async function saveAi(test = false) {
  if (!test && !aiConfig.value.api_key.trim()) { dialogError.value = '请输入 DeepSeek API Key'; return }
  await action('ai-config', async () => {
    if (test) {
      const { data } = await api.post('/supply/ai-config/test', {}, { headers: headers.value })
      notice.value = data.message || 'DeepSeek 连接测试成功。'
    } else {
      const { data } = await api.put('/supply/ai-config', { api_key: aiConfig.value.api_key.trim() }, { headers: headers.value })
      aiConfig.value.configured = !!data.configured; closeAiConfig(); notice.value = '货盘 DeepSeek 配置已保存。'
    }
  })
}
onMounted(async () => {
  window.addEventListener('resize', clearListingHoverPreview)
  await reload()
  if (!stopped) pollTimer = setInterval(() => { if (props.token && !document.hidden) void loadJobs(true) }, 5000)
})
onUnmounted(() => { window.removeEventListener('resize', clearListingHoverPreview); stopped = true; closeUsage(); statisticsScope.invalidate(); materialRequest++; listingRequest++; optionsRequest++; jobRequest++; pollingAbort.abort(); if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <section class="page supply-catalog">
    <div v-if="user.role==='supply_user'" class="supply-intro"><div class="supply-account">使用到期：{{supplyTime(context?.user?.supply_expires_at || user.supply_expires_at)}}</div></div>
    <p v-if="error" class="error supply-message" role="alert">{{error}}</p><p v-if="notice" class="supply-notice" role="status">{{notice}}</p>
    <div v-if="loading && !context" class="empty">正在加载货盘…</div>
    <template v-else-if="context">
      <div class="material-usage-tabs supply-tabs" role="navigation" aria-label="货盘功能"><button v-for="item in tabs" :key="item.key" :class="{active:tab===item.key}" @click="tab=item.key">{{item.label}}</button></div>
      <section v-if="tab==='materials' && canViewMaterials">
        <form class="supply-filters" @submit.prevent="searchMaterials"><label>产品模板<select v-model="materialTemplate"><option :value="null">全部模板</option><option v-for="item in templates" :key="item.id" :value="item.id">{{item.name}}</option></select></label><label>图片状态<select v-model="materialHealth"><option value="">全部状态</option><option v-for="(label,key) in supplyHealthLabels" :key="key" :value="key">{{label}}</option></select></label><label v-if="canManage">上架状态<select v-model="materialListed" :disabled="materialsLoading || !!busy"><option value="true">已上架</option><option value="false">已下架</option></select></label><label>搜索<input v-model="materialSearch" placeholder="素材名称或 SKU"/></label><button class="primary" :disabled="materialsLoading">查询</button></form>
        <div class="supply-section-heading"><span>共 {{materialTotal}} 条素材</span><div v-if="canManage" class="supply-actions"><button class="primary" :disabled="!!busy" @click="openListingPicker">上架</button><button v-if="materialResultListed==='true'" class="secondary" :disabled="!!busy || materialsLoading || !selectedMaterialIds.length" @click="batchListing(false)">批量下架</button><button v-else class="secondary" :disabled="!!busy || materialsLoading || !selectedMaterialIds.length" @click="batchListing(true)">批量重新上架</button></div></div>
        <div v-if="materialsLoading" class="empty" role="status">正在读取素材…</div>
        <div v-else class="supply-table-wrap supply-material-list" :class="{manageable:canManage}">
          <table aria-label="货盘素材列表">
            <thead><tr>
              <th v-if="canManage" class="supply-material-selection"><label class="supply-check"><input type="checkbox" :disabled="!materials.length || !!busy" :checked="materials.length>0 && selectedMaterialIds.length===materials.length" :indeterminate="selectedMaterialIds.length>0 && selectedMaterialIds.length<materials.length" aria-label="全选本页货盘素材" @change="selectedMaterialIds=selectedMaterialIds.length===materials.length?[]:materials.map(item=>item.id)"/>全选</label></th>
              <th>缩略图</th><th>SKU</th><th>模板</th><th>上架状态</th><th v-if="canManage">使用情况</th><th v-if="canManage">操作</th>
            </tr></thead>
            <tbody><tr v-for="row in materials" :key="row.id" :class="{selected:selectedMaterialIds.includes(row.id)}">
              <td v-if="canManage" class="supply-material-selection"><input v-model="selectedMaterialIds" :disabled="!!busy" type="checkbox" :value="row.id" :aria-label="`选择素材 ${row.sku || row.id}`"/></td>
              <td><button type="button" class="material-list-thumbnail" :title="row.name || row.sku" :aria-label="`预览 ${row.sku || row.name}`" @click="preview=row"><img :src="imageUrl(row.url)" :alt="row.name || row.sku" loading="lazy"/></button></td>
              <td><code>{{row.sku || row.name || `素材 #${row.id}`}}</code></td>
              <td>{{row.template_name || templateLabel(row.template_id)}}</td>
              <td><span class="supply-tag" :class="{listed:row.supply_listed}">{{row.supply_listed?'已上架':'已下架'}}</span></td>
              <td v-if="canManage"><button type="button" class="supply-usage-button" @click="showUsage(row)">{{row.user_count || 0}} 人使用 · {{row.use_count || 0}} 次链接使用</button></td>
              <td v-if="canManage"><div class="supply-actions"><button type="button" class="secondary" :disabled="!!busy" @click="toggleListing(row)">{{row.supply_listed?'下架':'重新上架'}}</button></div></td>
            </tr></tbody>
          </table>
        </div>
        <p v-if="!materialsLoading && !materials.length" class="empty">暂无符合条件的素材。</p>
        <footer class="supply-pagination"><label>每页<select v-model.number="materialPageSize" :disabled="materialsLoading" @change="loadMaterials(true)"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option><option :value="500">500</option><option :value="1000">1000</option></select>条</label><button :disabled="materialsLoading || materialPage===1" @click="materialPage--;loadMaterials()">上一页</button><span>{{materialPage}} / {{materialPages}}</span><button :disabled="materialsLoading || materialPage>=materialPages" @click="materialPage++;loadMaterials()">下一页</button></footer>
      </section>
      <section v-else-if="tab==='templates'">
        <form class="supply-template-toolbar" @submit.prevent="searchTemplates">
          <input v-model="templateFilters.search" class="supply-template-search" aria-label="搜索模板名称" placeholder="搜索模板名称"/>
          <label>是否公开<select v-model="templateFilters.publicStatus"><option value="">全部</option><option value="true">已公开</option><option value="false">未公开</option></select></label>
          <button type="submit" class="primary" :disabled="loading || !!busy">{{busy==='template-search'?'搜索中…':'搜索'}}</button>
        </form>
        <div class="template-layout supply-template-layout">
          <section class="groups" aria-label="模板分类">
            <div class="groups-heading"><h3>模板分类</h3></div>
            <button type="button" :class="{selected:activeTemplateGroupId===null}" :aria-pressed="activeTemplateGroupId===null" @click="activeTemplateGroupId=null">全部模板</button>
            <button v-for="group in templateGroups" :key="group.id" type="button" :class="{selected:activeTemplateGroupId===group.id}" :aria-pressed="activeTemplateGroupId===group.id" @click="activeTemplateGroupId=group.id">{{group.name}}</button>
          </section>
          <section class="supply-template-results">
            <div class="section-heading"><h2>{{activeTemplateGroupName}}</h2><span>共 {{filteredTemplates.length}} 个模板</span></div>
            <div class="supply-template-grid">
              <article v-for="item in filteredTemplates" :key="item.id" class="supply-card">
                <div class="supply-template-cover">
                  <img v-if="item.cover_url" :src="imageUrl(item.cover_url)" :alt="item.name" loading="lazy"/>
                  <span v-else>暂无模板图片</span>
                </div>
                <div class="supply-section-heading"><h3>{{item.name}}</h3><span class="supply-tag" :class="{published:item.supply_public}">{{item.supply_public?'已公开':'未公开'}}</span></div>
                <p class="supply-template-description">{{item.description || '暂无模板描述'}}</p>
                <p v-if="canManage" class="supply-fallback">{{item.supply_fallback_title || '尚未设置兜底基础标题'}}</p>
                <div v-if="canManage" class="supply-actions"><button class="primary" :disabled="!!busy" @click="togglePublic(item)">{{item.supply_public?'取消公开':'公开'}}</button><button v-if="canAdmin" class="secondary" :disabled="!!busy" @click="editFallback(item)">兜底标题</button></div>
              </article>
            </div><p v-if="!filteredTemplates.length" class="empty">暂无符合条件的产品模板。</p>
          </section>
        </div>
      </section>
      <section v-else-if="tab==='strategies'">
        <div class="supply-section-heading"><p>每个链接 5–9 个素材 SKU，每次生成 10–50 个商品组。</p><button class="primary" :disabled="!!busy" @click="editStrategy()">新增策略</button></div>
        <div class="supply-table-wrap"><table><thead><tr><th>策略</th><th>产品模板</th><th>类目库/店铺类型</th><th>类目</th><th>售价</th><th>生成数量</th><th>操作</th></tr></thead><tbody><tr v-for="row in strategies" :key="row.id"><td>{{row.name}}</td><td>{{templateLabel(row.template_id)}}</td><td>{{strategyCatalogLabel(row.category_catalog_id)}}</td><td>{{row.category_name}}</td><td>{{row.price}}</td><td>{{row.sku_count}} SKU × {{row.link_count}} 链接</td><td><div class="supply-actions"><button class="primary" :disabled="!!busy || myActiveJob" @click="submitStrategy(row)">{{busy===`submit-${row.id}`?'提交中…':'生成表格'}}</button><button :disabled="!!busy" @click="editStrategy(row)">编辑</button><button class="danger" :disabled="!!busy" @click="deleteStrategy(row)">删除</button></div></td></tr></tbody></table></div><p v-if="myActiveJob" class="supply-help">你有一个未完成任务，完成或取消后可再次提交。</p><p v-if="!strategies.length" class="empty">尚未配置策略，创建策略后即可生成表格。</p>
      </section>
      <section v-else-if="tab==='jobs'">
        <div class="supply-section-heading"><p>后台处理期间可以离开页面；完成后下载 Excel，文件保留 7 天。</p><div class="supply-actions supply-job-controls"><select v-if="canManage" v-model="jobsScope" aria-label="任务范围" @change="jobPage=1;loadJobs()"><option value="own">我的任务</option><option value="company">公司任务</option></select><button class="secondary" :disabled="jobsLoading" @click="loadJobs()">刷新记录</button></div></div>
        <div class="supply-table-wrap"><table><thead><tr><th>任务</th><th v-if="canManage">用户 / 代理</th><th>状态</th><th>进度</th><th>时间</th><th>文件 / 操作</th></tr></thead><tbody><tr v-for="row in jobs" :key="row.id"><td>#{{row.id}}<small>{{row.strategy_name || ''}}</small></td><td v-if="canManage">{{row.user_name || '—'}}<small>{{row.agent_name || '内部使用'}}</small></td><td><span :class="['supply-tag',row.state]">{{supplyJobLabels[row.state] || row.state}}</span><small v-if="row.error" class="error">{{row.error}}</small></td><td>{{supplyStageLabels[row.stage] || row.stage || '等待处理'}}<small>{{progressLabel(row)}}</small></td><td>{{supplyTime(row.created_at)}}<small v-if="row.completed_at">完成：{{supplyTime(row.completed_at)}}</small></td><td><div class="supply-actions"><button v-if="canDownload(row)" class="primary" :disabled="!!busy" @click="downloadJob(row)">{{busy===`download-${row.id}`?'下载中…':'下载 Excel'}}</button><span v-else>{{supplyFileStatus(row)}}</span><button :disabled="!!busy" @click="viewJob(row)">详情</button><button v-if="unfinishedSupplyJob(row)" class="danger" :disabled="!!busy" @click="cancelJob(row)">取消</button></div><small v-if="row.output_expires_at">到期：{{supplyTime(row.output_expires_at)}}</small></td></tr></tbody></table></div><p v-if="!jobs.length" class="empty">暂无生成记录。</p><footer class="supply-pagination"><span>共 {{jobTotal}} 条</span><label>每页<select v-model.number="jobPageSize" :disabled="jobsLoading" @change="jobPage=1;loadJobs()"><option :value="30">30</option><option :value="50">50</option><option :value="100">100</option></select>条</label><button :disabled="jobsLoading || jobPage===1" @click="jobPage--;loadJobs()">上一页</button><span>{{jobPage}} / {{jobPages}}</span><button :disabled="jobsLoading || jobPage>=jobPages" @click="jobPage++;loadJobs()">下一页</button></footer>
      </section>
      <section v-else-if="tab==='users' && canManage">
        <div class="supply-section-heading"><h3>货盘管理</h3></div>
        <div class="supply-table-wrap">
          <table>
            <thead><tr><th>成员</th><th>运营组</th><th>邮箱</th></tr></thead>
            <tbody><tr v-for="row in managers" :key="row.id"><td>{{row.name}}</td><td>{{row.group_name || '未分组'}}</td><td class="supply-email">{{row.email}}</td></tr></tbody>
          </table>
        </div><p v-if="!managers.length && busy!=='load-users' && !loading" class="empty">暂无已授予货盘管理权限的人员。</p>
        <div class="supply-section-heading"><h3>货盘代理</h3><button v-if="canAdmin" class="secondary" :disabled="!!busy" @click="editAgent()">新增货盘代理</button></div>
        <div class="supply-table-wrap">
          <table>
            <thead><tr><th>ID</th><th>创建时间</th><th>姓名</th><th v-if="canAdmin">操作</th></tr></thead>
            <tbody><tr v-for="row in agents" :key="row.id"><td>{{row.id}}</td><td>{{supplyTime(row.created_at)}}</td><td>{{row.name}}</td><td v-if="canAdmin"><button :disabled="!!busy" @click="editAgent(row)">编辑</button></td></tr></tbody>
          </table>
        </div><p v-if="!agents.length" class="empty">暂无代理。</p>
        <div class="supply-section-heading"><h3>货盘用户</h3><button v-if="canAdmin" class="secondary" :disabled="!!busy || !agents.length" @click="editUser()">创建货盘用户</button></div><p class="supply-help">账号由公司管理员创建，并绑定代理。{{canAdmin?'续期不会解除停用，恢复不会延长有效期。':'货盘管理员可查看用户信息，账号管理由公司管理员处理。'}}</p>
        <div class="supply-table-wrap"><table><thead><tr><th>用户</th><th>邮箱</th><th>代理</th><th>状态</th><th>使用到期</th><th v-if="canAdmin">操作</th></tr></thead><tbody><tr v-for="row in users" :key="row.id"><td>{{row.name}}</td><td class="supply-email">{{row.email}}</td><td>{{row.agent_name || agents.find(agent=>agent.id===row.agent_id)?.name || '—'}}</td><td>{{accountStatus(row)}}</td><td>{{supplyTime(row.supply_expires_at)}}</td><td v-if="canAdmin"><div class="supply-actions"><button :disabled="!!busy" @click="editUser(row)">编辑</button><button :disabled="!!busy" @click="renewUser=row;renewMonths=12;dialogError=''">续期</button><button :class="{danger:row.is_active}" :disabled="!!busy" @click="toggleUser(row)">{{row.is_active?'停用':'恢复'}}</button></div></td></tr></tbody></table></div><p v-if="!users.length" class="empty">暂无货盘用户。</p>
      </section>
      <section v-else-if="tab==='statistics' && canManage">
        <div class="supply-section-heading"><p>按成功完成任务中的最终素材统计，下载单独记录。</p><button class="secondary" :disabled="!!busy" @click="action('load-statistics',loadStatistics)">刷新统计</button></div>
        <div v-if="statistics" class="supply-metrics"><article><span>成功任务</span><b>{{statistics.summary?.success_count ?? statistics.summary?.job_count ?? statistics.job_count ?? 0}}</b></article><article><span>使用用户</span><b>{{statistics.summary?.user_count ?? statistics.user_count ?? 0}}</b></article><article><span>素材链接使用</span><b>{{statistics.summary?.use_count ?? 0}}</b></article><article><span>下载次数</span><b>{{statistics.summary?.download_count ?? statistics.download_count ?? 0}}</b></article></div>
        <h3>代理统计</h3><div class="supply-table-wrap"><table><thead><tr><th>代理</th><th>用户数</th><th>成功任务</th><th>下载次数</th></tr></thead><tbody><tr v-for="(row,index) in statistics?.agents || []" :key="row.agent_id || index"><td>{{row.agent_name || row.name || '内部使用'}}</td><td>{{row.user_count || 0}}</td><td>{{row.success_count ?? row.job_count ?? 0}}</td><td>{{row.download_count ?? '—'}}</td></tr></tbody></table></div>
      </section>
      <section v-else-if="tab==='settings' && canAdmin">
        <h3>货盘 DeepSeek 配置</h3>
        <p class="supply-help">固定使用 deepseek-flash 在后台生成货盘商品标题；调用失败会使用产品模板的基础标题。</p>
        <div class="shop-actions"><span class="miaoshou-status" :class="aiConfig.configured?'configured':'missing'">{{aiConfig.configured?'货盘 DeepSeek API Key 已配置':'请先配置货盘 DeepSeek API Key'}}</span><button class="secondary" :disabled="!!busy" @click="openAiConfig">{{aiConfig.configured?'更新 API Key':'配置 API Key'}}</button><button class="secondary" :disabled="!!busy || !aiConfig.configured" @click="saveAi(true)">{{busy==='ai-config'?'测试中…':'测试连接'}}</button></div>
      </section>
    </template>

    <div v-if="showListingPicker && canManage" class="modal-backdrop" @click.self="closeListingPicker">
      <section v-dialog-focus="{close:closeListingPicker,busy:!!busy}" class="modal-card supply-dialog supply-wide-dialog supply-listing-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-listing-title">
        <button class="modal-close" :disabled="!!busy" aria-label="关闭上架窗口" @click="closeListingPicker">×</button>
        <h2 id="supply-listing-title">从素材库上架</h2>
        <div class="supply-listing-content" @scroll.passive="clearListingHoverPreview">
        <form class="supply-filters" @submit.prevent="loadListingCandidates(true)">
          <label>产品模板<select v-model="listingTemplate" :disabled="!!busy"><option :value="null">全部模板</option><option v-for="item in templates" :key="item.id" :value="item.id">{{item.name}}</option></select></label>
          <label>搜索<input v-model="listingSearch" :disabled="!!busy" placeholder="素材名称或 SKU"/></label>
          <button class="secondary" :disabled="listingLoading || !!busy">查询</button>
        </form>
        <div class="supply-section-heading"><span>共 {{listingTotal}} 条可选素材</span><label class="supply-check"><input type="checkbox" :checked="selectableListingIds.length>0 && selectableListingIds.every(id=>listingSelectedIds.includes(id))" :indeterminate="listingSelectedIds.length>0 && listingSelectedIds.length<selectableListingIds.length" :disabled="listingLoading || !!busy || !selectableListingIds.length" @change="listingSelectedIds=listingSelectedIds.length===selectableListingIds.length?[]:[...selectableListingIds]"/>本页全选</label></div>
        <p v-if="listingError || dialogError" class="error" role="alert">{{listingError || dialogError}}</p>
        <div v-if="listingLoading" class="empty" role="status">正在读取素材库…</div>
        <div v-else class="supply-material-grid">
          <label v-for="row in listingCandidates" :key="row.id" class="supply-material supply-listing-option" :class="{selected:listingSelectedIds.includes(row.id)}">
            <div class="supply-listing-image" @pointerenter="showListingHoverPreview(row, $event)" @pointerleave="clearListingHoverPreview"><img :src="imageUrl(row.url)" :alt="row.name || row.sku" loading="lazy"/></div>
            <input v-model="listingSelectedIds" class="supply-listing-checkbox" type="checkbox" :value="row.id" :disabled="!!busy || !canListMaterial(row)" :aria-label="`选择上架素材 ${row.sku || row.name}`"/>
            <div class="supply-material-body"><b>{{row.sku || row.name}}</b><small>{{row.template_name || templateLabel(row.template_id)}}</small><small v-if="!canListMaterial(row)">缺少模板、SKU 或图片，暂不能上架</small></div>
          </label>
        </div>
        <p v-if="!listingLoading && !listingCandidates.length && !listingError" class="empty">暂无符合条件的待上架素材。</p>
        <footer class="supply-pagination"><span>每页 {{listingPageSize}} 条</span><button :disabled="listingLoading || !!busy || listingPage===1" @click="listingPage--;loadListingCandidates()">上一页</button><span>{{listingPage}} / {{listingPages}}</span><button :disabled="listingLoading || !!busy || listingPage>=listingPages" @click="listingPage++;loadListingCandidates()">下一页</button></footer>
        </div>
        <div class="modal-actions"><span>本页已选 {{listingSelectedIds.length}} 条</span><button class="ghost" :disabled="!!busy" @click="closeListingPicker">取消</button><button class="primary" :disabled="!!busy || listingLoading || !listingSelectedIds.length" @click="listSelectedMaterials">{{busy==='list-selected'?'上架中…':'确认上架'}}</button></div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="listingHoverPreview && showListingPicker && canManage" class="supply-listing-hover-preview" :style="{left:`${listingHoverPreview.left}px`,top:`${listingHoverPreview.top}px`,width:`${listingHoverPreview.width}px`,height:`${listingHoverPreview.height}px`}">
        <img :src="imageUrl(listingHoverPreview.row.url)" :alt="listingHoverPreview.row.name || listingHoverPreview.row.sku" @load="resizeListingHoverPreview"/>
      </div>
    </Teleport>

    <div v-if="showAiConfig && canAdmin" class="modal-backdrop" @click.self="!busy && closeAiConfig()">
      <section v-dialog-focus="{close:closeAiConfig,busy:!!busy}" class="modal-card supply-ai-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-ai-title">
        <h2 id="supply-ai-title">{{aiConfig.configured?'更新':'配置'}}货盘 DeepSeek API Key</h2>
        <p>API Key 会加密保存，仅用于本公司的货盘商品标题生成。模型固定为 deepseek-flash。</p>
        <form @submit.prevent="saveAi()">
          <label>API Key<input v-model="aiConfig.api_key" type="password" maxlength="2048" autocomplete="new-password" :placeholder="aiConfig.configured?'输入新 API Key 以替换当前配置':'请输入 DeepSeek API Key'" required /></label>
          <p v-if="dialogError" class="error modal-error" role="alert">{{dialogError}}</p>
          <div class="modal-actions"><button type="button" class="ghost" :disabled="!!busy" @click="closeAiConfig">取消</button><button class="primary" :disabled="!!busy || !aiConfig.api_key.trim()">{{busy==='ai-config'?'保存中…':'安全保存'}}</button></div>
        </form>
      </section>
    </div>

    <div v-if="showStrategy" class="modal-backdrop" @click.self="!busy && (showStrategy=false)"><section v-dialog-focus="{close:()=>{showStrategy=false},busy:!!busy}" class="modal-card supply-dialog supply-strategy-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-strategy-title"><button class="modal-close" :disabled="!!busy" aria-label="关闭策略" @click="showStrategy=false">×</button><h2 id="supply-strategy-title">{{strategyEditing?'编辑':'新增'}}生成策略</h2><form @submit.prevent="saveStrategy"><div class="supply-form-grid"><label>策略名称<input v-model="strategyForm.name" required maxlength="100"/></label><label>公开产品模板<select v-model="strategyForm.template_id" required><option :value="null" disabled>请选择模板</option><option v-for="row in publicTemplates" :key="row.id" :value="row.id">{{row.name}}</option></select></label><label>类目库 / 店铺类型<select v-model="strategyForm.category_catalog_id" required @change="loadStrategyOptions()"><option :value="null" disabled>请选择类目库</option><option v-for="row in catalogs" :key="row.id" :value="row.id">{{row.name}}（{{catalogLabel(row.template_type)}}）</option></select></label><div class="supply-field"><span>商品类目</span><SearchableSelect v-model="strategyForm.category_name" :options="strategyOptions?.categories || []" value-key="name" label-key="name" :disabled="optionsLoading" placeholder="请选择商品类目" @change="strategyForm.attributes={}"/></div><label>售价<input v-model="strategyForm.price" type="number" step="0.01" min="0.01" max="999999" required/></label><label>库存<input v-model.number="strategyForm.stock" type="number" min="0" max="999999" step="1" required/></label><label v-if="strategyOptions?.capabilities?.supports_cod !== false">货到付款（COD）<select v-model="strategyForm.cod"><option value="Y">Y</option><option value="N">N</option></select></label><label>每个链接素材 SKU 数<input v-model.number="strategyForm.sku_count" type="number" min="5" max="9" step="1" required/></label><label>链接数量<input v-model.number="strategyForm.link_count" type="number" min="10" max="50" step="1" required/></label></div><p class="supply-help">预计 {{expectedRows.toLocaleString()}} 个数据行 / 最多 4,994 行。每个素材按 {{selectedTemplate?.sizes?.length || 1}} 个尺码展开。</p><p v-if="optionsLoading" class="supply-help">正在加载类目与属性…</p><section v-if="categoryAttributes.length" class="supply-attributes"><h3>类目属性</h3><div class="supply-form-grid"><label v-for="field in categoryAttributes" :key="field.field"><span>{{field.label || field.field}}<b v-if="field.required" class="required"> *</b></span><input v-model="strategyForm.attributes[field.field]" type="text" maxlength="500" :required="field.required" :placeholder="field.options?.length?'填写模板支持值':'按商品实际信息填写'"/><small v-if="field.options?.length">支持值：{{field.options.join('、')}}</small><small v-if="field.input_mode==='multiple'">多个值用逗号分隔。</small></label></div></section><label>附加标题要求（可选）<textarea v-model="strategyForm.title_requirements" maxlength="1000" rows="3" placeholder="例如：突出长袖与日常穿搭；只填写真实商品特点"></textarea></label><p v-if="strategyError || dialogError" class="error" role="alert">{{strategyError || dialogError}}</p><div class="modal-actions"><button type="button" class="ghost" :disabled="!!busy" @click="showStrategy=false">取消</button><button class="primary" :disabled="!!busy || optionsLoading || !strategyOptions">{{busy==='strategy'?'保存中…':'保存策略'}}</button></div></form></section></div>
    <div v-if="templateEditing" class="modal-backdrop" @click.self="!busy && (templateEditing=null)"><section v-dialog-focus="{close:()=>{templateEditing=null},busy:!!busy}" class="modal-card supply-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-fallback-title"><button class="modal-close" :disabled="!!busy" aria-label="关闭" @click="templateEditing=null">×</button><h2 id="supply-fallback-title">{{templateEditing.name}} · 兜底基础标题</h2><p>填写适用于该模板所有候选素材的真实英文商品标题，25–220 个字符。生成时自动附加唯一编号。</p><form @submit.prevent="saveFallback"><label>基础标题<textarea v-model="fallbackTitle" rows="4" minlength="25" maxlength="220" required placeholder="Printed Long Sleeve Nursing Maxi Dress"></textarea></label><p v-if="dialogError" class="error" role="alert">{{dialogError}}</p><div class="modal-actions"><button class="primary" :disabled="!!busy">保存</button></div></form></section></div>
    <div v-if="showAgent" class="modal-backdrop" @click.self="!busy && (showAgent=false)"><section v-dialog-focus="{close:()=>{showAgent=false},busy:!!busy}" class="modal-card supply-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-agent-title"><button class="modal-close" :disabled="!!busy" aria-label="关闭" @click="showAgent=false">×</button><h2 id="supply-agent-title">{{agentForm.id?'编辑':'新增'}}代理</h2><form @submit.prevent="saveAgent"><label>代理名称<input v-model="agentForm.name" maxlength="100" required/></label><p v-if="dialogError" class="error" role="alert">{{dialogError}}</p><div class="modal-actions"><button class="primary" :disabled="!!busy">保存代理</button></div></form></section></div>
    <div v-if="showUser" class="modal-backdrop" @click.self="!busy && (showUser=false)"><section v-dialog-focus="{close:()=>{showUser=false},busy:!!busy}" class="modal-card supply-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-user-title"><button class="modal-close" :disabled="!!busy" aria-label="关闭" @click="showUser=false">×</button><h2 id="supply-user-title">{{userEditing?'编辑':'创建'}}货盘用户</h2><form @submit.prevent="saveUser"><label>姓名<input v-model="userForm.name" maxlength="80" required/></label><label>邮箱<input v-model="userForm.email" type="email" maxlength="255" autocomplete="off" required/></label><label>{{userEditing?'重设密码（留空保留）':'密码'}}<input v-model="userForm.password" type="password" minlength="8" maxlength="72" :required="!userEditing" autocomplete="new-password"/></label><label>所属代理<select v-model="userForm.agent_id" required><option :value="null" disabled>请选择代理</option><option v-for="row in agents" :key="row.id" :value="row.id">{{row.name}}</option></select></label><label v-if="!userEditing">使用有效期（月）<input v-model.number="userForm.months" type="number" min="1" max="1200" step="1" required/></label><p class="supply-help">{{userEditing?'修改代理不影响历史任务统计；续期、停用和恢复请使用列表中的操作。':'有效期从创建时间起按自然月计算，默认 12 个月。'}}</p><p v-if="dialogError" class="error" role="alert">{{dialogError}}</p><div class="modal-actions"><button class="primary" :disabled="!!busy">{{busy==='user'?'保存中…':'保存账号'}}</button></div></form></section></div>
    <div v-if="renewUser" class="modal-backdrop" @click.self="!busy && (renewUser=null)"><section v-dialog-focus="{close:()=>{renewUser=null},busy:!!busy}" class="modal-card supply-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-renew-title"><button class="modal-close" :disabled="!!busy" aria-label="关闭" @click="renewUser=null">×</button><h2 id="supply-renew-title">{{renewUser.name}} · 续期</h2><p>当前到期：{{supplyTime(renewUser.supply_expires_at)}}。未到期从现有期限延长；已到期从现在延长。</p><form @submit.prevent="renew"><label>续期月数<input v-model.number="renewMonths" type="number" min="1" max="1200" step="1" required/></label><p v-if="dialogError" class="error" role="alert">{{dialogError}}</p><div class="modal-actions"><button class="primary" :disabled="!!busy">确认续期</button></div></form></section></div>
    <div v-if="usageMaterial" class="modal-backdrop" @click.self="closeUsage"><section v-dialog-focus="{close:closeUsage,busy:false}" class="modal-card supply-dialog supply-wide-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-usage-title">
      <button class="modal-close" aria-label="关闭使用记录" @click="closeUsage">×</button>
      <h2 id="supply-usage-title">{{usageMaterial.sku || `素材 #${usageMaterial.id}`}} · 使用记录</h2>
      <p>按任务汇总，每页 20 个任务。仅记录成功任务最终使用的素材；被替换及失败任务不计入。</p>
      <p v-if="usageLoading" class="empty" role="status">正在加载…</p>
      <p v-if="usageError" class="error" role="alert">{{usageError}} <button class="secondary" :disabled="usageLoading" @click="loadUsage(usageRetryPage)">重试</button></p>
      <div v-if="usage.length" class="supply-table-wrap" :aria-busy="usageLoading"><table aria-label="素材使用任务记录">
        <thead><tr><th>用户</th><th>代理</th><th>任务</th><th>链接使用次数</th><th>完成时间</th></tr></thead>
        <tbody><tr v-for="row in usage" :key="row.job_id"><td>{{row.user_name || '—'}}</td><td>{{row.agent_name || '内部使用'}}</td><td>#{{row.job_id}}</td><td>{{row.link_count}}</td><td>{{supplyTime(row.completed_at)}}</td></tr></tbody>
      </table></div>
      <p v-if="!usageLoading && !usageError && !usage.length" class="empty">{{usageTotal?'本页暂无记录。':'暂无成功使用记录。'}}</p>
      <footer class="supply-pagination" role="navigation" aria-label="使用记录分页">
        <span>共 {{usageTotal}} 个任务 · 第 {{usagePage}} / {{usagePages}} 页</span>
        <button class="secondary" :disabled="usageLoading || usagePage<=1" @click="loadUsage(usagePage-1)">上一页</button>
        <button class="secondary" :disabled="usageLoading || usagePage>=usagePages" @click="loadUsage(usagePage+1)">下一页</button>
      </footer>
    </section></div>
    <div v-if="jobDetail" class="modal-backdrop" @click.self="jobDetail=null"><section v-dialog-focus="{close:()=>{jobDetail=null},busy:false}" class="modal-card supply-dialog supply-wide-dialog" role="dialog" aria-modal="true" aria-labelledby="supply-job-title"><button class="modal-close" aria-label="关闭" @click="jobDetail=null">×</button><h2 id="supply-job-title">生成任务 #{{jobDetail.id}}</h2><p>{{supplyJobLabels[jobDetail.state] || jobDetail.state}} · {{supplyStageLabels[jobDetail.stage] || jobDetail.stage}} · {{progressLabel(jobDetail)}}</p><p v-if="jobDetail.error" class="error">{{jobDetail.error}}</p><div class="supply-detail-grid"><span>提交时间：{{supplyTime(jobDetail.created_at)}}</span><span>完成时间：{{supplyTime(jobDetail.completed_at)}}</span><span>用户：{{jobDetail.user_name || user.name}}</span><span>代理：{{jobDetail.agent_name || '内部使用'}}</span></div><p v-if="jobDetail.strategy || jobDetail.snapshot?.strategy" class="supply-help">快照：{{(jobDetail.strategy || jobDetail.snapshot.strategy).sku_count}} SKU × {{(jobDetail.strategy || jobDetail.snapshot.strategy).link_count}} 链接 · 售价 {{(jobDetail.strategy || jobDetail.snapshot.strategy).price}}</p><article v-for="(row,index) in jobDetail.links || jobDetail.drafts || []" :key="row.index || index" class="supply-link-preview"><b>链接 {{index+1}}</b><p>{{row.title}}</p><div class="supply-link-images"><img v-for="(asset,assetIndex) in row.materials || row.assets || []" :key="asset.id || assetIndex" :src="imageUrl(asset.url || asset.image_url)" :alt="asset.sku || '素材'" loading="lazy"/></div></article><div class="modal-actions"><button v-if="canDownload(jobDetail)" class="primary" :disabled="!!busy" @click="downloadJob(jobDetail)">下载 Excel</button><span v-else>{{supplyFileStatus(jobDetail)}}</span></div></section></div>
    <div v-if="preview" class="modal-backdrop" @click.self="preview=null"><section v-dialog-focus="{close:()=>{preview=null},busy:false}" class="modal-card supply-dialog supply-image-dialog" role="dialog" aria-modal="true" aria-label="素材图片预览"><button class="modal-close" aria-label="关闭预览" @click="preview=null">×</button><img :src="imageUrl(preview.url)" :alt="preview.name || preview.sku"/><p>{{preview.sku || preview.name}}</p></section></div>
  </section>
</template>

<style scoped>
.supply-tag.listed{background:#eaf9ef;color:#167144}
.supply-table-wrap.supply-material-list{margin:0;border-color:#ebe9f3;border-radius:15px}
.supply-material-list table{min-width:560px;table-layout:auto}
.supply-material-list.manageable table{min-width:900px}
.supply-table-wrap.supply-material-list th{background:#faf9fc;color:#858092;font-size:12px}
.supply-table-wrap.supply-material-list th,.supply-table-wrap.supply-material-list td{padding:14px 19px;vertical-align:middle}
.supply-material-list tr.selected{background:#faf9ff}
.supply-material-list .supply-material-selection{min-width:60px;width:60px}
.supply-material-list code{display:block;max-width:260px;overflow-wrap:anywhere}
.supply-material-list .material-list-thumbnail img{width:50px;height:64px;object-fit:cover}
.supply-template-toolbar{display:flex;align-items:end;flex-wrap:wrap;gap:12px;margin-bottom:20px}
.supply-template-toolbar .supply-template-search{width:280px;max-width:100%;height:42px}
.supply-template-toolbar label{width:180px;max-width:100%}
.supply-template-toolbar select{margin:0}
.supply-template-layout{grid-template-columns:190px minmax(0,1fr)}
.supply-template-results{min-width:0}
.supply-template-layout .groups button{overflow-wrap:anywhere}
@media(max-width:800px){.supply-template-layout{grid-template-columns:minmax(0,1fr)}}
.supply-ai-dialog{max-width:calc(100vw - 32px)}
.supply-ai-dialog label{display:block;color:inherit}
.supply-ai-dialog input{padding:12px;border-color:#e2dff0;border-radius:10px}
.supply-catalog{min-width:0}.supply-intro,.supply-section-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.supply-intro h2,.supply-section-heading h3{margin:0}.supply-intro p,.supply-section-heading p{color:#64748b;margin:6px 0}.supply-account{font-size:13px;color:#64748b}.supply-tabs{overflow-x:auto}.supply-tabs button{flex-shrink:0;white-space:nowrap}.supply-message,.supply-notice{padding:12px 16px;border-radius:8px;margin:12px 0}.supply-message{background:#fff1f2}.supply-notice{background:#effaf3;color:#166534}.supply-filters{display:flex;flex-wrap:wrap;align-items:end;gap:12px;background:#fff;border:1px solid #e2e8f0;padding:16px;border-radius:12px;margin-bottom:18px}.supply-filters label{min-width:140px;flex:1;margin:0}.supply-catalog label,.supply-field{display:flex;flex-direction:column;gap:8px;color:#475569;font-size:13px}.supply-catalog input,.supply-catalog select,.supply-catalog textarea{border:1px solid #d8dfeb;border-radius:7px;background:white;padding:9px 11px;width:100%;font:inherit;color:#0f172a;box-sizing:border-box}.supply-catalog input[type=checkbox]{width:auto;accent-color:#5368ef}.supply-catalog input:focus,.supply-catalog select:focus,.supply-catalog textarea:focus{outline:2px solid #a5b4fc;outline-offset:1px}.supply-catalog button:disabled{opacity:.5;cursor:not-allowed}.supply-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.supply-actions button{font-size:12px;padding:8px 11px;white-space:nowrap}.supply-check{flex-direction:row!important;align-items:center;white-space:nowrap}.supply-material-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px}.supply-material{position:relative;overflow:hidden;background:white;border:1px solid #e2e8f0;border-radius:12px}.supply-image{width:100%;height:220px;border:0!important;border-radius:0!important;background:#f4f6fa!important;padding:0!important}.supply-image img{width:100%;height:100%;object-fit:contain}.supply-select{position:absolute;left:10px;top:10px;background:white;border-radius:5px;padding:7px}.supply-material-body{padding:14px;display:flex;flex-direction:column;gap:9px}.supply-material-body b{font-size:14px;overflow-wrap:anywhere}.supply-material small,.supply-table-wrap small{font-size:12px;color:#64748b;display:block}.supply-health-reason{overflow-wrap:anywhere}.supply-tags{display:flex;gap:7px;flex-wrap:wrap}.supply-tag{display:inline-flex;padding:4px 8px;background:#f1f5f9;border-radius:6px;color:#64748b;white-space:nowrap;font-size:12px}.supply-tag.available,.supply-tag.completed{background:#eaf9ef;color:#167144}.supply-tag.invalid,.supply-tag.failed{background:#fff0f0;color:#b42318}.supply-tag.check_failed,.supply-tag.retry_wait{background:#fff6df;color:#9a6700}.supply-tag.running,.supply-tag.queued{background:#eef2ff;color:#465fe0}.supply-usage-button{padding:0!important;text-align:left!important;color:#5368ef!important;font-size:12px;border:0!important;background:transparent!important}.supply-pagination{display:flex;align-items:center;justify-content:flex-end;gap:12px;margin-top:20px;color:#64748b;font-size:13px}.supply-pagination label{flex-direction:row;align-items:center}.supply-pagination select{width:75px}.supply-template-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}.supply-card{border:1px solid #e2e8f0;border-radius:12px;padding:20px;background:#fff}.supply-card p{color:#64748b;font-size:13px;line-height:1.6}.supply-fallback{min-height:44px;overflow-wrap:anywhere}.supply-table-wrap{overflow-x:auto;border:1px solid #e2e8f0;border-radius:10px;background:white;margin:14px 0 24px}.supply-table-wrap table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}.supply-table-wrap th{background:#f8fafc;color:#64748b;font-weight:500;padding:12px 16px;white-space:nowrap}.supply-table-wrap td{padding:14px 16px;border-top:1px solid #eef1f5;vertical-align:top;min-width:85px}.supply-table-wrap small{margin-top:7px;max-width:250px;overflow-wrap:anywhere}.supply-help{color:#64748b;font-size:13px;line-height:1.7}.supply-email{overflow-wrap:anywhere}.supply-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:26px}.supply-metrics article{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:12px}.supply-metrics span{font-size:13px;color:#64748b}.supply-metrics b{font-size:28px}.supply-settings{max-width:620px;margin-bottom:24px}.supply-settings label{margin:16px 0}.supply-dialog{position:relative;width:min(560px,calc(100vw - 32px));max-height:90vh;overflow:auto;padding:28px}.supply-dialog p{color:#64748b;line-height:1.65;font-size:13px}.supply-dialog p.error{color:#b42318}.supply-dialog form>label{margin-top:16px}.supply-strategy-dialog,.supply-wide-dialog{width:min(900px,calc(100vw - 32px))}.supply-form-grid,.supply-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.supply-attributes{border-top:1px solid #e2e8f0;padding-top:8px;margin:20px 0}.supply-attributes small{line-height:1.6;color:#64748b;overflow-wrap:anywhere}.supply-image-dialog{text-align:center}.supply-image-dialog img{max-width:100%;max-height:70vh;object-fit:contain}.supply-detail-grid{font-size:13px;color:#64748b}.supply-link-preview{border-top:1px solid #e2e8f0;padding:16px 0}.supply-link-images{display:flex;gap:8px;overflow:auto}.supply-link-images img{width:100px;height:100px;object-fit:contain;background:#f8fafc}.required{color:#dc2626}@media(max-width:800px){.supply-intro,.supply-section-heading{flex-wrap:wrap}.supply-form-grid,.supply-detail-grid{grid-template-columns:1fr}.supply-metrics{grid-template-columns:repeat(2,1fr)}.supply-dialog{padding:24px 18px}.supply-pagination{flex-wrap:wrap;justify-content:center}.supply-material-grid{grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}}
.supply-job-controls{flex-wrap:nowrap}
.supply-job-controls select,.supply-job-controls button{height:36px;box-sizing:border-box;margin:0;font-size:13px}
.supply-job-controls select{width:auto;min-width:120px}
.supply-template-grid{grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr))}
.supply-card{min-width:0;display:flex;flex-direction:column}
.supply-template-cover{height:220px;display:flex;align-items:center;justify-content:center;background:#f4f6fa;border-radius:8px;overflow:hidden;margin-bottom:16px;color:#64748b;font-size:13px}
.supply-template-cover img{width:100%;height:100%;object-fit:contain}
.supply-card .supply-section-heading{flex-wrap:nowrap;align-items:flex-start;margin-bottom:0}
.supply-card h3{min-width:0;overflow-wrap:anywhere}
.supply-tag.published{background:#eaf9ef;color:#167144;flex-shrink:0}
.supply-template-description{white-space:pre-wrap;overflow-wrap:anywhere}
.supply-card .supply-actions{margin-top:auto}
.supply-listing-dialog{max-width:calc(100vw - 32px);display:flex;flex-direction:column;overflow:hidden}
.supply-listing-content{min-height:0;overflow:auto;padding:2px}
.supply-listing-dialog .supply-filters{border:0;border-radius:0;padding:0;background:transparent}
.supply-listing-dialog .supply-filters label{flex:0 1 200px;max-width:100%}
.supply-listing-dialog h2,.supply-listing-dialog .modal-actions{flex-shrink:0}
.supply-listing-option{cursor:pointer;gap:0!important;min-width:0}
.supply-listing-dialog .supply-listing-option,.supply-listing-dialog .supply-filters label{margin:0}
.supply-listing-option.selected{border-color:#5368ef;box-shadow:0 0 0 1px #5368ef}
.supply-listing-image{height:120px;background:#f4f6fa}
.supply-listing-image img{width:100%;height:100%;object-fit:contain}
.supply-listing-hover-preview{position:fixed;z-index:100;pointer-events:none;box-sizing:border-box;padding:4px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;box-shadow:0 12px 40px #1d164640}
.supply-listing-hover-preview img{display:block;width:100%;height:100%;object-fit:contain;border-radius:6px}
.supply-listing-checkbox{position:absolute;top:6px;left:6px}
.supply-listing-option .supply-material-body{padding:8px;gap:4px}
.supply-listing-option .supply-material-body b{font-size:12px}
.supply-listing-option .supply-material-body small{font-size:11px}
.supply-listing-dialog .modal-actions{flex-wrap:wrap}
.supply-listing-dialog .supply-material-grid{grid-template-columns:repeat(auto-fill,minmax(min(120px,100%),1fr));gap:10px}
</style>
