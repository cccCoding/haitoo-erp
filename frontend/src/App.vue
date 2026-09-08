<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const token = ref(localStorage.getItem('haitoro_token') || '')
const page = ref('dashboard')
const email = ref('operator@haitoro-demo.com')
const password = ref('ChangeMe123!')
const user = ref<any>(null), company = ref<any>(null), shops = ref<any[]>([]), templates = ref<any[]>([]), templateGroups = ref<any[]>([]), tasks = ref<any[]>([]), materialAssets = ref<any[]>([]), drafts = ref<any[]>([]), members = ref<any[]>([]), aiProviders = ref<any[]>([])
const loading = ref(false), error = ref('')
const toast = ref('')
const templateQuery = ref(''), activeGroupId = ref<number | null>(null), selectedTemplateId = ref<number | null>(null)
const showGroupDialog = ref(false), showTemplateDialog = ref(false), templateFormTab = ref<'basic' | 'product' | 'sku' | 'logistics' | 'ai-prompts'>('basic'), newGroupName = ref(''), newTemplateName = ref(''), newTemplateDescription = ref(''), newTemplateTitleTemplate = ref(''), newTemplateProductDescription = ref(''), newTemplateSizeChart = ref<File | null>(null), newTemplateSizeChartPreview = ref(''), newTemplateGroupId = ref<number | null>(null), newTemplateImage = ref<File | null>(null), newTemplateImagePreview = ref(''), newPackageWeight = ref<number | null>(null), newPackageLength = ref<number | null>(null), newPackageWidth = ref<number | null>(null), newPackageHeight = ref<number | null>(null), newSkuSizeOptions = ref<string[]>([]), newTemplateAiPrompts = ref<{name:string; content:string}[]>([]), editingTemplate = ref<any>(null)
const showMemberDialog = ref(false), editingMember = ref<any>(null), memberForm = ref({ name: '', user_code: '', email: '', password: '', is_active: true }), memberSaving = ref(false), memberFormError = ref('')
const showMemberCredentialDialog = ref(false), credentialMember = ref<any>(null), credentialProvider = ref<any>(null), credentialApiKey = ref(''), credentialSaving = ref(false)
const showMyAccountDialog = ref(false), myName = ref(''), myUserCode = ref(''), myAccountSaving = ref(false)
const managedShops = ref<any[]>([]), shopLoading = ref(false), shopError = ref('')
const showMiaoshouDialog = ref(false), miaoshouForm = ref({ app_id: '', app_secret: '' }), miaoshouSaving = ref(false)
const materialUploading = ref(false), materialUploadError = ref('')
const selectedMaterialAssetIds = ref<number[]>([]), materialTemplateFilterId = ref<number | null>(null), showMaterialDraftDialog = ref(false), materialDraftTemplateId = ref<number | null>(null), materialDraftTitle = ref(''), materialDraftProductDescription = ref(''), materialDraftSizeChartPreview = ref(''), materialDraftTitleGenerating = ref(false), materialDraftSaving = ref(false)
const pendingMaterialUploadFiles = ref<File[]>([]), showMaterialUploadDialog = ref(false), materialUploadTemplateId = ref<number | null>(null)
const materialUploadedCount = ref(0), materialUploadTotal = ref(0), pendingMaterialUploadUrls = ref<string[]>([])
const MATERIAL_UPLOAD_CONCURRENCY = 8, MATERIAL_UPLOAD_MAX_FILES = 100, IMAGE_UPLOAD_RETRY = 2
const templateSaving = ref(false)
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'], MAX_IMAGE_BYTES = 5 * 1024 * 1024
const showDraftEditDialog = ref(false), editingDraft = ref<any>(null), draftEditTitle = ref(''), draftEditProductDescription = ref(''), draftEditSaving = ref(false), draftEditError = ref('')
const publishingDraftId = ref<number | null>(null)
const draftPageSize = ref(20), currentDraftPage = ref(1), draftTemplateFilterId = ref<number | null>(null), draftCreatorFilterId = ref<number | null>(null)
const taskPageSize = ref(20), currentTaskPage = ref(1), taskTotal = ref(0), taskActiveCount = ref(0), taskStatusCounts = ref<Record<string, number>>({}), taskCreatorFilterId = ref<number | null>(null)
const materialPageSize = ref(20), currentMaterialPage = ref(1), materialTotal = ref(0), materialCreatorFilterId = ref<number | null>(null)
const creatorFiltersInitialized = ref(false)
const previewImageUrl = ref(''), previewImageAlt = ref('')
const showShopManagersDialog = ref(false), managingShop = ref<any>(null), selectedManagerIds = ref<number[]>([]), shopManagersSaving = ref(false)
const showTaskDetailDialog = ref(false), viewingTask = ref<any>(null), taskDetailLoading = ref(false)
const taskListRefreshing = ref(false), retryingTaskId = ref<number | null>(null)
const showClaimMaterialsDialog = ref(false), claimingTask = ref<any>(null), selectedClaimResultUrls = ref<string[]>([]), claimingMaterials = ref(false)
type CreativeAsset = { id: string; file: File; preview: string; uploadedUrl?: string }
const defaultSkuSizes = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL']
const defaultPackageLogistics = { weight: 0.28, length: 30, width: 16, height: 2 }
const creativeAssets = ref<CreativeAsset[]>([]), showCreativeAssetsDialog = ref(false), creativeAssetError = ref(''), creativeSubmitError = ref(''), creativeRequirement = ref(''), creativePromptIndex = ref(''), creativeProvider = ref(''), creativeRatio = ref<'1:1' | '3:4'>('1:1'), creativeQuality = ref<'1K' | '2K'>('1K'), creativeUploading = ref(false), creativeUploadedCount = ref(0)
const personalWhiteImages = ref<any[]>([]), personalPrompts = ref<any[]>([]), selectedWhiteImageId = ref<number | null>(null), personalResourcesLoading = ref(false)
const showPersonalResourcesDialog = ref(false), personalResourceTab = ref<'white-images' | 'prompts'>('white-images'), managedResourceUserId = ref<number | null>(null), managedWhiteImages = ref<any[]>([]), managedPrompts = ref<any[]>([]), personalResourceSaving = ref(false)
const showTeamResourcesDialog = ref(false), teamResourceTab = ref<'white-images' | 'prompts'>('white-images'), teamResourceUserId = ref<number | null>(null), teamResourceTemplateId = ref<number | null>(null), teamWhiteImages = ref<any[]>([]), teamPrompts = ref<any[]>([]), teamResourcesLoading = ref(false), teamResourceQuery = ref('')
const editingWhiteImage = ref<any>(null), whiteImageForm = ref({ template_id: null as number | null, name: '', file: null as File | null })
const editingPersonalPrompt = ref<any>(null), personalPromptForm = ref({ template_id: null as number | null, name: '', content: '' })
const nav = [{key:'dashboard', icon:'◈', label:'工作台'}, {key:'templates', icon:'▦', label:'产品模板'}, {key:'pod', icon:'✦', label:'AI创作'}, {key:'tasks', icon:'◌', label:'任务中心'}, {key:'materials', icon:'◈', label:'素材库'}, {key:'drafts', icon:'▤', label:'商品草稿'}, {key:'members', icon:'♙', label:'成员管理', adminOnly:true}, {key:'shops', icon:'▣', label:'店铺管理', adminOnly:true}]
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }))
const visibleNav = computed(() => nav.filter(item => !item.adminOnly || user.value?.role === 'company_admin'))
const pageTitle = computed(() => nav.find(x => x.key === page.value)?.label || '')
const filteredTemplates = computed(() => templates.value.filter(t => (!activeGroupId.value || t.group_id === activeGroupId.value) && t.name.toLowerCase().includes(templateQuery.value.trim().toLowerCase())))
// 运营端接口只返回后台已启用的模型；这里再保留一次筛选，避免接口数据异常时将停用模型带入任务。
const availableAiProviders = computed(() => aiProviders.value.filter(provider => provider.enabled !== false))
const selectedCreativeProvider = computed(() => availableAiProviders.value.find(provider => provider.provider === creativeProvider.value))
const creativeCredentialError = computed(() => selectedCreativeProvider.value?.credential_configured === false
  ? `尚未配置个人 ${selectedCreativeProvider.value.display_name} 平台密钥，请联系公司管理员配置`
  : '')
