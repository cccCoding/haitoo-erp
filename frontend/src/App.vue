<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const token = ref(localStorage.getItem('haitoo_token') || '')
const page = ref('dashboard')
const email = ref('operator@haitoo-demo.com')
const password = ref('ChangeMe123!')
const user = ref<any>(null), company = ref<any>(null), shops = ref<any[]>([]), templates = ref<any[]>([]), templateGroups = ref<any[]>([]), tasks = ref<any[]>([]), materialAssets = ref<any[]>([]), drafts = ref<any[]>([]), points = ref<any>(null), members = ref<any[]>([]), aiProviders = ref<any[]>([])
const loading = ref(false), error = ref('')
const toast = ref('')
const templateQuery = ref(''), activeGroupId = ref<number | null>(null), selectedTemplateId = ref<number | null>(null)
const showGroupDialog = ref(false), showTemplateDialog = ref(false), templateFormTab = ref<'basic' | 'product' | 'sku' | 'logistics' | 'ai-prompts'>('basic'), newGroupName = ref(''), newTemplateName = ref(''), newTemplateDescription = ref(''), newTemplateTitleTemplate = ref(''), newTemplateProductDescription = ref(''), newTemplateSizeChart = ref<File | null>(null), newTemplateSizeChartPreview = ref(''), newTemplateGroupId = ref<number | null>(null), newTemplateImage = ref<File | null>(null), newTemplateImagePreview = ref(''), newPackageWeight = ref<number | null>(null), newPackageLength = ref<number | null>(null), newPackageWidth = ref<number | null>(null), newPackageHeight = ref<number | null>(null), newSkuSizeOptions = ref<string[]>([]), newTemplateAiPrompts = ref<{name:string; content:string}[]>([]), editingTemplate = ref<any>(null)
const showMemberDialog = ref(false), editingMember = ref<any>(null), memberForm = ref({ name: '', user_code: '', email: '', password: '', is_active: true }), memberSaving = ref(false)
const showMyAccountDialog = ref(false), myName = ref(''), myUserCode = ref(''), myAccountSaving = ref(false)
const managedShops = ref<any[]>([]), shopLoading = ref(false), shopError = ref('')
const materialUploading = ref(false), materialUploadError = ref('')
const selectedMaterialAssetIds = ref<number[]>([]), showMaterialDraftDialog = ref(false), materialDraftTemplateId = ref<number | null>(null), materialDraftTitle = ref(''), materialDraftProductDescription = ref(''), materialDraftSizeChart = ref<File | null>(null), materialDraftSizeChartPreview = ref(''), materialDraftTitleGenerating = ref(false), materialDraftSaving = ref(false)
const materialDraftSkuPreviewItems = ref<any[]>([])
const showDraftEditDialog = ref(false), editingDraft = ref<any>(null), draftEditTitle = ref(''), draftEditProductDescription = ref(''), draftEditSaving = ref(false), draftEditError = ref('')
const publishingDraftId = ref<number | null>(null)
const draftPageSize = ref(20), currentDraftPage = ref(1)
const taskPageSize = ref(20), currentTaskPage = ref(1)
const ledgerPageSize = ref(20), currentLedgerPage = ref(1)
const previewImageUrl = ref(''), previewImageAlt = ref('')
const showShopManagersDialog = ref(false), managingShop = ref<any>(null), selectedManagerIds = ref<number[]>([]), shopManagersSaving = ref(false)
const showTaskDetailDialog = ref(false), viewingTask = ref<any>(null)
const taskListRefreshing = ref(false), retryingTaskId = ref<number | null>(null)
const showTaskDraftDialog = ref(false), draftingTask = ref<any>(null), taskDraftTitle = ref(''), taskDraftProductDescription = ref(''), taskDraftSizeChart = ref<File | null>(null), taskDraftSizeChartPreview = ref(''), taskDraftTitleGenerating = ref(false), taskDraftSaving = ref(false), taskDraftSkuPreviewItems = ref<any[]>([])
type CreativeAsset = { id: string; file: File; preview: string }
const defaultSkuSizes = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL']
const defaultPackageLogistics = { weight: 0.28, length: 30, width: 16, height: 2 }
const creativeAssets = ref<CreativeAsset[]>([]), showCreativeAssetsDialog = ref(false), creativeAssetError = ref(''), creativeRequirement = ref(''), creativePromptIndex = ref(''), creativeProvider = ref(''), creativeRatio = ref<'1:1' | '3:4'>('1:1'), creativeQuality = ref<'1K' | '2K'>('1K')
const nav = [{key:'dashboard', icon:'◈', label:'工作台'}, {key:'templates', icon:'▦', label:'产品模板'}, {key:'pod', icon:'✦', label:'AI创作'}, {key:'tasks', icon:'◌', label:'任务中心'}, {key:'materials', icon:'◈', label:'素材库'}, {key:'drafts', icon:'▤', label:'商品草稿'}, {key:'points', icon:'◉', label:'积分中心'}, {key:'members', icon:'♙', label:'成员管理', adminOnly:true}, {key:'shops', icon:'▣', label:'店铺管理', adminOnly:true}]
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }))
const visibleNav = computed(() => nav.filter(item => !item.adminOnly || user.value?.role === 'company_admin'))
const pageTitle = computed(() => nav.find(x => x.key === page.value)?.label || '')
const filteredTemplates = computed(() => templates.value.filter(t => (!activeGroupId.value || t.group_id === activeGroupId.value) && t.name.toLowerCase().includes(templateQuery.value.trim().toLowerCase())))
const estimatedCreativePoints = computed(() => creativeQuality.value === '2K' ? 20 : 12)
const selectedTemplate = computed(() => templates.value.find(t => t.id === selectedTemplateId.value))
const selectedMaterialAssets = computed(() => materialAssets.value.filter(asset => selectedMaterialAssetIds.value.includes(asset.id)))
const materialDraftTemplate = computed(() => templates.value.find(template => template.id === materialDraftTemplateId.value))
const materialDraftSizes = computed(() => {
  const options = materialDraftTemplate.value?.sku_specifications?.size?.options || []
  return options.map((size: unknown) => String(size).trim()).filter(Boolean)
})
const materialDraftSkuCount = computed(() => selectedMaterialAssets.value.length)
const draftPageCount = computed(() => Math.max(1, Math.ceil(drafts.value.length / draftPageSize.value)))
const visibleDraftPage = computed(() => Math.min(currentDraftPage.value, draftPageCount.value))
const pagedDrafts = computed(() => {
  const start = (visibleDraftPage.value - 1) * draftPageSize.value
  return drafts.value.slice(start, start + draftPageSize.value)
})
function changeDraftPageSize() { currentDraftPage.value = 1 }
const taskPageCount = computed(() => Math.max(1, Math.ceil(tasks.value.length / taskPageSize.value)))
const visibleTaskPage = computed(() => Math.min(currentTaskPage.value, taskPageCount.value))
const pagedTasks = computed(() => {
  const start = (visibleTaskPage.value - 1) * taskPageSize.value
  return tasks.value.slice(start, start + taskPageSize.value)
})
function changeTaskPageSize() { currentTaskPage.value = 1 }
const ledgerEntries = computed(() => points.value?.ledger || [])
const ledgerPageCount = computed(() => Math.max(1, Math.ceil(ledgerEntries.value.length / ledgerPageSize.value)))
const visibleLedgerPage = computed(() => Math.min(currentLedgerPage.value, ledgerPageCount.value))
const pagedLedgerEntries = computed(() => {
  const start = (visibleLedgerPage.value - 1) * ledgerPageSize.value
  return ledgerEntries.value.slice(start, start + ledgerPageSize.value)
})
function changeLedgerPageSize() { currentLedgerPage.value = 1 }
// 后端统一返回 Unix 毫秒时间戳；所有日期时间固定按 UTC+8 展示。
const nativeToLocaleString = Date.prototype.toLocaleString
const nativeToLocaleDateString = Date.prototype.toLocaleDateString
Date.prototype.toLocaleString = function (...args: Parameters<typeof Date.prototype.toLocaleString>) {
  const [locales, options] = args
  return nativeToLocaleString.call(this, locales ?? 'zh-CN', { ...options, timeZone: 'Asia/Shanghai' })
}
Date.prototype.toLocaleDateString = function (...args: Parameters<typeof Date.prototype.toLocaleDateString>) {
  const [locales, options] = args
  return nativeToLocaleDateString.call(this, locales ?? 'zh-CN', { ...options, timeZone: 'Asia/Shanghai' })
}

