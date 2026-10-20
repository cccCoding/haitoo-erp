<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import SearchableSelect from './SearchableSelect.vue'
import ShopDataHeading from './ShopDataHeading.vue'
import CrossCompanyCollection from './CrossCompanyCollection.vue'
import MaterialTransferDialog from './MaterialTransferDialog.vue'
import InfringementToggle from './InfringementToggle.vue'
import InfringementBadge from './InfringementBadge.vue'
import InfringementActions from './InfringementActions.vue'
import StyleSelect from './StyleSelect.vue'
import { applySelectedStyle, commonStyleTemplate, styleOptions, type MaterialStyle } from './material-styles'
import { deduplicatedImageUpload, imageSha256, transferItem, type MaterialTransferItem } from './material-transfer'
import { dialogFocus as vDialogFocus } from './dialog-focus'
import { batchTitleRequest, createBatchTitleGenerator, emptyTitleGenerationProgress, hasValidBatchTitles, isUnfinishedTitle, titleGenerationStatusLabels, type BatchTitleGroup } from './batch-title-generation'

const pageSizeOptions = [20, 50, 100, 500, 1000]
const SupplyCatalog = defineAsyncComponent(() => import('./SupplyCatalog.vue'))
const productLibraryPageSizeOptions = [...pageSizeOptions, 2000]
const materialPageSizeOptions = [...pageSizeOptions, 2000]
const hubUploadPageSizeOptions = [25, 50, 100, 500, 1000]

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const token = ref(localStorage.getItem('haitoro_token') || '')
const route = useRoute()
const router = useRouter()
const workspaceRouteNames = new Set(['collection', 'collection-history', 'dashboard', 'templates', 'pod', 'creative-resources', 'tasks', 'materials', 'drafts', 'product-library', 'supply', 'miaoshou', 'members', 'shops', 'tiktok-catalogs'])
const page = computed<string>({
  get: () => workspaceRouteNames.has(String(route.name)) ? String(route.name) : 'dashboard',
  set: value => { if (workspaceRouteNames.has(value) && value !== route.name) void router.push({ name: value }) },
})
const hubAgentPairingCode = ref(new URLSearchParams(location.search).get('hub_agent_pair') || '')
const email = ref('')
const password = ref('')
const user = ref<any>(null), company = ref<any>(null), shops = ref<any[]>([]), templates = ref<any[]>([]), templateGroups = ref<any[]>([]), tasks = ref<any[]>([]), materialAssets = ref<any[]>([]), drafts = ref<any[]>([]), members = ref<any[]>([]), operatorGroups = ref<any[]>([]), aiProviders = ref<any[]>([])
const loading = ref(false), error = ref('')
const toast = ref('')
const crossCompanyCollectionEnabled = ref(false)
const materialCollectionDetail = ref<any>(null)
const templateQuery = ref(''), activeGroupId = ref<number | null>(null), selectedTemplateId = ref<number | null>(null)
const showGroupDialog = ref(false), showTemplateDialog = ref(false), templateFormTab = ref<'basic' | 'product' | 'logistics' | 'ai-prompts'>('basic'), newGroupName = ref(''), newTemplateName = ref(''), newTemplateDescription = ref(''), newTemplateTitleTemplate = ref(''), newTemplateProductDescription = ref(''), newTemplateSizeChart = ref<File | null>(null), newTemplateSizeChartPreview = ref(''), newTemplateGroupId = ref<number | null>(null), newTemplateImage = ref<File | null>(null), newTemplateImagePreview = ref(''), newPackageWeight = ref<number | null>(null), newPackageLength = ref<number | null>(null), newPackageWidth = ref<number | null>(null), newPackageHeight = ref<number | null>(null), newSkuSizeOptions = ref<string[]>([]), newTemplateAiPrompts = ref<{name:string; content:string}[]>([]), editingTemplate = ref<any>(null)
const showMemberDialog = ref(false), editingMember = ref<any>(null), memberForm = ref({ name: '', user_code: '', email: '', password: '', is_active: true, role: 'member', group_id: null as number | null }), memberSaving = ref(false), memberFormError = ref(''), memberListRefreshing = ref(false)
const memberSupplyGrantSaving = ref(false)
const showOperatorGroupDialog = ref(false), editingOperatorGroup = ref<any>(null), operatorGroupForm = ref({ name: '', leader_user_id: null as number | null }), operatorGroupSaving = ref(false), operatorGroupError = ref('')
const showMemberCredentialDialog = ref(false), credentialMember = ref<any>(null), credentialProvider = ref<any>(null), credentialApiKey = ref(''), credentialSaving = ref(false)
const showMyAccountDialog = ref(false), myName = ref(''), myUserCode = ref(''), myAccountSaving = ref(false)
const managedShops = ref<any[]>([]), shopLoading = ref(false), shopError = ref('')
const showMiaoshouDialog = ref(false), miaoshouForm = ref({ app_id: '', app_secret: '' }), miaoshouSaving = ref(false)
const showHubstudioDialog = ref(false), hubstudioSaving = ref(false), hubstudioForm = ref({app_id:'', app_secret:'', group_code:''})
const hubUploadTasks = ref<any[]>([]), hubUploadTotal = ref(0), hubUploadPage = ref(1), hubUploadPageSize = ref(25), hubUploadCreatorId = ref<number | null>(null), hubUploadLoading = ref(false), hubUploadError = ref('')
const hubUploadTemplateId = ref<number | null>(null), hubUploadTemplates = ref<{id:number; name:string}[]>([])
const hubUploadPageCount = computed(() => Math.max(1, Math.ceil(hubUploadTotal.value / hubUploadPageSize.value)))
const hubUploadStatusLabels: Record<string, string> = {queued:'排队中', running:'执行中', completed:'已提交', awaiting_attention:'待人工处理', failed:'失败', cancelled:'已取消', expired:'已过期'}
let hubUploadRequestId = 0
async function loadHubUploadTasks() {
  if (!token.value || !user.value) return
  const requestId = ++hubUploadRequestId
  hubUploadLoading.value = true
  hubUploadError.value = ''
  try {
    const {data} = await api.get('/hub-upload-tasks', {headers:headers.value, params:{page:hubUploadPage.value, page_size:hubUploadPageSize.value, template_id:hubUploadTemplateId.value ?? undefined, scope:user.value.role === 'company_admin' ? 'company' : 'own', creator_id:user.value.role === 'company_admin' ? hubUploadCreatorId.value ?? undefined : undefined}})
    if (requestId !== hubUploadRequestId) return
    hubUploadTemplates.value = data.templates || []
    hubUploadTasks.value = data.items
    hubUploadTotal.value = data.total
    if (hubUploadPage.value > hubUploadPageCount.value) {
      hubUploadPage.value = hubUploadPageCount.value
      await loadHubUploadTasks()
    }
  } catch(e:any) {
    if (requestId === hubUploadRequestId) {
      hubUploadTasks.value = []
      hubUploadTotal.value = 0
      hubUploadError.value = e.response?.data?.detail || '加载自动上品记录失败，请重试'
    }
  } finally { if (requestId === hubUploadRequestId) hubUploadLoading.value = false }
}
function changeHubUploadPageSize() { hubUploadPage.value = 1; void loadHubUploadTasks() }
function changeHubUploadCreator() { hubUploadPage.value = 1; void loadHubUploadTasks() }
function changeHubUploadPage(target:number) { hubUploadPage.value = Math.min(Math.max(1, target), hubUploadPageCount.value); void loadHubUploadTasks() }
function hubUploadEnvironment(task:any) { return task.environment_name || task.container_code || (task.environment_id ? String(task.environment_id) : '等待领取') }
const tiktokCatalogs = ref<any[]>([]), tiktokCatalogLoading = ref(false), tiktokCatalogError = ref(''), tiktokCatalogListRefreshing = ref(false)
const showTiktokCatalogDialog = ref(false), tiktokCatalogName = ref(''), tiktokCatalogFile = ref<File | null>(null)
const tiktokCatalogTypeTab = ref<'tiktok_local'|'tiktok_cross_border'|'shopee_basic'>('tiktok_local')
const showTiktokCatalogDetailDialog = ref(false), managingTiktokCatalog = ref<any>(null), managingTiktokCatalogOptions = ref<any>(null), managingTiktokCategory = ref('')
const materialUploading = ref(false), materialUploadError = ref('')
const materialTemplateDownloading = ref(false), materialImportPreviewing = ref(false), materialImportSaving = ref(false)
const materialImportFileInput = ref<HTMLInputElement | null>(null), showMaterialImportDialog = ref(false)
const materialImportItems = ref<{url:string; exists:boolean; selected:boolean; is_infringing:boolean; style_id:number | null; failed?:boolean}[]>([])
const materialImportTemplateId = ref<number | null>(null), materialImportError = ref('')
const materialImportSelectedCount = computed(() => materialImportItems.value.filter(item => item.selected).length)
function materialSourceLabel(source:string) { return ({ai_created:'AI创作',local_upload:'本地上传',imported:'导入',cross_company:'采集'} as Record<string,string>)[source] || '本地上传' }

const selectedMaterialAssetIds = ref<number[]>([]), materialTemplateFilterId = ref<number | null>(null), showMaterialDraftDialog = ref(false), materialDraftTemplateId = ref<number | null>(null), materialDraftTitle = ref(''), materialDraftProductDescription = ref(''), materialDraftSizeChartPreview = ref(''), materialDraftTitleGenerating = ref(false), materialDraftSaving = ref(false)
const materialDraftAdditionalRequirements = ref(''), showDraftAdditionalRequirements = ref(false), showDraftTitleHelp = ref(false)
watch(showMaterialDraftDialog, () => { materialDraftAdditionalRequirements.value = ''; showDraftAdditionalRequirements.value = false; showDraftTitleHelp.value = false })

const libraryDraftMode = ref(false), libraryDraftSelection = ref<any[]>([]), materialDraftTitleEdited = ref(false)
const materialDraftAssets = ref<any[]>([]), draggedMaterialDraftAssetId = ref<number | null>(null)
type MaterialUsageTab = 'unused' | 'used'
const activeMaterialUsageTab = ref<MaterialUsageTab>('unused')
const materialUsageTabs: {key: MaterialUsageTab; label: string}[] = [{key:'unused', label:'未使用'}, {key:'used', label:'已使用'}]
type MaterialBatchGroup = BatchTitleGroup & {assets:any[]; additionalRequirements:string; showAdditionalRequirements:boolean; showTitleHelp:boolean}
const showMaterialBatchDraftDialog = ref(false), materialBatchGroupSize = ref<5|6|7|8>(5), materialBatchMode = ref<'sequential'|'random'>('sequential'), materialBatchGroups = ref<MaterialBatchGroup[]>([]), materialBatchSaving = ref(false)
const draggedMaterialBatchAsset = ref<{groupIndex:number; assetId:number} | null>(null)
let materialBatchGroupId = 0
const materialBatchTitleProgress = ref(emptyTitleGenerationProgress())
const materialBatchControlsLocked = computed(() => materialBatchSaving.value || materialBatchTitleProgress.value.running)
const materialBatchTitlesValid = computed(() => hasValidBatchTitles(materialBatchGroups.value))
const materialBatchUnfinishedTitles = computed(() => materialBatchGroups.value.filter(isUnfinishedTitle))
const materialBatchTitleGenerator = createBatchTitleGenerator<MaterialBatchGroup>({
  progress: materialBatchTitleProgress.value,
  generate: async (group, signal) => {
    const request = batchTitleRequest(draftSelectionTemplateId.value!, libraryDraftMode.value, group.assets[0], group.additionalRequirements)
    const { data } = await api.post(request.url, request.payload, { headers: headers.value, signal, timeout: 60000 })
    return data.title
  },
  isCurrent: group => showMaterialBatchDraftDialog.value && materialBatchGroups.value.includes(group),
  onFatal: message => showToast(message),
})
watch(showMaterialBatchDraftDialog, visible => {
  if (!visible) materialBatchTitleGenerator.reset()
  for (const group of materialBatchGroups.value) { group.additionalRequirements = ''; group.showAdditionalRequirements = false; group.showTitleHelp = false }
}, { flush: 'sync' })
const pendingMaterialUploadFiles = ref<{file:File; preview:string; selected:boolean; is_infringing:boolean; style_id:number | null}[]>([]), showMaterialUploadDialog = ref(false), materialUploadTemplateId = ref<number | null>(null)
watch(showMaterialUploadDialog, visible => {
  if (!visible) clearMaterialUploadPreviews()
}, { flush: 'sync' })
function clearMaterialUploadPreviews() {
  pendingMaterialUploadFiles.value.forEach(item => URL.revokeObjectURL(item.preview))
  pendingMaterialUploadFiles.value = []
}
onUnmounted(clearMaterialUploadPreviews)
const batchClaimInfringement = ref<Record<string, boolean>>({})
function setImportInfringement(value:boolean) { materialImportItems.value.forEach(item => { if(item.selected) item.is_infringing=value }) }
function setUploadInfringement(value:boolean) { pendingMaterialUploadFiles.value.forEach(item => { if(item.selected) item.is_infringing=value }) }
function setBatchClaimInfringement(value:boolean) { selectedBatchClaimImages.value.forEach(key => { batchClaimInfringement.value[key]=value }) }
const MATERIAL_UPLOAD_MAX_FILES = 100, IMAGE_UPLOAD_RETRY = 2
const templateSaving = ref(false)
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'], MAX_IMAGE_BYTES = 3 * 1024 * 1024
const showDraftEditDialog = ref(false), editingDraft = ref<any>(null), draftEditTitle = ref(''), draftEditProductDescription = ref(''), draftEditSaving = ref(false), draftEditError = ref('')
const publishingDraftId = ref<number | null>(null), skippingCarouselDraftId = ref<number | null>(null), skippingMainImageDraftId = ref<number | null>(null), dispatchingDraftStage = ref<''|'carousel_pending'|'main_image_pending'|'ready_to_publish'>('')
const selectedDraftIds = ref<number[]>([]), showTiktokExportDialog = ref(false), tiktokExportOptions = ref<any>(null), tiktokExportLoading = ref(false), tiktokExportError = ref('')
const showShopeeExportDialog = ref(false), shopeeExportOptions = ref<any>(null), shopeeExportLoading = ref(false), shopeeExportError = ref('')
const showMiaoshouPublishDialog = ref(false), miaoshouPublishDraftIds = ref<number[]>([]), miaoshouPublishShopId = ref<number | null>(null), miaoshouPublishing = ref(false), miaoshouPublishCompleted = ref(0), miaoshouPublishFailed = ref(0)
const showBatchCarouselDialog = ref(false), showBatchMainImageDialog = ref(false), batchCarouselSaving = ref(false), batchMainImageSaving = ref(false), batchCarouselSkipping = ref(false), batchMainImageSkipping = ref(false), batchCarouselSelections = ref<Record<number,string[]>>({}), batchMainImageSelections = ref<Record<number,string[]>>({})
const showBatchImageReviewDialog = ref(false), batchImageReviewLoading = ref(false), batchImageReviewSaving = ref(false), batchImageReviewType = ref<'carousel'|'main_image'>('carousel'), batchImageReviewDrafts = ref<any[]>([]), batchImageReviewSelections = ref<Record<number,string[]>>({}), batchCarouselReviewNextStage = ref<'main_image_pending'|'ready_to_publish'>('main_image_pending')
const MAX_DRAFT_BATCH_SIZE = 100
const tiktokExportCatalogId = ref<number | null>(null), tiktokExportCategory = ref(''), tiktokExportDefaultPrice = ref<number | null>(null), tiktokExportDefaultQuantity = ref<number>(999), tiktokExportCod = ref<'Y' | 'N'>('Y'), tiktokExportAttributes = ref<Record<string, string>>({}), tiktokExportOverrides = ref<Record<number, {price:number | null; quantity:number | null}>>({}), tiktokSubmitting = ref(false)
const TIKTOK_EXPORT_ATTRIBUTE_PRESETS_VERSION = 'v1'
const shopeeExportCatalogId = ref<number | null>(null), shopeeExportCategoryId = ref(''), shopeeExportDefaultPrice = ref<number | null>(null), shopeeExportDefaultQuantity = ref<number>(999), shopeeExportChannels = ref<string[]>([]), shopeeExportOverrides = ref<Record<number,{price:number|null;quantity:number|null}>>({})
const draftPageSize = ref(20), currentDraftPage = ref(1), draftTemplateFilterId = ref<number | null>(null), draftCreatorFilterId = ref<number | null>(null), draftListRefreshing = ref(false)
const productLibraryItems = ref<any[]>([]), productLibraryTotal = ref(0), productLibraryPage = ref(1), productLibraryPageSize = ref(20), productLibraryLoading = ref(false), productLibraryImporting = ref(false), productLibraryDownloading = ref(false)
const productLibraryStatisticsSubmitting = ref(false)
const productLibraryStatisticsTask = ref<any>(null)
const productLibraryStatisticsRunning = computed(() => ['queued','running'].includes(productLibraryStatisticsTask.value?.status))
const productLibraryRankingItems = ref<any[]>([]), productLibraryRankingTotal = ref(0), productLibraryRankingPage = ref(1), productLibraryRankingPageSize = ref(20), productLibraryRankingLoading = ref(false)
const productLibraryRankingDate = ref<string | null>(null), productLibraryRankingThroughDate = ref<string | null>(null), productLibraryRankingError = ref('')
const productLibraryShops = ref<any[]>([]), productLibraryShopsLoading = ref(false), productLibraryAssigningId = ref<number | null>(null)
let productLibraryRankingRequestId = 0
const stagnantMaterials = ref<any[]>([]), stagnantTotal = ref(0), stagnantPage = ref(1), stagnantPageSize = ref(20), stagnantCreatorId = ref<number | null>(null), stagnantLoading = ref(false), stagnantError = ref('')
let stagnantRequestId = 0
const newImages = ref<any[]>([]), newImagesTotal = ref(0), newImagesPage = ref(1), newImagesPageSize = ref(20), newImagesCreatorId = ref<number | null>(null), newImagesUsageStatus = ref<'all'|'unused'|'used'>('all'), newImagesLoading = ref(false), newImagesError = ref('')
let newImagesRequestId = 0
type ProductLibraryTab = 'shops' | 'products' | 'top7' | 'top15' | 'top30' | 'new_images' | 'stagnant' | 'potential' | 'hot' | 'booming'
const activeProductLibraryTab = ref<ProductLibraryTab>('products')
const productLibraryTabs: {key:ProductLibraryTab;label:string}[] = [
  {key:'shops',label:'店铺管理'}, {key:'products',label:'排行榜'}, {key:'top7',label:'7天热销TOP50'}, {key:'top15',label:'15天热销TOP50'},
  {key:'top30',label:'30天热销TOP50'}, {key:'potential',label:'潜力款'},
  {key:'hot',label:'热销款'}, {key:'booming',label:'旺款'}, {key:'stagnant',label:'滞销款'}, {key:'new_images',label:'新图'},
]
const productLibraryRankingTabKeys = new Set<ProductLibraryTab>(['top7','top15','top30','potential','hot','booming'])
const productLibraryTopTabKeys = new Set<ProductLibraryTab>(['top7','top15','top30'])
const productLibraryCategoryDescriptions: Partial<Record<ProductLibraryTab,string>> = {
  stagnant:'素材创建超过 90 天且历史累计 0 订单',
  new_images:'近 5 天新增的素材',
  potential:'近7天销量大于30',
  hot:'近7天销量大于70',
  booming:'近7天销量大于130',
}
const productLibraryFilters = ref<{shops:{id:number;label:string}[];creators?:{id:number;name:string}[]}>({shops:[]})
const productLibrarySelectedShopIds = ref<number[]>([]), productLibraryShopSearch = ref('')
const productLibraryShopFilterDetails = ref<HTMLDetailsElement | null>(null)
function closeProductLibraryShopFilterOnOutsideClick(event: PointerEvent) {
  const details = productLibraryShopFilterDetails.value
  if (details?.open && !details.contains(event.target as Node)) details.open = false
}
const productLibraryShopOptions = computed(() => productLibraryFilters.value.shops.filter(shop => shop.label.toLocaleLowerCase().includes(productLibraryShopSearch.value.trim().toLocaleLowerCase())))
const productLibraryShopSelectionLabel = computed(() => productLibrarySelectedShopIds.value.length === 0 ? '全部店铺' : productLibrarySelectedShopIds.value.length === 1 ? productLibraryFilters.value.shops.find(shop => shop.id === productLibrarySelectedShopIds.value[0])?.label || '已选 1 家店铺' : `已选 ${productLibrarySelectedShopIds.value.length} 家店铺`)
const productLibraryTemplateFilter = ref(''), productLibrarySku = ref('')
const productLibraryCreatorId = ref<number | null>(null)
const productLibraryCreatorOptions = computed(() => productLibraryFilters.value.creators || (user.value?.role==='company_admin' ? members.value : []))
const appliedProductLibraryFilters = ref({sourceIds:[] as number[], template:'', sku:'', creatorId:null as number | null})
const rankingCreatorFilters = ref<Partial<Record<ProductLibraryTab, number | null>>>({})
const rankingShopFilters = ref<Partial<Record<ProductLibraryTab, number[]>>>({})
const MAX_PRODUCT_LIBRARY_SELECTION = 2000
const selectedProductLibraryIds = ref<number[]>([]), productLibraryBrokenImages = ref<number[]>([])
const showProductLibraryTemplateDialog = ref(false), productLibraryTargetTemplateId = ref<number | null>(null), productLibraryTemplateSaving = ref(false)
const productLibraryOrderProduct = ref<any | null>(null), productLibraryOrders = ref<any[]>([]), productLibraryOrderTotal = ref(0), productLibraryOrderCount = ref(0), productLibraryOrderPage = ref(1), productLibraryOrderPageSize = ref(20), productLibraryOrderLoading = ref(false)
let productLibraryOrderRequestId = 0
const productLibraryFileInput = ref<HTMLInputElement | null>(null)
type DraftTab = 'all' | 'pending' | 'carousel_pending' | 'main_image_pending' | 'ready_to_publish' | 'published'
const activeDraftTab = ref<DraftTab>('all'), draftTotal = ref(0), draftTabCounts = ref<Record<DraftTab, number>>({all:0,pending:0,carousel_pending:0,main_image_pending:0,ready_to_publish:0,published:0})
type DraftWorkStatus = 'all' | 'not_started' | 'in_progress' | 'awaiting_review' | 'failed'
const activeDraftWorkStatus = ref<DraftWorkStatus>('all'), draftWorkStatusCounts = ref<Record<DraftWorkStatus,number>>({all:0,not_started:0,in_progress:0,awaiting_review:0,failed:0})
const draftWorkStatusTabs:{key:DraftWorkStatus;label:string}[]=[{key:'all',label:'全部'},{key:'not_started',label:'未制作'},{key:'in_progress',label:'制作中'},{key:'awaiting_review',label:'待审核'},{key:'failed',label:'制作失败'}]
const draftTabs: {key:DraftTab;label:string}[] = [{key:'all',label:'全部'},{key:'pending',label:'待处理'},{key:'carousel_pending',label:'待制作轮播图'},{key:'main_image_pending',label:'待制作主图'},{key:'ready_to_publish',label:'待发布'},{key:'published',label:'发布成功'}]
const draftStatusLabels: Record<string,string> = {pending:'待处理',carousel_pending:'待制作轮播图',main_image_pending:'待制作主图',ready_to_publish:'待发布',published:'发布成功'}
type TaskType = 'sku_image' | 'carousel' | 'main_image'
const taskTypeLabels: Record<TaskType,string> = { sku_image:'SKU图', carousel:'轮播图', main_image:'首图' }
const initialTaskParams = new URLSearchParams(location.search)
const initialTaskType = initialTaskParams.get('task_type')
const activeTaskType = ref<TaskType>(['sku_image','carousel','main_image'].includes(initialTaskType || '') ? initialTaskType as TaskType : 'sku_image')
const initialTaskPage = Number(initialTaskParams.get('task_page'))
const initialTaskPageSize = Number(initialTaskParams.get('task_page_size'))
const initialTaskCreator = initialTaskParams.get('task_creator')
const initialTaskStatus = initialTaskParams.get('task_status')
const initialTaskFrom = initialTaskParams.get('task_from') || ''
const initialTaskTo = initialTaskParams.get('task_to') || ''
const initialTaskSkuQuery = initialTaskParams.get('task_skus') || ''
const initialTaskTemplateId = Number(initialTaskParams.get('task_template')) || null
const taskPageSize = ref(pageSizeOptions.includes(initialTaskPageSize) ? initialTaskPageSize : 20), currentTaskPage = ref(initialTaskPage > 0 ? initialTaskPage : 1), taskTotal = ref(0), taskActiveCount = ref(0), taskStatusCounts = ref<Record<string, number>>({}), taskCreatorFilterId = ref<number | null>(initialTaskCreator && initialTaskCreator !== 'all' ? Number(initialTaskCreator) || null : null)
const taskTypeTotals = ref<Record<string,number>>({sku_image:0,carousel:0,main_image:0})
const taskTypeFilteredTotals = ref<Record<string,number | null>>({sku_image:null,carousel:null,main_image:null})
const taskTabStates = ref<Record<TaskType,any>>({sku_image:null,carousel:null,main_image:null})
const taskStatusFilter = ref(initialTaskStatus !== null && ['queued','running','awaiting_selection','completed','failed',''].includes(initialTaskStatus) ? initialTaskStatus : ''), taskCreatedFrom = ref(initialTaskFrom), taskCreatedTo = ref(initialTaskTo)
const taskSkuQuery = ref(initialTaskSkuQuery)
const taskTemplateFilterId = ref<number | null>(initialTaskTemplateId)
const appliedTaskFilters = ref({ creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: initialTaskFrom ? new Date(initialTaskFrom).toISOString() : '', created_to: initialTaskTo ? new Date(initialTaskTo).toISOString() : '', sku_query: initialTaskSkuQuery, template_id: initialTaskTemplateId })
const selectedBatchClaimImages = ref(new Set<string>())
type ImageHoverPreview = {url:string; alt:string; left:number; top:number; width:number; height:number}
const batchClaimHoverPreview = ref<ImageHoverPreview | null>(null)
const materialHoverPreview = ref<ImageHoverPreview | null>(null)
const selectedTaskIds = ref<number[]>([]), showBatchClaimDialog = ref(false), batchClaimItems = ref<{taskId:number; taskLabel:string; url:string}[]>([]), batchClaimLoading = ref(false), batchClaiming = ref(false), batchClaimCompleted = ref(0), batchClaimTotal = ref(0), batchClaimFailed = ref(0)
const materialPageSize = ref(20), currentMaterialPage = ref(1), materialTotal = ref(0), materialCreatorFilterId = ref<number | null>(null), materialListRefreshing = ref(false)
type MaterialSourceType = '' | 'ai_created' | 'local_upload' | 'imported' | 'cross_company'
const materialStyleFilterId = ref<number | null>(null)
const materialSourceTypeFilter = ref<MaterialSourceType>('')
const materialCreatedFrom = ref(''), materialCreatedTo = ref('')
const appliedMaterialFilters = ref<{template_id:number | null; creator_id:number | null; style_id:number | null; source_type:MaterialSourceType; created_from:string; created_to:string}>({template_id:null, creator_id:null, style_id:null, source_type:'', created_from:'', created_to:''})
function materialQueryParams() { return {page:currentMaterialPage.value, page_size:materialPageSize.value, ...appliedMaterialFilters.value, created_from:appliedMaterialFilters.value.created_from || undefined, created_to:appliedMaterialFilters.value.created_to || undefined, usage_status:activeMaterialUsageTab.value} }
const creatorFiltersInitialized = ref(false)
const previewImageUrl = ref(''), previewImageAlt = ref('')
type ImageWorkspaceMode = 'carousel' | 'full'
const showDraftImageDialog = ref(false), imageWorkspaceMode = ref<ImageWorkspaceMode>('full'), imageDraft = ref<any>(null), imageWorkspaceLoading = ref(false), imageTasksRefreshing = ref(false), imageTaskCreatingType = ref<''|'carousel'|'main_image'>(''), imageConfirmSaving = ref(false)
const carouselConfirmNextStage = ref<'main_image_pending'|'ready_to_publish'>('main_image_pending')
type MainReferenceMode = 'random_carousel'|'random_sku'|'manual'
const selectedImageSkus = ref<string[]>([]), selectedMainReferences = ref<string[]>([]), mainReferenceMode = ref<MainReferenceMode>('random_carousel')
// 轮播图与首图任务使用各自独立的一套生成参数，互不干扰。
type ImageQuality = 'auto'|'1K'|'2K'
const carouselParams = ref<{prompt:string;provider:string;ratio:'1:1'|'3:4';quality:ImageQuality}>({prompt:'',provider:'',ratio:'1:1',quality:'1K'}), mainParams = ref<{prompt:string;provider:string;ratio:'1:1'|'3:4';quality:ImageQuality}>({prompt:'',provider:'',ratio:'1:1',quality:'1K'})
const batchCarouselParams = ref<{prompt:string;provider:string;ratio:'1:1'|'3:4';quality:ImageQuality}>({prompt:'',provider:'',ratio:'1:1',quality:'1K'})
const batchMainImageParams = ref<{prompt:string;provider:string;ratio:'1:1'|'3:4';quality:ImageQuality}>({prompt:'',provider:'',ratio:'1:1',quality:'1K'}), batchMainImageReferenceMode = ref<MainReferenceMode>('random_carousel')
const stagedFinalImageItems = ref<any[] | null>(null), draggedFinalImageUrl = ref('')
const showMainApplyDialog = ref(false), pendingMainApply = ref<{task:any;url:string}|null>(null), mainRemoveSku = ref('')
const showShopManagersDialog = ref(false), managingShop = ref<any>(null), selectedManagerIds = ref<number[]>([]), shopManagersSaving = ref(false)
const showTaskDetailDialog = ref(false), viewingTask = ref<any>(null), taskDetailLoading = ref(false)
const taskListRefreshing = ref(false), retryingTaskId = ref<number | null>(null), batchRetryingTasks = ref(false), retryingWorkspaceTaskId = ref<number | null>(null)
type CreativeAsset = { id: string; file: File; preview: string; uploadedUrl?: string }
const defaultSkuSizes = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL']
const defaultPackageLogistics = { weight: 0.28, length: 30, width: 16, height: 2 }
const creativeAssets = ref<CreativeAsset[]>([]), showCreativeAssetsDialog = ref(false), creativeAssetError = ref(''), creativeSubmitError = ref(''), creativeRequirement = ref(''), creativePromptIndex = ref(''), creativeProvider = ref(''), creativeRatio = ref<'1:1' | '3:4'>('1:1'), creativeQuality = ref<ImageQuality>('1K'), creativeUploading = ref(false), creativeUploadedCount = ref(0)
const personalWhiteImages = ref<any[]>([]), personalPrompts = ref<any[]>([]), selectedWhiteImageId = ref<number | null>(null), personalResourcesLoading = ref(false)
const personalResourceTab = ref<'white-images' | 'prompts' | 'styles'>('white-images'), managedResourceUserId = ref<number | null>(null), managedWhiteImages = ref<any[]>([]), managedPrompts = ref<any[]>([]), personalResourceSaving = ref(false)
const editingWhiteImage = ref<any>(null), whiteImageForm = ref({ template_id: null as number | null, name: '', file: null as File | null })
const editingPersonalPrompt = ref<any>(null), personalPromptForm = ref({ template_id: null as number | null, name: '', content: '' })
const resourceEditorType = ref<'white-images' | 'prompts' | null>(null), resourceEditorError = ref(''), resourceEditorUserId = ref<number | null>(null)
const resourceEditorTitle = computed(() => resourceEditorType.value==='white-images' ? (editingWhiteImage.value ? '编辑白底图' : '新增白底图') : (editingPersonalPrompt.value ? '编辑创作要求' : '新增创作要求'))
const nav = [{key:'dashboard', icon:'◈', label:'工作台'}, {key:'templates', icon:'▦', label:'产品模板'}, {key:'pod', icon:'✦', label:'AI创作'}, {key:'creative-resources', icon:'▧', label:'创作资源'}, {key:'tasks', icon:'◌', label:'任务中心'}, {key:'materials', icon:'◈', label:'素材库'}, {key:'drafts', icon:'▤', label:'商品草稿'}, {key:'product-library', icon:'▤', label:'产品库'}, {key:'supply', icon:'▦', label:'公开货盘'}, {key:'miaoshou', icon:'▤', label:'妙手管理', adminOnly:true}, {key:'shops', icon:'▣', label:'HubStudio管理'}, {key:'tiktok-catalogs', icon:'▧', label:'类目管理', adminOnly:true}, {key:'members', icon:'♙', label:'成员管理', adminOnly:true}]
const materialStyles = ref<MaterialStyle[]>([]), materialStylesLoading = ref(false)
const materialStyleLabels = computed(() => new Map(styleOptions(materialStyles.value, null).map(option => [option.value, option.label])))
const materialStyleTargetId = ref<number | null>(null), uploadStyleTargetId = ref<number | null>(null), importStyleTargetId = ref<number | null>(null)
const materialSettingKind = ref<'infringement' | 'style' | null>(null), materialSettingSaving = ref(false), materialSettingError = ref('')
const materialSettingAssetIds = ref<number[]>([]), materialSettingTemplateId = ref<number | null>(null), materialInfringementTarget = ref<boolean | null>(null)
const materialSettingTitle = computed(() => materialSettingKind.value === 'infringement' ? '设置侵权状态' : '设置风格')
const materialSettingStyleOptions = computed(() => [{value:null, label:'未分组'}, ...(materialSettingTemplateId.value ? styleOptions(materialStyles.value, materialSettingTemplateId.value) : [])])
const resourceTemplateFilterId = ref<number | null>(null), resourceQuery = ref(''), managedResourcesLoading = ref(false)
const resourceWhiteImageStatus = ref<'active' | 'deleted'>('active')
const appliedResourceFilters = ref<{ownerId:number | null;templateId:number | null;query:string;whiteImageStatus:'active' | 'deleted'}>({ownerId:null,templateId:null,query:'',whiteImageStatus:'active'})
const resourceSearchBusy = computed(() => managedResourcesLoading.value || materialStylesLoading.value || personalResourceSaving.value)
const resourceOwners = computed(() => members.value.filter(member => ['company_admin','member','team_leader'].includes(member.role)))
const resourceMatches = (item:any) => (!appliedResourceFilters.value.templateId || item.template_id===appliedResourceFilters.value.templateId) && `${item.name} ${item.content || ''}`.toLowerCase().includes(appliedResourceFilters.value.query)
const visibleManagedWhiteImages = computed(() => managedWhiteImages.value.filter(item => resourceMatches(item) && (item.deleted_at!=null)===(appliedResourceFilters.value.whiteImageStatus==='deleted')))
const visibleManagedPrompts = computed(() => managedPrompts.value.filter(resourceMatches))
const visibleResourceStyles = computed(() => materialStyles.value.filter(item => resourceMatches(item) && (user.value?.role!=='company_admin' || appliedResourceFilters.value.ownerId===null || item.created_by===appliedResourceFilters.value.ownerId)))
const resourceCurrentPage = ref(1), resourcePageSize = ref(20)
const resourceTotal = computed(() => personalResourceTab.value==='white-images' ? visibleManagedWhiteImages.value.length : personalResourceTab.value==='prompts' ? visibleManagedPrompts.value.length : visibleResourceStyles.value.length)
const resourcePageCount = computed(() => Math.max(1,Math.ceil(resourceTotal.value/resourcePageSize.value)))
const resourceVisiblePage = computed(() => Math.min(resourceCurrentPage.value,resourcePageCount.value))
const resourcePaginationBusy = computed(() => personalResourceSaving.value || (personalResourceTab.value==='styles' ? materialStylesLoading.value : managedResourcesLoading.value))
function resourcePageItems<T>(items:T[]):T[] {
  const offset=(resourceVisiblePage.value-1)*resourcePageSize.value
  return items.slice(offset,offset+resourcePageSize.value)
}
const pagedManagedWhiteImages = computed(() => resourcePageItems(visibleManagedWhiteImages.value))
const pagedManagedPrompts = computed(() => resourcePageItems(visibleManagedPrompts.value))
const pagedResourceStyles = computed(() => resourcePageItems(visibleResourceStyles.value))
watch([personalResourceTab,resourcePageSize], () => { resourceCurrentPage.value=1 })
watch(resourcePageCount, count => { resourceCurrentPage.value=Math.min(resourceCurrentPage.value,count) })
function changeResourcePage(target:number) {
  if(resourcePaginationBusy.value) return
  resourceCurrentPage.value=Math.min(Math.max(1,target),resourcePageCount.value)
}
const materialStyleFilterOptions = computed(() => [
  {value:null, label:'全部风格'}, {value:0, label:'未分组'},
  ...styleOptions(materialStyles.value, materialTemplateFilterId.value).map(option => ({...option,
    label: materialTemplateFilterId.value ? option.label : `${templates.value.find(item=>item.id===materialStyles.value.find(style=>style.id===option.value)?.template_id)?.name || '历史模板'} · ${option.label}`})),
])
let materialStylesRequestId = 0
async function loadMaterialStyles() {
  if (!token.value || !user.value || user.value.role==='supply_user') return
  const requestId = ++materialStylesRequestId
  materialStylesLoading.value=true
  try {
    const {data}=await api.get('/material-styles',{headers:headers.value})
    if(requestId===materialStylesRequestId) materialStyles.value=data.items || []
  } catch(e:any) { if(requestId===materialStylesRequestId) showToast(e.response?.data?.detail || '加载风格失败，请重试') }
  finally { if(requestId===materialStylesRequestId) materialStylesLoading.value=false }
}
watch(materialUploadTemplateId, () => { pendingMaterialUploadFiles.value.forEach(item=>item.style_id=null); uploadStyleTargetId.value=null })
watch(materialImportTemplateId, () => { materialImportItems.value.forEach(item=>item.style_id=null); importStyleTargetId.value=null })
watch(materialTemplateFilterId, () => { materialStyleFilterId.value=null })
function openMaterialSetting(kind: 'infringement' | 'style') {
  if (materialSettingSaving.value || !selectedMaterialAssetIds.value.length) return
  const limit = kind === 'infringement' ? 1000 : 2000
  if (selectedMaterialAssetIds.value.length > limit) { showToast(`每次最多修改 ${limit} 张素材，请减少选择`); return }
  materialSettingAssetIds.value = [...selectedMaterialAssetIds.value]
  materialSettingTemplateId.value = commonStyleTemplate(materialAssets.value.filter(asset => materialSettingAssetIds.value.includes(asset.id)))
  materialInfringementTarget.value = null
  materialStyleTargetId.value = null
  materialSettingError.value = ''
  materialSettingKind.value = kind
}
function closeMaterialSetting() {
  if (!materialSettingSaving.value) materialSettingKind.value = null
}
async function confirmMaterialSetting() {
  const kind = materialSettingKind.value, ids = [...materialSettingAssetIds.value]
  if (!kind || !ids.length || materialSettingSaving.value) return
  const isInfringing = materialInfringementTarget.value, styleId = materialStyleTargetId.value
  if (kind === 'infringement' && isInfringing === null) { materialSettingError.value = '请选择侵权状态'; return }
  if (kind === 'style' && styleId !== null && !materialSettingTemplateId.value) { materialSettingError.value = '设置风格请选择同一模板的素材'; return }
  materialSettingSaving.value = true
  materialSettingError.value = ''
  try {
    if (kind === 'infringement') {
      await api.patch(ids.length === 1 ? `/material-assets/${ids[0]}/infringement` : '/material-assets/infringement',
        {is_infringing:isInfringing, ...(ids.length === 1 ? {} : {material_asset_ids:ids})}, {headers:headers.value})
      await refreshMaterialList()
      showToast(`已将 ${ids.length} 张素材设为${isInfringing ? '侵权' : '不侵权'}`)
    } else {
      const {data} = await api.patch('/material-assets/style', {material_asset_ids:ids, style_id:styleId}, {headers:headers.value})
      await Promise.all([refreshMaterialList(), loadMaterialStyles()])
      showToast(`已将 ${data.count} 张素材设为${styleId === null ? '未分组' : '选中风格'}`)
    }
    materialSettingKind.value = null
  } catch(e:any) { materialSettingError.value = e.response?.data?.detail || '保存失败，请重试' }
  finally { materialSettingSaving.value = false }
}
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }))
const visibleNav = computed(() => nav.filter(item => user.value?.role === 'supply_user' ? item.key === 'supply' : !item.adminOnly || user.value?.role === 'company_admin'))
const pageTitle = computed(() => page.value === 'collection' ? '采集' : page.value === 'collection-history' ? '采集记录' : nav.find(x => x.key === page.value)?.label || '')
const filteredTemplates = computed(() => templates.value.filter(t => (!activeGroupId.value || t.group_id === activeGroupId.value) && t.name.toLowerCase().includes(templateQuery.value.trim().toLowerCase())))
function templateGroupIsEmpty(groupId: number) { return !templates.value.some(template => template.group_id === groupId) }
// 运营端接口只返回后台已启用的模型；这里再保留一次筛选，避免接口数据异常时将停用模型带入任务。
const availableAiProviders = computed(() => aiProviders.value.filter(provider => provider.enabled !== false))
// 密钥属于平台而不是具体模型。相同 credential_provider 的模型只显示一个入口。
const memberCredentialProviders = computed(() => {
  const seen = new Set<string>()
  return [...aiProviders.value, { provider: 'deepseek', credential_provider: 'deepseek', display_name: 'DeepSeek', credential_display_name: 'DeepSeek' }].filter(provider => {
    const credentialProvider = provider.credential_provider || provider.provider
    if (seen.has(credentialProvider)) return false
    seen.add(credentialProvider)
    return true
  }).map(provider => ({
    ...provider,
    credential_provider: provider.credential_provider || provider.provider,
    credential_display_name: provider.credential_provider === 'grsai' ? 'Grsai' : provider.display_name,
  }))
})
const selectedCreativeProvider = computed(() => availableAiProviders.value.find(provider => provider.provider === creativeProvider.value))
function providerUsesAutoQuality(provider: string) { return provider === 'grsai-gpt-image-2' }
function enforceProviderQuality(provider: string, params: { quality: ImageQuality }) { if (providerUsesAutoQuality(provider)) params.quality = 'auto'; else if (params.quality === 'auto') params.quality = '1K' }
const creativeCredentialError = computed(() => selectedCreativeProvider.value?.credential_configured === false
  ? `尚未配置个人 ${selectedCreativeProvider.value.display_name} 平台密钥，请联系公司管理员配置`
  : '')
const selectedTemplate = computed(() => templates.value.find(t => t.id === selectedTemplateId.value))
const selectedWhiteImage = computed(() => personalWhiteImages.value.find(item => item.id === selectedWhiteImageId.value))
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
const materialDraftSkuCount = computed(() => materialDraftAssets.value.length)
const canCreateMaterialBatch = computed(() => selectedMaterialAssets.value.length >= 5 && Boolean(selectedMaterialTemplateId.value))
// 服务端按 Tab 返回数据；这里再按 display_tab 兜底，避免接口请求失败或旧服务未更新时，
// 已切换的 Tab 短暂显示上一页的混合数据。
const filteredDrafts = computed(() => activeDraftTab.value === 'all' ? drafts.value : drafts.value.filter(draft => draft.display_tab === activeDraftTab.value))
const draftPageCount = computed(() => Math.max(1, Math.ceil(draftTotal.value / draftPageSize.value)))
const visibleDraftPage = computed(() => Math.min(currentDraftPage.value, draftPageCount.value))
const pagedDrafts = computed(() => filteredDrafts.value)
const selectedDrafts = computed(() => filteredDrafts.value.filter(draft => selectedDraftIds.value.includes(draft.id)))
const allPagedDraftsSelected = computed(() => Boolean(pagedDrafts.value.length) && pagedDrafts.value.every(draft => selectedDraftIds.value.includes(draft.id)))
const batchDispatchEligible = computed(() => selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'pending'))
const crossBorderManagedShops = computed(() => managedShops.value.filter(shop => shop.shop_type !== 'local'))
const miaoshouAssignableShops = computed(() => shops.value.filter(shop => shop.shop_type !== 'local' && shop.external_shop_id))
const batchMiaoshouPublishEligible = computed(() => activeDraftTab.value === 'ready_to_publish' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'ready_to_publish'))
const tiktokExportEligible = computed(() => selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab !== 'pending'))
const batchCarouselEligible = computed(() => activeDraftTab.value === 'carousel_pending' && ['all', 'not_started'].includes(activeDraftWorkStatus.value) && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'carousel_pending' && draft.carousel_task_summary?.work_status === 'not_started'))
const batchCarouselReviewEligible = computed(() => activeDraftTab.value === 'carousel_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.carousel_task_summary?.work_status === 'awaiting_review'))
const batchCarouselSkipEligible = computed(() => activeDraftTab.value === 'carousel_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'carousel_pending'))
const batchMainImageSkipEligible = computed(() => activeDraftTab.value === 'main_image_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'main_image_pending'))
const batchMainImageEligible = computed(() => activeDraftTab.value === 'main_image_pending' && ['all', 'not_started'].includes(activeDraftWorkStatus.value) && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'main_image_pending' && draft.main_image_task_summary?.work_status === 'not_started'))
const batchMainImageReviewEligible = computed(() => activeDraftTab.value === 'main_image_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.main_image_task_summary?.work_status === 'awaiting_review'))
const selectedTiktokCategoryAttributes = computed(() => tiktokExportOptions.value?.attributes_by_category?.[tiktokExportCategory.value] || [])
const managingTiktokCategoryAttributes = computed(() => managingTiktokCatalogOptions.value?.attributes_by_category?.[managingTiktokCategory.value] || [])
const activeTiktokCatalogs = computed(() => tiktokCatalogs.value.filter(catalog => (catalog.template_type || 'tiktok_local') === tiktokCatalogTypeTab.value))
const tiktokExportCatalogs = computed(() => tiktokCatalogs.value.filter(catalog => ['tiktok_local', 'tiktok_cross_border'].includes(catalog.template_type || 'tiktok_local')))
const shopeeCatalogs = computed(() => tiktokCatalogs.value.filter(catalog => catalog.template_type === 'shopee_basic'))
const tiktokExportIsLocal = computed(() => (tiktokExportOptions.value?.category_catalog?.template_type || tiktokCatalogs.value.find(catalog => catalog.id === tiktokExportCatalogId.value)?.template_type || 'tiktok_local') === 'tiktok_local')
function tiktokCatalogTypeLabel(type: string) { return type === 'shopee_basic' ? 'Shopee' : type === 'tiktok_cross_border' ? 'tk跨境店' : 'tk本土店' }
async function changeDraftPageSize() { if (draftListRefreshing.value) return; currentDraftPage.value = 1; selectedDraftIds.value=[]; await refreshDraftList() }
async function changeDraftTab(tab:DraftTab) { if (draftListRefreshing.value) return; activeDraftTab.value=tab; activeDraftWorkStatus.value='all'; currentDraftPage.value=1; selectedDraftIds.value=[]; await refreshDraftList() }
async function changeDraftWorkStatus(status:DraftWorkStatus) { if (draftListRefreshing.value) return; activeDraftWorkStatus.value=status; currentDraftPage.value=1; selectedDraftIds.value=[]; await refreshDraftList() }
async function changeDraftPage(next:number) { if (draftListRefreshing.value) return; currentDraftPage.value=next; selectedDraftIds.value=[]; await refreshDraftList() }
function toggleDraftSelection(draftId: number) {
  if (selectedDraftIds.value.includes(draftId)) {
    selectedDraftIds.value = selectedDraftIds.value.filter(id => id !== draftId)
    return
  }
  if (selectedDraftIds.value.length >= MAX_DRAFT_BATCH_SIZE) {
    showToast(`一次最多选择 ${MAX_DRAFT_BATCH_SIZE} 条商品草稿`)
    return
  }
  selectedDraftIds.value = [...selectedDraftIds.value, draftId]
}
function togglePagedDrafts() {
  const pageIds = pagedDrafts.value.map(draft => draft.id)
  if (allPagedDraftsSelected.value) {
    selectedDraftIds.value = selectedDraftIds.value.filter(id => !pageIds.includes(id))
    return
  }
  const remaining = MAX_DRAFT_BATCH_SIZE - selectedDraftIds.value.length
  const candidates = pageIds.filter(id => !selectedDraftIds.value.includes(id))
  const additions = candidates.slice(0, remaining)
  selectedDraftIds.value = [...selectedDraftIds.value, ...additions]
  if (additions.length < candidates.length) {
    showToast(`一次最多选择 ${MAX_DRAFT_BATCH_SIZE} 条商品草稿`)
  }
}
async function changeDraftTemplateFilter() { if (draftListRefreshing.value) return; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList() }
async function changeDraftCreatorFilter() { if (draftListRefreshing.value) return; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList() }
async function refreshDraftList() {
  try {
    draftListRefreshing.value = true
    const { data } = await api.get('/drafts', { headers: headers.value, params: { creator_id: draftCreatorFilterId.value, template_id:draftTemplateFilterId.value, tab:activeDraftTab.value, work_status:activeDraftWorkStatus.value, page:currentDraftPage.value, page_size:draftPageSize.value } })
    drafts.value = data.items
    draftTotal.value = data.total
    draftTabCounts.value = data.tab_counts
    draftWorkStatusCounts.value = data.work_status_counts
    selectedDraftIds.value = selectedDraftIds.value.filter(id => data.items.some((draft:any) => draft.id === id))
  } catch (e:any) { showToast(e.response?.data?.detail || '刷新商品草稿失败') }
  finally { draftListRefreshing.value = false }
}
function draftWorkSummary(draft:any) { return draft.display_tab==='carousel_pending' ? draft.carousel_task_summary : draft.main_image_task_summary }
async function dispatchSelectedDrafts(targetStage:'carousel_pending'|'main_image_pending'|'ready_to_publish') {
  if (!batchDispatchEligible.value) { showToast('仅可分发待处理状态的商品草稿'); return }
  const targetLabel=draftStatusLabels[targetStage]
  try {
    dispatchingDraftStage.value=targetStage
    const {data}=await api.post('/drafts/dispatch',{draft_ids:selectedDraftIds.value,target_stage:targetStage},{headers:headers.value})
    selectedDraftIds.value=[]
    await refreshDraftList()
    showToast(`已将 ${data.total} 条草稿分发至${targetLabel}`)
  } catch(e:any) { showToast(e.response?.data?.detail || '分发商品草稿失败') }
  finally { dispatchingDraftStage.value='' }
}
function openBatchCarouselDialog() {
  if (!batchCarouselEligible.value) { showToast('仅可选择尚未创建轮播图任务的待制作草稿'); return }
  const defaultProvider = availableAiProviders.value.find(item=>item.is_default)?.provider || availableAiProviders.value[0]?.provider || ''
  batchCarouselParams.value={prompt:carouselParams.value.prompt || '保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图',provider:defaultProvider,ratio:carouselParams.value.ratio,quality:carouselParams.value.quality}
  batchCarouselSelections.value=Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, (draft.sku_items || []).map((item:any)=>item.sku).filter(Boolean)]))
  showBatchCarouselDialog.value=true
}
function toggleBatchCarouselSku(draftId:number, sku:string) {
  const selected=batchCarouselSelections.value[draftId] || []
  batchCarouselSelections.value={...batchCarouselSelections.value,[draftId]:selected.includes(sku)?selected.filter(item=>item!==sku):[...selected,sku]}
}
function uniqueMainReferenceItems(items:any[]):any[] {
  const seen=new Set<string>()
  return items.filter(item=>{const url=String(item?.image_url || '').trim();if(!url || seen.has(url))return false;seen.add(url);return true})
}
function mainCarouselItems(draft:any):any[] { return uniqueMainReferenceItems((draft?.carousel_items || []).filter((item:any)=>item && item.source_type!=='sku' && item.source_type!=='main_image')) }
function mainSkuItems(draft:any):any[] { return uniqueMainReferenceItems(draft?.sku_items || []) }
function batchMainImageEffectiveMode(draft:any):MainReferenceMode { return batchMainImageReferenceMode.value==='random_carousel' && !mainCarouselItems(draft).length ? 'random_sku' : batchMainImageReferenceMode.value }
function batchMainImageReferenceItems(draft:any):any[] { return batchMainImageEffectiveMode(draft)==='random_sku' ? mainSkuItems(draft) : mainCarouselItems(draft) }
function openBatchMainImageDialog() {
  if (!batchMainImageEligible.value) { showToast('仅可选择尚未创建首图任务的待制作主图草稿'); return }
  const defaultProvider=availableAiProviders.value.find(item=>item.is_default)?.provider || availableAiProviders.value[0]?.provider || ''
  batchMainImageParams.value={prompt:mainParams.value.prompt || '以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然，保持款式与颜色准确',provider:defaultProvider,ratio:mainParams.value.ratio,quality:mainParams.value.quality}
  batchMainImageReferenceMode.value='random_carousel'
  batchMainImageSelections.value=Object.fromEntries(selectedDrafts.value.map(draft=>[draft.id,[]]))
  showBatchMainImageDialog.value=true
}
function toggleBatchMainImageReference(draftId:number, url:string) {
  const selected=batchMainImageSelections.value[draftId] || []
  batchMainImageSelections.value={...batchMainImageSelections.value,[draftId]:selected.includes(url)?selected.filter(item=>item!==url):[...selected,url].slice(0,9)}
}
function batchReviewTasks(draft:any) { return (draft.tasks || []).filter((task:any)=>task.result_urls?.length) }
function batchReviewPendingTasks(draft:any) { return batchReviewTasks(draft).filter((task:any)=>task.status==='awaiting_selection') }
function batchReviewSelectedCount(draft:any) { return batchReviewTasks(draft).filter((task:any)=>(batchImageReviewSelections.value[task.id] || []).length).length }
function batchReviewTotalTasks() { return batchImageReviewDrafts.value.reduce((total,draft)=>total+batchReviewTasks(draft).length,0) }
function batchReviewChosenTasks() { return Object.values(batchImageReviewSelections.value).filter(urls=>urls.length).length }
function toggleBatchReviewResult(task:any,url:string) {
  if (task.status !== 'awaiting_selection') return
  const selected=batchImageReviewSelections.value[task.id] || []
  const next=batchImageReviewType.value==='main_image'
    ? (selected.includes(url) ? [] : [url])
    : (selected.includes(url) ? selected.filter(item=>item!==url) : [...selected,url])
  batchImageReviewSelections.value={...batchImageReviewSelections.value,[task.id]:next}
}
function selectAllBatchReviewTasks(draft?:any) {
  const targets=draft ? [draft] : batchImageReviewDrafts.value
  const next={...batchImageReviewSelections.value}
  for (const item of targets) for (const task of batchReviewPendingTasks(item)) next[task.id]=batchImageReviewType.value==='main_image' ? [task.result_urls[0]] : [...task.result_urls]
  batchImageReviewSelections.value=next
}
function clearBatchReviewDraft(draft:any) {
  const next={...batchImageReviewSelections.value}
  for (const task of batchReviewPendingTasks(draft)) next[task.id]=[]
  batchImageReviewSelections.value=next
}
async function openBatchImageReview(type:'carousel'|'main_image') {
  const eligible=type==='carousel' ? batchCarouselReviewEligible.value : batchMainImageReviewEligible.value
  if (!eligible) { showToast(`请选择同处于待审核状态的${type==='carousel'?'轮播图':'首图'}草稿`); return }
  batchImageReviewType.value=type; batchImageReviewDrafts.value=[]; batchImageReviewSelections.value={}; batchCarouselReviewNextStage.value='main_image_pending'; showBatchImageReviewDialog.value=true
  try {
    batchImageReviewLoading.value=true
    const {data}=await api.get('/drafts/batch-image-review',{headers:headers.value,params:{draft_ids:selectedDraftIds.value,task_type:type},paramsSerializer:{indexes:null}})
    batchImageReviewDrafts.value=data.items || []
    const adopted:Record<number,string[]>={}
    for (const draft of batchImageReviewDrafts.value) for (const task of batchReviewTasks(draft)) {
      const adoptedUrls=(draft.carousel_items || []).filter((item:any)=>item.task_id===task.id).map((item:any)=>item.image_url)
      adopted[task.id]=adoptedUrls.length ? adoptedUrls : (task.selected_result_url ? [task.selected_result_url] : [])
    }
    batchImageReviewSelections.value=adopted
  } catch(e:any) { showToast(e.response?.data?.detail || '加载批量审核候选图失败'); showBatchImageReviewDialog.value=false }
  finally { batchImageReviewLoading.value=false }
}
async function confirmBatchImageReview() {
  const selections=batchImageReviewDrafts.value.flatMap(draft=>batchReviewTasks(draft).flatMap((task:any)=>{
    const result_urls=batchImageReviewSelections.value[task.id] || []
    return result_urls.length ? [{draft_id:draft.id,task_id:task.id,result_urls}] : []
  }))
  if (!selections.length) { showToast('请至少选择一张候选图后再确认'); return }
  try {
    batchImageReviewSaving.value=true
    const {data}=await api.post('/drafts/batch-image-review/confirm',{task_type:batchImageReviewType.value,selections,...(batchImageReviewType.value==='carousel'?{next_stage:batchCarouselReviewNextStage.value}:{})},{headers:headers.value})
    showBatchImageReviewDialog.value=false; selectedDraftIds.value=[]; await refreshDraftList()
    const stageLabel=batchImageReviewType.value==='carousel' ? (batchCarouselReviewNextStage.value==='ready_to_publish'?'待发布':'首图创作') : '待发布'
    showToast(`已确认 ${data.reviewed_tasks} 个任务；${data.advanced_drafts} 条草稿进入${stageLabel}`)
  } catch(e:any) { showToast(e.response?.data?.detail || '批量确认图片失败') }
  finally { batchImageReviewSaving.value=false }
}
async function createBatchCarouselTasks() {
  if (!batchCarouselParams.value.prompt.trim()) { showToast('请填写轮播图的创作要求'); return }
  const batchDrafts=selectedDrafts.value.map(draft=>({draft_id:draft.id,source_skus:batchCarouselSelections.value[draft.id] || []}))
  if (batchDrafts.some(item=>!item.source_skus.length)) { showToast('每个草稿至少选择一张 SKU 图'); return }
  try {
    batchCarouselSaving.value=true
    const {data}=await api.post('/drafts/batch-carousel-tasks',{drafts:batchDrafts,provider:batchCarouselParams.value.provider,ratio:batchCarouselParams.value.ratio,quality:providerUsesAutoQuality(batchCarouselParams.value.provider)?'auto':batchCarouselParams.value.quality,creative_requirement:batchCarouselParams.value.prompt.trim()},{headers:headers.value})
    showBatchCarouselDialog.value=false; selectedDraftIds.value=[]; await refreshDraftList()
    showToast(`已为 ${data.draft_total} 条草稿创建 ${data.total} 条轮播图任务`)
  } catch(e:any) { showToast(e.response?.data?.detail || '批量创建轮播图任务失败') }
  finally { batchCarouselSaving.value=false }
}
async function createBatchMainImageTasks() {
  if (!batchMainImageParams.value.prompt.trim()) { showToast('请填写首图的创作要求'); return }
  const batchDrafts=selectedDrafts.value.map(draft=>({draft_id:draft.id,reference_urls:batchMainImageReferenceMode.value==='manual' ? [...new Set(batchMainImageSelections.value[draft.id] || [])] : []}))
  if (batchMainImageReferenceMode.value==='manual' && batchDrafts.some(item=>!item.reference_urls.length)) { showToast('每个草稿至少选择一张参考图'); return }
  if (batchMainImageReferenceMode.value!=='manual' && selectedDrafts.value.some(draft=>!batchMainImageReferenceItems(draft).length)) { showToast('所选草稿缺少可用于制作首图的轮播图或 SKU 图'); return }
  try {
    batchMainImageSaving.value=true
    const {data}=await api.post('/drafts/batch-main-image-tasks',{drafts:batchDrafts,reference_mode:batchMainImageReferenceMode.value,provider:batchMainImageParams.value.provider,ratio:batchMainImageParams.value.ratio,quality:providerUsesAutoQuality(batchMainImageParams.value.provider)?'auto':batchMainImageParams.value.quality,creative_requirement:batchMainImageParams.value.prompt.trim()},{headers:headers.value})
    showBatchMainImageDialog.value=false; selectedDraftIds.value=[]; await refreshDraftList()
    showToast(`已为 ${data.draft_total} 条草稿创建 ${data.total} 条首图任务`)
  } catch(e:any) { showToast(e.response?.data?.detail || '批量创建首图任务失败') }
  finally { batchMainImageSaving.value=false }
}
async function skipDraftCarousel(draft:any) {
  try {
    skippingCarouselDraftId.value=draft.id
    await api.post(`/drafts/${draft.id}/skip-carousel`,{}, {headers:headers.value})
    await refreshDraftList()
    showToast('已跳过轮播图制作，请继续制作主图')
  } catch(e:any) { showToast(e.response?.data?.detail || '跳过轮播图失败') }
  finally { skippingCarouselDraftId.value=null }
}
async function batchSkipDraftCarousel() {
  if (!batchCarouselSkipEligible.value) { showToast('仅可批量跳过待制作轮播图阶段的草稿'); return }
  try {
    batchCarouselSkipping.value=true
    const {data}=await api.post('/drafts/batch-skip-carousel',{draft_ids:selectedDraftIds.value},{headers:headers.value})
    selectedDraftIds.value=[]
    await refreshDraftList()
    showToast(`已跳过 ${data.total} 条草稿的轮播图制作`)
  } catch(e:any) { showToast(e.response?.data?.detail || '批量跳过轮播图制作失败') }
  finally { batchCarouselSkipping.value=false }
}
async function skipDraftMainImage(draft:any) {
  try {
    skippingMainImageDraftId.value=draft.id
    await api.post(`/drafts/${draft.id}/skip-main-image`,{}, {headers:headers.value})
    await refreshDraftList()
    showToast('已跳过首图制作，草稿已进入待发布')
  } catch(e:any) { showToast(e.response?.data?.detail || '跳过首图制作失败') }
  finally { skippingMainImageDraftId.value=null }
}
async function batchSkipDraftMainImage() {
  if (!batchMainImageSkipEligible.value) { showToast('仅可批量跳过待制作主图阶段的草稿'); return }
  try {
    batchMainImageSkipping.value=true
    const {data}=await api.post('/drafts/batch-skip-main-image',{draft_ids:selectedDraftIds.value},{headers:headers.value})
    selectedDraftIds.value=[]
    await refreshDraftList()
    showToast(`已跳过 ${data.total} 条草稿的首图制作`)
  } catch(e:any) { showToast(e.response?.data?.detail || '批量跳过首图制作失败') }
  finally { batchMainImageSkipping.value=false }
}
const taskPageCount = computed(() => Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value)))
const visibleTaskPage = computed(() => Math.min(currentTaskPage.value, taskPageCount.value))
const pagedTasks = computed(() => tasks.value)
const claimablePagedTasks = computed(() => pagedTasks.value.filter(task => ['awaiting_selection', 'completed'].includes(task.status) && (task.result_count || task.result_urls?.length)))
const retryablePagedTasks = computed(() => pagedTasks.value.filter(task => task.status === 'failed'))
const selectablePagedTasks = computed(() => pagedTasks.value.filter(task => task.status === 'failed' || activeTaskType.value === 'sku_image' && claimablePagedTasks.value.some(item => item.id === task.id)))
const selectedClaimableTaskIds = computed(() => claimablePagedTasks.value.filter(task => selectedTaskIds.value.includes(task.id)).map(task => task.id))
const selectedRetryTaskIds = computed(() => retryablePagedTasks.value.filter(task => selectedTaskIds.value.includes(task.id)).map(task => task.id))
const allSelectableTasksSelected = computed(() => Boolean(selectablePagedTasks.value.length) && selectablePagedTasks.value.every(task => selectedTaskIds.value.includes(task.id)))
const someSelectableTasksSelected = computed(() => !allSelectableTasksSelected.value && selectablePagedTasks.value.some(task => selectedTaskIds.value.includes(task.id)))
const groupedBatchClaimItems = computed(() => {
  const groups = new Map<number, {taskId:number; taskLabel:string; urls:string[]}>()
  batchClaimItems.value.forEach(item => {
    const group = groups.get(item.taskId) || { taskId: item.taskId, taskLabel: item.taskLabel, urls: [] }
    group.urls.push(item.url); groups.set(item.taskId, group)
  })
  return [...groups.values()]
})
const allBatchClaimImagesSelected = computed(() => Boolean(batchClaimItems.value.length) && batchClaimItems.value.every(item => selectedBatchClaimImages.value.has(batchClaimImageKey(item.taskId, item.url))))
function createImageHoverPreview(event: Event, url: string, alt: string): ImageHoverPreview | null {
  if (event instanceof PointerEvent && event.pointerType === 'touch') return null
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const margin = 16, gap = 14
  const width = Math.min(360, window.innerWidth - margin * 2)
  const height = Math.min(480, window.innerHeight - margin * 2)
  const beside = rect.right + gap + width <= window.innerWidth - margin ? rect.right + gap : rect.left - gap - width
  return {
    url: imageUrl(url), alt, width, height,
    left: Math.max(margin, Math.min(beside, window.innerWidth - width - margin)),
    top: Math.max(margin, Math.min(rect.top + rect.height / 2 - height / 2, window.innerHeight - height - margin)),
  }
}
function showBatchClaimHoverPreview(event: Event, url: string, alt: string) {
  batchClaimHoverPreview.value = createImageHoverPreview(event, url, alt)
}
function showMaterialHoverPreview(event: Event, url: string, alt: string) {
  materialHoverPreview.value = createImageHoverPreview(event, url, alt)
}
function clearImageHoverPreviews() {
  batchClaimHoverPreview.value = null
  materialHoverPreview.value = null
}
watch([showMaterialUploadDialog, showMaterialImportDialog], () => { materialHoverPreview.value = null })
watch(showBatchClaimDialog, () => { batchClaimHoverPreview.value = null })
watch(batchClaiming, () => { batchClaimHoverPreview.value = null })
function batchClaimImageKey(taskId: number, url: string) { return `${taskId}:${url}` }
function toggleBatchClaimImage(taskId: number, url: string) {
  if (batchClaiming.value) return
  const key = batchClaimImageKey(taskId, url)
  if (selectedBatchClaimImages.value.has(key)) selectedBatchClaimImages.value.delete(key)
  else selectedBatchClaimImages.value.add(key)
}
function toggleAllBatchClaimImages() {
  if (batchClaimLoading.value || batchClaiming.value) return
  selectedBatchClaimImages.value = allBatchClaimImagesSelected.value ? new Set() : new Set(batchClaimItems.value.map(item => batchClaimImageKey(item.taskId, item.url)))
}
function syncTaskUrl() { if (page.value !== 'tasks') return; void router.replace({ name: 'tasks', query: { task_type:activeTaskType.value, task_page:String(currentTaskPage.value), task_page_size:String(taskPageSize.value), task_creator:taskCreatorFilterId.value ? String(taskCreatorFilterId.value) : 'all', task_status:taskStatusFilter.value, ...(taskCreatedFrom.value ? {task_from:taskCreatedFrom.value} : {}), ...(taskCreatedTo.value ? {task_to:taskCreatedTo.value} : {}), ...(activeTaskType.value==='sku_image' && taskSkuQuery.value.trim() ? {task_skus:taskSkuQuery.value} : {}), ...(activeTaskType.value==='sku_image' && taskTemplateFilterId.value ? {task_template:String(taskTemplateFilterId.value)} : {}) } }) }
function clearTaskUrl() { if (route.query.task_type) void router.replace({ name: page.value }) }
watch(page,value=>{
  if (user.value?.role === 'supply_user' && value !== 'supply') { void router.replace({name:'supply'}); return }
  value==='tasks'?syncTaskUrl():clearTaskUrl()
  shopError.value = ''
  if (value === 'shops') void loadHubUploadTasks()
  if (value === 'creative-resources') void enterCreativeResources()
  if (value === 'materials') void loadMaterialStyles()
  if (value === 'product-library') {
    if (user.value?.role !== 'company_admin' && activeProductLibraryTab.value === 'shops') activeProductLibraryTab.value = 'products'
    if (user.value?.role === 'company_admin') void loadProductLibraryStatisticsStatus()
    if (activeProductLibraryTab.value === 'shops') void loadProductLibraryShops()
    else if (activeProductLibraryTab.value === 'products') void loadProductLibrary(true)
    else if (activeProductLibraryTab.value === 'stagnant') void loadStagnantMaterials()
    else if (activeProductLibraryTab.value === 'new_images') void loadNewImages()
    else if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) void loadProductLibraryRankingTab()
  }
  else { selectedProductLibraryIds.value = []; stagnantRequestId++; newImagesRequestId++; closeProductLibraryOrders() }
})
function applyTaskPage(data: any) {
  tasks.value = data.items || []
  taskTotal.value = data.total || 0
  taskTypeTotals.value = {...taskTypeTotals.value, ...(data.task_type_counts || {})}
  taskTypeFilteredTotals.value = {...taskTypeFilteredTotals.value, [activeTaskType.value]:data.total || 0}
  taskActiveCount.value = data.active_count || 0
  taskStatusCounts.value = data.status_counts || {}
  currentTaskPage.value = data.page || 1
  const selectableIds = new Set(tasks.value.filter(task => taskCanBeSelected(task)).map(task => task.id))
  selectedTaskIds.value = selectedTaskIds.value.filter(id => selectableIds.has(id))
  if (page.value === 'tasks') syncTaskUrl()
}
async function changeTaskPageSize() { if (taskListRefreshing.value) return; currentTaskPage.value = 1; selectedTaskIds.value = []; syncTaskUrl(); await refreshTaskList() }
async function changeTaskPage(targetPage: number) { if (taskListRefreshing.value) return; currentTaskPage.value = Math.min(Math.max(1, targetPage), taskPageCount.value); selectedTaskIds.value = []; syncTaskUrl(); await refreshTaskList() }
function taskQueryParams() { return { page: currentTaskPage.value, page_size: taskPageSize.value, task_type: activeTaskType.value, creator_id: appliedTaskFilters.value.creator_id ?? undefined, status: appliedTaskFilters.value.status || undefined, created_from: appliedTaskFilters.value.created_from || undefined, created_to: appliedTaskFilters.value.created_to || undefined, sku_query: activeTaskType.value==='sku_image' ? appliedTaskFilters.value.sku_query.trim() || undefined : undefined, template_id: activeTaskType.value==='sku_image' ? appliedTaskFilters.value.template_id ?? undefined : undefined } }
function snapshotTaskTab() {
  taskTabStates.value[activeTaskType.value] = { page:currentTaskPage.value, pageSize:taskPageSize.value, creator:taskCreatorFilterId.value, status:taskStatusFilter.value, from:taskCreatedFrom.value, to:taskCreatedTo.value, skuQuery:taskSkuQuery.value, templateId:taskTemplateFilterId.value, applied:{...appliedTaskFilters.value} }
}
async function switchTaskType(rawType:string) {
  const type=rawType as TaskType
  if (type===activeTaskType.value) return
  snapshotTaskTab(); activeTaskType.value=type
  const state=taskTabStates.value[type]
  currentTaskPage.value=state?.page || 1; taskPageSize.value=state?.pageSize || 20
  taskCreatorFilterId.value=state?.creator ?? user.value?.id ?? null; taskStatusFilter.value=state?.status ?? ''; taskCreatedFrom.value=state?.from || ''; taskCreatedTo.value=state?.to || ''
  taskSkuQuery.value=state?.skuQuery || ''
  taskTemplateFilterId.value=state?.templateId ?? null
  appliedTaskFilters.value=state?.applied || {creator_id:taskCreatorFilterId.value,status:taskStatusFilter.value,created_from:'',created_to:'',sku_query:'',template_id:null}
  selectedTaskIds.value=[]
  syncTaskUrl()
  await refreshTaskList()
}
function taskTypeLabel(task:any) { return taskTypeLabels[(task?.task_type || 'sku_image') as TaskType] || 'SKU图' }
function toUtcIso(value: string) { return value ? new Date(value).toISOString() : '' }
async function searchTasks() {
  if (taskCreatedFrom.value && taskCreatedTo.value && new Date(taskCreatedFrom.value) > new Date(taskCreatedTo.value)) { showToast('创建开始时间不能晚于结束时间'); return }
  appliedTaskFilters.value = { creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: toUtcIso(taskCreatedFrom.value), created_to: toUtcIso(taskCreatedTo.value), sku_query: activeTaskType.value==='sku_image' ? taskSkuQuery.value : '', template_id: activeTaskType.value==='sku_image' ? taskTemplateFilterId.value : null }
  currentTaskPage.value = 1
  selectedTaskIds.value = []
  syncTaskUrl()
  await refreshTaskList()
}
const materialPageCount = computed(() => Math.max(1, Math.ceil(materialTotal.value / materialPageSize.value)))
const visibleMaterialPage = computed(() => Math.min(currentMaterialPage.value, materialPageCount.value))
function applyMaterialPage(data: any) { materialAssets.value = data.items || []; materialTotal.value = data.total || 0; currentMaterialPage.value = data.page || 1 }
async function changeMaterialPageSize() { if (materialListRefreshing.value) return; currentMaterialPage.value = 1; await refreshMaterialList() }
async function changeMaterialPage(targetPage: number) { if (materialListRefreshing.value) return; currentMaterialPage.value = Math.min(Math.max(1, targetPage), materialPageCount.value); await refreshMaterialList() }
async function searchMaterials() {
  if (materialListRefreshing.value) return
  if (materialCreatedFrom.value && materialCreatedTo.value && new Date(materialCreatedFrom.value) > new Date(materialCreatedTo.value)) { showToast('创建开始时间不能晚于结束时间'); return }
  appliedMaterialFilters.value = {template_id:materialTemplateFilterId.value, creator_id:materialCreatorFilterId.value, style_id:materialStyleFilterId.value, source_type:materialSourceTypeFilter.value, created_from:toUtcIso(materialCreatedFrom.value), created_to:toUtcIso(materialCreatedTo.value)}
  currentMaterialPage.value = 1
  await refreshMaterialList()
}
async function changeMaterialUsageTab(tab: MaterialUsageTab) { if (activeMaterialUsageTab.value === tab || materialListRefreshing.value) return; activeMaterialUsageTab.value = tab; currentMaterialPage.value = 1; selectedMaterialAssetIds.value = []; await refreshMaterialList() }
async function refreshMaterialList() {
  try {
    materialListRefreshing.value = true
    selectedMaterialAssetIds.value = []
    const { data } = await api.get('/material-assets', { headers: headers.value, params: materialQueryParams() })
    applyMaterialPage(data)
  } catch (e:any) { showToast(e.response?.data?.detail || '刷新素材列表失败') }
  finally { materialListRefreshing.value = false }
}
const productLibraryPageCount = computed(() => Math.max(1, Math.ceil(productLibraryTotal.value / productLibraryPageSize.value)))
const productLibraryRankingPageCount = computed(() => Math.max(1, Math.ceil(productLibraryRankingTotal.value / productLibraryRankingPageSize.value)))
const stagnantPageCount = computed(() => Math.max(1, Math.ceil(stagnantTotal.value / stagnantPageSize.value)))
const newImagesPageCount = computed(() => Math.max(1, Math.ceil(newImagesTotal.value / newImagesPageSize.value)))
const productLibraryOrderPageCount = computed(() => Math.max(1, Math.ceil(productLibraryOrderTotal.value / productLibraryOrderPageSize.value)))
const selectableProductLibraryItems = computed(() => activeProductLibraryTab.value === 'products' ? productLibraryItems.value : activeProductLibraryTab.value === 'stagnant' ? stagnantMaterials.value : activeProductLibraryTab.value === 'new_images' ? newImages.value : productLibraryRankingItems.value)
const productLibrarySelectionLoading = computed(() => productLibraryLoading.value || productLibraryRankingLoading.value || stagnantLoading.value || newImagesLoading.value)
const draftSelectionAssets = computed(() => libraryDraftMode.value ? libraryDraftSelection.value : selectedMaterialAssets.value)
const draftSelectionTemplateId = computed(() => libraryDraftMode.value ? libraryDraftSelection.value[0]?.template_id : selectedMaterialTemplateId.value)
watch([libraryDraftMode, draftSelectionTemplateId, token], () => materialBatchTitleGenerator.reset(), { flush: 'sync' })
const allPagedProductsSelected = computed(() => selectableProductLibraryItems.value.length > 0 && selectableProductLibraryItems.value.every(item => selectedProductLibraryIds.value.includes(item.id)))
async function loadProductLibraryShops() {
  if (user.value?.role !== 'company_admin') return
  try {
    productLibraryShopsLoading.value = true
    const {data} = await api.get('/product-library/shops', {headers:headers.value})
    productLibraryShops.value = data || []
  } catch(e:any) { showProductLibraryErrorToast(e, '加载产品库店铺失败') }
  finally { productLibraryShopsLoading.value = false }
}
async function assignProductLibraryShop(shop:any, event:Event) {
  const select = event.target as HTMLSelectElement
  const value = select.value
  const assigned_user_id = value ? Number(value) : null
  try {
    productLibraryAssigningId.value = shop.id
    await api.put(`/product-library/shops/${shop.id}/assignment`, {assigned_user_id}, {headers:headers.value})
    shop.assigned_user_id = assigned_user_id
    shop.assigned_user_name = members.value.find(member => member.id === assigned_user_id)?.name || null
    showToast('店铺负责人已更新')
  } catch(e:any) {
    select.value = shop.assigned_user_id == null ? '' : String(shop.assigned_user_id)
    showProductLibraryErrorToast(e, '分配店铺失败')
  } finally { productLibraryAssigningId.value = null }
}
async function loadProductLibraryRankingTab() {
  try {
    const {data} = await api.get('/product-library/filters', {headers:headers.value})
    productLibraryFilters.value = data
  } catch(e:any) { showProductLibraryErrorToast(e, '加载店铺筛选失败') }
  await loadProductLibraryRankings()
}
async function loadProductLibrary(withFilters = false) {
  try {
    productLibraryLoading.value = true
    const applied = appliedProductLibraryFilters.value
    const params = {page:productLibraryPage.value, page_size:productLibraryPageSize.value,
      source_ids:applied.sourceIds.length ? applied.sourceIds : undefined, sku:applied.sku || undefined,
      template_id:applied.template && applied.template !== 'unmatched' ? Number(applied.template) : undefined,
      unmatched:applied.template === 'unmatched' ? true : undefined, creator_id:applied.creatorId || undefined}
    const [list, filters] = await Promise.all([
      api.get('/product-library', {headers:headers.value, params, paramsSerializer:{indexes:null}}),
      withFilters ? api.get('/product-library/filters', {headers:headers.value}) : Promise.resolve(null),
    ])
    productLibraryItems.value = list.data.items || []
    productLibraryTotal.value = list.data.total || 0
    productLibraryBrokenImages.value = []
    if (filters) productLibraryFilters.value = filters.data
  } catch(e:any) { showProductLibraryErrorToast(e, '加载产品库失败') }
  finally { productLibraryLoading.value = false }
}
function showProductLibraryErrorToast(error:any, fallback:string): string {
  const detail = error.response?.data?.detail
  const message = typeof detail === 'string' && detail.trim() ? detail : fallback
  showToast(message)
  return message
}
async function loadProductLibraryRankings() {
  selectedProductLibraryIds.value = []
  if (!productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) return
  const requestId = ++productLibraryRankingRequestId
  const category = activeProductLibraryTab.value
  const isTop50 = productLibraryTopTabKeys.has(category)
  try {
    productLibraryRankingLoading.value = true
    productLibraryRankingError.value = ''
    const {data} = await api.get('/product-library/rankings', {headers:headers.value, params:{category, page:isTop50 ? 1 : productLibraryRankingPage.value, page_size:isTop50 ? 50 : productLibraryRankingPageSize.value,
      source_ids:rankingShopFilters.value[category]?.length ? rankingShopFilters.value[category] : undefined, creator_id:rankingCreatorFilters.value[category] || undefined}, paramsSerializer:{indexes:null}})
    if (requestId !== productLibraryRankingRequestId) return
    productLibraryRankingItems.value = data.items || []
    productLibraryRankingTotal.value = data.total || 0
    productLibraryRankingDate.value = data.snapshot_date || null
    productLibraryRankingThroughDate.value = data.through_date || null
    productLibraryBrokenImages.value = []
  } catch(e:any) {
    if (requestId === productLibraryRankingRequestId)
      productLibraryRankingError.value = showProductLibraryErrorToast(e, '加载榜单失败')
  } finally {
    if (requestId === productLibraryRankingRequestId) productLibraryRankingLoading.value = false
  }
}
async function loadStagnantMaterials() {
  selectedProductLibraryIds.value = []
  const requestId = ++stagnantRequestId
  try {
    stagnantLoading.value = true
    stagnantError.value = ''
    const {data} = await api.get('/product-library/stagnant', {headers:headers.value, params:{
      page:stagnantPage.value, page_size:stagnantPageSize.value,
      creator_id:user.value?.role === 'company_admin' ? stagnantCreatorId.value : undefined,
    }})
    if (requestId !== stagnantRequestId) return
    stagnantMaterials.value = data.items || []
    stagnantTotal.value = data.total || 0
    stagnantPage.value = data.page || 1
    productLibraryBrokenImages.value = []
  } catch(e:any) {
    if (requestId === stagnantRequestId)
      stagnantError.value = showProductLibraryErrorToast(e, '加载滞销素材失败')
  } finally {
    if (requestId === stagnantRequestId) stagnantLoading.value = false
  }
}
function changeStagnantCreator() { stagnantPage.value = 1; void loadStagnantMaterials() }
function changeStagnantPageSize() { stagnantPage.value = 1; void loadStagnantMaterials() }
function changeStagnantPage(next:number) {
  if (stagnantLoading.value || next < 1 || next > stagnantPageCount.value) return
  stagnantPage.value = next
  void loadStagnantMaterials()
}
async function loadNewImages() {
  selectedProductLibraryIds.value = []
  const requestId = ++newImagesRequestId
  try {
    newImagesLoading.value = true
    newImagesError.value = ''
    const {data} = await api.get('/product-library/new-images', {headers:headers.value, params:{
      page:newImagesPage.value, page_size:newImagesPageSize.value,
      creator_id:user.value?.role === 'company_admin' ? newImagesCreatorId.value : undefined,
      usage_status:newImagesUsageStatus.value,
    }})
    if (requestId !== newImagesRequestId) return
    newImages.value = data.items || []
    newImagesTotal.value = data.total || 0
    newImagesPage.value = data.page || 1
    productLibraryBrokenImages.value = []
  } catch(e:any) {
    if (requestId === newImagesRequestId)
      newImagesError.value = showProductLibraryErrorToast(e, '加载新图失败')
  } finally {
    if (requestId === newImagesRequestId) newImagesLoading.value = false
  }
}
function changeNewImagesFilters() { newImagesPage.value = 1; void loadNewImages() }
function changeNewImagesPageSize() { newImagesPage.value = 1; void loadNewImages() }
function changeNewImagesPage(next:number) {
  if (newImagesLoading.value || next < 1 || next > newImagesPageCount.value) return
  newImagesPage.value = next
  void loadNewImages()
}
function changeProductLibraryRankingPage(next:number) {
  if (productLibraryTopTabKeys.has(activeProductLibraryTab.value) || productLibraryRankingLoading.value || next < 1 || next > productLibraryRankingPageCount.value) return
  productLibraryRankingPage.value = next
  void loadProductLibraryRankings()
}
function changeProductLibraryRankingPageSize() {
  if (productLibraryTopTabKeys.has(activeProductLibraryTab.value)) return
  productLibraryRankingPage.value = 1
  void loadProductLibraryRankings()
}
function searchProductLibrary() {
  if (productLibraryLoading.value || productLibraryRankingLoading.value) return
  productLibraryShopFilterDetails.value?.removeAttribute('open')
  if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) {
    rankingShopFilters.value[activeProductLibraryTab.value] = [...productLibrarySelectedShopIds.value]
    rankingCreatorFilters.value[activeProductLibraryTab.value] = productLibraryCreatorId.value
    productLibraryRankingPage.value = 1
    selectedProductLibraryIds.value = []
    void loadProductLibraryRankings()
    return
  }
  appliedProductLibraryFilters.value = {
    sourceIds:[...productLibrarySelectedShopIds.value], template:productLibraryTemplateFilter.value,
    sku:productLibrarySku.value.trim(), creatorId:productLibraryCreatorId.value,
  }
  productLibraryPage.value=1
  selectedProductLibraryIds.value=[]
  void loadProductLibrary()
}
function changeProductLibraryPageSize() { productLibraryPage.value=1; selectedProductLibraryIds.value=[]; void loadProductLibrary() }
function changeProductLibraryTab(tab: ProductLibraryTab) {
  if (user.value?.role !== 'company_admin' && tab === 'shops') {
    showToast('当前账号没有此操作权限')
    return
  }
  if (activeProductLibraryTab.value === tab) return
  activeProductLibraryTab.value = tab
  productLibraryCreatorId.value = tab === 'products' ? appliedProductLibraryFilters.value.creatorId : rankingCreatorFilters.value[tab] ?? null
  productLibrarySelectedShopIds.value = [...(tab === 'products' ? appliedProductLibraryFilters.value.sourceIds : rankingShopFilters.value[tab] || [])]
  productLibraryShopSearch.value = ''
  closeProductLibraryOrders()
  selectedProductLibraryIds.value = []
  productLibraryRankingRequestId++
  stagnantRequestId++
  newImagesRequestId++
  if (tab === 'shops') void loadProductLibraryShops()
  else if (tab === 'products') void loadProductLibrary(true)
  else if (tab === 'stagnant') { stagnantPage.value = 1; void loadStagnantMaterials() }
  else if (tab === 'new_images') { newImagesPage.value = 1; void loadNewImages() }
  else if (productLibraryRankingTabKeys.has(tab)) {
    productLibraryRankingPage.value = 1
    productLibraryRankingItems.value = []
    productLibraryRankingTotal.value = 0
    productLibraryRankingDate.value = null
    void loadProductLibraryRankingTab()
  }
}
function changeProductLibraryPage(next:number) {
  if (productLibraryLoading.value || next < 1 || next > productLibraryPageCount.value) return
  productLibraryPage.value=next; void loadProductLibrary()
}
function openProductLibraryOrders(item:any) {
  productLibraryOrderProduct.value = {...item,
    sourceIds:[...(activeProductLibraryTab.value === 'products' ? appliedProductLibraryFilters.value.sourceIds : rankingShopFilters.value[activeProductLibraryTab.value] || [])],
    category:productLibraryRankingTabKeys.has(activeProductLibraryTab.value) ? activeProductLibraryTab.value : undefined,
    snapshotDate:productLibraryRankingTabKeys.has(activeProductLibraryTab.value) ? productLibraryRankingDate.value : undefined,
  }
  productLibraryOrderPage.value = 1
  productLibraryOrders.value = []
  productLibraryOrderTotal.value = 0
  productLibraryOrderCount.value = 0
  void loadProductLibraryOrders()
}
function closeProductLibraryOrders() {
  productLibraryOrderRequestId++
  productLibraryOrderProduct.value = null
  productLibraryOrderLoading.value = false
}
async function loadProductLibraryOrders() {
  const product = productLibraryOrderProduct.value
  if (!product) return
  const requestId = ++productLibraryOrderRequestId
  try {
    productLibraryOrderLoading.value = true
    productLibraryOrders.value = []
    const {data} = await api.get(`/product-library/${product.id}/orders`, {headers:headers.value, params:{page:productLibraryOrderPage.value, page_size:productLibraryOrderPageSize.value,
      source_ids:product.sourceIds.length ? product.sourceIds : undefined,
      category:product.category, snapshot_date:product.snapshotDate}, paramsSerializer:{indexes:null}})
    if (requestId !== productLibraryOrderRequestId) return
    productLibraryOrders.value = data.items || []
    productLibraryOrderTotal.value = data.total || 0
    productLibraryOrderCount.value = data.order_count || 0
  } catch(e:any) {
    if (requestId === productLibraryOrderRequestId) {
      showProductLibraryErrorToast(e, '加载订单详情失败')
      closeProductLibraryOrders()
    }
  } finally {
    if (requestId === productLibraryOrderRequestId) productLibraryOrderLoading.value = false
  }
}
function changeProductLibraryOrderPageSize() { productLibraryOrderPage.value = 1; void loadProductLibraryOrders() }
function changeProductLibraryOrderPage(next:number) {
  if (productLibraryOrderLoading.value || next < 1 || next > productLibraryOrderPageCount.value) return
  productLibraryOrderPage.value = next
  void loadProductLibraryOrders()
}
function toggleProductLibrarySelection(item:any) {
  if (productLibrarySelectionLoading.value) return
  if (selectedProductLibraryIds.value.includes(item.id)) {
    selectedProductLibraryIds.value = selectedProductLibraryIds.value.filter(id => id !== item.id)
  } else if (selectedProductLibraryIds.value.length >= MAX_PRODUCT_LIBRARY_SELECTION) {
    showToast(`一次最多选择 ${MAX_PRODUCT_LIBRARY_SELECTION} 条产品`)
  } else {
    selectedProductLibraryIds.value = [...selectedProductLibraryIds.value, item.id]
  }
}
function togglePagedProducts() {
  if (productLibrarySelectionLoading.value) return
  const ids = selectableProductLibraryItems.value.map(item => item.id)
  if (allPagedProductsSelected.value) {
    selectedProductLibraryIds.value = selectedProductLibraryIds.value.filter(id => !ids.includes(id))
    return
  }
  const merged = [...new Set([...selectedProductLibraryIds.value, ...ids])]
  if (merged.length > MAX_PRODUCT_LIBRARY_SELECTION) { showToast(`一次最多选择 ${MAX_PRODUCT_LIBRARY_SELECTION} 条产品`); return }
  selectedProductLibraryIds.value = merged
}
function openProductLibraryTemplateDialog() {
  if (productLibrarySelectionLoading.value || !selectedProductLibraryIds.value.length || user.value?.role !== 'company_admin' || activeProductLibraryTab.value === 'shops') return
  productLibraryTargetTemplateId.value = null
  showProductLibraryTemplateDialog.value = true
}
async function saveProductLibraryTemplate() {
  if (productLibraryTemplateSaving.value || !productLibraryTargetTemplateId.value || !selectedProductLibraryIds.value.length) return
  try {
    productLibraryTemplateSaving.value = true
    const {data} = await api.post('/product-library/templates/batch', {
      ...(activeProductLibraryTab.value === 'new_images' || activeProductLibraryTab.value === 'stagnant'
        ? {material_asset_ids:selectedProductLibraryIds.value}
        : {product_ids:selectedProductLibraryIds.value}),
      template_id:productLibraryTargetTemplateId.value,
    }, {headers:headers.value})
    showProductLibraryTemplateDialog.value = false
    selectedProductLibraryIds.value = []
    await refreshLibraryDraftSource()
    showToast(`已为 ${data.updated} 条数据设置模版：${data.template}`)
  } catch(e:any) { showToast(e.response?.data?.detail || '批量设置模版失败') }
  finally { productLibraryTemplateSaving.value = false }
}
async function downloadProductLibraryTemplate() {
  try {
    productLibraryDownloading.value = true
    const response = await api.get('/product-library/import-template', {headers:headers.value, responseType:'blob'})
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url; link.download = '产品库导入模版.xlsx'; document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { showToast('下载导入模版失败') }
  finally { productLibraryDownloading.value = false }
}
async function importProductLibrary(event:Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    productLibraryImporting.value = true
    const form = new FormData(); form.append('file', file)
    const {data} = await api.post('/product-library/import', form, {headers:headers.value})
    productLibraryPage.value=1
    selectedProductLibraryIds.value=[]
    await loadProductLibrary(true)
    if (activeProductLibraryTab.value === 'shops') await loadProductLibraryShops()
    if (activeProductLibraryTab.value === 'stagnant') await loadStagnantMaterials()
    showToast(`导入完成：新增 ${data.created_shops} 个店铺、${data.created_products} 个产品、${data.created_orders} 个订单，更新 ${data.updated_products} 个产品`)
  } catch(e:any) { showToast(e.response?.data?.detail || '导入产品库失败') }
  finally { productLibraryImporting.value = false; input.value = '' }
}
async function loadProductLibraryStatisticsStatus() {
  if (!token.value || user.value?.role !== 'company_admin') return
  const currentToken = token.value
  const currentTaskId = productLibraryStatisticsTask.value?.task_id
  try {
    const {data} = await api.get('/product-library/rankings/refresh/status', {headers:headers.value})
    if (currentToken !== token.value) return
    if (currentTaskId !== productLibraryStatisticsTask.value?.task_id) return
    const previous = productLibraryStatisticsTask.value
    productLibraryStatisticsTask.value = data.task
    if (previous?.task_id === data.task?.task_id && ['queued','running'].includes(previous.status) && data.task?.status === 'succeeded') {
      if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) await loadProductLibraryRankings()
      showToast(`数据统计完成：截至 ${data.task.through_date}`)
    }
    if (previous?.task_id === data.task?.task_id && ['queued','running'].includes(previous.status) && data.task?.status === 'failed') showToast('数据统计失败，请重试')
  } catch { /* 轮询失败时保留当前状态，下次继续查询。 */ }
}
async function runProductLibraryStatistics() {
  if (user.value?.role !== 'company_admin' || productLibraryStatisticsSubmitting.value || productLibraryImporting.value) return
  try {
    productLibraryStatisticsSubmitting.value = true
    const {data} = await api.post('/product-library/rankings/refresh', null, {headers:headers.value})
    productLibraryStatisticsTask.value = data.task
    showToast(data.message || (data.existing ? '已有统计任务正在执行' : '统计任务已提交'))
    if (data.task?.status === 'succeeded' && productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) await loadProductLibraryRankings()
  } catch(e:any) { showToast(e.response?.data?.detail || '数据统计失败，请重试') }
  finally { productLibraryStatisticsSubmitting.value = false }
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
  if (user.value.role === 'supply_user') {
    crossCompanyCollectionEnabled.value = false
    tasks.value=[]; materialAssets.value=[]; templates.value=[]; taskActiveCount.value=0
    if (page.value !== 'supply') await router.replace({name:'supply'})
    return
  }
  crossCompanyCollectionEnabled.value = (await api.get('/cross-company-collection/capability',h)).data.enabled
  if (route.meta.requiresCompanyAdmin && user.value.role !== 'company_admin') {
    await router.replace({ name: 'dashboard' })
    showToast('当前账号没有访问该管理页面的权限')
  }
  if (!creatorFiltersInitialized.value) {
    if (!initialTaskParams.has('task_creator')) taskCreatorFilterId.value = user.value.id
    appliedTaskFilters.value.creator_id = taskCreatorFilterId.value
    materialCreatorFilterId.value = user.value.id
    appliedMaterialFilters.value.creator_id = user.value.id
    draftCreatorFilterId.value = user.value.id
    creatorFiltersInitialized.value = true
  }
  const [s, t, g, task, material, d, providers, catalogs] = await Promise.all([api.get('/shops',h), api.get('/templates',h), api.get('/template-groups',h), api.get('/tasks',{...h,params:taskQueryParams()}), api.get('/material-assets',{...h,params:materialQueryParams()}), api.get('/drafts',{...h,params:{creator_id:draftCreatorFilterId.value,template_id:draftTemplateFilterId.value,tab:activeDraftTab.value,work_status:activeDraftWorkStatus.value,page:currentDraftPage.value,page_size:draftPageSize.value}}), api.get('/ai-providers',h), api.get('/category-catalogs',h)])
  shops.value=s.data; templates.value=t.data; templateGroups.value=g.data; applyTaskPage(task.data); applyMaterialPage(material.data); drafts.value=d.data.items; draftTotal.value=d.data.total; draftTabCounts.value=d.data.tab_counts; draftWorkStatusCounts.value=d.data.work_status_counts; aiProviders.value=providers.data; tiktokCatalogs.value=catalogs.data
  // 后台停用当前所选模型后，刷新时立即切换到仍启用的默认模型，避免提交已停用的值。
  if (!availableAiProviders.value.some(item => item.provider === creativeProvider.value)) {
    creativeProvider.value = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || ''
  }
  if (user.value.role === 'company_admin') {
    const [companyMembers, companyGroups, companyShops] = await Promise.all([api.get('/members', h), api.get('/operator-groups', h), api.get('/shops/manage', h)])
    members.value = companyMembers.data
    operatorGroups.value = companyGroups.data
    managedShops.value = companyShops.data
  } else { members.value = []; operatorGroups.value = []; managedShops.value = [] }
  if (!selectedTemplateId.value && templates.value[0]) selectedTemplateId.value=templates.value[0].id
  if (selectedTemplateId.value) await loadMyTemplateResources(false)
  if (page.value === 'product-library') {
    if (user.value.role !== 'company_admin' && activeProductLibraryTab.value === 'shops') activeProductLibraryTab.value = 'products'
    if (user.value.role === 'company_admin') void loadProductLibraryStatisticsStatus()
    if (activeProductLibraryTab.value === 'shops') await loadProductLibraryShops()
    else if (activeProductLibraryTab.value === 'products') await loadProductLibrary(true)
    else if (activeProductLibraryTab.value === 'stagnant') await loadStagnantMaterials()
    else if (activeProductLibraryTab.value === 'new_images') await loadNewImages()
    else if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) await loadProductLibraryRankingTab()
  }
  if (page.value === 'shops') await loadHubUploadTasks()
  await loadMaterialStyles()
  if (page.value === 'creative-resources') await enterCreativeResources()
  if (hubAgentPairingCode.value) {
    try {
      const {data} = await api.post('/hub-agent/pairings/complete', {code:hubAgentPairingCode.value}, h)
      if (data.status === 'completed') {
        hubAgentPairingCode.value = ''
        const url = new URL(location.href); url.searchParams.delete('hub_agent_pair'); history.replaceState({}, '', url)
        showToast(`本机执行器 ${data.agent_name || ''} 已授权`)
      }
    } catch (e:any) { showToast(e.response?.data?.detail || '本机执行器配对失败') }
  }
}
async function login() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/auth/login', { email: email.value, password: password.value })
    token.value = data.access_token
    localStorage.setItem('haitoro_token', token.value)
    await refresh()
  } catch (e: any) {
    const detail = e.response?.data?.detail
    error.value = typeof detail === 'string' && detail.trim() ? detail : '登录失败，请检查账号密码'
  } finally {
    loading.value = false
  }
}
function onCreativeAssetChange(event: Event) {
  if (creativeUploading.value) { showToast('图片上传处理中，请等待本轮上传结束'); (event.target as HTMLInputElement).value = ''; return }
  const files = Array.from((event.target as HTMLInputElement).files || [])
  const available = 500 - creativeAssets.value.length
  const supported = files.filter(file => ALLOWED_IMAGE_TYPES.includes(file.type) && file.size > 0 && file.size <= MAX_IMAGE_BYTES)
  supported.slice(0, available).forEach(file => creativeAssets.value.push({ id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`, file, preview: URL.createObjectURL(file) }))
  if (files.length <= available) creativeAssetError.value = ''
  if (supported.length !== files.length) creativeAssetError.value = '仅支持 JPG、PNG、WebP，且单张不能超过 3MB。'
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
  const upload = deduplicatedImageUpload(async (file, sha256) => {
    const {data: target} = await api.post('/uploads/creative-asset/presign', {
      content_type: file.type, content_length: file.size, sha256,
    }, {headers: headers.value})
    if (target.upload_url) {
      await axios.put(target.upload_url, file, {headers: {'Content-Type': file.type}})
    }
    return (await api.post('/uploads/complete', {
      category: 'creative', upload_token: target.upload_token, file_token: target.file_token,
    }, {headers: headers.value})).data.url
  })
  const worker = async () => {
    while (true) {
      const index = cursor++
      if (index >= assets.length) return
      const asset = assets[index]
      if (asset.uploadedUrl) { urls[index] = asset.uploadedUrl; continue }
      asset.uploadedUrl = await upload(asset.file)
      urls[index] = asset.uploadedUrl
      creativeUploadedCount.value++
    }
  }
  const workerResults = await Promise.allSettled(Array.from({length: Math.min(4, assets.length)}, worker))
  const failedWorker = workerResults.find((result): result is PromiseRejectedResult => result.status === 'rejected')
  if (failedWorker) throw failedWorker.reason
  return [...new Set(urls)]
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
    const {data} = await api.post('/tasks',{template_id:selectedTemplateId.value,white_image_id:selectedWhiteImageId.value,provider:creativeProvider.value,ratio:creativeRatio.value,quality:providerUsesAutoQuality(creativeProvider.value)?'auto':creativeQuality.value,print_url:print_urls[0],print_urls,creative_requirement:creativeRequirement.value.trim()},{headers:headers.value})
    activeTaskType.value='sku_image'; currentTaskPage.value = 1
    const taskUrl=new URL(location.href); taskUrl.searchParams.set('task_type','sku_image'); history.replaceState({},'',taskUrl)
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
async function deleteTemplateGroup(group:any) { if (!templateGroupIsEmpty(group.id)) return; if (!confirm(`确定删除空模板分类「${group.name}」吗？`)) return; try { await api.delete(`/template-groups/${group.id}`,{headers:headers.value}); if (activeGroupId.value===group.id) activeGroupId.value=null; await refresh(); showToast('模板分类已删除') } catch (e:any) { showToast(e.response?.data?.detail || '删除模板分类失败') } }
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
let managedResourcesRequestId = 0
async function loadManagedTemplateResources() {
  if(!user.value) return
  const requestId=++managedResourcesRequestId, ownerId=appliedResourceFilters.value.ownerId, companyId=user.value.company_id
  const params={...(ownerId===null ? {scope:'company'} : {user_id:ownerId}),white_image_status:appliedResourceFilters.value.whiteImageStatus}
  managedResourcesLoading.value=true
  try {
    const {data}=await api.get('/user-template-resources',{headers:headers.value,params})
    if(requestId===managedResourcesRequestId && companyId===user.value?.company_id) { managedWhiteImages.value=data.white_images || []; managedPrompts.value=data.prompts || [] }
  } catch(e:any) { if(requestId===managedResourcesRequestId) showToast(e.response?.data?.detail || '加载员工模板资源失败') }
  finally { if(requestId===managedResourcesRequestId) managedResourcesLoading.value=false }
}
async function enterCreativeResources() {
  if (!user.value) return
  const tab=String(route.query.tab || '')
  personalResourceTab.value=['white-images','prompts','styles'].includes(tab) ? tab as 'white-images'|'prompts'|'styles' : 'white-images'
  const templateId=Number(route.query.template)
  resourceTemplateFilterId.value=templates.value.some(item=>item.id===templateId) ? templateId : null
  managedResourceUserId.value=user.value.role==='company_admin' ? null : user.value.id
  resourceWhiteImageStatus.value='active'
  applyResourceFilters()
  resetWhiteImageForm(); resetPersonalPromptForm()
  await Promise.all([loadManagedTemplateResources(),loadMaterialStyles()])
}
function applyResourceFilters() {
  appliedResourceFilters.value={ownerId:managedResourceUserId.value,templateId:resourceTemplateFilterId.value,query:resourceQuery.value.trim().toLowerCase(),whiteImageStatus:resourceWhiteImageStatus.value}
  resourceCurrentPage.value=1
}
async function searchCreativeResources() {
  if(resourceSearchBusy.value) return
  applyResourceFilters()
  const query={...route.query}
  if(appliedResourceFilters.value.templateId) query.template=String(appliedResourceFilters.value.templateId)
  else delete query.template
  void router.replace({name:'creative-resources',query})
  await Promise.all([loadManagedTemplateResources(),loadMaterialStyles()])
}
async function openPersonalResourcesDialog(tab: 'white-images' | 'prompts' = 'white-images') {
  await router.push({name:'creative-resources',query:{tab,...(selectedTemplateId.value ? {template:String(selectedTemplateId.value)} : {})}})
}
watch(() => route.query.tab, tab => { if(page.value==='creative-resources' && ['white-images','prompts','styles'].includes(String(tab))) personalResourceTab.value=tab as 'white-images'|'prompts'|'styles' })
function setResourceTab(tab:'white-images'|'prompts'|'styles') {
  personalResourceTab.value=tab
  void router.replace({name:'creative-resources',query:{...route.query,tab}})
}
function resetWhiteImageForm() { editingWhiteImage.value=null; whiteImageForm.value={template_id:resourceTemplateFilterId.value,name:'',file:null} }
function openResourceEditor(type:'white-images'|'prompts', item:any=null) {
  if(personalResourceSaving.value || (type==='white-images' && item?.deleted_at!=null)) return
  resetWhiteImageForm(); resetPersonalPromptForm(); resourceEditorError.value=''
  resourceEditorUserId.value=item?.user_id || managedResourceUserId.value || user.value?.id || null
  if(item && type==='white-images') { editingWhiteImage.value=item; whiteImageForm.value={template_id:item.template_id,name:item.name,file:null} }
  if(item && type==='prompts') { editingPersonalPrompt.value=item; personalPromptForm.value={template_id:item.template_id,name:item.name,content:item.content} }
  resourceEditorType.value=type
}
function closeResourceEditor() {
  if(personalResourceSaving.value) return
  resourceEditorType.value=null; resourceEditorError.value=''; resourceEditorUserId.value=null; resetWhiteImageForm(); resetPersonalPromptForm()
}
async function saveResourceEditor() {
  if(resourceEditorType.value==='white-images') await saveWhiteImage()
  else if(resourceEditorType.value==='prompts') await savePersonalPrompt()
}
watch(personalResourceTab, closeResourceEditor)
watch(page, value => { if(value!=='creative-resources') closeResourceEditor() })
function validUploadImageFile(file: File) {
  if (ALLOWED_IMAGE_TYPES.includes(file.type) && file.size > 0 && file.size <= MAX_IMAGE_BYTES) return true
  showToast('仅支持 JPG、PNG、WebP，且单张不能超过 3MB')
  return false
}
function onWhiteImageFileChange(event:Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  if (file && !validUploadImageFile(file)) { input.value = ''; whiteImageForm.value.file=null; return }
  whiteImageForm.value.file = file
}
async function saveWhiteImage() {
  if(personalResourceSaving.value) return
  resourceEditorError.value=''
  if (!whiteImageForm.value.template_id) { resourceEditorError.value='请先选择产品模板'; return }
  if (!resourceEditorUserId.value || !whiteImageForm.value.name.trim()) { resourceEditorError.value='请填写白底图名称'; return }
  if (!editingWhiteImage.value && !whiteImageForm.value.file) { resourceEditorError.value='请上传白底图'; return }
  try {
    personalResourceSaving.value=true
    let image_url: string | undefined
    if (!editingWhiteImage.value && whiteImageForm.value.file) image_url = await presignAndUploadImage(whiteImageForm.value.file, 'template-white')
    if (editingWhiteImage.value) await api.put(`/user-template-white-images/${editingWhiteImage.value.id}`,{name:whiteImageForm.value.name.trim()},{headers:headers.value})
    else await api.post('/user-template-white-images',{template_id:whiteImageForm.value.template_id,user_id:resourceEditorUserId.value,name:whiteImageForm.value.name.trim(),image_url},{headers:headers.value})
    if(!editingWhiteImage.value) resourceCurrentPage.value=1
    resourceEditorType.value=null; resetWhiteImageForm(); await Promise.all([loadManagedTemplateResources(),loadMaterialStyles()]); if(resourceEditorUserId.value===user.value.id) await loadMyTemplateResources()
  } catch(e:any) { resourceEditorError.value=e.response?.data?.detail || '保存白底图失败' }
  finally { personalResourceSaving.value=false }
}
async function deleteWhiteImage(item:any) {
  if(personalResourceSaving.value || item.deleted_at!=null || !confirm(`确定将白底图「${item.name}」标记为已删除吗？白底图记录、图片、对应风格和已归类素材均会保留。`)) return
  personalResourceSaving.value=true
  try {
    await api.delete(`/user-template-white-images/${item.id}`,{headers:headers.value})
    if(editingWhiteImage.value?.id===item.id) resetWhiteImageForm()
    await Promise.all([loadManagedTemplateResources(),loadMaterialStyles()])
    if(item.user_id===user.value.id) await loadMyTemplateResources()
  } catch(e:any) { showToast(e.response?.data?.detail || '删除白底图失败') }
  finally { personalResourceSaving.value=false }
}
function resetPersonalPromptForm() { editingPersonalPrompt.value=null; personalPromptForm.value={template_id:resourceTemplateFilterId.value,name:'',content:''} }
function resourceOwnerName(item:any) {
  return item.created_by_name || (item.user_id===user.value?.id ? user.value.name : members.value.find(member=>member.id===item.user_id)?.name) || '历史记录缺失'
}
function resourceCreatedAt(item:any) { return item.created_at!=null ? new Date(item.created_at).toLocaleString() : '—' }
function resourceTemplateName(item:any) { return templates.value.find(template=>template.id===item.template_id)?.name || '模板已删除' }
async function savePersonalPrompt() {
  if(personalResourceSaving.value) return
  resourceEditorError.value=''
  const name=personalPromptForm.value.name.trim(), content=personalPromptForm.value.content.trim()
  if(!personalPromptForm.value.template_id){resourceEditorError.value='请先选择产品模板';return}
  if(!resourceEditorUserId.value || !name || !content){resourceEditorError.value='请完整填写名称和创作要求';return}
  try {
    personalResourceSaving.value=true
    if(editingPersonalPrompt.value) await api.put(`/user-template-prompts/${editingPersonalPrompt.value.id}`,{name,content},{headers:headers.value})
    else await api.post('/user-template-prompts',{template_id:personalPromptForm.value.template_id,user_id:resourceEditorUserId.value,name,content},{headers:headers.value})
    if(!editingPersonalPrompt.value) resourceCurrentPage.value=1
    resourceEditorType.value=null; resetPersonalPromptForm(); await loadManagedTemplateResources()
    if(resourceEditorUserId.value===user.value.id) await loadMyTemplateResources()
  } catch(e:any) { resourceEditorError.value=e.response?.data?.detail || '保存创作要求失败' }
  finally { personalResourceSaving.value=false }
}
async function deletePersonalPrompt(item:any) {
  if(personalResourceSaving.value || !confirm(`确定删除创作要求「${item.name}」吗？`)) return
  personalResourceSaving.value=true
  try {
    await api.delete(`/user-template-prompts/${item.id}`,{headers:headers.value})
    await loadManagedTemplateResources()
    if(item.user_id===user.value.id) await loadMyTemplateResources()
  } catch(e:any) { showToast(e.response?.data?.detail || '删除创作要求失败') }
  finally { personalResourceSaving.value=false }
}
function onCoverChange(event: Event) { const input=event.target as HTMLInputElement, file=input.files?.[0] || null; if(file && !validUploadImageFile(file)){input.value='';return} newTemplateImage.value=file; newTemplateImagePreview.value=file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.cover_url) }
function onSizeChartChange(event: Event) { const input=event.target as HTMLInputElement, file=input.files?.[0] || null; if(file && !validUploadImageFile(file)){input.value='';return} newTemplateSizeChart.value=file; newTemplateSizeChartPreview.value=file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.size_chart_url) }
function normalizeTemplateNameForSku() { const name=newTemplateName.value.trim().toUpperCase(); if(!/^[A-Z0-9]{1,5}$/.test(name)){templateFormTab.value='basic';showToast('模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字');throw new Error('invalid template name')} newTemplateName.value=name }
async function presignAndUploadImage(file: File, category: string): Promise<string> {
  const sha256 = await imageSha256(file)
  const { data } = await api.post('/uploads/presign', {
    category, files: [{ content_type: file.type, content_length: file.size, sha256 }],
  }, { headers: headers.value })
  const target = data[0]
  if (target.upload_url) {
    await axios.put(target.upload_url, file, { headers: { 'Content-Type': file.type } })
  }
  return (await api.post('/uploads/complete', {
    category, upload_token: target.upload_token, file_token: target.file_token,
  }, { headers: headers.value })).data.url
}
async function uploadCover() { normalizeTemplateNameForSku(); if (!newTemplateImage.value) return undefined; return presignAndUploadImage(newTemplateImage.value, 'template') }
async function uploadSizeChart() { if (!newTemplateSizeChart.value) return undefined; return presignAndUploadImage(newTemplateSizeChart.value, 'template-size-chart') }
function validateNewTemplate() {
  const sizeOptions = newSkuSizeOptions.value.map(value => value.trim()).filter(Boolean)
  const validations = [
    { valid: /^[A-Z0-9]{1,5}$/.test(newTemplateName.value.trim().toUpperCase()), tab: 'basic' as const, message: '模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字' },
    { valid: Boolean(newTemplateName.value.trim() && newTemplateImage.value && newTemplateDescription.value.trim() && newTemplateGroupId.value !== null), tab: 'basic' as const, message: '请完整填写模版信息，并上传模板图片和选择模板分类' },
    { valid: Boolean(newTemplateProductDescription.value.trim() && newTemplateSizeChart.value), tab: 'product' as const, message: '请完整填写商品信息，并上传尺码图' },
    { valid: sizeOptions.length > 0 && newSkuSizeOptions.value.every(value => value.trim()), tab: 'product' as const, message: '请完整填写 SKU 尺码' },
    { valid: [newPackageWeight.value, newPackageLength.value, newPackageWidth.value, newPackageHeight.value].every(value => value !== null && value > 0), tab: 'logistics' as const, message: '请完整填写物流信息' },
  ]
  const missing = validations.find(item => !item.valid)
  if (!missing) return true
  templateFormTab.value = missing.tab
  showToast(missing.message)
  return false
}
async function createTemplate() { if (!editingTemplate.value && !validateNewTemplate()) return; if (editingTemplate.value && !newTemplateName.value.trim()) { templateFormTab.value='basic'; showToast('请输入模板名称'); return } if (editingTemplate.value && [newPackageWeight.value,newPackageLength.value,newPackageWidth.value,newPackageHeight.value].some(value => value === null || value <= 0)) { templateFormTab.value='logistics'; showToast('请完整填写物流信息'); return } const ai_prompts=newTemplateAiPrompts.value.map(item=>({name:item.name.trim(),content:item.content.trim()})).filter(item=>item.name || item.content); if (ai_prompts.some(item=>!item.name || !item.content)) { templateFormTab.value='ai-prompts'; showToast('请完整填写 AI生成素材提示的名称和内容，或删除空白项'); return } try { templateSaving.value = true; const [uploadedCoverUrl, uploadedSizeChartUrl] = await Promise.all([uploadCover(), uploadSizeChart()]); const cover_url=uploadedCoverUrl ?? editingTemplate.value?.cover_url ?? null; const size_chart_url=uploadedSizeChartUrl ?? editingTemplate.value?.size_chart_url ?? null; const sizeOptions=newSkuSizeOptions.value.map(value=>value.trim()).filter(Boolean); const sku_specifications={size:{name:'尺码',options:sizeOptions}}; const payload={name:newTemplateName.value.trim(),description:newTemplateDescription.value.trim() || null,title_template:newTemplateTitleTemplate.value.trim() || null,product_description:newTemplateProductDescription.value.trim() || null,size_chart_url,group_id:newTemplateGroupId.value,cover_url,package_weight:newPackageWeight.value,package_length:newPackageLength.value,package_width:newPackageWidth.value,package_height:newPackageHeight.value,sku_specifications,ai_prompts,color_count:1,sku_count:Math.max(1,sizeOptions.length)}; if(editingTemplate.value) await api.put(`/templates/${editingTemplate.value.id}`,payload,{headers:headers.value}); else await api.post('/templates',payload,{headers:headers.value}); showTemplateDialog.value=false; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || e?.message || '保存模板失败' } finally { templateSaving.value = false } }
async function deleteTemplate(template:any) { if (!confirm(`确定删除模板「${template.name}」吗？`)) return; try { await api.delete(`/templates/${template.id}`,{headers:headers.value}); if(selectedTemplateId.value===template.id) selectedTemplateId.value=templates.value.find(t=>t.id!==template.id)?.id || null; await refresh() } catch (e:any) { error.value=e.response?.data?.detail || '删除模板失败' } }
function imageUrl(url?: string) { return url ? (url.startsWith('/') ? `${api.defaults.baseURL}${url}` : url) : '' }
const taskStatusLabel: Record<string, string> = { queued: '排队中', running: '处理中', awaiting_selection: '待审核', completed: '已完成', failed: '失败' }
function taskStatusClass(status?: string) { return status === 'awaiting_selection' ? 'purple' : status === 'completed' ? 'blue' : status === 'failed' ? 'orange' : 'purple' }
async function refreshTaskList() {
  try {
    taskListRefreshing.value = true
    const { data } = await api.get('/tasks', { headers: headers.value, params: taskQueryParams() })
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
  materialDraftTitle.value = ''
  materialDraftProductDescription.value = template?.product_description || ''
  materialDraftSizeChartPreview.value = imageUrl(template?.size_chart_url)
}
async function generateMaterialDraftTitle() {
  if (!materialDraftTemplateId.value || !materialDraftAssets.value[0]) return
  const firstAsset = materialDraftAssets.value[0], fromLibrary = libraryDraftMode.value
  try {
    materialDraftTitleGenerating.value = true
    const { data } = await api.post(libraryDraftMode.value ? '/product-library/generate-draft-title' : `/templates/${materialDraftTemplateId.value}/generate-draft-title`, { ...(libraryDraftMode.value ? librarySource(materialDraftAssets.value[0]) : { image_url: materialDraftAssets.value[0].url }), additional_requirements: materialDraftAdditionalRequirements.value.trim() }, { headers: headers.value })
    if (libraryDraftMode.value !== fromLibrary || materialDraftAssets.value[0]?.id !== firstAsset.id) return
    materialDraftTitle.value = data.title
    materialDraftTitleEdited.value = true
  } catch (e:any) {
    showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试')
  } finally {
    materialDraftTitleGenerating.value = false
  }
}
function openMaterialDraftDialog() { libraryDraftMode.value = false; if(!selectedMaterialTemplateId.value){showToast('请选择属于同一产品模板的素材');return} materialDraftAssets.value = [...selectedMaterialAssets.value]; draggedMaterialDraftAssetId.value = null; materialDraftTemplateId.value = selectedMaterialTemplateId.value; materialDraftTitle.value = ''; materialDraftProductDescription.value = ''; materialDraftSizeChartPreview.value = ''; onMaterialDraftTemplateChange(); showMaterialDraftDialog.value = true }
function librarySource(asset:any) { return {source_type:asset.source_type, id:asset.id} }
function openProductLibraryDraftDialog(batch = false) {
  if (productLibrarySelectionLoading.value) return
  const assets = selectableProductLibraryItems.value.filter(item => selectedProductLibraryIds.value.includes(item.id)).map(item => ({...item, url:item.image_url}))
  if (!assets.length) return
  if (assets.some(asset => !asset.url?.trim() || !asset.sku?.trim())) { showToast('所选数据缺少图片或 SKU，请修正后再创建'); return }
  const templateId = assets[0].template_id
  if (!templateId || !templates.value.some(template => template.id === templateId) || assets.some(asset => asset.template_id !== templateId)) { showToast('请先匹配同一有效产品模板，或调整选择'); return }
  if (!batch && new Set(assets.map(asset => asset.sku.trim())).size !== assets.length) { showToast('所选数据包含重复 SKU，请调整选择'); return }
  if (batch && assets.length < 5) { showToast('组合创建至少需要 5 张图片'); return }
  libraryDraftMode.value = true
  libraryDraftSelection.value = assets
  if (batch) {
    if (assets.length < materialBatchGroupSize.value) materialBatchGroupSize.value = 5
    buildMaterialBatchGroups(); draggedMaterialBatchAsset.value = null; showMaterialBatchDraftDialog.value = true
  } else {
    materialDraftAssets.value = [...assets]; draggedMaterialDraftAssetId.value = null
    materialDraftTemplateId.value = templateId; onMaterialDraftTemplateChange()
    materialDraftTitle.value = assets[0].title || ''; materialDraftTitleEdited.value = false
    showMaterialDraftDialog.value = true
  }
}
async function refreshLibraryDraftSource() {
  selectedProductLibraryIds.value = []
  if (activeProductLibraryTab.value === 'products') await loadProductLibrary()
  else if (activeProductLibraryTab.value === 'stagnant') await loadStagnantMaterials()
  else if (activeProductLibraryTab.value === 'new_images') await loadNewImages()
  else await loadProductLibraryRankings()
}
function startMaterialDraftDrag(event: DragEvent, assetId: number) {
  draggedMaterialDraftAssetId.value = assetId
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(assetId))
  }
}
function moveMaterialDraftAsset(assetId: number, targetId: number) {
  if (assetId === targetId) return
  const assets = [...materialDraftAssets.value]
  const from = assets.findIndex(asset => asset.id === assetId)
  const to = assets.findIndex(asset => asset.id === targetId)
  if (from < 0 || to < 0) return
  const [asset] = assets.splice(from, 1)
  assets.splice(to, 0, asset)
  materialDraftAssets.value = assets
  if (libraryDraftMode.value && !materialDraftTitleEdited.value) materialDraftTitle.value = assets[0]?.title || ''
}
function dropMaterialDraftAsset(targetId: number) {
  if (draggedMaterialDraftAssetId.value !== null) moveMaterialDraftAsset(draggedMaterialDraftAssetId.value, targetId)
  draggedMaterialDraftAssetId.value = null
}
async function createDraftFromMaterialAssets() {
  if (materialDraftSaving.value || !materialDraftAssets.value.length) return
  if (!materialDraftTemplateId.value) { showToast('请选择产品模板'); return }
  const title = materialDraftTitle.value.trim()
  if (title.length < 25 || title.length > 255) { showToast('商品标题长度须为 25-255 个字符'); return }
  try {
    materialDraftSaving.value = true
    await api.post(libraryDraftMode.value ? '/drafts/from-product-library' : '/drafts/from-material-assets', { ...(libraryDraftMode.value ? {sources:materialDraftAssets.value.map(librarySource)} : {material_asset_ids: materialDraftAssets.value.map(asset => asset.id)}), template_id: materialDraftTemplateId.value, title, product_description: materialDraftProductDescription.value.trim() || null }, { headers: headers.value })
    selectedMaterialAssetIds.value = []
    showMaterialDraftDialog.value = false
    if (libraryDraftMode.value) await refreshLibraryDraftSource()
    await refresh()
    page.value = 'drafts'
    showToast('商品草稿已创建，请在列表中手动发布至妙手')
  } catch (e:any) {
    showToast(e.response?.data?.detail || '创建商品草稿失败，请稍后重试')
  } finally {
    materialDraftSaving.value = false
  }
}
function shuffleAssets(items: any[]) {
  const shuffled = [...items]
  for (let index = shuffled.length - 1; index > 0; index--) { const target = Math.floor(Math.random() * (index + 1)); [shuffled[index], shuffled[target]] = [shuffled[target], shuffled[index]] }
  return shuffled
}
function buildMaterialBatchGroups() {
  materialBatchTitleGenerator.reset()
  const assets = materialBatchMode.value === 'random' ? shuffleAssets(draftSelectionAssets.value) : [...draftSelectionAssets.value]
  const completeCount = Math.floor(assets.length / materialBatchGroupSize.value) * materialBatchGroupSize.value
  materialBatchGroups.value = Array.from({length: completeCount / materialBatchGroupSize.value}, (_, index) => ({ id: ++materialBatchGroupId, assets: assets.slice(index * materialBatchGroupSize.value, (index + 1) * materialBatchGroupSize.value), title: libraryDraftMode.value ? assets[index * materialBatchGroupSize.value]?.title || '' : '', titleStatus: 'idle', titleError: '', edited:false, additionalRequirements: '', showAdditionalRequirements: false, showTitleHelp: false }))
}
function openMaterialBatchDraftDialog() {
  libraryDraftMode.value = false
  if (!canCreateMaterialBatch.value) { showToast('请选择至少 5 张属于同一产品模板的素材'); return }
  buildMaterialBatchGroups(); draggedMaterialBatchAsset.value = null; showMaterialBatchDraftDialog.value = true
}
function rebuildMaterialBatchGroups() { if (materialBatchControlsLocked.value) return; materialBatchTitleGenerator.reset(); draggedMaterialBatchAsset.value = null; if (draftSelectionAssets.value.length >= materialBatchGroupSize.value) buildMaterialBatchGroups(); else materialBatchGroups.value = [] }
function startMaterialBatchDrag(event: DragEvent, groupIndex: number, assetId: number) {
  if (materialBatchControlsLocked.value) { event.preventDefault(); return }
  draggedMaterialBatchAsset.value = {groupIndex, assetId}
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(assetId))
  }
}
function moveMaterialBatchAsset(groupIndex: number, from: number, to: number) {
  if (materialBatchControlsLocked.value) return
  const group = materialBatchGroups.value[groupIndex]
  if (!group || from < 0 || to < 0 || from >= group.assets.length || to >= group.assets.length || from === to) return
  const assets = [...group.assets]
  const [asset] = assets.splice(from, 1)
  assets.splice(to, 0, asset)
  if (assets[0] !== group.assets[0]) { group.titleStatus = 'idle'; group.titleError = '' }
  group.assets = assets
  if (libraryDraftMode.value && !group.edited) group.title = assets[0]?.title || ''
}
function dropMaterialBatchAsset(groupIndex: number, targetId: number) {
  const dragged = draggedMaterialBatchAsset.value
  draggedMaterialBatchAsset.value = null
  if (!dragged || dragged.groupIndex !== groupIndex) return
  const assets = materialBatchGroups.value[groupIndex]?.assets || []
  moveMaterialBatchAsset(groupIndex, assets.findIndex(asset => asset.id === dragged.assetId), assets.findIndex(asset => asset.id === targetId))
}
function editMaterialBatchTitle(group: MaterialBatchGroup) {
  group.edited = true
  group.titleStatus = 'idle'
  group.titleError = ''
}
async function generateMaterialBatchTitles(groups: MaterialBatchGroup[] = materialBatchGroups.value) {
  if (materialBatchControlsLocked.value || !showMaterialBatchDraftDialog.value || !draftSelectionTemplateId.value || !groups.length) return
  draggedMaterialBatchAsset.value = null
  await materialBatchTitleGenerator.run(groups)
}
function generateMaterialBatchTitle(group: MaterialBatchGroup) {
  return generateMaterialBatchTitles([group])
}
function stopMaterialBatchTitleGeneration() {
  materialBatchTitleGenerator.stop()
  draggedMaterialBatchAsset.value = null
}
async function createMaterialBatchDrafts() {
  if (materialBatchControlsLocked.value || !draftSelectionTemplateId.value || !materialBatchGroups.value.length) return
  if (libraryDraftMode.value && materialBatchGroups.value.some(group => new Set(group.assets.map(asset => asset.sku.trim())).size !== group.assets.length)) { showToast('同一草稿不能包含重复 SKU，请调整组合'); return }
  if (materialBatchGroups.value.some(group => group.title.trim().length < 25 || group.title.trim().length > 255)) { showToast('请为每个组合填写 25-255 个字符的商品标题'); return }
  try {
    materialBatchSaving.value = true
    const {data} = await api.post(libraryDraftMode.value ? '/drafts/from-product-library/batch' : '/drafts/from-material-assets/batch', { template_id: draftSelectionTemplateId.value, groups: materialBatchGroups.value.map(group => ({...(libraryDraftMode.value ? {sources:group.assets.map(librarySource)} : {material_asset_ids:group.assets.map(asset => asset.id)}), title:group.title.trim()})) }, {headers:headers.value})
    selectedMaterialAssetIds.value = []; showMaterialBatchDraftDialog.value = false; if (libraryDraftMode.value) await refreshLibraryDraftSource(); await refresh(); page.value = 'drafts'; showToast(`已创建 ${data.total} 条商品草稿`)
  } catch (e:any) { showToast(e.response?.data?.detail || '批量创建商品草稿失败，请稍后重试') }
  finally { materialBatchSaving.value = false }
}
function openDraftEditDialog(draft: any) { editingDraft.value = draft; draftEditTitle.value = draft.title; draftEditProductDescription.value = draft.product_description || ''; draftEditError.value = ''; showDraftEditDialog.value = true }
// 商品图片已被 AI 生成图覆盖时，回退到轮播图记录里取来源 SKU。
function draftSkuForImage(draft: any, imageUrl: string) {
  return draft?.sku_items?.find((item: any) => item.image_url === imageUrl)?.sku
    || draft?.carousel_items?.find((item: any) => item.image_url === imageUrl)?.sku
    || '—'
}
// SKU 图＝草稿入库时的原始素材图，按 SKU 去重展示。
const draftEditSkus = computed(() => {
  const seen = new Set<string>()
  return (editingDraft.value?.sku_items || []).filter((item: any) => {
    if (!item?.sku || !item?.image_url || seen.has(item.sku)) return false
    seen.add(item.sku)
    return true
  })
})
function openImagePreview(url: string, alt: string) { previewImageUrl.value = imageUrl(url); previewImageAlt.value = alt }
function openTemplateCoverPreview(template: any) { previewImageUrl.value = templateCoverUrl(template); previewImageAlt.value = template.name }
const imageDraftSkus = computed(() => {
  const seen=new Set<string>()
  const adoptedSourceSkus=new Set((imageDraft.value?.carousel_items || [])
    .filter((item:any)=>item?.source_type==='carousel' && item?.sku)
    .map((item:any)=>item.sku))
  return (imageDraft.value?.sku_items || []).filter((item:any)=>{if(!item.sku || !item.image_url || seen.has(item.sku) || adoptedSourceSkus.has(item.sku))return false;seen.add(item.sku);return true})
})
function skuFallbackCarouselItems(draft:any) {
  const seenSkus=new Set<string>(),seenUrls=new Set<string>()
  return (draft?.sku_items || []).filter((item:any)=>{
    if(!item?.sku || !item?.image_url || seenSkus.has(item.sku) || seenUrls.has(item.image_url))return false
    seenSkus.add(item.sku);seenUrls.add(item.image_url);return true
  }).slice(0,9).map((item:any)=>({sku:item.sku,image_url:item.image_url,task_id:null,source_type:'sku'}))
}
const draftFinalImageItems = computed(() => {
  if (!imageDraft.value) return []
  if (stagedFinalImageItems.value !== null) return stagedFinalImageItems.value
  const seen = new Set<string>()
  return (imageDraft.value.carousel_items || []).filter((item:any)=>item?.image_url && !seen.has(item.image_url) && seen.add(item.image_url))
})
const draftImagePreviewUrls = computed(() => draftFinalImageItems.value.map((item:any)=>item.image_url))
const adoptedCarouselItems = computed(() => (imageDraft.value?.carousel_items || []).filter((item:any)=>item?.source_type==='carousel'))
const mainCarouselReferenceItems = computed(() => mainCarouselItems(imageDraft.value))
const mainSkuReferenceItems = computed(() => mainSkuItems(imageDraft.value))
const mainRandomReferenceItems = computed(() => mainReferenceMode.value==='random_sku' ? mainSkuReferenceItems.value : mainCarouselReferenceItems.value)
const currentGeneratedMainImage = computed(() => (imageDraft.value?.carousel_items || []).find((item:any)=>item.source_type==='main_image') || null)
function selectMainReferenceMode(mode:MainReferenceMode) { mainReferenceMode.value=mode==='random_carousel' && !mainCarouselReferenceItems.value.length ? 'random_sku' : mode }
function retainValidMainReferences() { const allowed=new Set([...mainCarouselReferenceItems.value,...mainSkuReferenceItems.value].map(item=>item.image_url));selectedMainReferences.value=selectedMainReferences.value.filter(url=>allowed.has(url)) }
function resetFinalImageOrder(){stagedFinalImageItems.value=null;draggedFinalImageUrl.value=''}
async function loadImageWorkspace(draftId:number, tasksOnly=false) {
  if(tasksOnly) imageTasksRefreshing.value=true
  else imageWorkspaceLoading.value=true
  try {
    const workspace=(await api.get(`/drafts/${draftId}/image-workspace`,{headers:headers.value})).data
    if(tasksOnly && imageDraft.value?.id===draftId){
      imageDraft.value.carousel_tasks=workspace.carousel_tasks
      imageDraft.value.main_image_tasks=workspace.main_image_tasks
    } else imageDraft.value=workspace
  } finally {
    if(tasksOnly) imageTasksRefreshing.value=false
    else imageWorkspaceLoading.value=false
  }
}
async function openImageWorkspace(draft:any, mode:ImageWorkspaceMode='full', focusMain=false) {
  imageWorkspaceMode.value=mode; showDraftImageDialog.value=true; imageDraft.value=null; selectedImageSkus.value=[]; selectedMainReferences.value=[]; mainReferenceMode.value='random_carousel'; carouselConfirmNextStage.value='main_image_pending';resetFinalImageOrder()
  const defaultImageProvider=availableAiProviders.value.find(item=>item.is_default)?.provider || availableAiProviders.value[0]?.provider || ''
  carouselParams.value={prompt:'保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图',provider:defaultImageProvider,ratio:'1:1',quality:'1K'}
  mainParams.value={prompt:'以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然，保持款式与颜色准确',provider:defaultImageProvider,ratio:'1:1',quality:'1K'}
  try {
    await loadImageWorkspace(draft.id)
    selectMainReferenceMode(mainReferenceMode.value)
    if (focusMain) {
      await nextTick()
      document.getElementById('main-image-workspace-section')?.scrollIntoView({behavior:'smooth',block:'start'})
    }
  } catch(e:any){showDraftImageDialog.value=false;showToast(e.response?.data?.detail || '加载图片制作台失败')}
}
function openCarouselImageWorkspace(draft:any) { return openImageWorkspace(draft, 'carousel') }
function openFullImageWorkspace(draft:any, focusMain=false) { return openImageWorkspace(draft, 'full', focusMain) }
function toggleImageSku(sku:string) {
  selectedImageSkus.value=selectedImageSkus.value.includes(sku) ? selectedImageSkus.value.filter(item=>item!==sku) : [...selectedImageSkus.value,sku].slice(0,9)
}
function toggleMainReference(url:string) { selectedMainReferences.value=selectedMainReferences.value.includes(url) ? selectedMainReferences.value.filter(item=>item!==url) : [...selectedMainReferences.value,url].slice(0,9) }
async function createDraftImageTasks(type:'carousel'|'main_image') {
  if(!imageDraft.value) return
  if(type==='carousel' && !selectedImageSkus.value.length){showToast('请至少选择一个 SKU');return}
  if(type==='main_image')selectMainReferenceMode(mainReferenceMode.value)
  if(type==='main_image' && mainReferenceMode.value!=='manual' && !mainRandomReferenceItems.value.length){showToast('缺少可用于制作首图的轮播图或 SKU 图');return}
  if(type==='main_image' && mainReferenceMode.value==='manual' && !selectedMainReferences.value.length){showToast('请手动选择首图参考图');return}
  const params = type==='carousel' ? carouselParams.value : mainParams.value
  if(!params.prompt.trim()){showToast(type==='carousel'?'请填写轮播图的创作要求':'请填写首图的创作要求');return}
  try {
    imageTaskCreatingType.value=type
    const mainReferenceUrls=mainReferenceMode.value==='manual' ? [...new Set(selectedMainReferences.value)] : []
    const {data}=await api.post(`/drafts/${imageDraft.value.id}/image-tasks`,{task_type:type,source_skus:type==='carousel'?selectedImageSkus.value:[],reference_mode:mainReferenceMode.value,reference_urls:type==='main_image'?mainReferenceUrls:[],provider:params.provider,ratio:params.ratio,quality:providerUsesAutoQuality(params.provider)?'auto':params.quality,creative_requirement:params.prompt.trim()},{headers:headers.value})
    const taskKey=type==='carousel'?'carousel_tasks':'main_image_tasks'
    imageDraft.value[taskKey]=[...(data.items || []).reverse(),...(imageDraft.value[taskKey] || [])]
    if(type==='carousel'){ selectedImageSkus.value=[] }
    showToast(type==='carousel'?`已创建 ${data.total} 条轮播图任务`:'首图任务已创建')
  }catch(e:any){showToast(e.response?.data?.detail || '创建图片任务失败')}finally{imageTaskCreatingType.value=''}
}
function isWorkspaceTaskSelected(task:any,url:string) {
  if(!imageDraft.value) return false
  if(task.task_type==='main_image') return (imageDraft.value.carousel_items || []).some((item:any)=>item.task_id===task.id && item.image_url===url)
  const sku=String(task.parameters?.source_sku || '')
  return imageDraft.value.carousel_items?.some((item:any)=>item.sku===sku && item.image_url===url)
}
function isTaskResultSelected(task:any,url:string) {
  return showDraftImageDialog.value && imageDraft.value?.id===Number(task.parameters?.draft_id)
    ? isWorkspaceTaskSelected(task,url)
    : task.selected_result_url===url
}
function taskHasSuccessfulResult(task:any) { return ['awaiting_selection','completed'].includes(task?.status) && !!task?.result_urls?.[0] }
function stageCarouselTaskResult(task:any,url:string) {
  if(!imageDraft.value) return
  const sku=String(task.parameters?.source_sku || '')
  if(!sku){showToast('该任务缺少来源 SKU');return}
  const generated={sku,image_url:url,task_id:task.id,source_type:'carousel'}
  const existing=[...(imageDraft.value.carousel_items || [])]
  const fallbackIndex=existing.findIndex((item:any)=>item.source_type==='sku' && item.sku===sku)
  if(fallbackIndex >= 0) existing.splice(fallbackIndex,1,generated)
  else {
    if(existing.length >= 9){showToast('商品最终图片最多 9 张，请先移除一张轮播图');return}
    existing.push(generated)
  }
  resetFinalImageOrder()
  imageDraft.value.carousel_items=existing
  imageDraft.value.using_sku_fallback=false
  retainValidMainReferences()
  selectMainReferenceMode(mainReferenceMode.value)
  showToast('已暂存为轮播图，确认后保存到草稿')
}
function stageMainTaskResult(task:any,url:string,removeSku?:string) {
  if(!imageDraft.value) return
  const existing=(imageDraft.value.carousel_items || []).filter((item:any)=>item.source_type!=='main_image')
  if(!removeSku && existing.length===9){
    pendingMainApply.value={task,url}
    mainRemoveSku.value=existing[8]?.image_url || ''
    showMainApplyDialog.value=true
    return
  }
  resetFinalImageOrder()
  const remaining=removeSku ? existing.filter((item:any)=>item.image_url!==removeSku) : existing
  imageDraft.value.carousel_items=[{sku:null,image_url:url,task_id:task.id,source_type:'main_image'},...remaining]
  imageDraft.value.using_sku_fallback=false
  showMainApplyDialog.value=false
  pendingMainApply.value=null
  showToast('已暂存为首图，确认后保存到草稿')
}
async function applyImageTaskResult(task:any,url:string,removeSku?:string) {
  const draftId=task.parameters?.draft_id
  if(!draftId) return
  if(!showDraftImageDialog.value || imageDraft.value?.id!==Number(draftId)){
    showTaskDetailDialog.value=false
    page.value='drafts'
    await openImageWorkspace({id:Number(draftId)}, task.task_type==='carousel' ? 'carousel' : 'full', task.task_type==='main_image')
    if(!imageDraft.value) return
  }
  if(task.task_type==='main_image') stageMainTaskResult(task,url,removeSku)
  else stageCarouselTaskResult(task,url)
}
function removeMainImage(){if(!imageDraft.value)return;resetFinalImageOrder();const remaining=(imageDraft.value.carousel_items || []).filter((item:any)=>item.source_type!=='main_image');imageDraft.value.carousel_items=remaining.length?remaining:skuFallbackCarouselItems(imageDraft.value);imageDraft.value.using_sku_fallback=!remaining.length}
function workspaceCarouselTasks():any[] { return (imageDraft.value?.carousel_tasks || []).filter((task:any)=>task && task.id) }
async function refreshWorkspaceTasks() { if(!imageDraft.value) return; try { await loadImageWorkspace(imageDraft.value.id,true) } catch(e:any){showToast(e.response?.data?.detail || '刷新任务失败')} }
function toggleWorkspaceCarouselTask(task:any) {
  if(!imageDraft.value) return
  const url = task?.result_urls?.[0]
  if(!taskHasSuccessfulResult(task) || !url) return
  if(isWorkspaceTaskSelected(task,url)){
    resetFinalImageOrder()
    const sourceSku=String(task.parameters?.source_sku || '')
    const remaining=(imageDraft.value.carousel_items || []).filter((item:any)=>!(item.task_id===task.id && item.image_url===url))
    const sourceImage=imageDraft.value.sku_items?.find((item:any)=>item.sku===sourceSku && item.image_url)
    if(sourceImage && !remaining.some((item:any)=>item.sku===sourceSku)) {
      remaining.push({sku:sourceSku,image_url:sourceImage.image_url,task_id:null,source_type:'sku'})
    }
    imageDraft.value.carousel_items=remaining.length?remaining:skuFallbackCarouselItems(imageDraft.value)
    imageDraft.value.using_sku_fallback=!remaining.length
    retainValidMainReferences()
    selectMainReferenceMode(mainReferenceMode.value)
    showToast('已取消采用该轮播图，确认后保存到草稿')
    return
  }
  stageCarouselTaskResult(task,url)
}
function workspaceMainTasks():any[] { return (imageDraft.value?.main_image_tasks || []).filter((task:any)=>task && task.id) }
function workspaceFailedTasks():any[] {
  const tasks = imageWorkspaceMode.value==='carousel' ? workspaceCarouselTasks() : workspaceCarouselTasks().concat(workspaceMainTasks())
  return tasks.filter((task:any)=>task.status==='failed' && !task.failure_ignored)
}
function toggleWorkspaceMainTask(task:any) {
  if(!imageDraft.value) return
  const url = task?.result_urls?.[0]
  if(!taskHasSuccessfulResult(task) || !url) return
  if(isWorkspaceTaskSelected(task,url)){
    removeMainImage()
    showToast('已取消采用该首图，确认后保存到草稿')
    return
  }
  stageMainTaskResult(task,url)
}
function dropFinalImage(targetUrl:string){if(!draggedFinalImageUrl.value || draggedFinalImageUrl.value===targetUrl)return;const items=[...draftFinalImageItems.value];const from=items.findIndex((item:any)=>item.image_url===draggedFinalImageUrl.value),to=items.findIndex((item:any)=>item.image_url===targetUrl);if(from<0 || to<0)return;const [moved]=items.splice(from,1);items.splice(to,0,moved);stagedFinalImageItems.value=items;draggedFinalImageUrl.value=''}
function removeFinalImage(imageUrl:string){const items=draftFinalImageItems.value.filter((item:any)=>item.image_url!==imageUrl);if(items.length===draftFinalImageItems.value.length)return;if(!items.length){showToast('请至少保留一张 SKU 图或轮播图');return}stagedFinalImageItems.value=items;draggedFinalImageUrl.value='';showToast('已从最终商品图片中移除，确认后保存到草稿')}
async function openImageWorkspaceFromTask(task:any){const draftId=task?.parameters?.draft_id;if(!draftId)return;showTaskDetailDialog.value=false;page.value='drafts';await openImageWorkspace({id:draftId},task.task_type==='carousel'?'carousel':'full',task.task_type==='main_image');if(task.task_type==='carousel' && task.parameters?.source_sku)selectedImageSkus.value=[task.parameters.source_sku];await nextTick();document.getElementById(task.task_type==='main_image'?'main-image-workspace-section':'carousel-workspace-section')?.scrollIntoView({behavior:'smooth',block:'start'})}
async function confirmDraftImages(){if(!imageDraft.value)return;if(!draftFinalImageItems.value.length){showToast('请至少保留一张 SKU 图或轮播图后再保存');return}try{imageConfirmSaving.value=true;const isConfirmingCarousel=imageDraft.value.workflow_stage==='carousel_pending';const payload={image_items:draftFinalImageItems.value.map((item:any)=>({result_url:item.image_url,sku:item.sku || null,task_id:item.task_id || null})),...(isConfirmingCarousel?{next_stage:carouselConfirmNextStage.value}:{})};imageDraft.value=(await api.post(`/drafts/${imageDraft.value.id}/images/confirm`,payload,{headers:headers.value})).data;await refreshDraftList();showDraftImageDialog.value=false;showToast(isConfirmingCarousel?(carouselConfirmNextStage.value==='ready_to_publish'?'轮播图已确认，商品已进入待发布':'轮播图已确认，请继续首图创作'):'商品图片已保存到草稿')}catch(e:any){showToast(e.response?.data?.detail || '保存商品图片失败')}finally{imageConfirmSaving.value=false}}
async function saveDraftEdit() {
  const title = draftEditTitle.value.trim()
  if (!editingDraft.value || title.length < 25 || title.length > 255) { draftEditError.value = '商品标题长度须为 25-255 个字符'; return }
  try {
    draftEditSaving.value = true
    draftEditError.value = ''
    await api.put(`/drafts/${editingDraft.value.id}`, { title, product_description: draftEditProductDescription.value.trim() || null }, { headers: headers.value })
    showDraftEditDialog.value = false
    await refresh()
  } catch (e:any) {
    draftEditError.value = e.response?.data?.detail || '保存商品草稿失败，请稍后重试'
  } finally {
    draftEditSaving.value = false
  }
}
function openMiaoshouPublishDialog(draftsToPublish: any[]) {
  if (!draftsToPublish.length) return
  if (!miaoshouAssignableShops.value.length) { showToast('没有可分配的妙手店铺，请联系管理员同步并分配店铺权限'); return }
  miaoshouPublishDraftIds.value = draftsToPublish.map(draft => draft.id)
  miaoshouPublishShopId.value = null
  miaoshouPublishCompleted.value = 0
  miaoshouPublishFailed.value = 0
  showMiaoshouPublishDialog.value = true
}
function publishDraftToMiaoshou(draft: any) { openMiaoshouPublishDialog([draft]) }
function openBatchMiaoshouPublishDialog() {
  if (!batchMiaoshouPublishEligible.value) { showToast('仅可批量发布待发布状态的商品草稿'); return }
  openMiaoshouPublishDialog(selectedDrafts.value)
}
async function confirmMiaoshouPublish() {
  if (!miaoshouPublishShopId.value) { showToast('请先选择要分配的店铺'); return }
  try {
    miaoshouPublishing.value = true
    miaoshouPublishCompleted.value = 0
    miaoshouPublishFailed.value = 0
    for (const draftId of miaoshouPublishDraftIds.value) {
      publishingDraftId.value = draftId
      try { await api.post(`/drafts/${draftId}/claim-to-tiktok`, { shop_id: miaoshouPublishShopId.value }, { headers: headers.value }) }
      catch { miaoshouPublishFailed.value++ }
      finally { miaoshouPublishCompleted.value++ }
    }
    await refresh()
    if (!miaoshouPublishFailed.value) {
      showMiaoshouPublishDialog.value = false
      selectedDraftIds.value = []
      showToast(`已发布并分配 ${miaoshouPublishCompleted.value} 条商品到所选店铺`)
    } else showToast(`发布完成，${miaoshouPublishFailed.value} 条失败，可保留弹窗后重试`)
  } finally {
    publishingDraftId.value = null
    miaoshouPublishing.value = false
  }
}
async function openTiktokExportDialog() {
  if (!selectedDrafts.value.length) return
  const templateIds = new Set(selectedDrafts.value.map(draft => draft.template_id))
  if (templateIds.size !== 1 || templateIds.has(null)) { showToast('一次只能导出属于同一产品模板的商品草稿'); return }
  const titleGroups = new Map<string, any[]>()
  for (const draft of selectedDrafts.value) {
    const titleKey = String(draft.title || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase()
    const group = titleGroups.get(titleKey) || []
    group.push(draft)
    titleGroups.set(titleKey, group)
  }
  const duplicateTitles = [...titleGroups.values()].filter(group => group.length > 1)
  if (duplicateTitles.length) {
    showToast(`同批导出的商品名称必须不同：${duplicateTitles.map(group => `#${group.map(draft => draft.id).join('、#')}`).join('；')}`)
    return
  }
  showTiktokExportDialog.value = true
  tiktokExportLoading.value = true
  tiktokExportError.value = ''
  tiktokExportCatalogId.value = tiktokExportCatalogs.value[0]?.id || null
  tiktokExportCategory.value = ''
  tiktokExportDefaultPrice.value = null
  tiktokExportDefaultQuantity.value = 999
  tiktokExportCod.value = 'Y'
  tiktokExportAttributes.value = {}
  tiktokExportOptions.value = null
  tiktokExportOverrides.value = Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, { price: null, quantity: null }]))
  try {
    if (!tiktokExportCatalogId.value) throw new Error('请先由管理员新增 TK 类目库')
    tiktokExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: tiktokExportCatalogId.value } })).data
  } catch (e:any) {
    tiktokExportError.value = e.response?.data?.detail || e.message || '加载 TikTok 模板选项失败'
  } finally {
    tiktokExportLoading.value = false
  }
}
async function openShopeeExportDialog() {
  if (!selectedDrafts.value.length) return
  const templateIds = new Set(selectedDrafts.value.map(draft => draft.template_id))
  if (templateIds.size !== 1 || templateIds.has(null)) { showToast('一次只能导出属于同一产品模板的商品草稿'); return }
  const titleGroups = new Map<string, any[]>()
  for (const draft of selectedDrafts.value) {
    const titleKey = String(draft.title || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase()
    const group = titleGroups.get(titleKey) || []
    group.push(draft)
    titleGroups.set(titleKey, group)
  }
  const duplicateTitles = [...titleGroups.values()].filter(group => group.length > 1)
  if (duplicateTitles.length) {
    showToast(`同批导出的商品名称必须不同：${duplicateTitles.map(group => `#${group.map(draft => draft.id).join('、#')}`).join('；')}`)
    return
  }
  showShopeeExportDialog.value = true
  shopeeExportLoading.value = true
  shopeeExportError.value = ''
  shopeeExportCatalogId.value = shopeeCatalogs.value[0]?.id || null
  shopeeExportCategoryId.value = ''
  shopeeExportDefaultPrice.value = null
  shopeeExportDefaultQuantity.value = 999
  shopeeExportChannels.value = []
  shopeeExportOptions.value = null
  shopeeExportOverrides.value = Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, { price: null, quantity: null }]))
  try {
    if (!shopeeExportCatalogId.value) throw new Error('请先由管理员新增 Shopee 类目库')
    shopeeExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: shopeeExportCatalogId.value } })).data
    shopeeExportChannels.value = shopeeExportOptions.value.shipping_channels?.[0]?.field ? [shopeeExportOptions.value.shipping_channels[0].field] : []
  } catch (e:any) {
    shopeeExportError.value = e.response?.data?.detail || e.message || '加载 Shopee 模板选项失败'
  } finally { shopeeExportLoading.value = false }
}
async function changeShopeeExportCatalog() {
  shopeeExportCategoryId.value = ''
  shopeeExportChannels.value = []
  shopeeExportOptions.value = null
  if (!shopeeExportCatalogId.value) return
  try {
    shopeeExportLoading.value = true
    shopeeExportError.value = ''
    shopeeExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: shopeeExportCatalogId.value } })).data
    shopeeExportChannels.value = shopeeExportOptions.value.shipping_channels?.[0]?.field ? [shopeeExportOptions.value.shipping_channels[0].field] : []
  } catch (e:any) { shopeeExportError.value = e.response?.data?.detail || '加载 Shopee 类目库失败' }
  finally { shopeeExportLoading.value = false }
}
async function exportSelectedDraftsToShopee() {
  const defaultPrice = Number(shopeeExportDefaultPrice.value)
  const defaultQuantity = Number(shopeeExportDefaultQuantity.value)
  if (!shopeeExportCatalogId.value) { shopeeExportError.value = '请选择 Shopee 类目库'; return }
  if (!shopeeExportCategoryId.value) { shopeeExportError.value = '请选择 Shopee 商品类目'; return }
  if (!Number.isFinite(defaultPrice) || defaultPrice < 0.10 || defaultPrice > 1000000000) { shopeeExportError.value = '默认售价须为 0.10–1000000000'; return }
  if (!Number.isInteger(defaultQuantity) || defaultQuantity < 0 || defaultQuantity > 10000000) { shopeeExportError.value = '默认库存须为 0–10000000 的整数'; return }
  if (!shopeeExportChannels.value.length) { shopeeExportError.value = '请至少选择一个物流渠道'; return }
  const productOverrides:any[] = []
  for (const draft of selectedDrafts.value) {
    const value:any = shopeeExportOverrides.value[draft.id] || {}
    const item:any = { draft_id: draft.id }
    if (value.price !== null && value.price !== '') {
      const price = Number(value.price)
      if (!Number.isFinite(price) || price < 0.10 || price > 1000000000) { shopeeExportError.value = `商品草稿 #${draft.id} 的售价覆盖值无效`; return }
      item.price = price
    }
    if (value.quantity !== null && value.quantity !== '') {
      const quantity = Number(value.quantity)
      if (!Number.isInteger(quantity) || quantity < 0 || quantity > 10000000) { shopeeExportError.value = `商品草稿 #${draft.id} 的库存覆盖值无效`; return }
      item.quantity = quantity
    }
    if (Object.keys(item).length > 1) productOverrides.push(item)
  }
  try {
    shopeeExportLoading.value = true
    shopeeExportError.value = ''
    const response = await api.post('/drafts/export-shopee', {
      draft_ids: selectedDraftIds.value,
      category_catalog_id: shopeeExportCatalogId.value,
      category_id: shopeeExportCategoryId.value,
      default_price: defaultPrice,
      default_quantity: defaultQuantity,
      shipping_channels: shopeeExportChannels.value,
      product_overrides: productOverrides,
    }, { headers: headers.value, responseType: 'blob' })
    const disposition = String(response.headers['content-disposition'] || '')
    const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const filename = utf8Name ? decodeURIComponent(utf8Name) : 'Shopee批量上传.xlsx'
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    showShopeeExportDialog.value = false
    selectedDraftIds.value = []
    await refreshDraftList()
    showToast('Shopee 批量上传表格已生成，商品草稿已标记为已发布')
  } catch (e:any) {
    if (e.response?.data instanceof Blob) {
      try { shopeeExportError.value = JSON.parse(await e.response.data.text()).detail || '导出失败' }
      catch { shopeeExportError.value = '导出 Shopee 表格失败' }
    } else shopeeExportError.value = e.response?.data?.detail || '导出 Shopee 表格失败'
  } finally { shopeeExportLoading.value = false }
}
function tiktokExportAttributePresetsStorageKey() {
  return user.value?.id ? `haitoro_tiktok_export_attribute_presets_${TIKTOK_EXPORT_ATTRIBUTE_PRESETS_VERSION}:${user.value.id}` : ''
}
function isTiktokExportAttributePresetMap(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
function readTiktokExportAttributePresets() {
  const storageKey = tiktokExportAttributePresetsStorageKey()
  if (!storageKey) return {} as Record<string, Record<string, Record<string, string>>>
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey) || '{}')
    if (!isTiktokExportAttributePresetMap(parsed)) return {}
    const presets: Record<string, Record<string, Record<string, string>>> = {}
    for (const [catalogId, categories] of Object.entries(parsed)) {
      if (!isTiktokExportAttributePresetMap(categories)) continue
      for (const [category, attributes] of Object.entries(categories)) {
        if (!isTiktokExportAttributePresetMap(attributes)) continue
        const validAttributes = Object.fromEntries(Object.entries(attributes).filter(([, value]) => typeof value === 'string')) as Record<string, string>
        if (Object.keys(validAttributes).length) (presets[catalogId] ||= {})[category] = validAttributes
      }
    }
    return presets
  } catch { return {} }
}
function saveTiktokExportAttributePresets() {
  const storageKey = tiktokExportAttributePresetsStorageKey()
  if (!storageKey || !tiktokExportCatalogId.value || !tiktokExportCategory.value) return
  const allowedFields = new Set(selectedTiktokCategoryAttributes.value.map((field:any) => field.field))
  const attributes = Object.fromEntries(Object.entries(tiktokExportAttributes.value).filter(([field, value]) => allowedFields.has(field) && typeof value === 'string' && value.trim()))
  const presets = readTiktokExportAttributePresets()
  const catalogKey = String(tiktokExportCatalogId.value)
  if (Object.keys(attributes).length) {
    presets[catalogKey] ||= {}
    presets[catalogKey][tiktokExportCategory.value] = attributes
  } else {
    delete presets[catalogKey]?.[tiktokExportCategory.value]
    if (presets[catalogKey] && !Object.keys(presets[catalogKey]).length) delete presets[catalogKey]
  }
  try {
    if (Object.keys(presets).length) localStorage.setItem(storageKey, JSON.stringify(presets))
    else localStorage.removeItem(storageKey)
  } catch { /* 浏览器存储不可用时不影响导出。 */ }
}
function restoreTiktokExportAttributePresets() {
  const catalogKey = tiktokExportCatalogId.value ? String(tiktokExportCatalogId.value) : ''
  const remembered = catalogKey && tiktokExportCategory.value ? readTiktokExportAttributePresets()[catalogKey]?.[tiktokExportCategory.value] : {}
  const allowedFields = new Set(selectedTiktokCategoryAttributes.value.map((field:any) => field.field))
  tiktokExportAttributes.value = Object.fromEntries(Object.entries(remembered || {}).filter(([field, value]) => allowedFields.has(field) && typeof value === 'string' && value.trim()))
}
watch(tiktokExportAttributes, saveTiktokExportAttributePresets, { deep: true })
function changeTiktokExportCategory() { restoreTiktokExportAttributePresets() }
async function changeTiktokExportCatalog() {
  tiktokExportCategory.value = ''
  tiktokExportAttributes.value = {}
  tiktokExportOptions.value = null
  if (!tiktokExportCatalogId.value) return
  try {
    tiktokExportLoading.value = true
    tiktokExportError.value = ''
    tiktokExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: tiktokExportCatalogId.value } })).data
  } catch (e:any) { tiktokExportError.value = e.response?.data?.detail || '加载 TK 类目库失败' }
  finally { tiktokExportLoading.value = false }
}
function hasTiktokAttributeValue(value: string) { return Boolean(value?.trim()) }
function tiktokAttributeMode(field:any) {
  const mode = ['single', 'multiple'].includes(field.input_mode) ? 'select' : field.input_mode || (!field.options?.length ? 'text' : field.allow_custom ? 'select_or_text' : 'select')
  return ({ text: '手动填写', select: '选择', select_or_text: '选择或手动填写' } as Record<string,string>)[mode] || '手动填写'
}
function tiktokAttributePlaceholder(field:any) {
  if (field.input_type === 'url') return '请输入 http:// 或 https:// 开头的 URL'
  const mode = ['single', 'multiple'].includes(field.input_mode) ? 'select' : field.input_mode || (!field.options?.length ? 'text' : field.allow_custom ? 'select_or_text' : 'select')
  if (mode === 'select') return '输入模板支持的属性值；'
  if (mode === 'select_or_text') return '输入支持的属性值，或手动填写其他值'
  return '请输入属性值'
}
async function exportSelectedDrafts() {
  const defaultPrice = Number(tiktokExportDefaultPrice.value)
  const defaultQuantity = Number(tiktokExportDefaultQuantity.value)
  if (!tiktokExportCatalogId.value) { tiktokExportError.value = '请选择 TK 类目库'; return }
  if (!tiktokExportCategory.value) { tiktokExportError.value = '请选择 TikTok 商品类目'; return }
  if (!Number.isFinite(defaultPrice) || defaultPrice < 0.01 || defaultPrice > 999999) { tiktokExportError.value = '默认售价须为 0.01–999999'; return }
  if (!Number.isInteger(defaultQuantity) || defaultQuantity < 0 || defaultQuantity > 999999) { tiktokExportError.value = '默认库存须为 0–999999 的整数'; return }
  const productOverrides:any[] = []
  for (const draft of selectedDrafts.value) {
    const value:any = tiktokExportOverrides.value[draft.id] || {}
    const item:any = { draft_id: draft.id }
    if (value.price !== null && value.price !== '') {
      const price = Number(value.price)
      if (!Number.isFinite(price) || price < 0.01 || price > 999999) { tiktokExportError.value = `商品草稿 #${draft.id} 的售价覆盖值无效`; return }
      item.price = price
    }
    if (value.quantity !== null && value.quantity !== '') {
      const quantity = Number(value.quantity)
      if (!Number.isInteger(quantity) || quantity < 0 || quantity > 999999) { tiktokExportError.value = `商品草稿 #${draft.id} 的库存覆盖值无效`; return }
      item.quantity = quantity
    }
    if (Object.keys(item).length > 1) productOverrides.push(item)
  }
  try {
    tiktokExportLoading.value = true
    tiktokExportError.value = ''
    const response = await api.post('/drafts/export-tiktok', {
      draft_ids: selectedDraftIds.value,
      category_catalog_id: tiktokExportCatalogId.value,
      category: tiktokExportCategory.value,
      default_price: defaultPrice,
      default_quantity: defaultQuantity,
      cod: tiktokExportCod.value,
      attributes: Object.fromEntries(Object.entries(tiktokExportAttributes.value).filter(([, value]) => hasTiktokAttributeValue(value))),
      product_overrides: productOverrides,
    }, { headers: headers.value, responseType: 'blob' })
    const disposition = String(response.headers['content-disposition'] || '')
    const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const filename = utf8Name ? decodeURIComponent(utf8Name) : 'TikTok批量上传.xlsx'
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    showTiktokExportDialog.value = false
    selectedDraftIds.value = []
    await refreshDraftList()
    showToast('TikTok 批量上传表格已生成，商品草稿已标记为已发布')
  } catch (e:any) {
    if (e.response?.data instanceof Blob) {
      try { tiktokExportError.value = JSON.parse(await e.response.data.text()).detail || '导出失败' }
      catch { tiktokExportError.value = '导出 TikTok 表格失败' }
    } else tiktokExportError.value = e.response?.data?.detail || '导出 TikTok 表格失败'
  } finally {
    tiktokExportLoading.value = false
  }
}
async function submitSelectedDraftsToHubstudio() {
  const defaultPrice = Number(tiktokExportDefaultPrice.value), defaultQuantity = Number(tiktokExportDefaultQuantity.value)
  if (!tiktokExportIsLocal.value) { tiktokExportError.value = 'tk跨境店类目库仅支持下载表格，不能自动上品'; return }
  if (!tiktokExportCatalogId.value || !tiktokExportCategory.value || !Number.isFinite(defaultPrice) || defaultPrice < 0.01 || !Number.isInteger(defaultQuantity) || defaultQuantity < 0) { tiktokExportError.value = '请先完整填写 TikTok 导出参数'; return }
  const product_overrides = selectedDrafts.value.flatMap(draft => {
    const value:any = tiktokExportOverrides.value[draft.id] || {}; const item:any = {draft_id:draft.id}
    if (value.price !== null && value.price !== '') item.price = Number(value.price)
    if (value.quantity !== null && value.quantity !== '') item.quantity = Number(value.quantity)
    return Object.keys(item).length > 1 ? [item] : []
  })
  try {
    tiktokSubmitting.value = true; tiktokExportError.value = ''
    const {data} = await api.post('/drafts/submit-to-hubstudio', {draft_ids:selectedDraftIds.value, category_catalog_id:tiktokExportCatalogId.value, category:tiktokExportCategory.value, default_price:defaultPrice, default_quantity:defaultQuantity, cod:tiktokExportCod.value, attributes:Object.fromEntries(Object.entries(tiktokExportAttributes.value).filter(([, value]) => hasTiktokAttributeValue(value))), product_overrides}, {headers:headers.value})
    showTiktokExportDialog.value = false; selectedDraftIds.value = []; await refreshDraftList(); showToast(`自动上品任务 #${data.id} 已进入队列，将按执行器本机的模版策略分配环境`)
  } catch (e:any) { tiktokExportError.value = e.response?.data?.detail || '创建 HubStudio 自动上品任务失败' }
  finally { tiktokSubmitting.value = false }
}

async function refreshTiktokCatalogList() {
  if (tiktokCatalogListRefreshing.value) return
  try {
    tiktokCatalogListRefreshing.value = true; tiktokCatalogError.value = ''
    tiktokCatalogs.value = (await api.get('/category-catalogs', { headers: headers.value })).data
  } catch(e:any) { tiktokCatalogError.value = e.response?.data?.detail || '刷新类目列表失败' }
  finally { tiktokCatalogListRefreshing.value = false }
}
function openTiktokCatalogCreateDialog() {
  tiktokCatalogName.value = ''
  tiktokCatalogFile.value = null
  tiktokCatalogError.value = ''
  showTiktokCatalogDialog.value = true
}
function onTiktokCatalogFileChange(event: Event) {
  tiktokCatalogFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
async function createTiktokCatalog() {
  const name = tiktokCatalogName.value.trim()
  if (!name || !tiktokCatalogFile.value) { tiktokCatalogError.value = '请填写类目库名称并选择平台 XLSX 模板'; return }
  const form = new FormData()
  form.append('name', name)
  form.append('template_type', tiktokCatalogTypeTab.value)
  form.append('file', tiktokCatalogFile.value)
  try {
    tiktokCatalogLoading.value = true; tiktokCatalogError.value = ''
    await api.post('/category-catalogs', form, { headers: headers.value })
    showTiktokCatalogDialog.value = false
    tiktokCatalogs.value = (await api.get('/category-catalogs', { headers: headers.value })).data
    showToast('类目库已导入')
  } catch (e:any) { tiktokCatalogError.value = e.response?.data?.detail || '导入类目库失败' }
  finally { tiktokCatalogLoading.value = false }
}
async function openTiktokCatalogDetail(catalog:any) {
  try {
    tiktokCatalogLoading.value = true; tiktokCatalogError.value = ''
    const { data } = await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: catalog.id } })
    managingTiktokCatalog.value = catalog
    managingTiktokCatalogOptions.value = data
    managingTiktokCategory.value = data.categories?.[0]?.name || ''
    showTiktokCatalogDetailDialog.value = true
  } catch (e:any) { tiktokCatalogError.value = e.response?.data?.detail || '读取 TK 类目库失败' }
  finally { tiktokCatalogLoading.value = false }
}
async function setTiktokAttributeInputMode(field:any, inputMode:string) {
  if (!managingTiktokCatalog.value) return
  try {
    tiktokCatalogLoading.value = true; tiktokCatalogError.value = ''
    const { data } = await api.patch(`/category-catalogs/${managingTiktokCatalog.value.id}`, {
      attribute_input_modes: [{ category: managingTiktokCategory.value, field: field.field, input_mode: inputMode }],
    }, { headers: headers.value })
    managingTiktokCatalogOptions.value = data.options || managingTiktokCatalogOptions.value
    tiktokExportOptions.value = null
    showToast(`${field.label} 已设置为${tiktokAttributeMode({...field, input_mode: inputMode})}`)
  } catch (e:any) { tiktokCatalogError.value = e.response?.data?.detail || '保存属性选择方式失败' }
  finally { tiktokCatalogLoading.value = false }
}
function onTiktokInputModeChange(field:any, event:Event) {
  setTiktokAttributeInputMode(field, (event.target as HTMLSelectElement).value)
}
async function deleteTiktokCatalog(catalog:any) {
  if (!confirm(`确定删除类目库“${catalog.name}”吗？`)) return
  try {
    tiktokCatalogLoading.value = true; tiktokCatalogError.value = ''
    await api.delete(`/category-catalogs/${catalog.id}`, { headers: headers.value })
    tiktokCatalogs.value = tiktokCatalogs.value.filter(item => item.id !== catalog.id)
    showToast('类目库已删除')
  } catch (e:any) { tiktokCatalogError.value = e.response?.data?.detail || '删除类目库失败' }
  finally { tiktokCatalogLoading.value = false }
}
function toggleTaskSelection(taskId: number) { selectedTaskIds.value = selectedTaskIds.value.includes(taskId) ? selectedTaskIds.value.filter(id => id !== taskId) : [...selectedTaskIds.value, taskId] }
function taskCanBeSelected(task:any) { return task.status === 'failed' || activeTaskType.value === 'sku_image' && ['awaiting_selection','completed'].includes(task.status) && Boolean(task.result_count || task.result_urls?.length) }
function toggleAllSelectableTasks() { selectedTaskIds.value = allSelectableTasksSelected.value ? [] : selectablePagedTasks.value.map(task => task.id) }
async function openBatchClaimDialog() {
  if (!selectedClaimableTaskIds.value.length) { showToast('请至少选择一个可审核任务'); return }
  showBatchClaimDialog.value = true; batchClaimLoading.value = true; batchClaimItems.value = []; batchClaimInfringement.value = {}; selectedBatchClaimImages.value = new Set(); batchClaimCompleted.value = 0; batchClaimTotal.value = 0; batchClaimFailed.value = 0
  try {
    const details = await Promise.all(selectedClaimableTaskIds.value.map(id => api.get(`/tasks/${id}`, { headers: headers.value }).then(response => response.data)))
    batchClaimItems.value = details.flatMap(task => (task.result_urls || []).map((url: string) => ({ taskId: task.id, taskLabel: `任务 #${task.id}`, url })))
    selectedBatchClaimImages.value = new Set(batchClaimItems.value.map(item => batchClaimImageKey(item.taskId, item.url)))
    if (!batchClaimItems.value.length) showToast('所选任务没有可审核图片')
  } catch (e:any) { showBatchClaimDialog.value = false; showToast(e.response?.data?.detail || '加载批量审核内容失败') }
  finally { batchClaimLoading.value = false }
}
async function confirmBatchClaim() {
  if (batchClaimLoading.value || batchClaiming.value) return
  const groups=groupedBatchClaimItems.value.map(group=>({...group,urls:group.urls.filter(url=>selectedBatchClaimImages.value.has(batchClaimImageKey(group.taskId,url)))}))
  const requestHeaders={...headers.value}
  const items=groups.flatMap(group=>(group.urls.length ? group.urls : [null]).map(url=>{ const isInfringing=url ? Boolean(batchClaimInfringement.value[batchClaimImageKey(group.taskId,url)]) : false; return transferItem(`任务 #${group.taskId}${url ? '' : '（不采用图片）'}`,async(force,requestKey)=>{
    const {data}=await api.post(`/tasks/${group.taskId}/claim-materials`,{
      result_urls:url ? [url] : [],force_create:force,request_key:requestKey,is_infringing:isInfringing,
    },{headers:requestHeaders})
    return data.items[0] || {outcome:'created'}
  },url ? imageUrl(url) : undefined) }))
  showBatchClaimDialog.value=false
  selectedTaskIds.value=[]
  openMaterialTransfers(items)
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
async function retrySelectedTasks() {
  const taskIds = selectedRetryTaskIds.value
  if (!taskIds.length) { showToast('请至少选择一个失败任务'); return }
  try {
    batchRetryingTasks.value = true
    const { data } = await api.post('/tasks/batch-retry', { task_ids: taskIds }, { headers: headers.value })
    selectedTaskIds.value = selectedTaskIds.value.filter(id => !taskIds.includes(id))
    await refreshTaskList()
    showToast(`已将 ${data.total} 个失败任务重新入队`)
  } catch (e:any) { showToast(e.response?.data?.detail || '批量重试任务失败') }
  finally { batchRetryingTasks.value = false }
}
async function retryWorkspaceTask(task: any) {
  try {
    retryingWorkspaceTaskId.value = task.id
    await api.post(`/tasks/${task.id}/retry`, {}, { headers: headers.value })
    await refreshWorkspaceTasks()
    showToast('失败任务已重新入队')
  } catch (e: any) { showToast(e.response?.data?.detail || '重试任务失败') }
  finally { retryingWorkspaceTaskId.value = null }
}
async function ignoreWorkspaceTaskFailure(task:any) {
  if (!imageDraft.value) return
  try {
    await api.post(`/drafts/${imageDraft.value.id}/image-tasks/${task.id}/ignore-failure`, {}, {headers:headers.value})
    await refreshWorkspaceTasks(); await refreshDraftList()
    showToast('已忽略失败任务，可继续当前制作阶段')
  } catch (e:any) { showToast(e.response?.data?.detail || '忽略失败任务失败') }
}
async function downloadMaterialImportTemplate() {
  try {
    materialTemplateDownloading.value = true
    const { data } = await api.get('/material-assets/import-template', {headers:headers.value, responseType:'blob'})
    const url = URL.createObjectURL(data), link = document.createElement('a')
    link.href = url; link.download = '素材库导入模版.xlsx'
    document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { showToast('下载素材导入模版失败') }
  finally { materialTemplateDownloading.value = false }
}
async function previewMaterialImport(event:Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  input.value = ''
  if (!file || materialImportPreviewing.value || materialImportSaving.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) { showToast('请上传 .xlsx 格式的素材表格'); return }
  if (file.size > 20 * 1024 * 1024) { showToast('Excel 文件不能超过 20MB'); return }
  try {
    materialImportPreviewing.value = true
    const form = new FormData(); form.append('file', file)
    const { data } = await api.post('/material-assets/import-preview', form, {headers:headers.value})
    materialImportItems.value = data.items.map((item:{url:string; exists:boolean}) => ({...item, selected:!item.exists, is_infringing:false, style_id:null}))
    materialImportTemplateId.value = null
    materialImportError.value = ''
    showMaterialImportDialog.value = true
  } catch(e:any) { showToast(e.response?.data?.detail || '解析素材表格失败') }
  finally { materialImportPreviewing.value = false }
}
const materialTransferItems = ref<MaterialTransferItem[]>([]), showMaterialTransferResults = ref(false)
function openMaterialTransfers(items: MaterialTransferItem[]) {
  materialTransferItems.value = items
  showMaterialTransferResults.value = true
}
async function refreshAfterMaterialTransfer() {
  try { await Promise.all([refreshMaterialList(), refreshTaskList(), loadMaterialStyles()]) }
  catch { showToast('处理结果已保存，列表刷新失败，请刷新页面') }
}
async function confirmMaterialImport() {
  if (!materialImportTemplateId.value) { materialImportError.value = '请选择产品模板'; return }
  const selected = materialImportItems.value.filter(item=>item.selected).map(item=>({...item}))
  if (!selected.length) { materialImportError.value = '请至少选择一张素材'; return }
  const templateId = materialImportTemplateId.value, requestHeaders = {...headers.value}
  const items = selected.map(source => {
    let fileToken: string | undefined
    return transferItem(source.url, async (force, requestKey) => {
      const {data} = await api.post('/material-assets/import-confirm', {
        is_infringing:source.is_infringing, style_id:source.style_id, template_id:templateId, urls:fileToken ? [] : [source.url], file_token:fileToken,
        force_create:force || source.exists, request_key:requestKey,
      }, {headers:requestHeaders})
      const result = data.items[0]
      if (result.file_token) fileToken = result.file_token
      if (result.outcome==='error' && /过期/.test(result.error || '')) fileToken=undefined
      return result
    }, source.url)
  })
  showMaterialImportDialog.value = false
  openMaterialTransfers(items)
}
function chooseMaterialUploadFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  if (files.length > MATERIAL_UPLOAD_MAX_FILES) { showToast(`单次最多上传 ${MATERIAL_UPLOAD_MAX_FILES} 张图片`); return }
  if (files.some(file => !ALLOWED_IMAGE_TYPES.includes(file.type) || !file.size || file.size > MAX_IMAGE_BYTES)) { showToast('仅支持 JPG、PNG、WebP，且单张不能超过 3MB'); return }
  clearMaterialUploadPreviews()
  pendingMaterialUploadFiles.value = files.map(file=>({file, preview:URL.createObjectURL(file), selected:true, is_infringing:false, style_id:null}))
  materialUploadError.value = ''
  materialUploadTemplateId.value = null
  showMaterialUploadDialog.value = true
}
async function uploadMaterialAssets() {
  const files = pendingMaterialUploadFiles.value.filter(item=>item.selected).map(item=>({...item})), templateId = materialUploadTemplateId.value
  if (!files.length || !templateId) { materialUploadError.value='请选择产品模板和至少一张图片'; return }
  const requestHeaders = {...headers.value}
  const prepared = new Map<string, Promise<any>>()
  const items = files.map(({file,is_infringing,style_id}) => {
    let target: any, fileHash: string | undefined
    return transferItem(file.name, async (force, requestKey) => {
      if (!target) {
        const sha256 = fileHash || await imageSha256(file)
        fileHash=sha256
        if (!prepared.has(sha256)) {
          const promise = (async () => {
            const { data } = await api.post('/material-assets/presign', {
              template_id:templateId, files:[{content_type:file.type,content_length:file.size,sha256}],
            }, {headers:requestHeaders})
            const signed = data[0]
            if (signed.upload_url) {
              let lastError: unknown
              for (let attempt=0; attempt<=IMAGE_UPLOAD_RETRY; attempt++) {
                try { await axios.put(signed.upload_url,file,{headers:{'Content-Type':file.type}}); lastError=undefined; break }
                catch (error) { lastError=error }
              }
              if (lastError) throw lastError
            }
            return signed
          })()
          prepared.set(sha256,promise)
          void promise.catch(()=>prepared.delete(sha256))
        }
        target = await prepared.get(sha256)
      }
      const {data} = await api.post('/material-assets/commit', {
        template_id:templateId, items:[{upload_token:target.upload_token,file_token:target.file_token,
          name:file.name,request_key:requestKey,force_create:force,is_infringing,style_id}],
      }, {headers:requestHeaders})
      const result = data.items[0]
      if (result.file_token) { target.file_token=result.file_token; target.upload_token=undefined }
      if (result.outcome==='error' && /过期/.test(result.error || '')) { target=undefined; if(fileHash) prepared.delete(fileHash) }
      return result
    })
  })
  showMaterialUploadDialog.value=false
  pendingMaterialUploadFiles.value=[]
  openMaterialTransfers(items)
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
async function refreshMemberList() {
  if (memberListRefreshing.value) return
  try {
    memberListRefreshing.value = true
    const [memberResponse, groupResponse] = await Promise.all([api.get('/members', { headers: headers.value }), api.get('/operator-groups', { headers: headers.value })])
    members.value = memberResponse.data
    operatorGroups.value = groupResponse.data
  } catch(e:any) { showToast(e.response?.data?.detail || '刷新成员列表失败') }
  finally { memberListRefreshing.value = false }
}
function operatorGroupName(groupId:number | null) { return operatorGroups.value.find(group => group.id === groupId)?.name || '未分组' }
function operatorGroupMembers(groupId:number) { return members.value.filter(member => member.group_id === groupId) }
function memberRoleLabel(member:any) { return member.role === 'company_admin' ? '公司管理员' : member.role === 'team_leader' ? '运营组长' : member.group_id ? '组员' : '普通运营' }
function openOperatorGroupDialog(group?:any) { editingOperatorGroup.value=group || null; operatorGroupForm.value={name:group?.name || '',leader_user_id:null}; operatorGroupError.value=''; showOperatorGroupDialog.value=true }
async function saveOperatorGroup() {
  const name=operatorGroupForm.value.name.trim()
  if (!name) { operatorGroupError.value='请输入组名'; return }
  if (!editingOperatorGroup.value && !operatorGroupForm.value.leader_user_id) { operatorGroupError.value='请选择组长'; return }
  try {
    operatorGroupSaving.value=true; operatorGroupError.value=''
    if (editingOperatorGroup.value) await api.patch(`/operator-groups/${editingOperatorGroup.value.id}`,{name},{headers:headers.value})
    else await api.post('/operator-groups',{name,leader_user_id:operatorGroupForm.value.leader_user_id},{headers:headers.value})
    showOperatorGroupDialog.value=false; await refreshMemberList(); showToast('运营组已保存')
  } catch(e:any) { operatorGroupError.value=e.response?.data?.detail || '保存运营组失败' }
  finally { operatorGroupSaving.value=false }
}
async function deleteOperatorGroup(group:any) {
  const affected=operatorGroupMembers(group.id)
  const otherCount=affected.filter(member => member.id !== group.leader_user_id).length
  if (!confirm(`确定删除“${group.name}”吗？该组组长和 ${otherCount} 位组员（共 ${affected.length} 人）都将恢复为未分组普通运营。`)) return
  try { await api.delete(`/operator-groups/${group.id}`,{headers:headers.value}); await refreshMemberList(); showToast('运营组已删除') }
  catch(e:any) { showToast(e.response?.data?.detail || '删除运营组失败') }
}
function openMemberDialog(member?: any) { editingMember.value=member || null; memberForm.value={name:member?.name || '',user_code:member?.user_code || '',email:member?.email || '',password:'',is_active:member?.is_active ?? true,role:member?.role || 'member',group_id:member?.group_id ?? null}; memberFormError.value=''; showMemberDialog.value=true }
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
  if (memberForm.value.role === 'team_leader' && !memberForm.value.group_id) { invalid('请选择组长所属运营组'); return }
  try { memberSaving.value=true; error.value=''; const payload:any={name,user_code:userCode,email,role:memberForm.value.role,group_id:memberForm.value.group_id}; if(memberForm.value.password) payload.password=memberForm.value.password; if(editingMember.value) await api.put(`/members/${editingMember.value.id}`,payload,{headers:headers.value}); else await api.post('/members',payload,{headers:headers.value}); showMemberDialog.value=false; await refresh(); showToast('成员已保存') } catch(e:any) { const message=e.response?.data?.detail || '保存成员失败'; memberFormError.value=message; error.value=message; showToast(message) } finally { memberSaving.value=false } }
async function toggleMember(member:any) { try { await api.put(`/members/${member.id}`,{is_active:!member.is_active},{headers:headers.value}); await refresh() } catch(e:any) { error.value=e.response?.data?.detail || '更新成员状态失败' } }
async function toggleMemberSupplyGrant(member:any) {
  if (memberSupplyGrantSaving.value || !['member', 'team_leader'].includes(member.role)) return
  const enabled = !member.supply_admin
  try {
    memberSupplyGrantSaving.value = true
    const { data } = await api.post(`/supply/grants/${member.id}`, { enabled }, { headers: headers.value })
    member.supply_admin = data.supply_admin
    showToast(enabled ? '已授予货盘管理权限' : '已撤销货盘管理权限')
  } catch(e:any) { showToast(e.response?.data?.detail || '更新货盘管理权限失败') }
  finally { memberSupplyGrantSaving.value = false }
}
function openMemberCredentialDialog(member:any, provider:any) { credentialMember.value=member; credentialProvider.value=provider; credentialApiKey.value=''; showMemberCredentialDialog.value=true }
function memberCredentialKey() { return credentialProvider.value?.credential_provider || credentialProvider.value?.provider }
function memberCredentialPreview() { return credentialMember.value?.ai_provider_credential_previews?.[memberCredentialKey()] || '' }
async function saveMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !credentialApiKey.value.trim()) { showToast('请输入平台密钥'); return } try { credentialSaving.value=true; await api.put(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`,{api_key:credentialApiKey.value.trim()},{headers:headers.value}); showMemberCredentialDialog.value=false; await refresh(); showToast(`${credentialProvider.value.credential_display_name || credentialProvider.value.display_name} 平台密钥已安全保存`) } catch(e:any) { showToast(e.response?.data?.detail || '保存平台密钥失败') } finally { credentialSaving.value=false } }
async function clearMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !confirm(`确定清除 ${credentialMember.value.name} 的 ${credentialProvider.value.credential_display_name || credentialProvider.value.display_name} 平台密钥吗？`)) return; try { credentialSaving.value=true; await api.delete(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`,{headers:headers.value}); showMemberCredentialDialog.value=false; await refresh(); showToast('平台密钥已清除') } catch(e:any) { showToast(e.response?.data?.detail || '清除平台密钥失败') } finally { credentialSaving.value=false } }
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
function openHubstudioDialog() { hubstudioForm.value={app_id:'',app_secret:'',group_code:''}; showHubstudioDialog.value=true }
async function saveHubstudioAccount() { try { hubstudioSaving.value=true; await api.put('/hubstudio/account',hubstudioForm.value,{headers:headers.value}); showHubstudioDialog.value=false; await refresh(); showToast('HubStudio API 凭据已保存') } catch(e:any) { shopError.value=e.response?.data?.detail || '保存 HubStudio 配置失败' } finally { hubstudioSaving.value=false } }
let toastTimer: ReturnType<typeof setTimeout> | undefined
function showToast(message: string) { toast.value = message; if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = '' }, 3000) }
function logout(){ resourceEditorType.value=null; resourceEditorError.value=''; resourceEditorUserId.value=null; managedResourcesRequestId++; managedResourcesLoading.value=false; managedWhiteImages.value=[]; managedPrompts.value=[]; managedResourceUserId.value=null; showMaterialUploadDialog.value=false; showMaterialTransferResults.value=false; crossCompanyCollectionEnabled.value=false; materialCollectionDetail.value=null; hubUploadTemplateId.value=null; hubUploadTemplates.value=[]; hubUploadRequestId++; hubUploadTasks.value=[]; hubUploadTotal.value=0; hubUploadPage.value=1; hubUploadCreatorId.value=null; hubUploadLoading.value=false; hubUploadError.value=''; showHubstudioDialog.value=false; localStorage.removeItem('haitoro_token'); token.value=''; user.value=null; taskCreatorFilterId.value=null; materialCreatorFilterId.value=null; materialTemplateFilterId.value=null; materialSourceTypeFilter.value=''; materialCreatedFrom.value=''; materialCreatedTo.value=''; materialStylesRequestId++; materialStyles.value=[]; materialStylesLoading.value=false; materialStyleFilterId.value=null; appliedMaterialFilters.value={template_id:null,creator_id:null,style_id:null,source_type:'',created_from:'',created_to:''}; draftCreatorFilterId.value=null; creatorFiltersInitialized.value=false; productLibraryItems.value=[]; productLibraryTotal.value=0; productLibraryPage.value=1; productLibraryRankingRequestId++; productLibraryRankingItems.value=[]; productLibraryRankingTotal.value=0; productLibraryRankingDate.value=null; productLibraryRankingThroughDate.value=null; productLibraryShops.value=[]; rankingShopFilters.value={}; rankingCreatorFilters.value={}; productLibraryCreatorId.value=null; stagnantRequestId++; stagnantMaterials.value=[]; stagnantTotal.value=0; stagnantPage.value=1; stagnantCreatorId.value=null; stagnantError.value=''; stagnantLoading.value=false; newImagesRequestId++; newImages.value=[]; newImagesTotal.value=0; newImagesPage.value=1; newImagesCreatorId.value=null; newImagesUsageStatus.value='all'; newImagesError.value=''; newImagesLoading.value=false; productLibraryStatisticsTask.value=null; activeProductLibraryTab.value='products'; productLibrarySelectedShopIds.value=[]; productLibraryShopSearch.value=''; productLibraryTemplateFilter.value=''; productLibrarySku.value=''; appliedProductLibraryFilters.value={sourceIds:[],template:'',sku:'',creatorId:null}; selectedProductLibraryIds.value=[]; productLibraryFilters.value={shops:[]} }
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
  if (!token.value || user.value?.role === 'supply_user' || !taskActiveCount.value) return
  try { applyTaskPage((await api.get('/tasks', { headers: headers.value, params: taskQueryParams() })).data) } catch { /* 保留上一次任务状态，等待下次轮询。 */ }
}
onMounted(() => {
  if (token.value) refresh().catch(logout)
  document.addEventListener('pointerdown', closeProductLibraryShopFilterOnOutsideClick)
  window.addEventListener('resize', clearImageHoverPreviews)
  taskResultPollingTimer = setInterval(refreshPendingTaskResults, 5000)
  productLibraryStatisticsPollingTimer = setInterval(() => {
    if (page.value === 'product-library' && productLibraryStatisticsRunning.value) void loadProductLibraryStatisticsStatus()
  }, 5000)
})
let productLibraryStatisticsPollingTimer: ReturnType<typeof setInterval> | undefined
onUnmounted(() => {
  showMaterialTransferResults.value=false
  materialBatchTitleGenerator.reset()
  document.removeEventListener('pointerdown', closeProductLibraryShopFilterOnOutsideClick)
  window.removeEventListener('resize', clearImageHoverPreviews)
  if (taskResultPollingTimer) clearInterval(taskResultPollingTimer)
  if (productLibraryStatisticsPollingTimer) clearInterval(productLibraryStatisticsPollingTimer)
})
</script>

<template>
  <main v-if="!token" class="login-shell">
    <section class="login-card"><img class="brand-mark" src="/brand-icon.png" alt="Haitoro" width="44" height="44" /><h2>欢迎回到 Haitoro POD 工作台</h2><label>邮箱<input v-model="email" type="email" autocomplete="username" /></label><label>密码<input v-model="password" type="password" autocomplete="current-password" /></label><button class="primary full" :disabled="loading" @click="login">{{ loading ? '登录中…' : '登录' }}</button><p v-if="error" class="error">{{ error }}</p></section>
  </main>
  <div v-if="showTiktokCatalogDialog" class="modal-backdrop" @click.self="!tiktokCatalogLoading && (showTiktokCatalogDialog=false)"><section class="modal-card tiktok-catalog-create-dialog"><button class="modal-close" :disabled="tiktokCatalogLoading" @click="showTiktokCatalogDialog=false">×</button><h2>新增类目</h2><p>当前店铺类型：{{tiktokCatalogTypeLabel(tiktokCatalogTypeTab)}}。请上传对应平台下载的批量上传 XLSX 模板，系统会使用匹配的解析器校验。</p><label>类目库名称 <b class="required">*</b><input v-model="tiktokCatalogName" maxlength="120" placeholder="例如：女装"/></label><label>模板文件 <b class="required">*</b><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="onTiktokCatalogFileChange"/><small>仅支持 .xlsx，最大 10MB。</small></label><p v-if="tiktokCatalogError" class="error material-draft-error">{{tiktokCatalogError}}</p><div class="modal-actions"><button class="ghost" :disabled="tiktokCatalogLoading" @click="showTiktokCatalogDialog=false">取消</button><button class="primary" :disabled="tiktokCatalogLoading" @click="createTiktokCatalog">{{tiktokCatalogLoading ? '解析中…' : '上传并解析'}}</button></div></section></div>
  <div v-if="showTiktokCatalogDetailDialog" class="modal-backdrop" @click.self="showTiktokCatalogDetailDialog=false"><section class="modal-card tiktok-catalog-detail-dialog"><button class="modal-close" @click="showTiktokCatalogDetailDialog=false">×</button><h2>{{managingTiktokCatalog?.name}} · 属性设置</h2><p>导入后仅支持修正属性的输入方式；属性名称、状态和候选值保持模板原始内容。</p><label>商品类目<select v-model="managingTiktokCategory"><option v-for="category in managingTiktokCatalogOptions?.categories || []" :key="category.name" :value="category.name">{{category.name}}</option></select></label><div class="tiktok-property-list"><div class="tiktok-property-head"><span>属性</span><span>状态</span><span>选项数</span><span>输入方式</span></div><div v-for="field in managingTiktokCategoryAttributes" :key="field.field" class="tiktok-property-row"><span><b>{{field.label}}</b><small>{{field.field}}</small></span><span>{{field.required ? '必填' : '可选'}}</span><span>{{field.options?.length || 0}}</span><select class="tiktok-input-mode-select" :value="['single','multiple'].includes(field.input_mode) ? 'select' : field.input_mode || (!field.options?.length ? 'text' : field.allow_custom ? 'select_or_text' : 'select')" :disabled="tiktokCatalogLoading" @change="onTiktokInputModeChange(field,$event)"><option value="text">手动填写</option><option value="select" :disabled="!field.options?.length">选择</option><option value="select_or_text" :disabled="!field.options?.length">选择或手动填写</option></select></div><p v-if="!managingTiktokCategoryAttributes.length" class="empty">该类目没有可填写属性。</p></div><div class="modal-actions"><button class="primary" @click="showTiktokCatalogDetailDialog=false">完成</button></div></section></div>
  <main v-if="token" class="app-shell">
    <aside><div class="logo"><img src="/brand-icon.png" alt="Haitoro" width="27" height="27" /><b>Haitoro AI</b></div><nav><button v-for="item in visibleNav" :key="item.key" :class="{active: page===item.key}" @click="page=item.key"><i>{{item.icon}}</i>{{item.label}}</button></nav></aside>
    <section class="content"><header><div><h1>{{ pageTitle }}</h1></div><div class="context"><button class="member account-button" :disabled="user?.role==='supply_user'" @click="openMyAccountDialog">{{user?.name}} · {{ user?.role === 'supply_user' ? '货盘用户' : user?.role === 'company_admin' ? '管理员' : user?.role === 'team_leader' ? '运营组长' : '运营成员' }}{{user?.group_name ? ` · ${user.group_name}` : ''}}{{user?.user_code ? ` · ${user.user_code}` : ''}}</button><button class="ghost" @click="logout">退出</button></div></header>
      <SupplyCatalog v-if="page==='supply'" :token="token" :user="user" :initial-tab="String(route.query.tab || '')" @unauthorized="logout" />
      <section v-else-if="page==='dashboard'" class="page"><div class="hero"><div><p>POD 商品工作台</p><h2>今天要先处理什么？</h2><span>从 AI创作到待发布商品，所有进度都在这里。</span></div><button class="primary" @click="page='pod'">✦ 开始 AI创作</button></div><div class="metrics"><article><span>待领取任务</span><b>{{taskStatusCounts.awaiting_selection || 0}}</b><em>请选择要领取的图片</em></article><article><span>待发布商品</span><b>{{drafts.length}}</b><em>妙手接口待接入</em></article><article><span>素材库</span><b>{{materialTotal}}</b><em>已保存的商品素材</em></article></div><div class="two-col"><section class="panel"><h3>最近任务 <button @click="page='tasks'">查看全部</button></h3><div v-for="task in tasks.slice(0,3)" :key="task.id" class="task-row"><span class="thumb">✦</span><div><strong>AI创作 #{{task.id}}</strong><small>{{taskTypeLabel(task)}} · {{new Date(task.created_at).toLocaleString()}}</small></div><span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span></div><p v-if="!tasks.length" class="empty">暂无 AI 创作任务。</p></section><section class="panel"><h3>快捷操作</h3><button class="quick" @click="page='templates'">▦ 浏览产品模板 <span>→</span></button><button class="quick" @click="page='tasks'">◌ 查看任务中心 <span>→</span></button></section></div></section>
      <section v-else-if="page==='templates'" class="page"><div class="toolbar"><input v-model="templateQuery" placeholder="搜索模板名称"/><div v-if="user?.role==='company_admin'" class="toolbar-actions"><button class="primary" @click="openTemplateDialog()">新增模板</button></div></div><div class="template-layout"><section class="groups"><div class="groups-heading"><h3>模板分类</h3><button v-if="user?.role==='company_admin'" class="add-group" @click="showGroupDialog=true">新增</button></div><button :class="{selected:activeGroupId===null}" @click="activeGroupId=null">全部模板</button><div v-for="group in templateGroups" :key="group.id" class="template-group-item"><button :class="{selected:activeGroupId===group.id}" @click="activeGroupId=group.id">{{group.name}}</button><button v-if="user?.role==='company_admin' && !group.is_platform && templateGroupIsEmpty(group.id)" class="template-group-delete" :aria-label="`删除空模板分类 ${group.name}`" :title="`删除空模板分类 ${group.name}`" @click.stop="deleteTemplateGroup(group)">×</button></div></section><section><div class="section-heading"><h2>{{activeGroupId ? templateGroups.find(g=>g.id===activeGroupId)?.name : '全部模板'}}</h2><span>共 {{filteredTemplates.length}} 个模板</span></div><div class="template-grid"><article v-for="t in filteredTemplates" :key="t.id" class="template-card"><button v-if="hasTemplateCover(t)" type="button" class="template-image hasCover template-image-button" :aria-label="`查看 ${t.name} 大图`" title="查看大图" @click="openTemplateCoverPreview(t)"><img :src="templateCoverUrl(t)" :alt="t.name"/></button><div v-else class="template-image"><span>{{t.name.includes('T恤')?'♧':'♔'}}</span></div><h3>{{t.name}}</h3><p v-if="t.description" class="template-description">{{t.description}}</p><div class="template-actions"><button @click="useTemplate(t)">用于 AI创作 →</button><template v-if="!t.is_platform && user?.role==='company_admin'"><button @click="openTemplateDialog(t)">编辑</button><button class="danger" @click="deleteTemplate(t)">删除</button></template></div></article><p v-if="!filteredTemplates.length" class="empty">没有符合条件的模板。</p></div></section></div></section>
      <section v-else-if="page==='pod'" class="page"><div class="mode-tabs"><button>灵感参考</button><button class="active">印花贴合</button><button>创作变体</button></div><section class="pod-panel"><div class="pod-heading personal-resource-heading"><div><h2>印花贴合</h2><p>上传印花素材，选择产品模板和个人白底图，生成 AI 创作效果图。</p></div><div class="personal-resource-actions"><button class="secondary" @click="openPersonalResourcesDialog()">管理白底图与创作要求</button></div><label class="requirement-label">创作要求 <b>*</b><span v-if="selectedTemplateAiPrompts().length || personalPrompts.length" class="prompt-picker"><select v-model="creativePromptIndex" @change="applyTemplateAiPrompt"><option value="">选择创作要求</option><optgroup v-if="selectedTemplateAiPrompts().length" label="产品模板创作要求"><option v-for="(prompt,index) in selectedTemplateAiPrompts()" :key="`template-${index}`" :value="`template:${index}`">{{prompt.name}}</option></optgroup><optgroup v-if="personalPrompts.length" label="我的创作要求"><option v-for="prompt in personalPrompts" :key="`personal-${prompt.id}`" :value="`personal:${prompt.id}`">{{prompt.name}}</option></optgroup></select><small>选择后会填充至下方，仍可自行修改。</small></span><textarea v-model="creativeRequirement" maxlength="1000" placeholder="例如：保留花朵细节，色彩清晰自然，印花完整贴合布料"></textarea></label></div><div class="pod-grid"><article><label>创作素材</label><label class="upload floral" :class="{hasAsset:creativeAssets.length, invalid:creativeAssetError}"><input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="onCreativeAssetChange"/><img v-if="creativeAssets.length" :src="creativeAssets[0].preview" alt="印花素材预览"/><template v-else><b>✿</b><span>点击上传印花图</span><small>JPG、PNG、WebP，单张最大 3MB</small></template><button v-if="creativeAssets.length" type="button" class="asset-count" @click.prevent="showCreativeAssetsDialog=true">{{creativeAssets.length}}</button></label><p v-if="creativeAssetError" class="creative-asset-error" role="alert">{{creativeAssetError}}</p><button v-if="creativeAssets.length" class="manage-assets" @click="showCreativeAssetsDialog=true">管理 {{creativeAssets.length}} 张印花图</button></article><article class="white-image-picker"><label>产品模板</label><select v-model="selectedTemplateId" @change="onCreativeTemplateChange"><option v-for="t in templates" :key="t.id" :value="t.id">{{t.name}}</option></select><label class="white-image-label">产品白底图 <b>*</b></label><select v-model="selectedWhiteImageId" :disabled="personalResourcesLoading || !personalWhiteImages.length"><option :value="null">{{personalWhiteImages.length ? '请选择白底图' : '尚未设置白底图'}}</option><option v-for="item in personalWhiteImages" :key="item.id" :value="item.id">{{item.name}}</option></select><div v-if="selectedWhiteImage" class="product-preview template-preview"><img :src="imageUrl(selectedWhiteImage.image_url)" :alt="selectedWhiteImage.name"/></div><div v-else class="white-image-empty"><span>{{personalWhiteImages.length ? '请从上方选择一张白底图' : '尚未设置该模板的白底图，请先设置'}}</span><button v-if="!personalWhiteImages.length" @click="openPersonalResourcesDialog('white-images')">立即设置</button></div></article><article class="settings"><label class="settings-title">创作参数</label><div class="parameter-fields"><label class="parameter-field"><span>AI模型</span><select v-model="creativeProvider" :disabled="!availableAiProviders.length"><option v-if="!availableAiProviders.length" value="">暂无后台已启用的模型</option><option v-for="provider in availableAiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}{{provider.credential_configured ? '' : ' · 未配置密钥'}}</option></select><small v-if="!availableAiProviders.length">请联系超级管理员在后台启用至少一个模型。</small></label><label class="parameter-field"><span>画面比例</span><select v-model="creativeRatio"><option>1:1</option><option>3:4</option></select></label><label class="parameter-field"><span>清晰度</span><select v-model="creativeQuality"><option>1K</option><option>2K</option></select></label></div></article><aside class="estimate"><div v-if="creativeUploading" class="upload-progress"><span>上传中 {{creativeUploadedCount}} / {{creativeAssets.length}}</span><progress :max="creativeAssets.length" :value="creativeUploadedCount"></progress><small>上传完成后将按模型配置创建独立任务；中断后再次提交会续传未完成图片。</small></div><button class="primary full" :disabled="!availableAiProviders.length || creativeUploading || !selectedWhiteImageId || Boolean(creativeCredentialError)" @click="createTask">{{creativeUploading ? `上传中 ${creativeUploadedCount}/${creativeAssets.length}` : '✦ 开始印花贴合'}}</button><p v-if="creativeCredentialError || creativeSubmitError" class="creative-submit-error" role="alert">{{creativeCredentialError || creativeSubmitError}}</p></aside></div></section></section>
      <section v-else-if="page==='tasks'" class="page">
        <nav class="task-type-tabs" aria-label="任务类型">
          <button v-for="(label,type) in taskTypeLabels" :key="type" :class="{active:activeTaskType===type}" :disabled="taskListRefreshing" @click="switchTaskType(type)">
            <i class="task-type-tabs-icon" aria-hidden="true">{{type==='sku_image'?'🖼':type==='carousel'?'🎞':'🏷'}}</i>
            <span class="task-type-tabs-label">{{label}}</span>
            <span class="task-type-tabs-badge">{{taskTypeTotals[type] || 0}}</span>
            <em v-if="taskTypeFilteredTotals[type]!==null" class="task-type-tabs-filter">筛选 {{taskTypeFilteredTotals[type]}}</em>
          </button>
        </nav>
        <div class="section-heading task-center-heading"><div><span>筛选条件设置后需点击搜索；可多选失败任务批量重试，SKU 图任务还可批量审核结果图。</span><div class="task-filter-row"><label v-if="activeTaskType==='sku_image'" class="task-sku-search">SKU 批量查询<textarea v-model="taskSkuQuery" rows="3" placeholder="每行输入一个SKU"></textarea></label><label v-if="activeTaskType==='sku_image'">模版<select v-model="taskTemplateFilterId"><option :value="null">全部模版</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><label>状态<select v-model="taskStatusFilter"><option value="">全部状态</option><option v-for="(label,status) in taskStatusLabel" :key="status" :value="status">{{label}}</option></select></label><label v-if="user?.role==='company_admin'">创作人<select v-model="taskCreatorFilterId"><option :value="null">全部创作人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label><label>创建开始时间<input v-model="taskCreatedFrom" type="datetime-local"/></label><label>创建结束时间<input v-model="taskCreatedTo" type="datetime-local"/></label><button class="primary task-search-button" :disabled="taskListRefreshing" @click="searchTasks">{{taskListRefreshing ? '搜索中…' : '搜索'}}</button></div></div></div>
        <div v-if="selectedTaskIds.length" class="task-batch-bar"><strong>已选择 {{selectedTaskIds.length}} 个任务</strong><span class="task-batch-actions"><button v-if="selectedRetryTaskIds.length" class="primary" :disabled="batchRetryingTasks || taskListRefreshing" @click="retrySelectedTasks">{{batchRetryingTasks ? '批量重试中…' : `批量重试（${selectedRetryTaskIds.length}）`}}</button><button v-if="activeTaskType==='sku_image' && selectedClaimableTaskIds.length" class="primary" :disabled="batchClaimLoading || batchClaiming || batchRetryingTasks" @click="openBatchClaimDialog">批量审核（{{selectedClaimableTaskIds.length}}）</button></span></div>
        <section class="draft-table task-table refreshable-list" :aria-busy="taskListRefreshing">
          <div class="thead task-list-grid"><label class="material-checkbox material-select-all"><input type="checkbox" :checked="allSelectableTasksSelected" :indeterminate="someSelectableTasksSelected" :disabled="!selectablePagedTasks.length" aria-label="全选本页可批量操作任务" @change="toggleAllSelectableTasks"/><span>选择</span></label><span>任务编号</span><span>任务类型</span><span>创作素材</span><span>产品模版</span><span>AI模型</span><span>创建时间</span><span>创建人</span><span>外部任务 ID</span><span>状态</span><span>结果</span><span>处理信息</span><span>操作</span></div>
          <div v-for="task in pagedTasks" :key="task.id" class="trow task-list-grid" :class="{selected:selectedTaskIds.includes(task.id)}"><label class="material-checkbox"><input v-if="taskCanBeSelected(task)" type="checkbox" :checked="selectedTaskIds.includes(task.id)" :aria-label="`选择任务 ${task.id}`" @change="toggleTaskSelection(task.id)"/></label><strong>#{{task.id}}</strong><span>{{taskTypeLabel(task)}}</span><button v-if="task.parameters?.print_url" type="button" class="task-material-thumbnail" title="查看创作素材" aria-label="查看创作素材大图" @click.stop.prevent="openImagePreview(task.parameters.print_url, '创作素材')"><img :src="imageUrl(task.parameters.print_url)" alt="创作素材"/></button><span v-else>—</span><span>{{task.template_name || '—'}}</span><span class="ai-model-cell"><b>{{task.provider === 'grsai' ? 'Grsai' : task.provider || '默认模型'}}</b><small v-if="task.provider_model">{{task.provider_model}}</small></span><span>{{new Date(task.created_at).toLocaleString()}}</span><span>{{task.created_by_name || '历史记录缺失'}}</span><span class="provider-task-id"><code>{{task.provider_task_id || '—'}}</code><button v-if="task.provider_task_id" class="copy-icon-button" title="复制外部任务 ID" aria-label="复制外部任务 ID" @click="copyProviderTaskId(task)">⧉</button></span><span class="task-progress-cell"><span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span><small>{{task.progress?.total_prints || 0}} 张参考图 · 已提交 {{task.submit_attempts || 0}} 次</small></span><button v-if="task.result_urls?.[0]" type="button" class="task-material-thumbnail" title="查看结果图" aria-label="查看首张结果图" @click.stop.prevent="openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`)"><img :src="imageUrl(task.result_urls[0])" :alt="`任务 #${task.id} 结果图`"/></button><span v-else>—</span><span :class="{error: task.status==='failed'}">{{task.failure_reason || '—'}}</span><span class="task-actions"><button class="secondary" @click="openTaskDetail(task)">查看详情</button><button v-if="activeTaskType!=='sku_image'" class="secondary" @click="openImageWorkspaceFromTask(task)">打开草稿</button><button v-if="task.status==='failed'" class="secondary" :disabled="retryingTaskId===task.id || batchRetryingTasks" @click="retryTaskResult(task)">{{retryingTaskId===task.id ? '重试中…' : '重试任务'}}</button></span></div>
          <p v-if="!tasks.length && !taskListRefreshing" class="empty">暂无 AI 创作任务。</p><footer v-if="taskTotal" class="draft-pagination"><span>共 {{taskTotal}} 条</span><label>每页 <select v-model.number="taskPageSize" :disabled="taskListRefreshing" @change="changeTaskPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="taskListRefreshing || visibleTaskPage===1" @click="changeTaskPage(visibleTaskPage-1)">上一页</button><span>第 {{visibleTaskPage}} / {{taskPageCount}} 页</span><button :disabled="taskListRefreshing || visibleTaskPage===taskPageCount" @click="changeTaskPage(visibleTaskPage+1)">下一页</button></footer>
          <div v-if="taskListRefreshing" class="list-refresh-overlay" role="status"><i></i><span>正在刷新列表…</span></div>
        </section>
      </section>
      <section v-else-if="page==='creative-resources'" class="page creative-resources-page">
      <div class="material-usage-tabs" role="tablist" aria-label="创作资源类型"><button type="button" role="tab" :aria-selected="personalResourceTab==='white-images'" :class="{active:personalResourceTab==='white-images'}" @click="setResourceTab('white-images')">白底图</button><button type="button" role="tab" :aria-selected="personalResourceTab==='prompts'" :class="{active:personalResourceTab==='prompts'}" @click="setResourceTab('prompts')">创作要求</button><button type="button" role="tab" :aria-selected="personalResourceTab==='styles'" :class="{active:personalResourceTab==='styles'}" @click="setResourceTab('styles')">风格分组</button></div>
      <div class="creative-resource-filters">
        <label v-if="user?.role==='company_admin'">创建人<select v-model="managedResourceUserId" :disabled="personalResourceSaving"><option :value="null">全部成员</option><option v-for="owner in resourceOwners" :key="owner.id" :value="owner.id">{{owner.name}}</option></select></label>
        <label>产品模板<select v-model="resourceTemplateFilterId" :disabled="personalResourceSaving"><option :value="null">全部模板</option><option v-for="item in templates" :key="item.id" :value="item.id">{{item.name}}</option></select></label>
        <label v-if="personalResourceTab==='white-images'">状态<select v-model="resourceWhiteImageStatus" :disabled="personalResourceSaving"><option value="active">有效</option><option value="deleted">已删除</option></select></label>
        <label>搜索<input v-model="resourceQuery" :placeholder="personalResourceTab==='styles' ? '搜索风格名称' : '搜索名称'"/></label>
        <div class="creative-resource-filter-actions">
          <button type="button" class="secondary" :disabled="resourceSearchBusy" @click="searchCreativeResources">搜索</button>
          <button v-if="personalResourceTab!=='styles'" type="button" class="primary" :aria-label="personalResourceTab==='white-images' ? '新增白底图' : '新增创作要求'" :disabled="resourceSearchBusy" @click="openResourceEditor(personalResourceTab)">新增</button>
        </div>
      </div>
      <p v-if="managedResourcesLoading && personalResourceTab!=='styles'" role="status">正在加载创作资源…</p>

      <section v-if="personalResourceTab==='white-images'" class="creative-resource-pane" aria-label="白底图列表">
        <div class="creative-resource-toolbar"><span>共 {{visibleManagedWhiteImages.length}} 张白底图</span></div>
        <div class="creative-resource-table-wrap" :aria-busy="managedResourcesLoading">
          <table class="creative-resource-table white-image-resource-table">
            <thead><tr><th scope="col">ID</th><th scope="col">图片</th><th scope="col">模板</th><th scope="col">名称</th><th scope="col">创建时间</th><th scope="col">创建人</th><th scope="col">操作</th></tr></thead>
            <tbody><tr v-for="item in pagedManagedWhiteImages" :key="item.id"><td>{{item.id}}</td><td><button type="button" class="resource-table-thumbnail" :aria-label="`查看白底图 ${item.name}`" @click="openImagePreview(item.image_url,item.name)"><img :src="imageUrl(item.image_url)" :alt="item.name"/></button></td><td>{{resourceTemplateName(item)}}</td><td class="resource-name-cell">{{item.name}}</td><td class="resource-time-cell">{{resourceCreatedAt(item)}}</td><td>{{resourceOwnerName(item)}}</td><td><div v-if="item.deleted_at==null" class="creative-resource-row-actions"><button type="button" :disabled="personalResourceSaving" @click="openResourceEditor('white-images',item)">编辑</button><button type="button" class="danger" :disabled="personalResourceSaving" @click="deleteWhiteImage(item)">删除</button></div><span v-else class="resource-image-unavailable">已删除</span></td></tr>
              <tr v-if="!visibleManagedWhiteImages.length && !managedResourcesLoading"><td colspan="7" class="empty">暂无符合条件的白底图。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section v-else-if="personalResourceTab==='prompts'" class="creative-resource-pane" aria-label="创作要求列表">
        <div class="creative-resource-toolbar"><span>共 {{visibleManagedPrompts.length}} 条创作要求</span></div>
        <div class="creative-resource-table-wrap" :aria-busy="managedResourcesLoading">
          <table class="creative-resource-table prompt-resource-table">
            <thead><tr><th scope="col">ID</th><th scope="col">名称</th><th scope="col">模板</th><th scope="col">提示词</th><th scope="col">创建时间</th><th scope="col">创建人</th><th scope="col">操作</th></tr></thead>
            <tbody><tr v-for="item in pagedManagedPrompts" :key="item.id"><td>{{item.id}}</td><td class="resource-name-cell">{{item.name}}</td><td>{{resourceTemplateName(item)}}</td><td><div class="resource-prompt-content">{{item.content}}</div></td><td class="resource-time-cell">{{resourceCreatedAt(item)}}</td><td>{{resourceOwnerName(item)}}</td><td><div class="creative-resource-row-actions"><button type="button" :disabled="personalResourceSaving" @click="openResourceEditor('prompts',item)">编辑</button><button type="button" class="danger" :disabled="personalResourceSaving" @click="deletePersonalPrompt(item)">删除</button></div></td></tr>
              <tr v-if="!visibleManagedPrompts.length && !managedResourcesLoading"><td colspan="7" class="empty">暂无符合条件的创作要求。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <div v-else class="resource-styles-pane">
        <div class="creative-resource-toolbar"><span>共 {{visibleResourceStyles.length}} 个风格</span></div>
        <p>同一模板的风格在公司内共享，可用于素材归类。风格由白底图创建，永久保留，不支持删除。</p>
        <p v-if="materialStylesLoading" role="status">正在加载风格…</p>
        <div class="creative-resource-table-wrap" :aria-busy="materialStylesLoading">
          <table class="creative-resource-table style-resource-table">
            <thead><tr><th scope="col">ID</th><th scope="col">风格名称</th><th scope="col">白底图</th><th scope="col">模板</th><th scope="col">创建人</th><th scope="col">素材数量</th><th scope="col">来源状态</th></tr></thead>
            <tbody><tr v-for="item in pagedResourceStyles" :key="item.id"><td>{{item.id}}</td><td class="resource-name-cell">{{item.name}}</td><td><button v-if="item.white_image_url" type="button" class="resource-table-thumbnail" :aria-label="`查看风格白底图 ${item.name}`" @click="openImagePreview(item.white_image_url,item.name)"><img :src="imageUrl(item.white_image_url)" :alt="item.name"/></button><span v-else class="resource-image-unavailable">{{item.source_exists ? '无权查看' : '白底图已删除'}}</span></td><td>{{resourceTemplateName(item)}}</td><td>{{item.created_by_name || '历史记录缺失'}}</td><td>{{item.material_count}} 张素材</td><td><span class="chip" :class="item.source_exists ? 'purple' : 'blue'">{{item.source_exists ? '来源白底图存在' : '来源白底图已删除'}}</span></td></tr>
              <tr v-if="!visibleResourceStyles.length && !materialStylesLoading"><td colspan="7" class="empty">暂无符合条件的风格，新增白底图后自动创建。</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <footer class="draft-pagination creative-resource-pagination" aria-label="创作资源分页"><span>共 {{resourceTotal}} 条</span><label>每页 <select v-model.number="resourcePageSize" :disabled="resourcePaginationBusy"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button type="button" :disabled="resourcePaginationBusy || resourceVisiblePage===1" @click="changeResourcePage(resourceVisiblePage-1)">上一页</button><span>第 {{resourceVisiblePage}} / {{resourcePageCount}} 页</span><button type="button" :disabled="resourcePaginationBusy || resourceVisiblePage===resourcePageCount" @click="changeResourcePage(resourceVisiblePage+1)">下一页</button></footer>
      </section>
      <CrossCompanyCollection v-else-if="page==='collection' || page==='collection-history'" :key="page" :token="token" :templates="templates" :user="user" :history-only="page==='collection-history'" @back="page='materials';refresh()" @revoked="crossCompanyCollectionEnabled=false" @unauthorized="logout" @account="openMyAccountDialog" />
      <section v-else-if="page==='materials'" class="page">
        <div class="section-heading material-heading"><div><span>素材入库后将永久绑定产品模板和 SKU；请选择同一模板的素材创建商品草稿。</span><div class="material-usage-tabs"><button v-for="tab in materialUsageTabs" :key="tab.key" :class="{active:activeMaterialUsageTab===tab.key}" @click="changeMaterialUsageTab(tab.key)">{{tab.label}}</button></div></div><div class="material-import-actions"><button v-if="crossCompanyCollectionEnabled && user?.role==='company_admin'" class="secondary" @click="page='collection'">采集</button><button class="secondary" :disabled="materialTemplateDownloading" @click="downloadMaterialImportTemplate">{{materialTemplateDownloading ? '下载中…' : '下载模版'}}</button><button class="secondary" :disabled="materialImportPreviewing || materialImportSaving" @click="materialImportFileInput?.click()">{{materialImportPreviewing ? '解析中…' : '导入模版'}}</button><input ref="materialImportFileInput" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden @change="previewMaterialImport"/><label class="secondary material-upload-button" :class="{disabled: materialUploading}"><input type="file" multiple accept="image/png,image/jpeg,image/webp" :disabled="materialUploading" @change="chooseMaterialUploadFiles"/>{{materialUploading ? '上传中…' : '上传本地素材'}}</label></div></div>
        <div class="material-filter-row material-search-filters"><label class="material-template-filter">产品模板<select v-model="materialTemplateFilterId"><option :value="null">全部模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><label class="material-template-filter material-style-filter">风格<SearchableSelect v-model="materialStyleFilterId" :options="materialStyleFilterOptions" :disabled="materialStylesLoading" search-placeholder="搜索风格或创建人"/></label><label v-if="user?.role==='company_admin'" class="material-template-filter">创作人<select v-model="materialCreatorFilterId"><option :value="null">全部创作人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label><label class="material-template-filter">类型<select v-model="materialSourceTypeFilter"><option value="">全部类型</option><option value="ai_created">AI创作</option><option value="local_upload">本地上传</option><option value="imported">导入</option><option v-if="crossCompanyCollectionEnabled" value="cross_company">采集</option></select></label><label class="material-template-filter material-time-filter">创建开始时间<input v-model="materialCreatedFrom" type="datetime-local"/></label><label class="material-template-filter material-time-filter">创建结束时间<input v-model="materialCreatedTo" type="datetime-local"/></label><button class="primary material-search-button" :disabled="materialListRefreshing" @click="searchMaterials">{{materialListRefreshing ? '搜索中…' : '搜索'}}</button></div>
        <p v-if="materialUploadError" class="error material-upload-error">{{materialUploadError}}</p>
        <section v-if="selectedMaterialAssetIds.length" class="material-draft-bar"><strong>已选 {{selectedMaterialAssetIds.length}} 张素材</strong><button class="primary" @click="openMaterialDraftDialog">创建商品草稿</button><button class="primary" @click="openMaterialBatchDraftDialog">组合创建草稿</button><button class="secondary" :disabled="materialSettingSaving" @click="openMaterialSetting('infringement')">设置侵权状态</button><button class="secondary" :disabled="materialSettingSaving || materialStylesLoading" @click="openMaterialSetting('style')">设置风格</button><button class="negative" :disabled="materialSettingSaving" @click="deleteSelectedMaterialAssets">删除选中素材</button><button class="ghost" @click="selectedMaterialAssetIds=[]">取消选择</button></section>
        <section class="draft-table material-list refreshable-list" :aria-busy="materialListRefreshing">
          <div class="thead material-thead"><label class="material-checkbox material-select-all"><input type="checkbox" :checked="allCurrentMaterialAssetsSelected" :indeterminate="someCurrentMaterialAssetsSelected" :disabled="!filteredMaterialAssets.some(asset=>asset.sku)" aria-label="全选本页可用素材" @change="toggleAllCurrentMaterialAssets"/><span>全选</span></label><span>缩略图</span><span>SKU</span><span>模板 / 风格</span><span>类型</span><span>是否侵权</span><span>创建时间</span><span>创建人</span></div>
          <div v-for="asset in filteredMaterialAssets" :key="asset.id" class="trow material-trow" :class="{selected: selectedMaterialAssetIds.includes(asset.id)}"><label class="material-checkbox" :aria-label="`选择素材 ${asset.name}`"><input type="checkbox" :checked="selectedMaterialAssetIds.includes(asset.id)" :disabled="!asset.sku" @change="toggleMaterialAsset(asset.id)"/></label><button type="button" class="material-list-thumbnail" :title="asset.name" :aria-label="`预览素材 ${asset.name}`" @click="openImagePreview(asset.url, asset.name)"><img :src="imageUrl(asset.url)" :alt="asset.name"/></button><code :class="{error:!asset.sku}">{{asset.sku || '无 SKU，请重新上传或领取'}}</code><span class="material-template-style"><span>{{asset.template_name || materialTemplateName(asset)}}</span><small class="material-style-badge" :class="{ungrouped:!asset.style_id}" :title="asset.style_name || '未分组'">{{asset.style_name || '未分组'}}</small></span><span class="material-type-cell"><i class="chip" :class="asset.source_type === 'ai_created' ? 'purple' : 'blue'">{{materialSourceLabel(asset.source_type)}}</i><button v-if="asset.collection_source" type="button" class="material-detail-icon" title="素材采集来源" aria-label="素材采集来源" @click.stop="materialCollectionDetail=asset"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.5" r=".8" fill="currentColor" stroke="none"/></svg></button><small v-if="asset.source_task_id" class="material-source-task">任务 #{{asset.source_task_id}}</small></span><span><InfringementBadge :is-infringing="!!asset.is_infringing"/></span><span>{{new Date(asset.created_at).toLocaleString()}}</span><span>{{asset.created_by_name || '历史记录缺失'}}</span></div>
          <div v-if="!filteredMaterialAssets.length && !materialListRefreshing" class="empty">{{materialTotal ? '没有符合筛选条件的素材。' : '暂无素材。可上传本地图片，或在任务中心领取生成图片。'}}</div><footer v-if="materialTotal" class="draft-pagination"><span>共 {{materialTotal}} 条</span><label>每页 <select v-model.number="materialPageSize" :disabled="materialListRefreshing" @change="changeMaterialPageSize"><option v-for="size in materialPageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="materialListRefreshing || visibleMaterialPage===1" @click="changeMaterialPage(visibleMaterialPage-1)">上一页</button><span>第 {{visibleMaterialPage}} / {{materialPageCount}} 页</span><button :disabled="materialListRefreshing || visibleMaterialPage===materialPageCount" @click="changeMaterialPage(visibleMaterialPage+1)">下一页</button></footer>
          <div v-if="materialListRefreshing" class="list-refresh-overlay" role="status"><i></i><span>正在刷新列表…</span></div>
        </section>
      </section>
      <section v-else-if="page==='drafts'" class="page">
        <div class="section-heading draft-heading"><div><span>本地草稿可批量导出 TikTok 或 Shopee 表格，也可手动发布至妙手后认领到 TikTok 采集箱。</span><div class="material-filter-row"><label class="draft-template-filter">产品模板<select v-model="draftTemplateFilterId" @change="changeDraftTemplateFilter"><option :value="null">全部模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><label v-if="user?.role==='company_admin'" class="draft-template-filter">创作人<select v-model="draftCreatorFilterId" @change="changeDraftCreatorFilter"><option :value="null">全部创作人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div></div><div class="draft-heading-actions"><button class="primary" @click="page='materials'">新建商品草稿</button></div></div>
        <nav class="draft-tabs" aria-label="商品草稿流程"><button v-for="item in draftTabs" :key="item.key" :class="{active:activeDraftTab===item.key}" @click="changeDraftTab(item.key)">{{item.label}} <b>({{draftTabCounts[item.key] || 0}})</b></button></nav>
        <nav v-if="activeDraftTab==='carousel_pending' || activeDraftTab==='main_image_pending'" class="draft-work-status-tabs" aria-label="制作状态"><button v-for="item in draftWorkStatusTabs" :key="item.key" :class="{active:activeDraftWorkStatus===item.key}" @click="changeDraftWorkStatus(item.key)">{{item.label}} <b>({{draftWorkStatusCounts[item.key] || 0}})</b></button></nav>
        <section v-if="selectedDraftIds.length" class="draft-export-bar"><strong>已选择 {{selectedDraftIds.length}} / {{MAX_DRAFT_BATCH_SIZE}} 条商品草稿</strong><template v-if="batchDispatchEligible"><button class="primary" :disabled="!!dispatchingDraftStage" @click="dispatchSelectedDrafts('carousel_pending')">{{dispatchingDraftStage==='carousel_pending' ? '分发中…' : '去做轮播图'}}</button><button class="secondary" :disabled="!!dispatchingDraftStage" @click="dispatchSelectedDrafts('main_image_pending')">{{dispatchingDraftStage==='main_image_pending' ? '分发中…' : '去做主图'}}</button><button class="secondary" :disabled="!!dispatchingDraftStage" @click="dispatchSelectedDrafts('ready_to_publish')">{{dispatchingDraftStage==='ready_to_publish' ? '分发中…' : '直接到待发布'}}</button></template><button v-if="batchCarouselEligible" class="primary" @click="openBatchCarouselDialog">批量制作轮播图</button><button v-if="batchCarouselSkipEligible" class="secondary" :disabled="batchCarouselSkipping" @click="batchSkipDraftCarousel">{{batchCarouselSkipping ? '跳过中…' : '批量跳过轮播图制作'}}</button><button v-if="batchCarouselReviewEligible" class="primary" @click="openBatchImageReview('carousel')">批量审核轮播图</button><button v-if="batchMainImageEligible" class="primary" @click="openBatchMainImageDialog">批量制作主图</button><button v-if="batchMainImageSkipEligible" class="secondary" :disabled="batchMainImageSkipping" @click="batchSkipDraftMainImage">{{batchMainImageSkipping ? '跳过中…' : '批量跳过首图制作'}}</button><button v-if="batchMainImageReviewEligible" class="primary" @click="openBatchImageReview('main_image')">批量审核首图</button><button v-if="batchMiaoshouPublishEligible" class="primary" @click="openBatchMiaoshouPublishDialog">批量发布至妙手</button><button v-if="tiktokExportEligible" class="primary" @click="openTiktokExportDialog">导出 TikTok 表格</button><button v-if="tiktokExportEligible" class="primary" @click="openShopeeExportDialog">导出 Shopee 表格</button><button class="ghost" @click="selectedDraftIds=[]">取消选择</button></section>
        <div class="draft-table task-table refreshable-list" :aria-busy="draftListRefreshing">
          <div class="thead draft-thead">
            <label class="material-checkbox" aria-label="选择当前页商品草稿"><input type="checkbox" :checked="allPagedDraftsSelected" @change="togglePagedDrafts"/></label>
            <span>ID</span><span>商品</span><span>模板</span><span>商品标题</span><span>SKU 数量</span><span>创建时间</span><span>创作人</span><span>轮播图</span><span>导出次数</span><span>状态</span><span>操作</span>
          </div>
          <div v-for="draft in pagedDrafts" :key="draft.id" class="trow draft-trow" :class="{selected:selectedDraftIds.includes(draft.id)}">
            <label class="material-checkbox" :aria-label="`选择商品草稿 ${draft.id}`"><input type="checkbox" :checked="selectedDraftIds.includes(draft.id)" :disabled="selectedDraftIds.length >= MAX_DRAFT_BATCH_SIZE && !selectedDraftIds.includes(draft.id)" @change="toggleDraftSelection(draft.id)"/></label>
            <strong>{{draft.id}}</strong>
            <button v-if="draft.image_urls?.[0]" class="draft-thumbnail" title="查看大图" @click="openImagePreview(draft.image_urls[0], draft.title)"><img :src="imageUrl(draft.image_urls[0])" :alt="draft.title"/></button><span v-else></span>
            <span>{{draftTemplateName(draft)}}</span><b class="draft-product-title" :title="draft.title">{{draft.title}}</b><span>{{draft.sku_items?.length || 1}}</span><span>{{new Date(draft.created_at).toLocaleString()}}</span><span>{{draft.created_by_name || '历史记录缺失'}}</span>
            <span class="draft-carousel-flag" :class="draft.carousel_items?.length ? 'has' : 'none'">{{draft.carousel_items?.length ? '有' : '无'}}</span><span>{{draft.export_count || 0}}</span>
            <span class="draft-status-cell">
              <span class="chip" :class="draft.display_tab==='published' ? 'blue' : 'purple'">{{draftStatusLabels[draft.display_tab] || draft.display_tab}}</span>
              <small v-if="draft.display_tab==='carousel_pending' || draft.display_tab==='main_image_pending'">{{({not_started:'未制作',in_progress:'制作中',awaiting_review:'待审核',failed:'制作失败'} as any)[draftWorkSummary(draft)?.work_status]}}<template v-if="draftWorkSummary(draft)?.work_status==='in_progress' && draftWorkSummary(draft)?.awaiting_selection">（含待审核结果）</template></small>
              <small v-if="draftWorkSummary(draft)?.failed" class="error">{{draftWorkSummary(draft)?.failure_reasons?.[0] || '存在失败任务'}}</small>
            </span>
            <span class="draft-trow-actions">
              <button @click="openDraftEditDialog(draft)">编辑</button>
              <template v-if="draft.display_tab==='carousel_pending'"><button class="primary compact-action" @click="openCarouselImageWorkspace(draft)">轮播图工作台</button><button class="secondary compact-action" :disabled="skippingCarouselDraftId===draft.id" @click="skipDraftCarousel(draft)">{{skippingCarouselDraftId===draft.id ? '跳过中…' : '跳过轮播图制作'}}</button></template>
              <template v-else-if="draft.display_tab==='main_image_pending'"><button class="primary compact-action" @click="openFullImageWorkspace(draft,true)">首图工作台</button><button class="secondary compact-action" :disabled="skippingMainImageDraftId===draft.id" @click="skipDraftMainImage(draft)">{{skippingMainImageDraftId===draft.id ? '跳过中…' : '跳过首图制作'}}</button></template>
              <button v-else-if="draft.display_tab!=='pending'" @click="openFullImageWorkspace(draft)">图片工作台</button>
              <button v-if="draft.display_tab==='ready_to_publish'" class="primary compact-action" :disabled="publishingDraftId===draft.id" @click="publishDraftToMiaoshou(draft)">{{publishingDraftId===draft.id ? '处理中…' : '发布至妙手'}}</button>
            </span>
          </div>
          <div v-if="!filteredDrafts.length && !draftListRefreshing" class="empty">{{draftTotal ? '没有符合筛选条件的商品草稿。' : '暂无商品草稿，请先在任务中心领取素材，或上传本地素材。'}}</div>
          <footer v-else-if="!draftListRefreshing || draftTotal" class="draft-pagination"><span>共 {{draftTotal}} 条</span><label>每页 <select v-model.number="draftPageSize" :disabled="draftListRefreshing" @change="changeDraftPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="draftListRefreshing || visibleDraftPage===1" @click="changeDraftPage(visibleDraftPage-1)">上一页</button><span>第 {{visibleDraftPage}} / {{draftPageCount}} 页</span><button :disabled="draftListRefreshing || visibleDraftPage===draftPageCount" @click="changeDraftPage(visibleDraftPage+1)">下一页</button></footer>
          <div v-if="draftListRefreshing" class="list-refresh-overlay" role="status"><i></i><span>正在刷新列表…</span></div>
        </div>
      </section>
      <section v-else-if="page==='product-library'" class="page">
        <div class="section-heading product-library-heading">
          <div><span>按基础 SKU 汇总：订单数按订单去重，销量为各尺码销售数量之和。</span></div>
          <div v-if="user?.role==='company_admin'" class="product-library-actions">
            <button class="secondary" :disabled="productLibraryDownloading" @click="downloadProductLibraryTemplate">{{productLibraryDownloading ? '下载中…' : '下载导入模版'}}</button>
            <button class="primary" :disabled="productLibraryImporting" @click="productLibraryFileInput?.click()">{{productLibraryImporting ? '导入中…' : '导入'}}</button>
            <button class="secondary" type="button" :disabled="productLibraryStatisticsSubmitting || productLibraryImporting" @click="runProductLibraryStatistics">{{productLibraryStatisticsSubmitting ? '提交中…' : '数据统计'}}</button>
            <input ref="productLibraryFileInput" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden @change="importProductLibrary"/>
          </div>
        </div>
        <p v-if="productLibraryStatisticsTask" class="product-library-category-description" role="status">
          <template v-if="productLibraryStatisticsTask.status==='queued'">统计任务排队中（{{productLibraryStatisticsTask.snapshot_date}} 榜单）</template>
          <template v-else-if="productLibraryStatisticsTask.status==='running'">正在后台统计（{{productLibraryStatisticsTask.snapshot_date}} 榜单）</template>
          <template v-else-if="productLibraryStatisticsTask.status==='succeeded'">最近一次统计已完成：截至 {{productLibraryStatisticsTask.through_date}}</template>
          <template v-else>最近一次统计失败，请点击“数据统计”重试。</template>
        </p>
        <div class="material-usage-tabs product-library-tabs" role="tablist" aria-label="产品库分类"><button v-for="tab in productLibraryTabs.filter(item => item.key !== 'shops' || user?.role === 'company_admin')" :key="tab.key" type="button" role="tab" :aria-selected="activeProductLibraryTab===tab.key" :class="{active:activeProductLibraryTab===tab.key}" @click="changeProductLibraryTab(tab.key)">{{tab.label}}</button></div>
        <p v-if="productLibraryCategoryDescriptions[activeProductLibraryTab]" class="product-library-category-description">{{productLibraryCategoryDescriptions[activeProductLibraryTab]}}</p>
        <div v-if="activeProductLibraryTab==='products' || productLibraryRankingTabKeys.has(activeProductLibraryTab)" class="product-library-filters">
          <div class="product-library-shop-filter"><span>店铺名称</span><details ref="productLibraryShopFilterDetails"><summary><span :title="productLibraryShopSelectionLabel">{{productLibraryShopSelectionLabel}}</span><span aria-hidden="true">▾</span></summary><div class="product-library-shop-filter-panel"><input v-model="productLibraryShopSearch" type="search" placeholder="搜索平台、站点或店铺" aria-label="搜索店铺"/><div class="product-library-shop-filter-actions"><span>可选 {{productLibraryShopOptions.length }} 家</span><button type="button" :disabled="!productLibrarySelectedShopIds.length" @click="productLibrarySelectedShopIds=[]">清空选择</button></div><div class="product-library-shop-filter-options"><label v-for="shop in productLibraryShopOptions" :key="shop.id" class="product-library-shop-filter-option"><input v-model="productLibrarySelectedShopIds" type="checkbox" :value="shop.id"/><span>{{shop.label}}</span></label><p v-if="!productLibraryShopOptions.length" class="product-library-shop-filter-empty">没有匹配的店铺</p></div></div></details></div>
          <label v-if="activeProductLibraryTab==='products'">模版<select v-model="productLibraryTemplateFilter" :disabled="productLibraryLoading"><option value="">全部模版</option><option value="unmatched">未匹配</option><option v-for="item in templates" :key="item.id" :value="String(item.id)">{{item.name}}</option></select></label>
          <label v-if="activeProductLibraryTab==='products'">SKU<input v-model="productLibrarySku" type="search" placeholder="输入 SKU" :disabled="productLibraryLoading"/></label>
          <label>创建人<select v-model="productLibraryCreatorId" :disabled="productLibraryLoading || productLibraryRankingLoading"><option :value="null">全部创建人</option><option v-for="creator in productLibraryCreatorOptions" :key="creator.id" :value="creator.id">{{creator.name}}</option></select></label>
          <button type="button" class="primary product-library-search-button" :disabled="productLibraryLoading || productLibraryRankingLoading" @click="searchProductLibrary">搜索</button>
        </div>
        <section v-if="activeProductLibraryTab!=='shops' && selectedProductLibraryIds.length" class="draft-export-bar product-library-selection-bar"><strong>已选 {{selectedProductLibraryIds.length}} / {{MAX_PRODUCT_LIBRARY_SELECTION}} 条</strong><button class="primary" :disabled="productLibrarySelectionLoading" @click="openProductLibraryDraftDialog()">创建商品草稿</button><button class="primary" :disabled="productLibrarySelectionLoading" @click="openProductLibraryDraftDialog(true)">组合创建草稿</button><button v-if="user?.role==='company_admin'" class="primary" :disabled="productLibrarySelectionLoading" @click="openProductLibraryTemplateDialog">批量设置模版</button><button class="ghost" @click="selectedProductLibraryIds=[]">取消选择</button></section>
        <div v-if="activeProductLibraryTab==='products'" class="draft-table product-library-table" :aria-busy="productLibraryLoading">
          <div class="thead product-library-head"><label class="product-library-select-heading"><input type="checkbox" :checked="allPagedProductsSelected" :disabled="!selectableProductLibraryItems.length || productLibraryLoading" aria-label="选择当前页产品" @change="togglePagedProducts"/>商品</label><span>SKU</span><span>模版</span><span>标题</span><ShopDataHeading/><span>创建人</span><span>创建时间</span><span>订单数</span><span>销量</span><span>操作</span></div>
          <div v-for="item in activeProductLibraryTab==='products' ? productLibraryItems : []" :key="item.id" class="trow product-library-row">
            <div class="product-library-product-cell"><input type="checkbox" :checked="selectedProductLibraryIds.includes(item.id)" :disabled="selectedProductLibraryIds.length >= MAX_PRODUCT_LIBRARY_SELECTION && !selectedProductLibraryIds.includes(item.id)" :aria-label="`选择产品 ${item.sku}`" @change="toggleProductLibrarySelection(item)"/><button v-if="item.image_url && !productLibraryBrokenImages.includes(item.id)" class="product-library-image" title="查看大图" :aria-label="`查看 ${item.sku} 商品大图`" @click="openImagePreview(item.image_url, item.title || item.sku)"><img :key="item.image_url" :src="imageUrl(item.image_url)" :alt="item.title || item.sku" @error="productLibraryBrokenImages.push(item.id)"/></button><span v-else class="product-library-image">暂无图片</span></div>
            <span class="product-library-code" :title="item.sku">{{item.sku}}</span><span>{{item.template}}</span>
            <span class="product-library-title" :title="item.title">{{item.title || '—'}}</span><span class="product-library-shop-data"><span v-for="shop in item.shop_data" :key="`${shop.source_id}-${shop.product_id}`">{{shop.shop_name}}-{{shop.product_id}}-{{shop.sales_quantity}}</span></span><span>{{item.material_created_by_name || ''}}</span><span>{{item.material_created_at != null ? new Date(item.material_created_at).toLocaleString() : ''}}</span><strong>{{item.order_count}}</strong><strong>{{item.sales_quantity}}</strong><button class="product-library-detail-button" type="button" title="查看详情" :aria-label="`查看 ${item.sku} 的订单详情`" @click="openProductLibraryOrders(item)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.8"/></svg></button>
          </div>
          <div v-if="activeProductLibraryTab!=='products'" class="empty">暂无产品。</div>
          <div v-else-if="!productLibraryItems.length && !productLibraryLoading" class="empty">{{productLibraryTotal ? '没有符合筛选条件的产品。' : user?.role==='company_admin' ? '暂无产品，请先下载模版并导入历史订单。' : '暂无可查看的产品，请联系管理员分配店铺。'}}</div>
          <footer v-if="activeProductLibraryTab==='products'" class="draft-pagination product-library-pagination"><span>共 {{productLibraryTotal}} 条</span><label>每页 <select v-model.number="productLibraryPageSize" :disabled="productLibraryLoading" @change="changeProductLibraryPageSize"><option v-for="size in productLibraryPageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="productLibraryLoading || productLibraryPage===1" @click="changeProductLibraryPage(productLibraryPage-1)">上一页</button><span>第 {{productLibraryPage}} / {{productLibraryPageCount}} 页</span><button :disabled="productLibraryLoading || productLibraryPage===productLibraryPageCount" @click="changeProductLibraryPage(productLibraryPage+1)">下一页</button></footer>
          <footer v-else class="draft-pagination product-library-pagination"><span>共 0 条</span></footer>
          <div v-if="activeProductLibraryTab==='products' && productLibraryLoading" class="list-refresh-overlay" role="status"><i></i><span>正在加载产品库…</span></div>
        </div>
        <div v-else-if="activeProductLibraryTab==='shops' && user?.role==='company_admin'" class="product-library-ranking-section">
          <p class="product-library-category-description">导入订单后自动保存平台、站点和店铺。每个店铺最多分配一位运营；组长可见组员数据；未分配店铺仅管理员可见。</p>
          <div class="draft-table product-library-table" :aria-busy="productLibraryShopsLoading">
            <div class="thead" style="grid-template-columns:1fr 1fr 2fr 2fr"><span>平台</span><span>站点</span><span>店铺名称</span><span>负责运营</span></div>
            <div v-for="shop in productLibraryShops" :key="shop.id" class="trow" style="grid-template-columns:1fr 1fr 2fr 2fr"><span>{{shop.platform}}</span><span>{{shop.site}}</span><strong>{{shop.shop_name}}</strong><select :value="shop.assigned_user_id ?? ''" :disabled="productLibraryAssigningId===shop.id" :aria-label="`分配 ${shop.shop_name} 的负责运营`" @change="assignProductLibraryShop(shop, $event)"><option value="">未分配</option><option v-for="member in members.filter(item => (item.role==='member' || item.role==='team_leader') && (item.is_active || item.id===shop.assigned_user_id))" :key="member.id" :value="member.id">{{member.name}} · {{operatorGroupName(member.group_id)}} · {{memberRoleLabel(member)}}</option></select></div>
            <p v-if="!productLibraryShops.length && !productLibraryShopsLoading" class="empty">暂无店铺，请先导入产品库订单。</p>
            <div v-if="productLibraryShopsLoading" class="list-refresh-overlay" role="status"><i></i><span>正在加载店铺…</span></div>
          </div>
        </div>
        <div v-else-if="activeProductLibraryTab==='stagnant'" class="product-library-ranking-section">
          <div v-if="user?.role==='company_admin'" class="product-library-filters"><label>创建人<select v-model="stagnantCreatorId" :disabled="stagnantLoading" @change="changeStagnantCreator"><option :value="null">全部创建人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div>
          <div class="draft-table product-library-table" :aria-busy="stagnantLoading">
            <div class="thead product-library-stagnant-grid"><label class="product-library-select-heading"><input type="checkbox" :checked="allPagedProductsSelected" :disabled="!selectableProductLibraryItems.length || productLibrarySelectionLoading" aria-label="选择当前页数据" @change="togglePagedProducts"/>商品</label><span>SKU</span><span>模版</span><span>创建人</span><span>创建时间</span></div>
            <div v-for="item in stagnantMaterials" :key="item.id" class="trow product-library-stagnant-grid">
              <div class="product-library-product-cell"><input type="checkbox" :checked="selectedProductLibraryIds.includes(item.id)" :disabled="productLibrarySelectionLoading || (selectedProductLibraryIds.length >= MAX_PRODUCT_LIBRARY_SELECTION && !selectedProductLibraryIds.includes(item.id))" :aria-label="`选择 ${item.sku || '素材'}`" @change="toggleProductLibrarySelection(item)"/><button v-if="item.image_url && !productLibraryBrokenImages.includes(item.id)" class="product-library-image" title="查看大图" :aria-label="`查看 ${item.sku} 素材大图`" @click="openImagePreview(item.image_url, item.sku)"><img :src="imageUrl(item.image_url)" :alt="item.sku" @error="productLibraryBrokenImages.push(item.id)"/></button><span v-else class="product-library-image">暂无图片</span></div>
              <span class="product-library-code" :title="item.sku">{{item.sku}}</span><span>{{item.template}}</span><span>{{item.created_by_name}}</span><span>{{new Date(item.created_at).toLocaleString()}}</span>
            </div>
            <div v-if="!stagnantMaterials.length && !stagnantLoading && !stagnantError" class="empty">暂无符合条件的素材。</div>
            <footer class="draft-pagination product-library-stagnant-pagination"><span>共 {{stagnantTotal}} 条</span><label>每页 <select v-model.number="stagnantPageSize" :disabled="stagnantLoading" @change="changeStagnantPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="stagnantLoading || stagnantPage===1" @click="changeStagnantPage(stagnantPage-1)">上一页</button><span>第 {{stagnantPage}} / {{stagnantPageCount}} 页</span><button :disabled="stagnantLoading || stagnantPage===stagnantPageCount" @click="changeStagnantPage(stagnantPage+1)">下一页</button></footer>
            <div v-if="stagnantLoading" class="list-refresh-overlay" role="status"><i></i><span>正在加载滞销素材…</span></div>
          </div>
        </div>
        <div v-else-if="activeProductLibraryTab==='new_images'" class="product-library-ranking-section">
          <div class="product-library-filters">
            <label v-if="user?.role==='company_admin'">创建人<select v-model="newImagesCreatorId" :disabled="newImagesLoading" @change="changeNewImagesFilters"><option :value="null">全部创建人</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label>
            <label>使用状态<select v-model="newImagesUsageStatus" :disabled="newImagesLoading" @change="changeNewImagesFilters"><option value="all">全部状态</option><option value="unused">未使用</option><option value="used">已使用</option></select></label>
          </div>
          <div class="draft-table product-library-table" :aria-busy="newImagesLoading">
            <div class="thead product-library-new-images-grid"><label class="product-library-select-heading"><input type="checkbox" :checked="allPagedProductsSelected" :disabled="!selectableProductLibraryItems.length || productLibrarySelectionLoading" aria-label="选择当前页数据" @change="togglePagedProducts"/>商品</label><span>SKU</span><span>模版</span><span>创建人</span><span>创建时间</span><span>使用状态</span></div>
            <div v-for="item in newImages" :key="item.id" class="trow product-library-new-images-grid">
              <div class="product-library-product-cell"><input type="checkbox" :checked="selectedProductLibraryIds.includes(item.id)" :disabled="productLibrarySelectionLoading || (selectedProductLibraryIds.length >= MAX_PRODUCT_LIBRARY_SELECTION && !selectedProductLibraryIds.includes(item.id))" :aria-label="`选择 ${item.sku || '素材'}`" @change="toggleProductLibrarySelection(item)"/><button v-if="item.image_url && !productLibraryBrokenImages.includes(item.id)" class="product-library-image" title="查看大图" :aria-label="`查看 ${item.sku || '素材'} 大图`" @click="openImagePreview(item.image_url, item.sku || '素材')"><img :src="imageUrl(item.image_url)" :alt="item.sku || '素材'" @error="productLibraryBrokenImages.push(item.id)"/></button><span v-else class="product-library-image">暂无图片</span></div>
              <span class="product-library-code" :title="item.sku || ''">{{item.sku || '—'}}</span><span>{{item.template}}</span><span>{{item.created_by_name}}</span><span>{{new Date(item.created_at).toLocaleString()}}</span><span>{{item.usage_status==='used'?'已使用':'未使用'}}</span>
            </div>
            <div v-if="!newImages.length && !newImagesLoading && !newImagesError" class="empty">暂无符合条件的素材。</div>
            <footer class="draft-pagination product-library-new-images-pagination"><span>共 {{newImagesTotal}} 条</span><label>每页 <select v-model.number="newImagesPageSize" :disabled="newImagesLoading" @change="changeNewImagesPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="newImagesLoading || newImagesPage===1" @click="changeNewImagesPage(newImagesPage-1)">上一页</button><span>第 {{newImagesPage}} / {{newImagesPageCount}} 页</span><button :disabled="newImagesLoading || newImagesPage===newImagesPageCount" @click="changeNewImagesPage(newImagesPage+1)">下一页</button></footer>
            <div v-if="newImagesLoading" class="list-refresh-overlay" role="status"><i></i><span>正在加载新图…</span></div>
          </div>
        </div>
        <div v-else-if="!productLibraryRankingTabKeys.has(activeProductLibraryTab)" class="draft-table product-library-table"><div class="empty">暂无产品。</div><footer class="draft-pagination product-library-pagination"><span>共 0 条</span></footer></div>
        <div v-else class="product-library-ranking-section">
          <p v-if="productLibraryRankingDate" class="product-library-ranking-date">{{productLibraryRankingDate}} 榜单 · 统计截至 {{productLibraryRankingThroughDate}}</p>
          <div class="draft-table product-library-table" :aria-busy="productLibraryRankingLoading">
            <div class="thead product-library-ranking-grid"><span>名次</span><label class="product-library-select-heading"><input type="checkbox" :checked="allPagedProductsSelected" :disabled="!selectableProductLibraryItems.length || productLibrarySelectionLoading" aria-label="选择当前页数据" @change="togglePagedProducts"/>商品</label><span>SKU</span><span>模版</span><span>标题</span><ShopDataHeading/><span>创建人</span><span>创建时间</span><span>订单数</span><span>销量</span><span>操作</span></div>
            <div v-for="item in productLibraryRankingItems" :key="item.id" class="trow product-library-ranking-grid">
              <strong class="product-library-ranking-rank">#{{item.rank}}</strong>
              <div class="product-library-product-cell"><input type="checkbox" :checked="selectedProductLibraryIds.includes(item.id)" :disabled="productLibrarySelectionLoading || (selectedProductLibraryIds.length >= MAX_PRODUCT_LIBRARY_SELECTION && !selectedProductLibraryIds.includes(item.id))" :aria-label="`选择 ${item.sku || '素材'}`" @change="toggleProductLibrarySelection(item)"/><button v-if="item.image_url && !productLibraryBrokenImages.includes(item.id)" class="product-library-image" title="查看大图" :aria-label="`查看 ${item.sku} 商品大图`" @click="openImagePreview(item.image_url, item.title || item.sku)"><img :src="imageUrl(item.image_url)" :alt="item.title || item.sku" @error="productLibraryBrokenImages.push(item.id)"/></button><span v-else class="product-library-image">暂无图片</span></div>
              <span class="product-library-code" :title="item.sku">{{item.sku}}</span><span>{{item.template}}</span><span class="product-library-title" :title="item.title">{{item.title || '—'}}</span><span class="product-library-shop-data"><span v-for="shop in item.shop_data" :key="`${shop.source_id}-${shop.product_id}`">{{shop.shop_name}}-{{shop.product_id}}-{{shop.sales_quantity}}</span></span><span>{{item.material_created_by_name || ''}}</span><span>{{item.material_created_at != null ? new Date(item.material_created_at).toLocaleString() : ''}}</span><strong>{{item.order_count}}</strong><strong>{{item.sales_quantity}}</strong><button class="product-library-detail-button" type="button" title="查看详情" :aria-label="`查看 ${item.sku} 的订单详情`" @click="openProductLibraryOrders(item)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.8"/></svg></button>
            </div>
            <div v-if="!productLibraryRankingItems.length && !productLibraryRankingLoading && !productLibraryRankingError" class="empty">{{productLibraryRankingDate ? '该榜单暂无符合条件的产品。' : user?.role==='company_admin' ? '尚未生成榜单，点击“数据统计”开始后台统计。' : '尚未生成榜单，请联系管理员进行数据统计。'}}</div>
            <footer v-if="productLibraryRankingDate" class="draft-pagination product-library-ranking-pagination"><span>共 {{productLibraryRankingTotal}} 条</span><template v-if="!productLibraryTopTabKeys.has(activeProductLibraryTab)"><label>每页 <select v-model.number="productLibraryRankingPageSize" :disabled="productLibraryRankingLoading" @change="changeProductLibraryRankingPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="productLibraryRankingLoading || productLibraryRankingPage===1" @click="changeProductLibraryRankingPage(productLibraryRankingPage-1)">上一页</button><span>第 {{productLibraryRankingPage}} / {{productLibraryRankingPageCount}} 页</span><button :disabled="productLibraryRankingLoading || productLibraryRankingPage===productLibraryRankingPageCount" @click="changeProductLibraryRankingPage(productLibraryRankingPage+1)">下一页</button></template></footer>
            <div v-if="productLibraryRankingLoading" class="list-refresh-overlay" role="status"><i></i><span>正在加载榜单…</span></div>
          </div>
        </div>
      </section>
      <section v-else-if="page==='miaoshou' && user?.role==='company_admin'" class="page">
          <p v-if="shopError" class="error">{{shopError}}</p>
          <div class="shop-actions"><span class="miaoshou-status" :class="company?.miaoshou_configured?'configured':'missing'">{{company?.miaoshou_configured?'妙手 API Key 已配置':'请先配置妙手 API Key'}}</span><button class="secondary" :disabled="miaoshouSaving || shopLoading" @click="openMiaoshouDialog">{{company?.miaoshou_configured?'更新 API Key':'配置 API Key'}}</button><button class="primary" :disabled="shopLoading || miaoshouSaving || !company?.miaoshou_configured" @click="loadMiaoshouShops">{{shopLoading ? '同步中…' : '↻ 同步妙手店铺'}}</button></div><section class="draft-table"><div class="thead" style="grid-template-columns:.65fr 1.2fr 1fr .75fr .7fr .9fr .9fr 1.3fr .8fr"><span>店铺 ID</span><span>店铺名称</span><span>店铺昵称</span><span>平台</span><span>站点</span><span>授权状态</span><span>授权到期</span><span>管理人员</span><span>操作</span></div><div v-for="shop in crossBorderManagedShops" :key="shop.id" class="trow" style="grid-template-columns:.65fr 1.2fr 1fr .75fr .7fr .9fr .9fr 1.3fr .8fr"><span>#{{shop.external_shop_id || shop.id}}</span><span><b>{{shop.name || '—'}}</b></span><span>{{shop.nickname || '—'}}</span><span>{{shop.platform || '—'}}</span><span>{{shop.region || '—'}}</span><span class="chip" :class="shop.auth_status ? 'blue' : 'orange'">{{shop.auth_status || '未知'}}</span><span>{{shop.auth_expires_at || '—'}}</span><span>{{shop.manager_users.length ? shop.manager_users.map((member:any)=>member.name).join('、') : '暂未分配'}}</span><span><button @click="openShopManagersDialog(shop)">分配人员</button></span></div><p v-if="!crossBorderManagedShops.length && !shopLoading" class="empty">{{company?.miaoshou_configured?'暂无已同步店铺，点击“同步妙手店铺”开始获取。':'配置妙手 API Key 后即可同步店铺。'}}</p></section>
      </section>
      <section v-else-if="page==='members' && user?.role==='company_admin'" class="page">
        <div class="section-heading"><div><span>管理本公司运营组、成员账号和每位员工独立的模型平台密钥。</span></div><div class="section-heading-actions"><button class="ghost" :disabled="memberListRefreshing" @click="refreshMemberList">{{memberListRefreshing ? '刷新中…' : '↻ 刷新'}}</button></div></div>
        <div class="section-heading operator-groups-heading"><h2>运营组</h2><button class="primary" @click="openOperatorGroupDialog()">新增组</button></div>
        <div class="operator-group-list">
          <article v-for="group in operatorGroups" :key="group.id" class="operator-group-card"><div><h3>{{group.name}}</h3><p>组长：{{members.find(member => member.id === group.leader_user_id)?.name || '—'}} · {{operatorGroupMembers(group.id).length}} 人</p></div><div class="operator-group-actions"><button @click="openOperatorGroupDialog(group)">更名</button><button class="negative" @click="deleteOperatorGroup(group)">删除</button></div></article>
          <p v-if="!operatorGroups.length" class="operator-groups-empty">暂无运营组。新增组时请选择一位已启用的普通运营担任组长。</p>
        </div>
        <div class="section-heading member-list-heading"><div class="member-list-title"><h2>公司成员</h2><span>共 {{members.length}} 人</span></div><button class="primary" @click="openMemberDialog()">新增成员</button></div>
        <section class="draft-table refreshable-list member-list-scroll" :aria-busy="memberListRefreshing"><div class="thead member-grid"><span>成员</span><span>用户代码</span><span>角色</span><span>运营组</span><span>邮箱</span><span>货盘管理权限</span><span>状态</span><span>加入时间</span><span>操作</span></div><div v-for="member in members" :key="member.id" class="trow member-grid"><span><b>{{member.name}}</b></span><span>{{member.user_code || '—'}}</span><span>{{memberRoleLabel(member)}}</span><span>{{member.group_id ? operatorGroupName(member.group_id) : '—'}}</span><span>{{member.email}}</span><span class="member-supply-access"><template v-if="member.role === 'member' || member.role === 'team_leader'"><span class="member-permission-status" :class="member.supply_admin ? 'configured' : 'missing'">{{member.supply_admin ? '已授予' : '未授予'}}</span><button :class="member.supply_admin ? 'negative' : 'positive'" :disabled="memberSupplyGrantSaving" :aria-label="`${member.supply_admin ? '撤销' : '授予'} ${member.name} 的货盘管理权限`" @click="toggleMemberSupplyGrant(member)">{{member.supply_admin ? '撤销权限' : '授予权限'}}</button></template><span v-else class="member-permission-status configured">默认拥有</span></span><span class="chip" :class="member.is_active ? 'blue' : 'orange'">{{member.is_active ? '启用中' : '已停用'}}</span><span>{{new Date(member.created_at).toLocaleDateString()}}</span><span class="member-row-actions"><template v-if="member.role === 'member' || member.role === 'team_leader'"><button @click="openMemberDialog(member)">编辑</button><button v-if="member.role !== 'team_leader'" :class="member.is_active ? 'negative' : 'positive'" @click="toggleMember(member)">{{member.is_active ? '停用' : '启用'}}</button></template><button v-for="provider in memberCredentialProviders" :key="provider.credential_provider" class="credential-button" :class="member.ai_provider_credentials?.[provider.credential_provider] ? 'configured' : 'missing'" @click="openMemberCredentialDialog(member, provider)">{{provider.credential_display_name}} 密钥 · {{member.ai_provider_credentials?.[provider.credential_provider] ? '已配置' : '待配置'}}</button></span></div><p v-if="!members.length && !memberListRefreshing" class="empty">暂无公司成员。</p><div v-if="memberListRefreshing" class="list-refresh-overlay" role="status"><i></i><span>正在刷新列表…</span></div></section>
      </section>
      <section v-else-if="page==='shops'" class="page">
        <div class="section-heading"><div><span>环境同步和模版上品策略配置在员工电脑的本地执行器工作页完成；这里查看自动上品记录。</span></div></div>
        <p v-if="shopError && user?.role==='company_admin'" class="error">{{shopError}}</p>
        <div v-if="user?.role==='company_admin'" class="shop-actions"><span class="miaoshou-status" :class="company?.hubstudio_configured?'configured':'missing'">{{company?.hubstudio_configured?'HubStudio API 已配置':'请配置 HubStudio API'}}</span><button class="secondary" @click="openHubstudioDialog">{{company?.hubstudio_configured?'更新':'配置'}} HubStudio API</button></div>
        <p>启动新版执行器，在本机工作页同步环境，并配置产品模版对应的允许环境及轮流或随机分配方式。随后在商品草稿导出窗口生成自动上品任务。“已提交”表示上传提交完成，不代表平台审核通过。</p>
        <div class="section-heading"><h2>自动上品记录</h2><div class="section-heading-actions"><button class="ghost" :disabled="hubUploadLoading" @click="loadHubUploadTasks">{{hubUploadLoading?'刷新中…':'↻ 刷新'}}</button></div></div>
        <div class="hub-upload-filters"><label>模版 <select v-model="hubUploadTemplateId" :disabled="hubUploadLoading" @change="changeHubUploadCreator"><option :value="null">全部模版</option><option v-for="template in hubUploadTemplates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><label v-if="user?.role==='company_admin'">创建人 <select v-model="hubUploadCreatorId" :disabled="hubUploadLoading" @change="changeHubUploadCreator"><option :value="null">全部成员</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div>
        <p v-if="hubUploadError" class="error" role="alert">{{hubUploadError}}</p>
        <section class="draft-table refreshable-list hub-upload-table" :aria-busy="hubUploadLoading">
          <div class="thead hub-upload-grid"><span>ID</span><span>模版</span><span>商品数量</span><span>创建人</span><span>创建时间</span><span>环境</span><span>状态</span></div>
          <div v-for="task in hubUploadTasks" :key="task.id" class="trow hub-upload-grid"><span>#{{task.id}}</span><span>{{task.template_name || '模版未知'}}</span><span>{{task.product_count}}</span><span>{{task.created_by_name || `账号 #${task.created_by}`}}</span><span>{{task.created_at ? new Date(task.created_at).toLocaleString() : '—'}}</span><span :title="hubUploadEnvironment(task)">{{hubUploadEnvironment(task)}}</span><span class="chip" :class="['completed','running'].includes(task.status)?'blue':'orange'">{{task.stage === 'imported' ? '导入成功' : hubUploadStatusLabels[task.status] || task.status}}</span></div>
          <p v-if="!hubUploadTasks.length && !hubUploadLoading && !hubUploadError" class="empty">暂无自动上品记录。</p>
          <footer class="draft-pagination"><span>共 {{hubUploadTotal}} 条</span><label>每页 <select v-model.number="hubUploadPageSize" :disabled="hubUploadLoading" @change="changeHubUploadPageSize"><option v-for="size in hubUploadPageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="hubUploadLoading || !!hubUploadError || hubUploadPage===1" @click="changeHubUploadPage(hubUploadPage-1)">上一页</button><span>第 {{hubUploadPage}} / {{hubUploadPageCount}} 页</span><button :disabled="hubUploadLoading || !!hubUploadError || hubUploadPage>=hubUploadPageCount" @click="changeHubUploadPage(hubUploadPage+1)">下一页</button></footer>
          <div v-if="hubUploadLoading" class="list-refresh-overlay" role="status"><i></i><span>正在加载自动上品记录…</span></div>
        </section>
      </section>
      <section v-else-if="page==='tiktok-catalogs' && user?.role==='company_admin'" class="page">
        <div class="section-heading"><div><span>按平台与店铺类型管理批量上传模板；上传文件会由对应解析器验证。</span></div><div class="section-heading-actions"><button class="ghost" :disabled="tiktokCatalogListRefreshing" @click="refreshTiktokCatalogList">{{tiktokCatalogListRefreshing ? '刷新中…' : '↻ 刷新'}}</button><button class="primary" @click="openTiktokCatalogCreateDialog">新增类目</button></div></div>
        <div class="catalog-type-tabs"><button :class="{active:tiktokCatalogTypeTab==='tiktok_local'}" @click="tiktokCatalogTypeTab='tiktok_local'">tk本土店</button><button :class="{active:tiktokCatalogTypeTab==='tiktok_cross_border'}" @click="tiktokCatalogTypeTab='tiktok_cross_border'">tk跨境店</button><button :class="{active:tiktokCatalogTypeTab==='shopee_basic'}" @click="tiktokCatalogTypeTab='shopee_basic'">Shopee</button></div>
        <p v-if="tiktokCatalogError" class="error">{{tiktokCatalogError}}</p>
        <div class="draft-table refreshable-list" :aria-busy="tiktokCatalogListRefreshing"><div class="thead tiktok-catalog-grid"><span>类目库名称</span><span>店铺类型</span><span>模板版本</span><span>来源文件</span><span>类目数</span><span>更新时间</span><span>操作</span></div><div v-for="catalog in activeTiktokCatalogs" :key="catalog.id" class="trow tiktok-catalog-grid"><span><b>{{catalog.name}}</b></span><span>{{tiktokCatalogTypeLabel(catalog.template_type)}}</span><span>{{catalog.template_version || '—'}}</span><span>{{catalog.source_filename}}</span><span>{{catalog.category_count}}</span><span>{{new Date(catalog.updated_at).toLocaleString()}}</span><span class="tiktok-catalog-actions"><button v-if="catalog.template_type!=='shopee_basic'" @click="openTiktokCatalogDetail(catalog)">属性设置</button><button class="negative" :disabled="tiktokCatalogLoading" @click="deleteTiktokCatalog(catalog)">删除</button></span></div><p v-if="!activeTiktokCatalogs.length && !tiktokCatalogListRefreshing" class="empty">暂无{{tiktokCatalogTypeLabel(tiktokCatalogTypeTab)}}类目库，请先点击“新增类目”导入平台模板。</p><div v-if="tiktokCatalogListRefreshing" class="list-refresh-overlay" role="status"><i></i><span>正在刷新列表…</span></div></div>
      </section>
    </section>
  </main>
  <div v-if="materialSettingKind" class="modal-backdrop" @click.self="closeMaterialSetting">
    <section v-dialog-focus="{close:closeMaterialSetting,busy:materialSettingSaving}" class="modal-card material-setting-dialog" role="dialog" aria-modal="true" aria-labelledby="material-setting-title">
      <button type="button" class="modal-close" :disabled="materialSettingSaving" aria-label="关闭批量设置弹窗" @click="closeMaterialSetting">×</button>
      <h2 id="material-setting-title">{{materialSettingTitle}}</h2>
      <p>将为已选的 {{materialSettingAssetIds.length}} 张素材{{materialSettingTitle}}。</p>
      <form @submit.prevent="confirmMaterialSetting">
        <label v-if="materialSettingKind==='infringement'">侵权状态<select v-model="materialInfringementTarget" aria-label="侵权状态" :disabled="materialSettingSaving" @change="materialSettingError=''"><option :value="null" disabled>请选择侵权状态</option><option :value="true">侵权</option><option :value="false">不侵权</option></select></label>
        <template v-else>
          <label>风格<select v-model="materialStyleTargetId" aria-label="风格" :disabled="materialSettingSaving || materialStylesLoading" @change="materialSettingError=''"><option v-for="option in materialSettingStyleOptions" :key="option.value ?? 'ungrouped'" :value="option.value">{{option.label}}</option></select></label>
          <p v-if="!materialSettingTemplateId" class="material-setting-hint">所选素材跨模板，仅支持设为未分组。</p>
        </template>
        <p v-if="materialSettingError" class="error modal-error" role="alert">{{materialSettingError}}</p>
        <div class="modal-actions"><button type="button" class="ghost" :disabled="materialSettingSaving" @click="closeMaterialSetting">取消</button><button type="submit" class="primary" :disabled="materialSettingSaving || (materialSettingKind==='infringement' ? materialInfringementTarget===null : materialStylesLoading)">{{materialSettingSaving ? '保存中…' : '确认保存'}}</button></div>
      </form>
    </section>
  </div>
  <div v-if="materialCollectionDetail" class="modal-backdrop" @click.self="materialCollectionDetail=null"><section v-dialog-focus="{close:()=>{materialCollectionDetail=null}}" class="modal-card" role="dialog" aria-modal="true" aria-labelledby="collection-detail-title"><h2 id="collection-detail-title">素材采集来源</h2><p>来源公司：{{materialCollectionDetail.collection_source.source_company_name}}</p><p>来源库：{{materialCollectionDetail.collection_source.source_library==='material'?'素材库':'产品库'}}</p><p>原 SKU：{{materialCollectionDetail.collection_source.source_sku || '无 SKU'}}</p><p>采集时间：{{new Date(materialCollectionDetail.collection_source.collected_at).toLocaleString()}}</p><p>本公司 SKU：{{materialCollectionDetail.sku}}</p></section></div>
  <div v-if="showMaterialImportDialog" class="modal-backdrop" @click.self="!materialImportSaving && (showMaterialImportDialog=false)"><section class="modal-card material-draft-dialog claim-materials-dialog material-import-dialog" @scroll.capture="materialHoverPreview=null" role="dialog" aria-modal="true" aria-labelledby="material-import-title"><button class="modal-close" :disabled="materialImportSaving" aria-label="关闭导入弹窗" @click="showMaterialImportDialog=false">×</button><h2 id="material-import-title">导入素材</h2><p>新链接默认选中；勾选已存在的链接表示仍创建新素材和新 SKU，图片共用已保存文件。</p><label>产品模板<select v-model="materialImportTemplateId" :disabled="materialImportSaving" @change="materialImportError=''"><option :value="null">请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label><div class="material-import-toolbar"><button class="secondary" :disabled="materialImportSaving" @click="materialImportItems.forEach(item => item.selected=true)">全选</button><button class="secondary" :disabled="materialImportSaving" @click="materialImportItems.forEach(item => item.selected=false)">取消全选</button><InfringementActions :disabled="!materialImportSelectedCount || materialImportSaving" @set="setImportInfringement"/></div><div class="material-style-actions"><StyleSelect v-model="importStyleTargetId" :styles="materialStyles" :template-id="materialImportTemplateId" :disabled="materialImportSaving || materialStylesLoading"/><button type="button" class="secondary" :disabled="!materialImportSelectedCount || !materialImportTemplateId || materialStylesLoading || materialImportSaving" @click="applySelectedStyle(materialImportItems,importStyleTargetId)">应用到选中图片</button></div><strong class="material-import-count">共 {{materialImportItems.length}} 张 · 已选 {{materialImportSelectedCount}} 张</strong><div class="material-pending-head" aria-hidden="true"><span></span><span>图片</span><span>图片链接</span><span>风格</span><span>侵权状态</span></div><ul class="material-pending-list" aria-label="待导入图片">
    <li v-for="item in materialImportItems" :key="item.url" class="material-pending-row" :class="{selected:item.selected}">
      <input v-model="item.selected" type="checkbox" :disabled="materialImportSaving" :aria-label="`选择图片 ${item.url}`"/>
      <img v-if="!item.failed" :src="item.url" alt="待导入图片" loading="lazy" class="material-pending-thumbnail" tabindex="0" @pointerenter="showMaterialHoverPreview($event,item.url,'待导入图片')" @pointerleave="materialHoverPreview=null" @focus="showMaterialHoverPreview($event,item.url,'待导入图片')" @blur="materialHoverPreview=null" @error="item.failed=true;materialHoverPreview=null"/>
      <span v-else class="material-pending-image-error">图片预览失败<br/>仍可导入此链接</span>
      <div class="material-pending-info"><b>{{item.exists ? '已存在 · 勾选仍创建新 SKU' : '新素材'}}</b><small :title="item.url">{{item.url}}</small></div><span class="material-style-badge material-pending-style" :class="{ungrouped:!item.style_id}" :title="materialStyleLabels.get(item.style_id ?? 0) || '未分组'">{{materialStyleLabels.get(item.style_id ?? 0) || '未分组'}}</span>
      <InfringementToggle v-model="item.is_infringing" :disabled="materialImportSaving"/>
    </li>
  </ul><p v-if="materialImportError" class="error material-draft-error" role="alert">{{materialImportError}}</p><div class="modal-actions"><button class="ghost" :disabled="materialImportSaving" @click="showMaterialImportDialog=false">取消</button><button class="primary" :disabled="materialImportSaving" @click="confirmMaterialImport">{{materialImportSaving ? '导入中…' : `确认导入（${materialImportSelectedCount}）`}}</button></div></section></div>
  <div v-if="showBatchClaimDialog" class="modal-backdrop" @click.self="!batchClaiming && (showBatchClaimDialog=false)">
    <section class="modal-card batch-claim-dialog" @scroll="batchClaimHoverPreview=null">
      <button class="modal-close" :disabled="batchClaiming" @click="showBatchClaimDialog=false">×</button>
      <h2>批量审核</h2>
      <p>审核任务与图片；选中的图片表示采用，否则废弃。</p>
      <div v-if="batchClaimLoading" class="empty">正在加载任务结果…</div>
      <template v-else>
        <button type="button" class="ghost batch-claim-select-all" :disabled="batchClaiming || !batchClaimItems.length" @click="toggleAllBatchClaimImages">{{allBatchClaimImagesSelected ? '全部取消' : '全选'}}</button>
        <InfringementActions :disabled="!selectedBatchClaimImages.size || batchClaiming" @set="setBatchClaimInfringement"/><div class="batch-claim-table">
          <table aria-label="AI 图片批量审核">
            <colgroup><col class="batch-claim-task-column"/><col/><col class="batch-claim-infringement-column"/></colgroup>
            <thead><tr><th scope="col">任务</th><th scope="col">图</th><th scope="col">是否侵权</th></tr></thead>
            <tbody v-for="group in groupedBatchClaimItems" :key="group.taskId">
              <tr v-for="(url,index) in group.urls" :key="url" class="batch-claim-row">
                <th v-if="index===0" scope="rowgroup" :rowspan="group.urls.length">{{group.taskLabel}}</th>
                <td><button type="button" class="batch-claim-image" :class="{selected:selectedBatchClaimImages.has(batchClaimImageKey(group.taskId,url))}" :disabled="batchClaiming" :aria-pressed="selectedBatchClaimImages.has(batchClaimImageKey(group.taskId,url))" :aria-label="`采用${group.taskLabel}结果图 ${index+1}`" @click="toggleBatchClaimImage(group.taskId,url)" @pointerenter="showBatchClaimHoverPreview($event,url,`${group.taskLabel} 结果图 ${index+1}`)" @pointerleave="batchClaimHoverPreview=null" @focus="showBatchClaimHoverPreview($event,url,`${group.taskLabel} 结果图 ${index+1}`)" @blur="batchClaimHoverPreview=null">
                  <img :src="imageUrl(url)" :alt="`${group.taskLabel} 结果图 ${index+1}`"/>
                </button></td>
                <td><InfringementToggle :model-value="!!batchClaimInfringement[batchClaimImageKey(group.taskId,url)]" :disabled="batchClaiming" @update:model-value="batchClaimInfringement[batchClaimImageKey(group.taskId,url)]=$event"/></td>
              </tr>
            </tbody>
          </table>
          <p v-if="!groupedBatchClaimItems.length" class="empty">没有待审核任务。</p>
        </div>
      </template>
      <div v-if="batchClaiming || batchClaimCompleted" class="batch-claim-progress"><span>审核进度 {{batchClaimCompleted}} / {{batchClaimTotal}}<b v-if="batchClaimFailed"> · 失败 {{batchClaimFailed}}</b></span><progress :max="batchClaimTotal || 1" :value="batchClaimCompleted"></progress><small>正在处理审核结果，请勿关闭窗口。</small></div>
      <div class="modal-actions"><button class="ghost" :disabled="batchClaiming" @click="showBatchClaimDialog=false">取消</button><button class="primary" :disabled="batchClaimLoading || batchClaiming || !groupedBatchClaimItems.length" @click="confirmBatchClaim">{{batchClaiming ? `审核中 ${batchClaimCompleted}/${batchClaimTotal}` : '确认'}}</button></div>
    </section>
  </div>
  <Teleport to="body">
    <div v-if="showBatchClaimDialog && batchClaimHoverPreview" class="batch-claim-hover-preview" :style="{left:`${batchClaimHoverPreview.left}px`,top:`${batchClaimHoverPreview.top}px`,width:`${batchClaimHoverPreview.width}px`,height:`${batchClaimHoverPreview.height}px`}">
      <img :src="batchClaimHoverPreview.url" :alt="batchClaimHoverPreview.alt"/>
    </div>
  </Teleport>
  <div v-if="showMiaoshouPublishDialog" class="modal-backdrop" @click.self="!miaoshouPublishing && (showMiaoshouPublishDialog=false)"><section class="modal-card"><button class="modal-close" :disabled="miaoshouPublishing" @click="showMiaoshouPublishDialog=false">×</button><h2>{{miaoshouPublishDraftIds.length > 1 ? '批量发布至妙手' : '发布至妙手'}}</h2><p>将 {{miaoshouPublishDraftIds.length}} 条商品发布到妙手公共采集箱、认领至 TikTok 采集箱，并分配给下方店铺。</p><label>分配店铺 <b class="required">*</b><select v-model="miaoshouPublishShopId" :disabled="miaoshouPublishing"><option :value="null" disabled>请选择店铺</option><option v-for="shop in miaoshouAssignableShops" :key="shop.id" :value="shop.id">{{shop.name}}（#{{shop.external_shop_id}}）</option></select><small>仅显示您有管理权限的妙手同步店铺。</small></label><div v-if="miaoshouPublishing || miaoshouPublishCompleted" class="batch-claim-progress"><span>发布进度 {{miaoshouPublishCompleted}} / {{miaoshouPublishDraftIds.length}}<b v-if="miaoshouPublishFailed"> · 失败 {{miaoshouPublishFailed}}</b></span><progress :max="miaoshouPublishDraftIds.length || 1" :value="miaoshouPublishCompleted"></progress></div><div class="modal-actions"><button class="ghost" :disabled="miaoshouPublishing" @click="showMiaoshouPublishDialog=false">取消</button><button class="primary" :disabled="miaoshouPublishing || !miaoshouPublishShopId" @click="confirmMiaoshouPublish">{{miaoshouPublishing ? `发布中 ${miaoshouPublishCompleted}/${miaoshouPublishDraftIds.length}` : miaoshouPublishFailed ? '重试发布' : '确认并发布'}}</button></div></section></div>
  <div v-if="showTaskDetailDialog && viewingTask?.task_type==='sku_image'" class="modal-backdrop" @click.self="showTaskDetailDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showTaskDetailDialog=false">×</button><h2>任务详情 #{{viewingTask?.id}}</h2><p>{{viewingTask?.parameters?.task_type || 'SKU图'}} · {{viewingTask?.template_name || '历史模板已删除'}}</p><section class="draft-edit-section"><strong>印花图</strong><div class="material-draft-preview-images"><button v-for="url in viewingTask?.parameters?.print_urls || []" :key="url" @click="openImagePreview(url, '印花图')"><img :src="imageUrl(url)" alt="印花图"/></button><p v-if="!(viewingTask?.parameters?.print_urls?.length)">未保留印花图。</p></div></section><section v-if="viewingTask?.parameters?.white_image_url" class="draft-edit-section"><strong>产品白底图</strong><button class="task-material-thumbnail" @click="openImagePreview(viewingTask.parameters.white_image_url, viewingTask.parameters.white_image_name || '产品白底图')"><img :src="imageUrl(viewingTask.parameters.white_image_url)" :alt="viewingTask.parameters.white_image_name || '产品白底图'"/></button></section><section class="draft-edit-section"><strong>创作参数</strong><p>画面比例：{{viewingTask?.parameters?.ratio || '—'}} · 清晰度：{{viewingTask?.parameters?.quality || '—'}}</p><p>创作要求：{{viewingTask?.parameters?.private_creative_configuration ? '个人创作配置已隐藏' : viewingTask?.parameters?.creative_requirement || '未填写'}}</p></section><section class="draft-edit-section"><strong>任务信息</strong><p>模型：{{viewingTask?.provider === 'grsai' ? 'Grsai' : viewingTask?.provider || '默认模型'}} <span v-if="viewingTask?.provider_model">· {{viewingTask.provider_model}}</span></p><p>状态：<span class="chip" :class="taskStatusClass(viewingTask?.status)">{{taskStatusLabel[viewingTask?.status] || viewingTask?.status || '—'}}</span> · {{viewingTask?.parameters?.print_urls?.length || 0}} 张印花 · 已提交 {{viewingTask?.submit_attempts || 0}} 次</p><p>外部任务 ID：<code>{{viewingTask?.provider_task_id || '—'}}</code></p><p v-if="viewingTask?.failure_reason" :class="{error:viewingTask?.status==='failed'}">处理信息：{{viewingTask.failure_reason}}</p></section><section v-if="viewingTask?.result_map?.length" class="draft-edit-section"><strong>结果映射</strong><div class="task-result-map"><article v-for="item in viewingTask.result_map" :key="item.print_url"><button class="task-material-thumbnail" @click="openImagePreview(item.print_url, '印花图')"><img :src="imageUrl(item.print_url)" alt="印花图"/></button><small>{{item.result_urls?.length || 0}} 张生成结果</small><div class="material-draft-preview-images"><button v-for="url in item.result_urls || []" :key="url" @click="openImagePreview(url, '生成结果')"><img :src="imageUrl(url)" alt="生成结果"/></button></div></article></div></section><div class="modal-actions"><button class="primary" @click="showTaskDetailDialog=false">关闭</button></div></section></div>
  <div v-if="showCreativeAssetsDialog" class="modal-backdrop" @click.self="showCreativeAssetsDialog=false"><section class="modal-card asset-dialog"><button class="modal-close" @click="showCreativeAssetsDialog=false">×</button><h2>印花图素材</h2><div class="asset-summary"><span>共 {{creativeAssets.length}} 项，已直传 {{creativeAssets.filter(asset=>asset.uploadedUrl).length}} 项</span><label class="add-assets">＋ 继续上传<input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="onCreativeAssetChange"/></label></div><div class="asset-dialog-heading"><div><h3>印花图</h3><span>{{creativeAssets.length}} / 500</span></div><button @click="clearCreativeAssets">清空</button></div><p class="asset-status">最多 500 张，直传中断后再次提交会继续未完成项。</p><div class="asset-list"><article v-for="asset in creativeAssets" :key="asset.id" class="asset-row"><img :src="asset.preview" :alt="asset.file.name"/><div><strong>{{asset.file.name}}</strong><p><span>{{asset.uploadedUrl ? '已直传' : '待上传'}}</span>{{(asset.file.size / 1024).toFixed(1)}}KB</p></div><button class="asset-delete" title="删除" @click="removeCreativeAsset(asset.id)">×</button></article><p v-if="!creativeAssets.length" class="asset-empty">暂未上传印花图。</p></div></section></div>
  <div v-if="resourceEditorType" v-dialog-focus="{close:closeResourceEditor,busy:personalResourceSaving}" class="modal-backdrop" @click.self="closeResourceEditor">
    <section class="modal-card creative-resource-dialog" role="dialog" aria-modal="true" aria-labelledby="creative-resource-editor-title">
      <button type="button" class="modal-close" aria-label="关闭资源编辑" :disabled="personalResourceSaving" @click="closeResourceEditor">×</button>
      <h2 id="creative-resource-editor-title">{{resourceEditorTitle}}</h2>
      <form @submit.prevent="saveResourceEditor">
        <fieldset :disabled="personalResourceSaving">
          <label v-if="user?.role==='company_admin' && !editingWhiteImage && !editingPersonalPrompt">所属成员 <b>*</b><select v-model="resourceEditorUserId"><option v-for="owner in resourceOwners" :key="owner.id" :value="owner.id">{{owner.name}}</option></select></label>
          <template v-if="resourceEditorType==='white-images'">
            <label>产品模板 <b>*</b><select v-model="whiteImageForm.template_id" :disabled="Boolean(editingWhiteImage)"><option :value="null" disabled>请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label>
            <label>名称 <b>*</b><input v-model="whiteImageForm.name" maxlength="80" placeholder="例如：正面白底图"/></label>
            <label v-if="!editingWhiteImage">图片 <b>*</b><input type="file" accept="image/png,image/jpeg,image/webp" @change="onWhiteImageFileChange"/><small>JPG、PNG、WebP，最大 3MB</small></label>
            <div v-else class="resource-readonly-image"><span>图片（仅预览）</span><img class="resource-image-preview" :src="imageUrl(editingWhiteImage.image_url)" :alt="editingWhiteImage.name"/><small>编辑时仅支持修改名称，风格名称同步更新。</small></div>
          </template>
          <template v-else>
            <label>产品模板 <b>*</b><select v-model="personalPromptForm.template_id" :disabled="Boolean(editingPersonalPrompt)"><option :value="null" disabled>请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label>
            <label>名称 <b>*</b><input v-model="personalPromptForm.name" maxlength="80" placeholder="例如：自然布料贴合"/></label>
            <label>创作要求 <b>*</b><textarea v-model="personalPromptForm.content" maxlength="1000" rows="6" placeholder="描述印花贴合方式、细节和光影"></textarea></label>
          </template>
          <p v-if="resourceEditorError" class="error" role="alert">{{resourceEditorError}}</p>
          <div class="modal-actions"><button type="button" class="ghost" @click="closeResourceEditor">取消</button><button type="submit" class="primary">{{personalResourceSaving ? '保存中…' : '保存'}}</button></div>
        </fieldset>
      </form>
    </section>
  </div>
  <div v-if="showBatchMainImageDialog" class="modal-backdrop" @click.self="!batchMainImageSaving && (showBatchMainImageDialog=false)">
    <section class="modal-card batch-carousel-dialog">
      <button class="modal-close" :disabled="batchMainImageSaving" @click="showBatchMainImageDialog=false">×</button>
      <h2>批量制作主图</h2>
      <p>已选择 {{selectedDrafts.length}} 条草稿；随机参考最多 3 张，手动选择每条最多 9 张。</p>
      <div class="reference-mode-tabs" role="tablist">
        <button type="button" role="tab" :class="{active:batchMainImageReferenceMode==='random_carousel'}" :aria-selected="batchMainImageReferenceMode==='random_carousel'" @click="batchMainImageReferenceMode='random_carousel'"><i class="reference-mode-icon">🎲</i><b>随机选择最多 3 张轮播图</b><small>无轮播图的草稿自动使用 SKU 图</small></button>
        <button type="button" role="tab" :class="{active:batchMainImageReferenceMode==='random_sku'}" :aria-selected="batchMainImageReferenceMode==='random_sku'" @click="batchMainImageReferenceMode='random_sku'"><i class="reference-mode-icon">🎲</i><b>随机选择最多 3 张 SKU 图</b><small>从每条草稿的原始 SKU 图中随机挑选</small></button>
        <button type="button" role="tab" :class="{active:batchMainImageReferenceMode==='manual'}" :aria-selected="batchMainImageReferenceMode==='manual'" @click="batchMainImageReferenceMode='manual'"><i class="reference-mode-icon">👆</i><b>手动选择参考图</b><small>轮播图和 SKU 图可混选，每条最多 9 张</small></button>
      </div>
      <section class="batch-carousel-list">
        <article v-for="draft in selectedDrafts" :key="draft.id" class="batch-carousel-draft">
          <header><b>#{{draft.id}}</b><span :title="draft.title">{{draft.title}}</span><small>{{batchMainImageReferenceMode==='manual' ? `${(batchMainImageSelections[draft.id] || []).length} / 9 已选` : `${Math.min(3,batchMainImageReferenceItems(draft).length)} 张随机参考图`}}</small></header>
          <template v-if="batchMainImageReferenceMode==='manual'">
            <div class="main-reference-row"><strong>轮播图</strong><div class="batch-carousel-skus"><button v-for="item in mainCarouselItems(draft)" :key="item.image_url" type="button" :disabled="(batchMainImageSelections[draft.id] || []).length>=9 && !(batchMainImageSelections[draft.id] || []).includes(item.image_url)" :class="{selected:(batchMainImageSelections[draft.id] || []).includes(item.image_url)}" @click="toggleBatchMainImageReference(draft.id,item.image_url)"><img :src="imageUrl(item.image_url)" :alt="item.sku || '轮播图'"/><i>{{item.sku || '轮播图'}}</i></button><p v-if="!mainCarouselItems(draft).length" class="empty">暂无轮播图</p></div></div>
            <div class="main-reference-row"><strong>SKU 图</strong><div class="batch-carousel-skus"><button v-for="item in mainSkuItems(draft)" :key="item.image_url" type="button" :disabled="(batchMainImageSelections[draft.id] || []).length>=9 && !(batchMainImageSelections[draft.id] || []).includes(item.image_url)" :class="{selected:(batchMainImageSelections[draft.id] || []).includes(item.image_url)}" @click="toggleBatchMainImageReference(draft.id,item.image_url)"><img :src="imageUrl(item.image_url)" :alt="item.sku || 'SKU 图'"/><i>{{item.sku || 'SKU 图'}}</i></button><p v-if="!mainSkuItems(draft).length" class="empty">暂无 SKU 图</p></div></div>
          </template>
          <div v-else class="main-reference-row"><strong>{{batchMainImageEffectiveMode(draft)==='random_sku' ? 'SKU 图' : '轮播图'}}</strong><small v-if="batchMainImageReferenceMode==='random_carousel' && batchMainImageEffectiveMode(draft)==='random_sku'">无轮播图，已自动切换到随机 SKU 图</small><div class="batch-carousel-skus"><button v-for="item in batchMainImageReferenceItems(draft)" :key="item.image_url" type="button" disabled><img :src="imageUrl(item.image_url)" :alt="item.sku || '参考图'"/><i>{{item.sku || '参考图'}}</i></button><p v-if="!batchMainImageReferenceItems(draft).length" class="empty">暂无可用参考图</p></div></div>
        </article>
      </section>
      <section class="batch-carousel-params"><label>创作要求<textarea v-model="batchMainImageParams.prompt" rows="2" maxlength="1000" placeholder="请输入首图创作要求"/></label><div><label>AI 模型<select v-model="batchMainImageParams.provider"><option v-for="provider in availableAiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}</option></select></label><label>比例<select v-model="batchMainImageParams.ratio"><option>1:1</option><option>3:4</option></select></label><label>清晰度<select v-model="batchMainImageParams.quality"><option>1K</option><option>2K</option></select></label></div></section>
      <div class="modal-actions"><button class="ghost" :disabled="batchMainImageSaving" @click="showBatchMainImageDialog=false">取消</button><button class="primary" :disabled="batchMainImageSaving" @click="createBatchMainImageTasks">{{batchMainImageSaving?'创建中…':'开始创作主图'}}</button></div>
    </section>
  </div>
  <div v-if="showBatchImageReviewDialog" class="modal-backdrop" @click.self="!batchImageReviewSaving && (showBatchImageReviewDialog=false)"><section class="modal-card batch-image-review-dialog"><button class="modal-close" :disabled="batchImageReviewSaving" @click="showBatchImageReviewDialog=false">×</button><h2>批量审核{{batchImageReviewType==='carousel' ? '轮播图' : '首图'}}</h2><p>每条草稿至少选择一张候选图即可确认并进入下一阶段。</p><div v-if="batchImageReviewLoading" class="empty">正在加载候选图…</div><template v-else><div class="batch-review-toolbar"><strong>已选 {{batchReviewChosenTasks()}} / {{batchReviewTotalTasks()}} 个任务</strong><button class="secondary" @click="selectAllBatchReviewTasks()">{{batchImageReviewType==='carousel' ? '所有任务选全部' : '所有任务选首张'}}</button></div><section class="batch-review-list"><article v-for="draft in batchImageReviewDrafts" :key="draft.id" class="batch-review-draft"><header><div><b>#{{draft.id}}</b><span :title="draft.title">{{draft.title}}</span><small>{{batchReviewSelectedCount(draft)}} / {{batchReviewTasks(draft).length}} 已选</small></div><span><button class="ghost" @click="selectAllBatchReviewTasks(draft)">{{batchImageReviewType==='carousel' ? '本草稿选全部' : '本草稿选首张'}}</button><button class="ghost" @click="clearBatchReviewDraft(draft)">清除</button></span></header><div v-for="task in batchReviewTasks(draft)" :key="task.id" class="batch-review-task"><strong>{{batchImageReviewType==='carousel' ? `SKU：${task.parameters?.source_sku || '—'}` : `首图任务 #${task.id}`}}</strong><div><button v-for="url in task.result_urls" :key="url" type="button" :class="{selected:(batchImageReviewSelections[task.id] || []).includes(url)}" @click="toggleBatchReviewResult(task,url)"><img :src="imageUrl(url)" alt="候选图"/><i v-if="(batchImageReviewSelections[task.id] || []).includes(url)">✓</i></button></div></div><p v-if="!batchReviewTasks(draft).length" class="empty">该草稿暂无可审核的候选图。</p></article></section><div class="batch-review-footer"><div v-if="batchImageReviewType==='carousel'" class="carousel-confirm-next-step"><small>已选择图片的草稿下一步</small><label><input v-model="batchCarouselReviewNextStage" type="radio" value="main_image_pending"/>进入首图创作</label><label><input v-model="batchCarouselReviewNextStage" type="radio" value="ready_to_publish"/>直接到待发布</label></div><small v-else>已选择图片的草稿将进入待发布。</small><div class="modal-actions"><button class="ghost" :disabled="batchImageReviewSaving" @click="showBatchImageReviewDialog=false">取消</button><button class="primary" :disabled="batchImageReviewSaving" @click="confirmBatchImageReview">{{batchImageReviewSaving?'确认中…':`确认审核 ${batchReviewChosenTasks()} 个任务`}}</button></div></div></template></section></div>
  <div v-if="showMyAccountDialog" class="modal-backdrop" @click.self="showMyAccountDialog=false"><section class="modal-card"><h2>账号设置</h2><p>可修改当前管理员名称和用户代码；用户代码留空可清除，且在本公司内不可重复。</p><label>管理员名称<input v-model="myName" maxlength="80" placeholder="请输入管理员名称" /></label><label>用户代码 <small>（两个字符）</small><input v-model="myUserCode" maxlength="2" placeholder="例如：CN" /></label><div class="modal-actions"><button class="ghost" @click="showMyAccountDialog=false">取消</button><button class="primary" :disabled="myAccountSaving" @click="saveMyUserCode">{{myAccountSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showMaterialDraftDialog" class="modal-backdrop" @click.self="showMaterialDraftDialog=false">
    <section class="modal-card material-draft-dialog">
      <button class="modal-close" @click="showMaterialDraftDialog=false">×</button>
      <h2>创建商品草稿</h2>
      <p>将使用已选的 {{materialDraftAssets.length}} 张素材创建商品草稿。</p>
      <label>产品模板<input :value="materialDraftTemplate?.name || '—'" readonly/></label>
      <section class="material-draft-preview">
        <div class="material-draft-preview-heading"><strong>图片预览</strong><span>{{materialDraftAssets.length}} 张</span></div>
        <p v-if="materialDraftAssets.length > 1" class="material-draft-sort-hint">拖动图片调整顺序，首张图片将用于 AI 生成标题。</p>
        <div class="material-draft-preview-images">
          <button type="button" v-for="(asset, index) in materialDraftAssets" :key="asset.id" class="material-draft-sort-item material-batch-sort-item" :class="{dragging: draggedMaterialDraftAssetId === asset.id}" draggable="true" @dragstart="startMaterialDraftDrag($event, asset.id)" @dragover.prevent @drop.prevent="dropMaterialDraftAsset(asset.id)" @dragend="draggedMaterialDraftAssetId=null" :aria-label="`查看 ${asset.name || asset.sku} 大图`" @click="openImagePreview(asset.url, asset.name || asset.sku)">
            <img :src="imageUrl(asset.url)" :alt="asset.name || asset.sku" draggable="false"/>
            <span :class="{'is-first': index === 0}">{{index === 0 ? '首' : index + 1}}</span>
          </button>
        </div>
      </section>
      <section v-if="materialDraftTemplate" class="material-draft-details">
        <label>商品标题<input v-model="materialDraftTitle" @input="materialDraftTitleEdited=true" minlength="25" maxlength="255" placeholder="请输入 25-255 个字符，或使用 AI 生成"/><div class="material-draft-counter" :class="{invalid: materialDraftTitle.length > 0 && materialDraftTitle.length < 25}"><span>{{ materialDraftTitle.length }} / 255 字符</span></div></label>
        <div class="title-additional-requirements draft-title-generation-controls">
          <div class="draft-title-generation-actions"><button type="button" class="ghost" :aria-expanded="showDraftAdditionalRequirements" aria-controls="draft-title-additional-requirements" @click="showDraftAdditionalRequirements=!showDraftAdditionalRequirements">{{showDraftAdditionalRequirements ? '收起' : '展开'}}补充要求（选填）</button><div class="draft-title-generate-group"><button type="button" class="secondary" :disabled="materialDraftTitleGenerating" @click="generateMaterialDraftTitle">{{materialDraftTitleGenerating ? '生成中…' : 'AI 生成标题'}}</button><button type="button" class="draft-title-help-button" aria-label="标题生成说明" :aria-expanded="showDraftTitleHelp" aria-controls="draft-title-generation-help" @click="showDraftTitleHelp=!showDraftTitleHelp">ⓘ</button></div></div>
          <p v-if="showDraftTitleHelp" id="draft-title-generation-help" class="draft-title-generation-help">将使用此模版的 AI生成标题要求和首图生成英文标题；仅在要求明确指定时提及材质。</p>
          <label v-if="showDraftAdditionalRequirements" id="draft-title-additional-requirements">本次标题补充要求<textarea v-model="materialDraftAdditionalRequirements" maxlength="1000" placeholder="例如：重点突出蓝色花卉图案"/><small>仅作用于当前商品，不保存到模板；再次生成时保留，关闭后清空。</small></label>
        </div>
        <label>产品描述<textarea v-model="materialDraftProductDescription" maxlength="5000" placeholder="默认使用产品模版描述，可按商品修改"></textarea><div class="material-draft-counter"><span>{{ materialDraftProductDescription.length }} / 5000 字符</span></div></label>
      </section>
      <section v-if="materialDraftTemplate" class="material-draft-sku-summary"><strong>基础 SKU 列表</strong><p>{{libraryDraftMode ? '直接使用所选数据的基础 SKU；' : '直接使用素材入库时生成的永久 SKU；'}}发布妙手时会拼接模板尺码：{{materialDraftSizes.length ? materialDraftSizes.join('、') : '默认规格'}}。</p><b>共 {{materialDraftSkuCount}} 个基础 SKU</b><small v-if="!libraryDraftMode">格式：模板名称 + 用户代码 + 6 位随机字符串</small><div class="material-draft-sku-list"><div v-for="asset in materialDraftAssets" :key="asset.id"><span>图片 SKU</span><code>{{asset.sku}}</code></div></div><label class="material-draft-size-chart">尺码图<small>直接使用产品模版的尺码图；如需更换，请到产品模版中修改。</small><img v-if="materialDraftSizeChartPreview" :src="materialDraftSizeChartPreview" alt="尺码图预览"/><small v-else>该产品模版尚未上传尺码图</small></label></section>
      <div class="modal-actions"><button class="ghost" @click="showMaterialDraftDialog=false">取消</button><button class="primary" :disabled="materialDraftSaving" @click="createDraftFromMaterialAssets">{{materialDraftSaving ? '创建中…' : '确认创建'}}</button></div>
    </section>
  </div>
  <div v-if="showMaterialBatchDraftDialog" class="modal-backdrop" @click.self="!materialBatchControlsLocked && (showMaterialBatchDraftDialog=false)">
    <section class="modal-card material-batch-draft-dialog" role="dialog" aria-modal="true" aria-labelledby="material-batch-draft-title">
      <button class="modal-close" :disabled="materialBatchControlsLocked" aria-label="关闭组合创建弹窗" @click="showMaterialBatchDraftDialog=false">×</button>
      <h2 id="material-batch-draft-title">组合创建商品草稿</h2>
      <p>可复用已使用素材或数据；每个完整组合会创建一条草稿，产品描述固定采用模板描述。</p>
      <div class="material-batch-options">
        <label>每组图片<select v-model.number="materialBatchGroupSize" :disabled="materialBatchControlsLocked" @change="rebuildMaterialBatchGroups"><option :value="5">5 张</option><option :value="6">6 张</option><option :value="7">7 张</option><option :value="8">8 张</option></select></label>
        <label>组合方式<select v-model="materialBatchMode" :disabled="materialBatchControlsLocked" @change="rebuildMaterialBatchGroups"><option value="sequential">按列表顺序</option><option value="random">随机组合</option></select></label>
      </div>
      <p v-if="draftSelectionAssets.length % materialBatchGroupSize" class="material-batch-remainder">最后 {{draftSelectionAssets.length % materialBatchGroupSize}} 张不足一组，不参与创建，使用状态保持不变。</p>
      <section class="material-batch-title-toolbar" aria-label="批量生成标题">
        <div class="material-batch-title-actions">
          <button type="button" class="secondary" :disabled="materialBatchControlsLocked || !materialBatchGroups.length" @click="generateMaterialBatchTitles()">一键 AI 生成所有标题</button>
          <button v-if="materialBatchUnfinishedTitles.length" type="button" class="ghost" :disabled="materialBatchControlsLocked" @click="generateMaterialBatchTitles(materialBatchUnfinishedTitles)">重试未完成（{{materialBatchUnfinishedTitles.length}}）</button>
          <button v-if="materialBatchTitleProgress.running" type="button" class="ghost" @click="stopMaterialBatchTitleGeneration">停止生成</button>
        </div>
        <p class="material-batch-title-warning">将覆盖所有组合标题；使用各组首图、模板要求和本组补充要求。</p>
        <div v-if="materialBatchTitleProgress.total" class="material-batch-title-progress" role="status" aria-live="polite">
          <progress :value="materialBatchTitleProgress.completed" :max="materialBatchTitleProgress.total" aria-label="标题生成进度"></progress>
          <span>已完成 {{materialBatchTitleProgress.completed}} / {{materialBatchTitleProgress.total}}，成功 {{materialBatchTitleProgress.succeeded}}，失败 {{materialBatchTitleProgress.failed}}<template v-if="materialBatchTitleProgress.stopped">，已停止 {{materialBatchTitleProgress.stopped}}</template></span>
        </div>
        <p v-if="materialBatchTitleProgress.error" class="material-batch-title-error" role="alert">{{materialBatchTitleProgress.error}}</p>
      </section>
      <section class="material-batch-groups">
        <article v-for="(group,index) in materialBatchGroups" :key="group.id">
          <header><strong>草稿 {{index + 1}}</strong><div class="material-batch-group-meta"><span class="material-batch-title-status" :class="group.titleStatus">{{titleGenerationStatusLabels[group.titleStatus]}}</span><span>{{group.assets.length}} 张素材</span></div></header>
          <p class="material-batch-sort-hint">拖动图片调整本草稿顺序；点击图片查看大图。</p>
          <div class="material-draft-preview-images material-batch-preview-images">
            <button v-for="(asset, assetIndex) in group.assets" :key="asset.id" type="button" class="material-draft-sort-item material-batch-sort-item" :class="{dragging: draggedMaterialBatchAsset?.groupIndex === index && draggedMaterialBatchAsset?.assetId === asset.id}" :draggable="!materialBatchControlsLocked" :aria-label="'草稿 ' + (index + 1) + ' 第 ' + (assetIndex + 1) + ' 张图片：' + (asset.name || asset.sku) + (materialBatchControlsLocked ? '，点击查看大图' : '，点击查看大图或拖动调整顺序')" @dragstart="startMaterialBatchDrag($event, index, asset.id)" @dragover.prevent @drop.prevent="dropMaterialBatchAsset(index, asset.id)" @dragend="draggedMaterialBatchAsset=null" @click="openImagePreview(asset.url, (asset.name || asset.sku) + ' · 草稿 ' + (index + 1))">
              <img :src="imageUrl(asset.url)" :alt="asset.name || asset.sku" draggable="false"/>
              <span :class="{'is-first': assetIndex === 0}">{{assetIndex === 0 ? '首' : assetIndex + 1}}</span>
            </button>
          </div>
          <div class="material-draft-title-row"><input v-model="group.title" :disabled="materialBatchControlsLocked" :aria-label="'草稿 ' + (index + 1) + ' 商品标题'" @input="editMaterialBatchTitle(group)" minlength="25" maxlength="255" placeholder="请输入 25-255 个字符的商品标题"/></div>
          <small :class="{error:group.title.length>0 && group.title.trim().length<25}">{{group.title.length}} / 255 字符</small>
          <p v-if="group.titleError" class="material-batch-title-error" role="alert">{{group.titleError}}</p>
          <div class="title-additional-requirements draft-title-generation-controls">
            <div class="draft-title-generation-actions">
              <button type="button" class="ghost" :aria-expanded="group.showAdditionalRequirements" :aria-controls="'batch-title-additional-requirements-' + index" @click="group.showAdditionalRequirements=!group.showAdditionalRequirements">{{group.showAdditionalRequirements ? '收起' : '展开'}}补充要求（选填）</button>
              <div class="draft-title-generate-group"><button type="button" class="secondary" :disabled="materialBatchControlsLocked" @click="generateMaterialBatchTitle(group)">{{group.titleStatus === 'running' ? '生成中…' : 'AI 生成标题'}}</button><button type="button" class="draft-title-help-button" :aria-label="'草稿 ' + (index + 1) + ' 标题生成说明'" :aria-expanded="group.showTitleHelp" :aria-controls="'batch-title-generation-help-' + index" @click="group.showTitleHelp=!group.showTitleHelp">ⓘ</button></div>
            </div>
            <p v-if="group.showTitleHelp" :id="'batch-title-generation-help-' + index" class="draft-title-generation-help">将使用此模版的 AI生成标题要求和首图生成英文标题；仅在要求明确指定时提及材质。</p>
            <label v-if="group.showAdditionalRequirements" :id="'batch-title-additional-requirements-' + index">本草稿标题补充要求<textarea v-model="group.additionalRequirements" :disabled="materialBatchControlsLocked" maxlength="1000" placeholder="例如：重点突出蓝色花卉图案"/><small>仅作用于本草稿，不保存到模板；再次生成时保留，关闭弹窗或重新分组后清空。</small></label>
          </div>
        </article>
      </section>
      <div class="modal-actions"><button class="ghost" :disabled="materialBatchControlsLocked" @click="showMaterialBatchDraftDialog=false">取消</button><button class="primary" :disabled="materialBatchControlsLocked || !materialBatchTitlesValid" @click="createMaterialBatchDrafts">{{materialBatchSaving ? '创建中…' : '确认创建 ' + materialBatchGroups.length + ' 条草稿'}}</button></div>
    </section>
  </div>
  <div v-if="showBatchCarouselDialog" class="modal-backdrop" @click.self="!batchCarouselSaving && (showBatchCarouselDialog=false)"><section class="modal-card batch-carousel-dialog"><button class="modal-close" :disabled="batchCarouselSaving" @click="showBatchCarouselDialog=false">×</button><h2>批量制作轮播图</h2><p>已选择 {{selectedDrafts.length}} 条草稿；每个草稿至少保留一张 SKU 图。</p><section class="batch-carousel-list"><article v-for="draft in selectedDrafts" :key="draft.id" class="batch-carousel-draft"><header><b>#{{draft.id}}</b><span :title="draft.title">{{draft.title}}</span><small>{{(batchCarouselSelections[draft.id] || []).length}} / {{draft.sku_items?.length || 0}} 已选</small></header><div class="batch-carousel-skus"><button v-for="item in draft.sku_items || []" :key="item.sku" type="button" :class="{selected:(batchCarouselSelections[draft.id] || []).includes(item.sku)}" @click="toggleBatchCarouselSku(draft.id,item.sku)"><img :src="imageUrl(item.image_url)" :alt="item.sku"/><i>{{item.sku}}</i><span class="batch-carousel-hover"><img :src="imageUrl(item.image_url)" :alt="`${item.sku} 放大图`"/></span></button></div></article></section><section class="batch-carousel-params"><label>创作要求<textarea v-model="batchCarouselParams.prompt" rows="2" maxlength="1000" placeholder="请输入轮播图创作要求"/></label><div><label>AI 模型<select v-model="batchCarouselParams.provider"><option v-for="provider in availableAiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}</option></select></label><label>比例<select v-model="batchCarouselParams.ratio"><option>1:1</option><option>3:4</option></select></label><label>清晰度<select v-model="batchCarouselParams.quality"><option>1K</option><option>2K</option></select></label></div></section><div class="modal-actions"><button class="ghost" :disabled="batchCarouselSaving" @click="showBatchCarouselDialog=false">取消</button><button class="primary" :disabled="batchCarouselSaving" @click="createBatchCarouselTasks">{{batchCarouselSaving?'创建中…':'开始创作轮播图'}}</button></div></section></div>
  <div v-if="showTiktokExportDialog" class="modal-backdrop" @click.self="!tiktokExportLoading && (showTiktokExportDialog=false)"><section class="modal-card tiktok-export-dialog"><button class="modal-close" :disabled="tiktokExportLoading" @click="showTiktokExportDialog=false">×</button><h2>导出 TikTok 批量上传表格</h2><p>已选择 {{selectedDrafts.length}} 条同一产品模板的商品草稿。下列设置仅用于本次导出。</p><p v-if="tiktokExportIsLocal">自动上品任务由本地执行器领取，按本机模版策略选择一家允许环境；未匹配策略时等待配置。</p><div v-if="tiktokExportLoading && !tiktokExportOptions" class="empty">正在读取 TikTok 模板选项…</div><template v-else><section class="tiktok-export-grid"><label>类目库 / 店铺类型 <b class="required">*</b><select v-model="tiktokExportCatalogId" @change="changeTiktokExportCatalog"><option :value="null" disabled>请选择类目库</option><option v-for="catalog in tiktokExportCatalogs" :key="catalog.id" :value="catalog.id">{{catalog.name}}（{{tiktokCatalogTypeLabel(catalog.template_type)}}）</option></select></label><div class="export-field">商品类目 <b class="required">*</b><SearchableSelect v-model="tiktokExportCategory" :options="tiktokExportOptions?.categories || []" value-key="name" label-key="name" placeholder="请选择商品类目" search-placeholder="搜索类目名称，空格分隔多个关键词" @change="changeTiktokExportCategory"/></div><label>默认售价 <b class="required">*</b><input v-model.number="tiktokExportDefaultPrice" type="number" min="0.01" max="999999" step="0.01" placeholder="请输入售价"/></label><label>默认库存 <b class="required">*</b><input v-model.number="tiktokExportDefaultQuantity" type="number" min="0" max="999999" step="1"/></label><label v-if="tiktokExportOptions?.capabilities?.supports_cod !== false">货到付款（COD） <b class="required">*</b><select v-model="tiktokExportCod"><option value="Y">Y</option><option value="N">N</option></select></label></section><section v-if="selectedTiktokCategoryAttributes.length" class="tiktok-attribute-section"><h3>类目属性</h3><p>所有属性统一直接输入。“选择”仅校验模板支持值；</p><div class="tiktok-export-grid"><label v-for="field in selectedTiktokCategoryAttributes" :key="field.field"><span class="tiktok-attribute-label">{{field.label}} <b v-if="field.required" class="required">*</b><small class="multi-value-hint">{{tiktokAttributeMode(field)}}</small></span><input v-model="tiktokExportAttributes[field.field]" type="text" maxlength="500" :placeholder="tiktokAttributePlaceholder(field)"/><small v-if="field.options?.length" class="tiktok-supported-values">支持值：{{field.options.join('、')}}</small><small v-else class="tiktok-supported-values">请根据商品实际信息手动填写。</small></label></div></section><section class="tiktok-product-overrides"><h3>单品售价与库存</h3><p>留空时使用上方默认值。</p><div class="tiktok-override-head"><span>商品</span><span>售价覆盖</span><span>库存覆盖</span></div><div v-for="draft in selectedDrafts" :key="draft.id" class="tiktok-override-row"><strong>#{{draft.id}} {{draft.title}}</strong><input v-model.number="tiktokExportOverrides[draft.id].price" type="number" min="0.01" max="999999" step="0.01" placeholder="使用默认售价"/><input v-model.number="tiktokExportOverrides[draft.id].quantity" type="number" min="0" max="999999" step="1" placeholder="使用默认库存"/></div></section></template><p v-if="tiktokExportError" class="error material-draft-error">{{tiktokExportError}}</p><div class="modal-actions"><button class="ghost" :disabled="tiktokExportLoading || tiktokSubmitting" @click="showTiktokExportDialog=false">取消</button><button class="primary" :disabled="tiktokExportLoading || !tiktokExportOptions" @click="exportSelectedDrafts">{{tiktokExportLoading ? '生成中…' : '生成并下载'}}</button><button v-if="tiktokExportIsLocal" class="primary" :disabled="tiktokExportLoading || tiktokSubmitting || !tiktokExportOptions" @click="submitSelectedDraftsToHubstudio">{{tiktokSubmitting ? '创建任务中…' : '生成并自动上品'}}</button></div></section></div>
  <div v-if="showShopeeExportDialog" class="modal-backdrop" @click.self="!shopeeExportLoading && (showShopeeExportDialog=false)"><section class="modal-card tiktok-export-dialog"><button class="modal-close" :disabled="shopeeExportLoading" @click="showShopeeExportDialog=false">×</button><h2>导出 Shopee 批量上传表格</h2><p>已选择 {{selectedDrafts.length}} 条同一产品模板的商品草稿。变体名称固定使用 Color 和 Size。</p><div v-if="shopeeExportLoading && !shopeeExportOptions" class="empty">正在读取 Shopee 模板选项…</div><template v-else><section class="tiktok-export-grid"><label>Shopee 类目库 <b class="required">*</b><select v-model="shopeeExportCatalogId" @change="changeShopeeExportCatalog"><option :value="null" disabled>请选择类目库</option><option v-for="catalog in shopeeCatalogs" :key="catalog.id" :value="catalog.id">{{catalog.name}}</option></select></label><div class="export-field">商品类目 <b class="required">*</b><SearchableSelect v-model="shopeeExportCategoryId" :options="shopeeExportOptions?.categories || []" value-key="id" label-key="name" placeholder="请选择商品类目" search-placeholder="搜索类目名称，空格分隔多个关键词"/></div><label>默认售价 <b class="required">*</b><input v-model.number="shopeeExportDefaultPrice" type="number" min="0.10" max="1000000000" step="0.01" placeholder="请输入售价"/></label><label>默认库存 <b class="required">*</b><input v-model.number="shopeeExportDefaultQuantity" type="number" min="0" max="10000000" step="1"/></label></section><section class="tiktok-attribute-section"><h3>物流渠道 <b class="required">*</b></h3><p>至少选择一个渠道，导出时所选渠道写为 {{shopeeExportOptions?.shipping_channels?.[0]?.on_value || 'On'}}，其余写为 {{shopeeExportOptions?.shipping_channels?.[0]?.off_value || 'Off'}}。</p><div class="shopee-channel-options"><label v-for="channel in shopeeExportOptions?.shipping_channels || []" :key="channel.field"><input v-model="shopeeExportChannels" type="checkbox" :value="channel.field"/>{{channel.name}}</label></div></section><section class="tiktok-product-overrides"><h3>单品售价与库存</h3><p>主商品货号和整合规格编号使用草稿 ID；危险物品留空。售价与库存留空时使用默认值。</p><div class="tiktok-override-head"><span>商品</span><span>售价覆盖</span><span>库存覆盖</span></div><div v-for="draft in selectedDrafts" :key="draft.id" class="tiktok-override-row"><strong>#{{draft.id}} {{draft.title}}</strong><input v-model.number="shopeeExportOverrides[draft.id].price" type="number" min="0.10" max="1000000000" step="0.01" placeholder="使用默认售价"/><input v-model.number="shopeeExportOverrides[draft.id].quantity" type="number" min="0" max="10000000" step="1" placeholder="使用默认库存"/></div></section></template><p v-if="shopeeExportError" class="error material-draft-error">{{shopeeExportError}}</p><div class="modal-actions"><button class="ghost" :disabled="shopeeExportLoading" @click="showShopeeExportDialog=false">取消</button><button class="primary" :disabled="shopeeExportLoading || !shopeeExportOptions" @click="exportSelectedDraftsToShopee">{{shopeeExportLoading ? '生成中…' : '生成并下载'}}</button></div></section></div>
  <div v-if="showDraftEditDialog" class="modal-backdrop" @click.self="showDraftEditDialog=false"><section class="modal-card material-draft-dialog"><button class="modal-close" @click="showDraftEditDialog=false">×</button><h2>编辑商品草稿</h2><p>可修改商品标题和产品描述。</p><label>产品标题<input v-model="draftEditTitle" minlength="25" maxlength="255" placeholder="请输入 25-255 个字符"/></label><label>产品描述<textarea v-model="draftEditProductDescription" class="draft-edit-description" maxlength="5000" placeholder="请输入产品描述"></textarea></label><section class="draft-edit-section"><strong>SKU 图 <small class="draft-edit-hint">共 {{draftEditSkus.length}} 个</small></strong><div class="draft-edit-preview"><div v-for="item in draftEditSkus" :key="item.sku" class="draft-edit-image-item"><code :title="item.sku">{{item.sku}}</code><button title="放大查看" @click="openImagePreview(item.image_url, item.sku)"><img :src="imageUrl(item.image_url)" :alt="item.sku"/></button></div></div><p v-if="!draftEditSkus.length" class="draft-edit-empty">该草稿暂无 SKU 图。</p></section><section class="draft-edit-section"><strong>产品图片 <small class="draft-edit-hint">首图 + 其余轮播图</small></strong><div class="draft-edit-preview"><div v-for="(url,index) in editingDraft?.image_urls" :key="url" class="draft-edit-image-item"><code>{{index===0 ? '首图' : draftSkuForImage(editingDraft, url)}}</code><button title="放大查看" @click="openImagePreview(url, editingDraft?.title || '商品素材')"><img :src="imageUrl(url)" :alt="editingDraft?.title || '商品素材'"/></button></div></div></section><section v-if="editingDraft?.size_chart_url" class="draft-edit-section"><strong>尺码图</strong><button class="draft-edit-size-chart-button" title="放大查看" @click="openImagePreview(editingDraft.size_chart_url, '尺码图')"><img class="draft-edit-size-chart" :src="imageUrl(editingDraft.size_chart_url)" alt="尺码图"/></button></section><p v-if="draftEditError" class="error material-draft-error">{{draftEditError}}</p><div class="modal-actions"><button class="ghost" @click="showDraftEditDialog=false">取消</button><button class="primary" :disabled="draftEditSaving" @click="saveDraftEdit">{{draftEditSaving ? '保存中…' : '保存修改'}}</button></div></section></div>
  <div v-if="showTaskDetailDialog && viewingTask?.task_type!=='sku_image'" class="modal-backdrop image-result-backdrop" @click.self="showTaskDetailDialog=false"><section class="modal-card image-result-dialog"><button class="modal-close" @click="showTaskDetailDialog=false">×</button><h2>{{taskTypeLabel(viewingTask)}}任务 #{{viewingTask?.id}}</h2><p>{{viewingTask?.parameters?.source_sku ? `来源 SKU：${viewingTask.parameters.source_sku}` : `参考 ${viewingTask?.parameters?.reference_urls?.length || 0} 张${viewingTask?.parameters?.reference_mode==='random_sku' ? 'SKU 图' : viewingTask?.parameters?.reference_mode==='random_carousel' ? '轮播图' : '图片'}`}}</p><div class="modal-actions"><button class="secondary" @click="openImageWorkspaceFromTask(viewingTask)">打开对应商品草稿</button></div><div class="image-task-candidates"><article v-for="url in viewingTask?.result_urls || []" :key="url"><button class="candidate-preview" @click="openImagePreview(url,'生成结果')"><img :src="imageUrl(url)" alt="生成结果"/></button><button class="primary" :disabled="isTaskResultSelected(viewingTask,url)" @click="applyImageTaskResult(viewingTask,url)">{{isTaskResultSelected(viewingTask,url)?'已采用':viewingTask?.task_type==='carousel'?'采用为轮播图':'采用为首图'}}</button></article><p v-if="!(viewingTask?.result_urls?.length)" class="empty">任务完成后可在这里选择采用结果。</p></div></section></div>
  <div v-if="showDraftImageDialog" class="modal-backdrop image-workspace-backdrop" @click.self="showDraftImageDialog=false">
    <section class="modal-card image-workspace" :class="{'carousel-image-workspace':imageWorkspaceMode==='carousel'}">
      <button class="modal-close" @click="showDraftImageDialog=false">×</button>
      <header class="image-workspace-header">
        <div class="image-workspace-header-text">
          <small>商品草稿 #{{imageDraft?.id}}</small>
          <h2>{{imageWorkspaceMode==='carousel' ? '轮播图工作台' : '图片工作台'}}</h2>
          <p>{{imageDraft?.title}}</p>
        </div>
        <span class="chip purple">{{draftImagePreviewUrls.length}} / 9 张</span>
      </header>
      <nav v-if="imageWorkspaceMode==='full'" class="workspace-steps" aria-label="制作流程">
        <span class="workspace-step" :class="{active: true, done: imageDraft?.carousel_items?.length}">
          <i>1</i><span>生成轮播图</span>
        </span>
        <span class="workspace-step-divider"></span>
        <span class="workspace-step" :class="{active: imageDraft?.carousel_items?.length, done: currentGeneratedMainImage}">
          <i>2</i><span>制作首图</span>
        </span>
        <span class="workspace-step-divider"></span>
        <span class="workspace-step" :class="{active: draftImagePreviewUrls.length}">
          <i>3</i><span>预览确认</span>
        </span>
      </nav>
      <div v-if="imageWorkspaceLoading" class="empty">正在加载图片…</div>
      <template v-else-if="imageDraft">
        <section v-if="imageDraft.published" class="image-lock-notice">
          <strong>该草稿已经发布，仍可继续编辑图片</strong>
          <span>保存只更新本地草稿，不会自动同步到妙手或 TikTok。</span>
        </section>
        <div class="image-workspace-grid">
          <main class="image-workspace-main">
            <section id="carousel-workspace-section" class="workspace-card">
              <div class="workspace-card-header">
                <span class="workspace-step-badge">1</span>
                <div>
                  <h3>生成轮播图</h3>
                  <p>勾选 SKU 图并填写生成参数后开始创作</p>
                </div>
                <span class="workspace-card-action-hint">{{imageDraft.using_sku_fallback?'当前使用 SKU 图回退':`当前 ${imageDraft.carousel_items?.length || 0} 张`}}</span>
              </div>
              <div class="workspace-subsection">
                <div class="workspace-subsection-head">
                  <b>选择 SKU 图</b>
                  <span class="workspace-subsection-count">{{selectedImageSkus.length}} / 9 已选</span>
                </div>
                <div class="workspace-sku-scroll">
                  <label v-for="item in imageDraftSkus" :key="item.sku" class="workspace-sku-card" :class="{selected:selectedImageSkus.includes(item.sku)}">
                    <span class="workspace-sku-check"><input type="checkbox" :disabled="!selectedImageSkus.includes(item.sku) && selectedImageSkus.length>=9" :checked="selectedImageSkus.includes(item.sku)" @change="toggleImageSku(item.sku)"/></span>
                    <span class="workspace-sku-image"><img :src="imageUrl(item.image_url)" :alt="item.sku"/></span>
                    <span class="workspace-sku-info">
                      <b>{{item.sku}}</b>
                    </span>
                  </label>
                  <p v-if="!imageDraftSkus.length" class="workspace-sku-empty">该草稿暂无 SKU 素材。</p>
                </div>
              </div>
              <div class="workspace-params">
                <div class="workspace-settings-grid">
                  <label class="workspace-prompt-field">
                    <span>创作要求</span>
                    <textarea v-model="carouselParams.prompt" rows="2" maxlength="1000" placeholder="例如：保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图"></textarea>
                  </label>
                  <div class="workspace-settings-row">
                    <label>AI 模型<select v-model="carouselParams.provider"><option v-for="provider in availableAiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}</option></select></label>
                    <label>比例<select v-model="carouselParams.ratio"><option>1:1</option><option>3:4</option></select></label>
                    <label>清晰度<select v-model="carouselParams.quality"><option>1K</option><option>2K</option></select></label>
                    <button class="primary workspace-create-button" :disabled="!!imageTaskCreatingType || !selectedImageSkus.length" @click="createDraftImageTasks('carousel')">{{imageTaskCreatingType==='carousel' ? '创建中…' : '开始创作轮播图'}}</button>
                  </div>
                </div>
              </div>
              <div v-if="workspaceCarouselTasks().length" class="workspace-task-panel">
                <div class="workspace-task-panel-head">
                  <b>相关轮播图任务</b>
                  <button class="ghost workspace-task-refresh" :disabled="imageTasksRefreshing" @click="refreshWorkspaceTasks">{{imageTasksRefreshing ? '刷新中…' : '刷新'}}</button>
                </div>
                <div class="workspace-task-list">
                  <div class="workspace-task-row workspace-task-row-head carousel-task-row"><span>素材</span><span>提示词</span><span>状态</span><span>结果</span><span>处理信息</span><span>操作</span></div>
                  <div v-for="task in workspaceCarouselTasks()" :key="task.id" class="workspace-task-row carousel-task-row">
                    <button v-if="task.parameters?.print_url" type="button" class="workspace-task-thumb" title="查看创作素材" @click.stop.prevent="openImagePreview(task.parameters.print_url, '创作素材')"><img :src="imageUrl(task.parameters.print_url)" alt="创作素材"/></button>
                    <span v-else class="workspace-task-dash">—</span>
                    <span class="workspace-task-prompt" :title="task.parameters?.creative_requirement || ''">{{task.parameters?.creative_requirement || '—'}}</span>
                    <span class="workspace-task-status">
                      <span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span>
                      <small>#{{task.id}} · 已提交 {{task.submit_attempts || 0}} 次</small>
                    </span>
                    <button v-if="task.result_urls?.[0]" type="button" class="workspace-task-thumb" title="查看结果图" @click.stop.prevent="openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`)"><img :src="imageUrl(task.result_urls[0])" :alt="`任务 #${task.id} 结果图`"/></button>
                    <span v-else class="workspace-task-dash">—</span>
                    <span class="workspace-task-message" :class="{error: task.status==='failed'}">{{task.failure_reason || '—'}}</span>
                    <span class="workspace-task-actions">
                      <button v-if="taskHasSuccessfulResult(task)" :class="isWorkspaceTaskSelected(task,task.result_urls[0]) ? 'secondary' : 'primary'" :title="isWorkspaceTaskSelected(task,task.result_urls[0]) ? '点击取消采用' : '点击采用'" @click="toggleWorkspaceCarouselTask(task)">{{isWorkspaceTaskSelected(task,task.result_urls[0]) ? '已采用' : '采用'}}</button>
                      <button v-if="task.status==='failed'" class="secondary" :disabled="retryingWorkspaceTaskId===task.id" @click="retryWorkspaceTask(task)">{{retryingWorkspaceTaskId===task.id ? '重试中…' : '重试'}}</button>
                    </span>
                  </div>
                </div>
              </div>
              <div class="workspace-subsection">
                <div class="workspace-subsection-head">
                  <b>生成的轮播图</b>
                  <small>通过上方任务的采用按钮控制图片是否保留</small>
                </div>
                <div class="carousel-strip generated-carousel-strip">
                  <article v-for="(item,index) in adoptedCarouselItems" :key="item.image_url">
                    <span class="carousel-strip-index">{{index + 1}}</span>
                    <img :src="imageUrl(item.image_url)" :alt="item.sku || 'AI 首图'"/>
                    <b>{{item.sku || 'AI 首图'}}</b>
                  </article>
                  <div v-if="!adoptedCarouselItems.length" class="carousel-empty">
                    <span class="carousel-empty-icon" aria-hidden="true">🖼</span>
                    <strong>还没有轮播图</strong>
                    <small>在上方勾选 SKU 图并填写生成参数，然后点击「开始创作轮播图」。</small>
                  </div>
                </div>
              </div>
            </section>
            <section v-if="imageWorkspaceMode==='full'" id="main-image-workspace-section" class="workspace-card">
              <div class="workspace-card-header">
                <span class="workspace-step-badge">2</span>
                <div>
                  <h3>制作首图</h3>
                  <p>首图就是最终轮播图第 1 张；不重新生成时使用当前轮播图第 1 张。</p>
                </div>
              </div>
              <div class="reference-mode-tabs" role="tablist">
                <button type="button" role="tab" :class="{active: mainReferenceMode==='random_carousel'}" :aria-selected="mainReferenceMode==='random_carousel'" @click="selectMainReferenceMode('random_carousel')">
                  <i class="reference-mode-icon">🎲</i>
                  <b>随机选择最多 3 张轮播图</b>
                  <small>无轮播图时自动切换到 SKU 图</small>
                </button>
                <button type="button" role="tab" :class="{active: mainReferenceMode==='random_sku'}" :aria-selected="mainReferenceMode==='random_sku'" @click="selectMainReferenceMode('random_sku')">
                  <i class="reference-mode-icon">🎲</i>
                  <b>随机选择最多 3 张 SKU 图</b>
                  <small>从原始 SKU 图中随机挑选</small>
                </button>
                <button type="button" role="tab" :class="{active: mainReferenceMode==='manual'}" :aria-selected="mainReferenceMode==='manual'" @click="mainReferenceMode='manual'">
                  <i class="reference-mode-icon">👆</i>
                  <b>手动选择参考图</b>
                  <small>轮播图和 SKU 图可混选，最多 9 张</small>
                </button>
              </div>
              <div v-if="mainReferenceMode==='manual'" class="main-reference-groups">
                <div class="main-reference-row"><strong>轮播图</strong><div class="reference-picker"><label v-for="item in mainCarouselReferenceItems" :key="item.image_url" :class="{selected:selectedMainReferences.includes(item.image_url)}"><input type="checkbox" :checked="selectedMainReferences.includes(item.image_url)" :disabled="selectedMainReferences.length>=9 && !selectedMainReferences.includes(item.image_url)" @change="toggleMainReference(item.image_url)"/><img :src="imageUrl(item.image_url)" :alt="item.sku || '轮播图'"/><span>{{item.sku || '轮播图'}}</span></label><p v-if="!mainCarouselReferenceItems.length" class="empty">暂无轮播图</p></div></div>
                <div class="main-reference-row"><strong>SKU 图</strong><div class="reference-picker"><label v-for="item in mainSkuReferenceItems" :key="item.image_url" :class="{selected:selectedMainReferences.includes(item.image_url)}"><input type="checkbox" :checked="selectedMainReferences.includes(item.image_url)" :disabled="selectedMainReferences.length>=9 && !selectedMainReferences.includes(item.image_url)" @change="toggleMainReference(item.image_url)"/><img :src="imageUrl(item.image_url)" :alt="item.sku || 'SKU 图'"/><span>{{item.sku || 'SKU 图'}}</span></label><p v-if="!mainSkuReferenceItems.length" class="empty">暂无 SKU 图</p></div></div>
              </div>
              <div class="workspace-params">
                <div class="workspace-settings-grid">
                  <label class="workspace-prompt-field">
                    <span>创作要求</span>
                    <textarea v-model="mainParams.prompt" rows="2" maxlength="1000" placeholder="例如：以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然"></textarea>
                  </label>
                  <div class="workspace-settings-row">
                    <label>AI 模型<select v-model="mainParams.provider"><option v-for="provider in availableAiProviders" :key="provider.provider" :value="provider.provider">{{provider.display_name}} · {{provider.model}}</option></select></label>
                    <label>比例<select v-model="mainParams.ratio"><option>1:1</option><option>3:4</option></select></label>
                    <label>清晰度<select v-model="mainParams.quality"><option>1K</option><option>2K</option></select></label>
                    <button class="primary workspace-create-button" :disabled="!!imageTaskCreatingType || (!mainCarouselReferenceItems.length && !mainSkuReferenceItems.length)" @click="createDraftImageTasks('main_image')">{{imageTaskCreatingType==='main_image' ? '创建中…' : '开始创作首图'}}</button>
                  </div>
                </div>
              </div>
              <div v-if="workspaceMainTasks().length" class="workspace-task-panel">
                <div class="workspace-task-panel-head">
                  <b>相关首图任务</b>
                  <button class="ghost workspace-task-refresh" :disabled="imageTasksRefreshing" @click="refreshWorkspaceTasks">{{imageTasksRefreshing ? '刷新中…' : '刷新'}}</button>
                </div>
                <div class="workspace-task-list">
                  <div class="workspace-task-row workspace-task-row-head carousel-task-row"><span>素材</span><span>提示词</span><span>状态</span><span>结果</span><span>处理信息</span><span>操作</span></div>
                  <div v-for="task in workspaceMainTasks()" :key="task.id" class="workspace-task-row carousel-task-row">
                    <button v-if="task.parameters?.print_url" type="button" class="workspace-task-thumb" title="查看创作素材" @click.stop.prevent="openImagePreview(task.parameters.print_url, '创作素材')"><img :src="imageUrl(task.parameters.print_url)" alt="创作素材"/></button>
                    <span v-else class="workspace-task-dash">—</span>
                    <span class="workspace-task-prompt" :title="task.parameters?.creative_requirement || ''">{{task.parameters?.creative_requirement || '—'}}</span>
                    <span class="workspace-task-status">
                      <span class="chip" :class="taskStatusClass(task.status)">{{taskStatusLabel[task.status] || task.status || '—'}}</span>
                      <small>#{{task.id}} · 已提交 {{task.submit_attempts || 0}} 次</small>
                    </span>
                    <button v-if="task.result_urls?.[0]" type="button" class="workspace-task-thumb" title="查看结果图" @click.stop.prevent="openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`)"><img :src="imageUrl(task.result_urls[0])" :alt="`任务 #${task.id} 结果图`"/></button>
                    <span v-else class="workspace-task-dash">—</span>
                    <span class="workspace-task-message" :class="{error: task.status==='failed'}">{{task.failure_reason || '—'}}</span>
                    <span class="workspace-task-actions">
                      <button v-if="taskHasSuccessfulResult(task)" :class="isWorkspaceTaskSelected(task,task.result_urls[0]) ? 'secondary' : 'primary'" :title="isWorkspaceTaskSelected(task,task.result_urls[0]) ? '点击取消采用' : '点击采用'" @click="toggleWorkspaceMainTask(task)">{{isWorkspaceTaskSelected(task,task.result_urls[0]) ? '已采用' : '采用'}}</button>
                      <button v-if="task.status==='failed'" class="secondary" :disabled="retryingWorkspaceTaskId===task.id" @click="retryWorkspaceTask(task)">{{retryingWorkspaceTaskId===task.id ? '重试中…' : '重试'}}</button>
                    </span>
                  </div>
                </div>
              </div>
              <div v-if="currentGeneratedMainImage" class="main-image-preview adopted-main-image-preview">
                <img :src="imageUrl(currentGeneratedMainImage.image_url)" alt="AI 生成图片"/>
                <span>已采用图片</span>
              </div>
            </section>
            <section v-if="workspaceFailedTasks().length" class="workspace-card">
              <div class="workspace-card-header"><span class="workspace-step-badge">!</span><div><h3>存在失败的作图任务</h3><p>失败任务会显示在当前制作阶段的“制作失败”筛选中；重试或忽略后会按当前任务状态重新归类。</p></div></div>
              <div class="workspace-task-actions"><template v-for="task in workspaceFailedTasks()" :key="task.id"><button class="secondary" :disabled="retryingWorkspaceTaskId===task.id" @click="retryWorkspaceTask(task)">{{retryingWorkspaceTaskId===task.id?'重试中…':`重试 #${task.id}`}}</button><button class="ghost" @click="ignoreWorkspaceTaskFailure(task)">忽略并继续</button></template></div>
            </section>
            <section v-if="imageWorkspaceMode==='full'" class="workspace-card final-image-preview-card">
              <div class="workspace-card-header">
                <span class="workspace-step-badge">3</span>
                <div>
                  <h3>最终商品图片预览</h3>
                  <p>拖动图片调整最终顺序；第 1 张就是首图，合计不超过 9 张。</p>
                </div>
                <span class="preview-count">{{draftImagePreviewUrls.length}} 张</span>
              </div>
              <div class="carousel-strip">
                <article v-for="(item,index) in draftFinalImageItems" :key="item.image_url" draggable="true" style="cursor:grab" @dragstart="draggedFinalImageUrl=item.image_url" @dragend="draggedFinalImageUrl=''" @dragover.prevent @drop="dropFinalImage(item.image_url)">
                  <span class="carousel-strip-index" :class="{'is-main': index===0}">{{index===0 ? '首' : index + 1}}</span>
                  <button type="button" class="carousel-strip-remove" title="从最终商品图片中移除" @click.stop="removeFinalImage(item.image_url)">×</button>
                  <img :src="imageUrl(item.image_url)" :alt="`商品图片 ${index+1}`"/>
                  <b>{{index===0 ? '1 · 首图' : `${index+1} · 轮播图`}}</b>
                </article>
                <div v-if="!draftImagePreviewUrls.length" class="carousel-empty">
                  <span class="carousel-empty-icon" aria-hidden="true">📦</span>
                  <strong>暂无最终图片</strong>
                  <small>没有自定义轮播图时，系统会自动使用 SKU 图。</small>
                </div>
              </div>
            </section>
          </main>
        </div>
        <div class="modal-actions image-workspace-actions">
          <div v-if="imageDraft?.workflow_stage==='carousel_pending'" class="carousel-confirm-next-step">
            <small>确认轮播图后</small>
            <label><input v-model="carouselConfirmNextStage" type="radio" value="main_image_pending"/>进入首图创作</label>
            <label><input v-model="carouselConfirmNextStage" type="radio" value="ready_to_publish"/>直接到待发布</label>
          </div>
          <small v-else>{{imageWorkspaceMode==='carousel' ? '采用轮播图后点击确认，将保存轮播图。' : '采用、移除和拖动排序仅在当前弹窗暂存；确认后一次保存到草稿。'}}</small>
          <button class="primary" :disabled="imageConfirmSaving || !!imageTaskCreatingType" @click="confirmDraftImages">{{imageConfirmSaving ? '保存中…' : imageDraft?.workflow_stage==='carousel_pending' ? (carouselConfirmNextStage==='ready_to_publish' ? '确认轮播图并到待发布' : '确认轮播图并进入首图创作') : imageDraft?.workflow_stage==='main_image_pending' ? '确认主图并进入待发布' : '保存到草稿'}}</button>
        </div>
      </template>
    </section>
  </div>
  <div v-if="showMainApplyDialog && pendingMainApply" class="modal-backdrop"><section class="modal-card"><button class="modal-close" @click="showMainApplyDialog=false">×</button><h2>选择要移除的轮播图</h2><p>当前已有 9 张轮播图，新首图会成为第 1 张并占用一个位置。</p><label>移除轮播图<select v-model="mainRemoveSku"><option v-for="item in imageDraft?.carousel_items || []" :key="item.image_url" :value="item.image_url">{{item.sku || 'AI 首图'}}</option></select></label><div class="modal-actions"><button class="ghost" @click="showMainApplyDialog=false">取消</button><button class="primary" @click="applyImageTaskResult(pendingMainApply.task,pendingMainApply.url,mainRemoveSku)">移除并采用首图</button></div></section></div>
  <div v-if="showGroupDialog" class="modal-backdrop" @click.self="showGroupDialog=false">
    <section v-if="showGroupDialog" class="modal-card"><h2>新增模板分类</h2><label>分类名称<input v-model="newGroupName" placeholder="例如：夏季服装" @keyup.enter="createGroup" /></label><div class="modal-actions"><button class="ghost" @click="showGroupDialog=false">取消</button><button class="primary" @click="createGroup">确认新增</button></div></section>
  </div>
  <div v-if="showOperatorGroupDialog" class="modal-backdrop" @click.self="showOperatorGroupDialog=false"><section class="modal-card"><h2>{{editingOperatorGroup ? '运营组更名' : '新增运营组'}}</h2><p>{{editingOperatorGroup ? '更改组名不会影响成员归属。' : '每组必须有一位组长；可以选择本公司已启用的普通运营。'}}</p><label>组名 <b class="required">*</b><input v-model="operatorGroupForm.name" maxlength="80" placeholder="请输入组名" /></label><label v-if="!editingOperatorGroup">组长 <b class="required">*</b><select v-model="operatorGroupForm.leader_user_id"><option :value="null">请选择组长</option><option v-for="member in members.filter(item => item.role === 'member' && item.is_active)" :key="member.id" :value="member.id">{{member.name}} · {{operatorGroupName(member.group_id)}}</option></select></label><p v-if="!editingOperatorGroup && !members.some(item => item.role === 'member' && item.is_active)" class="operator-group-hint">请先新增或启用一位普通运营。</p><p v-if="operatorGroupError" class="error modal-error">{{operatorGroupError}}</p><div class="modal-actions"><button class="ghost" @click="showOperatorGroupDialog=false">取消</button><button class="primary" :disabled="operatorGroupSaving" @click="saveOperatorGroup">{{operatorGroupSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showMemberDialog" class="modal-backdrop" @click.self="showMemberDialog=false"><section class="modal-card"><h2>{{editingMember ? '编辑成员' : '新增成员'}}</h2><p>{{editingMember ? '留空密码即可保持原密码不变。' : '姓名、用户代码、邮箱和密码为必填项。'}}</p><label>姓名 <b class="required">*</b><input v-model="memberForm.name" maxlength="80" placeholder="请输入姓名" /></label><label>用户代码 <b class="required">*</b><input v-model="memberForm.user_code" maxlength="2" placeholder="例如：CN（两个字符）" /></label><label>邮箱 <b class="required">*</b><input v-model="memberForm.email" type="email" placeholder="name@example.com" /></label><label>登录密码<input v-model="memberForm.password" type="password" minlength="8" :placeholder="editingMember ? '留空则不修改' : '至少 8 个字符'" /></label><label>角色<select v-model="memberForm.role" :disabled="editingMember?.role === 'team_leader'"><option value="member">普通运营／组员</option><option value="team_leader">运营组长</option></select></label><label>运营组<select v-model="memberForm.group_id" :disabled="editingMember?.role === 'team_leader'"><option :value="null">未分组</option><option v-for="group in operatorGroups" :key="group.id" :value="group.id">{{group.name}}</option></select></label><p v-if="memberForm.role === 'team_leader' && editingMember?.role !== 'team_leader'" class="operator-group-hint">保存后，该组原组长将自动转为组员。</p><p v-if="editingMember?.role === 'team_leader'" class="operator-group-hint">要调整当前组长的角色、分组或状态，请先为本组任命新组长。</p><p v-if="memberFormError" class="error modal-error">{{memberFormError}}</p><div class="modal-actions"><button class="ghost" @click="showMemberDialog=false">取消</button><button class="primary" :disabled="memberSaving" @click="saveMember">{{memberSaving ? '保存中…' : '保存'}}</button></div></section></div>
  <div v-if="showMemberCredentialDialog" class="modal-backdrop" @click.self="showMemberCredentialDialog=false"><section class="modal-card"><h2>配置 {{credentialProvider?.credential_display_name || credentialProvider?.display_name}} 平台密钥</h2><p>{{credentialMember?.name}} 将在{{credentialProvider?.provider === 'deepseek' ? '生成英文商品标题' : '创建和查询 AI 图像任务'}}时使用自己的密钥。密钥会加密保存，前端仅显示脱敏预览。</p><p v-if="memberCredentialPreview()" class="credential-preview">当前密钥：<code>{{memberCredentialPreview()}}</code></p><label>API Key<input v-model="credentialApiKey" type="password" maxlength="2000" autocomplete="new-password" :placeholder="memberCredentialPreview() ? '输入新密钥以替换当前配置' : '请输入新的平台密钥'" @keyup.enter="saveMemberCredential" /></label><div class="modal-actions credential-modal-actions"><button v-if="credentialMember?.ai_provider_credentials?.[memberCredentialKey()]" class="negative" :disabled="credentialSaving" @click="clearMemberCredential">清除密钥</button><span></span><button class="ghost" :disabled="credentialSaving" @click="showMemberCredentialDialog=false">取消</button><button class="primary" :disabled="credentialSaving || !credentialApiKey.trim()" @click="saveMemberCredential">{{credentialSaving ? '保存中…' : '安全保存'}}</button></div></section></div>
  <div v-if="showMiaoshouDialog" class="modal-backdrop" @click.self="showMiaoshouDialog=false"><section class="modal-card"><h2>{{company?.miaoshou_configured?'更新':'配置'}}妙手 API Key</h2><p>App ID 和 App Secret 会加密保存，仅用于本公司的店铺同步与商品上架。保存后将立即重新同步店铺。</p><label>App ID<input v-model="miaoshouForm.app_id" maxlength="255" autocomplete="off" placeholder="请输入 App ID" /></label><label>App Secret<input v-model="miaoshouForm.app_secret" type="password" maxlength="500" autocomplete="new-password" placeholder="请输入 App Secret" @keyup.enter="saveMiaoshouAccount" /></label><div class="modal-actions"><button class="ghost" :disabled="miaoshouSaving" @click="showMiaoshouDialog=false">取消</button><button class="primary" :disabled="miaoshouSaving || !miaoshouForm.app_id.trim() || !miaoshouForm.app_secret.trim()" @click="saveMiaoshouAccount">{{miaoshouSaving?'保存中…':'保存并同步'}}</button></div></section></div>
  <div v-if="showHubstudioDialog && user?.role==='company_admin'" class="modal-backdrop" @click.self="showHubstudioDialog=false"><section class="modal-card"><h2>配置 HubStudio API</h2><p>凭据会加密保存，仅向已认证的本地执行器提供，不返回浏览器。</p><label>App ID<input v-model="hubstudioForm.app_id" maxlength="255" /></label><label>App Secret<input v-model="hubstudioForm.app_secret" type="password" maxlength="2000" /></label><label>团队 Group Code<input v-model="hubstudioForm.group_code" maxlength="120" /></label><div class="modal-actions"><button class="ghost" :disabled="hubstudioSaving" @click="showHubstudioDialog=false">取消</button><button class="primary" :disabled="hubstudioSaving || !hubstudioForm.app_id || !hubstudioForm.app_secret || !hubstudioForm.group_code" @click="saveHubstudioAccount">{{hubstudioSaving?'保存中…':'安全保存'}}</button></div></section></div>
  <div v-if="showShopManagersDialog" class="modal-backdrop" @click.self="showShopManagersDialog=false"><section class="modal-card"><h2>分配店铺管理人员</h2><p>{{managingShop?.name}}。被选中的运营成员可在该店铺创建、管理并上架商品。</p><label v-for="member in members.filter(item => item.role === 'member' || item.role === 'team_leader')" :key="member.id" class="manager-option"><input v-model="selectedManagerIds" :value="member.id" type="checkbox" />{{member.name}} <small>{{member.email}}</small></label><p v-if="!members.some(item => item.role === 'member' || item.role === 'team_leader')" class="empty">请先在成员管理中新增运营成员。</p><div class="modal-actions"><button class="ghost" @click="showShopManagersDialog=false">取消</button><button class="primary" :disabled="shopManagersSaving" @click="saveShopManagers">{{shopManagersSaving ? '保存中…' : '保存分配'}}</button></div></section></div>
  <div v-if="showTemplateDialog" class="drawer-backdrop"><section class="template-drawer"><header><div><h2>{{editingTemplate ? '编辑产品模板' : '新增产品模板'}}</h2><p>完善模板信息后可直接用于 AI 创作。</p></div><button class="drawer-close" aria-label="关闭" :disabled="templateSaving" @click="showTemplateDialog=false">×</button></header><nav class="drawer-tabs"><button :class="{active:templateFormTab==='basic'}" @click="templateFormTab='basic'">模版信息</button><button :class="{active:templateFormTab==='product'}" @click="templateFormTab='product'">商品信息</button><button :class="{active:templateFormTab==='logistics'}" @click="templateFormTab='logistics'">物流信息</button><button :class="{active:templateFormTab==='ai-prompts'}" @click="templateFormTab='ai-prompts'">AI提示词</button></nav><div class="drawer-content"><div v-if="templateFormTab==='basic'" class="drawer-form"><label>模板名称<span>*</span><input v-model="newTemplateName" placeholder="例如：宽松短袖上衣" /></label><label>模板图片<span>*</span><input accept="image/png,image/jpeg,image/webp" type="file" @change="onCoverChange" /><small>{{newTemplateImage ? newTemplateImage.name : editingTemplate?.cover_url ? '保留当前图片' : '支持 JPG、PNG、WebP，最大 3MB'}}</small><div v-if="newTemplateImagePreview" class="template-upload-preview"><img :src="newTemplateImagePreview" alt="模板图片预览" /></div></label><label>模板描述<span>*</span><textarea v-model="newTemplateDescription" maxlength="500" placeholder="描述产品材质、版型和适用的印花区域"></textarea></label><label>模板分类<span>*</span><select v-model="newTemplateGroupId"><option :value="null" disabled>请选择模板分类</option><option v-for="group in templateGroups" :key="group.id" :value="group.id">{{group.name}}</option></select></label></div><div v-else-if="templateFormTab==='product'" class="drawer-form product-info-form"><label>产品描述<span>*</span><textarea v-model="newTemplateProductDescription" rows="4" maxlength="5000" placeholder="填写商品详情页的产品描述"></textarea></label><div class="sku-form"><section><strong><b>*</b> 尺码</strong><div class="sku-size-grid"><div v-for="(_, index) in newSkuSizeOptions" :key="index" class="sku-size-row"><input v-model="newSkuSizeOptions[index]" maxlength="50" placeholder="例如：M"/><small>{{newSkuSizeOptions[index].length}} / 50</small><button title="删除尺码" @click="newSkuSizeOptions.splice(index,1)">×</button></div></div><button class="sku-add-option" @click="addSkuSize">＋ 添加选项</button></section><small class="sku-total">预计生成 {{Math.max(1,newSkuSizeOptions.filter(value=>value.trim()).length)}} 个 SKU</small></div><label>尺码图<span>*</span><input accept="image/png,image/jpeg,image/webp" type="file" @change="onSizeChartChange" /><small>{{newTemplateSizeChart ? newTemplateSizeChart.name : editingTemplate?.size_chart_url ? '保留当前尺码图' : '支持 JPG、PNG、WebP，最多上传 1 张，最大 3MB'}}</small><div v-if="newTemplateSizeChartPreview" class="template-upload-preview"><img :src="newTemplateSizeChartPreview" alt="尺码图预览" /></div></label></div><div v-else-if="templateFormTab==='ai-prompts'" class="drawer-form ai-prompts-form"><label>AI生成标题要求（选填）<textarea v-model="newTemplateTitleTemplate" rows="4" maxlength="500" placeholder="例如：女款长袖连衣裙，突出印花与日常穿搭；如需提及材质，请写明具体材质"></textarea><small>留空时根据首图生成英文标题；填写后作为默认要求，也可在生成时补充。功能特性请明确描述，材质仅在明确要求并指定时提及。</small></label><div><h3>AI生成素材提示</h3><p>为印花贴合保存可复用的创作要求；在 AI 创作页选择模板后可一键填充并继续修改。</p></div><section v-for="(prompt, index) in newTemplateAiPrompts" :key="index" class="ai-prompt-editor"><div><b>提示词 {{index + 1}}</b><button type="button" class="danger" @click="removeTemplateAiPrompt(index)">删除</button></div><label>名称<input v-model="prompt.name" maxlength="80" placeholder="例如：自然布料贴合" /></label><label>提示词内容<textarea v-model="prompt.content" maxlength="1000" placeholder="描述印花贴合方式、细节、光影等创作要求"></textarea></label></section><button type="button" class="secondary ai-prompt-add" @click="addTemplateAiPrompt">＋ 新增提示词</button></div><div v-else class="drawer-form logistics-form"><h3>物流信息 <span title="用于运费及配送计算">?</span></h3><label><b>*</b> 包裹重量<div class="unit-input"><input v-model.number="newPackageWeight" type="number" min="0.001" step="0.001" placeholder="请输入重量" /><span>KG</span></div></label><label><b>*</b> 包裹尺寸<div class="dimension-inputs"><label><input v-model.number="newPackageLength" type="number" min="0.1" step="0.1" placeholder="长" /><span>cm</span></label><label><input v-model.number="newPackageWidth" type="number" min="0.1" step="0.1" placeholder="宽" /><span>cm</span></label><label><input v-model.number="newPackageHeight" type="number" min="0.1" step="0.1" placeholder="高" /><span>cm</span></label></div></label></div></div><footer><button class="ghost" :disabled="templateSaving" @click="showTemplateDialog=false">取消</button><button class="primary" :disabled="templateSaving" @click="createTemplate">{{templateSaving ? '上传中…' : (editingTemplate ? '保存修改' : '确认新增')}}</button></footer></section></div>
  <div v-if="previewImageUrl" class="image-preview-backdrop" @click.self="previewImageUrl=''"><section class="image-preview-modal"><button class="modal-close" aria-label="关闭大图" @click="previewImageUrl=''">×</button><img :src="previewImageUrl" :alt="previewImageAlt"/></section></div>
  <div v-if="productLibraryOrderProduct" class="modal-backdrop" @click.self="closeProductLibraryOrders"><section class="modal-card product-library-orders-dialog" role="dialog" aria-modal="true" aria-labelledby="product-library-orders-heading"><button class="modal-close" aria-label="关闭订单详情" @click="closeProductLibraryOrders">×</button><h2 id="product-library-orders-heading">订单详情</h2><p>{{productLibraryOrderProduct.sku}}</p><div class="product-library-orders-table" :aria-busy="productLibraryOrderLoading"><div class="product-library-orders-head"><span>下单时间</span><span>订单编号</span><span>店铺</span><span>产品 ID</span><span>数量</span></div><div v-for="(order, index) in productLibraryOrders" :key="index" class="product-library-orders-row"><span>{{new Date(order.ordered_at).toLocaleString()}}</span><span :title="order.order_number">{{order.order_number}}</span><span :title="order.shop_name">{{order.shop_name}}</span><span :title="order.product_id">{{order.product_id}}</span><strong>{{order.quantity}}</strong></div><div v-if="!productLibraryOrders.length && !productLibraryOrderLoading" class="empty">暂无订单</div><div v-if="productLibraryOrderLoading" class="product-library-orders-loading" role="status">正在加载订单…</div></div><footer class="draft-pagination product-library-orders-pagination"><span>共 {{productLibraryOrderCount}} 单 · {{productLibraryOrderTotal}} 条明细</span><label>每页 <select v-model.number="productLibraryOrderPageSize" :disabled="productLibraryOrderLoading" @change="changeProductLibraryOrderPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{size}}</option></select> 条</label><button :disabled="productLibraryOrderLoading || productLibraryOrderPage===1" @click="changeProductLibraryOrderPage(productLibraryOrderPage-1)">上一页</button><span>第 {{productLibraryOrderPage}} / {{productLibraryOrderPageCount}} 页</span><button :disabled="productLibraryOrderLoading || productLibraryOrderPage===productLibraryOrderPageCount" @click="changeProductLibraryOrderPage(productLibraryOrderPage+1)">下一页</button></footer></section></div>
  <div v-if="showProductLibraryTemplateDialog" class="modal-backdrop" @click.self="!productLibraryTemplateSaving && (showProductLibraryTemplateDialog=false)"><section class="modal-card product-library-template-dialog"><button class="modal-close" :disabled="productLibraryTemplateSaving" aria-label="关闭批量设置模版" @click="showProductLibraryTemplateDialog=false">×</button><h2>批量设置模版</h2><p>将为 {{selectedProductLibraryIds.length}} 条数据设置同一模版，原模版将被替换，SKU 和使用状态保持不变。</p><label>目标模版<select v-model="productLibraryTargetTemplateId" :disabled="productLibraryTemplateSaving"><option :value="null" disabled>请选择模版</option><option v-for="item in templates" :key="item.id" :value="item.id">{{item.name}}</option></select></label><div class="modal-actions"><button class="ghost" :disabled="productLibraryTemplateSaving" @click="showProductLibraryTemplateDialog=false">取消</button><button class="primary" :disabled="productLibraryTemplateSaving || !productLibraryTargetTemplateId" @click="saveProductLibraryTemplate">{{productLibraryTemplateSaving ? '保存中…' : '确认设置'}}</button></div></section></div>
  <div v-if="toast" class="toast" role="alert" style="position:fixed;top:24px;left:50%;z-index:1000;transform:translateX(-50%);padding:12px 18px;border-radius:10px;background:#302954;color:#fff;box-shadow:0 10px 28px #30295440;font-size:14px">{{ toast }}</div>
  <div v-if="showMaterialUploadDialog" class="modal-backdrop" @click.self="showMaterialUploadDialog=false">
    <section class="modal-card material-draft-dialog claim-materials-dialog material-upload-dialog" @scroll.capture="materialHoverPreview=null" role="dialog" aria-modal="true" aria-labelledby="material-upload-title">
      <button class="modal-close" @click="showMaterialUploadDialog=false">×</button><h2 id="material-upload-title">上传本地素材</h2>
      <p>共 {{pendingMaterialUploadFiles.length}} 张图片，默认不侵权，可逐张或批量修改。</p>
      <p>风格按模板共享，勾选图片后可批量应用；没有风格时请先在创作资源中新增白底图。</p><label>产品模板<select v-model="materialUploadTemplateId"><option :value="null" disabled>请选择产品模板</option><option v-for="template in templates" :key="template.id" :value="template.id">{{template.name}}</option></select></label>
      <div class="material-import-toolbar"><button type="button" class="secondary" @click="pendingMaterialUploadFiles.forEach(item=>item.selected=true)">全选</button><button type="button" class="secondary" @click="pendingMaterialUploadFiles.forEach(item=>item.selected=false)">取消全选</button><InfringementActions :disabled="!pendingMaterialUploadFiles.some(item=>item.selected)" @set="setUploadInfringement"/></div>
      <div class="material-style-actions"><StyleSelect v-model="uploadStyleTargetId" :styles="materialStyles" :template-id="materialUploadTemplateId" :disabled="materialStylesLoading"/><button type="button" class="secondary" :disabled="!pendingMaterialUploadFiles.some(item=>item.selected) || !materialUploadTemplateId || materialStylesLoading" @click="applySelectedStyle(pendingMaterialUploadFiles,uploadStyleTargetId)">应用到选中图片</button></div>
      <div class="material-pending-head" aria-hidden="true"><span></span><span>图片</span><span>文件名</span><span>风格</span><span>侵权状态</span></div><ul class="material-pending-list" aria-label="待上传图片">
        <li v-for="(item,index) in pendingMaterialUploadFiles" :key="index" class="material-pending-row" :class="{selected:item.selected}">
          <input v-model="item.selected" type="checkbox" :aria-label="`选择图片 ${item.file.name}`"/>
          <img :src="item.preview" :alt="item.file.name" class="material-pending-thumbnail" tabindex="0" @pointerenter="showMaterialHoverPreview($event,item.preview,item.file.name)" @pointerleave="materialHoverPreview=null" @focus="showMaterialHoverPreview($event,item.preview,item.file.name)" @blur="materialHoverPreview=null"/>
          <div class="material-pending-info"><b :title="item.file.name">{{item.file.name}}</b></div><span class="material-style-badge material-pending-style" :class="{ungrouped:!item.style_id}" :title="materialStyleLabels.get(item.style_id ?? 0) || '未分组'">{{materialStyleLabels.get(item.style_id ?? 0) || '未分组'}}</span>
          <InfringementToggle v-model="item.is_infringing"/>
        </li>
      </ul>
      <p v-if="materialUploadError" class="error">{{materialUploadError}}</p><div class="modal-actions"><button class="ghost" @click="showMaterialUploadDialog=false">取消</button><button class="primary" @click="uploadMaterialAssets">确认上传</button></div>
    </section>
  </div>
  <footer class="site-footer">
    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">粤ICP备2026142752号-1</a>
  </footer>
  <Teleport to="body">
    <div v-if="(showMaterialUploadDialog || showMaterialImportDialog) && materialHoverPreview" class="batch-claim-hover-preview material-hover-preview" :style="{left:`${materialHoverPreview.left}px`,top:`${materialHoverPreview.top}px`,width:`${materialHoverPreview.width}px`,height:`${materialHoverPreview.height}px`}">
      <img :src="materialHoverPreview.url" :alt="materialHoverPreview.alt"/>
    </div>
  </Teleport>
  <MaterialTransferDialog :visible="showMaterialTransferResults" :items="materialTransferItems" @close="showMaterialTransferResults=false" @changed="refreshAfterMaterialTransfer"/>
</template>

<style scoped>
.carousel-image-workspace {
  width: min(960px, calc(100vw - 40px));
  height: min(820px, calc(100vh - 40px));
}

/* SKU 选择卡使用固定分区，避免长图挤出卡片并遮住下方信息。 */
.workspace-sku-scroll {
  align-items: flex-start;
  min-height: 184px;
  padding: 2px 2px 8px;
}

.workspace-sku-card {
  box-sizing: border-box;
  flex: 0 0 100px;
  width: 100px;
  height: 174px;
  grid-template-rows: 16px 110px 32px;
  gap: 4px;
  padding: 5px;
  overflow: hidden;
}

.workspace-sku-card .workspace-sku-check {
  width: 100%;
  height: 16px;
  justify-content: flex-start;
}

.workspace-sku-card .workspace-sku-image {
  box-sizing: border-box;
  width: 100%;
  height: 110px;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}

.workspace-sku-card .workspace-sku-image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.workspace-sku-card .workspace-sku-info {
  box-sizing: border-box;
  height: 32px;
  min-height: 0;
  align-content: center;
  overflow: hidden;
}

.workspace-sku-card .workspace-sku-info b {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.generated-carousel-strip article {
  cursor: default;
}

.workspace-params .workspace-settings-row {
  grid-template-columns: minmax(180px, 320px) 104px 104px auto;
  align-items: end;
  justify-content: start;
}

.workspace-create-button {
  align-self: end;
  min-height: 36px;
  margin: 0;
  white-space: nowrap;
}

.workspace-task-list {
  max-height: 264px;
  overflow-x: hidden;
  overflow-y: auto;
}

.workspace-task-row-head {
  position: sticky;
  top: 0;
  z-index: 2;
}

.adopted-main-image-preview {
  margin-top: 13px;
  margin-bottom: 0;
}

@media (max-width: 700px) {
  .workspace-params .workspace-settings-row {
    grid-template-columns: 1fr 1fr;
  }

  .workspace-create-button {
    width: 100%;
  }
}
.hub-upload-filters { margin-bottom: 16px; }
.hub-upload-filters label { display: block; width: 200px; max-width: 100%; }
.hub-upload-filters select { width: 100%; }
.hub-upload-table { overflow-x: auto; }
.hub-upload-filters { display:flex; flex-wrap:wrap; gap:16px; margin-bottom:16px; }
.hub-upload-filters label { display:flex; flex-direction:column; gap:6px; min-width:200px; }
.hub-upload-grid { grid-template-columns: 80px 110px 90px minmax(100px, 1fr) minmax(180px, 1.3fr) minmax(160px, 1.5fr) 110px; min-width: 870px; }
.hub-upload-grid > span { overflow-wrap: anywhere; }
</style>