const selectedTemplate = computed(() => templates.value.find(t => t.id === selectedTemplateId.value))
const selectedWhiteImage = computed(() => personalWhiteImages.value.find(item => item.id === selectedWhiteImageId.value))
const otherResourceOwners = computed(() => user.value?.role === 'company_admin' ? members.value.filter(owner => owner.id !== user.value.id) : [])
const filteredTeamWhiteImages = computed(() => {
  const query = teamResourceQuery.value.trim().toLowerCase()
  return query ? teamWhiteImages.value.filter(item => item.name.toLowerCase().includes(query)) : teamWhiteImages.value
})
const filteredTeamPrompts = computed(() => {
  const query = teamResourceQuery.value.trim().toLowerCase()
  return query ? teamPrompts.value.filter(item => `${item.name} ${item.content}`.toLowerCase().includes(query)) : teamPrompts.value
})
const selectedMaterialAssets = computed(() => materialAssets.value.filter(asset => selectedMaterialAssetIds.value.includes(asset.id)))
const filteredMaterialAssets = computed(() => materialAssets.value)
const allCurrentMaterialAssetsSelected = computed(() => { const selectable=filteredMaterialAssets.value.filter(asset=>asset.sku); return Boolean(selectable.length) && selectable.every(asset => selectedMaterialAssetIds.value.includes(asset.id)) })
const someCurrentMaterialAssetsSelected = computed(() => !allCurrentMaterialAssetsSelected.value && filteredMaterialAssets.value.some(asset => selectedMaterialAssetIds.value.includes(asset.id)))
const selectedMaterialTemplateId = computed(() => {
  const templateIds = [...new Set(selectedMaterialAssets.value.map(asset => asset.template_id).filter(Boolean))]
  return templateIds.length === 1 ? templateIds[0] : null
})
const materialDraftTemplate = computed(() => templates.value.find(template => template.id === materialDraftTemplateId.value))
const materialDraftSizes = computed(() => {
  const options = materialDraftTemplate.value?.sku_specifications?.size?.options || []
  return options.map((size: unknown) => String(size).trim()).filter(Boolean)
})
const materialDraftSkuCount = computed(() => selectedMaterialAssets.value.length)
const filteredDrafts = computed(() => draftTemplateFilterId.value ? drafts.value.filter(draft => draft.template_id === draftTemplateFilterId.value) : drafts.value)
const draftPageCount = computed(() => Math.max(1, Math.ceil(filteredDrafts.value.length / draftPageSize.value)))
const visibleDraftPage = computed(() => Math.min(currentDraftPage.value, draftPageCount.value))
const pagedDrafts = computed(() => {
  const start = (visibleDraftPage.value - 1) * draftPageSize.value
  return filteredDrafts.value.slice(start, start + draftPageSize.value)
})
function changeDraftPageSize() { currentDraftPage.value = 1 }
async function changeDraftCreatorFilter() { currentDraftPage.value = 1; await refreshDraftList() }
async function refreshDraftList() {
  const { data } = await api.get('/drafts', { headers: headers.value, params: { creator_id: draftCreatorFilterId.value } })
  drafts.value = data
}
const taskPageCount = computed(() => Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value)))
const visibleTaskPage = computed(() => Math.min(currentTaskPage.value, taskPageCount.value))
const pagedTasks = computed(() => tasks.value)
function applyTaskPage(data: any) { tasks.value = data.items || []; taskTotal.value = data.total || 0; taskActiveCount.value = data.active_count || 0; taskStatusCounts.value = data.status_counts || {}; currentTaskPage.value = data.page || 1 }
async function changeTaskPageSize() { currentTaskPage.value = 1; await refreshTaskList() }
async function changeTaskPage(targetPage: number) { currentTaskPage.value = Math.min(Math.max(1, targetPage), taskPageCount.value); await refreshTaskList() }
async function changeTaskCreatorFilter() { currentTaskPage.value = 1; await refreshTaskList() }
const materialPageCount = computed(() => Math.max(1, Math.ceil(materialTotal.value / materialPageSize.value)))
const visibleMaterialPage = computed(() => Math.min(currentMaterialPage.value, materialPageCount.value))
function applyMaterialPage(data: any) { materialAssets.value = data.items || []; materialTotal.value = data.total || 0; currentMaterialPage.value = data.page || 1 }
async function changeMaterialPageSize() { currentMaterialPage.value = 1; await refreshMaterialList() }
async function changeMaterialPage(targetPage: number) { currentMaterialPage.value = Math.min(Math.max(1, targetPage), materialPageCount.value); await refreshMaterialList() }
async function changeMaterialFilter() { currentMaterialPage.value = 1; await refreshMaterialList() }
async function refreshMaterialList() {
  selectedMaterialAssetIds.value = []
  const { data } = await api.get('/material-assets', { headers: headers.value, params: { page: currentMaterialPage.value, page_size: materialPageSize.value, creator_id: materialCreatorFilterId.value, template_id: materialTemplateFilterId.value } })
  applyMaterialPage(data)
}
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
  const me = await api.get('/me', h)
  user.value = me.data.user
  company.value = me.data.company
  if (!creatorFiltersInitialized.value) {
    taskCreatorFilterId.value = user.value.id
    materialCreatorFilterId.value = user.value.id
    draftCreatorFilterId.value = user.value.id
    creatorFiltersInitialized.value = true
  }
  const [s, t, g, task, material, d, providers] = await Promise.all([api.get('/shops',h), api.get('/templates',h), api.get('/template-groups',h), api.get('/tasks',{...h,params:{page:currentTaskPage.value,page_size:taskPageSize.value,creator_id:taskCreatorFilterId.value}}), api.get('/material-assets',{...h,params:{page:currentMaterialPage.value,page_size:materialPageSize.value,creator_id:materialCreatorFilterId.value,template_id:materialTemplateFilterId.value}}), api.get('/drafts',{...h,params:{creator_id:draftCreatorFilterId.value}}), api.get('/ai-providers',h)])
  shops.value=s.data; templates.value=t.data; templateGroups.value=g.data; applyTaskPage(task.data); applyMaterialPage(material.data); drafts.value=d.data; aiProviders.value=providers.data
  // 后台停用当前所选模型后，刷新时立即切换到仍启用的默认模型，避免提交已停用的值。
  if (!availableAiProviders.value.some(item => item.provider === creativeProvider.value)) {
    creativeProvider.value = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || ''
  }
  if (user.value.role === 'company_admin') {
    const [companyMembers, companyShops] = await Promise.all([api.get('/members', h), api.get('/shops/manage', h)])
    members.value = companyMembers.data
    managedShops.value = companyShops.data
  } else { members.value = []; managedShops.value = [] }
  if (!selectedTemplateId.value && templates.value[0]) selectedTemplateId.value=templates.value[0].id
  if (selectedTemplateId.value) await loadMyTemplateResources(false)
}
async function login() { try { loading.value=true; error.value=''; const {data}=await api.post('/auth/login',{email:email.value,password:password.value}); token.value=data.access_token; localStorage.setItem('haitoro_token',token.value); await refresh() } catch { error.value='登录失败，请检查账号密码' } finally { loading.value=false } }
function onCreativeAssetChange(event: Event) {
  if (creativeUploading.value) { showToast('图片上传处理中，请等待本轮上传结束'); (event.target as HTMLInputElement).value = ''; return }
  const files = Array.from((event.target as HTMLInputElement).files || [])
  const available = 500 - creativeAssets.value.length
  const supported = files.filter(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size <= 5 * 1024 * 1024)
  supported.slice(0, available).forEach(file => creativeAssets.value.push({ id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`, file, preview: URL.createObjectURL(file) }))
  if (files.length <= available) creativeAssetError.value = ''
  if (supported.length !== files.length) creativeAssetError.value = '仅支持 JPG、PNG、WebP，且单张不能超过 5MB。'
  if (files.length > available) creativeAssetError.value = '单次印花贴合最多支持 500 张图片。'
  ;(event.target as HTMLInputElement).value = ''
}
function removeCreativeAsset(id: string) { if (creativeUploading.value) { showToast('图片上传处理中，暂时不能删除素材'); return } const asset = creativeAssets.value.find(item => item.id === id); if (asset) URL.revokeObjectURL(asset.preview); creativeAssets.value = creativeAssets.value.filter(item => item.id !== id) }
function clearCreativeAssets() { if (creativeUploading.value) { showToast('图片上传处理中，暂时不能清空素材'); return } creativeAssets.value.forEach(item => URL.revokeObjectURL(item.preview)); creativeAssets.value = []; showCreativeAssetsDialog.value = false }
async function uploadCreativeAssets() {
  // 固定本轮素材快照；任一 worker 失败后仍等待其他 worker 收尾，避免下一次提交与残留上传重叠。
  const assets = [...creativeAssets.value]
  const urls = Array<string>(assets.length)
  let cursor = 0
  creativeUploadedCount.value = assets.filter(asset => asset.uploadedUrl).length
  const worker = async () => {
    while (true) {
      const index = cursor++
      if (index >= assets.length) return
      const asset = assets[index]
      if (asset.uploadedUrl) { urls[index] = asset.uploadedUrl; continue }
      const {data: signed}=await api.post('/uploads/creative-asset/presign',{content_type:asset.file.type,content_length:asset.file.size},{headers:headers.value})
      await axios.put(signed.upload_url, asset.file, {headers:{'Content-Type':asset.file.type}})
      asset.uploadedUrl = signed.url
      urls[index] = signed.url
      creativeUploadedCount.value++
    }
  }
  const workerResults = await Promise.allSettled(Array.from({length: Math.min(4, assets.length)}, worker))
  const failedWorker = workerResults.find((result): result is PromiseRejectedResult => result.status === 'rejected')
  if (failedWorker) throw failedWorker.reason
  return urls
}
async function createTask() {
  creativeSubmitError.value = ''
  if (!creativeAssets.value.length) { creativeAssetError.value = '请先上传至少一张印花图，再开始印花贴合。'; return }
  if (!selectedWhiteImageId.value) { showToast(personalWhiteImages.value.length ? '请选择产品白底图' : '请先设置该模板的产品白底图'); return }
  if (!creativeRequirement.value.trim()) { showToast('请填写创作要求'); return }
  if (!selectedTemplateId.value) return
  if (!creativeProvider.value || !availableAiProviders.value.some(item => item.provider === creativeProvider.value)) { showToast('暂无可用的 AI 模型，请联系超级管理员在后台启用模型'); return }
  if (creativeCredentialError.value) { creativeSubmitError.value = creativeCredentialError.value; showToast(creativeCredentialError.value); return }
  try {
    creativeAssetError.value = ''
    creativeUploading.value = true
    const print_urls = await uploadCreativeAssets()
    const {data} = await api.post('/tasks',{template_id:selectedTemplateId.value,white_image_id:selectedWhiteImageId.value,provider:creativeProvider.value,ratio:creativeRatio.value,quality:creativeQuality.value,print_url:print_urls[0],print_urls,creative_requirement:creativeRequirement.value.trim()},{headers:headers.value})
    currentTaskPage.value = 1
    await refresh()
    page.value = 'tasks'
    showToast(`已创建 ${data.total} 条任务，共 ${print_urls.length} 张印花`)
  } catch (e:any) {
    const reason = e.response?.data?.detail || '创建 AI 任务失败'
    creativeSubmitError.value = reason
    showToast(reason)
  } finally { creativeUploading.value = false }
}
async function createGroup() { if (!newGroupName.value.trim()) return; try { await api.post('/template-groups',{name:newGroupName.value.trim()},{headers:headers.value}); newGroupName.value=''; showGroupDialog.value=false; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || '创建分类失败' } }
function openTemplateDialog(template?: any) { editingTemplate.value=template || null; templateFormTab.value='basic'; newTemplateName.value=template?.name || ''; newTemplateDescription.value=template?.description || ''; newTemplateTitleTemplate.value=template?.title_template || ''; newTemplateProductDescription.value=template?.product_description || ''; newTemplateSizeChart.value=null; newTemplateSizeChartPreview.value=imageUrl(template?.size_chart_url); newTemplateGroupId.value=template?.group_id || null; newTemplateImage.value=null; newTemplateImagePreview.value=imageUrl(template?.cover_url); newPackageWeight.value=template?.package_weight ?? defaultPackageLogistics.weight; newPackageLength.value=template?.package_length ?? defaultPackageLogistics.length; newPackageWidth.value=template?.package_width ?? defaultPackageLogistics.width; newPackageHeight.value=template?.package_height ?? defaultPackageLogistics.height; newSkuSizeOptions.value=template?.sku_specifications?.size?.options || [...defaultSkuSizes]; newTemplateAiPrompts.value=(template?.ai_prompts || []).map((item:any) => ({name:item?.name || '', content:item?.content || ''})); showTemplateDialog.value=true }
function addSkuSize() { newSkuSizeOptions.value.push('') }
function addTemplateAiPrompt() { newTemplateAiPrompts.value.push({ name: '', content: '' }) }
function removeTemplateAiPrompt(index: number) { newTemplateAiPrompts.value.splice(index, 1) }
function selectedTemplateAiPrompts() { return (selectedTemplate.value?.ai_prompts || []).filter((item:any) => item?.name && item?.content) }
function applyTemplateAiPrompt() {
  if (!creativePromptIndex.value) return
  const [source, identifier] = creativePromptIndex.value.split(':')
  const prompt = source === 'template' ? selectedTemplateAiPrompts()[Number(identifier)] : personalPrompts.value.find(item => item.id === Number(identifier))
  if (prompt) creativeRequirement.value=prompt.content
}
async function loadMyTemplateResources(preserveSelection = true) {
  if (!selectedTemplateId.value || !user.value) { personalWhiteImages.value=[]; personalPrompts.value=[]; selectedWhiteImageId.value=null; return }
  try {
    personalResourcesLoading.value=true
    const {data}=await api.get('/user-template-resources',{headers:headers.value,params:{template_id:selectedTemplateId.value}})
    personalWhiteImages.value=data.white_images || []; personalPrompts.value=data.prompts || []
    if (!preserveSelection || !personalWhiteImages.value.some(item=>item.id===selectedWhiteImageId.value)) selectedWhiteImageId.value=null
  } catch(e:any) { showToast(e.response?.data?.detail || '加载个人模板资源失败') }
  finally { personalResourcesLoading.value=false }
}
async function onCreativeTemplateChange() { selectedWhiteImageId.value=null; creativePromptIndex.value=''; creativeRequirement.value=''; await loadMyTemplateResources(false) }
async function loadManagedTemplateResources() {
  if (!managedResourceUserId.value) return
  try {
    const {data}=await api.get('/user-template-resources',{headers:headers.value,params:{user_id:managedResourceUserId.value}})
    managedWhiteImages.value=data.white_images || []; managedPrompts.value=data.prompts || []
  } catch(e:any) { showToast(e.response?.data?.detail || '加载员工模板资源失败') }
}
async function openPersonalResourcesDialog(tab: 'white-images' | 'prompts' = 'white-images') {
  personalResourceTab.value=tab; managedResourceUserId.value=user.value.id; resetWhiteImageForm(); resetPersonalPromptForm(); showPersonalResourcesDialog.value=true
  await loadManagedTemplateResources()
}
async function loadTeamTemplateResources() {
  if (!teamResourceUserId.value) { teamWhiteImages.value=[]; teamPrompts.value=[]; return }
  const userId=teamResourceUserId.value, templateId=teamResourceTemplateId.value
  try {
    teamResourcesLoading.value=true
    const params:any={user_id:userId}
    if (templateId) params.template_id=templateId
    const {data}=await api.get('/user-template-resources',{headers:headers.value,params})
    if (teamResourceUserId.value!==userId || teamResourceTemplateId.value!==templateId) return
    teamWhiteImages.value=data.white_images || []; teamPrompts.value=data.prompts || []
  } catch(e:any) { showToast(e.response?.data?.detail || '加载成员自定义内容失败') }
  finally { teamResourcesLoading.value=false }
}
async function openTeamResourcesDialog() {
  if (user.value?.role !== 'company_admin') return
  teamResourceTab.value='white-images'; teamResourceQuery.value=''; teamResourceUserId.value=otherResourceOwners.value[0]?.id || null; teamResourceTemplateId.value=null; teamWhiteImages.value=[]; teamPrompts.value=[]; showTeamResourcesDialog.value=true
  await loadTeamTemplateResources()
}
function resetWhiteImageForm() { editingWhiteImage.value=null; whiteImageForm.value={template_id:null,name:'',file:null} }
function editWhiteImage(item:any) { editingWhiteImage.value=item; whiteImageForm.value={template_id:item.template_id,name:item.name,file:null} }
function onWhiteImageFileChange(event:Event) { whiteImageForm.value.file=(event.target as HTMLInputElement).files?.[0] || null }
async function saveWhiteImage() {
  if (!whiteImageForm.value.template_id) { showToast('请先选择产品模板'); return }
  if (!managedResourceUserId.value || !whiteImageForm.value.name.trim()) { showToast('请填写白底图名称'); return }
  if (!editingWhiteImage.value && !whiteImageForm.value.file) { showToast('请上传白底图'); return }
  try {
    personalResourceSaving.value=true
    let image_url: string | undefined
    if (whiteImageForm.value.file) image_url = await presignAndUploadImage(whiteImageForm.value.file, 'template-white')
    if (editingWhiteImage.value) await api.put(`/user-template-white-images/${editingWhiteImage.value.id}`,{name:whiteImageForm.value.name.trim(),...(image_url?{image_url}:{})},{headers:headers.value})
    else await api.post('/user-template-white-images',{template_id:whiteImageForm.value.template_id,user_id:managedResourceUserId.value,name:whiteImageForm.value.name.trim(),image_url},{headers:headers.value})
    resetWhiteImageForm(); await loadManagedTemplateResources(); if(managedResourceUserId.value===user.value.id) await loadMyTemplateResources()
  } catch(e:any) { showToast(e.response?.data?.detail || '保存白底图失败') }
  finally { personalResourceSaving.value=false }
}
async function deleteWhiteImage(item:any) { if(!confirm(`确定删除白底图「${item.name}」吗？`)) return; try { await api.delete(`/user-template-white-images/${item.id}`,{headers:headers.value}); await loadManagedTemplateResources(); if(managedResourceUserId.value===user.value.id) await loadMyTemplateResources() } catch(e:any){showToast(e.response?.data?.detail || '删除白底图失败')} }
function resetPersonalPromptForm() { editingPersonalPrompt.value=null; personalPromptForm.value={template_id:null,name:'',content:''} }
function editPersonalPrompt(item:any) { editingPersonalPrompt.value=item; personalPromptForm.value={template_id:item.template_id,name:item.name,content:item.content} }
function resourceTemplateName(item:any) { return templates.value.find(template=>template.id===item.template_id)?.name || '模板已删除' }
async function savePersonalPrompt() {
  const name=personalPromptForm.value.name.trim(), content=personalPromptForm.value.content.trim()
  if(!personalPromptForm.value.template_id){showToast('请先选择产品模板');return}
  if(!managedResourceUserId.value || !name || !content){showToast('请完整填写名称和创作要求');return}
  try { personalResourceSaving.value=true; if(editingPersonalPrompt.value) await api.put(`/user-template-prompts/${editingPersonalPrompt.value.id}`,{name,content},{headers:headers.value}); else await api.post('/user-template-prompts',{template_id:personalPromptForm.value.template_id,user_id:managedResourceUserId.value,name,content},{headers:headers.value}); resetPersonalPromptForm(); await loadManagedTemplateResources(); if(managedResourceUserId.value===user.value.id) await loadMyTemplateResources() } catch(e:any){showToast(e.response?.data?.detail || '保存创作要求失败')} finally{personalResourceSaving.value=false}
}
async function deletePersonalPrompt(item:any) { if(!confirm(`确定删除创作要求「${item.name}」吗？`)) return; try { await api.delete(`/user-template-prompts/${item.id}`,{headers:headers.value}); await loadManagedTemplateResources(); if(managedResourceUserId.value===user.value.id) await loadMyTemplateResources() } catch(e:any){showToast(e.response?.data?.detail || '删除创作要求失败')} }
function onCoverChange(event: Event) { const file=(event.target as HTMLInputElement).files?.[0] || null; newTemplateImage.value=file; newTemplateImagePreview.value=file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.cover_url) }
function onSizeChartChange(event: Event) { const file=(event.target as HTMLInputElement).files?.[0] || null; newTemplateSizeChart.value=file; newTemplateSizeChartPreview.value=file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.size_chart_url) }
function normalizeTemplateNameForSku() { const name=newTemplateName.value.trim().toUpperCase(); if(!/^[A-Z0-9]{1,5}$/.test(name)){templateFormTab.value='basic';showToast('模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字');throw new Error('invalid template name')} newTemplateName.value=name }
async function presignAndUploadImage(file: File, category: string): Promise<string> {
  let lastError: any
  for (let attempt = 0; attempt <= IMAGE_UPLOAD_RETRY; attempt++) {
    try {
      const { data } = await api.post('/uploads/presign', {
        category, files: [{ content_type: file.type, content_length: file.size }],
      }, { headers: headers.value })
      await axios.put(data[0].upload_url, file, { headers: { 'Content-Type': file.type } })
      return data[0].url as string
    } catch (e: any) { lastError = e }
  }
  throw lastError
}
async function uploadCover() { normalizeTemplateNameForSku(); if (!newTemplateImage.value) return undefined; return presignAndUploadImage(newTemplateImage.value, 'template') }
async function uploadSizeChart() { if (!newTemplateSizeChart.value) return undefined; return presignAndUploadImage(newTemplateSizeChart.value, 'template-size-chart') }
function validateNewTemplate() {
  const sizeOptions = newSkuSizeOptions.value.map(value => value.trim()).filter(Boolean)
  const validations = [
    { valid: /^[A-Z0-9]{1,5}$/.test(newTemplateName.value.trim().toUpperCase()), tab: 'basic' as const, message: '模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字' },
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
async function createTemplate() { if (!editingTemplate.value && !validateNewTemplate()) return; if (editingTemplate.value && !newTemplateName.value.trim()) { templateFormTab.value='basic'; showToast('请输入模板名称'); return } if (editingTemplate.value && [newPackageWeight.value,newPackageLength.value,newPackageWidth.value,newPackageHeight.value].some(value => value === null || value <= 0)) { templateFormTab.value='logistics'; showToast('请完整填写物流信息'); return } const ai_prompts=newTemplateAiPrompts.value.map(item=>({name:item.name.trim(),content:item.content.trim()})).filter(item=>item.name || item.content); if (ai_prompts.some(item=>!item.name || !item.content)) { templateFormTab.value='ai-prompts'; showToast('请完整填写 AI 提示词的名称和内容，或删除空白项'); return } try { templateSaving.value = true; const [uploadedCoverUrl, uploadedSizeChartUrl] = await Promise.all([uploadCover(), uploadSizeChart()]); const cover_url=uploadedCoverUrl ?? editingTemplate.value?.cover_url ?? null; const size_chart_url=uploadedSizeChartUrl ?? editingTemplate.value?.size_chart_url ?? null; const sizeOptions=newSkuSizeOptions.value.map(value=>value.trim()).filter(Boolean); const sku_specifications={size:{name:'尺码',options:sizeOptions}}; const payload={name:newTemplateName.value.trim(),description:newTemplateDescription.value.trim() || null,title_template:newTemplateTitleTemplate.value.trim() || null,product_description:newTemplateProductDescription.value.trim() || null,size_chart_url,group_id:newTemplateGroupId.value,cover_url,package_weight:newPackageWeight.value,package_length:newPackageLength.value,package_width:newPackageWidth.value,package_height:newPackageHeight.value,sku_specifications,ai_prompts,color_count:1,sku_count:Math.max(1,sizeOptions.length)}; if(editingTemplate.value) await api.put(`/templates/${editingTemplate.value.id}`,payload,{headers:headers.value}); else await api.post('/templates',payload,{headers:headers.value}); showTemplateDialog.value=false; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || e?.message || '保存模板失败' } finally { templateSaving.value = false } }
async function deleteTemplate(template:any) { if (!confirm(`确定删除模板「${template.name}」吗？`)) return; try { await api.delete(`/templates/${template.id}`,{headers:headers.value}); if(selectedTemplateId.value===template.id) selectedTemplateId.value=templates.value.find(t=>t.id!==template.id)?.id || null; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || '删除模板失败' } }
function imageUrl(url?: string) { return url ? (url.startsWith('/') ? `${api.defaults.baseURL}${url}` : url) : '' }
const taskStatusLabel: Record<string, string> = { queued: '排队中', running: '处理中', awaiting_selection: '待选图', completed: '已完成', failed: '失败' }
function taskStatusClass(status?: string) { return status === 'awaiting_selection' ? 'purple' : status === 'completed' ? 'blue' : status === 'failed' ? 'orange' : 'purple' }
async function refreshTaskList() {
  try {
    taskListRefreshing.value = true
    const { data } = await api.get('/tasks', { headers: headers.value, params: { page: currentTaskPage.value, page_size: taskPageSize.value, creator_id: taskCreatorFilterId.value } })
    applyTaskPage(data)
    if (showTaskDetailDialog.value && viewingTask.value) viewingTask.value = (await api.get(`/tasks/${viewingTask.value.id}`, { headers: headers.value })).data
  } catch (e: any) { showToast(e.response?.data?.detail || '刷新任务列表失败') }
  finally { taskListRefreshing.value = false }
}
async function copyProviderTaskId(task: any) { if (!task.provider_task_id) return; try { await navigator.clipboard.writeText(task.provider_task_id); showToast('外部任务 ID 已复制') } catch { showToast('复制失败，请手动复制') } }
async function openTaskDetail(task: any) { viewingTask.value = task; showTaskDetailDialog.value = true; taskDetailLoading.value = true; try { viewingTask.value = (await api.get(`/tasks/${task.id}`, { headers: headers.value })).data } catch (e:any) { showToast(e.response?.data?.detail || '加载任务详情失败') } finally { taskDetailLoading.value = false } }
function templateCoverUrl(template?: any) { if (template?.cover_url) return imageUrl(template.cover_url); return template?.name === '白色 T恤正面' ? '/template-white-tshirt-front.png' : '/template-tshirt.svg' }
function hasTemplateCover(template?: any) { return Boolean(template?.cover_url || template?.name === '白色 T恤正面') }
function useTemplate(template:any) { selectedTemplateId.value=template.id; page.value='pod' }
function toggleMaterialAsset(assetId: number) { const asset=materialAssets.value.find(item=>item.id===assetId); if(!asset?.sku){showToast('历史素材没有 SKU，请重新上传或领取');return} selectedMaterialAssetIds.value = selectedMaterialAssetIds.value.includes(assetId) ? selectedMaterialAssetIds.value.filter(id => id !== assetId) : [...selectedMaterialAssetIds.value, assetId] }
function toggleAllCurrentMaterialAssets() { selectedMaterialAssetIds.value = allCurrentMaterialAssetsSelected.value ? [] : filteredMaterialAssets.value.filter(asset=>asset.sku).map(asset => asset.id) }
function materialTemplateName(asset: any) { return templates.value.find(template => template.id === asset.template_id)?.name || '未设置模板' }
function draftTemplateName(draft: any) { return templates.value.find(template => template.id === draft.template_id)?.name || '历史模板已删除' }
function onMaterialDraftTemplateChange() {
  const template = materialDraftTemplate.value
  materialDraftTitle.value = template ? `${template.name} POD 商品` : ''
  materialDraftProductDescription.value = template?.product_description || ''
  materialDraftSizeChartPreview.value = imageUrl(template?.size_chart_url)
}
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
function openMaterialDraftDialog() { if(!selectedMaterialTemplateId.value){showToast('请选择属于同一产品模板的素材');return} materialDraftTemplateId.value = selectedMaterialTemplateId.value; materialDraftTitle.value = ''; materialDraftProductDescription.value = ''; materialDraftSizeChartPreview.value = ''; onMaterialDraftTemplateChange(); showMaterialDraftDialog.value = true }
async function createDraftFromMaterialAssets() {
  if (!selectedMaterialAssetIds.value.length) return
  if (!materialDraftTemplateId.value) { showToast('请选择产品模板'); return }
  if (!materialDraftTitle.value.trim()) { showToast('请生成或填写商品标题'); return }
  try {
    materialDraftSaving.value = true
    const size_chart_url = materialDraftTemplate.value?.size_chart_url ?? null
    const { data: draft } = await api.post('/drafts/from-material-assets', { material_asset_ids: selectedMaterialAssetIds.value, template_id: materialDraftTemplateId.value, title: materialDraftTitle.value.trim(), product_description: materialDraftProductDescription.value.trim() || null, size_chart_url }, { headers: headers.value })
    const { data: publishResult } = await api.post(`/drafts/${draft.id}/claim-to-tiktok`, {}, { headers: headers.value })
    selectedMaterialAssetIds.value = []
    showMaterialDraftDialog.value = false
    await refresh()
    page.value = 'drafts'
    showToast(`已发布公共草稿箱并认领到 TikTok（编号：${publishResult.tiktok_collect_box_detail_id}）`)
  } catch (e:any) {
    showToast(e.response?.data?.detail || '创建、发布或认领 TikTok 失败；草稿已保留，可在商品待发布页重试')
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
  if (draft.tiktok_collect_box_id) return
  try {
    publishingDraftId.value = draft.id
    const { data } = await api.post(`/drafts/${draft.id}/claim-to-tiktok`, {}, { headers: headers.value })
    await refresh()
    showToast(data.already_claimed ? '该商品已认领到 TikTok 采集箱' : `已发布公共草稿箱并认领到 TikTok（编号：${data.tiktok_collect_box_detail_id}）`)
  } catch (e: any) {
    showToast(e.response?.data?.detail || '发布并认领 TikTok 失败，请稍后重试')
  } finally {
    publishingDraftId.value = null
  }
}
async function openClaimMaterialsDialog(task: any) { try { claimingTask.value = (await api.get(`/tasks/${task.id}`, { headers: headers.value })).data; selectedClaimResultUrls.value = []; showClaimMaterialsDialog.value = true } catch (e:any) { showToast(e.response?.data?.detail || '加载任务结果失败') } }
function toggleClaimResult(url: string) { selectedClaimResultUrls.value = selectedClaimResultUrls.value.includes(url) ? selectedClaimResultUrls.value.filter(item => item !== url) : [...selectedClaimResultUrls.value, url] }
async function claimMaterials() {
  if (!claimingTask.value || !selectedClaimResultUrls.value.length) { showToast('请至少选择一张图片'); return }
  try {
    claimingMaterials.value = true
    await api.post(`/tasks/${claimingTask.value.id}/claim-materials`, { result_urls: selectedClaimResultUrls.value }, { headers: headers.value })
    showClaimMaterialsDialog.value = false
    await refresh()
    showToast('领取成功，可在素材库查看')
  } catch(e:any) { showToast(e.response?.data?.detail || '领取素材失败') }
  finally { claimingMaterials.value = false }
}
async function retryTaskResult(task: any) {
  try {
    retryingTaskId.value = task.id
    await api.post(`/tasks/${task.id}/retry`, {}, { headers: headers.value })
    await refreshTaskList()
    showToast('失败任务已重新入队')
  } catch (e: any) { showToast(e.response?.data?.detail || '重试任务失败') }
  finally { retryingTaskId.value = null }
}
function chooseMaterialUploadFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  if (files.length > MATERIAL_UPLOAD_MAX_FILES) { showToast(`单次最多上传 ${MATERIAL_UPLOAD_MAX_FILES} 张图片`); return }
  if (files.some(file => !ALLOWED_IMAGE_TYPES.includes(file.type) || !file.size || file.size > MAX_IMAGE_BYTES)) { showToast('仅支持 JPG、PNG、WebP，且单张不能超过 5MB'); return }
  pendingMaterialUploadFiles.value = files
  pendingMaterialUploadUrls.value = []
  materialUploadTemplateId.value = null
  showMaterialUploadDialog.value = true
}
async function uploadMaterialAssets() {
  const files = [...pendingMaterialUploadFiles.value]
  if (!files.length || !materialUploadTemplateId.value) { showToast('请选择产品模板'); return }
  try {
    materialUploading.value = true
    materialUploadError.value = ''
    materialUploadTotal.value = files.length
    materialUploadedCount.value = 0
    // 已直传成功的图片保留 URL，重试时只补传失败的那几张。
    const missing = files.map((_file, index) => index).filter(index => !pendingMaterialUploadUrls.value[index])
    if (missing.length) {
      const { data: signed } = await api.post('/material-assets/presign', {
        files: missing.map(index => ({ content_type: files[index].type, content_length: files[index].size })),
      }, { headers: headers.value })
      let cursor = 0
      const worker = async () => {
        while (true) {
          const slot = cursor++
          if (slot >= missing.length) return
          const index = missing[slot], file = files[index], target = signed[slot]
          for (let attempt = 0; attempt <= IMAGE_UPLOAD_RETRY && !pendingMaterialUploadUrls.value[index]; attempt++) {
            await axios.put(target.upload_url, file, { headers: { 'Content-Type': file.type } })
              .then(() => { pendingMaterialUploadUrls.value[index] = target.url })
              .catch(() => undefined)
          }
          if (!pendingMaterialUploadUrls.value[index]) throw new Error(`「${file.name}」上传失败`)
          materialUploadedCount.value++
        }
      }
      const results = await Promise.allSettled(Array.from({ length: Math.min(MATERIAL_UPLOAD_CONCURRENCY, missing.length) }, worker))
      const failed = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
      if (failed) throw failed.reason
    }
    await api.post('/material-assets/commit', {
      template_id: materialUploadTemplateId.value,
      items: files.map((file, index) => ({ url: pendingMaterialUploadUrls.value[index], name: file.name })),
    }, { headers: headers.value })
    showMaterialUploadDialog.value = false
    pendingMaterialUploadFiles.value = []
    pendingMaterialUploadUrls.value = []
    currentMaterialPage.value = 1
    await refreshMaterialList()
    showToast(`已上传 ${files.length} 张素材`)
  } catch (e:any) {
    materialUploadError.value = e.response?.data?.detail || e?.message || '上传素材失败，请稍后重试'
  } finally {
    materialUploading.value = false
    materialUploadTotal.value = 0
  }
}
async function deleteSelectedMaterialAssets() {
  const assetIds = [...selectedMaterialAssetIds.value]
  if (!assetIds.length || !confirm(`确定从素材库删除选中的 ${assetIds.length} 张图片吗？`)) return
  try {
    await Promise.all(assetIds.map(assetId => api.delete(`/material-assets/${assetId}`, { headers: headers.value })))
    await refreshMaterialList()
    showToast(`已删除 ${assetIds.length} 张素材`)
  } catch (e: any) {
    await refreshMaterialList()
    showToast(e.response?.data?.detail || '删除素材失败，请稍后重试')
  }
}
function openMemberDialog(member?: any) { editingMember.value=member || null; memberForm.value={name:member?.name || '',user_code:member?.user_code || '',email:member?.email || '',password:'',is_active:member?.is_active ?? true}; memberFormError.value=''; showMemberDialog.value=true }
function openMyAccountDialog() { myName.value=user.value?.name || ''; myUserCode.value=user.value?.user_code || ''; showMyAccountDialog.value=true }
async function saveMyUserCode() { const name=myName.value.trim(), userCode=myUserCode.value.trim(); if (!name) { showToast('请输入管理员名称'); return } if (userCode && [...userCode].length !== 2) { showToast('用户代码必须恰好为两个字符'); return } try { myAccountSaving.value=true; const {data}=await api.patch('/me',{name,user_code:userCode || null},{headers:headers.value}); user.value=data; showMyAccountDialog.value=false; showToast('账户设置已保存') } catch(e:any) { showToast(e.response?.data?.detail || '保存账户设置失败') } finally { myAccountSaving.value=false } }
async function saveMember() {
  const name=memberForm.value.name.trim(), userCode=memberForm.value.user_code.trim(), email=memberForm.value.email.trim()
  memberFormError.value=''
  const invalid=(message:string)=>{ memberFormError.value=message; showToast(message) }
  if (!name) { invalid('请输入姓名'); return }
  if (!userCode) { invalid('请输入用户代码'); return }
  if ([...userCode].length !== 2) { invalid('用户代码必须恰好为两个字符'); return }
  if (!email) { invalid('请输入邮箱'); return }
  if (!memberForm.value.password && !editingMember.value) { invalid('请设置登录密码'); return }
  if (memberForm.value.password && memberForm.value.password.length < 8) { invalid('登录密码至少 8 个字符'); return }
  try { memberSaving.value=true; error.value=''; const payload:any={name,user_code:userCode,email}; if(memberForm.value.password) payload.password=memberForm.value.password; if(editingMember.value) await api.put(`/members/${editingMember.value.id}`,payload,{headers:headers.value}); else await api.post('/members',payload,{headers:headers.value}); showMemberDialog.value=false; await refresh(); showToast('成员已保存') } catch(e:any) { const message=e.response?.data?.detail || '保存成员失败'; memberFormError.value=message; error.value=message; showToast(message) } finally { memberSaving.value=false } }
async function toggleMember(member:any) { try { await api.put(`/members/${member.id}`,{is_active:!member.is_active},{headers:headers.value}); await refresh() } catch(e:any) { error.value=e.response?.data?.detail || '更新成员状态失败' } }
function openMemberCredentialDialog(member:any, provider:any) { credentialMember.value=member; credentialProvider.value=provider; credentialApiKey.value=''; showMemberCredentialDialog.value=true }
function memberCredentialPreview() { return credentialMember.value?.ai_provider_credential_previews?.[credentialProvider.value?.provider] || '' }
async function saveMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !credentialApiKey.value.trim()) { showToast('请输入平台密钥'); return } try { credentialSaving.value=true; await api.put(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`,{api_key:credentialApiKey.value.trim()},{headers:headers.value}); showMemberCredentialDialog.value=false; await refresh(); showToast(`${credentialProvider.value.display_name} 平台密钥已安全保存`) } catch(e:any) { showToast(e.response?.data?.detail || '保存平台密钥失败') } finally { credentialSaving.value=false } }
async function clearMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !confirm(`确定清除 ${credentialMember.value.name} 的 ${credentialProvider.value.display_name} 平台密钥吗？`)) return; try { credentialSaving.value=true; await api.delete(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`,{headers:headers.value}); showMemberCredentialDialog.value=false; await refresh(); showToast('平台密钥已清除') } catch(e:any) { showToast(e.response?.data?.detail || '清除平台密钥失败') } finally { credentialSaving.value=false } }
async function loadMiaoshouShops() { try { shopLoading.value=true; shopError.value=''; await api.post('/miaoshou/shops',{}, {headers:headers.value}); await refresh(); return true } catch(e:any) { shopError.value=e.response?.data?.detail || '获取妙手店铺失败'; return false } finally { shopLoading.value=false } }
function openMiaoshouDialog() { miaoshouForm.value={app_id:'',app_secret:''}; shopError.value=''; showMiaoshouDialog.value=true }
async function saveMiaoshouAccount() {
  const appId=miaoshouForm.value.app_id.trim(), appSecret=miaoshouForm.value.app_secret.trim()
  if (!appId || !appSecret) { showToast('请输入 App ID 和 App Secret'); return }
  try {
    miaoshouSaving.value=true; shopError.value=''
    await api.put('/miaoshou/account',{app_id:appId,app_secret:appSecret},{headers:headers.value})
    if (company.value) company.value.miaoshou_configured=true
    showMiaoshouDialog.value=false
    const synced=await loadMiaoshouShops()
    showToast(synced ? '妙手 API Key 已保存，店铺同步完成' : '妙手 API Key 已保存，请检查同步错误后重试')
  } catch(e:any) { shopError.value=e.response?.data?.detail || '保存妙手 API Key 失败'; showToast(shopError.value) }
  finally { miaoshouSaving.value=false }
}
function openShopManagersDialog(shop:any) { managingShop.value=shop; selectedManagerIds.value=shop.manager_users.map((member:any)=>member.id); showShopManagersDialog.value=true }
async function saveShopManagers() { if (!managingShop.value) return; try { shopManagersSaving.value=true; await api.put(`/shops/${managingShop.value.id}/managers`, {member_ids:selectedManagerIds.value}, {headers:headers.value}); showShopManagersDialog.value=false; await refresh() } catch(e:any) { shopError.value=e.response?.data?.detail || '保存店铺管理人员失败' } finally { shopManagersSaving.value=false } }
let toastTimer: ReturnType<typeof setTimeout> | undefined
function showToast(message: string) { toast.value = message; if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = '' }, 3000) }
function logout(){ localStorage.removeItem('haitoro_token'); token.value=''; user.value=null; taskCreatorFilterId.value=null; materialCreatorFilterId.value=null; draftCreatorFilterId.value=null; creatorFiltersInitialized.value=false }
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
  if (!token.value || !taskActiveCount.value) return
  try { applyTaskPage((await api.get('/tasks', { headers: headers.value, params: { page: currentTaskPage.value, page_size: taskPageSize.value, creator_id: taskCreatorFilterId.value } })).data) } catch { /* 保留上一次任务状态，等待下次轮询。 */ }
}
onMounted(() => {
  if (token.value) refresh().catch(logout)
  taskResultPollingTimer = setInterval(refreshPendingTaskResults, 5000)
})
onUnmounted(() => taskResultPollingTimer && clearInterval(taskResultPollingTimer))
</script>

<template>
  <main v-if="!token" class="login-shell">
    <section class="login-card"><div class="brand-mark">H</div><p class="eyebrow">Haitoro AI POD 工作台</p><h1>欢迎回到 POD 工作台</h1><p>登录后仅可访问所属公司及已授权店铺。</p><label>邮箱<input v-model="email" type="email" /></label><label>密码<input v-model="password" type="password" /></label><button class="primary full" :disabled="loading" @click="login">{{ loading ? '登录中…' : '登录' }}</button><small>演示账号：operator@haitoro-demo.com / ChangeMe123!</small><p v-if="error" class="error">{{ error }}</p></section>
  </main>
  <main v-else class="app-shell">
    <aside><div class="logo"><span>H</span><b>Haitoro AI</b></div><nav><button v-for="item in visibleNav" :key="item.key" :class="{active: page===item.key}" @click="page=item.key"><i>{{item.icon}}</i>{{item.label}}</button></nav></aside>
    <section class="content"><header><div><h1>{{ pageTitle }}</h1></div><div class="context"><button class="member account-button" @click="openMyAccountDialog">{{user?.name}} · {{ user?.role === 'company_admin' ? '管理员' : '运营成员' }}{{user?.user_code ? ` · ${user.user_code}` : ''}}</button><button class="ghost" @click="logout">退出</button></div></header>
      <section v-if="page==='dashboard'" class="page"><div class="hero"><div><p>POD 商品工作台</p><h2>今天要先处理什么？</h2><span>从 AI创作到待发布商品，所有进度都在这里。</span></div><button class="primary" @click="page='pod'">✦ 开始 AI创作</button></div><div class="metrics"><article><span>待领取任务</span><b>{{taskStatusCounts.awaiting_selection || 0}}</b><em>请选择要领取的图片</em></article><article><span>待发布商品</span><b>{{drafts.length}}</b><em>妙手接口待接入</em></article><article><span>素材库</span><b>{{materialTotal}}</b><em>已保存的商品素材</em></article></div><div class="two-col"><section class="panel"><h3>最近任务 <button @click="page='tasks'">查看全部</button></h3><div v-for="task in tasks.slice(0,3)" :key="task.id" class="task-row"><span class="thumb">✦</span><div><strong>AI创作 #{{task.id}}</strong><small>{{task.parameters?.task_type || '替换印花'}} · {{new Date(task.created_at).toLocaleString()}}</small></div><span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span></div><p v-if="!tasks.length" class="empty">暂无 AI 创作任务。</p></section><section class="panel"><h3>快捷操作</h3><button class="quick" @click="page='templates'">▦ 浏览产品模板 <span>→</span></button><button class="quick" @click="page='tasks'">◌ 查看任务中心 <span>→</span></button></section></div></section>
      <section v-else-if="page==='templates'" class="page"><div class="toolbar"><input v-model="templateQuery" placeholder="搜索模板名称"/><div v-if="user?.role==='company_admin'" class="toolbar-actions"><button class="primary" @click="openTemplateDialog()">新增模板</button></div></div><div class="template-layout"><section class="groups"><div class="groups-heading"><h3>模板分类</h3><button v-if="user?.role==='company_admin'" class="add-group" @click="showGroupDialog=true">新增</button></div><button :class="{selected:activeGroupId===null}" @click="activeGroupId=null">全部模板</button><button v-for="group in templateGroups" :key="group.id" :class="{selected:activeGroupId===group.id}" @click="activeGroupId=group.id">{{group.name}}</button></section><section><div class="section-heading"><h2>{{activeGroupId ? templateGroups.find(g=>g.id===activeGroupId)?.name : '全部模板'}}</h2><span>共 {{filteredTemplates.length}} 个模板</span></div><div class="template-grid"><article v-for="t in filteredTemplates" :key="t.id" class="template-card"><div class="template-image" :class="{hasCover: hasTemplateCover(t)}"><img v-if="hasTemplateCover(t)" :src="templateCoverUrl(t)" :alt="t.name"/><span v-else>{{t.name.includes('T恤')?'♧':'♔'}}</span></div><h3>{{t.name}}</h3><p><span class="chip" :class="t.is_platform?'blue':'purple'">{{t.is_platform?'平台模板':'公司私有'}}</span></p><p v-if="t.description" class="template-description">{{t.description}}</p><small>{{t.color_count}} 个颜色 · {{t.sku_count}} 个 SKU</small><div class="template-actions"><button @click="useTemplate(t)">用于 AI创作 →</button><template v-if="!t.is_platform && user?.role==='company_admin'"><button @click="openTemplateDialog(t)">编辑</button><button class="danger" @click="deleteTemplate(t)">删除</button></template></div></article><p v-if="!filteredTemplates.length" class="empty">没有符合条件的模板。</p></div></section></div></section>
      <section v-else-if="page==='pod'" class="page"><div class="mode-tabs"><button>灵感参考</button><button class="active">印花贴合</button><button>创作变体</button></div><section class="pod-panel"><div class="pod-heading personal-resource-heading"><div><h2>印花贴合</h2><p>上传印花素材，选择产品模板和个人白底图，生成 AI 创作效果图。</p></div><div class="personal-resource-actions"><button class="secondary" @click="openPersonalResourcesDialog()">管理白底图与创作要求</button><button v-if="user?.role==='company_admin'" class="secondary" @click="openTeamResourcesDialog">查看成员自定义内容</button></div><label class="requirement-label">创作要求 <b>*</b><span v-if="selectedTemplateAiPrompts().length || personalPrompts.length" class="prompt-picker"><select v-model="creativePromptIndex" @change="applyTemplateAiPrompt"><option value="">选择创作要求</option><optgroup v-if="selectedTemplateAiPrompts().length" label="产品模板创作要求"><option v-for="(prompt,index) in selectedTemplateAiPrompts()" :key="`template-${index}`" :value="`template:${index}`">{{prompt.name}}</option></optgroup><optgroup v-if="personalPrompts.length" label="我的创作要求"><option v-for="prompt in personalPrompts" :key="`personal-${prompt.id}`" :value="`personal:${prompt.id}`">{{prompt.name}}</option></optgroup></select><small>选择后会填充至下方，仍可自行修改。</small></span><textarea v-model="creativeRequirement" maxlength="1000" placeholder="例如：保留花朵细节，色彩清晰自然，印花完整贴合布料"></textarea></label></div><div class="pod-grid"><article><label>创作素材</label><label class="upload floral" :class="{hasAsset:creativeAssets.length, invalid:creativeAssetError}"><input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="onCreativeAssetChange"/><img v-if="creativeAssets.length" :src="creativeAssets[0].preview" alt="印花素材预览"/><template v-else><b>✿</b><span>点击上传印花图</span><small>JPG、PNG、WebP，单张最大 5MB</small></template><button v-if="creativeAssets.length" type="button" class="asset-count" @click.prevent="showCreativeAssetsDialog=true">{{creativeAssets.length}}</button></label><p v-if="creativeAssetError" class="creative-asset-error" role="alert">{{creativeAssetError}}</p><button v-if="creativeAssets.length" class="manage-assets" @click="showCreativeAssetsDialog=true">管理 {{creativeAssets.length}} 张印花图</button></article><article class="white-image-picker"><label>产品模板</label><select v-model="selectedTemplateId" @change="onCreativeTemplateChange"><option v-for="t in templates" :key="t.id" :value="t.id">{{t.name}}</option></select><label class="white-image-label">产品白底图 <b>*</b></label><select v-model="selectedWhiteImageId" :disabled="personalResourcesLoading || !personalWhiteImages.length"><option :value="null">{{personalWhiteImages.length ? '请选择白底图' : '尚未设置白底图'}}</option><option v-for="item in personalWhiteImages" :key="item.id" :value="item.id">{{item.name}}</option></select><div v-if="selectedWhiteImage" class="product-preview template-preview"><img :src="imageUrl(selectedWhiteImage.image_url)" :alt="selectedWhiteImage.name"/></div><div v-else class="white-image-empty"><span>{{personalWhiteImages.length ? '请从上方选择一张白底图' : '尚未设置该模板的白底图，请先设置'}}</span><button v-if="!personalWhiteImages.length" @click="openPersonalResourcesDialog('white-images')">立即设置</button></div></article><article class="settings"><label class="settings-title">创作参数</label><div class="parameter-fields"><label class="parameter-field"><span>AI模型</span><select v-model="creativeProvider" :disabled="!availableAiProviders.length"><option v-if="!availableAiProviders.length" value="">暂无后台已启用的模型</option><option v-for="provider in availableAiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}{{provider.credential_configured ? '' : ' · 未配置密钥'}}</option></select><small v-if="!availableAiProviders.length">请联系超级管理员在后台启用至少一个模型。</small></label><label class="parameter-field"><span>画面比例</span><select v-model="creativeRatio"><option>1:1</option><option>3:4</option></select></label><label class="parameter-field"><span>清晰度</span><select v-model="creativeQuality"><option>1K</option><option>2K</option></select></label></div></article><aside class="estimate"><div v-if="creativeUploading" class="upload-progress"><span>上传中 {{creativeUploadedCount}} / {{creativeAssets.length}}</span><progress :max="creativeAssets.length" :value="creativeUploadedCount"></progress><small>上传完成后将按模型配置创建独立任务；中断后再次提交会续传未完成图片。</small></div><button class="primary full" :disabled="!availableAiProviders.length || creativeUploading || !selectedWhiteImageId || Boolean(creativeCredentialError)" @click="createTask">{{creativeUploading ? `上传中 ${creativeUploadedCount}/${creativeAssets.length}` : '✦ 开始印花贴合'}}</button><p v-if="creativeCredentialError || creativeSubmitError" class="creative-submit-error" role="alert">{{creativeCredentialError || creativeSubmitError}}</p></aside></div></section></section>
      <section v-else-if="page==='tasks'" class="page">
        <div class="section-heading"><div><span>批量操作已拆成独立任务；生成图片需先领取到素材库，再创建商品草稿。</span><label v-if="user?.role==='company_admin'" class="material-template-filter">创作人<select v-model="taskCreatorFilterId" @change="changeTaskCreatorFilter"><option :value="null">全部创作人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div><button class="secondary" :disabled="taskListRefreshing" @click="refreshTaskList">{{taskListRefreshing ? '刷新中…' : '↻ 刷新列表'}}</button></div>
        <section class="draft-table task-table">
          <div class="thead" style="grid-template-columns:.55fr .75fr .8fr .95fr 1.2fr 1.1fr .75fr 1.55fr 1.05fr .75fr 1.3fr 1.9fr"><span>任务编号</span><span>任务类型</span><span>创作素材</span><span>产品模版</span><span>AI模型</span><span>创建时间</span><span>创建人</span><span>外部任务 ID</span><span>状态</span><span>结果</span><span>处理信息</span><span>操作</span></div>
          <div v-for="task in pagedTasks" :key="task.id" class="trow" style="grid-template-columns:.55fr .75fr .8fr .95fr 1.2fr 1.1fr .75fr 1.55fr 1.05fr .75fr 1.3fr 1.9fr"><strong>#{{task.id}}</strong><span>{{task.parameters?.task_type || '替换印花'}}</span><button v-if="task.parameters?.print_url" type="button" class="task-material-thumbnail" title="查看创作素材" aria-label="查看创作素材大图" @click.stop.prevent="openImagePreview(task.parameters.print_url, '创作素材')"><img :src="imageUrl(task.parameters.print_url)" alt="创作素材"/></button><span v-else>—</span><span>{{task.template_name || '—'}}</span><span class="ai-model-cell"><b>{{task.provider === 'grsai' ? 'Grsai' : task.provider || '默认模型'}}</b><small v-if="task.provider_model">{{task.provider_model}}</small></span><span>{{new Date(task.created_at).toLocaleString()}}</span><span>{{task.created_by_name || '历史记录缺失'}}</span><span class="provider-task-id"><code>{{task.provider_task_id || '—'}}</code><button v-if="task.provider_task_id" class="copy-icon-button" title="复制外部任务 ID" aria-label="复制外部任务 ID" @click="copyProviderTaskId(task)">⧉</button></span><span class="task-progress-cell"><span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span><small>{{task.progress?.total_prints || 0}} 张印花 · 已提交 {{task.submit_attempts || 0}} 次</small></span><button v-if="task.result_urls?.[0]" type="button" class="task-material-thumbnail" title="查看结果图" aria-label="查看首张结果图" @click.stop.prevent="openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`)"><img :src="imageUrl(task.result_urls[0])" :alt="`任务 #${task.id} 结果图`"/></button><span v-else>—</span><span :class="{error: task.status==='failed'}">{{task.failure_reason || '—'}}</span><span class="task-actions"><button class="secondary" @click="openTaskDetail(task)">查看详情</button><button v-if="task.status==='failed'" class="secondary" :disabled="retryingTaskId===task.id" @click="retryTaskResult(task)">{{retryingTaskId===task.id ? '重试中…' : '重试任务'}}</button><button v-if="task.result_count || task.result_urls?.length" class="secondary" @click="openClaimMaterialsDialog(task)">领取素材</button></span></div>
          <p v-if="!tasks.length" class="empty">暂无 AI 创作任务。</p><footer v-if="taskTotal" class="draft-pagination"><span>共 {{taskTotal}} 条</span><label>每页 <select v-model.number="taskPageSize" @change="changeTaskPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select> 条</label><button :disabled="visibleTaskPage===1" @click="changeTaskPage(visibleTaskPage-1)">上一页</button><span>第 {{visibleTaskPage}} / {{taskPageCount}} 页</span><button :disabled="visibleTaskPage===taskPageCount" @click="changeTaskPage(visibleTaskPage+1)">下一页</button></footer>
        </section>
      </section>
      <section v-else-if="page==='materials'" class="page">
        <div class="section-heading"><div><span>素材入库后将永久绑定产品模板和 SKU；请选择同一模板的素材创建商品草稿。</span><div class="material-filter-row"><label class="material-template-filter">产品模板<select v-model="materialTemplateFilterId" @change="changeMaterialFilter"><option :value="null">全部模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><label v-if="user?.role==='company_admin'" class="material-template-filter">创作人<select v-model="materialCreatorFilterId" @change="changeMaterialFilter"><option :value="null">全部创作人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div></div><label class="primary material-upload-button" :class="{disabled: materialUploading}"><input type="file" multiple accept="image/png,image/jpeg,image/webp" :disabled="materialUploading" @change="chooseMaterialUploadFiles"/>{{materialUploading ? '上传中…' : '上传本地素材'}}</label></div>
        <p v-if="materialUploadError" class="error material-upload-error">{{materialUploadError}}</p>
        <section v-if="selectedMaterialAssetIds.length" class="material-draft-bar"><strong>已选 {{selectedMaterialAssetIds.length}} 张素材</strong><button class="primary" @click="openMaterialDraftDialog">创建商品草稿</button><button class="negative" @click="deleteSelectedMaterialAssets">删除选中素材</button><button class="ghost" @click="selectedMaterialAssetIds=[]">取消选择</button></section>
        <section class="draft-table material-list">
          <div class="thead material-thead"><label class="material-checkbox material-select-all"><input type="checkbox" :checked="allCurrentMaterialAssetsSelected" :indeterminate="someCurrentMaterialAssetsSelected" :disabled="!filteredMaterialAssets.some(asset=>asset.sku)" aria-label="全选本页可用素材" @change="toggleAllCurrentMaterialAssets"/><span>全选</span></label><span>缩略图</span><span>SKU</span><span>模板</span><span>类型</span><span>创建时间</span><span>创建人</span></div>
          <div v-for="asset in filteredMaterialAssets" :key="asset.id" class="trow material-trow" :class="{selected: selectedMaterialAssetIds.includes(asset.id)}"><label class="material-checkbox" :aria-label="`选择素材 ${asset.name}`"><input type="checkbox" :checked="selectedMaterialAssetIds.includes(asset.id)" :disabled="!asset.sku" @change="toggleMaterialAsset(asset.id)"/></label><button type="button" class="material-list-thumbnail" :title="asset.name" :aria-label="`预览素材 ${asset.name}`" @click="openImagePreview(asset.url, asset.name)"><img :src="imageUrl(asset.url)" :alt="asset.name"/></button><code :class="{error:!asset.sku}">{{asset.sku || '无 SKU，请重新上传或领取'}}</code><span>{{asset.template_name || materialTemplateName(asset)}}</span><span><i class="chip" :class="asset.source_type === 'ai_created' ? 'purple' : 'blue'">{{asset.source_type === 'ai_created' ? 'AI创作' : '本地上传'}}</i><small v-if="asset.source_task_id" class="material-source-task">任务 #{{asset.source_task_id}}</small></span><span>{{new Date(asset.created_at).toLocaleString()}}</span><span>{{asset.created_by_name || '历史记录缺失'}}</span></div>
          <div v-if="!filteredMaterialAssets.length" class="empty">{{materialTotal ? '没有符合筛选条件的素材。' : '暂无素材。可上传本地图片，或在任务中心领取生成图片。'}}</div><footer v-if="materialTotal" class="draft-pagination"><span>共 {{materialTotal}} 条</span><label>每页 <select v-model.number="materialPageSize" @change="changeMaterialPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select> 条</label><button :disabled="visibleMaterialPage===1" @click="changeMaterialPage(visibleMaterialPage-1)">上一页</button><span>第 {{visibleMaterialPage}} / {{materialPageCount}} 页</span><button :disabled="visibleMaterialPage===materialPageCount" @click="changeMaterialPage(visibleMaterialPage+1)">下一页</button></footer>
        </section>
      </section>
      <section v-else-if="page==='drafts'" class="page"><div class="section-heading"><div><span>发布到公共草稿箱后，自动认领到 TikTok 采集箱。</span><div class="material-filter-row"><label class="draft-template-filter">产品模板<select v-model="draftTemplateFilterId" @change="currentDraftPage=1"><option :value="null">全部模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><label v-if="user?.role==='company_admin'" class="draft-template-filter">创作人<select v-model="draftCreatorFilterId" @change="changeDraftCreatorFilter"><option :value="null">全部创作人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div></div><button class="primary" @click="page='materials'">新建商品草稿</button></div><div class="draft-table"><div class="thead draft-thead"><span>商品</span><span>模板</span><span>商品标题</span><span>SKU 数量</span><span>来源任务</span><span>创建时间</span><span>创作人</span><span>更新时间</span><span>最新修改用户</span><span>状态</span><span>操作</span></div><div v-for="draft in pagedDrafts" :key="draft.id" class="trow draft-trow"><button v-if="draft.image_urls?.[0]" class="draft-thumbnail" title="查看大图" @click="openImagePreview(draft.image_urls[0], draft.title)"><img :src="imageUrl(draft.image_urls[0])" :alt="draft.title"/></button><span v-else></span><span>{{draftTemplateName(draft)}}</span><b class="draft-product-title">{{draft.title}}</b><span>{{draft.sku_items?.length || 1}}</span><span>{{draft.source_task_id ? `#${draft.source_task_id}` : '素材库'}}</span><span>{{new Date(draft.created_at).toLocaleString()}}</span><span>{{draft.created_by_name || '历史记录缺失'}}</span><span>{{new Date(draft.updated_at || draft.created_at).toLocaleString()}}</span><span>{{draft.updated_by_name || '历史记录缺失'}}</span><span class="chip" :class="draft.tiktok_collect_box_id ? 'blue' : 'orange'">{{draft.tiktok_collect_box_id ? '已认领到 TikTok' : draft.miaoshou_collect_box_id ? '待认领到 TikTok' : '待发布'}}</span><span><button @click="openDraftEditDialog(draft)">编辑</button> <button v-if="!draft.tiktok_collect_box_id" class="primary compact-action" :disabled="publishingDraftId===draft.id" @click="publishDraftToMiaoshou(draft)">{{publishingDraftId===draft.id ? '处理中…' : '发布并认领 TikTok'}}</button><small v-else>TikTok #{{draft.tiktok_collect_box_id}}</small></span></div><div v-if="!filteredDrafts.length" class="empty">{{drafts.length ? '没有符合筛选条件的商品草稿。' : '暂无商品草稿，请先在任务中心领取素材，或上传本地素材。'}}</div><footer v-else class="draft-pagination"><span>共 {{filteredDrafts.length}} 条</span><label>每页 <select v-model.number="draftPageSize" @change="changeDraftPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option><option :value="500">500</option><option :value="1000">1000</option></select> 条</label><button :disabled="visibleDraftPage===1" @click="currentDraftPage=visibleDraftPage-1">上一页</button><span>第 {{visibleDraftPage}} / {{draftPageCount}} 页</span><button :disabled="visibleDraftPage===draftPageCount" @click="currentDraftPage=visibleDraftPage+1">下一页</button></footer></div></section>
      <section v-else-if="page==='members' && user?.role==='company_admin'" class="page"><div class="section-heading"><div><span>管理本公司成员账号，并为包括公司管理员在内的每位员工配置独立模型平台密钥。</span></div><button class="primary" @click="openMemberDialog()">新增成员</button></div><section class="draft-table"><div class="thead" style="grid-template-columns:1fr .65fr .8fr .9fr .7fr .85fr 1.6fr"><span>成员</span><span>用户代码</span><span>账号类型</span><span>邮箱</span><span>状态</span><span>加入时间</span><span>操作</span></div><div v-for="member in members" :key="member.id" class="trow" style="grid-template-columns:1fr .65fr .8fr .9fr .7fr .85fr 1.6fr"><span><b>{{member.name}}</b></span><span>{{member.user_code || '—'}}</span><span>{{member.role === 'company_admin' ? '公司管理员' : '普通成员'}}</span><span>{{member.email}}</span><span class="chip" :class="member.is_active ? 'blue' : 'orange'">{{member.is_active ? '启用中' : '已停用'}}</span><span>{{new Date(member.created_at).toLocaleDateString()}}</span><span class="member-row-actions"><template v-if="member.role === 'member'"><button @click="openMemberDialog(member)">编辑</button><button :class="member.is_active ? 'negative' : 'positive'" @click="toggleMember(member)">{{member.is_active ? '停用' : '启用'}}</button></template><button v-for="provider in aiProviders" :key="provider.provider" class="credential-button" :class="member.ai_provider_credentials?.[provider.provider] ? 'configured' : 'missing'" @click="openMemberCredentialDialog(member, provider)">{{provider.display_name}} 密钥 · {{member.ai_provider_credentials?.[provider.provider] ? '已配置' : '待配置'}}</button></span></div><p v-if="!members.length" class="empty">暂无公司成员。</p></section></section>
      <section v-else-if="page==='shops' && user?.role==='company_admin'" class="page"><div class="section-heading"><div><span>已同步的妙手店铺会保存在数据库中，可为每个店铺分配多个普通成员。</span><span class="miaoshou-status" :class="company?.miaoshou_configured?'configured':'missing'">{{company?.miaoshou_configured?'妙手 API Key 已配置':'请先配置妙手 API Key'}}</span></div><div class="shop-actions"><button class="secondary" :disabled="miaoshouSaving || shopLoading" @click="openMiaoshouDialog">{{company?.miaoshou_configured?'更新 API Key':'配置 API Key'}}</button><button class="primary" :disabled="shopLoading || miaoshouSaving || !company?.miaoshou_configured" @click="loadMiaoshouShops">{{shopLoading ? '同步中…' : '↻ 同步妙手店铺'}}</button></div></div><p v-if="shopError" class="error">{{shopError}}</p><section class="draft-table"><div class="thead" style="grid-template-columns:.65fr 1.2fr 1fr .75fr .7fr .9fr .9fr 1.3fr .75fr"><span>店铺 ID</span><span>店铺名称</span><span>店铺昵称</span><span>平台</span><span>站点</span><span>授权状态</span><span>授权到期</span><span>管理人员</span><span>操作</span></div><div v-for="shop in managedShops" :key="shop.id" class="trow" style="grid-template-columns:.65fr 1.2fr 1fr .75fr .7fr .9fr .9fr 1.3fr .75fr"><span>#{{shop.external_shop_id || shop.id}}</span><span><b>{{shop.name || '—'}}</b></span><span>{{shop.nickname || '—'}}</span><span>{{shop.platform || '—'}}</span><span>{{shop.region || '—'}}</span><span class="chip" :class="shop.auth_status ? 'blue' : 'orange'">{{shop.auth_status || '未知'}}</span><span>{{shop.auth_expires_at || '—'}}</span><span>{{shop.manager_users.length ? shop.manager_users.map((member:any)=>member.name).join('、') : '暂未分配'}}</span><span><button @click="openShopManagersDialog(shop)">分配人员</button></span></div><p v-if="!managedShops.length && !shopLoading" class="empty">{{company?.miaoshou_configured?'暂无已同步店铺，点击“同步妙手店铺”开始获取。':'配置妙手 API Key 后即可同步店铺。'}}</p></section></section>
    </section>
  </main>
  <div v-if="showClaimMaterialsDialog" class="modal-backdrop" @click.self="showClaimMaterialsDialog=false"><section class="modal-card material-draft-dialog claim-materials-dialog"><button class="modal-close" @click="showClaimMaterialsDialog=false">×</button><h2>领取素材</h2><p>请选择要领取到素材库的图片。</p><div class="material-grid claim-result-grid"><button v-for="url in claimingTask?.result_urls || []" :key="url" class="material-card" :class="{selected:selectedClaimResultUrls.includes(url)}" @click="toggleClaimResult(url)"><span class="material-select-mark">{{selectedClaimResultUrls.includes(url) ? '✓' : ''}}</span><img :src="imageUrl(url)" alt="生成结果图"/></button></div><p v-if="!(claimingTask?.result_urls?.length)" class="empty">暂无可领取图片。</p><div class="modal-actions"><button class="ghost" @click="showClaimMaterialsDialog=false">取消</button><button class="primary" :disabled="claimingMaterials || !selectedClaimResultUrls.length" @click="claimMaterials">{{claimingMaterials ? '领取中…' : '领取'}}</button></div></section></div>
  <div v-if="showTaskDetailDialog" class="modal-backdrop" @click.self="showTaskDetailDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showTaskDetailDialog=false">×</button><h2>任务详情 #{{viewingTask?.id}}</h2><p>{{viewingTask?.parameters?.task_type || '替换印花'}} · {{viewingTask?.template_name || '历史模板已删除'}}</p><section class="draft-edit-section"><strong>印花图</strong><div class="material-draft-preview-images"><button v-for="url in viewingTask?.parameters?.print_urls || []" :key="url" @click="openImagePreview(url, '印花图')"><img :src="imageUrl(url)" alt="印花图"/></button><p v-if="!(viewingTask?.parameters?.print_urls?.length)">未保留印花图。</p></div></section><section v-if="viewingTask?.parameters?.white_image_url" class="draft-edit-section"><strong>产品白底图</strong><button class="task-material-thumbnail" @click="openImagePreview(viewingTask.parameters.white_image_url, viewingTask.parameters.white_image_name || '产品白底图')"><img :src="imageUrl(viewingTask.parameters.white_image_url)" :alt="viewingTask.parameters.white_image_name || '产品白底图'"/></button></section><section class="draft-edit-section"><strong>创作参数</strong><p>画面比例：{{viewingTask?.parameters?.ratio || '—'}} · 清晰度：{{viewingTask?.parameters?.quality || '—'}}</p><p>创作要求：{{viewingTask?.parameters?.private_creative_configuration ? '个人创作配置已隐藏' : viewingTask?.parameters?.creative_requirement || '未填写'}}</p></section><section class="draft-edit-section"><strong>任务信息</strong><p>模型：{{viewingTask?.provider === 'grsai' ? 'Grsai' : viewingTask?.provider || '默认模型'}} <span v-if="viewingTask?.provider_model">· {{viewingTask.provider_model}}</span></p><p>状态：<span class="chip" :class="taskStatusClass(viewingTask?.status)">{{taskStatusLabel[viewingTask?.status] || viewingTask?.status || '—'}}</span> · {{viewingTask?.parameters?.print_urls?.length || 0}} 张印花 · 已提交 {{viewingTask?.submit_attempts || 0}} 次</p><p>外部任务 ID：<code>{{viewingTask?.provider_task_id || '—'}}</code></p><p v-if="viewingTask?.failure_reason" :class="{error:viewingTask?.status==='failed'}">处理信息：{{viewingTask.failure_reason}}</p></section><section v-if="viewingTask?.result_map?.length" class="draft-edit-section"><strong>结果映射</strong><div class="task-result-map"><article v-for="item in viewingTask.result_map" :key="item.print_url"><button class="task-material-thumbnail" @click="openImagePreview(item.print_url, '印花图')"><img :src="imageUrl(item.print_url)" alt="印花图"/></button><small>{{item.result_urls?.length || 0}} 张生成结果</small><div class="material-draft-preview-images"><button v-for="url in item.result_urls || []" :key="url" @click="openImagePreview(url, '生成结果')"><img :src="imageUrl(url)" alt="生成结果"/></button></div></article></div></section><div class="modal-actions"><button class="primary" @click="showTaskDetailDialog=false">关闭</button></div></section></div>
  <div v-if="showCreativeAssetsDialog" class="modal-backdrop" @click.self="showCreativeAssetsDialog=false"><section class="modal-card asset-dialog"><button class="modal-close" @click="showCreativeAssetsDialog=false">×</button><h2>印花图素材</h2><div class="asset-summary"><span>共 {{creativeAssets.length}} 项，已直传 {{creativeAssets.filter(asset=>asset.uploadedUrl).length}} 项</span><label class="add-assets">＋ 继续上传<input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="onCreativeAssetChange"/></label></div><div class="asset-dialog-heading"><div><h3>印花图</h3><span>{{creativeAssets.length}} / 500</span></div><button @click="clearCreativeAssets">清空</button></div><p class="asset-status">最多 500 张，直传中断后再次提交会继续未完成项。</p><div class="asset-list"><article v-for="asset in creativeAssets" :key="asset.id" class="asset-row"><img :src="asset.preview" :alt="asset.file.name"/><div><strong>{{asset.file.name}}</strong><p><span>{{asset.uploadedUrl ? '已直传' : '待上传'}}</span>{{(asset.file.size / 1024).toFixed(1)}}KB</p></div><button class="asset-delete" title="删除" @click="removeCreativeAsset(asset.id)">×</button></article><p v-if="!creativeAssets.length" class="asset-empty">暂未上传印花图。</p></div></section></div>
  <div v-if="showPersonalResourcesDialog" class="modal-backdrop" @click.self="showPersonalResourcesDialog=false">
    <section class="modal-card personal-resources-dialog">
      <button class="modal-close" @click="showPersonalResourcesDialog=false">×</button>
      <h2>管理白底图与创作要求</h2>
      <p>仅管理您自己的内容；新增时请选择内容所属的产品模板。</p>
      <nav class="resource-tabs"><button :class="{active:personalResourceTab==='white-images'}" @click="personalResourceTab='white-images'">白底图</button><button :class="{active:personalResourceTab==='prompts'}" @click="personalResourceTab='prompts'">创作要求</button></nav>
      <div v-if="personalResourceTab==='white-images'" class="resource-pane">
        <form class="resource-editor" @submit.prevent="saveWhiteImage"><h3>{{editingWhiteImage?'编辑白底图':'新增白底图'}}</h3><label>产品模板 <b>*</b><select v-model="whiteImageForm.template_id" :disabled="Boolean(editingWhiteImage)"><option :value="null" disabled>请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select><small v-if="editingWhiteImage">编辑时不可更改所属模板</small></label><label>名称<input v-model="whiteImageForm.name" maxlength="80" placeholder="例如：正面白底图"/></label><label>图片<input type="file" accept="image/png,image/jpeg,image/webp" @change="onWhiteImageFileChange"/><small>{{editingWhiteImage?'不重新选择则保留当前图片':'JPG、PNG、WebP，最大 5MB'}}</small></label><div><button v-if="editingWhiteImage" type="button" class="ghost" @click="resetWhiteImageForm">取消编辑</button><button class="primary" :disabled="personalResourceSaving">{{personalResourceSaving?'保存中…':'保存白底图'}}</button></div></form>
        <div class="resource-list"><article v-for="item in managedWhiteImages" :key="item.id"><img :src="imageUrl(item.image_url)" :alt="item.name"/><div><strong>{{item.name}}</strong><small>{{resourceTemplateName(item)}} · {{new Date(item.updated_at).toLocaleString()}}</small></div><button @click="editWhiteImage(item)">编辑</button><button class="danger" @click="deleteWhiteImage(item)">删除</button></article><p v-if="!managedWhiteImages.length" class="empty">您尚未设置白底图。</p></div>
      </div>
      <div v-else class="resource-pane">
        <form class="resource-editor" @submit.prevent="savePersonalPrompt"><h3>{{editingPersonalPrompt?'编辑创作要求':'新增创作要求'}}</h3><label>产品模板 <b>*</b><select v-model="personalPromptForm.template_id" :disabled="Boolean(editingPersonalPrompt)"><option :value="null" disabled>请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select><small v-if="editingPersonalPrompt">编辑时不可更改所属模板</small></label><label>名称<input v-model="personalPromptForm.name" maxlength="80" placeholder="例如：自然布料贴合"/></label><label>创作要求<textarea v-model="personalPromptForm.content" maxlength="1000" placeholder="描述印花贴合方式、细节和光影"></textarea></label><div><button v-if="editingPersonalPrompt" type="button" class="ghost" @click="resetPersonalPromptForm">取消编辑</button><button class="primary" :disabled="personalResourceSaving">{{personalResourceSaving?'保存中…':'保存创作要求'}}</button></div></form>
        <div class="resource-list prompt-resource-list"><article v-for="item in managedPrompts" :key="item.id"><div><strong>{{item.name}}</strong><small>{{resourceTemplateName(item)}}</small><p>{{item.content}}</p></div><button @click="editPersonalPrompt(item)">编辑</button><button class="danger" @click="deletePersonalPrompt(item)">删除</button></article><p v-if="!managedPrompts.length" class="empty">您尚未保存个人创作要求。</p></div>
      </div>
    </section>
  </div>
  <div v-if="showTeamResourcesDialog" class="modal-backdrop" @click.self="showTeamResourcesDialog=false">
    <section class="modal-card personal-resources-dialog team-resources-dialog">
      <button class="modal-close" @click="showTeamResourcesDialog=false">×</button>
      <h2>查看成员自定义内容</h2>
      <p>按成员和产品模板筛选自定义内容，此处仅供查看。</p>
      <div v-if="otherResourceOwners.length" class="team-resource-filters">
        <label class="resource-owner-picker">成员<select v-model="teamResourceUserId" @change="teamResourceQuery='';loadTeamTemplateResources()"><option v-for="owner in otherResourceOwners" :key="owner.id" :value="owner.id">{{owner.name}} · {{owner.email}}</option></select></label>
        <label class="resource-owner-picker">产品模板<select v-model="teamResourceTemplateId" @change="teamResourceQuery='';loadTeamTemplateResources()"><option :value="null">全部模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label>
        <label class="resource-query-picker">搜索<input v-model="teamResourceQuery" placeholder="搜索名称或创作要求"/></label>
      </div>
      <nav v-if="otherResourceOwners.length" class="resource-tabs"><button :class="{active:teamResourceTab==='white-images'}" @click="teamResourceTab='white-images'">白底图（{{teamWhiteImages.length}}）</button><button :class="{active:teamResourceTab==='prompts'}" @click="teamResourceTab='prompts'">创作要求（{{teamPrompts.length}}）</button></nav>
      <p v-if="teamResourcesLoading" class="empty">正在加载成员内容…</p>
      <div v-else-if="otherResourceOwners.length && teamResourceTab==='white-images'" class="resource-list team-resource-list"><article v-for="item in filteredTeamWhiteImages" :key="item.id"><button class="team-white-image" title="查看大图" @click="openImagePreview(item.image_url,item.name)"><img :src="imageUrl(item.image_url)" :alt="item.name"/></button><div><strong>{{item.name}}</strong><small>{{resourceTemplateName(item)}} · {{new Date(item.updated_at).toLocaleString()}}</small></div></article><p v-if="!filteredTeamWhiteImages.length" class="empty">没有符合条件的白底图。</p></div>
      <div v-else-if="otherResourceOwners.length" class="resource-list prompt-resource-list team-resource-list"><article v-for="item in filteredTeamPrompts" :key="item.id"><div><strong>{{item.name}}</strong><small>{{resourceTemplateName(item)}} · {{new Date(item.updated_at).toLocaleString()}}</small><p>{{item.content}}</p></div></article><p v-if="!filteredTeamPrompts.length" class="empty">没有符合条件的创作要求。</p></div>
      <p v-else class="empty">暂无其他成员可供查看。</p>
    </section>
  </div>
  <div v-if="showMyAccountDialog" class="modal-backdrop" @click.self="showMyAccountDialog=false"><section class="modal-card"><h2>账号设置</h2><p>可修改当前管理员名称和用户代码；用户代码留空可清除，且在本公司内不可重复。</p><label>管理员名称<input v-model="myName" maxlength="80" placeholder="请输入管理员名称" /></label><label>用户代码 <small>（两个字符）</small><input v-model="myUserCode" maxlength="2" placeholder="例如：CN" /></label><div class="modal-actions"><button class="ghost" @click="showMyAccountDialog=false">取消</button><button class="primary" :disabled="myAccountSaving" @click="saveMyUserCode">{{myAccountSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showMaterialDraftDialog" class="modal-backdrop" @click.self="showMaterialDraftDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showMaterialDraftDialog=false">×</button><h2>创建商品草稿</h2><p>将使用已选的 {{selectedMaterialAssetIds.length}} 张素材创建商品草稿。</p><label>产品模板<input :value="materialDraftTemplate?.name || '—'" readonly/></label><section class="material-draft-preview"><div class="material-draft-preview-heading"><strong>图片预览</strong><span>{{selectedMaterialAssets.length}} 张</span></div><div class="material-draft-preview-images"><img v-for="asset in selectedMaterialAssets" :key="asset.id" :src="imageUrl(asset.url)" :alt="asset.name"/></div></section><section v-if="materialDraftTemplate" class="material-draft-details"><label>商品标题<div class="material-draft-title-row"><input v-model="materialDraftTitle" maxlength="180" placeholder="请生成或填写商品标题"/><button class="secondary" :disabled="materialDraftTitleGenerating" @click="generateMaterialDraftTitle">{{materialDraftTitleGenerating ? '生成中…' : 'AI 生成标题'}}</button></div><small>将使用此模版的 AI生成标题约束和首张素材图生成标题。</small></label><label>产品描述<textarea v-model="materialDraftProductDescription" maxlength="5000" placeholder="默认使用产品模版描述，可按商品修改"></textarea></label></section><section v-if="materialDraftTemplate" class="material-draft-sku-summary"><strong>基础 SKU 列表</strong><p>直接使用素材入库时生成的永久 SKU；发布妙手时会拼接模板尺码：{{materialDraftSizes.length ? materialDraftSizes.join('、') : '默认规格'}}。</p><b>共 {{materialDraftSkuCount}} 个基础 SKU</b><small>格式：模板名称 + 用户代码 + 6 位随机字符串</small><div class="material-draft-sku-list"><div v-for="asset in selectedMaterialAssets" :key="asset.id"><span>图片 SKU</span><code>{{asset.sku}}</code></div></div><label class="material-draft-size-chart">尺码图<small>直接使用产品模版的尺码图；如需更换，请到产品模版中修改。</small><img v-if="materialDraftSizeChartPreview" :src="materialDraftSizeChartPreview" alt="尺码图预览"/><small v-else>该产品模版尚未上传尺码图</small></label></section><div class="modal-actions"><button class="ghost" @click="showMaterialDraftDialog=false">取消</button><button class="primary" :disabled="materialDraftSaving" @click="createDraftFromMaterialAssets">{{materialDraftSaving ? '创建中…' : '确认创建'}}</button></div></section></div>
  <div v-if="showDraftEditDialog" class="modal-backdrop" @click.self="showDraftEditDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showDraftEditDialog=false">×</button><h2>编辑商品草稿</h2><p>可修改商品标题和产品描述。</p><label>产品标题<input v-model="draftEditTitle" maxlength="180" placeholder="请输入商品标题"/></label><label>产品描述<textarea v-model="draftEditProductDescription" class="draft-edit-description" maxlength="5000" placeholder="请输入产品描述"></textarea></label><section class="draft-edit-section"><strong>产品图片</strong><div class="draft-edit-preview"><div v-for="url in editingDraft?.image_urls" :key="url" class="draft-edit-image-item"><code>{{draftSkuForImage(editingDraft, url)}}</code><button title="放大查看" @click="openImagePreview(url, editingDraft?.title || '商品素材')"><img :src="imageUrl(url)" :alt="editingDraft?.title || '商品素材'"/></button></div></div></section><section v-if="editingDraft?.size_chart_url" class="draft-edit-section"><strong>尺码图</strong><button class="draft-edit-size-chart-button" title="放大查看" @click="openImagePreview(editingDraft.size_chart_url, '尺码图')"><img class="draft-edit-size-chart" :src="imageUrl(editingDraft.size_chart_url)" alt="尺码图"/></button></section><p v-if="draftEditError" class="error material-draft-error">{{draftEditError}}</p><div class="modal-actions"><button class="ghost" @click="showDraftEditDialog=false">取消</button><button class="primary" :disabled="draftEditSaving" @click="saveDraftEdit">{{draftEditSaving ? '保存中…' : '保存修改'}}</button></div></section></div>
  <div v-if="showGroupDialog" class="modal-backdrop" @click.self="showGroupDialog=false">
    <section v-if="showGroupDialog" class="modal-card"><h2>新增模板分类</h2><label>分类名称<input v-model="newGroupName" placeholder="例如：夏季服装" @keyup.enter="createGroup" /></label><div class="modal-actions"><button class="ghost" @click="showGroupDialog=false">取消</button><button class="primary" @click="createGroup">确认新增</button></div></section>
  </div>
  <div v-if="showMemberDialog" class="modal-backdrop" @click.self="showMemberDialog=false"><section class="modal-card"><h2>{{editingMember ? '编辑成员' : '新增成员'}}</h2><p>{{editingMember ? '姓名、用户代码、邮箱为必填项；留空密码即可保持原密码不变。' : '姓名、用户代码、邮箱为必填项；新成员将作为普通成员加入当前公司。'}}</p><label>姓名 <b class="required">*</b><input v-model="memberForm.name" maxlength="80" placeholder="请输入姓名" /></label><label>用户代码 <b class="required">*</b><input v-model="memberForm.user_code" maxlength="2" placeholder="例如：CN（两个字符）" /></label><label>邮箱 <b class="required">*</b><input v-model="memberForm.email" type="email" placeholder="name@example.com" /></label><label>登录密码<input v-model="memberForm.password" type="password" minlength="8" :placeholder="editingMember ? '留空则不修改' : '至少 8 个字符'" /></label><p v-if="memberFormError" class="error modal-error">{{memberFormError}}</p><div class="modal-actions"><button class="ghost" @click="showMemberDialog=false">取消</button><button class="primary" :disabled="memberSaving" @click="saveMember">{{memberSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showMemberCredentialDialog" class="modal-backdrop" @click.self="showMemberCredentialDialog=false"><section class="modal-card"><h2>配置 {{credentialProvider?.display_name}} 平台密钥</h2><p>{{credentialMember?.name}} 将在创建和查询 AI 任务时使用自己的密钥。密钥会加密保存，前端仅显示脱敏预览。</p><p v-if="memberCredentialPreview()" class="credential-preview">当前密钥：<code>{{memberCredentialPreview()}}</code></p><label>API Key<input v-model="credentialApiKey" type="password" maxlength="2000" autocomplete="new-password" :placeholder="memberCredentialPreview() ? '输入新密钥以替换当前配置' : '请输入新的平台密钥'" @keyup.enter="saveMemberCredential" /></label><div class="modal-actions credential-modal-actions"><button v-if="credentialMember?.ai_provider_credentials?.[credentialProvider?.provider]" class="negative" :disabled="credentialSaving" @click="clearMemberCredential">清除密钥</button><span></span><button class="ghost" :disabled="credentialSaving" @click="showMemberCredentialDialog=false">取消</button><button class="primary" :disabled="credentialSaving || !credentialApiKey.trim()" @click="saveMemberCredential">{{credentialSaving ? '保存中…' : '安全保存'}}</button></div></section></div>
  <div v-if="showMiaoshouDialog" class="modal-backdrop" @click.self="showMiaoshouDialog=false"><section class="modal-card"><h2>{{company?.miaoshou_configured?'更新':'配置'}}妙手 API Key</h2><p>App ID 和 App Secret 会加密保存，仅用于本公司的店铺同步与商品上架。保存后将立即重新同步店铺。</p><label>App ID<input v-model="miaoshouForm.app_id" maxlength="255" autocomplete="off" placeholder="请输入 App ID" /></label><label>App Secret<input v-model="miaoshouForm.app_secret" type="password" maxlength="500" autocomplete="new-password" placeholder="请输入 App Secret" @keyup.enter="saveMiaoshouAccount" /></label><div class="modal-actions"><button class="ghost" :disabled="miaoshouSaving" @click="showMiaoshouDialog=false">取消</button><button class="primary" :disabled="miaoshouSaving || !miaoshouForm.app_id.trim() || !miaoshouForm.app_secret.trim()" @click="saveMiaoshouAccount">{{miaoshouSaving?'保存中…':'保存并同步'}}</button></div></section></div>
  <div v-if="showShopManagersDialog" class="modal-backdrop" @click.self="showShopManagersDialog=false"><section class="modal-card"><h2>分配店铺管理人员</h2><p>{{managingShop?.name}}。被选中的普通成员可在该店铺创建、管理并上架商品。</p><label v-for="member in members.filter(item => item.role === 'member')" :key="member.id" class="manager-option"><input v-model="selectedManagerIds" :value="member.id" type="checkbox" />{{member.name}} <small>{{member.email}}</small></label><p v-if="!members.some(item => item.role === 'member')" class="empty">请先在成员管理中新增普通成员。</p><div class="modal-actions"><button class="ghost" @click="showShopManagersDialog=false">取消</button><button class="primary" :disabled="shopManagersSaving" @click="saveShopManagers">{{shopManagersSaving ? '保存中…' : '保存分配'}}</button></div></section></div>
  <div v-if="showTemplateDialog" class="drawer-backdrop"><section class="template-drawer"><header><div><h2>{{editingTemplate ? '编辑产品模板' : '新增产品模板'}}</h2><p>完善模板信息后可直接用于 AI 创作。</p></div><button class="drawer-close" aria-label="关闭" :disabled="templateSaving" @click="showTemplateDialog=false">×</button></header><nav class="drawer-tabs"><button :class="{active:templateFormTab==='basic'}" @click="templateFormTab='basic'">模版信息</button><button :class="{active:templateFormTab==='product'}" @click="templateFormTab='product'">商品信息</button><button :class="{active:templateFormTab==='sku'}" @click="templateFormTab='sku'">SKU</button><button :class="{active:templateFormTab==='logistics'}" @click="templateFormTab='logistics'">物流信息</button><button :class="{active:templateFormTab==='ai-prompts'}" @click="templateFormTab='ai-prompts'">AI提示词</button></nav><div class="drawer-content"><div v-if="templateFormTab==='basic'" class="drawer-form"><label>模板名称<span>*</span><input v-model="newTemplateName" placeholder="例如：宽松短袖上衣" /></label><label>模板图片<span>*</span><input accept="image/png,image/jpeg,image/webp" type="file" @change="onCoverChange" /><small>{{newTemplateImage ? newTemplateImage.name : editingTemplate?.cover_url ? '保留当前图片' : '支持 JPG、PNG、WebP，最大 5MB'}}</small><div v-if="newTemplateImagePreview" class="template-upload-preview"><img :src="newTemplateImagePreview" alt="模板图片预览" /></div></label><label>模板描述<span>*</span><textarea v-model="newTemplateDescription" maxlength="500" placeholder="描述产品材质、版型和适用的印花区域"></textarea></label><label>模板分类<span>*</span><select v-model="newTemplateGroupId"><option :value="null" disabled>请选择模板分类</option><option v-for="group in templateGroups" :key="group.id" :value="group.id">{{group.name}}</option></select></label></div><div v-else-if="templateFormTab==='product'" class="drawer-form product-info-form"><label>AI生成标题约束<span>*</span><input v-model="newTemplateTitleTemplate" maxlength="500" placeholder="例如：突出材质、款式与适用场景，不包含夸大宣传" /></label><label>产品描述<span>*</span><textarea v-model="newTemplateProductDescription" maxlength="5000" placeholder="填写商品详情页的产品描述"></textarea></label><label>尺码图<span>*</span><input accept="image/png,image/jpeg,image/webp" type="file" @change="onSizeChartChange" /><small>{{newTemplateSizeChart ? newTemplateSizeChart.name : editingTemplate?.size_chart_url ? '保留当前尺码图' : '支持 JPG、PNG、WebP，最多上传 1 张，最大 5MB'}}</small><div v-if="newTemplateSizeChartPreview" class="template-upload-preview"><img :src="newTemplateSizeChartPreview" alt="尺码图预览" /></div></label></div><div v-else-if="templateFormTab==='sku'" class="sku-form"><section><strong><b>*</b> 尺码</strong><div class="sku-size-grid"><div v-for="(_, index) in newSkuSizeOptions" :key="index" class="sku-size-row"><input v-model="newSkuSizeOptions[index]" maxlength="50" placeholder="例如：M"/><small>{{newSkuSizeOptions[index].length}} / 50</small><button title="删除尺码" @click="newSkuSizeOptions.splice(index,1)">×</button></div></div><button class="sku-add-option" @click="addSkuSize">＋ 添加选项</button></section><small class="sku-total">预计生成 {{Math.max(1,newSkuSizeOptions.filter(value=>value.trim()).length)}} 个 SKU</small></div><div v-else-if="templateFormTab==='ai-prompts'" class="drawer-form ai-prompts-form"><div><h3>AI 提示词</h3><p>为印花贴合保存可复用的创作要求；在 AI 创作页选择模板后可一键填充并继续修改。</p></div><section v-for="(prompt, index) in newTemplateAiPrompts" :key="index" class="ai-prompt-editor"><div><b>提示词 {{index + 1}}</b><button type="button" class="danger" @click="removeTemplateAiPrompt(index)">删除</button></div><label>名称<input v-model="prompt.name" maxlength="80" placeholder="例如：自然布料贴合" /></label><label>提示词内容<textarea v-model="prompt.content" maxlength="1000" placeholder="描述印花贴合方式、细节、光影等创作要求"></textarea></label></section><button type="button" class="secondary ai-prompt-add" @click="addTemplateAiPrompt">＋ 新增提示词</button></div><div v-else class="drawer-form logistics-form"><h3>物流信息 <span title="用于运费及配送计算">?</span></h3><label><b>*</b> 包裹重量<div class="unit-input"><input v-model.number="newPackageWeight" type="number" min="0.001" step="0.001" placeholder="请输入重量" /><span>KG</span></div></label><label><b>*</b> 包裹尺寸<div class="dimension-inputs"><label><input v-model.number="newPackageLength" type="number" min="0.1" step="0.1" placeholder="长" /><span>cm</span></label><label><input v-model.number="newPackageWidth" type="number" min="0.1" step="0.1" placeholder="宽" /><span>cm</span></label><label><input v-model.number="newPackageHeight" type="number" min="0.1" step="0.1" placeholder="高" /><span>cm</span></label></div></label></div></div><footer><button class="ghost" :disabled="templateSaving" @click="showTemplateDialog=false">取消</button><button class="primary" :disabled="templateSaving" @click="createTemplate">{{templateSaving ? '上传中…' : (editingTemplate ? '保存修改' : '确认新增')}}</button></footer></section></div>
  <div v-if="previewImageUrl" class="image-preview-backdrop" @click.self="previewImageUrl=''"><section class="image-preview-modal"><button class="modal-close" aria-label="关闭大图" @click="previewImageUrl=''">×</button><img :src="previewImageUrl" :alt="previewImageAlt"/></section></div>
  <div v-if="toast" class="toast" role="alert" style="position:fixed;top:24px;left:50%;z-index:1000;transform:translateX(-50%);padding:12px 18px;border-radius:10px;background:#302954;color:#fff;box-shadow:0 10px 28px #30295440;font-size:14px">{{ toast }}</div>
  <div v-if="showMaterialUploadDialog" class="modal-backdrop" @click.self="showMaterialUploadDialog=false"><section class="modal-card material-template-dialog"><button class="modal-close" @click="showMaterialUploadDialog=false">×</button><h2>上传本地素材</h2><p>已选择 {{pendingMaterialUploadFiles.length}} 张图片，请先选择产品模板。</p><p v-if="materialUploading" style="margin:-10px 0 16px;color:#5545ca">正在上传 {{materialUploadedCount}} / {{materialUploadTotal}}…</p><label>产品模板<select v-model="materialUploadTemplateId" :disabled="materialUploading"><option :value="null" disabled>请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><p v-if="materialUploadError" style="margin:14px 0 0;color:#d34b5f">{{materialUploadError}}</p><div class="modal-actions"><button class="ghost" :disabled="materialUploading" @click="showMaterialUploadDialog=false">取消</button><button class="primary" :disabled="materialUploading" @click="uploadMaterialAssets">{{materialUploading ? '上传中…' : '确认上传'}}</button></div></section></div>
</template>