async function refresh() {
  const h = { headers: headers.value }
  const [me, s, t, g, task, material, d, p, providers] = await Promise.all([api.get('/me',h), api.get('/shops',h), api.get('/templates',h), api.get('/template-groups',h), api.get('/tasks',h), api.get('/material-assets',h), api.get('/drafts',h), api.get('/points',h), api.get('/ai-providers',h)])
  user.value=me.data.user; company.value=me.data.company; shops.value=s.data; templates.value=t.data; templateGroups.value=g.data; tasks.value=task.data; materialAssets.value=material.data; drafts.value=d.data; points.value=p.data; aiProviders.value=providers.data
  if (!creativeProvider.value) creativeProvider.value = aiProviders.value.find(item => item.is_default)?.provider || aiProviders.value[0]?.provider || ''
  if (user.value.role === 'company_admin') {
    const [companyMembers, companyShops] = await Promise.all([api.get('/members', h), api.get('/shops/manage', h)])
    members.value = companyMembers.data
    managedShops.value = companyShops.data
  } else { members.value = []; managedShops.value = [] }
  if (!selectedTemplateId.value && templates.value[0]) selectedTemplateId.value=templates.value[0].id
  if (viewingTask.value) viewingTask.value = tasks.value.find(task => task.id === viewingTask.value.id) || null
}
async function login() { try { loading.value=true; error.value=''; const {data}=await api.post('/auth/login',{email:email.value,password:password.value}); token.value=data.access_token; localStorage.setItem('haitoo_token',token.value); await refresh() } catch { error.value='登录失败，请检查账号密码' } finally { loading.value=false } }
function onCreativeAssetChange(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  const available = 1000 - creativeAssets.value.length
  files.slice(0, available).forEach(file => creativeAssets.value.push({ id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`, file, preview: URL.createObjectURL(file) }))
  if (files.length) creativeAssetError.value = ''
  ;(event.target as HTMLInputElement).value = ''
}
function removeCreativeAsset(id: string) { const asset = creativeAssets.value.find(item => item.id === id); if (asset) URL.revokeObjectURL(asset.preview); creativeAssets.value = creativeAssets.value.filter(item => item.id !== id) }
function clearCreativeAssets() { creativeAssets.value.forEach(item => URL.revokeObjectURL(item.preview)); creativeAssets.value = []; showCreativeAssetsDialog.value = false }
async function uploadCreativeAssets() { return Promise.all(creativeAssets.value.map(async asset => { const form=new FormData(); form.append('file',asset.file); const {data}=await api.post('/uploads/creative-asset',form,{headers:headers.value}); return data.url })) }
async function createTask() { if (!creativeAssets.value.length) { creativeAssetError.value = '请先上传至少一张印花图，再开始印花贴合。'; return } if (!creativeRequirement.value.trim()) { showToast('请填写创作要求'); return } if (!selectedTemplateId.value || !creativeProvider.value) return; try { creativeAssetError.value = ''; const print_urls=await uploadCreativeAssets(); await api.post('/tasks',{template_id:selectedTemplateId.value,provider:creativeProvider.value,ratio:creativeRatio.value,quality:creativeQuality.value,print_url:print_urls[0],print_urls,creative_requirement:creativeRequirement.value.trim()},{headers:headers.value}); await refresh(); page.value='tasks' } catch (e:any) { error.value=e.response?.data?.detail || '创建 AI 任务失败' } }
async function createGroup() { if (!newGroupName.value.trim()) return; try { await api.post('/template-groups',{name:newGroupName.value.trim()},{headers:headers.value}); newGroupName.value=''; showGroupDialog.value=false; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || '创建分类失败' } }
function openTemplateDialog(template?: any) { editingTemplate.value=template || null; templateFormTab.value='basic'; newTemplateName.value=template?.name || ''; newTemplateDescription.value=template?.description || ''; newTemplateTitleTemplate.value=template?.title_template || ''; newTemplateProductDescription.value=template?.product_description || ''; newTemplateSizeChart.value=null; newTemplateSizeChartPreview.value=imageUrl(template?.size_chart_url); newTemplateGroupId.value=template?.group_id || null; newTemplateImage.value=null; newTemplateImagePreview.value=imageUrl(template?.cover_url); newPackageWeight.value=template?.package_weight ?? defaultPackageLogistics.weight; newPackageLength.value=template?.package_length ?? defaultPackageLogistics.length; newPackageWidth.value=template?.package_width ?? defaultPackageLogistics.width; newPackageHeight.value=template?.package_height ?? defaultPackageLogistics.height; newSkuSizeOptions.value=template?.sku_specifications?.size?.options || [...defaultSkuSizes]; newTemplateAiPrompts.value=(template?.ai_prompts || []).map((item:any) => ({name:item?.name || '', content:item?.content || ''})); showTemplateDialog.value=true }
function addSkuSize() { newSkuSizeOptions.value.push('') }
function addTemplateAiPrompt() { newTemplateAiPrompts.value.push({ name: '', content: '' }) }
function removeTemplateAiPrompt(index: number) { newTemplateAiPrompts.value.splice(index, 1) }
function selectedTemplateAiPrompts() { return (selectedTemplate.value?.ai_prompts || []).filter((item:any) => item?.name && item?.content) }
function applyTemplateAiPrompt() { if (creativePromptIndex.value === '') return; const prompt=selectedTemplateAiPrompts()[Number(creativePromptIndex.value)]; if (prompt) creativeRequirement.value=prompt.content }
function onCreativeTemplateChange() { creativePromptIndex.value=''; creativeRequirement.value='' }
function onCoverChange(event: Event) { const file=(event.target as HTMLInputElement).files?.[0] || null; newTemplateImage.value=file; newTemplateImagePreview.value=file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.cover_url) }
function onSizeChartChange(event: Event) { const file=(event.target as HTMLInputElement).files?.[0] || null; newTemplateSizeChart.value=file; newTemplateSizeChartPreview.value=file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.size_chart_url) }
async function uploadCover() { if (!newTemplateImage.value) return undefined; const form=new FormData(); form.append('file',newTemplateImage.value); const {data}=await api.post('/uploads/template-cover',form,{headers:headers.value}); return data.url }
async function uploadSizeChart() { if (!newTemplateSizeChart.value) return undefined; const form=new FormData(); form.append('file',newTemplateSizeChart.value); const {data}=await api.post('/uploads/template-cover',form,{headers:headers.value}); return data.url }
function validateNewTemplate() {
  const sizeOptions = newSkuSizeOptions.value.map(value => value.trim()).filter(Boolean)
  const validations = [
    { valid: Boolean(newTemplateName.value.trim() && newTemplateImage.value && newTemplateDescription.value.trim() && newTemplateGroupId.value !== null), tab: 'basic' as const, message: '请完整填写模版信息，并上传模板图片和选择模板分类' },
    { valid: Boolean(newTemplateTitleTemplate.value.trim() && newTemplateProductDescription.value.trim() && newTemplateSizeChart.value), tab: 'product' as const, message: '请完整填写商品信息，并上传尺码图' },
    { valid: sizeOptions.length > 0 && newSkuSizeOptions.value.every(value => value.trim()), tab: 'sku' as const, message: '请完整填写 SKU 尺码' },
    { valid: [newPackageWeight.value, newPackageLength.value, newPackageWidth.value, newPackageHeight.value].every(value => value !== null && value > 0), tab: 'logistics' as const, message: '请完整填写物流信息' },
  ]
  const missing = validations.find(item => !item.valid)
  if (!missing) return true
  templateFormTab.value = missing.tab
  showToast(missing.message)
  return false
}
async function createTemplate() { if (!editingTemplate.value && !validateNewTemplate()) return; if (editingTemplate.value && !newTemplateName.value.trim()) { templateFormTab.value='basic'; showToast('请输入模板名称'); return } if (editingTemplate.value && [newPackageWeight.value,newPackageLength.value,newPackageWidth.value,newPackageHeight.value].some(value => value === null || value <= 0)) { templateFormTab.value='logistics'; showToast('请完整填写物流信息'); return } const ai_prompts=newTemplateAiPrompts.value.map(item=>({name:item.name.trim(),content:item.content.trim()})).filter(item=>item.name || item.content); if (ai_prompts.some(item=>!item.name || !item.content)) { templateFormTab.value='ai-prompts'; showToast('请完整填写 AI 提示词的名称和内容，或删除空白项'); return } try { const cover_url=(await uploadCover()) ?? editingTemplate.value?.cover_url ?? null; const size_chart_url=(await uploadSizeChart()) ?? editingTemplate.value?.size_chart_url ?? null; const sizeOptions=newSkuSizeOptions.value.map(value=>value.trim()).filter(Boolean); const sku_specifications={size:{name:'尺码',options:sizeOptions}}; const payload={name:newTemplateName.value.trim(),description:newTemplateDescription.value.trim() || null,title_template:newTemplateTitleTemplate.value.trim() || null,product_description:newTemplateProductDescription.value.trim() || null,size_chart_url,group_id:newTemplateGroupId.value,cover_url,package_weight:newPackageWeight.value,package_length:newPackageLength.value,package_width:newPackageWidth.value,package_height:newPackageHeight.value,sku_specifications,ai_prompts,color_count:1,sku_count:Math.max(1,sizeOptions.length)}; if(editingTemplate.value) await api.put(`/templates/${editingTemplate.value.id}`,payload,{headers:headers.value}); else await api.post('/templates',payload,{headers:headers.value}); showTemplateDialog.value=false; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || '保存模板失败' } }
async function deleteTemplate(template:any) { if (!confirm(`确定删除模板「${template.name}」吗？`)) return; try { await api.delete(`/templates/${template.id}`,{headers:headers.value}); if(selectedTemplateId.value===template.id) selectedTemplateId.value=templates.value.find(t=>t.id!==template.id)?.id || null; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || '删除模板失败' } }
function imageUrl(url?: string) { return url ? (url.startsWith('/') ? `${api.defaults.baseURL}${url}` : url) : '' }
const taskStatusLabel: Record<string, string> = { queued: '排队中', running: '处理中', awaiting_selection: '待选图', completed: '已完成', failed: '失败' }
function taskStatusClass(status?: string) { return status === 'awaiting_selection' ? 'purple' : status === 'completed' ? 'blue' : status === 'failed' ? 'orange' : 'purple' }
async function refreshTaskList() {
  try {
    taskListRefreshing.value = true
    tasks.value = (await api.get('/tasks', { headers: headers.value })).data
    if (viewingTask.value) viewingTask.value = tasks.value.find(task => task.id === viewingTask.value.id) || null
  } catch (e: any) { showToast(e.response?.data?.detail || '刷新任务列表失败') }
  finally { taskListRefreshing.value = false }
}
async function copyProviderTaskId(task: any) { if (!task.provider_task_id) return; try { await navigator.clipboard.writeText(task.provider_task_id); showToast('外部任务 ID 已复制') } catch { showToast('复制失败，请手动复制') } }
function openTaskDetail(task: any) { viewingTask.value = task; showTaskDetailDialog.value = true }
function templateCoverUrl(template?: any) { if (template?.cover_url) return imageUrl(template.cover_url); return template?.name === '白色 T恤正面' ? '/template-white-tshirt-front.png' : '/template-tshirt.svg' }
function hasTemplateCover(template?: any) { return Boolean(template?.cover_url || template?.name === '白色 T恤正面') }
function useTemplate(template:any) { selectedTemplateId.value=template.id; page.value='pod' }
function toggleMaterialAsset(assetId: number) { selectedMaterialAssetIds.value = selectedMaterialAssetIds.value.includes(assetId) ? selectedMaterialAssetIds.value.filter(id => id !== assetId) : [...selectedMaterialAssetIds.value, assetId] }
function randomSkuSuffix() { const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'; return Array.from(crypto.getRandomValues(new Uint8Array(6)), value => alphabet[value % alphabet.length]).join('') }
function refreshMaterialDraftSkuPreview() {
  materialDraftSkuPreviewItems.value = materialDraftTemplate.value
    ? selectedMaterialAssets.value.map(asset => ({ image_url: asset.url, size: null, sku: `M05L${user.value?.user_code?.toUpperCase() || '??'}${randomSkuSuffix()}` }))
    : []
}
function onMaterialDraftTemplateChange() {
  refreshMaterialDraftSkuPreview()
  const template = materialDraftTemplate.value
  materialDraftTitle.value = template ? `${template.name} POD 商品` : ''
  materialDraftProductDescription.value = template?.product_description || ''
  materialDraftSizeChart.value = null
  materialDraftSizeChartPreview.value = imageUrl(template?.size_chart_url)
}
function onMaterialDraftSizeChartChange(event: Event) { const file=(event.target as HTMLInputElement).files?.[0] || null; materialDraftSizeChart.value=file; materialDraftSizeChartPreview.value=file ? URL.createObjectURL(file) : imageUrl(materialDraftTemplate.value?.size_chart_url) }
async function uploadMaterialDraftSizeChart() { if (!materialDraftSizeChart.value) return undefined; const form=new FormData(); form.append('file',materialDraftSizeChart.value); const {data}=await api.post('/uploads/draft-size-chart',form,{headers:headers.value}); return data.url }
async function generateMaterialDraftTitle() {
  if (!materialDraftTemplateId.value || !selectedMaterialAssets.value[0]) return
  try {
    materialDraftTitleGenerating.value = true
    const { data } = await api.post(`/templates/${materialDraftTemplateId.value}/generate-draft-title`, { image_url: selectedMaterialAssets.value[0].url }, { headers: headers.value })
    materialDraftTitle.value = data.title
  } catch (e:any) {
    showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试')
  } finally {
    materialDraftTitleGenerating.value = false
  }
}
function openMaterialDraftDialog() { materialDraftTemplateId.value = null; materialDraftTitle.value = ''; materialDraftProductDescription.value = ''; materialDraftSizeChart.value = null; materialDraftSizeChartPreview.value = ''; materialDraftSkuPreviewItems.value = []; showMaterialDraftDialog.value = true }
function openTaskDraftDialog(task: any) {
  const template = templates.value.find(item => item.id === task.template_id)
  if (!template || !task.selected_result_url) { showToast('任务缺少产品模板或已选结果图'); return }
  draftingTask.value = task
  taskDraftTitle.value = `${template.name} POD 商品`
  taskDraftProductDescription.value = template.product_description || ''
  taskDraftSizeChart.value = null
  taskDraftSizeChartPreview.value = imageUrl(template.size_chart_url)
  taskDraftSkuPreviewItems.value = [{ image_url: task.selected_result_url, size: null, sku: `M05L${user.value?.user_code?.toUpperCase() || '??'}${randomSkuSuffix()}` }]
  showTaskDraftDialog.value = true
}
function onTaskDraftSizeChartChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] || null
  taskDraftSizeChart.value = file
  const template = templates.value.find(item => item.id === draftingTask.value?.template_id)
  taskDraftSizeChartPreview.value = file ? URL.createObjectURL(file) : imageUrl(template?.size_chart_url)
}
async function uploadTaskDraftSizeChart() {
  if (!taskDraftSizeChart.value) return undefined
  const form = new FormData(); form.append('file', taskDraftSizeChart.value)
  const { data } = await api.post('/uploads/draft-size-chart', form, { headers: headers.value })
  return data.url
}
async function generateTaskDraftTitle() {
  if (!draftingTask.value?.template_id || !draftingTask.value?.selected_result_url) return
  try {
    taskDraftTitleGenerating.value = true
    const { data } = await api.post(`/templates/${draftingTask.value.template_id}/generate-draft-title`, { image_url: draftingTask.value.selected_result_url }, { headers: headers.value })
    taskDraftTitle.value = data.title
  } catch (e: any) { showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试') }
  finally { taskDraftTitleGenerating.value = false }
}
async function createTaskDraft() {
  if (!draftingTask.value || !taskDraftTitle.value.trim()) { showToast('请生成或填写商品标题'); return }
  try {
    taskDraftSaving.value = true
    const template = templates.value.find(item => item.id === draftingTask.value.template_id)
    const size_chart_url = (await uploadTaskDraftSizeChart()) ?? template?.size_chart_url ?? null
    await api.post(`/tasks/${draftingTask.value.id}/draft`, { title: taskDraftTitle.value.trim(), product_description: taskDraftProductDescription.value.trim() || null, size_chart_url, sku_items: taskDraftSkuPreviewItems.value }, { headers: headers.value })
    showTaskDraftDialog.value = false
    await refresh()
    page.value = 'drafts'
    showToast('商品草稿已创建')
  } catch (e: any) { showToast(e.response?.data?.detail || '创建商品草稿失败') }
  finally { taskDraftSaving.value = false }
}
async function createDraftFromMaterialAssets() {
  if (!selectedMaterialAssetIds.value.length) return
  if (!materialDraftTemplateId.value) { showToast('请选择产品模板'); return }
  if (!materialDraftTitle.value.trim()) { showToast('请生成或填写商品标题'); return }
  try {
    materialDraftSaving.value = true
    const size_chart_url = (await uploadMaterialDraftSizeChart()) ?? materialDraftTemplate.value?.size_chart_url ?? null
    const { data: draft } = await api.post('/drafts/from-material-assets', { material_asset_ids: selectedMaterialAssetIds.value, template_id: materialDraftTemplateId.value, title: materialDraftTitle.value.trim(), product_description: materialDraftProductDescription.value.trim() || null, size_chart_url, sku_items: materialDraftSkuPreviewItems.value }, { headers: headers.value })
    const { data: publishResult } = await api.post(`/drafts/${draft.id}/publish-to-miaoshou`, {}, { headers: headers.value })
    selectedMaterialAssetIds.value = []
    showMaterialDraftDialog.value = false
    await refresh()
    page.value = 'drafts'
    showToast(`已创建并上传至妙手公共采集箱（编号：${publishResult.common_collect_box_detail_id}）`)
  } catch (e:any) {
    showToast(e.response?.data?.detail || '创建或上传妙手失败；草稿已保留，可在商品待发布页重试')
  } finally {
    materialDraftSaving.value = false
  }
}
function openDraftEditDialog(draft: any) { editingDraft.value = draft; draftEditTitle.value = draft.title; draftEditProductDescription.value = draft.product_description || ''; draftEditError.value = ''; showDraftEditDialog.value = true }
function draftSkuForImage(draft: any, imageUrl: string) { return draft?.sku_items?.find((item: any) => item.image_url === imageUrl)?.sku || '—' }
function openImagePreview(url: string, alt: string) { previewImageUrl.value = imageUrl(url); previewImageAlt.value = alt }
async function saveDraftEdit() {
  if (!editingDraft.value || !draftEditTitle.value.trim()) { draftEditError.value = '请输入商品标题'; return }
  try {
    draftEditSaving.value = true
    draftEditError.value = ''
    await api.put(`/drafts/${editingDraft.value.id}`, { title: draftEditTitle.value.trim(), product_description: draftEditProductDescription.value.trim() || null }, { headers: headers.value })
    showDraftEditDialog.value = false
    await refresh()
  } catch (e:any) {
    draftEditError.value = e.response?.data?.detail || '保存商品草稿失败，请稍后重试'
  } finally {
    draftEditSaving.value = false
  }
}
async function publishDraftToMiaoshou(draft: any) {
  if (draft.miaoshou_collect_box_id) return
  try {
    publishingDraftId.value = draft.id
    const { data } = await api.post(`/drafts/${draft.id}/publish-to-miaoshou`, {}, { headers: headers.value })
    await refresh()
    showToast(data.already_published ? '该商品已发布到妙手公共采集箱' : `已发布到妙手公共采集箱（编号：${data.common_collect_box_detail_id}）`)
  } catch (e: any) {
    showToast(e.response?.data?.detail || '发布到妙手失败，请稍后重试')
  } finally {
    publishingDraftId.value = null
  }
}
async function selectTask(task:any) { await api.post(`/tasks/${task.id}/select`,{result_url:task.result_urls[0]},{headers:headers.value}); await refresh() }
async function retryTaskResult(task: any) {
  try {
    retryingTaskId.value = task.id
    await api.post(`/tasks/${task.id}/retry-result`, {}, { headers: headers.value })
    await refreshTaskList()
    showToast('已开始重新获取结果')
  } catch (e: any) { showToast(e.response?.data?.detail || '重新获取结果失败') }
  finally { retryingTaskId.value = null }
}
async function claimMaterials(task:any) { try { const {data}=await api.post(`/tasks/${task.id}/claim-materials`,{}, {headers:headers.value}); await refresh(); page.value='materials'; if (!data.claimed) error.value='该任务的图片已在素材库中' } catch(e:any) { error.value=e.response?.data?.detail || '领取素材失败' } }
async function uploadMaterialAssets(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  try {
    materialUploading.value = true
    materialUploadError.value = ''
    const form = new FormData()
    files.forEach(file => form.append('files', file))
    await api.post('/material-assets/upload', form, { headers: headers.value })
    await refresh()
  } catch (e:any) {
    materialUploadError.value = e.response?.data?.detail || '上传素材失败，请稍后重试'
  } finally {
    materialUploading.value = false
  }
}
async function deleteSelectedMaterialAssets() {
  const assetIds = [...selectedMaterialAssetIds.value]
  if (!assetIds.length || !confirm(`确定从素材库删除选中的 ${assetIds.length} 张图片吗？`)) return
  try {
    await Promise.all(assetIds.map(assetId => api.delete(`/material-assets/${assetId}`, { headers: headers.value })))
    materialAssets.value = materialAssets.value.filter(item => !assetIds.includes(item.id))
    selectedMaterialAssetIds.value = []
    showToast(`已删除 ${assetIds.length} 张素材`)
  } catch (e: any) {
    await refresh()
    showToast(e.response?.data?.detail || '删除素材失败，请稍后重试')
  }
}
function openMemberDialog(member?: any) { editingMember.value=member || null; memberForm.value={name:member?.name || '',user_code:member?.user_code || '',email:member?.email || '',password:'',is_active:member?.is_active ?? true}; showMemberDialog.value=true }
function openMyAccountDialog() { myName.value=user.value?.name || ''; myUserCode.value=user.value?.user_code || ''; showMyAccountDialog.value=true }
async function saveMyUserCode() { const name=myName.value.trim(), userCode=myUserCode.value.trim(); if (!name) { showToast('请输入管理员名称'); return } if (userCode && [...userCode].length !== 2) { showToast('用户代码必须恰好为两个字符'); return } try { myAccountSaving.value=true; const {data}=await api.patch('/me',{name,user_code:userCode || null},{headers:headers.value}); user.value=data; showMyAccountDialog.value=false; showToast('账户设置已保存') } catch(e:any) { showToast(e.response?.data?.detail || '保存账户设置失败') } finally { myAccountSaving.value=false } }
async function saveMember() { if (!memberForm.value.name.trim() || !memberForm.value.email.trim() || (!editingMember.value && memberForm.value.password.length < 8)) return; const userCode = memberForm.value.user_code.trim(); if (userCode && [...userCode].length !== 2) { showToast('用户代码必须恰好为两个字符'); return } try { memberSaving.value=true; error.value=''; const payload:any={name:memberForm.value.name.trim(),user_code:userCode || null,email:memberForm.value.email.trim()}; if(memberForm.value.password) payload.password=memberForm.value.password; if(editingMember.value) await api.put(`/members/${editingMember.value.id}`,payload,{headers:headers.value}); else await api.post('/members',payload,{headers:headers.value}); showMemberDialog.value=false; await refresh(); showToast('成员已保存') } catch(e:any) { const message=e.response?.data?.detail || '保存成员失败'; error.value=message; showToast(message) } finally { memberSaving.value=false } }
async function toggleMember(member:any) { try { await api.put(`/members/${member.id}`,{is_active:!member.is_active},{headers:headers.value}); await refresh() } catch(e:any) { error.value=e.response?.data?.detail || '更新成员状态失败' } }
async function loadMiaoshouShops() { try { shopLoading.value=true; shopError.value=''; await api.post('/miaoshou/shops',{}, {headers:headers.value}); await refresh() } catch(e:any) { shopError.value=e.response?.data?.detail || '获取妙手店铺失败' } finally { shopLoading.value=false } }
function openShopManagersDialog(shop:any) { managingShop.value=shop; selectedManagerIds.value=shop.manager_users.map((member:any)=>member.id); showShopManagersDialog.value=true }
async function saveShopManagers() { if (!managingShop.value) return; try { shopManagersSaving.value=true; await api.put(`/shops/${managingShop.value.id}/managers`, {member_ids:selectedManagerIds.value}, {headers:headers.value}); showShopManagersDialog.value=false; await refresh() } catch(e:any) { shopError.value=e.response?.data?.detail || '保存店铺管理人员失败' } finally { shopManagersSaving.value=false } }
let toastTimer: ReturnType<typeof setTimeout> | undefined
function showToast(message: string) { toast.value = message; if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = '' }, 3000) }
function logout(){ localStorage.removeItem('haitoo_token'); token.value=''; user.value=null }
api.interceptors.response.use(
  response => response,
  requestError => {
    if (requestError.response?.data?.detail === '登录已失效') {
      logout()
      showToast('登录已失效，请重新登录')
    }
    return Promise.reject(requestError)
  },
)
let taskResultPollingTimer: ReturnType<typeof setInterval> | undefined
async function refreshPendingTaskResults() {
  if (!token.value || !tasks.value.some(task => ['queued', 'running'].includes(task.status))) return
  try { tasks.value = (await api.get('/tasks', { headers: headers.value })).data } catch { /* 保留上一次任务状态，等待下次轮询。 */ }
}
onMounted(() => {
  if (token.value) refresh().catch(logout)
  taskResultPollingTimer = setInterval(refreshPendingTaskResults, 5000)
})
onUnmounted(() => taskResultPollingTimer && clearInterval(taskResultPollingTimer))
</script>

<template>
  <main v-if="!token" class="login-shell">
    <section class="login-card"><div class="brand-mark">H</div><p class="eyebrow">HAITOO AI POD 工作台</p><h1>欢迎回到 POD 工作台</h1><p>登录后仅可访问所属公司及已授权店铺。</p><label>邮箱<input v-model="email" type="email" /></label><label>密码<input v-model="password" type="password" /></label><button class="primary full" :disabled="loading" @click="login">{{ loading ? '登录中…' : '登录' }}</button><small>演示账号：operator@haitoo-demo.com / ChangeMe123!</small><p v-if="error" class="error">{{ error }}</p></section>
  </main>
  <main v-else class="app-shell">
    <aside><div class="logo"><span>H</span><b>HAITOO AI</b></div><nav><button v-for="item in visibleNav" :key="item.key" :class="{active: page===item.key}" @click="page=item.key"><i>{{item.icon}}</i>{{item.label}}</button></nav><div class="side-help">积分结算<br/><strong>预冻结 · 按实结算</strong></div></aside>
    <section class="content"><header><div><p class="eyebrow">{{ company?.name }}</p><h1>{{ pageTitle }}</h1></div><div class="context"><div class="points-pill"><span>积分余量</span><b>{{points?.available ?? 0}}</b><small>冻结 {{points?.frozen ?? 0}}</small><button @click="page='points'">明细</button></div><button class="member account-button" @click="openMyAccountDialog">{{user?.name}} · {{ user?.role === 'company_admin' ? '管理员' : '运营成员' }}{{user?.user_code ? ` · ${user.user_code}` : ''}}</button><button class="ghost" @click="logout">退出</button></div></header>
      <section v-if="page==='dashboard'" class="page"><div class="hero"><div><p>POD 商品工作台</p><h2>今天要先处理什么？</h2><span>从 AI创作到待发布商品，所有进度都在这里。</span></div><button class="primary" @click="page='pod'">✦ 开始 AI创作</button></div><div class="metrics"><article><span>待选图任务</span><b>{{tasks.filter(t=>t.status==='awaiting_selection').length}}</b><em>需要人工确认</em></article><article><span>待发布商品</span><b>{{drafts.length}}</b><em>妙手接口待接入</em></article><article><span>可用积分</span><b>{{points?.available ?? 0}}</b><em>冻结 {{points?.frozen ?? 0}} 积分</em></article></div><div class="two-col"><section class="panel"><h3>待选图任务 <button @click="page='tasks'">查看全部</button></h3><div v-for="task in tasks.slice(0,3)" :key="task.id" class="task-row"><span class="thumb">✦</span><div><strong>AI创作 #{{task.id}}</strong><small>{{task.parameters.quality}}</small></div><span class="chip blue">{{task.status==='awaiting_selection'?'待选图':'处理中'}}</span></div></section><section class="panel"><h3>快捷操作</h3><button class="quick" @click="page='templates'">▦ 浏览产品模板 <span>→</span></button><button class="quick" @click="page='points'">◉ 查看积分明细 <span>→</span></button></section></div></section>
      <section v-else-if="page==='templates'" class="page"><div class="toolbar"><input v-model="templateQuery" placeholder="搜索模板名称"/><div v-if="user?.role==='company_admin'" class="toolbar-actions"><button class="primary" @click="openTemplateDialog()">新增模板</button></div></div><div class="template-layout"><section class="groups"><div class="groups-heading"><h3>模板分类</h3><button v-if="user?.role==='company_admin'" class="add-group" @click="showGroupDialog=true">新增</button></div><button :class="{selected:activeGroupId===null}" @click="activeGroupId=null">全部模板</button><button v-for="group in templateGroups" :key="group.id" :class="{selected:activeGroupId===group.id}" @click="activeGroupId=group.id">{{group.name}}</button></section><section><div class="section-heading"><h2>{{activeGroupId ? templateGroups.find(g=>g.id===activeGroupId)?.name : '全部模板'}}</h2><span>共 {{filteredTemplates.length}} 个模板</span></div><div class="template-grid"><article v-for="t in filteredTemplates" :key="t.id" class="template-card"><div class="template-image" :class="{hasCover: hasTemplateCover(t)}"><img v-if="hasTemplateCover(t)" :src="templateCoverUrl(t)" :alt="t.name"/><span v-else>{{t.name.includes('T恤')?'♧':'♔'}}</span></div><h3>{{t.name}}</h3><p><span class="chip" :class="t.is_platform?'blue':'purple'">{{t.is_platform?'平台模板':'公司私有'}}</span></p><p v-if="t.description" class="template-description">{{t.description}}</p><small>{{t.color_count}} 个颜色 · {{t.sku_count}} 个 SKU</small><div class="template-actions"><button @click="useTemplate(t)">用于 AI创作 →</button><template v-if="!t.is_platform && user?.role==='company_admin'"><button @click="openTemplateDialog(t)">编辑</button><button class="danger" @click="deleteTemplate(t)">删除</button></template></div></article><p v-if="!filteredTemplates.length" class="empty">没有符合条件的模板。</p></div></section></div></section>
      <section v-else-if="page==='pod'" class="page"><div class="mode-tabs"><button>灵感参考</button><button class="active">印花贴合</button><button>创作变体</button></div><section class="pod-panel"><div class="pod-heading"><h2>印花贴合</h2><p>上传印花素材并选择产品模板，生成 AI 创作后的商品效果图。</p><label class="requirement-label">创作要求 <b>*</b><span v-if="selectedTemplateAiPrompts().length" class="prompt-picker"><select v-model="creativePromptIndex" @change="applyTemplateAiPrompt"><option value="">选择模版内置 AI 提示词</option><option v-for="(prompt,index) in selectedTemplateAiPrompts()" :key="`${prompt.name}-${index}`" :value="String(index)">{{prompt.name}}</option></select><small>选择后会填充至下方，仍可自行修改。</small></span><textarea v-model="creativeRequirement" maxlength="1000" placeholder="例如：保留花朵细节，色彩清晰自然，印花完整贴合布料"></textarea></label></div><div class="pod-grid"><article><label>创作素材</label><label class="upload floral" :class="{hasAsset:creativeAssets.length, invalid:creativeAssetError}"><input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="onCreativeAssetChange"/><img v-if="creativeAssets.length" :src="creativeAssets[0].preview" alt="印花素材预览"/><template v-else><b>✿</b><span>点击上传印花图</span><small>JPG、PNG、WebP，单张最大 5MB</small></template><button v-if="creativeAssets.length" type="button" class="asset-count" @click.prevent="showCreativeAssetsDialog=true">{{creativeAssets.length}}</button></label><p v-if="creativeAssetError" class="creative-asset-error" role="alert">{{creativeAssetError}}</p><button v-if="creativeAssets.length" class="manage-assets" @click="showCreativeAssetsDialog=true">管理 {{creativeAssets.length}} 张印花图</button></article><article><label>产品模板</label><select v-model="selectedTemplateId" @change="onCreativeTemplateChange"><option v-for="t in templates" :key="t.id" :value="t.id">{{t.name}}</option></select><div class="product-preview template-preview"><img :src="templateCoverUrl(selectedTemplate)" :alt="selectedTemplate?.name || '产品模板'"/><span>{{selectedTemplate?.name}}</span></div></article><article class="settings"><label class="settings-title">创作参数</label><div class="parameter-fields"><label class="parameter-field"><span>AI模型</span><select v-model="creativeProvider"><option v-for="provider in aiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}</option></select></label><label class="parameter-field"><span>画面比例</span><select v-model="creativeRatio"><option>1:1</option><option>3:4</option></select></label><label class="parameter-field"><span>清晰度</span><select v-model="creativeQuality"><option>1K</option><option>2K</option></select></label></div></article><aside class="estimate"><span>本次印花贴合</span><b>预估冻结 {{estimatedCreativePoints}} 积分</b><small>完成后按实际 AI 用量结算，多退少补。</small><button class="primary full" @click="createTask">✦ 开始印花贴合</button></aside></div></section></section>
      <section v-else-if="page==='tasks'" class="page"><div class="section-heading"><div><span>生成完成后可领取全部图片到素材库；选图后可直接创建商品草稿。</span></div><button class="secondary" :disabled="taskListRefreshing" @click="refreshTaskList">{{taskListRefreshing ? '刷新中…' : '↻ 刷新列表'}}</button></div><section class="draft-table task-table"><div class="thead" style="grid-template-columns:.55fr .75fr .95fr 1.2fr 1.1fr .75fr 1.55fr .7fr .6fr 1.3fr 1.9fr"><span>任务编号</span><span>任务类型</span><span>产品模版</span><span>AI模型</span><span>创建时间</span><span>创建人</span><span>外部任务 ID</span><span>状态</span><span>结果数量</span><span>失败原因</span><span>操作</span></div><div v-for="task in pagedTasks" :key="task.id" class="trow" style="grid-template-columns:.55fr .75fr .95fr 1.2fr 1.1fr .75fr 1.55fr .7fr .6fr 1.3fr 1.9fr"><strong>#{{task.id}}</strong><span>{{task.parameters?.task_type || '替换印花'}}</span><span>{{task.template_name || '—'}}</span><span class="ai-model-cell"><b>{{task.provider === 'grsai' ? 'Grsai' : task.provider || '默认模型'}}</b><small v-if="task.provider_model">{{task.provider_model}}</small></span><span>{{new Date(task.created_at).toLocaleString()}}</span><span>{{task.created_by_name || '历史记录缺失'}}</span><span class="provider-task-id"><code>{{task.provider_task_id || '—'}}</code><button v-if="task.provider_task_id" class="copy-icon-button" title="复制外部任务 ID" aria-label="复制外部任务 ID" @click="copyProviderTaskId(task)">⧉</button></span><span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span><span>{{task.result_urls?.length || 0}} 张</span><span :class="{error: task.failure_reason}">{{task.failure_reason || '—'}}</span><span class="task-actions"><button class="secondary" @click="openTaskDetail(task)">查看详情</button><button v-if="task.provider==='grsai' && task.status==='failed' && task.failure_reason==='grsai 任务查询超时，请稍后重试'" class="secondary" :disabled="retryingTaskId===task.id" @click="retryTaskResult(task)">{{retryingTaskId===task.id ? '获取中…' : '重新获取结果'}}</button><button v-if="task.status==='awaiting_selection'" class="primary" @click="selectTask(task)">确认选图</button><button v-if="['awaiting_selection','completed'].includes(task.status)" class="secondary" @click="claimMaterials(task)">领取素材</button><button v-if="task.status==='completed'" class="secondary" @click="openTaskDraftDialog(task)">创建草稿</button></span></div><p v-if="!tasks.length" class="empty">暂无 AI 创作任务。</p><footer v-if="tasks.length" class="draft-pagination"><span>共 {{tasks.length}} 条</span><label>每页 <select v-model.number="taskPageSize" @change="changeTaskPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option><option :value="500">500</option><option :value="1000">1000</option></select> 条</label><button :disabled="visibleTaskPage===1" @click="currentTaskPage=visibleTaskPage-1">上一页</button><span>第 {{visibleTaskPage}} / {{taskPageCount}} 页</span><button :disabled="visibleTaskPage===taskPageCount" @click="currentTaskPage=visibleTaskPage+1">下一页</button></footer></section></section>
      <section v-else-if="page==='materials'" class="page"><div class="section-heading"><div><span>选择一张或多张素材，指定产品模板后即可创建商品草稿。</span></div><label class="primary material-upload-button" :class="{disabled: materialUploading}"><input type="file" multiple accept="image/png,image/jpeg,image/webp" :disabled="materialUploading" @change="uploadMaterialAssets"/>{{materialUploading ? '上传中…' : '上传本地素材'}}</label></div><p v-if="materialUploadError" class="error material-upload-error">{{materialUploadError}}</p><section v-if="selectedMaterialAssetIds.length" class="material-draft-bar"><strong>已选 {{selectedMaterialAssetIds.length}} 张素材</strong><button class="primary" @click="openMaterialDraftDialog">创建商品草稿</button><button class="negative" @click="deleteSelectedMaterialAssets">删除选中素材</button><button class="ghost" @click="selectedMaterialAssetIds=[]">取消选择</button></section><div class="material-grid"><button v-for="asset in materialAssets" :key="asset.id" class="material-card" :class="{selected: selectedMaterialAssetIds.includes(asset.id)}" @click="toggleMaterialAsset(asset.id)"><span class="material-select-mark">{{selectedMaterialAssetIds.includes(asset.id) ? '✓' : ''}}</span><img :src="imageUrl(asset.url)" :alt="asset.name"/><div><b>{{asset.name}}</b><small>{{asset.source_task_id ? `来源任务 #${asset.source_task_id}` : '本地上传'}} · {{new Date(asset.created_at).toLocaleDateString()}}</small></div></button><p v-if="!materialAssets.length" class="empty">暂无素材。可上传本地图片，或在任务中心领取生成图片。</p></div></section>
      <section v-else-if="page==='drafts'" class="page"><div class="section-heading"><div><span>确认后将商品创建到妙手公共采集箱。</span></div><button class="primary" @click="page='materials'">新建商品草稿</button></div><div class="draft-table"><div class="thead draft-thead"><span>商品</span><span>商品标题</span><span>SKU 数量</span><span>来源任务</span><span>创建时间</span><span>更新时间</span><span>最新修改用户</span><span>状态</span><span>操作</span></div><div v-for="draft in pagedDrafts" :key="draft.id" class="trow draft-trow"><button v-if="draft.image_urls?.[0]" class="draft-thumbnail" title="查看大图" @click="openImagePreview(draft.image_urls[0], draft.title)"><img :src="imageUrl(draft.image_urls[0])" :alt="draft.title"/></button><span v-else></span><b class="draft-product-title">{{draft.title}}</b><span>{{draft.sku_items?.length || 1}}</span><span>{{draft.source_task_id ? `#${draft.source_task_id}` : '素材库'}}</span><span>{{new Date(draft.created_at).toLocaleString()}}</span><span>{{new Date(draft.updated_at || draft.created_at).toLocaleString()}}</span><span>{{draft.updated_by_name || '历史记录缺失'}}</span><span class="chip" :class="draft.miaoshou_collect_box_id ? 'blue' : 'orange'">{{draft.miaoshou_collect_box_id ? '已发布至妙手' : '待发布至妙手'}}</span><span><button @click="openDraftEditDialog(draft)">编辑</button> <button v-if="!draft.miaoshou_collect_box_id" class="primary compact-action" :disabled="publishingDraftId===draft.id" @click="publishDraftToMiaoshou(draft)">{{publishingDraftId===draft.id ? '发布中…' : '发布到妙手'}}</button><small v-else>采集箱 #{{draft.miaoshou_collect_box_id}}</small></span></div><div v-if="!drafts.length" class="empty">暂无商品草稿，请先在任务中心选图。</div><footer v-else class="draft-pagination"><span>共 {{drafts.length}} 条</span><label>每页 <select v-model.number="draftPageSize" @change="changeDraftPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option><option :value="500">500</option><option :value="1000">1000</option></select> 条</label><button :disabled="visibleDraftPage===1" @click="currentDraftPage=visibleDraftPage-1">上一页</button><span>第 {{visibleDraftPage}} / {{draftPageCount}} 页</span><button :disabled="visibleDraftPage===draftPageCount" @click="currentDraftPage=visibleDraftPage+1">下一页</button></footer></div></section>
      <section v-else-if="page==='members' && user?.role==='company_admin'" class="page"><div class="section-heading"><div><span>管理本公司普通成员的账号、登录密码、两字符用户代码和启用状态。</span></div><button class="primary" @click="openMemberDialog()">新增成员</button></div><section class="draft-table"><div class="thead" style="grid-template-columns:1fr .65fr .8fr .8fr .8fr .9fr .8fr"><span>成员</span><span>用户代码</span><span>账号类型</span><span>邮箱</span><span>状态</span><span>加入时间</span><span>操作</span></div><div v-for="member in members" :key="member.id" class="trow" style="grid-template-columns:1fr .65fr .8fr .8fr .8fr .9fr .8fr"><span><b>{{member.name}}</b></span><span>{{member.user_code || '—'}}</span><span>普通成员</span><span>{{member.email}}</span><span class="chip" :class="member.is_active ? 'blue' : 'orange'">{{member.is_active ? '启用中' : '已停用'}}</span><span>{{new Date(member.created_at).toLocaleDateString()}}</span><span><button @click="openMemberDialog(member)">编辑</button> <button :class="member.is_active ? 'negative' : 'positive'" @click="toggleMember(member)">{{member.is_active ? '停用' : '启用'}}</button></span></div><p v-if="!members.length" class="empty">暂未添加普通成员。</p></section></section>
      <section v-else-if="page==='shops' && user?.role==='company_admin'" class="page"><div class="section-heading"><div><span>已同步的妙手店铺会保存在数据库中，可为每个店铺分配多个普通成员。</span></div><button class="primary" :disabled="shopLoading" @click="loadMiaoshouShops">{{shopLoading ? '同步中…' : '↻ 同步妙手店铺'}}</button></div><p v-if="shopError" class="error">{{shopError}}</p><section class="draft-table"><div class="thead" style="grid-template-columns:.65fr 1.2fr 1fr .75fr .7fr .9fr .9fr 1.3fr .75fr"><span>店铺 ID</span><span>店铺名称</span><span>店铺昵称</span><span>平台</span><span>站点</span><span>授权状态</span><span>授权到期</span><span>管理人员</span><span>操作</span></div><div v-for="shop in managedShops" :key="shop.id" class="trow" style="grid-template-columns:.65fr 1.2fr 1fr .75fr .7fr .9fr .9fr 1.3fr .75fr"><span>#{{shop.external_shop_id || shop.id}}</span><span><b>{{shop.name || '—'}}</b></span><span>{{shop.nickname || '—'}}</span><span>{{shop.platform || '—'}}</span><span>{{shop.region || '—'}}</span><span class="chip" :class="shop.auth_status ? 'blue' : 'orange'">{{shop.auth_status || '未知'}}</span><span>{{shop.auth_expires_at || '—'}}</span><span>{{shop.manager_users.length ? shop.manager_users.map((member:any)=>member.name).join('、') : '暂未分配'}}</span><span><button @click="openShopManagersDialog(shop)">分配人员</button></span></div><p v-if="!managedShops.length && !shopLoading" class="empty">暂无已同步店铺，点击“同步妙手店铺”开始获取。</p></section></section>
      <section v-else class="page"><div class="points-grid"><article class="balance"><span>可用积分</span><b>{{points?.available ?? 0}}</b><small>公司管理员可管理充值</small></article><article class="balance muted"><span>冻结积分</span><b>{{points?.frozen ?? 0}}</b><small>任务完成后自动结算</small></article><article class="rule"><h3>AI 积分结算规则</h3><p>任务提交时先预冻结，完成后按实际 AI 用量结算，多退少补。</p></article></div><section class="panel ledger"><h3>积分流水</h3><div v-for="row in pagedLedgerEntries" :key="row.id" class="ledger-row"><span><b>{{row.entry_type}}</b><small>{{new Date(row.created_at).toLocaleString()}}</small></span><span>{{row.note}}</span><span class="ledger-actor">操作人：{{row.actor_name}}</span><strong :class="row.amount>0?'positive':'negative'">{{row.amount>0?'+':''}}{{row.amount}}</strong><span>余额 {{row.balance_after}}</span></div><footer v-if="ledgerEntries.length" class="draft-pagination"><span>共 {{ledgerEntries.length}} 条</span><label>每页 <select v-model.number="ledgerPageSize" @change="changeLedgerPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option><option :value="500">500</option><option :value="1000">1000</option></select> 条</label><button :disabled="visibleLedgerPage===1" @click="currentLedgerPage=visibleLedgerPage-1">上一页</button><span>第 {{visibleLedgerPage}} / {{ledgerPageCount}} 页</span><button :disabled="visibleLedgerPage===ledgerPageCount" @click="currentLedgerPage=visibleLedgerPage+1">下一页</button></footer></section></section>
    </section>
  </main>
  <div v-if="showTaskDetailDialog" class="modal-backdrop" @click.self="showTaskDetailDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showTaskDetailDialog=false">×</button><h2>任务详情 #{{viewingTask?.id}}</h2><p>{{viewingTask?.parameters?.task_type || '替换印花'}} · {{viewingTask?.template_name || '历史模板已删除'}}</p><section class="draft-edit-section"><strong>印花图</strong><div class="material-draft-preview-images"><button v-for="url in viewingTask?.parameters?.print_urls || []" :key="url" @click="openImagePreview(url, '印花图')"><img :src="imageUrl(url)" alt="印花图"/></button><p v-if="!(viewingTask?.parameters?.print_urls?.length)">未保留印花图。</p></div></section><section class="draft-edit-section"><strong>创作参数</strong><p>画面比例：{{viewingTask?.parameters?.ratio || '—'}} · 清晰度：{{viewingTask?.parameters?.quality || '—'}}</p><p>创作要求：{{viewingTask?.parameters?.creative_requirement || '未填写'}}</p></section><section class="draft-edit-section"><strong>任务信息</strong><p>模型：{{viewingTask?.provider === 'grsai' ? 'Grsai' : viewingTask?.provider || '默认模型'}} <span v-if="viewingTask?.provider_model">· {{viewingTask.provider_model}}</span></p><p>状态：<span class="chip" :class="taskStatusClass(viewingTask?.status)">{{taskStatusLabel[viewingTask?.status] || viewingTask?.status || '—'}}</span></p><p>外部任务 ID：{{viewingTask?.provider_task_id || '—'}}</p><p v-if="viewingTask?.failure_reason" class="error">失败原因：{{viewingTask.failure_reason}}</p></section><div class="modal-actions"><button class="primary" @click="showTaskDetailDialog=false">关闭</button></div></section></div>
  <div v-if="showCreativeAssetsDialog" class="modal-backdrop" @click.self="showCreativeAssetsDialog=false"><section class="modal-card asset-dialog"><button class="modal-close" @click="showCreativeAssetsDialog=false">×</button><h2>印花图素材</h2><div class="asset-summary"><span>共 {{creativeAssets.length}} 项，已上传 {{creativeAssets.length}}，失败 0</span><label class="add-assets">＋ 继续上传<input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="onCreativeAssetChange"/></label></div><div class="asset-dialog-heading"><div><h3>印花图</h3><span>{{creativeAssets.length}} / 1000</span></div><button @click="clearCreativeAssets">清空</button></div><p class="asset-status">共 {{creativeAssets.length}} 项，已上传 {{creativeAssets.length}}，失败 0</p><div class="asset-list"><article v-for="asset in creativeAssets" :key="asset.id" class="asset-row"><img :src="asset.preview" :alt="asset.file.name"/><div><strong>{{asset.file.name}}</strong><p><span>印花图</span>{{(asset.file.size / 1024).toFixed(1)}}KB</p></div><button class="asset-delete" title="删除" @click="removeCreativeAsset(asset.id)">×</button></article><p v-if="!creativeAssets.length" class="asset-empty">暂未上传印花图。</p></div></section></div>
  <div v-if="showMyAccountDialog" class="modal-backdrop" @click.self="showMyAccountDialog=false"><section class="modal-card"><h2>账号设置</h2><p>可修改当前管理员名称和用户代码；用户代码留空可清除，且在本公司内不可重复。</p><label>管理员名称<input v-model="myName" maxlength="80" placeholder="请输入管理员名称" /></label><label>用户代码 <small>（两个字符）</small><input v-model="myUserCode" maxlength="2" placeholder="例如：CN" /></label><div class="modal-actions"><button class="ghost" @click="showMyAccountDialog=false">取消</button><button class="primary" :disabled="myAccountSaving" @click="saveMyUserCode">{{myAccountSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showMaterialDraftDialog" class="modal-backdrop" @click.self="showMaterialDraftDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showMaterialDraftDialog=false">×</button><h2>创建商品草稿</h2><p>将使用已选的 {{selectedMaterialAssetIds.length}} 张素材创建商品草稿。</p><label>产品模板<select v-model="materialDraftTemplateId" @change="onMaterialDraftTemplateChange"><option :value="null">请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><section class="material-draft-preview"><div class="material-draft-preview-heading"><strong>图片预览</strong><span>{{selectedMaterialAssets.length}} 张</span></div><div class="material-draft-preview-images"><img v-for="asset in selectedMaterialAssets" :key="asset.id" :src="imageUrl(asset.url)" :alt="asset.name"/></div></section><section v-if="materialDraftTemplate" class="material-draft-details"><label>商品标题<div class="material-draft-title-row"><input v-model="materialDraftTitle" maxlength="180" placeholder="请生成或填写商品标题"/><button class="secondary" :disabled="materialDraftTitleGenerating" @click="generateMaterialDraftTitle">{{materialDraftTitleGenerating ? '生成中…' : 'AI 生成标题'}}</button></div><small>将使用此模版的 AI生成标题约束和首张素材图生成标题。</small></label><label>产品描述<textarea v-model="materialDraftProductDescription" maxlength="5000" placeholder="默认使用产品模版描述，可按商品修改"></textarea></label></section><section v-if="materialDraftTemplate" class="material-draft-sku-summary"><strong>基础 SKU 列表</strong><p>每张图片生成 1 个基础 SKU；发布妙手时会拼接模板尺码：{{materialDraftSizes.length ? materialDraftSizes.join('、') : '默认规格'}}。</p><b>共 {{materialDraftSkuCount}} 个基础 SKU</b><small>格式：M05L + 用户代码 + 6 位随机字符串</small><div class="material-draft-sku-list"><div v-for="item in materialDraftSkuPreviewItems" :key="item.sku"><span>图片 SKU</span><code>{{item.sku}}</code></div></div><label class="material-draft-size-chart">尺码图<input accept="image/png,image/jpeg,image/webp" type="file" @change="onMaterialDraftSizeChartChange"/><small>{{materialDraftSizeChart ? materialDraftSizeChart.name : materialDraftTemplate?.size_chart_url ? '默认使用产品模版尺码图，可重新选择一张图片' : '可上传 1 张尺码图，支持 JPG、PNG、WebP，最大 5MB'}}</small><img v-if="materialDraftSizeChartPreview" :src="materialDraftSizeChartPreview" alt="尺码图预览"/></label></section><div class="modal-actions"><button class="ghost" @click="showMaterialDraftDialog=false">取消</button><button class="primary" :disabled="materialDraftSaving" @click="createDraftFromMaterialAssets">{{materialDraftSaving ? '创建中…' : '确认创建'}}</button></div></section></div>
  <div v-if="showTaskDraftDialog" class="modal-backdrop" @click.self="showTaskDraftDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showTaskDraftDialog=false">×</button><h2>创建商品草稿</h2><p>将使用任务 #{{draftingTask?.id}} 已确认的生成图创建商品草稿。</p><label>产品模板<input :value="templates.find(template => template.id === draftingTask?.template_id)?.name || '历史模板已删除'" readonly /></label><section class="material-draft-preview"><div class="material-draft-preview-heading"><strong>图片预览</strong><span>1 张</span></div><div class="material-draft-preview-images"><img v-if="draftingTask?.selected_result_url" :src="imageUrl(draftingTask.selected_result_url)" alt="任务已选结果图"/></div></section><section class="material-draft-details"><label>商品标题<div class="material-draft-title-row"><input v-model="taskDraftTitle" maxlength="180" placeholder="请生成或填写商品标题"/><button class="secondary" :disabled="taskDraftTitleGenerating" @click="generateTaskDraftTitle">{{taskDraftTitleGenerating ? '生成中…' : 'AI 生成标题'}}</button></div><small>将使用该任务产品模板的 AI 生成标题约束和已选结果图生成标题。</small></label><label>产品描述<textarea v-model="taskDraftProductDescription" maxlength="5000" placeholder="默认使用产品模版描述，可按商品修改"></textarea></label></section><section class="material-draft-sku-summary"><strong>基础 SKU 列表</strong><p>已选结果图将生成 1 个基础 SKU；发布妙手时会拼接模板尺码。</p><div class="material-draft-sku-list"><div v-for="item in taskDraftSkuPreviewItems" :key="item.sku"><span>图片 SKU</span><code>{{item.sku}}</code></div></div><label class="material-draft-size-chart">尺码图<input accept="image/png,image/jpeg,image/webp" type="file" @change="onTaskDraftSizeChartChange"/><small>{{taskDraftSizeChart ? taskDraftSizeChart.name : taskDraftSizeChartPreview ? '默认使用产品模版尺码图，可重新选择一张图片' : '可上传 1 张尺码图，支持 JPG、PNG、WebP，最大 5MB'}}</small><img v-if="taskDraftSizeChartPreview" :src="taskDraftSizeChartPreview" alt="尺码图预览"/></label></section><div class="modal-actions"><button class="ghost" @click="showTaskDraftDialog=false">取消</button><button class="primary" :disabled="taskDraftSaving" @click="createTaskDraft">{{taskDraftSaving ? '创建中…' : '确认创建'}}</button></div></section></div>
  <div v-if="showDraftEditDialog" class="modal-backdrop" @click.self="showDraftEditDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showDraftEditDialog=false">×</button><h2>编辑商品草稿</h2><p>可修改商品标题和产品描述。</p><label>产品标题<input v-model="draftEditTitle" maxlength="180" placeholder="请输入商品标题"/></label><label>产品描述<textarea v-model="draftEditProductDescription" class="draft-edit-description" maxlength="5000" placeholder="请输入产品描述"></textarea></label><section class="draft-edit-section"><strong>产品图片</strong><div class="draft-edit-preview"><div v-for="url in editingDraft?.image_urls" :key="url" class="draft-edit-image-item"><code>{{draftSkuForImage(editingDraft, url)}}</code><button title="放大查看" @click="openImagePreview(url, editingDraft?.title || '商品素材')"><img :src="imageUrl(url)" :alt="editingDraft?.title || '商品素材'"/></button></div></div></section><section v-if="editingDraft?.size_chart_url" class="draft-edit-section"><strong>尺码图</strong><button class="draft-edit-size-chart-button" title="放大查看" @click="openImagePreview(editingDraft.size_chart_url, '尺码图')"><img class="draft-edit-size-chart" :src="imageUrl(editingDraft.size_chart_url)" alt="尺码图"/></button></section><p v-if="draftEditError" class="error material-draft-error">{{draftEditError}}</p><div class="modal-actions"><button class="ghost" @click="showDraftEditDialog=false">取消</button><button class="primary" :disabled="draftEditSaving" @click="saveDraftEdit">{{draftEditSaving ? '保存中…' : '保存修改'}}</button></div></section></div>
  <div v-if="showGroupDialog" class="modal-backdrop" @click.self="showGroupDialog=false">
    <section v-if="showGroupDialog" class="modal-card"><h2>新增模板分类</h2><label>分类名称<input v-model="newGroupName" placeholder="例如：夏季服装" @keyup.enter="createGroup" /></label><div class="modal-actions"><button class="ghost" @click="showGroupDialog=false">取消</button><button class="primary" @click="createGroup">确认新增</button></div></section>
  </div>
  <div v-if="showMemberDialog" class="modal-backdrop" @click.self="showMemberDialog=false"><section class="modal-card"><h2>{{editingMember ? '编辑成员' : '新增成员'}}</h2><p>{{editingMember ? '留空密码即可保持原密码不变。' : '新成员将作为普通成员加入当前公司。'}}</p><label>姓名<input v-model="memberForm.name" maxlength="80" placeholder="请输入姓名" /></label><label>用户代码<input v-model="memberForm.user_code" maxlength="2" placeholder="例如：CN" /></label><label>邮箱<input v-model="memberForm.email" type="email" placeholder="name@example.com" /></label><label>登录密码<input v-model="memberForm.password" type="password" minlength="8" :placeholder="editingMember ? '留空则不修改' : '至少 8 个字符'" /></label><div class="modal-actions"><button class="ghost" @click="showMemberDialog=false">取消</button><button class="primary" :disabled="memberSaving" @click="saveMember">{{memberSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showShopManagersDialog" class="modal-backdrop" @click.self="showShopManagersDialog=false"><section class="modal-card"><h2>分配店铺管理人员</h2><p>{{managingShop?.name}}。被选中的普通成员可在该店铺创建、管理并上架商品。</p><label v-for="member in members" :key="member.id" class="manager-option"><input v-model="selectedManagerIds" :value="member.id" type="checkbox" />{{member.name}} <small>{{member.email}}</small></label><p v-if="!members.length" class="empty">请先在成员管理中新增普通成员。</p><div class="modal-actions"><button class="ghost" @click="showShopManagersDialog=false">取消</button><button class="primary" :disabled="shopManagersSaving" @click="saveShopManagers">{{shopManagersSaving ? '保存中…' : '保存分配'}}</button></div></section></div>
  <div v-if="showTemplateDialog" class="drawer-backdrop" @click.self="showTemplateDialog=false"><section class="template-drawer"><header><div><h2>{{editingTemplate ? '编辑产品模板' : '新增产品模板'}}</h2><p>完善模板信息后可直接用于 AI 创作。</p></div><button class="drawer-close" aria-label="关闭" @click="showTemplateDialog=false">×</button></header><nav class="drawer-tabs"><button :class="{active:templateFormTab==='basic'}" @click="templateFormTab='basic'">模版信息</button><button :class="{active:templateFormTab==='product'}" @click="templateFormTab='product'">商品信息</button><button :class="{active:templateFormTab==='sku'}" @click="templateFormTab='sku'">SKU</button><button :class="{active:templateFormTab==='logistics'}" @click="templateFormTab='logistics'">物流信息</button><button :class="{active:templateFormTab==='ai-prompts'}" @click="templateFormTab='ai-prompts'">AI提示词</button></nav><div class="drawer-content"><div v-if="templateFormTab==='basic'" class="drawer-form"><label>模板名称<span>*</span><input v-model="newTemplateName" placeholder="例如：宽松短袖上衣" /></label><label>模板图片<span>*</span><input accept="image/png,image/jpeg,image/webp" type="file" @change="onCoverChange" /><small>{{newTemplateImage ? newTemplateImage.name : editingTemplate?.cover_url ? '保留当前图片' : '支持 JPG、PNG、WebP，最大 5MB'}}</small><div v-if="newTemplateImagePreview" class="template-upload-preview"><img :src="newTemplateImagePreview" alt="模板图片预览" /></div></label><label>模板描述<span>*</span><textarea v-model="newTemplateDescription" maxlength="500" placeholder="描述产品材质、版型和适用的印花区域"></textarea></label><label>模板分类<span>*</span><select v-model="newTemplateGroupId"><option :value="null" disabled>请选择模板分类</option><option v-for="group in templateGroups" :key="group.id" :value="group.id">{{group.name}}</option></select></label></div><div v-else-if="templateFormTab==='product'" class="drawer-form product-info-form"><label>AI生成标题约束<span>*</span><input v-model="newTemplateTitleTemplate" maxlength="500" placeholder="例如：突出材质、款式与适用场景，不包含夸大宣传" /></label><label>产品描述<span>*</span><textarea v-model="newTemplateProductDescription" maxlength="5000" placeholder="填写商品详情页的产品描述"></textarea></label><label>尺码图<span>*</span><input accept="image/png,image/jpeg,image/webp" type="file" @change="onSizeChartChange" /><small>{{newTemplateSizeChart ? newTemplateSizeChart.name : editingTemplate?.size_chart_url ? '保留当前尺码图' : '支持 JPG、PNG、WebP，最多上传 1 张，最大 5MB'}}</small><div v-if="newTemplateSizeChartPreview" class="template-upload-preview"><img :src="newTemplateSizeChartPreview" alt="尺码图预览" /></div></label></div><div v-else-if="templateFormTab==='sku'" class="sku-form"><section><strong><b>*</b> 尺码</strong><div class="sku-size-grid"><div v-for="(_, index) in newSkuSizeOptions" :key="index" class="sku-size-row"><input v-model="newSkuSizeOptions[index]" maxlength="50" placeholder="例如：M"/><small>{{newSkuSizeOptions[index].length}} / 50</small><button title="删除尺码" @click="newSkuSizeOptions.splice(index,1)">×</button></div></div><button class="sku-add-option" @click="addSkuSize">＋ 添加选项</button></section><small class="sku-total">预计生成 {{Math.max(1,newSkuSizeOptions.filter(value=>value.trim()).length)}} 个 SKU</small></div><div v-else-if="templateFormTab==='ai-prompts'" class="drawer-form ai-prompts-form"><div><h3>AI 提示词</h3><p>为印花贴合保存可复用的创作要求；在 AI 创作页选择模板后可一键填充并继续修改。</p></div><section v-for="(prompt, index) in newTemplateAiPrompts" :key="index" class="ai-prompt-editor"><div><b>提示词 {{index + 1}}</b><button type="button" class="danger" @click="removeTemplateAiPrompt(index)">删除</button></div><label>名称<input v-model="prompt.name" maxlength="80" placeholder="例如：自然布料贴合" /></label><label>提示词内容<textarea v-model="prompt.content" maxlength="1000" placeholder="描述印花贴合方式、细节、光影等创作要求"></textarea></label></section><button type="button" class="secondary ai-prompt-add" @click="addTemplateAiPrompt">＋ 新增提示词</button></div><div v-else class="drawer-form logistics-form"><h3>物流信息 <span title="用于运费及配送计算">?</span></h3><label><b>*</b> 包裹重量<div class="unit-input"><input v-model.number="newPackageWeight" type="number" min="0.001" step="0.001" placeholder="请输入重量" /><span>KG</span></div></label><label><b>*</b> 包裹尺寸<div class="dimension-inputs"><label><input v-model.number="newPackageLength" type="number" min="0.1" step="0.1" placeholder="长" /><span>cm</span></label><label><input v-model.number="newPackageWidth" type="number" min="0.1" step="0.1" placeholder="宽" /><span>cm</span></label><label><input v-model.number="newPackageHeight" type="number" min="0.1" step="0.1" placeholder="高" /><span>cm</span></label></div></label></div></div><footer><button class="ghost" @click="showTemplateDialog=false">取消</button><button class="primary" @click="createTemplate">{{editingTemplate ? '保存修改' : '确认新增'}}</button></footer></section></div>
  <div v-if="previewImageUrl" class="image-preview-backdrop" @click.self="previewImageUrl=''"><section class="image-preview-modal"><button class="modal-close" aria-label="关闭大图" @click="previewImageUrl=''">×</button><img :src="previewImageUrl" :alt="previewImageAlt"/></section></div>
  <div v-if="toast" class="toast" role="alert" style="position:fixed;top:24px;left:50%;z-index:1000;transform:translateX(-50%);padding:12px 18px;border-radius:10px;background:#302954;color:#fff;box-shadow:0 10px 28px #30295440;font-size:14px">{{ toast }}</div>
</template>
