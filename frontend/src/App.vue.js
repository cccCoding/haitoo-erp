import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from 'axios';
import SearchableSelect from './SearchableSelect.vue';
import ShopDataHeading from './ShopDataHeading.vue';
const pageSizeOptions = [20, 50, 100, 500, 1000];
const productLibraryPageSizeOptions = [...pageSizeOptions, 2000];
const hubUploadPageSizeOptions = [25, 50, 100, 500, 1000];
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' });
const token = ref(localStorage.getItem('haitoro_token') || '');
const route = useRoute();
const router = useRouter();
const workspaceRouteNames = new Set(['dashboard', 'templates', 'pod', 'tasks', 'materials', 'drafts', 'product-library', 'miaoshou-collect-box', 'members', 'shops', 'tiktok-catalogs']);
const page = computed({
    get: () => workspaceRouteNames.has(String(route.name)) ? String(route.name) : 'dashboard',
    set: value => { if (workspaceRouteNames.has(value) && value !== route.name)
        void router.push({ name: value }); },
});
const hubAgentPairingCode = ref(new URLSearchParams(location.search).get('hub_agent_pair') || '');
const email = ref('');
const password = ref('');
const user = ref(null), company = ref(null), shops = ref([]), templates = ref([]), templateGroups = ref([]), tasks = ref([]), materialAssets = ref([]), drafts = ref([]), members = ref([]), operatorGroups = ref([]), aiProviders = ref([]);
const loading = ref(false), error = ref('');
const toast = ref('');
const templateQuery = ref(''), activeGroupId = ref(null), selectedTemplateId = ref(null);
const showGroupDialog = ref(false), showTemplateDialog = ref(false), templateFormTab = ref('basic'), newGroupName = ref(''), newTemplateName = ref(''), newTemplateDescription = ref(''), newTemplateTitleTemplate = ref(''), newTemplateProductDescription = ref(''), newTemplateSizeChart = ref(null), newTemplateSizeChartPreview = ref(''), newTemplateGroupId = ref(null), newTemplateImage = ref(null), newTemplateImagePreview = ref(''), newPackageWeight = ref(null), newPackageLength = ref(null), newPackageWidth = ref(null), newPackageHeight = ref(null), newSkuSizeOptions = ref([]), newTemplateAiPrompts = ref([]), editingTemplate = ref(null);
const showMemberDialog = ref(false), editingMember = ref(null), memberForm = ref({ name: '', user_code: '', email: '', password: '', is_active: true, role: 'member', group_id: null }), memberSaving = ref(false), memberFormError = ref(''), memberListRefreshing = ref(false);
const showOperatorGroupDialog = ref(false), editingOperatorGroup = ref(null), operatorGroupForm = ref({ name: '', leader_user_id: null }), operatorGroupSaving = ref(false), operatorGroupError = ref('');
const showMemberCredentialDialog = ref(false), credentialMember = ref(null), credentialProvider = ref(null), credentialApiKey = ref(''), credentialSaving = ref(false);
const showMyAccountDialog = ref(false), myName = ref(''), myUserCode = ref(''), myAccountSaving = ref(false);
const managedShops = ref([]), shopLoading = ref(false), shopError = ref('');
const activeMiaoshouTab = ref('shops');
const showMiaoshouDialog = ref(false), miaoshouForm = ref({ app_id: '', app_secret: '' }), miaoshouSaving = ref(false);
const showHubstudioDialog = ref(false), hubstudioSaving = ref(false), hubstudioForm = ref({ app_id: '', app_secret: '', group_code: '' });
const hubUploadTasks = ref([]), hubUploadTotal = ref(0), hubUploadPage = ref(1), hubUploadPageSize = ref(25), hubUploadCreatorId = ref(null), hubUploadLoading = ref(false), hubUploadError = ref('');
const hubUploadTemplateId = ref(null), hubUploadTemplates = ref([]);
const hubUploadPageCount = computed(() => Math.max(1, Math.ceil(hubUploadTotal.value / hubUploadPageSize.value)));
const hubUploadStatusLabels = { queued: '排队中', running: '执行中', completed: '已提交', awaiting_attention: '待人工处理', failed: '失败', cancelled: '已取消', expired: '已过期' };
let hubUploadRequestId = 0;
async function loadHubUploadTasks() {
    if (!token.value || !user.value)
        return;
    const requestId = ++hubUploadRequestId;
    hubUploadLoading.value = true;
    hubUploadError.value = '';
    try {
        const { data } = await api.get('/hub-upload-tasks', { headers: headers.value, params: { page: hubUploadPage.value, page_size: hubUploadPageSize.value, template_id: hubUploadTemplateId.value ?? undefined, scope: user.value.role === 'company_admin' ? 'company' : 'own', creator_id: user.value.role === 'company_admin' ? hubUploadCreatorId.value ?? undefined : undefined } });
        if (requestId !== hubUploadRequestId)
            return;
        hubUploadTemplates.value = data.templates || [];
        hubUploadTasks.value = data.items;
        hubUploadTotal.value = data.total;
        if (hubUploadPage.value > hubUploadPageCount.value) {
            hubUploadPage.value = hubUploadPageCount.value;
            await loadHubUploadTasks();
        }
    }
    catch (e) {
        if (requestId === hubUploadRequestId) {
            hubUploadTasks.value = [];
            hubUploadTotal.value = 0;
            hubUploadError.value = e.response?.data?.detail || '加载自动上品记录失败，请重试';
        }
    }
    finally {
        if (requestId === hubUploadRequestId)
            hubUploadLoading.value = false;
    }
}
function changeHubUploadPageSize() { hubUploadPage.value = 1; void loadHubUploadTasks(); }
function changeHubUploadCreator() { hubUploadPage.value = 1; void loadHubUploadTasks(); }
function changeHubUploadPage(target) { hubUploadPage.value = Math.min(Math.max(1, target), hubUploadPageCount.value); void loadHubUploadTasks(); }
function hubUploadEnvironment(task) { return task.environment_name || task.container_code || (task.environment_id ? String(task.environment_id) : '等待领取'); }
const tiktokCatalogs = ref([]), tiktokCatalogLoading = ref(false), tiktokCatalogError = ref(''), tiktokCatalogListRefreshing = ref(false);
const showTiktokCatalogDialog = ref(false), tiktokCatalogName = ref(''), tiktokCatalogFile = ref(null);
const tiktokCatalogTypeTab = ref('tiktok_local');
const showTiktokCatalogDetailDialog = ref(false), managingTiktokCatalog = ref(null), managingTiktokCatalogOptions = ref(null), managingTiktokCategory = ref('');
const materialUploading = ref(false), materialUploadError = ref('');
const materialDownloading = ref(false);
const selectedMaterialAssetIds = ref([]), materialTemplateFilterId = ref(null), showMaterialDraftDialog = ref(false), materialDraftTemplateId = ref(null), materialDraftTitle = ref(''), materialDraftProductDescription = ref(''), materialDraftSizeChartPreview = ref(''), materialDraftTitleGenerating = ref(false), materialDraftSaving = ref(false);
const materialDraftAdditionalRequirements = ref(''), showDraftAdditionalRequirements = ref(false), showDraftTitleHelp = ref(false);
watch(showMaterialDraftDialog, () => { materialDraftAdditionalRequirements.value = ''; showDraftAdditionalRequirements.value = false; showDraftTitleHelp.value = false; });
const libraryDraftMode = ref(false), libraryDraftSelection = ref([]), materialDraftTitleEdited = ref(false);
const materialDraftAssets = ref([]), draggedMaterialDraftAssetId = ref(null);
const activeMaterialUsageTab = ref('unused');
const materialUsageTabs = [{ key: 'unused', label: '未使用' }, { key: 'used', label: '已使用' }];
const showMaterialBatchDraftDialog = ref(false), materialBatchGroupSize = ref(5), materialBatchMode = ref('sequential'), materialBatchGroups = ref([]), materialBatchSaving = ref(false);
const draggedMaterialBatchAsset = ref(null);
watch(showMaterialBatchDraftDialog, () => { for (const group of materialBatchGroups.value) {
    group.additionalRequirements = '';
    group.showAdditionalRequirements = false;
    group.showTitleHelp = false;
} });
const pendingMaterialUploadFiles = ref([]), showMaterialUploadDialog = ref(false), materialUploadTemplateId = ref(null);
const materialUploadedCount = ref(0), materialUploadTotal = ref(0), pendingMaterialUploadUrls = ref([]);
const MATERIAL_UPLOAD_CONCURRENCY = 8, MATERIAL_UPLOAD_MAX_FILES = 100, IMAGE_UPLOAD_RETRY = 2;
const templateSaving = ref(false);
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'], MAX_IMAGE_BYTES = 3 * 1024 * 1024;
const showDraftEditDialog = ref(false), editingDraft = ref(null), draftEditTitle = ref(''), draftEditProductDescription = ref(''), draftEditSaving = ref(false), draftEditError = ref('');
const publishingDraftId = ref(null), skippingCarouselDraftId = ref(null), skippingMainImageDraftId = ref(null), dispatchingDraftStage = ref('');
const selectedDraftIds = ref([]), showTiktokExportDialog = ref(false), tiktokExportOptions = ref(null), tiktokExportLoading = ref(false), tiktokExportError = ref('');
const showShopeeExportDialog = ref(false), shopeeExportOptions = ref(null), shopeeExportLoading = ref(false), shopeeExportError = ref('');
const showMiaoshouPublishDialog = ref(false), miaoshouPublishDraftIds = ref([]), miaoshouPublishShopId = ref(null), miaoshouPublishing = ref(false), miaoshouPublishCompleted = ref(0), miaoshouPublishFailed = ref(0);
const showBatchCarouselDialog = ref(false), showBatchMainImageDialog = ref(false), batchCarouselSaving = ref(false), batchMainImageSaving = ref(false), batchCarouselSkipping = ref(false), batchMainImageSkipping = ref(false), batchCarouselSelections = ref({}), batchMainImageSelections = ref({});
const showBatchImageReviewDialog = ref(false), batchImageReviewLoading = ref(false), batchImageReviewSaving = ref(false), batchImageReviewType = ref('carousel'), batchImageReviewDrafts = ref([]), batchImageReviewSelections = ref({}), batchCarouselReviewNextStage = ref('main_image_pending');
const MAX_DRAFT_BATCH_SIZE = 100;
const tiktokExportCatalogId = ref(null), tiktokExportCategory = ref(''), tiktokExportDefaultPrice = ref(null), tiktokExportDefaultQuantity = ref(999), tiktokExportCod = ref('Y'), tiktokExportAttributes = ref({}), tiktokExportOverrides = ref({}), tiktokSubmitting = ref(false);
const TIKTOK_EXPORT_ATTRIBUTE_PRESETS_VERSION = 'v1';
const shopeeExportCatalogId = ref(null), shopeeExportCategoryId = ref(''), shopeeExportDefaultPrice = ref(null), shopeeExportDefaultQuantity = ref(999), shopeeExportChannels = ref([]), shopeeExportOverrides = ref({});
const draftPageSize = ref(20), currentDraftPage = ref(1), draftTemplateFilterId = ref(null), draftCreatorFilterId = ref(null), draftListRefreshing = ref(false);
const collectBoxItems = ref([]), collectBoxTotal = ref(0), collectBoxLoading = ref(false);
const productLibraryItems = ref([]), productLibraryTotal = ref(0), productLibraryPage = ref(1), productLibraryPageSize = ref(20), productLibraryLoading = ref(false), productLibraryImporting = ref(false), productLibraryDownloading = ref(false);
const productLibraryStatisticsSubmitting = ref(false);
const productLibraryStatisticsTask = ref(null);
const productLibraryStatisticsRunning = computed(() => ['queued', 'running'].includes(productLibraryStatisticsTask.value?.status));
const productLibraryRankingItems = ref([]), productLibraryRankingTotal = ref(0), productLibraryRankingPage = ref(1), productLibraryRankingPageSize = ref(20), productLibraryRankingLoading = ref(false);
const productLibraryRankingDate = ref(null), productLibraryRankingThroughDate = ref(null), productLibraryRankingError = ref('');
const productLibraryShops = ref([]), productLibraryShopsLoading = ref(false), productLibraryAssigningId = ref(null);
let productLibraryRankingRequestId = 0;
const stagnantMaterials = ref([]), stagnantTotal = ref(0), stagnantPage = ref(1), stagnantPageSize = ref(20), stagnantCreatorId = ref(null), stagnantLoading = ref(false), stagnantError = ref('');
let stagnantRequestId = 0;
const newImages = ref([]), newImagesTotal = ref(0), newImagesPage = ref(1), newImagesPageSize = ref(20), newImagesCreatorId = ref(null), newImagesUsageStatus = ref('all'), newImagesLoading = ref(false), newImagesError = ref('');
let newImagesRequestId = 0;
const activeProductLibraryTab = ref('products');
const productLibraryTabs = [
    { key: 'shops', label: '店铺管理' }, { key: 'products', label: '排行榜' }, { key: 'top7', label: '7天热销TOP50' }, { key: 'top15', label: '15天热销TOP50' },
    { key: 'top30', label: '30天热销TOP50' }, { key: 'potential', label: '潜力款' },
    { key: 'hot', label: '热销款' }, { key: 'booming', label: '旺款' }, { key: 'stagnant', label: '滞销款' }, { key: 'new_images', label: '新图' },
];
const productLibraryRankingTabKeys = new Set(['top7', 'top15', 'top30', 'potential', 'hot', 'booming']);
const productLibraryTopTabKeys = new Set(['top7', 'top15', 'top30']);
const productLibraryCategoryDescriptions = {
    stagnant: '素材创建超过 90 天且历史累计 0 订单',
    new_images: '近 5 天新增的素材',
    potential: '近7天销量大于30',
    hot: '近7天销量大于70',
    booming: '近7天销量大于130',
};
const productLibraryFilters = ref({ shops: [] });
const productLibrarySelectedShopIds = ref([]), productLibraryShopSearch = ref('');
const productLibraryShopFilterDetails = ref(null);
function closeProductLibraryShopFilterOnOutsideClick(event) {
    const details = productLibraryShopFilterDetails.value;
    if (details?.open && !details.contains(event.target))
        details.open = false;
}
const productLibraryShopOptions = computed(() => productLibraryFilters.value.shops.filter(shop => shop.label.toLocaleLowerCase().includes(productLibraryShopSearch.value.trim().toLocaleLowerCase())));
const productLibraryShopSelectionLabel = computed(() => productLibrarySelectedShopIds.value.length === 0 ? '全部店铺' : productLibrarySelectedShopIds.value.length === 1 ? productLibraryFilters.value.shops.find(shop => shop.id === productLibrarySelectedShopIds.value[0])?.label || '已选 1 家店铺' : `已选 ${productLibrarySelectedShopIds.value.length} 家店铺`);
const productLibraryTemplateFilter = ref(''), productLibrarySku = ref('');
const appliedProductLibraryFilters = ref({ sourceIds: [], template: '', sku: '' });
const rankingShopFilters = ref({});
const selectedProductLibraryIds = ref([]), productLibraryBrokenImages = ref([]);
const showProductLibraryTemplateDialog = ref(false), productLibraryTargetTemplateId = ref(null), productLibraryTemplateSaving = ref(false);
const productLibraryOrderProduct = ref(null), productLibraryOrders = ref([]), productLibraryOrderTotal = ref(0), productLibraryOrderCount = ref(0), productLibraryOrderPage = ref(1), productLibraryOrderPageSize = ref(20), productLibraryOrderLoading = ref(false);
let productLibraryOrderRequestId = 0;
const productLibraryFileInput = ref(null);
const collectBoxConfigured = ref(false), collectBoxLastSyncedAt = ref(null), collectBoxInitialSyncedAt = ref(null);
const collectBoxQuery = ref(''), collectBoxPage = ref(1), collectBoxPageSize = ref(20);
const activeDraftTab = ref('all'), draftTotal = ref(0), draftTabCounts = ref({ all: 0, pending: 0, carousel_pending: 0, main_image_pending: 0, ready_to_publish: 0, published: 0 });
const activeDraftWorkStatus = ref('all'), draftWorkStatusCounts = ref({ all: 0, not_started: 0, in_progress: 0, awaiting_review: 0, failed: 0 });
const draftWorkStatusTabs = [{ key: 'all', label: '全部' }, { key: 'not_started', label: '未制作' }, { key: 'in_progress', label: '制作中' }, { key: 'awaiting_review', label: '待审核' }, { key: 'failed', label: '制作失败' }];
const draftTabs = [{ key: 'all', label: '全部' }, { key: 'pending', label: '待处理' }, { key: 'carousel_pending', label: '待制作轮播图' }, { key: 'main_image_pending', label: '待制作主图' }, { key: 'ready_to_publish', label: '待发布' }, { key: 'published', label: '发布成功' }];
const draftStatusLabels = { pending: '待处理', carousel_pending: '待制作轮播图', main_image_pending: '待制作主图', ready_to_publish: '待发布', published: '发布成功' };
const taskTypeLabels = { sku_image: 'SKU图', carousel: '轮播图', main_image: '首图' };
const initialTaskParams = new URLSearchParams(location.search);
const initialTaskType = initialTaskParams.get('task_type');
const activeTaskType = ref(['sku_image', 'carousel', 'main_image'].includes(initialTaskType || '') ? initialTaskType : 'sku_image');
const initialTaskPage = Number(initialTaskParams.get('task_page'));
const initialTaskPageSize = Number(initialTaskParams.get('task_page_size'));
const initialTaskCreator = initialTaskParams.get('task_creator');
const initialTaskStatus = initialTaskParams.get('task_status');
const initialTaskFrom = initialTaskParams.get('task_from') || '';
const initialTaskTo = initialTaskParams.get('task_to') || '';
const initialTaskSkuQuery = initialTaskParams.get('task_skus') || '';
const initialTaskTemplateId = Number(initialTaskParams.get('task_template')) || null;
const taskPageSize = ref(pageSizeOptions.includes(initialTaskPageSize) ? initialTaskPageSize : 20), currentTaskPage = ref(initialTaskPage > 0 ? initialTaskPage : 1), taskTotal = ref(0), taskActiveCount = ref(0), taskStatusCounts = ref({}), taskCreatorFilterId = ref(initialTaskCreator && initialTaskCreator !== 'all' ? Number(initialTaskCreator) || null : null);
const taskTypeTotals = ref({ sku_image: 0, carousel: 0, main_image: 0 });
const taskTypeFilteredTotals = ref({ sku_image: null, carousel: null, main_image: null });
const taskTabStates = ref({ sku_image: null, carousel: null, main_image: null });
const taskStatusFilter = ref(initialTaskStatus !== null && ['queued', 'running', 'awaiting_selection', 'completed', 'failed', ''].includes(initialTaskStatus) ? initialTaskStatus : 'awaiting_selection'), taskCreatedFrom = ref(initialTaskFrom), taskCreatedTo = ref(initialTaskTo);
const taskSkuQuery = ref(initialTaskSkuQuery);
const taskTemplateFilterId = ref(initialTaskTemplateId);
const appliedTaskFilters = ref({ creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: initialTaskFrom ? new Date(initialTaskFrom).toISOString() : '', created_to: initialTaskTo ? new Date(initialTaskTo).toISOString() : '', sku_query: initialTaskSkuQuery, template_id: initialTaskTemplateId });
const selectedTaskIds = ref([]), showBatchClaimDialog = ref(false), batchClaimItems = ref([]), batchClaimLoading = ref(false), batchClaiming = ref(false), batchClaimCompleted = ref(0), batchClaimTotal = ref(0), batchClaimFailed = ref(0);
const materialPageSize = ref(20), currentMaterialPage = ref(1), materialTotal = ref(0), materialCreatorFilterId = ref(null), materialListRefreshing = ref(false);
const creatorFiltersInitialized = ref(false);
const previewImageUrl = ref(''), previewImageAlt = ref('');
const showDraftImageDialog = ref(false), imageWorkspaceMode = ref('full'), imageDraft = ref(null), imageWorkspaceLoading = ref(false), imageTasksRefreshing = ref(false), imageTaskCreatingType = ref(''), imageConfirmSaving = ref(false);
const carouselConfirmNextStage = ref('main_image_pending');
const selectedImageSkus = ref([]), selectedMainReferences = ref([]), mainReferenceMode = ref('random_carousel');
const carouselParams = ref({ prompt: '', provider: '', ratio: '1:1', quality: '1K' }), mainParams = ref({ prompt: '', provider: '', ratio: '1:1', quality: '1K' });
const batchCarouselParams = ref({ prompt: '', provider: '', ratio: '1:1', quality: '1K' });
const batchMainImageParams = ref({ prompt: '', provider: '', ratio: '1:1', quality: '1K' }), batchMainImageReferenceMode = ref('random_carousel');
const stagedFinalImageItems = ref(null), draggedFinalImageUrl = ref('');
const showMainApplyDialog = ref(false), pendingMainApply = ref(null), mainRemoveSku = ref('');
const showShopManagersDialog = ref(false), managingShop = ref(null), selectedManagerIds = ref([]), shopManagersSaving = ref(false);
const showTaskDetailDialog = ref(false), viewingTask = ref(null), taskDetailLoading = ref(false);
const taskListRefreshing = ref(false), retryingTaskId = ref(null), batchRetryingTasks = ref(false), retryingWorkspaceTaskId = ref(null);
const showClaimMaterialsDialog = ref(false), claimingTask = ref(null), selectedClaimResultUrls = ref([]), claimingMaterials = ref(false);
const defaultSkuSizes = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL'];
const defaultPackageLogistics = { weight: 0.28, length: 30, width: 16, height: 2 };
const creativeAssets = ref([]), showCreativeAssetsDialog = ref(false), creativeAssetError = ref(''), creativeSubmitError = ref(''), creativeRequirement = ref(''), creativePromptIndex = ref(''), creativeProvider = ref(''), creativeRatio = ref('1:1'), creativeQuality = ref('1K'), creativeUploading = ref(false), creativeUploadedCount = ref(0);
const personalWhiteImages = ref([]), personalPrompts = ref([]), selectedWhiteImageId = ref(null), personalResourcesLoading = ref(false);
const showPersonalResourcesDialog = ref(false), personalResourceTab = ref('white-images'), managedResourceUserId = ref(null), managedWhiteImages = ref([]), managedPrompts = ref([]), personalResourceSaving = ref(false);
const showTeamResourcesDialog = ref(false), teamResourceTab = ref('white-images'), teamResourceUserId = ref(null), teamResourceTemplateId = ref(null), teamWhiteImages = ref([]), teamPrompts = ref([]), teamResourcesLoading = ref(false), teamResourceQuery = ref('');
const editingWhiteImage = ref(null), whiteImageForm = ref({ template_id: null, name: '', file: null });
const editingPersonalPrompt = ref(null), personalPromptForm = ref({ template_id: null, name: '', content: '' });
const nav = [{ key: 'dashboard', icon: '◈', label: '工作台' }, { key: 'templates', icon: '▦', label: '产品模板' }, { key: 'pod', icon: '✦', label: 'AI创作' }, { key: 'tasks', icon: '◌', label: '任务中心' }, { key: 'materials', icon: '◈', label: '素材库' }, { key: 'drafts', icon: '▤', label: '商品草稿' }, { key: 'product-library', icon: '▤', label: '产品库' }, { key: 'miaoshou-collect-box', icon: '▤', label: '妙手管理' }, { key: 'shops', icon: '▣', label: 'HubStudio管理' }, { key: 'tiktok-catalogs', icon: '▧', label: '类目管理', adminOnly: true }, { key: 'members', icon: '♙', label: '成员管理', adminOnly: true }];
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }));
const visibleNav = computed(() => nav.filter(item => !item.adminOnly || user.value?.role === 'company_admin'));
const pageTitle = computed(() => nav.find(x => x.key === page.value)?.label || '');
const filteredTemplates = computed(() => templates.value.filter(t => (!activeGroupId.value || t.group_id === activeGroupId.value) && t.name.toLowerCase().includes(templateQuery.value.trim().toLowerCase())));
function templateGroupIsEmpty(groupId) { return !templates.value.some(template => template.group_id === groupId); }
// 运营端接口只返回后台已启用的模型；这里再保留一次筛选，避免接口数据异常时将停用模型带入任务。
const availableAiProviders = computed(() => aiProviders.value.filter(provider => provider.enabled !== false));
// 密钥属于平台而不是具体模型。相同 credential_provider 的模型只显示一个入口。
const memberCredentialProviders = computed(() => {
    const seen = new Set();
    return [...aiProviders.value, { provider: 'deepseek', credential_provider: 'deepseek', display_name: 'DeepSeek', credential_display_name: 'DeepSeek' }].filter(provider => {
        const credentialProvider = provider.credential_provider || provider.provider;
        if (seen.has(credentialProvider))
            return false;
        seen.add(credentialProvider);
        return true;
    }).map(provider => ({
        ...provider,
        credential_provider: provider.credential_provider || provider.provider,
        credential_display_name: provider.credential_provider === 'grsai' ? 'Grsai' : provider.display_name,
    }));
});
const selectedCreativeProvider = computed(() => availableAiProviders.value.find(provider => provider.provider === creativeProvider.value));
function providerUsesAutoQuality(provider) { return provider === 'grsai-gpt-image-2'; }
function enforceProviderQuality(provider, params) { if (providerUsesAutoQuality(provider))
    params.quality = 'auto';
else if (params.quality === 'auto')
    params.quality = '1K'; }
const creativeCredentialError = computed(() => selectedCreativeProvider.value?.credential_configured === false
    ? `尚未配置个人 ${selectedCreativeProvider.value.display_name} 平台密钥，请联系公司管理员配置`
    : '');
const selectedTemplate = computed(() => templates.value.find(t => t.id === selectedTemplateId.value));
const selectedWhiteImage = computed(() => personalWhiteImages.value.find(item => item.id === selectedWhiteImageId.value));
const otherResourceOwners = computed(() => user.value?.role === 'company_admin' ? members.value.filter(owner => owner.id !== user.value.id) : []);
const filteredTeamWhiteImages = computed(() => {
    const query = teamResourceQuery.value.trim().toLowerCase();
    return query ? teamWhiteImages.value.filter(item => item.name.toLowerCase().includes(query)) : teamWhiteImages.value;
});
const filteredTeamPrompts = computed(() => {
    const query = teamResourceQuery.value.trim().toLowerCase();
    return query ? teamPrompts.value.filter(item => `${item.name} ${item.content}`.toLowerCase().includes(query)) : teamPrompts.value;
});
const selectedMaterialAssets = computed(() => materialAssets.value.filter(asset => selectedMaterialAssetIds.value.includes(asset.id)));
const filteredMaterialAssets = computed(() => materialAssets.value);
const allCurrentMaterialAssetsSelected = computed(() => { const selectable = filteredMaterialAssets.value.filter(asset => asset.sku); return Boolean(selectable.length) && selectable.every(asset => selectedMaterialAssetIds.value.includes(asset.id)); });
const someCurrentMaterialAssetsSelected = computed(() => !allCurrentMaterialAssetsSelected.value && filteredMaterialAssets.value.some(asset => selectedMaterialAssetIds.value.includes(asset.id)));
const selectedMaterialTemplateId = computed(() => {
    const templateIds = [...new Set(selectedMaterialAssets.value.map(asset => asset.template_id).filter(Boolean))];
    return templateIds.length === 1 ? templateIds[0] : null;
});
const materialDraftTemplate = computed(() => templates.value.find(template => template.id === materialDraftTemplateId.value));
const materialDraftSizes = computed(() => {
    const options = materialDraftTemplate.value?.sku_specifications?.size?.options || [];
    return options.map((size) => String(size).trim()).filter(Boolean);
});
const materialDraftSkuCount = computed(() => materialDraftAssets.value.length);
const canCreateMaterialBatch = computed(() => selectedMaterialAssets.value.length >= 5 && Boolean(selectedMaterialTemplateId.value));
// 服务端按 Tab 返回数据；这里再按 display_tab 兜底，避免接口请求失败或旧服务未更新时，
// 已切换的 Tab 短暂显示上一页的混合数据。
const filteredDrafts = computed(() => activeDraftTab.value === 'all' ? drafts.value : drafts.value.filter(draft => draft.display_tab === activeDraftTab.value));
const draftPageCount = computed(() => Math.max(1, Math.ceil(draftTotal.value / draftPageSize.value)));
const visibleDraftPage = computed(() => Math.min(currentDraftPage.value, draftPageCount.value));
const pagedDrafts = computed(() => filteredDrafts.value);
const selectedDrafts = computed(() => filteredDrafts.value.filter(draft => selectedDraftIds.value.includes(draft.id)));
const allPagedDraftsSelected = computed(() => Boolean(pagedDrafts.value.length) && pagedDrafts.value.every(draft => selectedDraftIds.value.includes(draft.id)));
const batchDispatchEligible = computed(() => selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'pending'));
const crossBorderManagedShops = computed(() => managedShops.value.filter(shop => shop.shop_type !== 'local'));
const miaoshouAssignableShops = computed(() => shops.value.filter(shop => shop.shop_type !== 'local' && shop.external_shop_id));
const batchMiaoshouPublishEligible = computed(() => activeDraftTab.value === 'ready_to_publish' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'ready_to_publish'));
const tiktokExportEligible = computed(() => selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab !== 'pending'));
const batchCarouselEligible = computed(() => activeDraftTab.value === 'carousel_pending' && ['all', 'not_started'].includes(activeDraftWorkStatus.value) && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'carousel_pending' && draft.carousel_task_summary?.work_status === 'not_started'));
const batchCarouselReviewEligible = computed(() => activeDraftTab.value === 'carousel_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.carousel_task_summary?.work_status === 'awaiting_review'));
const batchCarouselSkipEligible = computed(() => activeDraftTab.value === 'carousel_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'carousel_pending'));
const batchMainImageSkipEligible = computed(() => activeDraftTab.value === 'main_image_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'main_image_pending'));
const batchMainImageEligible = computed(() => activeDraftTab.value === 'main_image_pending' && ['all', 'not_started'].includes(activeDraftWorkStatus.value) && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.display_tab === 'main_image_pending' && draft.main_image_task_summary?.work_status === 'not_started'));
const batchMainImageReviewEligible = computed(() => activeDraftTab.value === 'main_image_pending' && selectedDrafts.value.length > 0 && selectedDrafts.value.every(draft => draft.main_image_task_summary?.work_status === 'awaiting_review'));
const selectedTiktokCategoryAttributes = computed(() => tiktokExportOptions.value?.attributes_by_category?.[tiktokExportCategory.value] || []);
const managingTiktokCategoryAttributes = computed(() => managingTiktokCatalogOptions.value?.attributes_by_category?.[managingTiktokCategory.value] || []);
const activeTiktokCatalogs = computed(() => tiktokCatalogs.value.filter(catalog => (catalog.template_type || 'tiktok_local') === tiktokCatalogTypeTab.value));
const tiktokExportCatalogs = computed(() => tiktokCatalogs.value.filter(catalog => ['tiktok_local', 'tiktok_cross_border'].includes(catalog.template_type || 'tiktok_local')));
const shopeeCatalogs = computed(() => tiktokCatalogs.value.filter(catalog => catalog.template_type === 'shopee_basic'));
const tiktokExportIsLocal = computed(() => (tiktokExportOptions.value?.category_catalog?.template_type || tiktokCatalogs.value.find(catalog => catalog.id === tiktokExportCatalogId.value)?.template_type || 'tiktok_local') === 'tiktok_local');
function tiktokCatalogTypeLabel(type) { return type === 'shopee_basic' ? 'Shopee' : type === 'tiktok_cross_border' ? 'tk跨境店' : 'tk本土店'; }
async function changeDraftPageSize() { if (draftListRefreshing.value)
    return; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList(); }
async function changeDraftTab(tab) { if (draftListRefreshing.value)
    return; activeDraftTab.value = tab; activeDraftWorkStatus.value = 'all'; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList(); }
async function changeDraftWorkStatus(status) { if (draftListRefreshing.value)
    return; activeDraftWorkStatus.value = status; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList(); }
async function changeDraftPage(next) { if (draftListRefreshing.value)
    return; currentDraftPage.value = next; selectedDraftIds.value = []; await refreshDraftList(); }
function toggleDraftSelection(draftId) {
    if (selectedDraftIds.value.includes(draftId)) {
        selectedDraftIds.value = selectedDraftIds.value.filter(id => id !== draftId);
        return;
    }
    if (selectedDraftIds.value.length >= MAX_DRAFT_BATCH_SIZE) {
        showToast(`一次最多选择 ${MAX_DRAFT_BATCH_SIZE} 条商品草稿`);
        return;
    }
    selectedDraftIds.value = [...selectedDraftIds.value, draftId];
}
function togglePagedDrafts() {
    const pageIds = pagedDrafts.value.map(draft => draft.id);
    if (allPagedDraftsSelected.value) {
        selectedDraftIds.value = selectedDraftIds.value.filter(id => !pageIds.includes(id));
        return;
    }
    const remaining = MAX_DRAFT_BATCH_SIZE - selectedDraftIds.value.length;
    const candidates = pageIds.filter(id => !selectedDraftIds.value.includes(id));
    const additions = candidates.slice(0, remaining);
    selectedDraftIds.value = [...selectedDraftIds.value, ...additions];
    if (additions.length < candidates.length) {
        showToast(`一次最多选择 ${MAX_DRAFT_BATCH_SIZE} 条商品草稿`);
    }
}
async function changeDraftTemplateFilter() { if (draftListRefreshing.value)
    return; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList(); }
async function changeDraftCreatorFilter() { if (draftListRefreshing.value)
    return; currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList(); }
async function refreshDraftList() {
    try {
        draftListRefreshing.value = true;
        const { data } = await api.get('/drafts', { headers: headers.value, params: { creator_id: draftCreatorFilterId.value, template_id: draftTemplateFilterId.value, tab: activeDraftTab.value, work_status: activeDraftWorkStatus.value, page: currentDraftPage.value, page_size: draftPageSize.value } });
        drafts.value = data.items;
        draftTotal.value = data.total;
        draftTabCounts.value = data.tab_counts;
        draftWorkStatusCounts.value = data.work_status_counts;
        selectedDraftIds.value = selectedDraftIds.value.filter(id => data.items.some((draft) => draft.id === id));
    }
    catch (e) {
        showToast(e.response?.data?.detail || '刷新商品草稿失败');
    }
    finally {
        draftListRefreshing.value = false;
    }
}
function draftWorkSummary(draft) { return draft.display_tab === 'carousel_pending' ? draft.carousel_task_summary : draft.main_image_task_summary; }
async function dispatchSelectedDrafts(targetStage) {
    if (!batchDispatchEligible.value) {
        showToast('仅可分发待处理状态的商品草稿');
        return;
    }
    const targetLabel = draftStatusLabels[targetStage];
    try {
        dispatchingDraftStage.value = targetStage;
        const { data } = await api.post('/drafts/dispatch', { draft_ids: selectedDraftIds.value, target_stage: targetStage }, { headers: headers.value });
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast(`已将 ${data.total} 条草稿分发至${targetLabel}`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '分发商品草稿失败');
    }
    finally {
        dispatchingDraftStage.value = '';
    }
}
function openBatchCarouselDialog() {
    if (!batchCarouselEligible.value) {
        showToast('仅可选择尚未创建轮播图任务的待制作草稿');
        return;
    }
    const defaultProvider = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || '';
    batchCarouselParams.value = { prompt: carouselParams.value.prompt || '保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图', provider: defaultProvider, ratio: carouselParams.value.ratio, quality: carouselParams.value.quality };
    batchCarouselSelections.value = Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, (draft.sku_items || []).map((item) => item.sku).filter(Boolean)]));
    showBatchCarouselDialog.value = true;
}
function toggleBatchCarouselSku(draftId, sku) {
    const selected = batchCarouselSelections.value[draftId] || [];
    batchCarouselSelections.value = { ...batchCarouselSelections.value, [draftId]: selected.includes(sku) ? selected.filter(item => item !== sku) : [...selected, sku] };
}
function uniqueMainReferenceItems(items) {
    const seen = new Set();
    return items.filter(item => { const url = String(item?.image_url || '').trim(); if (!url || seen.has(url))
        return false; seen.add(url); return true; });
}
function mainCarouselItems(draft) { return uniqueMainReferenceItems((draft?.carousel_items || []).filter((item) => item && item.source_type !== 'sku' && item.source_type !== 'main_image')); }
function mainSkuItems(draft) { return uniqueMainReferenceItems(draft?.sku_items || []); }
function batchMainImageEffectiveMode(draft) { return batchMainImageReferenceMode.value === 'random_carousel' && !mainCarouselItems(draft).length ? 'random_sku' : batchMainImageReferenceMode.value; }
function batchMainImageReferenceItems(draft) { return batchMainImageEffectiveMode(draft) === 'random_sku' ? mainSkuItems(draft) : mainCarouselItems(draft); }
function openBatchMainImageDialog() {
    if (!batchMainImageEligible.value) {
        showToast('仅可选择尚未创建首图任务的待制作主图草稿');
        return;
    }
    const defaultProvider = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || '';
    batchMainImageParams.value = { prompt: mainParams.value.prompt || '以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然，保持款式与颜色准确', provider: defaultProvider, ratio: mainParams.value.ratio, quality: mainParams.value.quality };
    batchMainImageReferenceMode.value = 'random_carousel';
    batchMainImageSelections.value = Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, []]));
    showBatchMainImageDialog.value = true;
}
function toggleBatchMainImageReference(draftId, url) {
    const selected = batchMainImageSelections.value[draftId] || [];
    batchMainImageSelections.value = { ...batchMainImageSelections.value, [draftId]: selected.includes(url) ? selected.filter(item => item !== url) : [...selected, url].slice(0, 9) };
}
function batchReviewTasks(draft) { return (draft.tasks || []).filter((task) => task.result_urls?.length); }
function batchReviewPendingTasks(draft) { return batchReviewTasks(draft).filter((task) => task.status === 'awaiting_selection'); }
function batchReviewSelectedCount(draft) { return batchReviewTasks(draft).filter((task) => (batchImageReviewSelections.value[task.id] || []).length).length; }
function batchReviewTotalTasks() { return batchImageReviewDrafts.value.reduce((total, draft) => total + batchReviewTasks(draft).length, 0); }
function batchReviewChosenTasks() { return Object.values(batchImageReviewSelections.value).filter(urls => urls.length).length; }
function toggleBatchReviewResult(task, url) {
    if (task.status !== 'awaiting_selection')
        return;
    const selected = batchImageReviewSelections.value[task.id] || [];
    const next = batchImageReviewType.value === 'main_image'
        ? (selected.includes(url) ? [] : [url])
        : (selected.includes(url) ? selected.filter(item => item !== url) : [...selected, url]);
    batchImageReviewSelections.value = { ...batchImageReviewSelections.value, [task.id]: next };
}
function selectAllBatchReviewTasks(draft) {
    const targets = draft ? [draft] : batchImageReviewDrafts.value;
    const next = { ...batchImageReviewSelections.value };
    for (const item of targets)
        for (const task of batchReviewPendingTasks(item))
            next[task.id] = batchImageReviewType.value === 'main_image' ? [task.result_urls[0]] : [...task.result_urls];
    batchImageReviewSelections.value = next;
}
function clearBatchReviewDraft(draft) {
    const next = { ...batchImageReviewSelections.value };
    for (const task of batchReviewPendingTasks(draft))
        next[task.id] = [];
    batchImageReviewSelections.value = next;
}
async function openBatchImageReview(type) {
    const eligible = type === 'carousel' ? batchCarouselReviewEligible.value : batchMainImageReviewEligible.value;
    if (!eligible) {
        showToast(`请选择同处于待审核状态的${type === 'carousel' ? '轮播图' : '首图'}草稿`);
        return;
    }
    batchImageReviewType.value = type;
    batchImageReviewDrafts.value = [];
    batchImageReviewSelections.value = {};
    batchCarouselReviewNextStage.value = 'main_image_pending';
    showBatchImageReviewDialog.value = true;
    try {
        batchImageReviewLoading.value = true;
        const { data } = await api.get('/drafts/batch-image-review', { headers: headers.value, params: { draft_ids: selectedDraftIds.value, task_type: type }, paramsSerializer: { indexes: null } });
        batchImageReviewDrafts.value = data.items || [];
        const adopted = {};
        for (const draft of batchImageReviewDrafts.value)
            for (const task of batchReviewTasks(draft)) {
                const adoptedUrls = (draft.carousel_items || []).filter((item) => item.task_id === task.id).map((item) => item.image_url);
                adopted[task.id] = adoptedUrls.length ? adoptedUrls : (task.selected_result_url ? [task.selected_result_url] : []);
            }
        batchImageReviewSelections.value = adopted;
    }
    catch (e) {
        showToast(e.response?.data?.detail || '加载批量审核候选图失败');
        showBatchImageReviewDialog.value = false;
    }
    finally {
        batchImageReviewLoading.value = false;
    }
}
async function confirmBatchImageReview() {
    const selections = batchImageReviewDrafts.value.flatMap(draft => batchReviewTasks(draft).flatMap((task) => {
        const result_urls = batchImageReviewSelections.value[task.id] || [];
        return result_urls.length ? [{ draft_id: draft.id, task_id: task.id, result_urls }] : [];
    }));
    if (!selections.length) {
        showToast('请至少选择一张候选图后再确认');
        return;
    }
    try {
        batchImageReviewSaving.value = true;
        const { data } = await api.post('/drafts/batch-image-review/confirm', { task_type: batchImageReviewType.value, selections, ...(batchImageReviewType.value === 'carousel' ? { next_stage: batchCarouselReviewNextStage.value } : {}) }, { headers: headers.value });
        showBatchImageReviewDialog.value = false;
        selectedDraftIds.value = [];
        await refreshDraftList();
        const stageLabel = batchImageReviewType.value === 'carousel' ? (batchCarouselReviewNextStage.value === 'ready_to_publish' ? '待发布' : '首图创作') : '待发布';
        showToast(`已确认 ${data.reviewed_tasks} 个任务；${data.advanced_drafts} 条草稿进入${stageLabel}`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量确认图片失败');
    }
    finally {
        batchImageReviewSaving.value = false;
    }
}
async function createBatchCarouselTasks() {
    if (!batchCarouselParams.value.prompt.trim()) {
        showToast('请填写轮播图的创作要求');
        return;
    }
    const batchDrafts = selectedDrafts.value.map(draft => ({ draft_id: draft.id, source_skus: batchCarouselSelections.value[draft.id] || [] }));
    if (batchDrafts.some(item => !item.source_skus.length)) {
        showToast('每个草稿至少选择一张 SKU 图');
        return;
    }
    try {
        batchCarouselSaving.value = true;
        const { data } = await api.post('/drafts/batch-carousel-tasks', { drafts: batchDrafts, provider: batchCarouselParams.value.provider, ratio: batchCarouselParams.value.ratio, quality: providerUsesAutoQuality(batchCarouselParams.value.provider) ? 'auto' : batchCarouselParams.value.quality, creative_requirement: batchCarouselParams.value.prompt.trim() }, { headers: headers.value });
        showBatchCarouselDialog.value = false;
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast(`已为 ${data.draft_total} 条草稿创建 ${data.total} 条轮播图任务`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量创建轮播图任务失败');
    }
    finally {
        batchCarouselSaving.value = false;
    }
}
async function createBatchMainImageTasks() {
    if (!batchMainImageParams.value.prompt.trim()) {
        showToast('请填写首图的创作要求');
        return;
    }
    const batchDrafts = selectedDrafts.value.map(draft => ({ draft_id: draft.id, reference_urls: batchMainImageReferenceMode.value === 'manual' ? [...new Set(batchMainImageSelections.value[draft.id] || [])] : [] }));
    if (batchMainImageReferenceMode.value === 'manual' && batchDrafts.some(item => !item.reference_urls.length)) {
        showToast('每个草稿至少选择一张参考图');
        return;
    }
    if (batchMainImageReferenceMode.value !== 'manual' && selectedDrafts.value.some(draft => !batchMainImageReferenceItems(draft).length)) {
        showToast('所选草稿缺少可用于制作首图的轮播图或 SKU 图');
        return;
    }
    try {
        batchMainImageSaving.value = true;
        const { data } = await api.post('/drafts/batch-main-image-tasks', { drafts: batchDrafts, reference_mode: batchMainImageReferenceMode.value, provider: batchMainImageParams.value.provider, ratio: batchMainImageParams.value.ratio, quality: providerUsesAutoQuality(batchMainImageParams.value.provider) ? 'auto' : batchMainImageParams.value.quality, creative_requirement: batchMainImageParams.value.prompt.trim() }, { headers: headers.value });
        showBatchMainImageDialog.value = false;
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast(`已为 ${data.draft_total} 条草稿创建 ${data.total} 条首图任务`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量创建首图任务失败');
    }
    finally {
        batchMainImageSaving.value = false;
    }
}
async function skipDraftCarousel(draft) {
    try {
        skippingCarouselDraftId.value = draft.id;
        await api.post(`/drafts/${draft.id}/skip-carousel`, {}, { headers: headers.value });
        await refreshDraftList();
        showToast('已跳过轮播图制作，请继续制作主图');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '跳过轮播图失败');
    }
    finally {
        skippingCarouselDraftId.value = null;
    }
}
async function batchSkipDraftCarousel() {
    if (!batchCarouselSkipEligible.value) {
        showToast('仅可批量跳过待制作轮播图阶段的草稿');
        return;
    }
    try {
        batchCarouselSkipping.value = true;
        const { data } = await api.post('/drafts/batch-skip-carousel', { draft_ids: selectedDraftIds.value }, { headers: headers.value });
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast(`已跳过 ${data.total} 条草稿的轮播图制作`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量跳过轮播图制作失败');
    }
    finally {
        batchCarouselSkipping.value = false;
    }
}
async function skipDraftMainImage(draft) {
    try {
        skippingMainImageDraftId.value = draft.id;
        await api.post(`/drafts/${draft.id}/skip-main-image`, {}, { headers: headers.value });
        await refreshDraftList();
        showToast('已跳过首图制作，草稿已进入待发布');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '跳过首图制作失败');
    }
    finally {
        skippingMainImageDraftId.value = null;
    }
}
async function batchSkipDraftMainImage() {
    if (!batchMainImageSkipEligible.value) {
        showToast('仅可批量跳过待制作主图阶段的草稿');
        return;
    }
    try {
        batchMainImageSkipping.value = true;
        const { data } = await api.post('/drafts/batch-skip-main-image', { draft_ids: selectedDraftIds.value }, { headers: headers.value });
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast(`已跳过 ${data.total} 条草稿的首图制作`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量跳过首图制作失败');
    }
    finally {
        batchMainImageSkipping.value = false;
    }
}
const taskPageCount = computed(() => Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value)));
const visibleTaskPage = computed(() => Math.min(currentTaskPage.value, taskPageCount.value));
const pagedTasks = computed(() => tasks.value);
const claimablePagedTasks = computed(() => pagedTasks.value.filter(task => ['awaiting_selection', 'completed'].includes(task.status) && (task.result_count || task.result_urls?.length)));
const retryablePagedTasks = computed(() => pagedTasks.value.filter(task => task.status === 'failed'));
const selectablePagedTasks = computed(() => pagedTasks.value.filter(task => task.status === 'failed' || activeTaskType.value === 'sku_image' && claimablePagedTasks.value.some(item => item.id === task.id)));
const selectedClaimableTaskIds = computed(() => claimablePagedTasks.value.filter(task => selectedTaskIds.value.includes(task.id)).map(task => task.id));
const selectedRetryTaskIds = computed(() => retryablePagedTasks.value.filter(task => selectedTaskIds.value.includes(task.id)).map(task => task.id));
const allSelectableTasksSelected = computed(() => Boolean(selectablePagedTasks.value.length) && selectablePagedTasks.value.every(task => selectedTaskIds.value.includes(task.id)));
const someSelectableTasksSelected = computed(() => !allSelectableTasksSelected.value && selectablePagedTasks.value.some(task => selectedTaskIds.value.includes(task.id)));
const groupedBatchClaimItems = computed(() => {
    const groups = new Map();
    batchClaimItems.value.forEach(item => {
        const group = groups.get(item.taskId) || { taskId: item.taskId, taskLabel: item.taskLabel, urls: [] };
        group.urls.push(item.url);
        groups.set(item.taskId, group);
    });
    return [...groups.values()];
});
function syncTaskUrl() { if (page.value !== 'tasks')
    return; void router.replace({ name: 'tasks', query: { task_type: activeTaskType.value, task_page: String(currentTaskPage.value), task_page_size: String(taskPageSize.value), task_creator: taskCreatorFilterId.value ? String(taskCreatorFilterId.value) : 'all', task_status: taskStatusFilter.value, ...(taskCreatedFrom.value ? { task_from: taskCreatedFrom.value } : {}), ...(taskCreatedTo.value ? { task_to: taskCreatedTo.value } : {}), ...(activeTaskType.value === 'sku_image' && taskSkuQuery.value.trim() ? { task_skus: taskSkuQuery.value } : {}), ...(activeTaskType.value === 'sku_image' && taskTemplateFilterId.value ? { task_template: String(taskTemplateFilterId.value) } : {}) } }); }
function clearTaskUrl() { if (route.query.task_type)
    void router.replace({ name: page.value }); }
watch(page, value => {
    value === 'tasks' ? syncTaskUrl() : clearTaskUrl();
    shopError.value = '';
    if (value === 'shops')
        void loadHubUploadTasks();
    if (value === 'miaoshou-collect-box' && activeMiaoshouTab.value === 'collect_box')
        void loadCollectBox();
    if (value === 'product-library') {
        if (user.value?.role !== 'company_admin' && activeProductLibraryTab.value === 'shops')
            activeProductLibraryTab.value = 'products';
        if (user.value?.role === 'company_admin')
            void loadProductLibraryStatisticsStatus();
        if (activeProductLibraryTab.value === 'shops')
            void loadProductLibraryShops();
        else if (activeProductLibraryTab.value === 'products')
            void loadProductLibrary(true);
        else if (activeProductLibraryTab.value === 'stagnant')
            void loadStagnantMaterials();
        else if (activeProductLibraryTab.value === 'new_images')
            void loadNewImages();
        else if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value))
            void loadProductLibraryRankingTab();
    }
    else {
        selectedProductLibraryIds.value = [];
        stagnantRequestId++;
        newImagesRequestId++;
        closeProductLibraryOrders();
    }
});
function applyTaskPage(data) {
    tasks.value = data.items || [];
    taskTotal.value = data.total || 0;
    taskTypeTotals.value = { ...taskTypeTotals.value, ...(data.task_type_counts || {}) };
    taskTypeFilteredTotals.value = { ...taskTypeFilteredTotals.value, [activeTaskType.value]: data.total || 0 };
    taskActiveCount.value = data.active_count || 0;
    taskStatusCounts.value = data.status_counts || {};
    currentTaskPage.value = data.page || 1;
    const selectableIds = new Set(tasks.value.filter(task => taskCanBeSelected(task)).map(task => task.id));
    selectedTaskIds.value = selectedTaskIds.value.filter(id => selectableIds.has(id));
    if (page.value === 'tasks')
        syncTaskUrl();
}
async function changeTaskPageSize() { if (taskListRefreshing.value)
    return; currentTaskPage.value = 1; selectedTaskIds.value = []; syncTaskUrl(); await refreshTaskList(); }
async function changeTaskPage(targetPage) { if (taskListRefreshing.value)
    return; currentTaskPage.value = Math.min(Math.max(1, targetPage), taskPageCount.value); selectedTaskIds.value = []; syncTaskUrl(); await refreshTaskList(); }
function taskQueryParams() { return { page: currentTaskPage.value, page_size: taskPageSize.value, task_type: activeTaskType.value, creator_id: appliedTaskFilters.value.creator_id ?? undefined, status: appliedTaskFilters.value.status || undefined, created_from: appliedTaskFilters.value.created_from || undefined, created_to: appliedTaskFilters.value.created_to || undefined, sku_query: activeTaskType.value === 'sku_image' ? appliedTaskFilters.value.sku_query.trim() || undefined : undefined, template_id: activeTaskType.value === 'sku_image' ? appliedTaskFilters.value.template_id ?? undefined : undefined }; }
function snapshotTaskTab() {
    taskTabStates.value[activeTaskType.value] = { page: currentTaskPage.value, pageSize: taskPageSize.value, creator: taskCreatorFilterId.value, status: taskStatusFilter.value, from: taskCreatedFrom.value, to: taskCreatedTo.value, skuQuery: taskSkuQuery.value, templateId: taskTemplateFilterId.value, applied: { ...appliedTaskFilters.value } };
}
async function switchTaskType(rawType) {
    const type = rawType;
    if (type === activeTaskType.value)
        return;
    snapshotTaskTab();
    activeTaskType.value = type;
    const state = taskTabStates.value[type];
    currentTaskPage.value = state?.page || 1;
    taskPageSize.value = state?.pageSize || 20;
    taskCreatorFilterId.value = state?.creator ?? user.value?.id ?? null;
    taskStatusFilter.value = state?.status ?? 'awaiting_selection';
    taskCreatedFrom.value = state?.from || '';
    taskCreatedTo.value = state?.to || '';
    taskSkuQuery.value = state?.skuQuery || '';
    taskTemplateFilterId.value = state?.templateId ?? null;
    appliedTaskFilters.value = state?.applied || { creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: '', created_to: '', sku_query: '', template_id: null };
    selectedTaskIds.value = [];
    syncTaskUrl();
    await refreshTaskList();
}
function taskTypeLabel(task) { return taskTypeLabels[(task?.task_type || 'sku_image')] || 'SKU图'; }
function toUtcIso(value) { return value ? new Date(value).toISOString() : ''; }
async function searchTasks() {
    if (taskCreatedFrom.value && taskCreatedTo.value && new Date(taskCreatedFrom.value) > new Date(taskCreatedTo.value)) {
        showToast('创建开始时间不能晚于结束时间');
        return;
    }
    appliedTaskFilters.value = { creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: toUtcIso(taskCreatedFrom.value), created_to: toUtcIso(taskCreatedTo.value), sku_query: activeTaskType.value === 'sku_image' ? taskSkuQuery.value : '', template_id: activeTaskType.value === 'sku_image' ? taskTemplateFilterId.value : null };
    currentTaskPage.value = 1;
    selectedTaskIds.value = [];
    syncTaskUrl();
    await refreshTaskList();
}
const materialPageCount = computed(() => Math.max(1, Math.ceil(materialTotal.value / materialPageSize.value)));
const visibleMaterialPage = computed(() => Math.min(currentMaterialPage.value, materialPageCount.value));
function applyMaterialPage(data) { materialAssets.value = data.items || []; materialTotal.value = data.total || 0; currentMaterialPage.value = data.page || 1; }
async function changeMaterialPageSize() { if (materialListRefreshing.value)
    return; currentMaterialPage.value = 1; await refreshMaterialList(); }
async function changeMaterialPage(targetPage) { if (materialListRefreshing.value)
    return; currentMaterialPage.value = Math.min(Math.max(1, targetPage), materialPageCount.value); await refreshMaterialList(); }
async function changeMaterialFilter() { if (materialListRefreshing.value)
    return; currentMaterialPage.value = 1; await refreshMaterialList(); }
async function changeMaterialUsageTab(tab) { if (activeMaterialUsageTab.value === tab || materialListRefreshing.value)
    return; activeMaterialUsageTab.value = tab; currentMaterialPage.value = 1; selectedMaterialAssetIds.value = []; await refreshMaterialList(); }
async function refreshMaterialList() {
    try {
        materialListRefreshing.value = true;
        selectedMaterialAssetIds.value = [];
        const { data } = await api.get('/material-assets', { headers: headers.value, params: { page: currentMaterialPage.value, page_size: materialPageSize.value, creator_id: materialCreatorFilterId.value, template_id: materialTemplateFilterId.value, usage_status: activeMaterialUsageTab.value } });
        applyMaterialPage(data);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '刷新素材列表失败');
    }
    finally {
        materialListRefreshing.value = false;
    }
}
const collectBoxPageCount = computed(() => Math.max(1, Math.ceil(collectBoxTotal.value / collectBoxPageSize.value)));
function changeMiaoshouTab(tab) {
    if (activeMiaoshouTab.value === tab)
        return;
    activeMiaoshouTab.value = tab;
    shopError.value = '';
    if (tab === 'collect_box')
        void loadCollectBox();
}
async function loadCollectBox() {
    try {
        collectBoxLoading.value = true;
        const { data } = await api.get('/miaoshou/collect-box', { headers: headers.value, params: {
                query: collectBoxQuery.value.trim(),
                page: collectBoxPage.value, page_size: collectBoxPageSize.value,
            } });
        collectBoxItems.value = data.items || [];
        collectBoxTotal.value = data.total || 0;
        collectBoxConfigured.value = !!data.configured;
        collectBoxLastSyncedAt.value = data.last_synced_at || null;
        collectBoxInitialSyncedAt.value = data.initial_synced_at || null;
    }
    catch (e) {
        showToast(e.response?.data?.detail || '加载妙手采集箱失败');
    }
    finally {
        collectBoxLoading.value = false;
    }
}
function changeCollectBoxFilters() { collectBoxPage.value = 1; void loadCollectBox(); }
function changeCollectBoxPage(page) { if (page < 1 || page > collectBoxPageCount.value || collectBoxLoading.value)
    return; collectBoxPage.value = page; void loadCollectBox(); }
const productLibraryPageCount = computed(() => Math.max(1, Math.ceil(productLibraryTotal.value / productLibraryPageSize.value)));
const productLibraryRankingPageCount = computed(() => Math.max(1, Math.ceil(productLibraryRankingTotal.value / productLibraryRankingPageSize.value)));
const stagnantPageCount = computed(() => Math.max(1, Math.ceil(stagnantTotal.value / stagnantPageSize.value)));
const newImagesPageCount = computed(() => Math.max(1, Math.ceil(newImagesTotal.value / newImagesPageSize.value)));
const productLibraryOrderPageCount = computed(() => Math.max(1, Math.ceil(productLibraryOrderTotal.value / productLibraryOrderPageSize.value)));
const selectableProductLibraryItems = computed(() => activeProductLibraryTab.value === 'products' ? productLibraryItems.value : activeProductLibraryTab.value === 'stagnant' ? stagnantMaterials.value : activeProductLibraryTab.value === 'new_images' ? newImages.value : productLibraryRankingItems.value);
const productLibrarySelectionLoading = computed(() => productLibraryLoading.value || productLibraryRankingLoading.value || stagnantLoading.value || newImagesLoading.value);
const draftSelectionAssets = computed(() => libraryDraftMode.value ? libraryDraftSelection.value : selectedMaterialAssets.value);
const draftSelectionTemplateId = computed(() => libraryDraftMode.value ? libraryDraftSelection.value[0]?.template_id : selectedMaterialTemplateId.value);
const allPagedProductsSelected = computed(() => selectableProductLibraryItems.value.length > 0 && selectableProductLibraryItems.value.every(item => selectedProductLibraryIds.value.includes(item.id)));
async function loadProductLibraryShops() {
    if (user.value?.role !== 'company_admin')
        return;
    try {
        productLibraryShopsLoading.value = true;
        const { data } = await api.get('/product-library/shops', { headers: headers.value });
        productLibraryShops.value = data || [];
    }
    catch (e) {
        showProductLibraryErrorToast(e, '加载产品库店铺失败');
    }
    finally {
        productLibraryShopsLoading.value = false;
    }
}
async function assignProductLibraryShop(shop, event) {
    const select = event.target;
    const value = select.value;
    const assigned_user_id = value ? Number(value) : null;
    try {
        productLibraryAssigningId.value = shop.id;
        await api.put(`/product-library/shops/${shop.id}/assignment`, { assigned_user_id }, { headers: headers.value });
        shop.assigned_user_id = assigned_user_id;
        shop.assigned_user_name = members.value.find(member => member.id === assigned_user_id)?.name || null;
        showToast('店铺负责人已更新');
    }
    catch (e) {
        select.value = shop.assigned_user_id == null ? '' : String(shop.assigned_user_id);
        showProductLibraryErrorToast(e, '分配店铺失败');
    }
    finally {
        productLibraryAssigningId.value = null;
    }
}
async function loadProductLibraryRankingTab() {
    try {
        const { data } = await api.get('/product-library/filters', { headers: headers.value });
        productLibraryFilters.value = data;
    }
    catch (e) {
        showProductLibraryErrorToast(e, '加载店铺筛选失败');
    }
    await loadProductLibraryRankings();
}
async function loadProductLibrary(withFilters = false) {
    try {
        productLibraryLoading.value = true;
        const applied = appliedProductLibraryFilters.value;
        const params = { page: productLibraryPage.value, page_size: productLibraryPageSize.value,
            source_ids: applied.sourceIds.length ? applied.sourceIds : undefined, sku: applied.sku || undefined,
            template_id: applied.template && applied.template !== 'unmatched' ? Number(applied.template) : undefined,
            unmatched: applied.template === 'unmatched' ? true : undefined };
        const [list, filters] = await Promise.all([
            api.get('/product-library', { headers: headers.value, params, paramsSerializer: { indexes: null } }),
            withFilters ? api.get('/product-library/filters', { headers: headers.value }) : Promise.resolve(null),
        ]);
        productLibraryItems.value = list.data.items || [];
        productLibraryTotal.value = list.data.total || 0;
        productLibraryBrokenImages.value = [];
        if (filters)
            productLibraryFilters.value = filters.data;
    }
    catch (e) {
        showProductLibraryErrorToast(e, '加载产品库失败');
    }
    finally {
        productLibraryLoading.value = false;
    }
}
function showProductLibraryErrorToast(error, fallback) {
    const detail = error.response?.data?.detail;
    const message = typeof detail === 'string' && detail.trim() ? detail : fallback;
    showToast(message);
    return message;
}
async function loadProductLibraryRankings() {
    selectedProductLibraryIds.value = [];
    if (!productLibraryRankingTabKeys.has(activeProductLibraryTab.value))
        return;
    const requestId = ++productLibraryRankingRequestId;
    const category = activeProductLibraryTab.value;
    const isTop50 = productLibraryTopTabKeys.has(category);
    try {
        productLibraryRankingLoading.value = true;
        productLibraryRankingError.value = '';
        const { data } = await api.get('/product-library/rankings', { headers: headers.value, params: { category, page: isTop50 ? 1 : productLibraryRankingPage.value, page_size: isTop50 ? 50 : productLibraryRankingPageSize.value,
                source_ids: rankingShopFilters.value[category]?.length ? rankingShopFilters.value[category] : undefined }, paramsSerializer: { indexes: null } });
        if (requestId !== productLibraryRankingRequestId)
            return;
        productLibraryRankingItems.value = data.items || [];
        productLibraryRankingTotal.value = data.total || 0;
        productLibraryRankingDate.value = data.snapshot_date || null;
        productLibraryRankingThroughDate.value = data.through_date || null;
        productLibraryBrokenImages.value = [];
    }
    catch (e) {
        if (requestId === productLibraryRankingRequestId)
            productLibraryRankingError.value = showProductLibraryErrorToast(e, '加载榜单失败');
    }
    finally {
        if (requestId === productLibraryRankingRequestId)
            productLibraryRankingLoading.value = false;
    }
}
async function loadStagnantMaterials() {
    selectedProductLibraryIds.value = [];
    const requestId = ++stagnantRequestId;
    try {
        stagnantLoading.value = true;
        stagnantError.value = '';
        const { data } = await api.get('/product-library/stagnant', { headers: headers.value, params: {
                page: stagnantPage.value, page_size: stagnantPageSize.value,
                creator_id: user.value?.role === 'company_admin' ? stagnantCreatorId.value : undefined,
            } });
        if (requestId !== stagnantRequestId)
            return;
        stagnantMaterials.value = data.items || [];
        stagnantTotal.value = data.total || 0;
        stagnantPage.value = data.page || 1;
        productLibraryBrokenImages.value = [];
    }
    catch (e) {
        if (requestId === stagnantRequestId)
            stagnantError.value = showProductLibraryErrorToast(e, '加载滞销素材失败');
    }
    finally {
        if (requestId === stagnantRequestId)
            stagnantLoading.value = false;
    }
}
function changeStagnantCreator() { stagnantPage.value = 1; void loadStagnantMaterials(); }
function changeStagnantPageSize() { stagnantPage.value = 1; void loadStagnantMaterials(); }
function changeStagnantPage(next) {
    if (stagnantLoading.value || next < 1 || next > stagnantPageCount.value)
        return;
    stagnantPage.value = next;
    void loadStagnantMaterials();
}
async function loadNewImages() {
    selectedProductLibraryIds.value = [];
    const requestId = ++newImagesRequestId;
    try {
        newImagesLoading.value = true;
        newImagesError.value = '';
        const { data } = await api.get('/product-library/new-images', { headers: headers.value, params: {
                page: newImagesPage.value, page_size: newImagesPageSize.value,
                creator_id: user.value?.role === 'company_admin' ? newImagesCreatorId.value : undefined,
                usage_status: newImagesUsageStatus.value,
            } });
        if (requestId !== newImagesRequestId)
            return;
        newImages.value = data.items || [];
        newImagesTotal.value = data.total || 0;
        newImagesPage.value = data.page || 1;
        productLibraryBrokenImages.value = [];
    }
    catch (e) {
        if (requestId === newImagesRequestId)
            newImagesError.value = showProductLibraryErrorToast(e, '加载新图失败');
    }
    finally {
        if (requestId === newImagesRequestId)
            newImagesLoading.value = false;
    }
}
function changeNewImagesFilters() { newImagesPage.value = 1; void loadNewImages(); }
function changeNewImagesPageSize() { newImagesPage.value = 1; void loadNewImages(); }
function changeNewImagesPage(next) {
    if (newImagesLoading.value || next < 1 || next > newImagesPageCount.value)
        return;
    newImagesPage.value = next;
    void loadNewImages();
}
function changeProductLibraryRankingPage(next) {
    if (productLibraryTopTabKeys.has(activeProductLibraryTab.value) || productLibraryRankingLoading.value || next < 1 || next > productLibraryRankingPageCount.value)
        return;
    productLibraryRankingPage.value = next;
    void loadProductLibraryRankings();
}
function changeProductLibraryRankingPageSize() {
    if (productLibraryTopTabKeys.has(activeProductLibraryTab.value))
        return;
    productLibraryRankingPage.value = 1;
    void loadProductLibraryRankings();
}
function searchProductLibrary() {
    if (productLibraryLoading.value || productLibraryRankingLoading.value)
        return;
    productLibraryShopFilterDetails.value?.removeAttribute('open');
    if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value)) {
        rankingShopFilters.value[activeProductLibraryTab.value] = [...productLibrarySelectedShopIds.value];
        productLibraryRankingPage.value = 1;
        selectedProductLibraryIds.value = [];
        void loadProductLibraryRankings();
        return;
    }
    appliedProductLibraryFilters.value = {
        sourceIds: [...productLibrarySelectedShopIds.value], template: productLibraryTemplateFilter.value,
        sku: productLibrarySku.value.trim(),
    };
    productLibraryPage.value = 1;
    selectedProductLibraryIds.value = [];
    void loadProductLibrary();
}
function changeProductLibraryPageSize() { productLibraryPage.value = 1; selectedProductLibraryIds.value = []; void loadProductLibrary(); }
function changeProductLibraryTab(tab) {
    if (user.value?.role !== 'company_admin' && tab === 'shops') {
        showToast('当前账号没有此操作权限');
        return;
    }
    if (activeProductLibraryTab.value === tab)
        return;
    activeProductLibraryTab.value = tab;
    productLibrarySelectedShopIds.value = [...(tab === 'products' ? appliedProductLibraryFilters.value.sourceIds : rankingShopFilters.value[tab] || [])];
    productLibraryShopSearch.value = '';
    closeProductLibraryOrders();
    selectedProductLibraryIds.value = [];
    productLibraryRankingRequestId++;
    stagnantRequestId++;
    newImagesRequestId++;
    if (tab === 'shops')
        void loadProductLibraryShops();
    else if (tab === 'products')
        void loadProductLibrary(true);
    else if (tab === 'stagnant') {
        stagnantPage.value = 1;
        void loadStagnantMaterials();
    }
    else if (tab === 'new_images') {
        newImagesPage.value = 1;
        void loadNewImages();
    }
    else if (productLibraryRankingTabKeys.has(tab)) {
        productLibraryRankingPage.value = 1;
        productLibraryRankingItems.value = [];
        productLibraryRankingTotal.value = 0;
        productLibraryRankingDate.value = null;
        void loadProductLibraryRankingTab();
    }
}
function changeProductLibraryPage(next) {
    if (productLibraryLoading.value || next < 1 || next > productLibraryPageCount.value)
        return;
    productLibraryPage.value = next;
    void loadProductLibrary();
}
function openProductLibraryOrders(item) {
    productLibraryOrderProduct.value = { ...item,
        sourceIds: [...(activeProductLibraryTab.value === 'products' ? appliedProductLibraryFilters.value.sourceIds : rankingShopFilters.value[activeProductLibraryTab.value] || [])],
        category: productLibraryRankingTabKeys.has(activeProductLibraryTab.value) ? activeProductLibraryTab.value : undefined,
        snapshotDate: productLibraryRankingTabKeys.has(activeProductLibraryTab.value) ? productLibraryRankingDate.value : undefined,
    };
    productLibraryOrderPage.value = 1;
    productLibraryOrders.value = [];
    productLibraryOrderTotal.value = 0;
    productLibraryOrderCount.value = 0;
    void loadProductLibraryOrders();
}
function closeProductLibraryOrders() {
    productLibraryOrderRequestId++;
    productLibraryOrderProduct.value = null;
    productLibraryOrderLoading.value = false;
}
async function loadProductLibraryOrders() {
    const product = productLibraryOrderProduct.value;
    if (!product)
        return;
    const requestId = ++productLibraryOrderRequestId;
    try {
        productLibraryOrderLoading.value = true;
        productLibraryOrders.value = [];
        const { data } = await api.get(`/product-library/${product.id}/orders`, { headers: headers.value, params: { page: productLibraryOrderPage.value, page_size: productLibraryOrderPageSize.value,
                source_ids: product.sourceIds.length ? product.sourceIds : undefined,
                category: product.category, snapshot_date: product.snapshotDate }, paramsSerializer: { indexes: null } });
        if (requestId !== productLibraryOrderRequestId)
            return;
        productLibraryOrders.value = data.items || [];
        productLibraryOrderTotal.value = data.total || 0;
        productLibraryOrderCount.value = data.order_count || 0;
    }
    catch (e) {
        if (requestId === productLibraryOrderRequestId) {
            showProductLibraryErrorToast(e, '加载订单详情失败');
            closeProductLibraryOrders();
        }
    }
    finally {
        if (requestId === productLibraryOrderRequestId)
            productLibraryOrderLoading.value = false;
    }
}
function changeProductLibraryOrderPageSize() { productLibraryOrderPage.value = 1; void loadProductLibraryOrders(); }
function changeProductLibraryOrderPage(next) {
    if (productLibraryOrderLoading.value || next < 1 || next > productLibraryOrderPageCount.value)
        return;
    productLibraryOrderPage.value = next;
    void loadProductLibraryOrders();
}
function toggleProductLibrarySelection(item) {
    if (productLibrarySelectionLoading.value)
        return;
    if (selectedProductLibraryIds.value.includes(item.id)) {
        selectedProductLibraryIds.value = selectedProductLibraryIds.value.filter(id => id !== item.id);
    }
    else if (selectedProductLibraryIds.value.length >= 100) {
        showToast('一次最多选择 100 条产品');
    }
    else {
        selectedProductLibraryIds.value = [...selectedProductLibraryIds.value, item.id];
    }
}
function togglePagedProducts() {
    if (productLibrarySelectionLoading.value)
        return;
    const ids = selectableProductLibraryItems.value.map(item => item.id);
    if (allPagedProductsSelected.value) {
        selectedProductLibraryIds.value = selectedProductLibraryIds.value.filter(id => !ids.includes(id));
        return;
    }
    const merged = [...new Set([...selectedProductLibraryIds.value, ...ids])];
    if (merged.length > 100) {
        showToast('一次最多选择 100 条产品');
        return;
    }
    selectedProductLibraryIds.value = merged;
}
function openProductLibraryTemplateDialog() {
    if (productLibrarySelectionLoading.value || !selectedProductLibraryIds.value.length || user.value?.role !== 'company_admin' || activeProductLibraryTab.value === 'shops')
        return;
    productLibraryTargetTemplateId.value = null;
    showProductLibraryTemplateDialog.value = true;
}
async function saveProductLibraryTemplate() {
    if (productLibraryTemplateSaving.value || !productLibraryTargetTemplateId.value || !selectedProductLibraryIds.value.length)
        return;
    try {
        productLibraryTemplateSaving.value = true;
        const { data } = await api.post('/product-library/templates/batch', {
            ...(activeProductLibraryTab.value === 'new_images' || activeProductLibraryTab.value === 'stagnant'
                ? { material_asset_ids: selectedProductLibraryIds.value }
                : { product_ids: selectedProductLibraryIds.value }),
            template_id: productLibraryTargetTemplateId.value,
        }, { headers: headers.value });
        showProductLibraryTemplateDialog.value = false;
        selectedProductLibraryIds.value = [];
        await refreshLibraryDraftSource();
        showToast(`已为 ${data.updated} 条数据设置模版：${data.template}`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量设置模版失败');
    }
    finally {
        productLibraryTemplateSaving.value = false;
    }
}
async function downloadProductLibraryTemplate() {
    try {
        productLibraryDownloading.value = true;
        const response = await api.get('/product-library/import-template', { headers: headers.value, responseType: 'blob' });
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = '产品库导入模版.xlsx';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    catch {
        showToast('下载导入模版失败');
    }
    finally {
        productLibraryDownloading.value = false;
    }
}
async function importProductLibrary(event) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file)
        return;
    try {
        productLibraryImporting.value = true;
        const form = new FormData();
        form.append('file', file);
        const { data } = await api.post('/product-library/import', form, { headers: headers.value });
        productLibraryPage.value = 1;
        selectedProductLibraryIds.value = [];
        await loadProductLibrary(true);
        if (activeProductLibraryTab.value === 'shops')
            await loadProductLibraryShops();
        if (activeProductLibraryTab.value === 'stagnant')
            await loadStagnantMaterials();
        showToast(`导入完成：新增 ${data.created_shops} 个店铺、${data.created_products} 个产品、${data.created_orders} 个订单，更新 ${data.updated_products} 个产品`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '导入产品库失败');
    }
    finally {
        productLibraryImporting.value = false;
        input.value = '';
    }
}
async function loadProductLibraryStatisticsStatus() {
    if (!token.value || user.value?.role !== 'company_admin')
        return;
    const currentToken = token.value;
    const currentTaskId = productLibraryStatisticsTask.value?.task_id;
    try {
        const { data } = await api.get('/product-library/rankings/refresh/status', { headers: headers.value });
        if (currentToken !== token.value)
            return;
        if (currentTaskId !== productLibraryStatisticsTask.value?.task_id)
            return;
        const previous = productLibraryStatisticsTask.value;
        productLibraryStatisticsTask.value = data.task;
        if (previous?.task_id === data.task?.task_id && ['queued', 'running'].includes(previous.status) && data.task?.status === 'succeeded') {
            if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value))
                await loadProductLibraryRankings();
            showToast(`数据统计完成：截至 ${data.task.through_date}`);
        }
        if (previous?.task_id === data.task?.task_id && ['queued', 'running'].includes(previous.status) && data.task?.status === 'failed')
            showToast('数据统计失败，请重试');
    }
    catch { /* 轮询失败时保留当前状态，下次继续查询。 */ }
}
async function runProductLibraryStatistics() {
    if (user.value?.role !== 'company_admin' || productLibraryStatisticsSubmitting.value || productLibraryImporting.value)
        return;
    try {
        productLibraryStatisticsSubmitting.value = true;
        const { data } = await api.post('/product-library/rankings/refresh', null, { headers: headers.value });
        productLibraryStatisticsTask.value = data.task;
        showToast(data.message || (data.existing ? '已有统计任务正在执行' : '统计任务已提交'));
        if (data.task?.status === 'succeeded' && productLibraryRankingTabKeys.has(activeProductLibraryTab.value))
            await loadProductLibraryRankings();
    }
    catch (e) {
        showToast(e.response?.data?.detail || '数据统计失败，请重试');
    }
    finally {
        productLibraryStatisticsSubmitting.value = false;
    }
}
// 后端统一返回 Unix 毫秒时间戳；所有日期时间固定按 UTC+8 展示。
const nativeToLocaleString = Date.prototype.toLocaleString;
const nativeToLocaleDateString = Date.prototype.toLocaleDateString;
Date.prototype.toLocaleString = function (...args) {
    const [locales, options] = args;
    return nativeToLocaleString.call(this, locales ?? 'zh-CN', { ...options, timeZone: 'Asia/Shanghai' });
};
Date.prototype.toLocaleDateString = function (...args) {
    const [locales, options] = args;
    return nativeToLocaleDateString.call(this, locales ?? 'zh-CN', { ...options, timeZone: 'Asia/Shanghai' });
};
async function refresh() {
    const h = { headers: headers.value };
    const me = await api.get('/me', h);
    user.value = me.data.user;
    company.value = me.data.company;
    collectBoxConfigured.value = !!company.value?.miaoshou_configured;
    if (user.value.role !== 'company_admin')
        activeMiaoshouTab.value = 'collect_box';
    if (route.meta.requiresCompanyAdmin && user.value.role !== 'company_admin') {
        await router.replace({ name: 'dashboard' });
        showToast('当前账号没有访问该管理页面的权限');
    }
    if (!creatorFiltersInitialized.value) {
        if (!initialTaskParams.has('task_creator'))
            taskCreatorFilterId.value = user.value.id;
        appliedTaskFilters.value.creator_id = taskCreatorFilterId.value;
        materialCreatorFilterId.value = user.value.id;
        draftCreatorFilterId.value = user.value.id;
        creatorFiltersInitialized.value = true;
    }
    const [s, t, g, task, material, d, providers, catalogs] = await Promise.all([api.get('/shops', h), api.get('/templates', h), api.get('/template-groups', h), api.get('/tasks', { ...h, params: taskQueryParams() }), api.get('/material-assets', { ...h, params: { page: currentMaterialPage.value, page_size: materialPageSize.value, creator_id: materialCreatorFilterId.value, template_id: materialTemplateFilterId.value, usage_status: activeMaterialUsageTab.value } }), api.get('/drafts', { ...h, params: { creator_id: draftCreatorFilterId.value, template_id: draftTemplateFilterId.value, tab: activeDraftTab.value, work_status: activeDraftWorkStatus.value, page: currentDraftPage.value, page_size: draftPageSize.value } }), api.get('/ai-providers', h), api.get('/category-catalogs', h)]);
    shops.value = s.data;
    templates.value = t.data;
    templateGroups.value = g.data;
    applyTaskPage(task.data);
    applyMaterialPage(material.data);
    drafts.value = d.data.items;
    draftTotal.value = d.data.total;
    draftTabCounts.value = d.data.tab_counts;
    draftWorkStatusCounts.value = d.data.work_status_counts;
    aiProviders.value = providers.data;
    tiktokCatalogs.value = catalogs.data;
    // 后台停用当前所选模型后，刷新时立即切换到仍启用的默认模型，避免提交已停用的值。
    if (!availableAiProviders.value.some(item => item.provider === creativeProvider.value)) {
        creativeProvider.value = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || '';
    }
    if (user.value.role === 'company_admin') {
        const [companyMembers, companyGroups, companyShops] = await Promise.all([api.get('/members', h), api.get('/operator-groups', h), api.get('/shops/manage', h)]);
        members.value = companyMembers.data;
        operatorGroups.value = companyGroups.data;
        managedShops.value = companyShops.data;
    }
    else {
        members.value = [];
        operatorGroups.value = [];
        managedShops.value = [];
    }
    if (!selectedTemplateId.value && templates.value[0])
        selectedTemplateId.value = templates.value[0].id;
    if (selectedTemplateId.value)
        await loadMyTemplateResources(false);
    if (page.value === 'product-library') {
        if (user.value.role !== 'company_admin' && activeProductLibraryTab.value === 'shops')
            activeProductLibraryTab.value = 'products';
        if (user.value.role === 'company_admin')
            void loadProductLibraryStatisticsStatus();
        if (activeProductLibraryTab.value === 'shops')
            await loadProductLibraryShops();
        else if (activeProductLibraryTab.value === 'products')
            await loadProductLibrary(true);
        else if (activeProductLibraryTab.value === 'stagnant')
            await loadStagnantMaterials();
        else if (activeProductLibraryTab.value === 'new_images')
            await loadNewImages();
        else if (productLibraryRankingTabKeys.has(activeProductLibraryTab.value))
            await loadProductLibraryRankingTab();
    }
    if (page.value === 'miaoshou-collect-box' && activeMiaoshouTab.value === 'collect_box')
        await loadCollectBox();
    if (page.value === 'shops')
        await loadHubUploadTasks();
    if (hubAgentPairingCode.value) {
        try {
            const { data } = await api.post('/hub-agent/pairings/complete', { code: hubAgentPairingCode.value }, h);
            if (data.status === 'completed') {
                hubAgentPairingCode.value = '';
                const url = new URL(location.href);
                url.searchParams.delete('hub_agent_pair');
                history.replaceState({}, '', url);
                showToast(`本机执行器 ${data.agent_name || ''} 已授权`);
            }
        }
        catch (e) {
            showToast(e.response?.data?.detail || '本机执行器配对失败');
        }
    }
}
async function login() {
    loading.value = true;
    error.value = '';
    try {
        const { data } = await api.post('/auth/login', { email: email.value, password: password.value });
        token.value = data.access_token;
        localStorage.setItem('haitoro_token', token.value);
        await refresh();
    }
    catch (e) {
        const detail = e.response?.data?.detail;
        error.value = typeof detail === 'string' && detail.trim() ? detail : '登录失败，请检查账号密码';
    }
    finally {
        loading.value = false;
    }
}
function onCreativeAssetChange(event) {
    if (creativeUploading.value) {
        showToast('图片上传处理中，请等待本轮上传结束');
        event.target.value = '';
        return;
    }
    const files = Array.from(event.target.files || []);
    const available = 500 - creativeAssets.value.length;
    const supported = files.filter(file => ALLOWED_IMAGE_TYPES.includes(file.type) && file.size > 0 && file.size <= MAX_IMAGE_BYTES);
    supported.slice(0, available).forEach(file => creativeAssets.value.push({ id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`, file, preview: URL.createObjectURL(file) }));
    if (files.length <= available)
        creativeAssetError.value = '';
    if (supported.length !== files.length)
        creativeAssetError.value = '仅支持 JPG、PNG、WebP，且单张不能超过 3MB。';
    if (files.length > available)
        creativeAssetError.value = '单次印花贴合最多支持 500 张图片。';
    event.target.value = '';
}
function removeCreativeAsset(id) { if (creativeUploading.value) {
    showToast('图片上传处理中，暂时不能删除素材');
    return;
} const asset = creativeAssets.value.find(item => item.id === id); if (asset)
    URL.revokeObjectURL(asset.preview); creativeAssets.value = creativeAssets.value.filter(item => item.id !== id); }
function clearCreativeAssets() { if (creativeUploading.value) {
    showToast('图片上传处理中，暂时不能清空素材');
    return;
} creativeAssets.value.forEach(item => URL.revokeObjectURL(item.preview)); creativeAssets.value = []; showCreativeAssetsDialog.value = false; }
async function uploadCreativeAssets() {
    // 固定本轮素材快照；任一 worker 失败后仍等待其他 worker 收尾，避免下一次提交与残留上传重叠。
    const assets = [...creativeAssets.value];
    const urls = Array(assets.length);
    let cursor = 0;
    creativeUploadedCount.value = assets.filter(asset => asset.uploadedUrl).length;
    const worker = async () => {
        while (true) {
            const index = cursor++;
            if (index >= assets.length)
                return;
            const asset = assets[index];
            if (asset.uploadedUrl) {
                urls[index] = asset.uploadedUrl;
                continue;
            }
            const { data: signed } = await api.post('/uploads/creative-asset/presign', { content_type: asset.file.type, content_length: asset.file.size }, { headers: headers.value });
            await axios.put(signed.upload_url, asset.file, { headers: { 'Content-Type': asset.file.type } });
            asset.uploadedUrl = signed.url;
            urls[index] = signed.url;
            creativeUploadedCount.value++;
        }
    };
    const workerResults = await Promise.allSettled(Array.from({ length: Math.min(4, assets.length) }, worker));
    const failedWorker = workerResults.find((result) => result.status === 'rejected');
    if (failedWorker)
        throw failedWorker.reason;
    return urls;
}
async function createTask() {
    creativeSubmitError.value = '';
    if (!creativeAssets.value.length) {
        creativeAssetError.value = '请先上传至少一张印花图，再开始印花贴合。';
        return;
    }
    if (!selectedWhiteImageId.value) {
        showToast(personalWhiteImages.value.length ? '请选择产品白底图' : '请先设置该模板的产品白底图');
        return;
    }
    if (!creativeRequirement.value.trim()) {
        showToast('请填写创作要求');
        return;
    }
    if (!selectedTemplateId.value)
        return;
    if (!creativeProvider.value || !availableAiProviders.value.some(item => item.provider === creativeProvider.value)) {
        showToast('暂无可用的 AI 模型，请联系超级管理员在后台启用模型');
        return;
    }
    if (creativeCredentialError.value) {
        creativeSubmitError.value = creativeCredentialError.value;
        showToast(creativeCredentialError.value);
        return;
    }
    try {
        creativeAssetError.value = '';
        creativeUploading.value = true;
        const print_urls = await uploadCreativeAssets();
        const { data } = await api.post('/tasks', { template_id: selectedTemplateId.value, white_image_id: selectedWhiteImageId.value, provider: creativeProvider.value, ratio: creativeRatio.value, quality: providerUsesAutoQuality(creativeProvider.value) ? 'auto' : creativeQuality.value, print_url: print_urls[0], print_urls, creative_requirement: creativeRequirement.value.trim() }, { headers: headers.value });
        activeTaskType.value = 'sku_image';
        currentTaskPage.value = 1;
        const taskUrl = new URL(location.href);
        taskUrl.searchParams.set('task_type', 'sku_image');
        history.replaceState({}, '', taskUrl);
        await refresh();
        page.value = 'tasks';
        showToast(`已创建 ${data.total} 条任务，共 ${print_urls.length} 张印花`);
    }
    catch (e) {
        const reason = e.response?.data?.detail || '创建 AI 任务失败';
        creativeSubmitError.value = reason;
        showToast(reason);
    }
    finally {
        creativeUploading.value = false;
    }
}
async function createGroup() { if (!newGroupName.value.trim())
    return; try {
    await api.post('/template-groups', { name: newGroupName.value.trim() }, { headers: headers.value });
    newGroupName.value = '';
    showGroupDialog.value = false;
    await refresh();
}
catch (e) {
    error.value = e.response?.data?.detail || '创建分类失败';
} }
async function deleteTemplateGroup(group) { if (!templateGroupIsEmpty(group.id))
    return; if (!confirm(`确定删除空模板分类「${group.name}」吗？`))
    return; try {
    await api.delete(`/template-groups/${group.id}`, { headers: headers.value });
    if (activeGroupId.value === group.id)
        activeGroupId.value = null;
    await refresh();
    showToast('模板分类已删除');
}
catch (e) {
    showToast(e.response?.data?.detail || '删除模板分类失败');
} }
function openTemplateDialog(template) { editingTemplate.value = template || null; templateFormTab.value = 'basic'; newTemplateName.value = template?.name || ''; newTemplateDescription.value = template?.description || ''; newTemplateTitleTemplate.value = template?.title_template || ''; newTemplateProductDescription.value = template?.product_description || ''; newTemplateSizeChart.value = null; newTemplateSizeChartPreview.value = imageUrl(template?.size_chart_url); newTemplateGroupId.value = template?.group_id || null; newTemplateImage.value = null; newTemplateImagePreview.value = imageUrl(template?.cover_url); newPackageWeight.value = template?.package_weight ?? defaultPackageLogistics.weight; newPackageLength.value = template?.package_length ?? defaultPackageLogistics.length; newPackageWidth.value = template?.package_width ?? defaultPackageLogistics.width; newPackageHeight.value = template?.package_height ?? defaultPackageLogistics.height; newSkuSizeOptions.value = template?.sku_specifications?.size?.options || [...defaultSkuSizes]; newTemplateAiPrompts.value = (template?.ai_prompts || []).map((item) => ({ name: item?.name || '', content: item?.content || '' })); showTemplateDialog.value = true; }
function addSkuSize() { newSkuSizeOptions.value.push(''); }
function addTemplateAiPrompt() { newTemplateAiPrompts.value.push({ name: '', content: '' }); }
function removeTemplateAiPrompt(index) { newTemplateAiPrompts.value.splice(index, 1); }
function selectedTemplateAiPrompts() { return (selectedTemplate.value?.ai_prompts || []).filter((item) => item?.name && item?.content); }
function applyTemplateAiPrompt() {
    if (!creativePromptIndex.value)
        return;
    const [source, identifier] = creativePromptIndex.value.split(':');
    const prompt = source === 'template' ? selectedTemplateAiPrompts()[Number(identifier)] : personalPrompts.value.find(item => item.id === Number(identifier));
    if (prompt)
        creativeRequirement.value = prompt.content;
}
async function loadMyTemplateResources(preserveSelection = true) {
    if (!selectedTemplateId.value || !user.value) {
        personalWhiteImages.value = [];
        personalPrompts.value = [];
        selectedWhiteImageId.value = null;
        return;
    }
    try {
        personalResourcesLoading.value = true;
        const { data } = await api.get('/user-template-resources', { headers: headers.value, params: { template_id: selectedTemplateId.value } });
        personalWhiteImages.value = data.white_images || [];
        personalPrompts.value = data.prompts || [];
        if (!preserveSelection || !personalWhiteImages.value.some(item => item.id === selectedWhiteImageId.value))
            selectedWhiteImageId.value = null;
    }
    catch (e) {
        showToast(e.response?.data?.detail || '加载个人模板资源失败');
    }
    finally {
        personalResourcesLoading.value = false;
    }
}
async function onCreativeTemplateChange() { selectedWhiteImageId.value = null; creativePromptIndex.value = ''; creativeRequirement.value = ''; await loadMyTemplateResources(false); }
async function loadManagedTemplateResources() {
    if (!managedResourceUserId.value)
        return;
    try {
        const { data } = await api.get('/user-template-resources', { headers: headers.value, params: { user_id: managedResourceUserId.value } });
        managedWhiteImages.value = data.white_images || [];
        managedPrompts.value = data.prompts || [];
    }
    catch (e) {
        showToast(e.response?.data?.detail || '加载员工模板资源失败');
    }
}
async function openPersonalResourcesDialog(tab = 'white-images') {
    personalResourceTab.value = tab;
    managedResourceUserId.value = user.value.id;
    resetWhiteImageForm();
    resetPersonalPromptForm();
    showPersonalResourcesDialog.value = true;
    await loadManagedTemplateResources();
}
async function loadTeamTemplateResources() {
    if (!teamResourceUserId.value) {
        teamWhiteImages.value = [];
        teamPrompts.value = [];
        return;
    }
    const userId = teamResourceUserId.value, templateId = teamResourceTemplateId.value;
    try {
        teamResourcesLoading.value = true;
        const params = { user_id: userId };
        if (templateId)
            params.template_id = templateId;
        const { data } = await api.get('/user-template-resources', { headers: headers.value, params });
        if (teamResourceUserId.value !== userId || teamResourceTemplateId.value !== templateId)
            return;
        teamWhiteImages.value = data.white_images || [];
        teamPrompts.value = data.prompts || [];
    }
    catch (e) {
        showToast(e.response?.data?.detail || '加载成员自定义内容失败');
    }
    finally {
        teamResourcesLoading.value = false;
    }
}
async function openTeamResourcesDialog() {
    if (user.value?.role !== 'company_admin')
        return;
    teamResourceTab.value = 'white-images';
    teamResourceQuery.value = '';
    teamResourceUserId.value = otherResourceOwners.value[0]?.id || null;
    teamResourceTemplateId.value = null;
    teamWhiteImages.value = [];
    teamPrompts.value = [];
    showTeamResourcesDialog.value = true;
    await loadTeamTemplateResources();
}
function resetWhiteImageForm() { editingWhiteImage.value = null; whiteImageForm.value = { template_id: null, name: '', file: null }; }
function editWhiteImage(item) { editingWhiteImage.value = item; whiteImageForm.value = { template_id: item.template_id, name: item.name, file: null }; }
function validUploadImageFile(file) {
    if (ALLOWED_IMAGE_TYPES.includes(file.type) && file.size > 0 && file.size <= MAX_IMAGE_BYTES)
        return true;
    showToast('仅支持 JPG、PNG、WebP，且单张不能超过 3MB');
    return false;
}
function onWhiteImageFileChange(event) {
    const input = event.target;
    const file = input.files?.[0] || null;
    if (file && !validUploadImageFile(file)) {
        input.value = '';
        return;
    }
    whiteImageForm.value.file = file;
}
async function saveWhiteImage() {
    if (!whiteImageForm.value.template_id) {
        showToast('请先选择产品模板');
        return;
    }
    if (!managedResourceUserId.value || !whiteImageForm.value.name.trim()) {
        showToast('请填写白底图名称');
        return;
    }
    if (!editingWhiteImage.value && !whiteImageForm.value.file) {
        showToast('请上传白底图');
        return;
    }
    try {
        personalResourceSaving.value = true;
        let image_url;
        if (whiteImageForm.value.file)
            image_url = await presignAndUploadImage(whiteImageForm.value.file, 'template-white');
        if (editingWhiteImage.value)
            await api.put(`/user-template-white-images/${editingWhiteImage.value.id}`, { name: whiteImageForm.value.name.trim(), ...(image_url ? { image_url } : {}) }, { headers: headers.value });
        else
            await api.post('/user-template-white-images', { template_id: whiteImageForm.value.template_id, user_id: managedResourceUserId.value, name: whiteImageForm.value.name.trim(), image_url }, { headers: headers.value });
        resetWhiteImageForm();
        await loadManagedTemplateResources();
        if (managedResourceUserId.value === user.value.id)
            await loadMyTemplateResources();
    }
    catch (e) {
        showToast(e.response?.data?.detail || '保存白底图失败');
    }
    finally {
        personalResourceSaving.value = false;
    }
}
async function deleteWhiteImage(item) { if (!confirm(`确定删除白底图「${item.name}」吗？`))
    return; try {
    await api.delete(`/user-template-white-images/${item.id}`, { headers: headers.value });
    await loadManagedTemplateResources();
    if (managedResourceUserId.value === user.value.id)
        await loadMyTemplateResources();
}
catch (e) {
    showToast(e.response?.data?.detail || '删除白底图失败');
} }
function resetPersonalPromptForm() { editingPersonalPrompt.value = null; personalPromptForm.value = { template_id: null, name: '', content: '' }; }
function editPersonalPrompt(item) { editingPersonalPrompt.value = item; personalPromptForm.value = { template_id: item.template_id, name: item.name, content: item.content }; }
function resourceTemplateName(item) { return templates.value.find(template => template.id === item.template_id)?.name || '模板已删除'; }
async function savePersonalPrompt() {
    const name = personalPromptForm.value.name.trim(), content = personalPromptForm.value.content.trim();
    if (!personalPromptForm.value.template_id) {
        showToast('请先选择产品模板');
        return;
    }
    if (!managedResourceUserId.value || !name || !content) {
        showToast('请完整填写名称和创作要求');
        return;
    }
    try {
        personalResourceSaving.value = true;
        if (editingPersonalPrompt.value)
            await api.put(`/user-template-prompts/${editingPersonalPrompt.value.id}`, { name, content }, { headers: headers.value });
        else
            await api.post('/user-template-prompts', { template_id: personalPromptForm.value.template_id, user_id: managedResourceUserId.value, name, content }, { headers: headers.value });
        resetPersonalPromptForm();
        await loadManagedTemplateResources();
        if (managedResourceUserId.value === user.value.id)
            await loadMyTemplateResources();
    }
    catch (e) {
        showToast(e.response?.data?.detail || '保存创作要求失败');
    }
    finally {
        personalResourceSaving.value = false;
    }
}
async function deletePersonalPrompt(item) { if (!confirm(`确定删除创作要求「${item.name}」吗？`))
    return; try {
    await api.delete(`/user-template-prompts/${item.id}`, { headers: headers.value });
    await loadManagedTemplateResources();
    if (managedResourceUserId.value === user.value.id)
        await loadMyTemplateResources();
}
catch (e) {
    showToast(e.response?.data?.detail || '删除创作要求失败');
} }
function onCoverChange(event) { const input = event.target, file = input.files?.[0] || null; if (file && !validUploadImageFile(file)) {
    input.value = '';
    return;
} newTemplateImage.value = file; newTemplateImagePreview.value = file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.cover_url); }
function onSizeChartChange(event) { const input = event.target, file = input.files?.[0] || null; if (file && !validUploadImageFile(file)) {
    input.value = '';
    return;
} newTemplateSizeChart.value = file; newTemplateSizeChartPreview.value = file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.size_chart_url); }
function normalizeTemplateNameForSku() { const name = newTemplateName.value.trim().toUpperCase(); if (!/^[A-Z0-9]{1,5}$/.test(name)) {
    templateFormTab.value = 'basic';
    showToast('模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字');
    throw new Error('invalid template name');
} newTemplateName.value = name; }
async function presignAndUploadImage(file, category) {
    let lastError;
    for (let attempt = 0; attempt <= IMAGE_UPLOAD_RETRY; attempt++) {
        try {
            const { data } = await api.post('/uploads/presign', {
                category, files: [{ content_type: file.type, content_length: file.size }],
            }, { headers: headers.value });
            await axios.put(data[0].upload_url, file, { headers: { 'Content-Type': file.type } });
            return data[0].url;
        }
        catch (e) {
            lastError = e;
        }
    }
    throw lastError;
}
async function uploadCover() { normalizeTemplateNameForSku(); if (!newTemplateImage.value)
    return undefined; return presignAndUploadImage(newTemplateImage.value, 'template'); }
async function uploadSizeChart() { if (!newTemplateSizeChart.value)
    return undefined; return presignAndUploadImage(newTemplateSizeChart.value, 'template-size-chart'); }
function validateNewTemplate() {
    const sizeOptions = newSkuSizeOptions.value.map(value => value.trim()).filter(Boolean);
    const validations = [
        { valid: /^[A-Z0-9]{1,5}$/.test(newTemplateName.value.trim().toUpperCase()), tab: 'basic', message: '模板名称同时作为 SKU 前缀，仅支持 1-5 位字母或数字' },
        { valid: Boolean(newTemplateName.value.trim() && newTemplateImage.value && newTemplateDescription.value.trim() && newTemplateGroupId.value !== null), tab: 'basic', message: '请完整填写模版信息，并上传模板图片和选择模板分类' },
        { valid: Boolean(newTemplateProductDescription.value.trim() && newTemplateSizeChart.value), tab: 'product', message: '请完整填写商品信息，并上传尺码图' },
        { valid: sizeOptions.length > 0 && newSkuSizeOptions.value.every(value => value.trim()), tab: 'product', message: '请完整填写 SKU 尺码' },
        { valid: [newPackageWeight.value, newPackageLength.value, newPackageWidth.value, newPackageHeight.value].every(value => value !== null && value > 0), tab: 'logistics', message: '请完整填写物流信息' },
    ];
    const missing = validations.find(item => !item.valid);
    if (!missing)
        return true;
    templateFormTab.value = missing.tab;
    showToast(missing.message);
    return false;
}
async function createTemplate() { if (!editingTemplate.value && !validateNewTemplate())
    return; if (editingTemplate.value && !newTemplateName.value.trim()) {
    templateFormTab.value = 'basic';
    showToast('请输入模板名称');
    return;
} if (editingTemplate.value && [newPackageWeight.value, newPackageLength.value, newPackageWidth.value, newPackageHeight.value].some(value => value === null || value <= 0)) {
    templateFormTab.value = 'logistics';
    showToast('请完整填写物流信息');
    return;
} const ai_prompts = newTemplateAiPrompts.value.map(item => ({ name: item.name.trim(), content: item.content.trim() })).filter(item => item.name || item.content); if (ai_prompts.some(item => !item.name || !item.content)) {
    templateFormTab.value = 'ai-prompts';
    showToast('请完整填写 AI生成素材提示的名称和内容，或删除空白项');
    return;
} try {
    templateSaving.value = true;
    const [uploadedCoverUrl, uploadedSizeChartUrl] = await Promise.all([uploadCover(), uploadSizeChart()]);
    const cover_url = uploadedCoverUrl ?? editingTemplate.value?.cover_url ?? null;
    const size_chart_url = uploadedSizeChartUrl ?? editingTemplate.value?.size_chart_url ?? null;
    const sizeOptions = newSkuSizeOptions.value.map(value => value.trim()).filter(Boolean);
    const sku_specifications = { size: { name: '尺码', options: sizeOptions } };
    const payload = { name: newTemplateName.value.trim(), description: newTemplateDescription.value.trim() || null, title_template: newTemplateTitleTemplate.value.trim() || null, product_description: newTemplateProductDescription.value.trim() || null, size_chart_url, group_id: newTemplateGroupId.value, cover_url, package_weight: newPackageWeight.value, package_length: newPackageLength.value, package_width: newPackageWidth.value, package_height: newPackageHeight.value, sku_specifications, ai_prompts, color_count: 1, sku_count: Math.max(1, sizeOptions.length) };
    if (editingTemplate.value)
        await api.put(`/templates/${editingTemplate.value.id}`, payload, { headers: headers.value });
    else
        await api.post('/templates', payload, { headers: headers.value });
    showTemplateDialog.value = false;
    await refresh();
}
catch (e) {
    error.value = e.response?.data?.detail || e?.message || '保存模板失败';
}
finally {
    templateSaving.value = false;
} }
async function deleteTemplate(template) { if (!confirm(`确定删除模板「${template.name}」吗？`))
    return; try {
    await api.delete(`/templates/${template.id}`, { headers: headers.value });
    if (selectedTemplateId.value === template.id)
        selectedTemplateId.value = templates.value.find(t => t.id !== template.id)?.id || null;
    await refresh();
}
catch (e) {
    error.value = e.response?.data?.detail || '删除模板失败';
} }
function imageUrl(url) { return url ? (url.startsWith('/') ? `${api.defaults.baseURL}${url}` : url) : ''; }
const taskStatusLabel = { queued: '排队中', running: '处理中', awaiting_selection: '待选图', completed: '已完成', failed: '失败' };
function taskStatusClass(status) { return status === 'awaiting_selection' ? 'purple' : status === 'completed' ? 'blue' : status === 'failed' ? 'orange' : 'purple'; }
async function refreshTaskList() {
    try {
        taskListRefreshing.value = true;
        const { data } = await api.get('/tasks', { headers: headers.value, params: taskQueryParams() });
        applyTaskPage(data);
        if (showTaskDetailDialog.value && viewingTask.value)
            viewingTask.value = (await api.get(`/tasks/${viewingTask.value.id}`, { headers: headers.value })).data;
    }
    catch (e) {
        showToast(e.response?.data?.detail || '刷新任务列表失败');
    }
    finally {
        taskListRefreshing.value = false;
    }
}
async function copyProviderTaskId(task) { if (!task.provider_task_id)
    return; try {
    await navigator.clipboard.writeText(task.provider_task_id);
    showToast('外部任务 ID 已复制');
}
catch {
    showToast('复制失败，请手动复制');
} }
async function openTaskDetail(task) { viewingTask.value = task; showTaskDetailDialog.value = true; taskDetailLoading.value = true; try {
    viewingTask.value = (await api.get(`/tasks/${task.id}`, { headers: headers.value })).data;
}
catch (e) {
    showToast(e.response?.data?.detail || '加载任务详情失败');
}
finally {
    taskDetailLoading.value = false;
} }
function templateCoverUrl(template) { if (template?.cover_url)
    return imageUrl(template.cover_url); return template?.name === '白色 T恤正面' ? '/template-white-tshirt-front.png' : '/template-tshirt.svg'; }
function hasTemplateCover(template) { return Boolean(template?.cover_url || template?.name === '白色 T恤正面'); }
function useTemplate(template) { selectedTemplateId.value = template.id; page.value = 'pod'; }
function toggleMaterialAsset(assetId) { const asset = materialAssets.value.find(item => item.id === assetId); if (!asset?.sku) {
    showToast('历史素材没有 SKU，请重新上传或领取');
    return;
} selectedMaterialAssetIds.value = selectedMaterialAssetIds.value.includes(assetId) ? selectedMaterialAssetIds.value.filter(id => id !== assetId) : [...selectedMaterialAssetIds.value, assetId]; }
function toggleAllCurrentMaterialAssets() { selectedMaterialAssetIds.value = allCurrentMaterialAssetsSelected.value ? [] : filteredMaterialAssets.value.filter(asset => asset.sku).map(asset => asset.id); }
function materialTemplateName(asset) { return templates.value.find(template => template.id === asset.template_id)?.name || '未设置模板'; }
function draftTemplateName(draft) { return templates.value.find(template => template.id === draft.template_id)?.name || '历史模板已删除'; }
function onMaterialDraftTemplateChange() {
    const template = materialDraftTemplate.value;
    materialDraftTitle.value = '';
    materialDraftProductDescription.value = template?.product_description || '';
    materialDraftSizeChartPreview.value = imageUrl(template?.size_chart_url);
}
async function generateMaterialDraftTitle() {
    if (!materialDraftTemplateId.value || !materialDraftAssets.value[0])
        return;
    const firstAsset = materialDraftAssets.value[0], fromLibrary = libraryDraftMode.value;
    try {
        materialDraftTitleGenerating.value = true;
        const { data } = await api.post(libraryDraftMode.value ? '/product-library/generate-draft-title' : `/templates/${materialDraftTemplateId.value}/generate-draft-title`, { ...(libraryDraftMode.value ? librarySource(materialDraftAssets.value[0]) : { image_url: materialDraftAssets.value[0].url }), additional_requirements: materialDraftAdditionalRequirements.value.trim() }, { headers: headers.value });
        if (libraryDraftMode.value !== fromLibrary || materialDraftAssets.value[0]?.id !== firstAsset.id)
            return;
        materialDraftTitle.value = data.title;
        materialDraftTitleEdited.value = true;
    }
    catch (e) {
        showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试');
    }
    finally {
        materialDraftTitleGenerating.value = false;
    }
}
function openMaterialDraftDialog() { libraryDraftMode.value = false; if (!selectedMaterialTemplateId.value) {
    showToast('请选择属于同一产品模板的素材');
    return;
} materialDraftAssets.value = [...selectedMaterialAssets.value]; draggedMaterialDraftAssetId.value = null; materialDraftTemplateId.value = selectedMaterialTemplateId.value; materialDraftTitle.value = ''; materialDraftProductDescription.value = ''; materialDraftSizeChartPreview.value = ''; onMaterialDraftTemplateChange(); showMaterialDraftDialog.value = true; }
function librarySource(asset) { return { source_type: asset.source_type, id: asset.id }; }
function openProductLibraryDraftDialog(batch = false) {
    if (productLibrarySelectionLoading.value)
        return;
    const assets = selectableProductLibraryItems.value.filter(item => selectedProductLibraryIds.value.includes(item.id)).map(item => ({ ...item, url: item.image_url }));
    if (!assets.length)
        return;
    if (assets.some(asset => !asset.url?.trim() || !asset.sku?.trim())) {
        showToast('所选数据缺少图片或 SKU，请修正后再创建');
        return;
    }
    const templateId = assets[0].template_id;
    if (!templateId || !templates.value.some(template => template.id === templateId) || assets.some(asset => asset.template_id !== templateId)) {
        showToast('请先匹配同一有效产品模板，或调整选择');
        return;
    }
    if (!batch && new Set(assets.map(asset => asset.sku.trim())).size !== assets.length) {
        showToast('所选数据包含重复 SKU，请调整选择');
        return;
    }
    if (batch && assets.length < 5) {
        showToast('组合创建至少需要 5 张图片');
        return;
    }
    libraryDraftMode.value = true;
    libraryDraftSelection.value = assets;
    if (batch) {
        if (assets.length < materialBatchGroupSize.value)
            materialBatchGroupSize.value = 5;
        buildMaterialBatchGroups();
        draggedMaterialBatchAsset.value = null;
        showMaterialBatchDraftDialog.value = true;
    }
    else {
        materialDraftAssets.value = [...assets];
        draggedMaterialDraftAssetId.value = null;
        materialDraftTemplateId.value = templateId;
        onMaterialDraftTemplateChange();
        materialDraftTitle.value = assets[0].title || '';
        materialDraftTitleEdited.value = false;
        showMaterialDraftDialog.value = true;
    }
}
async function refreshLibraryDraftSource() {
    selectedProductLibraryIds.value = [];
    if (activeProductLibraryTab.value === 'products')
        await loadProductLibrary();
    else if (activeProductLibraryTab.value === 'stagnant')
        await loadStagnantMaterials();
    else if (activeProductLibraryTab.value === 'new_images')
        await loadNewImages();
    else
        await loadProductLibraryRankings();
}
function startMaterialDraftDrag(event, assetId) {
    draggedMaterialDraftAssetId.value = assetId;
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(assetId));
    }
}
function moveMaterialDraftAsset(assetId, targetId) {
    if (assetId === targetId)
        return;
    const assets = [...materialDraftAssets.value];
    const from = assets.findIndex(asset => asset.id === assetId);
    const to = assets.findIndex(asset => asset.id === targetId);
    if (from < 0 || to < 0)
        return;
    const [asset] = assets.splice(from, 1);
    assets.splice(to, 0, asset);
    materialDraftAssets.value = assets;
    if (libraryDraftMode.value && !materialDraftTitleEdited.value)
        materialDraftTitle.value = assets[0]?.title || '';
}
function dropMaterialDraftAsset(targetId) {
    if (draggedMaterialDraftAssetId.value !== null)
        moveMaterialDraftAsset(draggedMaterialDraftAssetId.value, targetId);
    draggedMaterialDraftAssetId.value = null;
}
async function createDraftFromMaterialAssets() {
    if (materialDraftSaving.value || !materialDraftAssets.value.length)
        return;
    if (!materialDraftTemplateId.value) {
        showToast('请选择产品模板');
        return;
    }
    const title = materialDraftTitle.value.trim();
    if (title.length < 25 || title.length > 255) {
        showToast('商品标题长度须为 25-255 个字符');
        return;
    }
    try {
        materialDraftSaving.value = true;
        await api.post(libraryDraftMode.value ? '/drafts/from-product-library' : '/drafts/from-material-assets', { ...(libraryDraftMode.value ? { sources: materialDraftAssets.value.map(librarySource) } : { material_asset_ids: materialDraftAssets.value.map(asset => asset.id) }), template_id: materialDraftTemplateId.value, title, product_description: materialDraftProductDescription.value.trim() || null }, { headers: headers.value });
        selectedMaterialAssetIds.value = [];
        showMaterialDraftDialog.value = false;
        if (libraryDraftMode.value)
            await refreshLibraryDraftSource();
        await refresh();
        page.value = 'drafts';
        showToast('商品草稿已创建，请在列表中手动发布至妙手');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '创建商品草稿失败，请稍后重试');
    }
    finally {
        materialDraftSaving.value = false;
    }
}
function shuffleAssets(items) {
    const shuffled = [...items];
    for (let index = shuffled.length - 1; index > 0; index--) {
        const target = Math.floor(Math.random() * (index + 1));
        [shuffled[index], shuffled[target]] = [shuffled[target], shuffled[index]];
    }
    return shuffled;
}
function buildMaterialBatchGroups() {
    const assets = materialBatchMode.value === 'random' ? shuffleAssets(draftSelectionAssets.value) : [...draftSelectionAssets.value];
    const completeCount = Math.floor(assets.length / materialBatchGroupSize.value) * materialBatchGroupSize.value;
    materialBatchGroups.value = Array.from({ length: completeCount / materialBatchGroupSize.value }, (_, index) => ({ assets: assets.slice(index * materialBatchGroupSize.value, (index + 1) * materialBatchGroupSize.value), title: libraryDraftMode.value ? assets[index * materialBatchGroupSize.value]?.title || '' : '', generating: false, edited: false, additionalRequirements: '', showAdditionalRequirements: false, showTitleHelp: false }));
}
function openMaterialBatchDraftDialog() {
    libraryDraftMode.value = false;
    if (!canCreateMaterialBatch.value) {
        showToast('请选择至少 5 张属于同一产品模板的素材');
        return;
    }
    buildMaterialBatchGroups();
    draggedMaterialBatchAsset.value = null;
    showMaterialBatchDraftDialog.value = true;
}
function rebuildMaterialBatchGroups() { draggedMaterialBatchAsset.value = null; if (draftSelectionAssets.value.length >= materialBatchGroupSize.value)
    buildMaterialBatchGroups();
else
    materialBatchGroups.value = []; }
function startMaterialBatchDrag(event, groupIndex, assetId) {
    draggedMaterialBatchAsset.value = { groupIndex, assetId };
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(assetId));
    }
}
function moveMaterialBatchAsset(groupIndex, from, to) {
    const group = materialBatchGroups.value[groupIndex];
    if (!group || from < 0 || to < 0 || from >= group.assets.length || to >= group.assets.length || from === to)
        return;
    const assets = [...group.assets];
    const [asset] = assets.splice(from, 1);
    assets.splice(to, 0, asset);
    group.assets = assets;
    if (libraryDraftMode.value && !group.edited)
        group.title = assets[0]?.title || '';
}
function dropMaterialBatchAsset(groupIndex, targetId) {
    const dragged = draggedMaterialBatchAsset.value;
    draggedMaterialBatchAsset.value = null;
    if (!dragged || dragged.groupIndex !== groupIndex)
        return;
    const assets = materialBatchGroups.value[groupIndex]?.assets || [];
    moveMaterialBatchAsset(groupIndex, assets.findIndex(asset => asset.id === dragged.assetId), assets.findIndex(asset => asset.id === targetId));
}
async function generateMaterialBatchTitle(group) {
    if (!draftSelectionTemplateId.value || !group.assets[0])
        return;
    const firstAsset = group.assets[0];
    try {
        group.generating = true;
        const { data } = await api.post(libraryDraftMode.value ? '/product-library/generate-draft-title' : `/templates/${draftSelectionTemplateId.value}/generate-draft-title`, { ...(libraryDraftMode.value ? librarySource(group.assets[0]) : { image_url: group.assets[0].url }), additional_requirements: group.additionalRequirements.trim() }, { headers: headers.value });
        if (group.assets[0]?.id === firstAsset.id) {
            group.title = data.title;
            group.edited = true;
        }
    }
    catch (e) {
        showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试');
    }
    finally {
        group.generating = false;
    }
}
async function createMaterialBatchDrafts() {
    if (materialBatchSaving.value || !draftSelectionTemplateId.value || !materialBatchGroups.value.length)
        return;
    if (libraryDraftMode.value && materialBatchGroups.value.some(group => new Set(group.assets.map(asset => asset.sku.trim())).size !== group.assets.length)) {
        showToast('同一草稿不能包含重复 SKU，请调整组合');
        return;
    }
    if (materialBatchGroups.value.some(group => group.title.trim().length < 25 || group.title.trim().length > 255)) {
        showToast('请为每个组合填写 25-255 个字符的商品标题');
        return;
    }
    try {
        materialBatchSaving.value = true;
        const { data } = await api.post(libraryDraftMode.value ? '/drafts/from-product-library/batch' : '/drafts/from-material-assets/batch', { template_id: draftSelectionTemplateId.value, groups: materialBatchGroups.value.map(group => ({ ...(libraryDraftMode.value ? { sources: group.assets.map(librarySource) } : { material_asset_ids: group.assets.map(asset => asset.id) }), title: group.title.trim() })) }, { headers: headers.value });
        selectedMaterialAssetIds.value = [];
        showMaterialBatchDraftDialog.value = false;
        if (libraryDraftMode.value)
            await refreshLibraryDraftSource();
        await refresh();
        page.value = 'drafts';
        showToast(`已创建 ${data.total} 条商品草稿`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量创建商品草稿失败，请稍后重试');
    }
    finally {
        materialBatchSaving.value = false;
    }
}
function openDraftEditDialog(draft) { editingDraft.value = draft; draftEditTitle.value = draft.title; draftEditProductDescription.value = draft.product_description || ''; draftEditError.value = ''; showDraftEditDialog.value = true; }
// 商品图片已被 AI 生成图覆盖时，回退到轮播图记录里取来源 SKU。
function draftSkuForImage(draft, imageUrl) {
    return draft?.sku_items?.find((item) => item.image_url === imageUrl)?.sku
        || draft?.carousel_items?.find((item) => item.image_url === imageUrl)?.sku
        || '—';
}
// SKU 图＝草稿入库时的原始素材图，按 SKU 去重展示。
const draftEditSkus = computed(() => {
    const seen = new Set();
    return (editingDraft.value?.sku_items || []).filter((item) => {
        if (!item?.sku || !item?.image_url || seen.has(item.sku))
            return false;
        seen.add(item.sku);
        return true;
    });
});
function openImagePreview(url, alt) { previewImageUrl.value = imageUrl(url); previewImageAlt.value = alt; }
function openTemplateCoverPreview(template) { previewImageUrl.value = templateCoverUrl(template); previewImageAlt.value = template.name; }
const imageDraftSkus = computed(() => {
    const seen = new Set();
    const adoptedSourceSkus = new Set((imageDraft.value?.carousel_items || [])
        .filter((item) => item?.source_type === 'carousel' && item?.sku)
        .map((item) => item.sku));
    return (imageDraft.value?.sku_items || []).filter((item) => { if (!item.sku || !item.image_url || seen.has(item.sku) || adoptedSourceSkus.has(item.sku))
        return false; seen.add(item.sku); return true; });
});
function skuFallbackCarouselItems(draft) {
    const seenSkus = new Set(), seenUrls = new Set();
    return (draft?.sku_items || []).filter((item) => {
        if (!item?.sku || !item?.image_url || seenSkus.has(item.sku) || seenUrls.has(item.image_url))
            return false;
        seenSkus.add(item.sku);
        seenUrls.add(item.image_url);
        return true;
    }).slice(0, 9).map((item) => ({ sku: item.sku, image_url: item.image_url, task_id: null, source_type: 'sku' }));
}
const draftFinalImageItems = computed(() => {
    if (!imageDraft.value)
        return [];
    if (stagedFinalImageItems.value !== null)
        return stagedFinalImageItems.value;
    const seen = new Set();
    return (imageDraft.value.carousel_items || []).filter((item) => item?.image_url && !seen.has(item.image_url) && seen.add(item.image_url));
});
const draftImagePreviewUrls = computed(() => draftFinalImageItems.value.map((item) => item.image_url));
const adoptedCarouselItems = computed(() => (imageDraft.value?.carousel_items || []).filter((item) => item?.source_type === 'carousel'));
const mainCarouselReferenceItems = computed(() => mainCarouselItems(imageDraft.value));
const mainSkuReferenceItems = computed(() => mainSkuItems(imageDraft.value));
const mainRandomReferenceItems = computed(() => mainReferenceMode.value === 'random_sku' ? mainSkuReferenceItems.value : mainCarouselReferenceItems.value);
const currentGeneratedMainImage = computed(() => (imageDraft.value?.carousel_items || []).find((item) => item.source_type === 'main_image') || null);
function selectMainReferenceMode(mode) { mainReferenceMode.value = mode === 'random_carousel' && !mainCarouselReferenceItems.value.length ? 'random_sku' : mode; }
function retainValidMainReferences() { const allowed = new Set([...mainCarouselReferenceItems.value, ...mainSkuReferenceItems.value].map(item => item.image_url)); selectedMainReferences.value = selectedMainReferences.value.filter(url => allowed.has(url)); }
function resetFinalImageOrder() { stagedFinalImageItems.value = null; draggedFinalImageUrl.value = ''; }
async function loadImageWorkspace(draftId, tasksOnly = false) {
    if (tasksOnly)
        imageTasksRefreshing.value = true;
    else
        imageWorkspaceLoading.value = true;
    try {
        const workspace = (await api.get(`/drafts/${draftId}/image-workspace`, { headers: headers.value })).data;
        if (tasksOnly && imageDraft.value?.id === draftId) {
            imageDraft.value.carousel_tasks = workspace.carousel_tasks;
            imageDraft.value.main_image_tasks = workspace.main_image_tasks;
        }
        else
            imageDraft.value = workspace;
    }
    finally {
        if (tasksOnly)
            imageTasksRefreshing.value = false;
        else
            imageWorkspaceLoading.value = false;
    }
}
async function openImageWorkspace(draft, mode = 'full', focusMain = false) {
    imageWorkspaceMode.value = mode;
    showDraftImageDialog.value = true;
    imageDraft.value = null;
    selectedImageSkus.value = [];
    selectedMainReferences.value = [];
    mainReferenceMode.value = 'random_carousel';
    carouselConfirmNextStage.value = 'main_image_pending';
    resetFinalImageOrder();
    const defaultImageProvider = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || '';
    carouselParams.value = { prompt: '保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图', provider: defaultImageProvider, ratio: '1:1', quality: '1K' };
    mainParams.value = { prompt: '以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然，保持款式与颜色准确', provider: defaultImageProvider, ratio: '1:1', quality: '1K' };
    try {
        await loadImageWorkspace(draft.id);
        selectMainReferenceMode(mainReferenceMode.value);
        if (focusMain) {
            await nextTick();
            document.getElementById('main-image-workspace-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
    catch (e) {
        showDraftImageDialog.value = false;
        showToast(e.response?.data?.detail || '加载图片制作台失败');
    }
}
function openCarouselImageWorkspace(draft) { return openImageWorkspace(draft, 'carousel'); }
function openFullImageWorkspace(draft, focusMain = false) { return openImageWorkspace(draft, 'full', focusMain); }
function toggleImageSku(sku) {
    selectedImageSkus.value = selectedImageSkus.value.includes(sku) ? selectedImageSkus.value.filter(item => item !== sku) : [...selectedImageSkus.value, sku].slice(0, 9);
}
function toggleMainReference(url) { selectedMainReferences.value = selectedMainReferences.value.includes(url) ? selectedMainReferences.value.filter(item => item !== url) : [...selectedMainReferences.value, url].slice(0, 9); }
async function createDraftImageTasks(type) {
    if (!imageDraft.value)
        return;
    if (type === 'carousel' && !selectedImageSkus.value.length) {
        showToast('请至少选择一个 SKU');
        return;
    }
    if (type === 'main_image')
        selectMainReferenceMode(mainReferenceMode.value);
    if (type === 'main_image' && mainReferenceMode.value !== 'manual' && !mainRandomReferenceItems.value.length) {
        showToast('缺少可用于制作首图的轮播图或 SKU 图');
        return;
    }
    if (type === 'main_image' && mainReferenceMode.value === 'manual' && !selectedMainReferences.value.length) {
        showToast('请手动选择首图参考图');
        return;
    }
    const params = type === 'carousel' ? carouselParams.value : mainParams.value;
    if (!params.prompt.trim()) {
        showToast(type === 'carousel' ? '请填写轮播图的创作要求' : '请填写首图的创作要求');
        return;
    }
    try {
        imageTaskCreatingType.value = type;
        const mainReferenceUrls = mainReferenceMode.value === 'manual' ? [...new Set(selectedMainReferences.value)] : [];
        const { data } = await api.post(`/drafts/${imageDraft.value.id}/image-tasks`, { task_type: type, source_skus: type === 'carousel' ? selectedImageSkus.value : [], reference_mode: mainReferenceMode.value, reference_urls: type === 'main_image' ? mainReferenceUrls : [], provider: params.provider, ratio: params.ratio, quality: providerUsesAutoQuality(params.provider) ? 'auto' : params.quality, creative_requirement: params.prompt.trim() }, { headers: headers.value });
        const taskKey = type === 'carousel' ? 'carousel_tasks' : 'main_image_tasks';
        imageDraft.value[taskKey] = [...(data.items || []).reverse(), ...(imageDraft.value[taskKey] || [])];
        if (type === 'carousel') {
            selectedImageSkus.value = [];
        }
        showToast(type === 'carousel' ? `已创建 ${data.total} 条轮播图任务` : '首图任务已创建');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '创建图片任务失败');
    }
    finally {
        imageTaskCreatingType.value = '';
    }
}
function isWorkspaceTaskSelected(task, url) {
    if (!imageDraft.value)
        return false;
    if (task.task_type === 'main_image')
        return (imageDraft.value.carousel_items || []).some((item) => item.task_id === task.id && item.image_url === url);
    const sku = String(task.parameters?.source_sku || '');
    return imageDraft.value.carousel_items?.some((item) => item.sku === sku && item.image_url === url);
}
function isTaskResultSelected(task, url) {
    return showDraftImageDialog.value && imageDraft.value?.id === Number(task.parameters?.draft_id)
        ? isWorkspaceTaskSelected(task, url)
        : task.selected_result_url === url;
}
function taskHasSuccessfulResult(task) { return ['awaiting_selection', 'completed'].includes(task?.status) && !!task?.result_urls?.[0]; }
function stageCarouselTaskResult(task, url) {
    if (!imageDraft.value)
        return;
    const sku = String(task.parameters?.source_sku || '');
    if (!sku) {
        showToast('该任务缺少来源 SKU');
        return;
    }
    const generated = { sku, image_url: url, task_id: task.id, source_type: 'carousel' };
    const existing = [...(imageDraft.value.carousel_items || [])];
    const fallbackIndex = existing.findIndex((item) => item.source_type === 'sku' && item.sku === sku);
    if (fallbackIndex >= 0)
        existing.splice(fallbackIndex, 1, generated);
    else {
        if (existing.length >= 9) {
            showToast('商品最终图片最多 9 张，请先移除一张轮播图');
            return;
        }
        existing.push(generated);
    }
    resetFinalImageOrder();
    imageDraft.value.carousel_items = existing;
    imageDraft.value.using_sku_fallback = false;
    retainValidMainReferences();
    selectMainReferenceMode(mainReferenceMode.value);
    showToast('已暂存为轮播图，确认后保存到草稿');
}
function stageMainTaskResult(task, url, removeSku) {
    if (!imageDraft.value)
        return;
    const existing = (imageDraft.value.carousel_items || []).filter((item) => item.source_type !== 'main_image');
    if (!removeSku && existing.length === 9) {
        pendingMainApply.value = { task, url };
        mainRemoveSku.value = existing[8]?.image_url || '';
        showMainApplyDialog.value = true;
        return;
    }
    resetFinalImageOrder();
    const remaining = removeSku ? existing.filter((item) => item.image_url !== removeSku) : existing;
    imageDraft.value.carousel_items = [{ sku: null, image_url: url, task_id: task.id, source_type: 'main_image' }, ...remaining];
    imageDraft.value.using_sku_fallback = false;
    showMainApplyDialog.value = false;
    pendingMainApply.value = null;
    showToast('已暂存为首图，确认后保存到草稿');
}
async function applyImageTaskResult(task, url, removeSku) {
    const draftId = task.parameters?.draft_id;
    if (!draftId)
        return;
    if (!showDraftImageDialog.value || imageDraft.value?.id !== Number(draftId)) {
        showTaskDetailDialog.value = false;
        page.value = 'drafts';
        await openImageWorkspace({ id: Number(draftId) }, task.task_type === 'carousel' ? 'carousel' : 'full', task.task_type === 'main_image');
        if (!imageDraft.value)
            return;
    }
    if (task.task_type === 'main_image')
        stageMainTaskResult(task, url, removeSku);
    else
        stageCarouselTaskResult(task, url);
}
function removeMainImage() { if (!imageDraft.value)
    return; resetFinalImageOrder(); const remaining = (imageDraft.value.carousel_items || []).filter((item) => item.source_type !== 'main_image'); imageDraft.value.carousel_items = remaining.length ? remaining : skuFallbackCarouselItems(imageDraft.value); imageDraft.value.using_sku_fallback = !remaining.length; }
function workspaceCarouselTasks() { return (imageDraft.value?.carousel_tasks || []).filter((task) => task && task.id); }
async function refreshWorkspaceTasks() { if (!imageDraft.value)
    return; try {
    await loadImageWorkspace(imageDraft.value.id, true);
}
catch (e) {
    showToast(e.response?.data?.detail || '刷新任务失败');
} }
function toggleWorkspaceCarouselTask(task) {
    if (!imageDraft.value)
        return;
    const url = task?.result_urls?.[0];
    if (!taskHasSuccessfulResult(task) || !url)
        return;
    if (isWorkspaceTaskSelected(task, url)) {
        resetFinalImageOrder();
        const sourceSku = String(task.parameters?.source_sku || '');
        const remaining = (imageDraft.value.carousel_items || []).filter((item) => !(item.task_id === task.id && item.image_url === url));
        const sourceImage = imageDraft.value.sku_items?.find((item) => item.sku === sourceSku && item.image_url);
        if (sourceImage && !remaining.some((item) => item.sku === sourceSku)) {
            remaining.push({ sku: sourceSku, image_url: sourceImage.image_url, task_id: null, source_type: 'sku' });
        }
        imageDraft.value.carousel_items = remaining.length ? remaining : skuFallbackCarouselItems(imageDraft.value);
        imageDraft.value.using_sku_fallback = !remaining.length;
        retainValidMainReferences();
        selectMainReferenceMode(mainReferenceMode.value);
        showToast('已取消采用该轮播图，确认后保存到草稿');
        return;
    }
    stageCarouselTaskResult(task, url);
}
function workspaceMainTasks() { return (imageDraft.value?.main_image_tasks || []).filter((task) => task && task.id); }
function workspaceFailedTasks() {
    const tasks = imageWorkspaceMode.value === 'carousel' ? workspaceCarouselTasks() : workspaceCarouselTasks().concat(workspaceMainTasks());
    return tasks.filter((task) => task.status === 'failed' && !task.failure_ignored);
}
function toggleWorkspaceMainTask(task) {
    if (!imageDraft.value)
        return;
    const url = task?.result_urls?.[0];
    if (!taskHasSuccessfulResult(task) || !url)
        return;
    if (isWorkspaceTaskSelected(task, url)) {
        removeMainImage();
        showToast('已取消采用该首图，确认后保存到草稿');
        return;
    }
    stageMainTaskResult(task, url);
}
function dropFinalImage(targetUrl) { if (!draggedFinalImageUrl.value || draggedFinalImageUrl.value === targetUrl)
    return; const items = [...draftFinalImageItems.value]; const from = items.findIndex((item) => item.image_url === draggedFinalImageUrl.value), to = items.findIndex((item) => item.image_url === targetUrl); if (from < 0 || to < 0)
    return; const [moved] = items.splice(from, 1); items.splice(to, 0, moved); stagedFinalImageItems.value = items; draggedFinalImageUrl.value = ''; }
function removeFinalImage(imageUrl) { const items = draftFinalImageItems.value.filter((item) => item.image_url !== imageUrl); if (items.length === draftFinalImageItems.value.length)
    return; if (!items.length) {
    showToast('请至少保留一张 SKU 图或轮播图');
    return;
} stagedFinalImageItems.value = items; draggedFinalImageUrl.value = ''; showToast('已从最终商品图片中移除，确认后保存到草稿'); }
async function openImageWorkspaceFromTask(task) { const draftId = task?.parameters?.draft_id; if (!draftId)
    return; showTaskDetailDialog.value = false; page.value = 'drafts'; await openImageWorkspace({ id: draftId }, task.task_type === 'carousel' ? 'carousel' : 'full', task.task_type === 'main_image'); if (task.task_type === 'carousel' && task.parameters?.source_sku)
    selectedImageSkus.value = [task.parameters.source_sku]; await nextTick(); document.getElementById(task.task_type === 'main_image' ? 'main-image-workspace-section' : 'carousel-workspace-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
async function confirmDraftImages() { if (!imageDraft.value)
    return; if (!draftFinalImageItems.value.length) {
    showToast('请至少保留一张 SKU 图或轮播图后再保存');
    return;
} try {
    imageConfirmSaving.value = true;
    const isConfirmingCarousel = imageDraft.value.workflow_stage === 'carousel_pending';
    const payload = { image_items: draftFinalImageItems.value.map((item) => ({ result_url: item.image_url, sku: item.sku || null, task_id: item.task_id || null })), ...(isConfirmingCarousel ? { next_stage: carouselConfirmNextStage.value } : {}) };
    imageDraft.value = (await api.post(`/drafts/${imageDraft.value.id}/images/confirm`, payload, { headers: headers.value })).data;
    await refreshDraftList();
    showDraftImageDialog.value = false;
    showToast(isConfirmingCarousel ? (carouselConfirmNextStage.value === 'ready_to_publish' ? '轮播图已确认，商品已进入待发布' : '轮播图已确认，请继续首图创作') : '商品图片已保存到草稿');
}
catch (e) {
    showToast(e.response?.data?.detail || '保存商品图片失败');
}
finally {
    imageConfirmSaving.value = false;
} }
async function saveDraftEdit() {
    const title = draftEditTitle.value.trim();
    if (!editingDraft.value || title.length < 25 || title.length > 255) {
        draftEditError.value = '商品标题长度须为 25-255 个字符';
        return;
    }
    try {
        draftEditSaving.value = true;
        draftEditError.value = '';
        await api.put(`/drafts/${editingDraft.value.id}`, { title, product_description: draftEditProductDescription.value.trim() || null }, { headers: headers.value });
        showDraftEditDialog.value = false;
        await refresh();
    }
    catch (e) {
        draftEditError.value = e.response?.data?.detail || '保存商品草稿失败，请稍后重试';
    }
    finally {
        draftEditSaving.value = false;
    }
}
function openMiaoshouPublishDialog(draftsToPublish) {
    if (!draftsToPublish.length)
        return;
    if (!miaoshouAssignableShops.value.length) {
        showToast('没有可分配的妙手店铺，请联系管理员同步并分配店铺权限');
        return;
    }
    miaoshouPublishDraftIds.value = draftsToPublish.map(draft => draft.id);
    miaoshouPublishShopId.value = null;
    miaoshouPublishCompleted.value = 0;
    miaoshouPublishFailed.value = 0;
    showMiaoshouPublishDialog.value = true;
}
function publishDraftToMiaoshou(draft) { openMiaoshouPublishDialog([draft]); }
function openBatchMiaoshouPublishDialog() {
    if (!batchMiaoshouPublishEligible.value) {
        showToast('仅可批量发布待发布状态的商品草稿');
        return;
    }
    openMiaoshouPublishDialog(selectedDrafts.value);
}
async function confirmMiaoshouPublish() {
    if (!miaoshouPublishShopId.value) {
        showToast('请先选择要分配的店铺');
        return;
    }
    try {
        miaoshouPublishing.value = true;
        miaoshouPublishCompleted.value = 0;
        miaoshouPublishFailed.value = 0;
        for (const draftId of miaoshouPublishDraftIds.value) {
            publishingDraftId.value = draftId;
            try {
                await api.post(`/drafts/${draftId}/claim-to-tiktok`, { shop_id: miaoshouPublishShopId.value }, { headers: headers.value });
            }
            catch {
                miaoshouPublishFailed.value++;
            }
            finally {
                miaoshouPublishCompleted.value++;
            }
        }
        await refresh();
        if (!miaoshouPublishFailed.value) {
            showMiaoshouPublishDialog.value = false;
            selectedDraftIds.value = [];
            showToast(`已发布并分配 ${miaoshouPublishCompleted.value} 条商品到所选店铺`);
        }
        else
            showToast(`发布完成，${miaoshouPublishFailed.value} 条失败，可保留弹窗后重试`);
    }
    finally {
        publishingDraftId.value = null;
        miaoshouPublishing.value = false;
    }
}
async function openTiktokExportDialog() {
    if (!selectedDrafts.value.length)
        return;
    const templateIds = new Set(selectedDrafts.value.map(draft => draft.template_id));
    if (templateIds.size !== 1 || templateIds.has(null)) {
        showToast('一次只能导出属于同一产品模板的商品草稿');
        return;
    }
    const titleGroups = new Map();
    for (const draft of selectedDrafts.value) {
        const titleKey = String(draft.title || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
        const group = titleGroups.get(titleKey) || [];
        group.push(draft);
        titleGroups.set(titleKey, group);
    }
    const duplicateTitles = [...titleGroups.values()].filter(group => group.length > 1);
    if (duplicateTitles.length) {
        showToast(`同批导出的商品名称必须不同：${duplicateTitles.map(group => `#${group.map(draft => draft.id).join('、#')}`).join('；')}`);
        return;
    }
    showTiktokExportDialog.value = true;
    tiktokExportLoading.value = true;
    tiktokExportError.value = '';
    tiktokExportCatalogId.value = tiktokExportCatalogs.value[0]?.id || null;
    tiktokExportCategory.value = '';
    tiktokExportDefaultPrice.value = null;
    tiktokExportDefaultQuantity.value = 999;
    tiktokExportCod.value = 'Y';
    tiktokExportAttributes.value = {};
    tiktokExportOptions.value = null;
    tiktokExportOverrides.value = Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, { price: null, quantity: null }]));
    try {
        if (!tiktokExportCatalogId.value)
            throw new Error('请先由管理员新增 TK 类目库');
        tiktokExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: tiktokExportCatalogId.value } })).data;
    }
    catch (e) {
        tiktokExportError.value = e.response?.data?.detail || e.message || '加载 TikTok 模板选项失败';
    }
    finally {
        tiktokExportLoading.value = false;
    }
}
async function openShopeeExportDialog() {
    if (!selectedDrafts.value.length)
        return;
    const templateIds = new Set(selectedDrafts.value.map(draft => draft.template_id));
    if (templateIds.size !== 1 || templateIds.has(null)) {
        showToast('一次只能导出属于同一产品模板的商品草稿');
        return;
    }
    const titleGroups = new Map();
    for (const draft of selectedDrafts.value) {
        const titleKey = String(draft.title || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
        const group = titleGroups.get(titleKey) || [];
        group.push(draft);
        titleGroups.set(titleKey, group);
    }
    const duplicateTitles = [...titleGroups.values()].filter(group => group.length > 1);
    if (duplicateTitles.length) {
        showToast(`同批导出的商品名称必须不同：${duplicateTitles.map(group => `#${group.map(draft => draft.id).join('、#')}`).join('；')}`);
        return;
    }
    showShopeeExportDialog.value = true;
    shopeeExportLoading.value = true;
    shopeeExportError.value = '';
    shopeeExportCatalogId.value = shopeeCatalogs.value[0]?.id || null;
    shopeeExportCategoryId.value = '';
    shopeeExportDefaultPrice.value = null;
    shopeeExportDefaultQuantity.value = 999;
    shopeeExportChannels.value = [];
    shopeeExportOptions.value = null;
    shopeeExportOverrides.value = Object.fromEntries(selectedDrafts.value.map(draft => [draft.id, { price: null, quantity: null }]));
    try {
        if (!shopeeExportCatalogId.value)
            throw new Error('请先由管理员新增 Shopee 类目库');
        shopeeExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: shopeeExportCatalogId.value } })).data;
        shopeeExportChannels.value = shopeeExportOptions.value.shipping_channels?.[0]?.field ? [shopeeExportOptions.value.shipping_channels[0].field] : [];
    }
    catch (e) {
        shopeeExportError.value = e.response?.data?.detail || e.message || '加载 Shopee 模板选项失败';
    }
    finally {
        shopeeExportLoading.value = false;
    }
}
async function changeShopeeExportCatalog() {
    shopeeExportCategoryId.value = '';
    shopeeExportChannels.value = [];
    shopeeExportOptions.value = null;
    if (!shopeeExportCatalogId.value)
        return;
    try {
        shopeeExportLoading.value = true;
        shopeeExportError.value = '';
        shopeeExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: shopeeExportCatalogId.value } })).data;
        shopeeExportChannels.value = shopeeExportOptions.value.shipping_channels?.[0]?.field ? [shopeeExportOptions.value.shipping_channels[0].field] : [];
    }
    catch (e) {
        shopeeExportError.value = e.response?.data?.detail || '加载 Shopee 类目库失败';
    }
    finally {
        shopeeExportLoading.value = false;
    }
}
async function exportSelectedDraftsToShopee() {
    const defaultPrice = Number(shopeeExportDefaultPrice.value);
    const defaultQuantity = Number(shopeeExportDefaultQuantity.value);
    if (!shopeeExportCatalogId.value) {
        shopeeExportError.value = '请选择 Shopee 类目库';
        return;
    }
    if (!shopeeExportCategoryId.value) {
        shopeeExportError.value = '请选择 Shopee 商品类目';
        return;
    }
    if (!Number.isFinite(defaultPrice) || defaultPrice < 0.10 || defaultPrice > 1000000000) {
        shopeeExportError.value = '默认售价须为 0.10–1000000000';
        return;
    }
    if (!Number.isInteger(defaultQuantity) || defaultQuantity < 0 || defaultQuantity > 10000000) {
        shopeeExportError.value = '默认库存须为 0–10000000 的整数';
        return;
    }
    if (!shopeeExportChannels.value.length) {
        shopeeExportError.value = '请至少选择一个物流渠道';
        return;
    }
    const productOverrides = [];
    for (const draft of selectedDrafts.value) {
        const value = shopeeExportOverrides.value[draft.id] || {};
        const item = { draft_id: draft.id };
        if (value.price !== null && value.price !== '') {
            const price = Number(value.price);
            if (!Number.isFinite(price) || price < 0.10 || price > 1000000000) {
                shopeeExportError.value = `商品草稿 #${draft.id} 的售价覆盖值无效`;
                return;
            }
            item.price = price;
        }
        if (value.quantity !== null && value.quantity !== '') {
            const quantity = Number(value.quantity);
            if (!Number.isInteger(quantity) || quantity < 0 || quantity > 10000000) {
                shopeeExportError.value = `商品草稿 #${draft.id} 的库存覆盖值无效`;
                return;
            }
            item.quantity = quantity;
        }
        if (Object.keys(item).length > 1)
            productOverrides.push(item);
    }
    try {
        shopeeExportLoading.value = true;
        shopeeExportError.value = '';
        const response = await api.post('/drafts/export-shopee', {
            draft_ids: selectedDraftIds.value,
            category_catalog_id: shopeeExportCatalogId.value,
            category_id: shopeeExportCategoryId.value,
            default_price: defaultPrice,
            default_quantity: defaultQuantity,
            shipping_channels: shopeeExportChannels.value,
            product_overrides: productOverrides,
        }, { headers: headers.value, responseType: 'blob' });
        const disposition = String(response.headers['content-disposition'] || '');
        const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
        const filename = utf8Name ? decodeURIComponent(utf8Name) : 'Shopee批量上传.xlsx';
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        showShopeeExportDialog.value = false;
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast('Shopee 批量上传表格已生成，商品草稿已标记为已发布');
    }
    catch (e) {
        if (e.response?.data instanceof Blob) {
            try {
                shopeeExportError.value = JSON.parse(await e.response.data.text()).detail || '导出失败';
            }
            catch {
                shopeeExportError.value = '导出 Shopee 表格失败';
            }
        }
        else
            shopeeExportError.value = e.response?.data?.detail || '导出 Shopee 表格失败';
    }
    finally {
        shopeeExportLoading.value = false;
    }
}
function tiktokExportAttributePresetsStorageKey() {
    return user.value?.id ? `haitoro_tiktok_export_attribute_presets_${TIKTOK_EXPORT_ATTRIBUTE_PRESETS_VERSION}:${user.value.id}` : '';
}
function isTiktokExportAttributePresetMap(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
function readTiktokExportAttributePresets() {
    const storageKey = tiktokExportAttributePresetsStorageKey();
    if (!storageKey)
        return {};
    try {
        const parsed = JSON.parse(localStorage.getItem(storageKey) || '{}');
        if (!isTiktokExportAttributePresetMap(parsed))
            return {};
        const presets = {};
        for (const [catalogId, categories] of Object.entries(parsed)) {
            if (!isTiktokExportAttributePresetMap(categories))
                continue;
            for (const [category, attributes] of Object.entries(categories)) {
                if (!isTiktokExportAttributePresetMap(attributes))
                    continue;
                const validAttributes = Object.fromEntries(Object.entries(attributes).filter(([, value]) => typeof value === 'string'));
                if (Object.keys(validAttributes).length)
                    (presets[catalogId] || (presets[catalogId] = {}))[category] = validAttributes;
            }
        }
        return presets;
    }
    catch {
        return {};
    }
}
function saveTiktokExportAttributePresets() {
    const storageKey = tiktokExportAttributePresetsStorageKey();
    if (!storageKey || !tiktokExportCatalogId.value || !tiktokExportCategory.value)
        return;
    const allowedFields = new Set(selectedTiktokCategoryAttributes.value.map((field) => field.field));
    const attributes = Object.fromEntries(Object.entries(tiktokExportAttributes.value).filter(([field, value]) => allowedFields.has(field) && typeof value === 'string' && value.trim()));
    const presets = readTiktokExportAttributePresets();
    const catalogKey = String(tiktokExportCatalogId.value);
    if (Object.keys(attributes).length) {
        presets[catalogKey] || (presets[catalogKey] = {});
        presets[catalogKey][tiktokExportCategory.value] = attributes;
    }
    else {
        delete presets[catalogKey]?.[tiktokExportCategory.value];
        if (presets[catalogKey] && !Object.keys(presets[catalogKey]).length)
            delete presets[catalogKey];
    }
    try {
        if (Object.keys(presets).length)
            localStorage.setItem(storageKey, JSON.stringify(presets));
        else
            localStorage.removeItem(storageKey);
    }
    catch { /* 浏览器存储不可用时不影响导出。 */ }
}
function restoreTiktokExportAttributePresets() {
    const catalogKey = tiktokExportCatalogId.value ? String(tiktokExportCatalogId.value) : '';
    const remembered = catalogKey && tiktokExportCategory.value ? readTiktokExportAttributePresets()[catalogKey]?.[tiktokExportCategory.value] : {};
    const allowedFields = new Set(selectedTiktokCategoryAttributes.value.map((field) => field.field));
    tiktokExportAttributes.value = Object.fromEntries(Object.entries(remembered || {}).filter(([field, value]) => allowedFields.has(field) && typeof value === 'string' && value.trim()));
}
watch(tiktokExportAttributes, saveTiktokExportAttributePresets, { deep: true });
function changeTiktokExportCategory() { restoreTiktokExportAttributePresets(); }
async function changeTiktokExportCatalog() {
    tiktokExportCategory.value = '';
    tiktokExportAttributes.value = {};
    tiktokExportOptions.value = null;
    if (!tiktokExportCatalogId.value)
        return;
    try {
        tiktokExportLoading.value = true;
        tiktokExportError.value = '';
        tiktokExportOptions.value = (await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: tiktokExportCatalogId.value } })).data;
    }
    catch (e) {
        tiktokExportError.value = e.response?.data?.detail || '加载 TK 类目库失败';
    }
    finally {
        tiktokExportLoading.value = false;
    }
}
function hasTiktokAttributeValue(value) { return Boolean(value?.trim()); }
function tiktokAttributeMode(field) {
    const mode = ['single', 'multiple'].includes(field.input_mode) ? 'select' : field.input_mode || (!field.options?.length ? 'text' : field.allow_custom ? 'select_or_text' : 'select');
    return { text: '手动填写', select: '选择', select_or_text: '选择或手动填写' }[mode] || '手动填写';
}
function tiktokAttributePlaceholder(field) {
    if (field.input_type === 'url')
        return '请输入 http:// 或 https:// 开头的 URL';
    const mode = ['single', 'multiple'].includes(field.input_mode) ? 'select' : field.input_mode || (!field.options?.length ? 'text' : field.allow_custom ? 'select_or_text' : 'select');
    if (mode === 'select')
        return '输入模板支持的属性值；';
    if (mode === 'select_or_text')
        return '输入支持的属性值，或手动填写其他值';
    return '请输入属性值';
}
async function exportSelectedDrafts() {
    const defaultPrice = Number(tiktokExportDefaultPrice.value);
    const defaultQuantity = Number(tiktokExportDefaultQuantity.value);
    if (!tiktokExportCatalogId.value) {
        tiktokExportError.value = '请选择 TK 类目库';
        return;
    }
    if (!tiktokExportCategory.value) {
        tiktokExportError.value = '请选择 TikTok 商品类目';
        return;
    }
    if (!Number.isFinite(defaultPrice) || defaultPrice < 0.01 || defaultPrice > 999999) {
        tiktokExportError.value = '默认售价须为 0.01–999999';
        return;
    }
    if (!Number.isInteger(defaultQuantity) || defaultQuantity < 0 || defaultQuantity > 999999) {
        tiktokExportError.value = '默认库存须为 0–999999 的整数';
        return;
    }
    const productOverrides = [];
    for (const draft of selectedDrafts.value) {
        const value = tiktokExportOverrides.value[draft.id] || {};
        const item = { draft_id: draft.id };
        if (value.price !== null && value.price !== '') {
            const price = Number(value.price);
            if (!Number.isFinite(price) || price < 0.01 || price > 999999) {
                tiktokExportError.value = `商品草稿 #${draft.id} 的售价覆盖值无效`;
                return;
            }
            item.price = price;
        }
        if (value.quantity !== null && value.quantity !== '') {
            const quantity = Number(value.quantity);
            if (!Number.isInteger(quantity) || quantity < 0 || quantity > 999999) {
                tiktokExportError.value = `商品草稿 #${draft.id} 的库存覆盖值无效`;
                return;
            }
            item.quantity = quantity;
        }
        if (Object.keys(item).length > 1)
            productOverrides.push(item);
    }
    try {
        tiktokExportLoading.value = true;
        tiktokExportError.value = '';
        const response = await api.post('/drafts/export-tiktok', {
            draft_ids: selectedDraftIds.value,
            category_catalog_id: tiktokExportCatalogId.value,
            category: tiktokExportCategory.value,
            default_price: defaultPrice,
            default_quantity: defaultQuantity,
            cod: tiktokExportCod.value,
            attributes: Object.fromEntries(Object.entries(tiktokExportAttributes.value).filter(([, value]) => hasTiktokAttributeValue(value))),
            product_overrides: productOverrides,
        }, { headers: headers.value, responseType: 'blob' });
        const disposition = String(response.headers['content-disposition'] || '');
        const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
        const filename = utf8Name ? decodeURIComponent(utf8Name) : 'TikTok批量上传.xlsx';
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        showTiktokExportDialog.value = false;
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast('TikTok 批量上传表格已生成，商品草稿已标记为已发布');
    }
    catch (e) {
        if (e.response?.data instanceof Blob) {
            try {
                tiktokExportError.value = JSON.parse(await e.response.data.text()).detail || '导出失败';
            }
            catch {
                tiktokExportError.value = '导出 TikTok 表格失败';
            }
        }
        else
            tiktokExportError.value = e.response?.data?.detail || '导出 TikTok 表格失败';
    }
    finally {
        tiktokExportLoading.value = false;
    }
}
async function submitSelectedDraftsToHubstudio() {
    const defaultPrice = Number(tiktokExportDefaultPrice.value), defaultQuantity = Number(tiktokExportDefaultQuantity.value);
    if (!tiktokExportIsLocal.value) {
        tiktokExportError.value = 'tk跨境店类目库仅支持下载表格，不能自动上品';
        return;
    }
    if (!tiktokExportCatalogId.value || !tiktokExportCategory.value || !Number.isFinite(defaultPrice) || defaultPrice < 0.01 || !Number.isInteger(defaultQuantity) || defaultQuantity < 0) {
        tiktokExportError.value = '请先完整填写 TikTok 导出参数';
        return;
    }
    const product_overrides = selectedDrafts.value.flatMap(draft => {
        const value = tiktokExportOverrides.value[draft.id] || {};
        const item = { draft_id: draft.id };
        if (value.price !== null && value.price !== '')
            item.price = Number(value.price);
        if (value.quantity !== null && value.quantity !== '')
            item.quantity = Number(value.quantity);
        return Object.keys(item).length > 1 ? [item] : [];
    });
    try {
        tiktokSubmitting.value = true;
        tiktokExportError.value = '';
        const { data } = await api.post('/drafts/submit-to-hubstudio', { draft_ids: selectedDraftIds.value, category_catalog_id: tiktokExportCatalogId.value, category: tiktokExportCategory.value, default_price: defaultPrice, default_quantity: defaultQuantity, cod: tiktokExportCod.value, attributes: Object.fromEntries(Object.entries(tiktokExportAttributes.value).filter(([, value]) => hasTiktokAttributeValue(value))), product_overrides }, { headers: headers.value });
        showTiktokExportDialog.value = false;
        selectedDraftIds.value = [];
        await refreshDraftList();
        showToast(`自动上品任务 #${data.id} 已进入队列，将按执行器本机的模版策略分配环境`);
    }
    catch (e) {
        tiktokExportError.value = e.response?.data?.detail || '创建 HubStudio 自动上品任务失败';
    }
    finally {
        tiktokSubmitting.value = false;
    }
}
async function refreshTiktokCatalogList() {
    if (tiktokCatalogListRefreshing.value)
        return;
    try {
        tiktokCatalogListRefreshing.value = true;
        tiktokCatalogError.value = '';
        tiktokCatalogs.value = (await api.get('/category-catalogs', { headers: headers.value })).data;
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '刷新类目列表失败';
    }
    finally {
        tiktokCatalogListRefreshing.value = false;
    }
}
function openTiktokCatalogCreateDialog() {
    tiktokCatalogName.value = '';
    tiktokCatalogFile.value = null;
    tiktokCatalogError.value = '';
    showTiktokCatalogDialog.value = true;
}
function onTiktokCatalogFileChange(event) {
    tiktokCatalogFile.value = event.target.files?.[0] || null;
}
async function createTiktokCatalog() {
    const name = tiktokCatalogName.value.trim();
    if (!name || !tiktokCatalogFile.value) {
        tiktokCatalogError.value = '请填写类目库名称并选择平台 XLSX 模板';
        return;
    }
    const form = new FormData();
    form.append('name', name);
    form.append('template_type', tiktokCatalogTypeTab.value);
    form.append('file', tiktokCatalogFile.value);
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        await api.post('/category-catalogs', form, { headers: headers.value });
        showTiktokCatalogDialog.value = false;
        tiktokCatalogs.value = (await api.get('/category-catalogs', { headers: headers.value })).data;
        showToast('类目库已导入');
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '导入类目库失败';
    }
    finally {
        tiktokCatalogLoading.value = false;
    }
}
async function openTiktokCatalogDetail(catalog) {
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        const { data } = await api.get('/category-export/options', { headers: headers.value, params: { category_catalog_id: catalog.id } });
        managingTiktokCatalog.value = catalog;
        managingTiktokCatalogOptions.value = data;
        managingTiktokCategory.value = data.categories?.[0]?.name || '';
        showTiktokCatalogDetailDialog.value = true;
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '读取 TK 类目库失败';
    }
    finally {
        tiktokCatalogLoading.value = false;
    }
}
async function setTiktokAttributeInputMode(field, inputMode) {
    if (!managingTiktokCatalog.value)
        return;
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        const { data } = await api.patch(`/category-catalogs/${managingTiktokCatalog.value.id}`, {
            attribute_input_modes: [{ category: managingTiktokCategory.value, field: field.field, input_mode: inputMode }],
        }, { headers: headers.value });
        managingTiktokCatalogOptions.value = data.options || managingTiktokCatalogOptions.value;
        tiktokExportOptions.value = null;
        showToast(`${field.label} 已设置为${tiktokAttributeMode({ ...field, input_mode: inputMode })}`);
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '保存属性选择方式失败';
    }
    finally {
        tiktokCatalogLoading.value = false;
    }
}
function onTiktokInputModeChange(field, event) {
    setTiktokAttributeInputMode(field, event.target.value);
}
async function deleteTiktokCatalog(catalog) {
    if (!confirm(`确定删除类目库“${catalog.name}”吗？`))
        return;
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        await api.delete(`/category-catalogs/${catalog.id}`, { headers: headers.value });
        tiktokCatalogs.value = tiktokCatalogs.value.filter(item => item.id !== catalog.id);
        showToast('类目库已删除');
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '删除类目库失败';
    }
    finally {
        tiktokCatalogLoading.value = false;
    }
}
async function openClaimMaterialsDialog(task) { try {
    claimingTask.value = (await api.get(`/tasks/${task.id}`, { headers: headers.value })).data;
    selectedClaimResultUrls.value = [];
    showClaimMaterialsDialog.value = true;
}
catch (e) {
    showToast(e.response?.data?.detail || '加载任务结果失败');
} }
function toggleClaimResult(url) { selectedClaimResultUrls.value = selectedClaimResultUrls.value.includes(url) ? selectedClaimResultUrls.value.filter(item => item !== url) : [...selectedClaimResultUrls.value, url]; }
async function claimMaterials() {
    if (!claimingTask.value || !selectedClaimResultUrls.value.length) {
        showToast('请至少选择一张图片');
        return;
    }
    try {
        claimingMaterials.value = true;
        await api.post(`/tasks/${claimingTask.value.id}/claim-materials`, { result_urls: selectedClaimResultUrls.value }, { headers: headers.value });
        showClaimMaterialsDialog.value = false;
        selectedTaskIds.value = [];
        await refresh();
        showToast('领取成功，可在素材库查看');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '领取素材失败');
    }
    finally {
        claimingMaterials.value = false;
    }
}
function toggleTaskSelection(taskId) { selectedTaskIds.value = selectedTaskIds.value.includes(taskId) ? selectedTaskIds.value.filter(id => id !== taskId) : [...selectedTaskIds.value, taskId]; }
function taskCanBeSelected(task) { return task.status === 'failed' || activeTaskType.value === 'sku_image' && ['awaiting_selection', 'completed'].includes(task.status) && Boolean(task.result_count || task.result_urls?.length); }
function toggleAllSelectableTasks() { selectedTaskIds.value = allSelectableTasksSelected.value ? [] : selectablePagedTasks.value.map(task => task.id); }
function removeBatchClaimImage(taskId, url) { if (!batchClaiming.value)
    batchClaimItems.value = batchClaimItems.value.filter(item => item.taskId !== taskId || item.url !== url); }
async function openBatchClaimDialog() {
    if (!selectedClaimableTaskIds.value.length) {
        showToast('请至少选择一个可领取任务');
        return;
    }
    showBatchClaimDialog.value = true;
    batchClaimLoading.value = true;
    batchClaimItems.value = [];
    batchClaimCompleted.value = 0;
    batchClaimFailed.value = 0;
    try {
        const details = await Promise.all(selectedClaimableTaskIds.value.map(id => api.get(`/tasks/${id}`, { headers: headers.value }).then(response => response.data)));
        batchClaimItems.value = details.flatMap(task => (task.result_urls || []).map((url) => ({ taskId: task.id, taskLabel: `任务 #${task.id}`, url })));
        if (!batchClaimItems.value.length)
            showToast('所选任务没有可领取图片');
    }
    catch (e) {
        showBatchClaimDialog.value = false;
        showToast(e.response?.data?.detail || '加载批量领取内容失败');
    }
    finally {
        batchClaimLoading.value = false;
    }
}
async function confirmBatchClaim() {
    const groups = groupedBatchClaimItems.value;
    if (!groups.length) {
        showToast('请至少保留一张图片');
        return;
    }
    batchClaiming.value = true;
    batchClaimCompleted.value = 0;
    batchClaimFailed.value = 0;
    batchClaimTotal.value = groups.length;
    for (const group of groups) {
        try {
            await api.post(`/tasks/${group.taskId}/claim-materials`, { result_urls: group.urls }, { headers: headers.value });
        }
        catch {
            batchClaimFailed.value++;
        }
        finally {
            batchClaimCompleted.value++;
        }
    }
    batchClaiming.value = false;
    if (!batchClaimFailed.value)
        showBatchClaimDialog.value = false;
    const claimedTaskIds = groups.map(group => group.taskId);
    selectedTaskIds.value = selectedTaskIds.value.filter(id => !claimedTaskIds.includes(id));
    await refreshTaskList();
    showToast(batchClaimFailed.value ? `批量领取完成，${batchClaimFailed.value} 个任务失败，可保留弹窗后重试` : `批量领取成功，共处理 ${batchClaimTotal.value} 个任务`);
}
async function retryTaskResult(task) {
    try {
        retryingTaskId.value = task.id;
        await api.post(`/tasks/${task.id}/retry`, {}, { headers: headers.value });
        await refreshTaskList();
        showToast('失败任务已重新入队');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '重试任务失败');
    }
    finally {
        retryingTaskId.value = null;
    }
}
async function retrySelectedTasks() {
    const taskIds = selectedRetryTaskIds.value;
    if (!taskIds.length) {
        showToast('请至少选择一个失败任务');
        return;
    }
    try {
        batchRetryingTasks.value = true;
        const { data } = await api.post('/tasks/batch-retry', { task_ids: taskIds }, { headers: headers.value });
        selectedTaskIds.value = selectedTaskIds.value.filter(id => !taskIds.includes(id));
        await refreshTaskList();
        showToast(`已将 ${data.total} 个失败任务重新入队`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '批量重试任务失败');
    }
    finally {
        batchRetryingTasks.value = false;
    }
}
async function retryWorkspaceTask(task) {
    try {
        retryingWorkspaceTaskId.value = task.id;
        await api.post(`/tasks/${task.id}/retry`, {}, { headers: headers.value });
        await refreshWorkspaceTasks();
        showToast('失败任务已重新入队');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '重试任务失败');
    }
    finally {
        retryingWorkspaceTaskId.value = null;
    }
}
async function ignoreWorkspaceTaskFailure(task) {
    if (!imageDraft.value)
        return;
    try {
        await api.post(`/drafts/${imageDraft.value.id}/image-tasks/${task.id}/ignore-failure`, {}, { headers: headers.value });
        await refreshWorkspaceTasks();
        await refreshDraftList();
        showToast('已忽略失败任务，可继续当前制作阶段');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '忽略失败任务失败');
    }
}
function chooseMaterialUploadFiles(event) {
    const input = event.target;
    const files = Array.from(input.files || []);
    input.value = '';
    if (!files.length)
        return;
    if (files.length > MATERIAL_UPLOAD_MAX_FILES) {
        showToast(`单次最多上传 ${MATERIAL_UPLOAD_MAX_FILES} 张图片`);
        return;
    }
    if (files.some(file => !ALLOWED_IMAGE_TYPES.includes(file.type) || !file.size || file.size > MAX_IMAGE_BYTES)) {
        showToast('仅支持 JPG、PNG、WebP，且单张不能超过 3MB');
        return;
    }
    pendingMaterialUploadFiles.value = files;
    pendingMaterialUploadUrls.value = [];
    materialUploadTemplateId.value = null;
    showMaterialUploadDialog.value = true;
}
async function uploadMaterialAssets() {
    const files = [...pendingMaterialUploadFiles.value];
    if (!files.length || !materialUploadTemplateId.value) {
        showToast('请选择产品模板');
        return;
    }
    try {
        materialUploading.value = true;
        materialUploadError.value = '';
        materialUploadTotal.value = files.length;
        materialUploadedCount.value = 0;
        // 已直传成功的图片保留 URL，重试时只补传失败的那几张。
        const missing = files.map((_file, index) => index).filter(index => !pendingMaterialUploadUrls.value[index]);
        if (missing.length) {
            const { data: signed } = await api.post('/material-assets/presign', {
                files: missing.map(index => ({ content_type: files[index].type, content_length: files[index].size })),
            }, { headers: headers.value });
            let cursor = 0;
            const worker = async () => {
                while (true) {
                    const slot = cursor++;
                    if (slot >= missing.length)
                        return;
                    const index = missing[slot], file = files[index], target = signed[slot];
                    for (let attempt = 0; attempt <= IMAGE_UPLOAD_RETRY && !pendingMaterialUploadUrls.value[index]; attempt++) {
                        await axios.put(target.upload_url, file, { headers: { 'Content-Type': file.type } })
                            .then(() => { pendingMaterialUploadUrls.value[index] = target.url; })
                            .catch(() => undefined);
                    }
                    if (!pendingMaterialUploadUrls.value[index])
                        throw new Error(`「${file.name}」上传失败`);
                    materialUploadedCount.value++;
                }
            };
            const results = await Promise.allSettled(Array.from({ length: Math.min(MATERIAL_UPLOAD_CONCURRENCY, missing.length) }, worker));
            const failed = results.find((result) => result.status === 'rejected');
            if (failed)
                throw failed.reason;
        }
        await api.post('/material-assets/commit', {
            template_id: materialUploadTemplateId.value,
            items: files.map((file, index) => ({ url: pendingMaterialUploadUrls.value[index], name: file.name })),
        }, { headers: headers.value });
        showMaterialUploadDialog.value = false;
        pendingMaterialUploadFiles.value = [];
        pendingMaterialUploadUrls.value = [];
        currentMaterialPage.value = 1;
        await refreshMaterialList();
        showToast(`已上传 ${files.length} 张素材`);
    }
    catch (e) {
        materialUploadError.value = e.response?.data?.detail || e?.message || '上传素材失败，请稍后重试';
    }
    finally {
        materialUploading.value = false;
        materialUploadTotal.value = 0;
    }
}
async function deleteSelectedMaterialAssets() {
    const assetIds = [...selectedMaterialAssetIds.value];
    if (!assetIds.length || !confirm(`确定从素材库删除选中的 ${assetIds.length} 张图片吗？`))
        return;
    try {
        await Promise.all(assetIds.map(assetId => api.delete(`/material-assets/${assetId}`, { headers: headers.value })));
        await refreshMaterialList();
        showToast(`已删除 ${assetIds.length} 张素材`);
    }
    catch (e) {
        await refreshMaterialList();
        showToast(e.response?.data?.detail || '删除素材失败，请稍后重试');
    }
}
async function downloadSelectedMaterialAssets() {
    if (!selectedMaterialAssetIds.value.length)
        return;
    try {
        materialDownloading.value = true;
        const response = await api.post('/material-assets/download', {
            material_asset_ids: selectedMaterialAssetIds.value,
        }, { headers: headers.value, responseType: 'blob' });
        const disposition = String(response.headers['content-disposition'] || '');
        const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
        const plainName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
        const filename = utf8Name ? decodeURIComponent(utf8Name) : plainName || (selectedMaterialAssetIds.value.length === 1 ? 'material.jpg' : 'haitoro-materials.zip');
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        showToast(`已开始下载 ${selectedMaterialAssetIds.value.length} 张素材`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '下载素材失败，请稍后重试');
    }
    finally {
        materialDownloading.value = false;
    }
}
async function refreshMemberList() {
    if (memberListRefreshing.value)
        return;
    try {
        memberListRefreshing.value = true;
        const [memberResponse, groupResponse] = await Promise.all([api.get('/members', { headers: headers.value }), api.get('/operator-groups', { headers: headers.value })]);
        members.value = memberResponse.data;
        operatorGroups.value = groupResponse.data;
    }
    catch (e) {
        showToast(e.response?.data?.detail || '刷新成员列表失败');
    }
    finally {
        memberListRefreshing.value = false;
    }
}
function operatorGroupName(groupId) { return operatorGroups.value.find(group => group.id === groupId)?.name || '未分组'; }
function operatorGroupMembers(groupId) { return members.value.filter(member => member.group_id === groupId); }
function memberRoleLabel(member) { return member.role === 'company_admin' ? '公司管理员' : member.role === 'team_leader' ? '运营组长' : member.group_id ? '组员' : '普通运营'; }
function openOperatorGroupDialog(group) { editingOperatorGroup.value = group || null; operatorGroupForm.value = { name: group?.name || '', leader_user_id: null }; operatorGroupError.value = ''; showOperatorGroupDialog.value = true; }
async function saveOperatorGroup() {
    const name = operatorGroupForm.value.name.trim();
    if (!name) {
        operatorGroupError.value = '请输入组名';
        return;
    }
    if (!editingOperatorGroup.value && !operatorGroupForm.value.leader_user_id) {
        operatorGroupError.value = '请选择组长';
        return;
    }
    try {
        operatorGroupSaving.value = true;
        operatorGroupError.value = '';
        if (editingOperatorGroup.value)
            await api.patch(`/operator-groups/${editingOperatorGroup.value.id}`, { name }, { headers: headers.value });
        else
            await api.post('/operator-groups', { name, leader_user_id: operatorGroupForm.value.leader_user_id }, { headers: headers.value });
        showOperatorGroupDialog.value = false;
        await refreshMemberList();
        showToast('运营组已保存');
    }
    catch (e) {
        operatorGroupError.value = e.response?.data?.detail || '保存运营组失败';
    }
    finally {
        operatorGroupSaving.value = false;
    }
}
async function deleteOperatorGroup(group) {
    const affected = operatorGroupMembers(group.id);
    const otherCount = affected.filter(member => member.id !== group.leader_user_id).length;
    if (!confirm(`确定删除“${group.name}”吗？该组组长和 ${otherCount} 位组员（共 ${affected.length} 人）都将恢复为未分组普通运营。`))
        return;
    try {
        await api.delete(`/operator-groups/${group.id}`, { headers: headers.value });
        await refreshMemberList();
        showToast('运营组已删除');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '删除运营组失败');
    }
}
function openMemberDialog(member) { editingMember.value = member || null; memberForm.value = { name: member?.name || '', user_code: member?.user_code || '', email: member?.email || '', password: '', is_active: member?.is_active ?? true, role: member?.role || 'member', group_id: member?.group_id ?? null }; memberFormError.value = ''; showMemberDialog.value = true; }
function openMyAccountDialog() { myName.value = user.value?.name || ''; myUserCode.value = user.value?.user_code || ''; showMyAccountDialog.value = true; }
async function saveMyUserCode() { const name = myName.value.trim(), userCode = myUserCode.value.trim(); if (!name) {
    showToast('请输入管理员名称');
    return;
} if (userCode && [...userCode].length !== 2) {
    showToast('用户代码必须恰好为两个字符');
    return;
} try {
    myAccountSaving.value = true;
    const { data } = await api.patch('/me', { name, user_code: userCode || null }, { headers: headers.value });
    user.value = data;
    showMyAccountDialog.value = false;
    showToast('账户设置已保存');
}
catch (e) {
    showToast(e.response?.data?.detail || '保存账户设置失败');
}
finally {
    myAccountSaving.value = false;
} }
async function saveMember() {
    const name = memberForm.value.name.trim(), userCode = memberForm.value.user_code.trim(), email = memberForm.value.email.trim();
    memberFormError.value = '';
    const invalid = (message) => { memberFormError.value = message; showToast(message); };
    if (!name) {
        invalid('请输入姓名');
        return;
    }
    if (!userCode) {
        invalid('请输入用户代码');
        return;
    }
    if ([...userCode].length !== 2) {
        invalid('用户代码必须恰好为两个字符');
        return;
    }
    if (!email) {
        invalid('请输入邮箱');
        return;
    }
    if (!memberForm.value.password && !editingMember.value) {
        invalid('请设置登录密码');
        return;
    }
    if (memberForm.value.password && memberForm.value.password.length < 8) {
        invalid('登录密码至少 8 个字符');
        return;
    }
    if (memberForm.value.role === 'team_leader' && !memberForm.value.group_id) {
        invalid('请选择组长所属运营组');
        return;
    }
    try {
        memberSaving.value = true;
        error.value = '';
        const payload = { name, user_code: userCode, email, role: memberForm.value.role, group_id: memberForm.value.group_id };
        if (memberForm.value.password)
            payload.password = memberForm.value.password;
        if (editingMember.value)
            await api.put(`/members/${editingMember.value.id}`, payload, { headers: headers.value });
        else
            await api.post('/members', payload, { headers: headers.value });
        showMemberDialog.value = false;
        await refresh();
        showToast('成员已保存');
    }
    catch (e) {
        const message = e.response?.data?.detail || '保存成员失败';
        memberFormError.value = message;
        error.value = message;
        showToast(message);
    }
    finally {
        memberSaving.value = false;
    }
}
async function toggleMember(member) { try {
    await api.put(`/members/${member.id}`, { is_active: !member.is_active }, { headers: headers.value });
    await refresh();
}
catch (e) {
    error.value = e.response?.data?.detail || '更新成员状态失败';
} }
function openMemberCredentialDialog(member, provider) { credentialMember.value = member; credentialProvider.value = provider; credentialApiKey.value = ''; showMemberCredentialDialog.value = true; }
function memberCredentialKey() { return credentialProvider.value?.credential_provider || credentialProvider.value?.provider; }
function memberCredentialPreview() { return credentialMember.value?.ai_provider_credential_previews?.[memberCredentialKey()] || ''; }
async function saveMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !credentialApiKey.value.trim()) {
    showToast('请输入平台密钥');
    return;
} try {
    credentialSaving.value = true;
    await api.put(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`, { api_key: credentialApiKey.value.trim() }, { headers: headers.value });
    showMemberCredentialDialog.value = false;
    await refresh();
    showToast(`${credentialProvider.value.credential_display_name || credentialProvider.value.display_name} 平台密钥已安全保存`);
}
catch (e) {
    showToast(e.response?.data?.detail || '保存平台密钥失败');
}
finally {
    credentialSaving.value = false;
} }
async function clearMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !confirm(`确定清除 ${credentialMember.value.name} 的 ${credentialProvider.value.credential_display_name || credentialProvider.value.display_name} 平台密钥吗？`))
    return; try {
    credentialSaving.value = true;
    await api.delete(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`, { headers: headers.value });
    showMemberCredentialDialog.value = false;
    await refresh();
    showToast('平台密钥已清除');
}
catch (e) {
    showToast(e.response?.data?.detail || '清除平台密钥失败');
}
finally {
    credentialSaving.value = false;
} }
async function loadMiaoshouShops() { try {
    shopLoading.value = true;
    shopError.value = '';
    await api.post('/miaoshou/shops', {}, { headers: headers.value });
    await refresh();
    return true;
}
catch (e) {
    shopError.value = e.response?.data?.detail || '获取妙手店铺失败';
    return false;
}
finally {
    shopLoading.value = false;
} }
function openMiaoshouDialog() { miaoshouForm.value = { app_id: '', app_secret: '' }; shopError.value = ''; showMiaoshouDialog.value = true; }
async function saveMiaoshouAccount() {
    const appId = miaoshouForm.value.app_id.trim(), appSecret = miaoshouForm.value.app_secret.trim();
    if (!appId || !appSecret) {
        showToast('请输入 App ID 和 App Secret');
        return;
    }
    try {
        miaoshouSaving.value = true;
        shopError.value = '';
        await api.put('/miaoshou/account', { app_id: appId, app_secret: appSecret }, { headers: headers.value });
        if (company.value)
            company.value.miaoshou_configured = true;
        showMiaoshouDialog.value = false;
        const synced = await loadMiaoshouShops();
        showToast(synced ? '妙手 API Key 已保存，店铺同步完成' : '妙手 API Key 已保存，请检查同步错误后重试');
    }
    catch (e) {
        shopError.value = e.response?.data?.detail || '保存妙手 API Key 失败';
        showToast(shopError.value);
    }
    finally {
        miaoshouSaving.value = false;
    }
}
function openShopManagersDialog(shop) { managingShop.value = shop; selectedManagerIds.value = shop.manager_users.map((member) => member.id); showShopManagersDialog.value = true; }
async function saveShopManagers() { if (!managingShop.value)
    return; try {
    shopManagersSaving.value = true;
    await api.put(`/shops/${managingShop.value.id}/managers`, { member_ids: selectedManagerIds.value }, { headers: headers.value });
    showShopManagersDialog.value = false;
    await refresh();
}
catch (e) {
    shopError.value = e.response?.data?.detail || '保存店铺管理人员失败';
}
finally {
    shopManagersSaving.value = false;
} }
function openHubstudioDialog() { hubstudioForm.value = { app_id: '', app_secret: '', group_code: '' }; showHubstudioDialog.value = true; }
async function saveHubstudioAccount() { try {
    hubstudioSaving.value = true;
    await api.put('/hubstudio/account', hubstudioForm.value, { headers: headers.value });
    showHubstudioDialog.value = false;
    await refresh();
    showToast('HubStudio API 凭据已保存');
}
catch (e) {
    shopError.value = e.response?.data?.detail || '保存 HubStudio 配置失败';
}
finally {
    hubstudioSaving.value = false;
} }
let toastTimer;
function showToast(message) { toast.value = message; if (toastTimer)
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = ''; }, 3000); }
function logout() { hubUploadTemplateId.value = null; hubUploadTemplates.value = []; hubUploadRequestId++; hubUploadTasks.value = []; hubUploadTotal.value = 0; hubUploadPage.value = 1; hubUploadCreatorId.value = null; hubUploadLoading.value = false; hubUploadError.value = ''; showHubstudioDialog.value = false; localStorage.removeItem('haitoro_token'); token.value = ''; user.value = null; taskCreatorFilterId.value = null; materialCreatorFilterId.value = null; draftCreatorFilterId.value = null; creatorFiltersInitialized.value = false; productLibraryItems.value = []; productLibraryTotal.value = 0; productLibraryPage.value = 1; productLibraryRankingRequestId++; productLibraryRankingItems.value = []; productLibraryRankingTotal.value = 0; productLibraryRankingDate.value = null; productLibraryRankingThroughDate.value = null; productLibraryShops.value = []; rankingShopFilters.value = {}; stagnantRequestId++; stagnantMaterials.value = []; stagnantTotal.value = 0; stagnantPage.value = 1; stagnantCreatorId.value = null; stagnantError.value = ''; stagnantLoading.value = false; newImagesRequestId++; newImages.value = []; newImagesTotal.value = 0; newImagesPage.value = 1; newImagesCreatorId.value = null; newImagesUsageStatus.value = 'all'; newImagesError.value = ''; newImagesLoading.value = false; productLibraryStatisticsTask.value = null; activeProductLibraryTab.value = 'products'; productLibrarySelectedShopIds.value = []; productLibraryShopSearch.value = ''; productLibraryTemplateFilter.value = ''; productLibrarySku.value = ''; appliedProductLibraryFilters.value = { sourceIds: [], template: '', sku: '' }; selectedProductLibraryIds.value = []; productLibraryFilters.value = { shops: [] }; }
api.interceptors.response.use(response => response, requestError => {
    if (requestError.response?.data?.detail === '登录已失效') {
        logout();
        showToast('登录已失效，请重新登录');
    }
    return Promise.reject(requestError);
});
let taskResultPollingTimer;
async function refreshPendingTaskResults() {
    if (!token.value || !taskActiveCount.value)
        return;
    try {
        applyTaskPage((await api.get('/tasks', { headers: headers.value, params: taskQueryParams() })).data);
    }
    catch { /* 保留上一次任务状态，等待下次轮询。 */ }
}
onMounted(() => {
    if (token.value)
        refresh().catch(logout);
    document.addEventListener('pointerdown', closeProductLibraryShopFilterOnOutsideClick);
    taskResultPollingTimer = setInterval(refreshPendingTaskResults, 5000);
    productLibraryStatisticsPollingTimer = setInterval(() => {
        if (page.value === 'product-library' && productLibraryStatisticsRunning.value)
            void loadProductLibraryStatisticsStatus();
    }, 5000);
});
let productLibraryStatisticsPollingTimer;
onUnmounted(() => {
    document.removeEventListener('pointerdown', closeProductLibraryShopFilterOnOutsideClick);
    if (taskResultPollingTimer)
        clearInterval(taskResultPollingTimer);
    if (productLibraryStatisticsPollingTimer)
        clearInterval(productLibraryStatisticsPollingTimer);
});
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-image']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-info']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-create-button']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-grid']} */ ;
// CSS variable injection 
// CSS variable injection end 
if (!__VLS_ctx.token) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
        ...{ class: "login-shell" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "login-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "brand-mark" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "eyebrow" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "email",
        autocomplete: "username",
    });
    (__VLS_ctx.email);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "password",
        autocomplete: "current-password",
    });
    (__VLS_ctx.password);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.login) },
        ...{ class: "primary full" },
        disabled: (__VLS_ctx.loading),
    });
    (__VLS_ctx.loading ? '登录中…' : '登录');
    if (__VLS_ctx.error) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error" },
        });
        (__VLS_ctx.error);
    }
}
if (__VLS_ctx.showTiktokCatalogDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokCatalogDialog))
                    return;
                !__VLS_ctx.tiktokCatalogLoading && (__VLS_ctx.showTiktokCatalogDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card tiktok-catalog-create-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokCatalogDialog))
                    return;
                __VLS_ctx.showTiktokCatalogDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.tiktokCatalogLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.tiktokCatalogTypeLabel(__VLS_ctx.tiktokCatalogTypeTab));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "120",
        placeholder: "例如：女装",
    });
    (__VLS_ctx.tiktokCatalogName);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onChange: (__VLS_ctx.onTiktokCatalogFileChange) },
        type: "file",
        accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    if (__VLS_ctx.tiktokCatalogError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error material-draft-error" },
        });
        (__VLS_ctx.tiktokCatalogError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokCatalogDialog))
                    return;
                __VLS_ctx.showTiktokCatalogDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.tiktokCatalogLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createTiktokCatalog) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.tiktokCatalogLoading),
    });
    (__VLS_ctx.tiktokCatalogLoading ? '解析中…' : '上传并解析');
}
if (__VLS_ctx.showTiktokCatalogDetailDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokCatalogDetailDialog))
                    return;
                __VLS_ctx.showTiktokCatalogDetailDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card tiktok-catalog-detail-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokCatalogDetailDialog))
                    return;
                __VLS_ctx.showTiktokCatalogDetailDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.managingTiktokCatalog?.name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.managingTiktokCategory),
    });
    for (const [category] of __VLS_getVForSourceType((__VLS_ctx.managingTiktokCatalogOptions?.categories || []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (category.name),
            value: (category.name),
        });
        (category.name);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "tiktok-property-list" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "tiktok-property-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    for (const [field] of __VLS_getVForSourceType((__VLS_ctx.managingTiktokCategoryAttributes))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (field.field),
            ...{ class: "tiktok-property-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (field.label);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (field.field);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (field.required ? '必填' : '可选');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (field.options?.length || 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (...[$event]) => {
                    if (!(__VLS_ctx.showTiktokCatalogDetailDialog))
                        return;
                    __VLS_ctx.onTiktokInputModeChange(field, $event);
                } },
            ...{ class: "tiktok-input-mode-select" },
            value: (['single', 'multiple'].includes(field.input_mode) ? 'select' : field.input_mode || (!field.options?.length ? 'text' : field.allow_custom ? 'select_or_text' : 'select')),
            disabled: (__VLS_ctx.tiktokCatalogLoading),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: "text",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: "select",
            disabled: (!field.options?.length),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: "select_or_text",
            disabled: (!field.options?.length),
        });
    }
    if (!__VLS_ctx.managingTiktokCategoryAttributes.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "empty" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokCatalogDetailDialog))
                    return;
                __VLS_ctx.showTiktokCatalogDetailDialog = false;
            } },
        ...{ class: "primary" },
    });
}
if (__VLS_ctx.token) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
        ...{ class: "app-shell" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "logo" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({});
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.visibleNav))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    __VLS_ctx.page = item.key;
                } },
            key: (item.key),
            ...{ class: ({ active: __VLS_ctx.page === item.key }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
        (item.icon);
        (item.label);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "content" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
    (__VLS_ctx.pageTitle);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "context" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.openMyAccountDialog) },
        ...{ class: "member account-button" },
    });
    (__VLS_ctx.user?.name);
    (__VLS_ctx.user?.role === 'company_admin' ? '管理员' : __VLS_ctx.user?.role === 'team_leader' ? '运营组长' : '运营成员');
    (__VLS_ctx.user?.group_name ? ` · ${__VLS_ctx.user.group_name}` : '');
    (__VLS_ctx.user?.user_code ? ` · ${__VLS_ctx.user.user_code}` : '');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.logout) },
        ...{ class: "ghost" },
    });
    if (__VLS_ctx.page === 'dashboard') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "hero" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!(__VLS_ctx.page === 'dashboard'))
                        return;
                    __VLS_ctx.page = 'pod';
                } },
            ...{ class: "primary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "metrics" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.taskStatusCounts.awaiting_selection || 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.drafts.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.materialTotal);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "two-col" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!(__VLS_ctx.page === 'dashboard'))
                        return;
                    __VLS_ctx.page = 'tasks';
                } },
        });
        for (const [task] of __VLS_getVForSourceType((__VLS_ctx.tasks.slice(0, 3)))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (task.id),
                ...{ class: "task-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "thumb" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (task.id);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.taskTypeLabel(task));
            (new Date(task.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (__VLS_ctx.taskStatusClass(task.status)) },
            });
            (__VLS_ctx.taskStatusLabel[task.status] || task.status || '—');
        }
        if (!__VLS_ctx.tasks.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!(__VLS_ctx.page === 'dashboard'))
                        return;
                    __VLS_ctx.page = 'templates';
                } },
            ...{ class: "quick" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!(__VLS_ctx.page === 'dashboard'))
                        return;
                    __VLS_ctx.page = 'tasks';
                } },
            ...{ class: "quick" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    }
    else if (__VLS_ctx.page === 'templates') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "toolbar" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            placeholder: "搜索模板名称",
        });
        (__VLS_ctx.templateQuery);
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "toolbar-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!(__VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.openTemplateDialog();
                    } },
                ...{ class: "primary" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "template-layout" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "groups" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "groups-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!(__VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.showGroupDialog = true;
                    } },
                ...{ class: "add-group" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!(__VLS_ctx.page === 'templates'))
                        return;
                    __VLS_ctx.activeGroupId = null;
                } },
            ...{ class: ({ selected: __VLS_ctx.activeGroupId === null }) },
        });
        for (const [group] of __VLS_getVForSourceType((__VLS_ctx.templateGroups))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (group.id),
                ...{ class: "template-group-item" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!(__VLS_ctx.page === 'templates'))
                            return;
                        __VLS_ctx.activeGroupId = group.id;
                    } },
                ...{ class: ({ selected: __VLS_ctx.activeGroupId === group.id }) },
            });
            (group.name);
            if (__VLS_ctx.user?.role === 'company_admin' && !group.is_platform && __VLS_ctx.templateGroupIsEmpty(group.id)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!(__VLS_ctx.user?.role === 'company_admin' && !group.is_platform && __VLS_ctx.templateGroupIsEmpty(group.id)))
                                return;
                            __VLS_ctx.deleteTemplateGroup(group);
                        } },
                    ...{ class: "template-group-delete" },
                    'aria-label': (`删除空模板分类 ${group.name}`),
                    title: (`删除空模板分类 ${group.name}`),
                });
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        (__VLS_ctx.activeGroupId ? __VLS_ctx.templateGroups.find(g => g.id === __VLS_ctx.activeGroupId)?.name : '全部模板');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.filteredTemplates.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "template-grid" },
        });
        for (const [t] of __VLS_getVForSourceType((__VLS_ctx.filteredTemplates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (t.id),
                ...{ class: "template-card" },
            });
            if (__VLS_ctx.hasTemplateCover(t)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!(__VLS_ctx.hasTemplateCover(t)))
                                return;
                            __VLS_ctx.openTemplateCoverPreview(t);
                        } },
                    type: "button",
                    ...{ class: "template-image hasCover template-image-button" },
                    'aria-label': (`查看 ${t.name} 大图`),
                    title: "查看大图",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.templateCoverUrl(t)),
                    alt: (t.name),
                });
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "template-image" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (t.name.includes('T恤') ? '♧' : '♔');
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            (t.name);
            if (t.description) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "template-description" },
                });
                (t.description);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "template-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!(__VLS_ctx.page === 'templates'))
                            return;
                        __VLS_ctx.useTemplate(t);
                    } },
            });
            if (!t.is_platform && __VLS_ctx.user?.role === 'company_admin') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!(!t.is_platform && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            __VLS_ctx.openTemplateDialog(t);
                        } },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!(!t.is_platform && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            __VLS_ctx.deleteTemplate(t);
                        } },
                    ...{ class: "danger" },
                });
            }
        }
        if (!__VLS_ctx.filteredTemplates.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    else if (__VLS_ctx.page === 'pod') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "mode-tabs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: "active" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "pod-panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "pod-heading personal-resource-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "personal-resource-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!(__VLS_ctx.page === 'pod'))
                        return;
                    __VLS_ctx.openPersonalResourcesDialog();
                } },
            ...{ class: "secondary" },
        });
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openTeamResourcesDialog) },
                ...{ class: "secondary" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "requirement-label" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        if (__VLS_ctx.selectedTemplateAiPrompts().length || __VLS_ctx.personalPrompts.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "prompt-picker" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.applyTemplateAiPrompt) },
                value: (__VLS_ctx.creativePromptIndex),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "",
            });
            if (__VLS_ctx.selectedTemplateAiPrompts().length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.optgroup, __VLS_intrinsicElements.optgroup)({
                    label: "产品模板创作要求",
                });
                for (const [prompt, index] of __VLS_getVForSourceType((__VLS_ctx.selectedTemplateAiPrompts()))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (`template-${index}`),
                        value: (`template:${index}`),
                    });
                    (prompt.name);
                }
            }
            if (__VLS_ctx.personalPrompts.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.optgroup, __VLS_intrinsicElements.optgroup)({
                    label: "我的创作要求",
                });
                for (const [prompt] of __VLS_getVForSourceType((__VLS_ctx.personalPrompts))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (`personal-${prompt.id}`),
                        value: (`personal:${prompt.id}`),
                    });
                    (prompt.name);
                }
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.creativeRequirement),
            maxlength: "1000",
            placeholder: "例如：保留花朵细节，色彩清晰自然，印花完整贴合布料",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "pod-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "upload floral" },
            ...{ class: ({ hasAsset: __VLS_ctx.creativeAssets.length, invalid: __VLS_ctx.creativeAssetError }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.onCreativeAssetChange) },
            type: "file",
            multiple: true,
            accept: "image/png,image/jpeg,image/webp",
        });
        if (__VLS_ctx.creativeAssets.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.creativeAssets[0].preview),
                alt: "印花素材预览",
            });
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        if (__VLS_ctx.creativeAssets.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.creativeAssets.length))
                            return;
                        __VLS_ctx.showCreativeAssetsDialog = true;
                    } },
                type: "button",
                ...{ class: "asset-count" },
            });
            (__VLS_ctx.creativeAssets.length);
        }
        if (__VLS_ctx.creativeAssetError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "creative-asset-error" },
                role: "alert",
            });
            (__VLS_ctx.creativeAssetError);
        }
        if (__VLS_ctx.creativeAssets.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.creativeAssets.length))
                            return;
                        __VLS_ctx.showCreativeAssetsDialog = true;
                    } },
                ...{ class: "manage-assets" },
            });
            (__VLS_ctx.creativeAssets.length);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            ...{ class: "white-image-picker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.onCreativeTemplateChange) },
            value: (__VLS_ctx.selectedTemplateId),
        });
        for (const [t] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (t.id),
                value: (t.id),
            });
            (t.name);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "white-image-label" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.selectedWhiteImageId),
            disabled: (__VLS_ctx.personalResourcesLoading || !__VLS_ctx.personalWhiteImages.length),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
        });
        (__VLS_ctx.personalWhiteImages.length ? '请选择白底图' : '尚未设置白底图');
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.personalWhiteImages))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (item.id),
                value: (item.id),
            });
            (item.name);
        }
        if (__VLS_ctx.selectedWhiteImage) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-preview template-preview" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(__VLS_ctx.selectedWhiteImage.image_url)),
                alt: (__VLS_ctx.selectedWhiteImage.name),
            });
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "white-image-empty" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.personalWhiteImages.length ? '请从上方选择一张白底图' : '尚未设置该模板的白底图，请先设置');
            if (!__VLS_ctx.personalWhiteImages.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.selectedWhiteImage))
                                return;
                            if (!(!__VLS_ctx.personalWhiteImages.length))
                                return;
                            __VLS_ctx.openPersonalResourcesDialog('white-images');
                        } },
                });
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            ...{ class: "settings" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "settings-title" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "parameter-fields" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "parameter-field" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.creativeProvider),
            disabled: (!__VLS_ctx.availableAiProviders.length),
        });
        if (!__VLS_ctx.availableAiProviders.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "",
            });
        }
        for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.availableAiProviders))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (provider.provider),
                value: (provider.provider),
            });
            (provider.display_name);
            (provider.model);
            (provider.credential_configured ? '' : ' · 未配置密钥');
        }
        if (!__VLS_ctx.availableAiProviders.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "parameter-field" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.creativeRatio),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "parameter-field" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.creativeQuality),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
            ...{ class: "estimate" },
        });
        if (__VLS_ctx.creativeUploading) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "upload-progress" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.creativeUploadedCount);
            (__VLS_ctx.creativeAssets.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.progress, __VLS_intrinsicElements.progress)({
                max: (__VLS_ctx.creativeAssets.length),
                value: (__VLS_ctx.creativeUploadedCount),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.createTask) },
            ...{ class: "primary full" },
            disabled: (!__VLS_ctx.availableAiProviders.length || __VLS_ctx.creativeUploading || !__VLS_ctx.selectedWhiteImageId || Boolean(__VLS_ctx.creativeCredentialError)),
        });
        (__VLS_ctx.creativeUploading ? `上传中 ${__VLS_ctx.creativeUploadedCount}/${__VLS_ctx.creativeAssets.length}` : '✦ 开始印花贴合');
        if (__VLS_ctx.creativeCredentialError || __VLS_ctx.creativeSubmitError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "creative-submit-error" },
                role: "alert",
            });
            (__VLS_ctx.creativeCredentialError || __VLS_ctx.creativeSubmitError);
        }
    }
    else if (__VLS_ctx.page === 'tasks') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
            ...{ class: "task-type-tabs" },
            'aria-label': "任务类型",
        });
        for (const [label, type] of __VLS_getVForSourceType((__VLS_ctx.taskTypeLabels))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.page === 'tasks'))
                            return;
                        __VLS_ctx.switchTaskType(type);
                    } },
                key: (type),
                ...{ class: ({ active: __VLS_ctx.activeTaskType === type }) },
                disabled: (__VLS_ctx.taskListRefreshing),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
                ...{ class: "task-type-tabs-icon" },
                'aria-hidden': "true",
            });
            (type === 'sku_image' ? '🖼' : type === 'carousel' ? '🎞' : '🏷');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "task-type-tabs-label" },
            });
            (label);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "task-type-tabs-badge" },
            });
            (__VLS_ctx.taskTypeTotals[type] || 0);
            if (__VLS_ctx.taskTypeFilteredTotals[type] !== null) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({
                    ...{ class: "task-type-tabs-filter" },
                });
                (__VLS_ctx.taskTypeFilteredTotals[type]);
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading task-center-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "task-filter-row" },
        });
        if (__VLS_ctx.activeTaskType === 'sku_image') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "task-sku-search" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: (__VLS_ctx.taskSkuQuery),
                rows: "3",
                placeholder: "每行输入一个SKU",
            });
        }
        if (__VLS_ctx.activeTaskType === 'sku_image') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: (__VLS_ctx.taskTemplateFilterId),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (null),
            });
            for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (template.id),
                    value: (template.id),
                });
                (template.name);
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.taskStatusFilter),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: "",
        });
        for (const [label, status] of __VLS_getVForSourceType((__VLS_ctx.taskStatusLabel))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (status),
                value: (status),
            });
            (label);
        }
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: (__VLS_ctx.taskCreatorFilterId),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (null),
            });
            for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (member.id),
                    value: (member.id),
                });
                (member.name);
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "datetime-local",
        });
        (__VLS_ctx.taskCreatedFrom);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "datetime-local",
        });
        (__VLS_ctx.taskCreatedTo);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.searchTasks) },
            ...{ class: "primary task-search-button" },
            disabled: (__VLS_ctx.taskListRefreshing),
        });
        (__VLS_ctx.taskListRefreshing ? '搜索中…' : '搜索');
        if (__VLS_ctx.selectedTaskIds.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "task-batch-bar" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedTaskIds.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "task-batch-actions" },
            });
            if (__VLS_ctx.selectedRetryTaskIds.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.retrySelectedTasks) },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.batchRetryingTasks || __VLS_ctx.taskListRefreshing),
                });
                (__VLS_ctx.batchRetryingTasks ? '批量重试中…' : `批量重试（${__VLS_ctx.selectedRetryTaskIds.length}）`);
            }
            if (__VLS_ctx.activeTaskType === 'sku_image' && __VLS_ctx.selectedClaimableTaskIds.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openBatchClaimDialog) },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.batchClaimLoading || __VLS_ctx.batchClaiming || __VLS_ctx.batchRetryingTasks),
                });
                (__VLS_ctx.selectedClaimableTaskIds.length);
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-table task-table refreshable-list" },
            'aria-busy': (__VLS_ctx.taskListRefreshing),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead task-list-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-checkbox material-select-all" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.toggleAllSelectableTasks) },
            type: "checkbox",
            checked: (__VLS_ctx.allSelectableTasksSelected),
            indeterminate: (__VLS_ctx.someSelectableTasksSelected),
            disabled: (!__VLS_ctx.selectablePagedTasks.length),
            'aria-label': "全选本页可批量操作任务",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [task] of __VLS_getVForSourceType((__VLS_ctx.pagedTasks))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (task.id),
                ...{ class: "trow task-list-grid" },
                ...{ class: ({ selected: __VLS_ctx.selectedTaskIds.includes(task.id) }) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "material-checkbox" },
            });
            if (__VLS_ctx.taskCanBeSelected(task)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    ...{ onChange: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(__VLS_ctx.taskCanBeSelected(task)))
                                return;
                            __VLS_ctx.toggleTaskSelection(task.id);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedTaskIds.includes(task.id)),
                    'aria-label': (`选择任务 ${task.id}`),
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (task.id);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.taskTypeLabel(task));
            if (task.parameters?.print_url) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.parameters?.print_url))
                                return;
                            __VLS_ctx.openImagePreview(task.parameters.print_url, '创作素材');
                        } },
                    type: "button",
                    ...{ class: "task-material-thumbnail" },
                    title: "查看创作素材",
                    'aria-label': "查看创作素材大图",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(task.parameters.print_url)),
                    alt: "创作素材",
                });
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.template_name || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "ai-model-cell" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (task.provider === 'grsai' ? 'Grsai' : task.provider || '默认模型');
            if (task.provider_model) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (task.provider_model);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(task.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.created_by_name || '历史记录缺失');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "provider-task-id" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (task.provider_task_id || '—');
            if (task.provider_task_id) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.provider_task_id))
                                return;
                            __VLS_ctx.copyProviderTaskId(task);
                        } },
                    ...{ class: "copy-icon-button" },
                    title: "复制外部任务 ID",
                    'aria-label': "复制外部任务 ID",
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "task-progress-cell" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (__VLS_ctx.taskStatusClass(task.status)) },
            });
            (__VLS_ctx.taskStatusLabel[task.status] || task.status || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (task.progress?.total_prints || 0);
            (task.submit_attempts || 0);
            if (task.result_urls?.[0]) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.result_urls?.[0]))
                                return;
                            __VLS_ctx.openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`);
                        } },
                    type: "button",
                    ...{ class: "task-material-thumbnail" },
                    title: "查看结果图",
                    'aria-label': "查看首张结果图",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(task.result_urls[0])),
                    alt: (`任务 #${task.id} 结果图`),
                });
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ({ error: task.status === 'failed' }) },
            });
            (task.failure_reason || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "task-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.page === 'tasks'))
                            return;
                        __VLS_ctx.openTaskDetail(task);
                    } },
                ...{ class: "secondary" },
            });
            if (__VLS_ctx.activeTaskType !== 'sku_image') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(__VLS_ctx.activeTaskType !== 'sku_image'))
                                return;
                            __VLS_ctx.openImageWorkspaceFromTask(task);
                        } },
                    ...{ class: "secondary" },
                });
            }
            if (task.status === 'failed') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.status === 'failed'))
                                return;
                            __VLS_ctx.retryTaskResult(task);
                        } },
                    ...{ class: "secondary" },
                    disabled: (__VLS_ctx.retryingTaskId === task.id || __VLS_ctx.batchRetryingTasks),
                });
                (__VLS_ctx.retryingTaskId === task.id ? '重试中…' : '重试任务');
            }
            if (__VLS_ctx.activeTaskType === 'sku_image' && (task.result_count || task.result_urls?.length)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(__VLS_ctx.activeTaskType === 'sku_image' && (task.result_count || task.result_urls?.length)))
                                return;
                            __VLS_ctx.openClaimMaterialsDialog(task);
                        } },
                    ...{ class: "secondary" },
                });
            }
        }
        if (!__VLS_ctx.tasks.length && !__VLS_ctx.taskListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
        if (__VLS_ctx.taskTotal) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.taskTotal);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeTaskPageSize) },
                value: (__VLS_ctx.taskPageSize),
                disabled: (__VLS_ctx.taskListRefreshing),
            });
            for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (size),
                    value: (size),
                });
                (size);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.taskTotal))
                            return;
                        __VLS_ctx.changeTaskPage(__VLS_ctx.visibleTaskPage - 1);
                    } },
                disabled: (__VLS_ctx.taskListRefreshing || __VLS_ctx.visibleTaskPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.visibleTaskPage);
            (__VLS_ctx.taskPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.taskTotal))
                            return;
                        __VLS_ctx.changeTaskPage(__VLS_ctx.visibleTaskPage + 1);
                    } },
                disabled: (__VLS_ctx.taskListRefreshing || __VLS_ctx.visibleTaskPage === __VLS_ctx.taskPageCount),
            });
        }
        if (__VLS_ctx.taskListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "list-refresh-overlay" },
                role: "status",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
    }
    else if (__VLS_ctx.page === 'materials') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-usage-tabs" },
        });
        for (const [tab] of __VLS_getVForSourceType((__VLS_ctx.materialUsageTabs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.page === 'materials'))
                            return;
                        __VLS_ctx.changeMaterialUsageTab(tab.key);
                    } },
                key: (tab.key),
                ...{ class: ({ active: __VLS_ctx.activeMaterialUsageTab === tab.key }) },
            });
            (tab.label);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-filter-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-template-filter" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeMaterialFilter) },
            value: (__VLS_ctx.materialTemplateFilterId),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
        });
        for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (template.id),
                value: (template.id),
            });
            (template.name);
        }
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "material-template-filter" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeMaterialFilter) },
                value: (__VLS_ctx.materialCreatorFilterId),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (null),
            });
            for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (member.id),
                    value: (member.id),
                });
                (member.name);
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "primary material-upload-button" },
            ...{ class: ({ disabled: __VLS_ctx.materialUploading }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.chooseMaterialUploadFiles) },
            type: "file",
            multiple: true,
            accept: "image/png,image/jpeg,image/webp",
            disabled: (__VLS_ctx.materialUploading),
        });
        (__VLS_ctx.materialUploading ? '上传中…' : '上传本地素材');
        if (__VLS_ctx.materialUploadError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "error material-upload-error" },
            });
            (__VLS_ctx.materialUploadError);
        }
        if (__VLS_ctx.selectedMaterialAssetIds.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "material-draft-bar" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedMaterialAssetIds.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openMaterialDraftDialog) },
                ...{ class: "primary" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openMaterialBatchDraftDialog) },
                ...{ class: "primary" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.downloadSelectedMaterialAssets) },
                ...{ class: "secondary" },
                disabled: (__VLS_ctx.materialDownloading),
            });
            (__VLS_ctx.materialDownloading ? '下载中…' : '下载到本地');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.deleteSelectedMaterialAssets) },
                ...{ class: "negative" },
                disabled: (__VLS_ctx.materialDownloading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.selectedMaterialAssetIds.length))
                            return;
                        __VLS_ctx.selectedMaterialAssetIds = [];
                    } },
                ...{ class: "ghost" },
                disabled: (__VLS_ctx.materialDownloading),
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-table material-list refreshable-list" },
            'aria-busy': (__VLS_ctx.materialListRefreshing),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead material-thead" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-checkbox material-select-all" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.toggleAllCurrentMaterialAssets) },
            type: "checkbox",
            checked: (__VLS_ctx.allCurrentMaterialAssetsSelected),
            indeterminate: (__VLS_ctx.someCurrentMaterialAssetsSelected),
            disabled: (!__VLS_ctx.filteredMaterialAssets.some(asset => asset.sku)),
            'aria-label': "全选本页可用素材",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [asset] of __VLS_getVForSourceType((__VLS_ctx.filteredMaterialAssets))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (asset.id),
                ...{ class: "trow material-trow" },
                ...{ class: ({ selected: __VLS_ctx.selectedMaterialAssetIds.includes(asset.id) }) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "material-checkbox" },
                'aria-label': (`选择素材 ${asset.name}`),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.page === 'materials'))
                            return;
                        __VLS_ctx.toggleMaterialAsset(asset.id);
                    } },
                type: "checkbox",
                checked: (__VLS_ctx.selectedMaterialAssetIds.includes(asset.id)),
                disabled: (!asset.sku),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.page === 'materials'))
                            return;
                        __VLS_ctx.openImagePreview(asset.url, asset.name);
                    } },
                type: "button",
                ...{ class: "material-list-thumbnail" },
                title: (asset.name),
                'aria-label': (`预览素材 ${asset.name}`),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(asset.url)),
                alt: (asset.name),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({
                ...{ class: ({ error: !asset.sku }) },
            });
            (asset.sku || '无 SKU，请重新上传或领取');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (asset.template_name || __VLS_ctx.materialTemplateName(asset));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
                ...{ class: "chip" },
                ...{ class: (asset.source_type === 'ai_created' ? 'purple' : 'blue') },
            });
            (asset.source_type === 'ai_created' ? 'AI创作' : '本地上传');
            if (asset.source_task_id) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                    ...{ class: "material-source-task" },
                });
                (asset.source_task_id);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(asset.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (asset.created_by_name || '历史记录缺失');
        }
        if (!__VLS_ctx.filteredMaterialAssets.length && !__VLS_ctx.materialListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "empty" },
            });
            (__VLS_ctx.materialTotal ? '没有符合筛选条件的素材。' : '暂无素材。可上传本地图片，或在任务中心领取生成图片。');
        }
        if (__VLS_ctx.materialTotal) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.materialTotal);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeMaterialPageSize) },
                value: (__VLS_ctx.materialPageSize),
                disabled: (__VLS_ctx.materialListRefreshing),
            });
            for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (size),
                    value: (size),
                });
                (size);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.materialTotal))
                            return;
                        __VLS_ctx.changeMaterialPage(__VLS_ctx.visibleMaterialPage - 1);
                    } },
                disabled: (__VLS_ctx.materialListRefreshing || __VLS_ctx.visibleMaterialPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.visibleMaterialPage);
            (__VLS_ctx.materialPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.materialTotal))
                            return;
                        __VLS_ctx.changeMaterialPage(__VLS_ctx.visibleMaterialPage + 1);
                    } },
                disabled: (__VLS_ctx.materialListRefreshing || __VLS_ctx.visibleMaterialPage === __VLS_ctx.materialPageCount),
            });
        }
        if (__VLS_ctx.materialListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "list-refresh-overlay" },
                role: "status",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
    }
    else if (__VLS_ctx.page === 'drafts') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading draft-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-filter-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "draft-template-filter" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeDraftTemplateFilter) },
            value: (__VLS_ctx.draftTemplateFilterId),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
        });
        for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (template.id),
                value: (template.id),
            });
            (template.name);
        }
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "draft-template-filter" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeDraftCreatorFilter) },
                value: (__VLS_ctx.draftCreatorFilterId),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (null),
            });
            for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (member.id),
                    value: (member.id),
                });
                (member.name);
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-heading-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!(__VLS_ctx.page === 'drafts'))
                        return;
                    __VLS_ctx.page = 'materials';
                } },
            ...{ class: "primary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
            ...{ class: "draft-tabs" },
            'aria-label': "商品草稿流程",
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.draftTabs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        __VLS_ctx.changeDraftTab(item.key);
                    } },
                key: (item.key),
                ...{ class: ({ active: __VLS_ctx.activeDraftTab === item.key }) },
            });
            (item.label);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.draftTabCounts[item.key] || 0);
        }
        if (__VLS_ctx.activeDraftTab === 'carousel_pending' || __VLS_ctx.activeDraftTab === 'main_image_pending') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
                ...{ class: "draft-work-status-tabs" },
                'aria-label': "制作状态",
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.draftWorkStatusTabs))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.activeDraftTab === 'carousel_pending' || __VLS_ctx.activeDraftTab === 'main_image_pending'))
                                return;
                            __VLS_ctx.changeDraftWorkStatus(item.key);
                        } },
                    key: (item.key),
                    ...{ class: ({ active: __VLS_ctx.activeDraftWorkStatus === item.key }) },
                });
                (item.label);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (__VLS_ctx.draftWorkStatusCounts[item.key] || 0);
            }
        }
        if (__VLS_ctx.selectedDraftIds.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "draft-export-bar" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedDraftIds.length);
            (__VLS_ctx.MAX_DRAFT_BATCH_SIZE);
            if (__VLS_ctx.batchDispatchEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.selectedDraftIds.length))
                                return;
                            if (!(__VLS_ctx.batchDispatchEligible))
                                return;
                            __VLS_ctx.dispatchSelectedDrafts('carousel_pending');
                        } },
                    ...{ class: "primary" },
                    disabled: (!!__VLS_ctx.dispatchingDraftStage),
                });
                (__VLS_ctx.dispatchingDraftStage === 'carousel_pending' ? '分发中…' : '去做轮播图');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.selectedDraftIds.length))
                                return;
                            if (!(__VLS_ctx.batchDispatchEligible))
                                return;
                            __VLS_ctx.dispatchSelectedDrafts('main_image_pending');
                        } },
                    ...{ class: "secondary" },
                    disabled: (!!__VLS_ctx.dispatchingDraftStage),
                });
                (__VLS_ctx.dispatchingDraftStage === 'main_image_pending' ? '分发中…' : '去做主图');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.selectedDraftIds.length))
                                return;
                            if (!(__VLS_ctx.batchDispatchEligible))
                                return;
                            __VLS_ctx.dispatchSelectedDrafts('ready_to_publish');
                        } },
                    ...{ class: "secondary" },
                    disabled: (!!__VLS_ctx.dispatchingDraftStage),
                });
                (__VLS_ctx.dispatchingDraftStage === 'ready_to_publish' ? '分发中…' : '直接到待发布');
            }
            if (__VLS_ctx.batchCarouselEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openBatchCarouselDialog) },
                    ...{ class: "primary" },
                });
            }
            if (__VLS_ctx.batchCarouselSkipEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.batchSkipDraftCarousel) },
                    ...{ class: "secondary" },
                    disabled: (__VLS_ctx.batchCarouselSkipping),
                });
                (__VLS_ctx.batchCarouselSkipping ? '跳过中…' : '批量跳过轮播图制作');
            }
            if (__VLS_ctx.batchCarouselReviewEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.selectedDraftIds.length))
                                return;
                            if (!(__VLS_ctx.batchCarouselReviewEligible))
                                return;
                            __VLS_ctx.openBatchImageReview('carousel');
                        } },
                    ...{ class: "primary" },
                });
            }
            if (__VLS_ctx.batchMainImageEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openBatchMainImageDialog) },
                    ...{ class: "primary" },
                });
            }
            if (__VLS_ctx.batchMainImageSkipEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.batchSkipDraftMainImage) },
                    ...{ class: "secondary" },
                    disabled: (__VLS_ctx.batchMainImageSkipping),
                });
                (__VLS_ctx.batchMainImageSkipping ? '跳过中…' : '批量跳过首图制作');
            }
            if (__VLS_ctx.batchMainImageReviewEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.selectedDraftIds.length))
                                return;
                            if (!(__VLS_ctx.batchMainImageReviewEligible))
                                return;
                            __VLS_ctx.openBatchImageReview('main_image');
                        } },
                    ...{ class: "primary" },
                });
            }
            if (__VLS_ctx.batchMiaoshouPublishEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openBatchMiaoshouPublishDialog) },
                    ...{ class: "primary" },
                });
            }
            if (__VLS_ctx.tiktokExportEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openTiktokExportDialog) },
                    ...{ class: "primary" },
                });
            }
            if (__VLS_ctx.tiktokExportEligible) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openShopeeExportDialog) },
                    ...{ class: "primary" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.selectedDraftIds.length))
                            return;
                        __VLS_ctx.selectedDraftIds = [];
                    } },
                ...{ class: "ghost" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-table task-table refreshable-list" },
            'aria-busy': (__VLS_ctx.draftListRefreshing),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead draft-thead" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-checkbox" },
            'aria-label': "选择当前页商品草稿",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.togglePagedDrafts) },
            type: "checkbox",
            checked: (__VLS_ctx.allPagedDraftsSelected),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.pagedDrafts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (draft.id),
                ...{ class: "trow draft-trow" },
                ...{ class: ({ selected: __VLS_ctx.selectedDraftIds.includes(draft.id) }) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "material-checkbox" },
                'aria-label': (`选择商品草稿 ${draft.id}`),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        __VLS_ctx.toggleDraftSelection(draft.id);
                    } },
                type: "checkbox",
                checked: (__VLS_ctx.selectedDraftIds.includes(draft.id)),
                disabled: (__VLS_ctx.selectedDraftIds.length >= __VLS_ctx.MAX_DRAFT_BATCH_SIZE && !__VLS_ctx.selectedDraftIds.includes(draft.id)),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (draft.id);
            if (draft.image_urls?.[0]) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(draft.image_urls?.[0]))
                                return;
                            __VLS_ctx.openImagePreview(draft.image_urls[0], draft.title);
                        } },
                    ...{ class: "draft-thumbnail" },
                    title: "查看大图",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(draft.image_urls[0])),
                    alt: (draft.title),
                });
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.draftTemplateName(draft));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
                ...{ class: "draft-product-title" },
                title: (draft.title),
            });
            (draft.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.sku_items?.length || 1);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(draft.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.created_by_name || '历史记录缺失');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "draft-carousel-flag" },
                ...{ class: (draft.carousel_items?.length ? 'has' : 'none') },
            });
            (draft.carousel_items?.length ? '有' : '无');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.export_count || 0);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "draft-status-cell" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (draft.display_tab === 'published' ? 'blue' : 'purple') },
            });
            (__VLS_ctx.draftStatusLabels[draft.display_tab] || draft.display_tab);
            if (draft.display_tab === 'carousel_pending' || draft.display_tab === 'main_image_pending') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                ({ not_started: '未制作', in_progress: '制作中', awaiting_review: '待审核', failed: '制作失败' }[__VLS_ctx.draftWorkSummary(draft)?.work_status]);
                if (__VLS_ctx.draftWorkSummary(draft)?.work_status === 'in_progress' && __VLS_ctx.draftWorkSummary(draft)?.awaiting_selection) {
                }
            }
            if (__VLS_ctx.draftWorkSummary(draft)?.failed) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                    ...{ class: "error" },
                });
                (__VLS_ctx.draftWorkSummary(draft)?.failure_reasons?.[0] || '存在失败任务');
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "draft-trow-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        __VLS_ctx.openDraftEditDialog(draft);
                    } },
            });
            if (draft.display_tab === 'carousel_pending') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(draft.display_tab === 'carousel_pending'))
                                return;
                            __VLS_ctx.openCarouselImageWorkspace(draft);
                        } },
                    ...{ class: "primary compact-action" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(draft.display_tab === 'carousel_pending'))
                                return;
                            __VLS_ctx.skipDraftCarousel(draft);
                        } },
                    ...{ class: "secondary compact-action" },
                    disabled: (__VLS_ctx.skippingCarouselDraftId === draft.id),
                });
                (__VLS_ctx.skippingCarouselDraftId === draft.id ? '跳过中…' : '跳过轮播图制作');
            }
            else if (draft.display_tab === 'main_image_pending') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(draft.display_tab === 'carousel_pending'))
                                return;
                            if (!(draft.display_tab === 'main_image_pending'))
                                return;
                            __VLS_ctx.openFullImageWorkspace(draft, true);
                        } },
                    ...{ class: "primary compact-action" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(draft.display_tab === 'carousel_pending'))
                                return;
                            if (!(draft.display_tab === 'main_image_pending'))
                                return;
                            __VLS_ctx.skipDraftMainImage(draft);
                        } },
                    ...{ class: "secondary compact-action" },
                    disabled: (__VLS_ctx.skippingMainImageDraftId === draft.id),
                });
                (__VLS_ctx.skippingMainImageDraftId === draft.id ? '跳过中…' : '跳过首图制作');
            }
            else if (draft.display_tab !== 'pending') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(draft.display_tab === 'carousel_pending'))
                                return;
                            if (!!(draft.display_tab === 'main_image_pending'))
                                return;
                            if (!(draft.display_tab !== 'pending'))
                                return;
                            __VLS_ctx.openFullImageWorkspace(draft);
                        } },
                });
            }
            if (draft.display_tab === 'ready_to_publish') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(draft.display_tab === 'ready_to_publish'))
                                return;
                            __VLS_ctx.publishDraftToMiaoshou(draft);
                        } },
                    ...{ class: "primary compact-action" },
                    disabled: (__VLS_ctx.publishingDraftId === draft.id),
                });
                (__VLS_ctx.publishingDraftId === draft.id ? '处理中…' : '发布至妙手');
            }
        }
        if (!__VLS_ctx.filteredDrafts.length && !__VLS_ctx.draftListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "empty" },
            });
            (__VLS_ctx.draftTotal ? '没有符合筛选条件的商品草稿。' : '暂无商品草稿，请先在任务中心领取素材，或上传本地素材。');
        }
        else if (!__VLS_ctx.draftListRefreshing || __VLS_ctx.draftTotal) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.draftTotal);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeDraftPageSize) },
                value: (__VLS_ctx.draftPageSize),
                disabled: (__VLS_ctx.draftListRefreshing),
            });
            for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (size),
                    value: (size),
                });
                (size);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!!(!__VLS_ctx.filteredDrafts.length && !__VLS_ctx.draftListRefreshing))
                            return;
                        if (!(!__VLS_ctx.draftListRefreshing || __VLS_ctx.draftTotal))
                            return;
                        __VLS_ctx.changeDraftPage(__VLS_ctx.visibleDraftPage - 1);
                    } },
                disabled: (__VLS_ctx.draftListRefreshing || __VLS_ctx.visibleDraftPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.visibleDraftPage);
            (__VLS_ctx.draftPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!!(!__VLS_ctx.filteredDrafts.length && !__VLS_ctx.draftListRefreshing))
                            return;
                        if (!(!__VLS_ctx.draftListRefreshing || __VLS_ctx.draftTotal))
                            return;
                        __VLS_ctx.changeDraftPage(__VLS_ctx.visibleDraftPage + 1);
                    } },
                disabled: (__VLS_ctx.draftListRefreshing || __VLS_ctx.visibleDraftPage === __VLS_ctx.draftPageCount),
            });
        }
        if (__VLS_ctx.draftListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "list-refresh-overlay" },
                role: "status",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
    }
    else if (__VLS_ctx.page === 'product-library') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading product-library-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.downloadProductLibraryTemplate) },
                ...{ class: "secondary" },
                disabled: (__VLS_ctx.productLibraryDownloading),
            });
            (__VLS_ctx.productLibraryDownloading ? '下载中…' : '下载导入模版');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!(__VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.productLibraryFileInput?.click();
                    } },
                ...{ class: "primary" },
                disabled: (__VLS_ctx.productLibraryImporting),
            });
            (__VLS_ctx.productLibraryImporting ? '导入中…' : '导入');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.runProductLibraryStatistics) },
                ...{ class: "secondary" },
                type: "button",
                disabled: (__VLS_ctx.productLibraryStatisticsSubmitting || __VLS_ctx.productLibraryImporting),
            });
            (__VLS_ctx.productLibraryStatisticsSubmitting ? '提交中…' : '数据统计');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (__VLS_ctx.importProductLibrary) },
                ref: "productLibraryFileInput",
                type: "file",
                accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                hidden: true,
            });
            /** @type {typeof __VLS_ctx.productLibraryFileInput} */ ;
        }
        if (__VLS_ctx.productLibraryStatisticsTask) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "product-library-category-description" },
                role: "status",
            });
            if (__VLS_ctx.productLibraryStatisticsTask.status === 'queued') {
                (__VLS_ctx.productLibraryStatisticsTask.snapshot_date);
            }
            else if (__VLS_ctx.productLibraryStatisticsTask.status === 'running') {
                (__VLS_ctx.productLibraryStatisticsTask.snapshot_date);
            }
            else if (__VLS_ctx.productLibraryStatisticsTask.status === 'succeeded') {
                (__VLS_ctx.productLibraryStatisticsTask.through_date);
            }
            else {
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-usage-tabs product-library-tabs" },
            role: "tablist",
            'aria-label': "产品库分类",
        });
        for (const [tab] of __VLS_getVForSourceType((__VLS_ctx.productLibraryTabs.filter(item => item.key !== 'shops' || __VLS_ctx.user?.role === 'company_admin')))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        __VLS_ctx.changeProductLibraryTab(tab.key);
                    } },
                key: (tab.key),
                type: "button",
                role: "tab",
                'aria-selected': (__VLS_ctx.activeProductLibraryTab === tab.key),
                ...{ class: ({ active: __VLS_ctx.activeProductLibraryTab === tab.key }) },
            });
            (tab.label);
        }
        if (__VLS_ctx.productLibraryCategoryDescriptions[__VLS_ctx.activeProductLibraryTab]) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "product-library-category-description" },
            });
            (__VLS_ctx.productLibraryCategoryDescriptions[__VLS_ctx.activeProductLibraryTab]);
        }
        if (__VLS_ctx.activeProductLibraryTab === 'products' || __VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-filters" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-shop-filter" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.details, __VLS_intrinsicElements.details)({
                ref: "productLibraryShopFilterDetails",
            });
            /** @type {typeof __VLS_ctx.productLibraryShopFilterDetails} */ ;
            __VLS_asFunctionalElement(__VLS_intrinsicElements.summary, __VLS_intrinsicElements.summary)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                title: (__VLS_ctx.productLibraryShopSelectionLabel),
            });
            (__VLS_ctx.productLibraryShopSelectionLabel);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                'aria-hidden': "true",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-shop-filter-panel" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "search",
                placeholder: "搜索平台、站点或店铺",
                'aria-label': "搜索店铺",
            });
            (__VLS_ctx.productLibraryShopSearch);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-shop-filter-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.productLibraryShopOptions.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab === 'products' || __VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                            return;
                        __VLS_ctx.productLibrarySelectedShopIds = [];
                    } },
                type: "button",
                disabled: (!__VLS_ctx.productLibrarySelectedShopIds.length),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-shop-filter-options" },
            });
            for (const [shop] of __VLS_getVForSourceType((__VLS_ctx.productLibraryShopOptions))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                    key: (shop.id),
                    ...{ class: "product-library-shop-filter-option" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    type: "checkbox",
                    value: (shop.id),
                });
                (__VLS_ctx.productLibrarySelectedShopIds);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.label);
            }
            if (!__VLS_ctx.productLibraryShopOptions.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "product-library-shop-filter-empty" },
                });
            }
            if (__VLS_ctx.activeProductLibraryTab === 'products') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: (__VLS_ctx.productLibraryTemplateFilter),
                    disabled: (__VLS_ctx.productLibraryLoading),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: "",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: "unmatched",
                });
                for (const [item] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (item.id),
                        value: (String(item.id)),
                    });
                    (item.name);
                }
            }
            if (__VLS_ctx.activeProductLibraryTab === 'products') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    type: "search",
                    placeholder: "输入 SKU",
                    disabled: (__VLS_ctx.productLibraryLoading),
                });
                (__VLS_ctx.productLibrarySku);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.searchProductLibrary) },
                type: "button",
                ...{ class: "primary product-library-search-button" },
                disabled: (__VLS_ctx.productLibraryLoading || __VLS_ctx.productLibraryRankingLoading),
            });
        }
        if (__VLS_ctx.activeProductLibraryTab !== 'shops' && __VLS_ctx.selectedProductLibraryIds.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "draft-export-bar product-library-selection-bar" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedProductLibraryIds.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab !== 'shops' && __VLS_ctx.selectedProductLibraryIds.length))
                            return;
                        __VLS_ctx.openProductLibraryDraftDialog();
                    } },
                ...{ class: "primary" },
                disabled: (__VLS_ctx.productLibrarySelectionLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab !== 'shops' && __VLS_ctx.selectedProductLibraryIds.length))
                            return;
                        __VLS_ctx.openProductLibraryDraftDialog(true);
                    } },
                ...{ class: "primary" },
                disabled: (__VLS_ctx.productLibrarySelectionLoading),
            });
            if (__VLS_ctx.user?.role === 'company_admin') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.openProductLibraryTemplateDialog) },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.productLibrarySelectionLoading),
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab !== 'shops' && __VLS_ctx.selectedProductLibraryIds.length))
                            return;
                        __VLS_ctx.selectedProductLibraryIds = [];
                    } },
                ...{ class: "ghost" },
            });
        }
        if (__VLS_ctx.activeProductLibraryTab === 'products') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-table product-library-table" },
                'aria-busy': (__VLS_ctx.productLibraryLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead product-library-head" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "product-library-select-heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (__VLS_ctx.togglePagedProducts) },
                type: "checkbox",
                checked: (__VLS_ctx.allPagedProductsSelected),
                disabled: (!__VLS_ctx.selectableProductLibraryItems.length || __VLS_ctx.productLibraryLoading),
                'aria-label': "选择当前页产品",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            /** @type {[typeof ShopDataHeading, ]} */ ;
            // @ts-ignore
            const __VLS_0 = __VLS_asFunctionalComponent(ShopDataHeading, new ShopDataHeading({}));
            const __VLS_1 = __VLS_0({}, ...__VLS_functionalComponentArgsRest(__VLS_0));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.activeProductLibraryTab === 'products' ? __VLS_ctx.productLibraryItems : []))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (item.id),
                    ...{ class: "trow product-library-row" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "product-library-product-cell" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    ...{ onChange: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            __VLS_ctx.toggleProductLibrarySelection(item);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedProductLibraryIds.includes(item.id)),
                    disabled: (__VLS_ctx.selectedProductLibraryIds.length >= 100 && !__VLS_ctx.selectedProductLibraryIds.includes(item.id)),
                    'aria-label': (`选择产品 ${item.sku}`),
                });
                if (item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.openImagePreview(item.image_url, item.title || item.sku);
                            } },
                        ...{ class: "product-library-image" },
                        title: "查看大图",
                        'aria-label': (`查看 ${item.sku} 商品大图`),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        ...{ onError: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.productLibraryBrokenImages.push(item.id);
                            } },
                        key: (item.image_url),
                        src: (__VLS_ctx.imageUrl(item.image_url)),
                        alt: (item.title || item.sku),
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "product-library-image" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-code" },
                    title: (item.sku),
                });
                (item.sku);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.template);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-title" },
                    title: (item.title),
                });
                (item.title || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-shop-data" },
                });
                for (const [shop] of __VLS_getVForSourceType((item.shop_data))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        key: (`${shop.source_id}-${shop.product_id}`),
                    });
                    (shop.shop_name);
                    (shop.product_id);
                    (shop.sales_quantity);
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.material_created_by_name || '');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.material_created_at != null ? new Date(item.material_created_at).toLocaleString() : '');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (item.order_count);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (item.sales_quantity);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            __VLS_ctx.openProductLibraryOrders(item);
                        } },
                    ...{ class: "product-library-detail-button" },
                    type: "button",
                    title: "查看详情",
                    'aria-label': (`查看 ${item.sku} 的订单详情`),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
                    viewBox: "0 0 24 24",
                    fill: "none",
                    stroke: "currentColor",
                    'stroke-width': "1.8",
                    'stroke-linecap': "round",
                    'stroke-linejoin': "round",
                    'aria-hidden': "true",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
                    d: "M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.circle)({
                    cx: "12",
                    cy: "12",
                    r: "2.8",
                });
            }
            if (__VLS_ctx.activeProductLibraryTab !== 'products') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "empty" },
                });
            }
            else if (!__VLS_ctx.productLibraryItems.length && !__VLS_ctx.productLibraryLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "empty" },
                });
                (__VLS_ctx.productLibraryTotal ? '没有符合筛选条件的产品。' : __VLS_ctx.user?.role === 'company_admin' ? '暂无产品，请先下载模版并导入历史订单。' : '暂无可查看的产品，请联系管理员分配店铺。');
            }
            if (__VLS_ctx.activeProductLibraryTab === 'products') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                    ...{ class: "draft-pagination product-library-pagination" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.productLibraryTotal);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    ...{ onChange: (__VLS_ctx.changeProductLibraryPageSize) },
                    value: (__VLS_ctx.productLibraryPageSize),
                    disabled: (__VLS_ctx.productLibraryLoading),
                });
                for (const [size] of __VLS_getVForSourceType((__VLS_ctx.productLibraryPageSizeOptions))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (size),
                        value: (size),
                    });
                    (size);
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            __VLS_ctx.changeProductLibraryPage(__VLS_ctx.productLibraryPage - 1);
                        } },
                    disabled: (__VLS_ctx.productLibraryLoading || __VLS_ctx.productLibraryPage === 1),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.productLibraryPage);
                (__VLS_ctx.productLibraryPageCount);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            __VLS_ctx.changeProductLibraryPage(__VLS_ctx.productLibraryPage + 1);
                        } },
                    disabled: (__VLS_ctx.productLibraryLoading || __VLS_ctx.productLibraryPage === __VLS_ctx.productLibraryPageCount),
                });
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                    ...{ class: "draft-pagination product-library-pagination" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
            if (__VLS_ctx.activeProductLibraryTab === 'products' && __VLS_ctx.productLibraryLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "list-refresh-overlay" },
                    role: "status",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
        else if (__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-ranking-section" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "product-library-category-description" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-table product-library-table" },
                'aria-busy': (__VLS_ctx.productLibraryShopsLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead" },
                ...{ style: {} },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [shop] of __VLS_getVForSourceType((__VLS_ctx.productLibraryShops))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (shop.id),
                    ...{ class: "trow" },
                    ...{ style: {} },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.platform);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.site);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (shop.shop_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    ...{ onChange: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            __VLS_ctx.assignProductLibraryShop(shop, $event);
                        } },
                    value: (shop.assigned_user_id ?? ''),
                    disabled: (__VLS_ctx.productLibraryAssigningId === shop.id),
                    'aria-label': (`分配 ${shop.shop_name} 的负责运营`),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: "",
                });
                for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members.filter(item => (item.role === 'member' || item.role === 'team_leader') && (item.is_active || item.id === shop.assigned_user_id))))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (member.id),
                        value: (member.id),
                    });
                    (member.name);
                    (__VLS_ctx.operatorGroupName(member.group_id));
                    (__VLS_ctx.memberRoleLabel(member));
                }
            }
            if (!__VLS_ctx.productLibraryShops.length && !__VLS_ctx.productLibraryShopsLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
            if (__VLS_ctx.productLibraryShopsLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "list-refresh-overlay" },
                    role: "status",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
        else if (__VLS_ctx.activeProductLibraryTab === 'stagnant') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-ranking-section" },
            });
            if (__VLS_ctx.user?.role === 'company_admin') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "product-library-filters" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    ...{ onChange: (__VLS_ctx.changeStagnantCreator) },
                    value: (__VLS_ctx.stagnantCreatorId),
                    disabled: (__VLS_ctx.stagnantLoading),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: (null),
                });
                for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (member.id),
                        value: (member.id),
                    });
                    (member.name);
                }
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-table product-library-table" },
                'aria-busy': (__VLS_ctx.stagnantLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead product-library-stagnant-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "product-library-select-heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (__VLS_ctx.togglePagedProducts) },
                type: "checkbox",
                checked: (__VLS_ctx.allPagedProductsSelected),
                disabled: (!__VLS_ctx.selectableProductLibraryItems.length || __VLS_ctx.productLibrarySelectionLoading),
                'aria-label': "选择当前页数据",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.stagnantMaterials))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (item.id),
                    ...{ class: "trow product-library-stagnant-grid" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "product-library-product-cell" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    ...{ onChange: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                return;
                            __VLS_ctx.toggleProductLibrarySelection(item);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedProductLibraryIds.includes(item.id)),
                    disabled: (__VLS_ctx.productLibrarySelectionLoading || (__VLS_ctx.selectedProductLibraryIds.length >= 100 && !__VLS_ctx.selectedProductLibraryIds.includes(item.id))),
                    'aria-label': (`选择 ${item.sku || '素材'}`),
                });
                if (item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.openImagePreview(item.image_url, item.sku);
                            } },
                        ...{ class: "product-library-image" },
                        title: "查看大图",
                        'aria-label': (`查看 ${item.sku} 素材大图`),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        ...{ onError: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.productLibraryBrokenImages.push(item.id);
                            } },
                        src: (__VLS_ctx.imageUrl(item.image_url)),
                        alt: (item.sku),
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "product-library-image" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-code" },
                    title: (item.sku),
                });
                (item.sku);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.template);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.created_by_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (new Date(item.created_at).toLocaleString());
            }
            if (!__VLS_ctx.stagnantMaterials.length && !__VLS_ctx.stagnantLoading && !__VLS_ctx.stagnantError) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "empty" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination product-library-stagnant-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.stagnantTotal);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeStagnantPageSize) },
                value: (__VLS_ctx.stagnantPageSize),
                disabled: (__VLS_ctx.stagnantLoading),
            });
            for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (size),
                    value: (size),
                });
                (size);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                            return;
                        __VLS_ctx.changeStagnantPage(__VLS_ctx.stagnantPage - 1);
                    } },
                disabled: (__VLS_ctx.stagnantLoading || __VLS_ctx.stagnantPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.stagnantPage);
            (__VLS_ctx.stagnantPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                            return;
                        __VLS_ctx.changeStagnantPage(__VLS_ctx.stagnantPage + 1);
                    } },
                disabled: (__VLS_ctx.stagnantLoading || __VLS_ctx.stagnantPage === __VLS_ctx.stagnantPageCount),
            });
            if (__VLS_ctx.stagnantLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "list-refresh-overlay" },
                    role: "status",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
        else if (__VLS_ctx.activeProductLibraryTab === 'new_images') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-ranking-section" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-filters" },
            });
            if (__VLS_ctx.user?.role === 'company_admin') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    ...{ onChange: (__VLS_ctx.changeNewImagesFilters) },
                    value: (__VLS_ctx.newImagesCreatorId),
                    disabled: (__VLS_ctx.newImagesLoading),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: (null),
                });
                for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (member.id),
                        value: (member.id),
                    });
                    (member.name);
                }
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeNewImagesFilters) },
                value: (__VLS_ctx.newImagesUsageStatus),
                disabled: (__VLS_ctx.newImagesLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "all",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "unused",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "used",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-table product-library-table" },
                'aria-busy': (__VLS_ctx.newImagesLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead product-library-new-images-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "product-library-select-heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (__VLS_ctx.togglePagedProducts) },
                type: "checkbox",
                checked: (__VLS_ctx.allPagedProductsSelected),
                disabled: (!__VLS_ctx.selectableProductLibraryItems.length || __VLS_ctx.productLibrarySelectionLoading),
                'aria-label': "选择当前页数据",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.newImages))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (item.id),
                    ...{ class: "trow product-library-new-images-grid" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "product-library-product-cell" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    ...{ onChange: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                return;
                            if (!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                return;
                            __VLS_ctx.toggleProductLibrarySelection(item);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedProductLibraryIds.includes(item.id)),
                    disabled: (__VLS_ctx.productLibrarySelectionLoading || (__VLS_ctx.selectedProductLibraryIds.length >= 100 && !__VLS_ctx.selectedProductLibraryIds.includes(item.id))),
                    'aria-label': (`选择 ${item.sku || '素材'}`),
                });
                if (item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.openImagePreview(item.image_url, item.sku || '素材');
                            } },
                        ...{ class: "product-library-image" },
                        title: "查看大图",
                        'aria-label': (`查看 ${item.sku || '素材'} 大图`),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        ...{ onError: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.productLibraryBrokenImages.push(item.id);
                            } },
                        src: (__VLS_ctx.imageUrl(item.image_url)),
                        alt: (item.sku || '素材'),
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "product-library-image" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-code" },
                    title: (item.sku || ''),
                });
                (item.sku || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.template);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.created_by_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (new Date(item.created_at).toLocaleString());
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.usage_status === 'used' ? '已使用' : '未使用');
            }
            if (!__VLS_ctx.newImages.length && !__VLS_ctx.newImagesLoading && !__VLS_ctx.newImagesError) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "empty" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination product-library-new-images-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.newImagesTotal);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeNewImagesPageSize) },
                value: (__VLS_ctx.newImagesPageSize),
                disabled: (__VLS_ctx.newImagesLoading),
            });
            for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (size),
                    value: (size),
                });
                (size);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                            return;
                        __VLS_ctx.changeNewImagesPage(__VLS_ctx.newImagesPage - 1);
                    } },
                disabled: (__VLS_ctx.newImagesLoading || __VLS_ctx.newImagesPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.newImagesPage);
            (__VLS_ctx.newImagesPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                            return;
                        if (!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                            return;
                        __VLS_ctx.changeNewImagesPage(__VLS_ctx.newImagesPage + 1);
                    } },
                disabled: (__VLS_ctx.newImagesLoading || __VLS_ctx.newImagesPage === __VLS_ctx.newImagesPageCount),
            });
            if (__VLS_ctx.newImagesLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "list-refresh-overlay" },
                    role: "status",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
        else if (!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-table product-library-table" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "empty" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination product-library-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "product-library-ranking-section" },
            });
            if (__VLS_ctx.productLibraryRankingDate) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "product-library-ranking-date" },
                });
                (__VLS_ctx.productLibraryRankingDate);
                (__VLS_ctx.productLibraryRankingThroughDate);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "draft-table product-library-table" },
                'aria-busy': (__VLS_ctx.productLibraryRankingLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead product-library-ranking-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "product-library-select-heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (__VLS_ctx.togglePagedProducts) },
                type: "checkbox",
                checked: (__VLS_ctx.allPagedProductsSelected),
                disabled: (!__VLS_ctx.selectableProductLibraryItems.length || __VLS_ctx.productLibrarySelectionLoading),
                'aria-label': "选择当前页数据",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            /** @type {[typeof ShopDataHeading, ]} */ ;
            // @ts-ignore
            const __VLS_3 = __VLS_asFunctionalComponent(ShopDataHeading, new ShopDataHeading({}));
            const __VLS_4 = __VLS_3({}, ...__VLS_functionalComponentArgsRest(__VLS_3));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.productLibraryRankingItems))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (item.id),
                    ...{ class: "trow product-library-ranking-grid" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({
                    ...{ class: "product-library-ranking-rank" },
                });
                (item.rank);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "product-library-product-cell" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    ...{ onChange: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                return;
                            if (!!(!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                return;
                            __VLS_ctx.toggleProductLibrarySelection(item);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedProductLibraryIds.includes(item.id)),
                    disabled: (__VLS_ctx.productLibrarySelectionLoading || (__VLS_ctx.selectedProductLibraryIds.length >= 100 && !__VLS_ctx.selectedProductLibraryIds.includes(item.id))),
                    'aria-label': (`选择 ${item.sku || '素材'}`),
                });
                if (item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                    return;
                                if (!!(!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.openImagePreview(item.image_url, item.title || item.sku);
                            } },
                        ...{ class: "product-library-image" },
                        title: "查看大图",
                        'aria-label': (`查看 ${item.sku} 商品大图`),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        ...{ onError: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                    return;
                                if (!!(!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                    return;
                                if (!(item.image_url && !__VLS_ctx.productLibraryBrokenImages.includes(item.id)))
                                    return;
                                __VLS_ctx.productLibraryBrokenImages.push(item.id);
                            } },
                        src: (__VLS_ctx.imageUrl(item.image_url)),
                        alt: (item.title || item.sku),
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "product-library-image" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-code" },
                    title: (item.sku),
                });
                (item.sku);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.template);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-title" },
                    title: (item.title),
                });
                (item.title || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "product-library-shop-data" },
                });
                for (const [shop] of __VLS_getVForSourceType((item.shop_data))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        key: (`${shop.source_id}-${shop.product_id}`),
                    });
                    (shop.shop_name);
                    (shop.product_id);
                    (shop.sales_quantity);
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.material_created_by_name || '');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.material_created_at != null ? new Date(item.material_created_at).toLocaleString() : '');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (item.order_count);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (item.sales_quantity);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                return;
                            if (!!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                return;
                            if (!!(!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                return;
                            __VLS_ctx.openProductLibraryOrders(item);
                        } },
                    ...{ class: "product-library-detail-button" },
                    type: "button",
                    title: "查看详情",
                    'aria-label': (`查看 ${item.sku} 的订单详情`),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
                    viewBox: "0 0 24 24",
                    fill: "none",
                    stroke: "currentColor",
                    'stroke-width': "1.8",
                    'stroke-linecap': "round",
                    'stroke-linejoin': "round",
                    'aria-hidden': "true",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
                    d: "M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.circle)({
                    cx: "12",
                    cy: "12",
                    r: "2.8",
                });
            }
            if (!__VLS_ctx.productLibraryRankingItems.length && !__VLS_ctx.productLibraryRankingLoading && !__VLS_ctx.productLibraryRankingError) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "empty" },
                });
                (__VLS_ctx.productLibraryRankingDate ? '该榜单暂无符合条件的产品。' : __VLS_ctx.user?.role === 'company_admin' ? '尚未生成榜单，点击“数据统计”开始后台统计。' : '尚未生成榜单，请联系管理员进行数据统计。');
            }
            if (__VLS_ctx.productLibraryRankingDate) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                    ...{ class: "draft-pagination product-library-ranking-pagination" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.productLibraryRankingTotal);
                if (!__VLS_ctx.productLibraryTopTabKeys.has(__VLS_ctx.activeProductLibraryTab)) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                        ...{ onChange: (__VLS_ctx.changeProductLibraryRankingPageSize) },
                        value: (__VLS_ctx.productLibraryRankingPageSize),
                        disabled: (__VLS_ctx.productLibraryRankingLoading),
                    });
                    for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                            key: (size),
                            value: (size),
                        });
                        (size);
                    }
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                    return;
                                if (!!(!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                    return;
                                if (!(__VLS_ctx.productLibraryRankingDate))
                                    return;
                                if (!(!__VLS_ctx.productLibraryTopTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                    return;
                                __VLS_ctx.changeProductLibraryRankingPage(__VLS_ctx.productLibraryRankingPage - 1);
                            } },
                        disabled: (__VLS_ctx.productLibraryRankingLoading || __VLS_ctx.productLibraryRankingPage === 1),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (__VLS_ctx.productLibraryRankingPage);
                    (__VLS_ctx.productLibraryRankingPageCount);
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'products'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'stagnant'))
                                    return;
                                if (!!(__VLS_ctx.activeProductLibraryTab === 'new_images'))
                                    return;
                                if (!!(!__VLS_ctx.productLibraryRankingTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                    return;
                                if (!(__VLS_ctx.productLibraryRankingDate))
                                    return;
                                if (!(!__VLS_ctx.productLibraryTopTabKeys.has(__VLS_ctx.activeProductLibraryTab)))
                                    return;
                                __VLS_ctx.changeProductLibraryRankingPage(__VLS_ctx.productLibraryRankingPage + 1);
                            } },
                        disabled: (__VLS_ctx.productLibraryRankingLoading || __VLS_ctx.productLibraryRankingPage === __VLS_ctx.productLibraryRankingPageCount),
                    });
                }
            }
            if (__VLS_ctx.productLibraryRankingLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "list-refresh-overlay" },
                    role: "status",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
    }
    else if (__VLS_ctx.page === 'miaoshou-collect-box') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-usage-tabs" },
            role: "tablist",
            'aria-label': "妙手管理分类",
        });
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!(__VLS_ctx.page === 'miaoshou-collect-box'))
                            return;
                        if (!(__VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.changeMiaoshouTab('shops');
                    } },
                role: "tab",
                'aria-selected': (__VLS_ctx.activeMiaoshouTab === 'shops'),
                ...{ class: ({ active: __VLS_ctx.activeMiaoshouTab === 'shops' }) },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    __VLS_ctx.changeMiaoshouTab('collect_box');
                } },
            role: "tab",
            'aria-selected': (__VLS_ctx.activeMiaoshouTab === 'collect_box'),
            ...{ class: ({ active: __VLS_ctx.activeMiaoshouTab === 'collect_box' }) },
        });
        if (__VLS_ctx.activeMiaoshouTab === 'shops' && __VLS_ctx.user?.role === 'company_admin') {
            if (__VLS_ctx.shopError) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "error" },
                });
                (__VLS_ctx.shopError);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "shop-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "miaoshou-status" },
                ...{ class: (__VLS_ctx.company?.miaoshou_configured ? 'configured' : 'missing') },
            });
            (__VLS_ctx.company?.miaoshou_configured ? '妙手 API Key 已配置' : '请先配置妙手 API Key');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openMiaoshouDialog) },
                ...{ class: "secondary" },
                disabled: (__VLS_ctx.miaoshouSaving || __VLS_ctx.shopLoading),
            });
            (__VLS_ctx.company?.miaoshou_configured ? '更新 API Key' : '配置 API Key');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.loadMiaoshouShops) },
                ...{ class: "primary" },
                disabled: (__VLS_ctx.shopLoading || __VLS_ctx.miaoshouSaving || !__VLS_ctx.company?.miaoshou_configured),
            });
            (__VLS_ctx.shopLoading ? '同步中…' : '↻ 同步妙手店铺');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "draft-table" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead" },
                ...{ style: {} },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [shop] of __VLS_getVForSourceType((__VLS_ctx.crossBorderManagedShops))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (shop.id),
                    ...{ class: "trow" },
                    ...{ style: {} },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.external_shop_id || shop.id);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (shop.name || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.nickname || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.platform || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.region || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "chip" },
                    ...{ class: (shop.auth_status ? 'blue' : 'orange') },
                });
                (shop.auth_status || '未知');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.auth_expires_at || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (shop.manager_users.length ? shop.manager_users.map((member) => member.name).join('、') : '暂未分配');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                return;
                            if (!(__VLS_ctx.activeMiaoshouTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            __VLS_ctx.openShopManagersDialog(shop);
                        } },
                });
            }
            if (!__VLS_ctx.crossBorderManagedShops.length && !__VLS_ctx.shopLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
                (__VLS_ctx.company?.miaoshou_configured ? '暂无已同步店铺，点击“同步妙手店铺”开始获取。' : '配置妙手 API Key 后即可同步店铺。');
            }
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "section-heading draft-heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            if (__VLS_ctx.collectBoxLastSyncedAt) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                    ...{ class: "collect-box-sync-time" },
                });
                (new Date(__VLS_ctx.collectBoxLastSyncedAt).toLocaleString());
            }
            if (!__VLS_ctx.collectBoxConfigured) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "error" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "collect-box-filters" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onKeyup: (__VLS_ctx.changeCollectBoxFilters) },
                placeholder: "搜索商品标题",
            });
            (__VLS_ctx.collectBoxQuery);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.changeCollectBoxFilters) },
                ...{ class: "secondary" },
                disabled: (__VLS_ctx.collectBoxLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "draft-table collect-box-table" },
                'aria-busy': (__VLS_ctx.collectBoxLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "thead collect-box-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.collectBoxItems))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (item.id),
                    ...{ class: "trow collect-box-grid" },
                });
                if (item.thumbnail) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                    return;
                                if (!!(__VLS_ctx.activeMiaoshouTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!(item.thumbnail))
                                    return;
                                __VLS_ctx.openImagePreview(item.thumbnail, item.title);
                            } },
                        ...{ class: "collect-box-thumbnail" },
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        src: (__VLS_ctx.imageUrl(item.thumbnail)),
                        alt: (item.title),
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "collect-box-title" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
                    title: (item.title),
                });
                (item.title);
                if (item.reason) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                        ...{ class: "error" },
                    });
                    (item.reason);
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.status || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.remote_created_at ? new Date(item.remote_created_at).toLocaleString() : '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.remote_updated_at ? new Date(item.remote_updated_at).toLocaleString() : '—');
            }
            if (!__VLS_ctx.collectBoxItems.length && !__VLS_ctx.collectBoxLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
                (__VLS_ctx.collectBoxInitialSyncedAt ? '没有符合筛选条件的采集箱商品。' : '尚未同步采集箱，系统将在配置妙手 API Key 后自动同步近 7 天数据。');
            }
            if (__VLS_ctx.collectBoxTotal) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                    ...{ class: "draft-pagination" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.collectBoxTotal);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    ...{ onChange: (__VLS_ctx.changeCollectBoxFilters) },
                    value: (__VLS_ctx.collectBoxPageSize),
                    disabled: (__VLS_ctx.collectBoxLoading),
                });
                for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: (size),
                        value: (size),
                    });
                    (size);
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                return;
                            if (!!(__VLS_ctx.activeMiaoshouTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(__VLS_ctx.collectBoxTotal))
                                return;
                            __VLS_ctx.changeCollectBoxPage(__VLS_ctx.collectBoxPage - 1);
                        } },
                    disabled: (__VLS_ctx.collectBoxLoading || __VLS_ctx.collectBoxPage === 1),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.collectBoxPage);
                (__VLS_ctx.collectBoxPageCount);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                return;
                            if (!!(__VLS_ctx.activeMiaoshouTab === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(__VLS_ctx.collectBoxTotal))
                                return;
                            __VLS_ctx.changeCollectBoxPage(__VLS_ctx.collectBoxPage + 1);
                        } },
                    disabled: (__VLS_ctx.collectBoxLoading || __VLS_ctx.collectBoxPage === __VLS_ctx.collectBoxPageCount),
                });
            }
            if (__VLS_ctx.collectBoxLoading) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "list-refresh-overlay" },
                    role: "status",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
    }
    else if (__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.refreshMemberList) },
            ...{ class: "ghost" },
            disabled: (__VLS_ctx.memberListRefreshing),
        });
        (__VLS_ctx.memberListRefreshing ? '刷新中…' : '↻ 刷新');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading operator-groups-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    __VLS_ctx.openOperatorGroupDialog();
                } },
            ...{ class: "primary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "operator-group-list" },
        });
        for (const [group] of __VLS_getVForSourceType((__VLS_ctx.operatorGroups))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (group.id),
                ...{ class: "operator-group-card" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            (group.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (__VLS_ctx.members.find(member => member.id === group.leader_user_id)?.name || '—');
            (__VLS_ctx.operatorGroupMembers(group.id).length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "operator-group-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                            return;
                        if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.openOperatorGroupDialog(group);
                    } },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                            return;
                        if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.deleteOperatorGroup(group);
                    } },
                ...{ class: "negative" },
            });
        }
        if (!__VLS_ctx.operatorGroups.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "operator-groups-empty" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading member-list-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "member-list-title" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.members.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    __VLS_ctx.openMemberDialog();
                } },
            ...{ class: "primary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-table refreshable-list member-list-scroll" },
            'aria-busy': (__VLS_ctx.memberListRefreshing),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead member-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (member.id),
                ...{ class: "trow member-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (member.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (member.user_code || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.memberRoleLabel(member));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (member.group_id ? __VLS_ctx.operatorGroupName(member.group_id) : '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (member.email);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (member.is_active ? 'blue' : 'orange') },
            });
            (member.is_active ? '启用中' : '已停用');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(member.created_at).toLocaleDateString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "member-row-actions" },
            });
            if (member.role === 'member' || member.role === 'team_leader') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                return;
                            if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(member.role === 'member' || member.role === 'team_leader'))
                                return;
                            __VLS_ctx.openMemberDialog(member);
                        } },
                });
                if (member.role !== 'team_leader') {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.token))
                                    return;
                                if (!!(__VLS_ctx.page === 'dashboard'))
                                    return;
                                if (!!(__VLS_ctx.page === 'templates'))
                                    return;
                                if (!!(__VLS_ctx.page === 'pod'))
                                    return;
                                if (!!(__VLS_ctx.page === 'tasks'))
                                    return;
                                if (!!(__VLS_ctx.page === 'materials'))
                                    return;
                                if (!!(__VLS_ctx.page === 'drafts'))
                                    return;
                                if (!!(__VLS_ctx.page === 'product-library'))
                                    return;
                                if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                    return;
                                if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                    return;
                                if (!(member.role === 'member' || member.role === 'team_leader'))
                                    return;
                                if (!(member.role !== 'team_leader'))
                                    return;
                                __VLS_ctx.toggleMember(member);
                            } },
                        ...{ class: (member.is_active ? 'negative' : 'positive') },
                    });
                    (member.is_active ? '停用' : '启用');
                }
            }
            for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.memberCredentialProviders))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                return;
                            if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            __VLS_ctx.openMemberCredentialDialog(member, provider);
                        } },
                    key: (provider.credential_provider),
                    ...{ class: "credential-button" },
                    ...{ class: (member.ai_provider_credentials?.[provider.credential_provider] ? 'configured' : 'missing') },
                });
                (provider.credential_display_name);
                (member.ai_provider_credentials?.[provider.credential_provider] ? '已配置' : '待配置');
            }
        }
        if (!__VLS_ctx.members.length && !__VLS_ctx.memberListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
        if (__VLS_ctx.memberListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "list-refresh-overlay" },
                role: "status",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
    }
    else if (__VLS_ctx.page === 'shops') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        if (__VLS_ctx.shopError && __VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "error" },
            });
            (__VLS_ctx.shopError);
        }
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "shop-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "miaoshou-status" },
                ...{ class: (__VLS_ctx.company?.hubstudio_configured ? 'configured' : 'missing') },
            });
            (__VLS_ctx.company?.hubstudio_configured ? 'HubStudio API 已配置' : '请配置 HubStudio API');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openHubstudioDialog) },
                ...{ class: "secondary" },
            });
            (__VLS_ctx.company?.hubstudio_configured ? '更新' : '配置');
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.loadHubUploadTasks) },
            ...{ class: "ghost" },
            disabled: (__VLS_ctx.hubUploadLoading),
        });
        (__VLS_ctx.hubUploadLoading ? '刷新中…' : '↻ 刷新');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "hub-upload-filters" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeHubUploadCreator) },
            value: (__VLS_ctx.hubUploadTemplateId),
            disabled: (__VLS_ctx.hubUploadLoading),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
        });
        for (const [template] of __VLS_getVForSourceType((__VLS_ctx.hubUploadTemplates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (template.id),
                value: (template.id),
            });
            (template.name);
        }
        if (__VLS_ctx.user?.role === 'company_admin') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeHubUploadCreator) },
                value: (__VLS_ctx.hubUploadCreatorId),
                disabled: (__VLS_ctx.hubUploadLoading),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (null),
            });
            for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (member.id),
                    value: (member.id),
                });
                (member.name);
            }
        }
        if (__VLS_ctx.hubUploadError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "error" },
                role: "alert",
            });
            (__VLS_ctx.hubUploadError);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-table refreshable-list hub-upload-table" },
            'aria-busy': (__VLS_ctx.hubUploadLoading),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead hub-upload-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [task] of __VLS_getVForSourceType((__VLS_ctx.hubUploadTasks))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (task.id),
                ...{ class: "trow hub-upload-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.id);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.template_name || '模版未知');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.product_count);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.created_by_name || `账号 #${task.created_by}`);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.created_at ? new Date(task.created_at).toLocaleString() : '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                title: (__VLS_ctx.hubUploadEnvironment(task)),
            });
            (__VLS_ctx.hubUploadEnvironment(task));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (['completed', 'running'].includes(task.status) ? 'blue' : 'orange') },
            });
            (task.stage === 'imported' ? '导入成功' : __VLS_ctx.hubUploadStatusLabels[task.status] || task.status);
        }
        if (!__VLS_ctx.hubUploadTasks.length && !__VLS_ctx.hubUploadLoading && !__VLS_ctx.hubUploadError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
            ...{ class: "draft-pagination" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.hubUploadTotal);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeHubUploadPageSize) },
            value: (__VLS_ctx.hubUploadPageSize),
            disabled: (__VLS_ctx.hubUploadLoading),
        });
        for (const [size] of __VLS_getVForSourceType((__VLS_ctx.hubUploadPageSizeOptions))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (size),
                value: (size),
            });
            (size);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    if (!(__VLS_ctx.page === 'shops'))
                        return;
                    __VLS_ctx.changeHubUploadPage(__VLS_ctx.hubUploadPage - 1);
                } },
            disabled: (__VLS_ctx.hubUploadLoading || !!__VLS_ctx.hubUploadError || __VLS_ctx.hubUploadPage === 1),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.hubUploadPage);
        (__VLS_ctx.hubUploadPageCount);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    if (!(__VLS_ctx.page === 'shops'))
                        return;
                    __VLS_ctx.changeHubUploadPage(__VLS_ctx.hubUploadPage + 1);
                } },
            disabled: (__VLS_ctx.hubUploadLoading || !!__VLS_ctx.hubUploadError || __VLS_ctx.hubUploadPage >= __VLS_ctx.hubUploadPageCount),
        });
        if (__VLS_ctx.hubUploadLoading) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "list-refresh-overlay" },
                role: "status",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
    }
    else if (__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.refreshTiktokCatalogList) },
            ...{ class: "ghost" },
            disabled: (__VLS_ctx.tiktokCatalogListRefreshing),
        });
        (__VLS_ctx.tiktokCatalogListRefreshing ? '刷新中…' : '↻ 刷新');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.openTiktokCatalogCreateDialog) },
            ...{ class: "primary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "catalog-type-tabs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    if (!!(__VLS_ctx.page === 'shops'))
                        return;
                    if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    __VLS_ctx.tiktokCatalogTypeTab = 'tiktok_local';
                } },
            ...{ class: ({ active: __VLS_ctx.tiktokCatalogTypeTab === 'tiktok_local' }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    if (!!(__VLS_ctx.page === 'shops'))
                        return;
                    if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    __VLS_ctx.tiktokCatalogTypeTab = 'tiktok_cross_border';
                } },
            ...{ class: ({ active: __VLS_ctx.tiktokCatalogTypeTab === 'tiktok_cross_border' }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.page === 'dashboard'))
                        return;
                    if (!!(__VLS_ctx.page === 'templates'))
                        return;
                    if (!!(__VLS_ctx.page === 'pod'))
                        return;
                    if (!!(__VLS_ctx.page === 'tasks'))
                        return;
                    if (!!(__VLS_ctx.page === 'materials'))
                        return;
                    if (!!(__VLS_ctx.page === 'drafts'))
                        return;
                    if (!!(__VLS_ctx.page === 'product-library'))
                        return;
                    if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                        return;
                    if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    if (!!(__VLS_ctx.page === 'shops'))
                        return;
                    if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    __VLS_ctx.tiktokCatalogTypeTab = 'shopee_basic';
                } },
            ...{ class: ({ active: __VLS_ctx.tiktokCatalogTypeTab === 'shopee_basic' }) },
        });
        if (__VLS_ctx.tiktokCatalogError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "error" },
            });
            (__VLS_ctx.tiktokCatalogError);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-table refreshable-list" },
            'aria-busy': (__VLS_ctx.tiktokCatalogListRefreshing),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead tiktok-catalog-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [catalog] of __VLS_getVForSourceType((__VLS_ctx.activeTiktokCatalogs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (catalog.id),
                ...{ class: "trow tiktok-catalog-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (catalog.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.tiktokCatalogTypeLabel(catalog.template_type));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (catalog.template_version || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (catalog.source_filename);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (catalog.category_count);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(catalog.updated_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "tiktok-catalog-actions" },
            });
            if (catalog.template_type !== 'shopee_basic') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!!(__VLS_ctx.page === 'materials'))
                                return;
                            if (!!(__VLS_ctx.page === 'drafts'))
                                return;
                            if (!!(__VLS_ctx.page === 'product-library'))
                                return;
                            if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                                return;
                            if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!!(__VLS_ctx.page === 'shops'))
                                return;
                            if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(catalog.template_type !== 'shopee_basic'))
                                return;
                            __VLS_ctx.openTiktokCatalogDetail(catalog);
                        } },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!!(__VLS_ctx.page === 'materials'))
                            return;
                        if (!!(__VLS_ctx.page === 'drafts'))
                            return;
                        if (!!(__VLS_ctx.page === 'product-library'))
                            return;
                        if (!!(__VLS_ctx.page === 'miaoshou-collect-box'))
                            return;
                        if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!!(__VLS_ctx.page === 'shops'))
                            return;
                        if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.deleteTiktokCatalog(catalog);
                    } },
                ...{ class: "negative" },
                disabled: (__VLS_ctx.tiktokCatalogLoading),
            });
        }
        if (!__VLS_ctx.activeTiktokCatalogs.length && !__VLS_ctx.tiktokCatalogListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
            (__VLS_ctx.tiktokCatalogTypeLabel(__VLS_ctx.tiktokCatalogTypeTab));
        }
        if (__VLS_ctx.tiktokCatalogListRefreshing) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "list-refresh-overlay" },
                role: "status",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
    }
}
if (__VLS_ctx.showClaimMaterialsDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showClaimMaterialsDialog))
                    return;
                __VLS_ctx.showClaimMaterialsDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-draft-dialog claim-materials-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showClaimMaterialsDialog))
                    return;
                __VLS_ctx.showClaimMaterialsDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-grid claim-result-grid" },
    });
    for (const [url] of __VLS_getVForSourceType((__VLS_ctx.claimingTask?.result_urls || []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showClaimMaterialsDialog))
                        return;
                    __VLS_ctx.toggleClaimResult(url);
                } },
            key: (url),
            ...{ class: "material-card" },
            ...{ class: ({ selected: __VLS_ctx.selectedClaimResultUrls.includes(url) }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "material-select-mark" },
        });
        (__VLS_ctx.selectedClaimResultUrls.includes(url) ? '✓' : '');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(url)),
            alt: "生成结果图",
        });
    }
    if (!(__VLS_ctx.claimingTask?.result_urls?.length)) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "empty" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showClaimMaterialsDialog))
                    return;
                __VLS_ctx.showClaimMaterialsDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.claimMaterials) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.claimingMaterials || !__VLS_ctx.selectedClaimResultUrls.length),
    });
    (__VLS_ctx.claimingMaterials ? '领取中…' : '领取');
}
if (__VLS_ctx.showBatchClaimDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchClaimDialog))
                    return;
                !__VLS_ctx.batchClaiming && (__VLS_ctx.showBatchClaimDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card batch-claim-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchClaimDialog))
                    return;
                __VLS_ctx.showBatchClaimDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.batchClaiming),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    if (__VLS_ctx.batchClaimLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-claim-table" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-claim-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [group] of __VLS_getVForSourceType((__VLS_ctx.groupedBatchClaimItems))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (group.taskId),
                ...{ class: "batch-claim-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (group.taskLabel);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (group.urls.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "batch-claim-images" },
            });
            for (const [url] of __VLS_getVForSourceType((group.urls))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.figure, __VLS_intrinsicElements.figure)({
                    key: (url),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(url)),
                    alt: (`${group.taskLabel} 结果图`),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showBatchClaimDialog))
                                return;
                            if (!!(__VLS_ctx.batchClaimLoading))
                                return;
                            __VLS_ctx.removeBatchClaimImage(group.taskId, url);
                        } },
                    type: "button",
                    title: "移除此图",
                    disabled: (__VLS_ctx.batchClaiming),
                });
            }
        }
        if (!__VLS_ctx.groupedBatchClaimItems.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    if (__VLS_ctx.batchClaiming || __VLS_ctx.batchClaimCompleted) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-claim-progress" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.batchClaimCompleted);
        (__VLS_ctx.batchClaimTotal);
        if (__VLS_ctx.batchClaimFailed) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.batchClaimFailed);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.progress, __VLS_intrinsicElements.progress)({
            max: (__VLS_ctx.batchClaimTotal || 1),
            value: (__VLS_ctx.batchClaimCompleted),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchClaimDialog))
                    return;
                __VLS_ctx.showBatchClaimDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.batchClaiming),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.confirmBatchClaim) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.batchClaimLoading || __VLS_ctx.batchClaiming || !__VLS_ctx.groupedBatchClaimItems.length),
    });
    (__VLS_ctx.batchClaiming ? `领取中 ${__VLS_ctx.batchClaimCompleted}/${__VLS_ctx.batchClaimTotal}` : __VLS_ctx.batchClaimFailed ? '重试领取' : '确认批量领取');
}
if (__VLS_ctx.showMiaoshouPublishDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouPublishDialog))
                    return;
                !__VLS_ctx.miaoshouPublishing && (__VLS_ctx.showMiaoshouPublishDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouPublishDialog))
                    return;
                __VLS_ctx.showMiaoshouPublishDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.miaoshouPublishing),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.miaoshouPublishDraftIds.length > 1 ? '批量发布至妙手' : '发布至妙手');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.miaoshouPublishDraftIds.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.miaoshouPublishShopId),
        disabled: (__VLS_ctx.miaoshouPublishing),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (null),
        disabled: true,
    });
    for (const [shop] of __VLS_getVForSourceType((__VLS_ctx.miaoshouAssignableShops))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (shop.id),
            value: (shop.id),
        });
        (shop.name);
        (shop.external_shop_id);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    if (__VLS_ctx.miaoshouPublishing || __VLS_ctx.miaoshouPublishCompleted) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-claim-progress" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.miaoshouPublishCompleted);
        (__VLS_ctx.miaoshouPublishDraftIds.length);
        if (__VLS_ctx.miaoshouPublishFailed) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (__VLS_ctx.miaoshouPublishFailed);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.progress, __VLS_intrinsicElements.progress)({
            max: (__VLS_ctx.miaoshouPublishDraftIds.length || 1),
            value: (__VLS_ctx.miaoshouPublishCompleted),
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouPublishDialog))
                    return;
                __VLS_ctx.showMiaoshouPublishDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.miaoshouPublishing),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.confirmMiaoshouPublish) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.miaoshouPublishing || !__VLS_ctx.miaoshouPublishShopId),
    });
    (__VLS_ctx.miaoshouPublishing ? `发布中 ${__VLS_ctx.miaoshouPublishCompleted}/${__VLS_ctx.miaoshouPublishDraftIds.length}` : __VLS_ctx.miaoshouPublishFailed ? '重试发布' : '确认并发布');
}
if (__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                    return;
                __VLS_ctx.showTaskDetailDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-draft-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                    return;
                __VLS_ctx.showTaskDetailDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.viewingTask?.id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.task_type || 'SKU图');
    (__VLS_ctx.viewingTask?.template_name || '历史模板已删除');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "draft-edit-section" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-preview-images" },
    });
    for (const [url] of __VLS_getVForSourceType((__VLS_ctx.viewingTask?.parameters?.print_urls || []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                        return;
                    __VLS_ctx.openImagePreview(url, '印花图');
                } },
            key: (url),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(url)),
            alt: "印花图",
        });
    }
    if (!(__VLS_ctx.viewingTask?.parameters?.print_urls?.length)) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    }
    if (__VLS_ctx.viewingTask?.parameters?.white_image_url) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-edit-section" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                        return;
                    if (!(__VLS_ctx.viewingTask?.parameters?.white_image_url))
                        return;
                    __VLS_ctx.openImagePreview(__VLS_ctx.viewingTask.parameters.white_image_url, __VLS_ctx.viewingTask.parameters.white_image_name || '产品白底图');
                } },
            ...{ class: "task-material-thumbnail" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(__VLS_ctx.viewingTask.parameters.white_image_url)),
            alt: (__VLS_ctx.viewingTask.parameters.white_image_name || '产品白底图'),
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "draft-edit-section" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.ratio || '—');
    (__VLS_ctx.viewingTask?.parameters?.quality || '—');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.private_creative_configuration ? '个人创作配置已隐藏' : __VLS_ctx.viewingTask?.parameters?.creative_requirement || '未填写');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "draft-edit-section" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.provider === 'grsai' ? 'Grsai' : __VLS_ctx.viewingTask?.provider || '默认模型');
    if (__VLS_ctx.viewingTask?.provider_model) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.viewingTask.provider_model);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "chip" },
        ...{ class: (__VLS_ctx.taskStatusClass(__VLS_ctx.viewingTask?.status)) },
    });
    (__VLS_ctx.taskStatusLabel[__VLS_ctx.viewingTask?.status] || __VLS_ctx.viewingTask?.status || '—');
    (__VLS_ctx.viewingTask?.parameters?.print_urls?.length || 0);
    (__VLS_ctx.viewingTask?.submit_attempts || 0);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
    (__VLS_ctx.viewingTask?.provider_task_id || '—');
    if (__VLS_ctx.viewingTask?.failure_reason) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ({ error: __VLS_ctx.viewingTask?.status === 'failed' }) },
        });
        (__VLS_ctx.viewingTask.failure_reason);
    }
    if (__VLS_ctx.viewingTask?.result_map?.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-edit-section" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "task-result-map" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.viewingTask.result_map))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (item.print_url),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                            return;
                        if (!(__VLS_ctx.viewingTask?.result_map?.length))
                            return;
                        __VLS_ctx.openImagePreview(item.print_url, '印花图');
                    } },
                ...{ class: "task-material-thumbnail" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.print_url)),
                alt: "印花图",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (item.result_urls?.length || 0);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "material-draft-preview-images" },
            });
            for (const [url] of __VLS_getVForSourceType((item.result_urls || []))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                                return;
                            if (!(__VLS_ctx.viewingTask?.result_map?.length))
                                return;
                            __VLS_ctx.openImagePreview(url, '生成结果');
                        } },
                    key: (url),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(url)),
                    alt: "生成结果",
                });
            }
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type === 'sku_image'))
                    return;
                __VLS_ctx.showTaskDetailDialog = false;
            } },
        ...{ class: "primary" },
    });
}
if (__VLS_ctx.showCreativeAssetsDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showCreativeAssetsDialog))
                    return;
                __VLS_ctx.showCreativeAssetsDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card asset-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showCreativeAssetsDialog))
                    return;
                __VLS_ctx.showCreativeAssetsDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "asset-summary" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.creativeAssets.length);
    (__VLS_ctx.creativeAssets.filter(asset => asset.uploadedUrl).length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: "add-assets" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onChange: (__VLS_ctx.onCreativeAssetChange) },
        type: "file",
        multiple: true,
        accept: "image/png,image/jpeg,image/webp",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "asset-dialog-heading" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.creativeAssets.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.clearCreativeAssets) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "asset-status" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "asset-list" },
    });
    for (const [asset] of __VLS_getVForSourceType((__VLS_ctx.creativeAssets))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (asset.id),
            ...{ class: "asset-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (asset.preview),
            alt: (asset.file.name),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (asset.file.name);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (asset.uploadedUrl ? '已直传' : '待上传');
        ((asset.file.size / 1024).toFixed(1));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showCreativeAssetsDialog))
                        return;
                    __VLS_ctx.removeCreativeAsset(asset.id);
                } },
            ...{ class: "asset-delete" },
            title: "删除",
        });
    }
    if (!__VLS_ctx.creativeAssets.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "asset-empty" },
        });
    }
}
if (__VLS_ctx.showPersonalResourcesDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showPersonalResourcesDialog))
                    return;
                __VLS_ctx.showPersonalResourcesDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card personal-resources-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showPersonalResourcesDialog))
                    return;
                __VLS_ctx.showPersonalResourcesDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
        ...{ class: "resource-tabs" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showPersonalResourcesDialog))
                    return;
                __VLS_ctx.personalResourceTab = 'white-images';
            } },
        ...{ class: ({ active: __VLS_ctx.personalResourceTab === 'white-images' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showPersonalResourcesDialog))
                    return;
                __VLS_ctx.personalResourceTab = 'prompts';
            } },
        ...{ class: ({ active: __VLS_ctx.personalResourceTab === 'prompts' }) },
    });
    if (__VLS_ctx.personalResourceTab === 'white-images') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "resource-pane" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.saveWhiteImage) },
            ...{ class: "resource-editor" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        (__VLS_ctx.editingWhiteImage ? '编辑白底图' : '新增白底图');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.whiteImageForm.template_id),
            disabled: (Boolean(__VLS_ctx.editingWhiteImage)),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
            disabled: true,
        });
        for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (template.id),
                value: (template.id),
            });
            (template.name);
        }
        if (__VLS_ctx.editingWhiteImage) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            maxlength: "80",
            placeholder: "例如：正面白底图",
        });
        (__VLS_ctx.whiteImageForm.name);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.onWhiteImageFileChange) },
            type: "file",
            accept: "image/png,image/jpeg,image/webp",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.editingWhiteImage ? '不重新选择则保留当前图片' : 'JPG、PNG、WebP，最大 3MB');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        if (__VLS_ctx.editingWhiteImage) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.resetWhiteImageForm) },
                type: "button",
                ...{ class: "ghost" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: "primary" },
            disabled: (__VLS_ctx.personalResourceSaving),
        });
        (__VLS_ctx.personalResourceSaving ? '保存中…' : '保存白底图');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "resource-list" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.managedWhiteImages))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (item.id),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.image_url)),
                alt: (item.name),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (item.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.resourceTemplateName(item));
            (new Date(item.updated_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showPersonalResourcesDialog))
                            return;
                        if (!(__VLS_ctx.personalResourceTab === 'white-images'))
                            return;
                        __VLS_ctx.editWhiteImage(item);
                    } },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showPersonalResourcesDialog))
                            return;
                        if (!(__VLS_ctx.personalResourceTab === 'white-images'))
                            return;
                        __VLS_ctx.deleteWhiteImage(item);
                    } },
                ...{ class: "danger" },
            });
        }
        if (!__VLS_ctx.managedWhiteImages.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "resource-pane" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.savePersonalPrompt) },
            ...{ class: "resource-editor" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        (__VLS_ctx.editingPersonalPrompt ? '编辑创作要求' : '新增创作要求');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.personalPromptForm.template_id),
            disabled: (Boolean(__VLS_ctx.editingPersonalPrompt)),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
            disabled: true,
        });
        for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (template.id),
                value: (template.id),
            });
            (template.name);
        }
        if (__VLS_ctx.editingPersonalPrompt) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            maxlength: "80",
            placeholder: "例如：自然布料贴合",
        });
        (__VLS_ctx.personalPromptForm.name);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.personalPromptForm.content),
            maxlength: "1000",
            placeholder: "描述印花贴合方式、细节和光影",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        if (__VLS_ctx.editingPersonalPrompt) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.resetPersonalPromptForm) },
                type: "button",
                ...{ class: "ghost" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: "primary" },
            disabled: (__VLS_ctx.personalResourceSaving),
        });
        (__VLS_ctx.personalResourceSaving ? '保存中…' : '保存创作要求');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "resource-list prompt-resource-list" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.managedPrompts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (item.id),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (item.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.resourceTemplateName(item));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (item.content);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showPersonalResourcesDialog))
                            return;
                        if (!!(__VLS_ctx.personalResourceTab === 'white-images'))
                            return;
                        __VLS_ctx.editPersonalPrompt(item);
                    } },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showPersonalResourcesDialog))
                            return;
                        if (!!(__VLS_ctx.personalResourceTab === 'white-images'))
                            return;
                        __VLS_ctx.deletePersonalPrompt(item);
                    } },
                ...{ class: "danger" },
            });
        }
        if (!__VLS_ctx.managedPrompts.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
}
if (__VLS_ctx.showTeamResourcesDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTeamResourcesDialog))
                    return;
                __VLS_ctx.showTeamResourcesDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card personal-resources-dialog team-resources-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTeamResourcesDialog))
                    return;
                __VLS_ctx.showTeamResourcesDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    if (__VLS_ctx.otherResourceOwners.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "team-resource-filters" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "resource-owner-picker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (...[$event]) => {
                    if (!(__VLS_ctx.showTeamResourcesDialog))
                        return;
                    if (!(__VLS_ctx.otherResourceOwners.length))
                        return;
                    __VLS_ctx.teamResourceQuery = '';
                    __VLS_ctx.loadTeamTemplateResources();
                } },
            value: (__VLS_ctx.teamResourceUserId),
        });
        for (const [owner] of __VLS_getVForSourceType((__VLS_ctx.otherResourceOwners))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (owner.id),
                value: (owner.id),
            });
            (owner.name);
            (owner.email);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "resource-owner-picker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (...[$event]) => {
                    if (!(__VLS_ctx.showTeamResourcesDialog))
                        return;
                    if (!(__VLS_ctx.otherResourceOwners.length))
                        return;
                    __VLS_ctx.teamResourceQuery = '';
                    __VLS_ctx.loadTeamTemplateResources();
                } },
            value: (__VLS_ctx.teamResourceTemplateId),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
        });
        for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (template.id),
                value: (template.id),
            });
            (template.name);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "resource-query-picker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            placeholder: "搜索名称或创作要求",
        });
        (__VLS_ctx.teamResourceQuery);
    }
    if (__VLS_ctx.otherResourceOwners.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
            ...{ class: "resource-tabs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showTeamResourcesDialog))
                        return;
                    if (!(__VLS_ctx.otherResourceOwners.length))
                        return;
                    __VLS_ctx.teamResourceTab = 'white-images';
                } },
            ...{ class: ({ active: __VLS_ctx.teamResourceTab === 'white-images' }) },
        });
        (__VLS_ctx.teamWhiteImages.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showTeamResourcesDialog))
                        return;
                    if (!(__VLS_ctx.otherResourceOwners.length))
                        return;
                    __VLS_ctx.teamResourceTab = 'prompts';
                } },
            ...{ class: ({ active: __VLS_ctx.teamResourceTab === 'prompts' }) },
        });
        (__VLS_ctx.teamPrompts.length);
    }
    if (__VLS_ctx.teamResourcesLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "empty" },
        });
    }
    else if (__VLS_ctx.otherResourceOwners.length && __VLS_ctx.teamResourceTab === 'white-images') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "resource-list team-resource-list" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.filteredTeamWhiteImages))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (item.id),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showTeamResourcesDialog))
                            return;
                        if (!!(__VLS_ctx.teamResourcesLoading))
                            return;
                        if (!(__VLS_ctx.otherResourceOwners.length && __VLS_ctx.teamResourceTab === 'white-images'))
                            return;
                        __VLS_ctx.openImagePreview(item.image_url, item.name);
                    } },
                ...{ class: "team-white-image" },
                title: "查看大图",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.image_url)),
                alt: (item.name),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (item.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.resourceTemplateName(item));
            (new Date(item.updated_at).toLocaleString());
        }
        if (!__VLS_ctx.filteredTeamWhiteImages.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    else if (__VLS_ctx.otherResourceOwners.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "resource-list prompt-resource-list team-resource-list" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.filteredTeamPrompts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (item.id),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (item.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.resourceTemplateName(item));
            (new Date(item.updated_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (item.content);
        }
        if (!__VLS_ctx.filteredTeamPrompts.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "empty" },
        });
    }
}
if (__VLS_ctx.showBatchMainImageDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchMainImageDialog))
                    return;
                !__VLS_ctx.batchMainImageSaving && (__VLS_ctx.showBatchMainImageDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card batch-carousel-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchMainImageDialog))
                    return;
                __VLS_ctx.showBatchMainImageDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.batchMainImageSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.selectedDrafts.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "reference-mode-tabs" },
        role: "tablist",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchMainImageDialog))
                    return;
                __VLS_ctx.batchMainImageReferenceMode = 'random_carousel';
            } },
        type: "button",
        role: "tab",
        ...{ class: ({ active: __VLS_ctx.batchMainImageReferenceMode === 'random_carousel' }) },
        'aria-selected': (__VLS_ctx.batchMainImageReferenceMode === 'random_carousel'),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
        ...{ class: "reference-mode-icon" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchMainImageDialog))
                    return;
                __VLS_ctx.batchMainImageReferenceMode = 'random_sku';
            } },
        type: "button",
        role: "tab",
        ...{ class: ({ active: __VLS_ctx.batchMainImageReferenceMode === 'random_sku' }) },
        'aria-selected': (__VLS_ctx.batchMainImageReferenceMode === 'random_sku'),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
        ...{ class: "reference-mode-icon" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchMainImageDialog))
                    return;
                __VLS_ctx.batchMainImageReferenceMode = 'manual';
            } },
        type: "button",
        role: "tab",
        ...{ class: ({ active: __VLS_ctx.batchMainImageReferenceMode === 'manual' }) },
        'aria-selected': (__VLS_ctx.batchMainImageReferenceMode === 'manual'),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
        ...{ class: "reference-mode-icon" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "batch-carousel-list" },
    });
    for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.selectedDrafts))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (draft.id),
            ...{ class: "batch-carousel-draft" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (draft.id);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            title: (draft.title),
        });
        (draft.title);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.batchMainImageReferenceMode === 'manual' ? `${(__VLS_ctx.batchMainImageSelections[draft.id] || []).length} / 9 已选` : `${Math.min(3, __VLS_ctx.batchMainImageReferenceItems(draft).length)} 张随机参考图`);
        if (__VLS_ctx.batchMainImageReferenceMode === 'manual') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "main-reference-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "batch-carousel-skus" },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.mainCarouselItems(draft)))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showBatchMainImageDialog))
                                return;
                            if (!(__VLS_ctx.batchMainImageReferenceMode === 'manual'))
                                return;
                            __VLS_ctx.toggleBatchMainImageReference(draft.id, item.image_url);
                        } },
                    key: (item.image_url),
                    type: "button",
                    disabled: ((__VLS_ctx.batchMainImageSelections[draft.id] || []).length >= 9 && !(__VLS_ctx.batchMainImageSelections[draft.id] || []).includes(item.image_url)),
                    ...{ class: ({ selected: (__VLS_ctx.batchMainImageSelections[draft.id] || []).includes(item.image_url) }) },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(item.image_url)),
                    alt: (item.sku || '轮播图'),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                (item.sku || '轮播图');
            }
            if (!__VLS_ctx.mainCarouselItems(draft).length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "main-reference-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "batch-carousel-skus" },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.mainSkuItems(draft)))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showBatchMainImageDialog))
                                return;
                            if (!(__VLS_ctx.batchMainImageReferenceMode === 'manual'))
                                return;
                            __VLS_ctx.toggleBatchMainImageReference(draft.id, item.image_url);
                        } },
                    key: (item.image_url),
                    type: "button",
                    disabled: ((__VLS_ctx.batchMainImageSelections[draft.id] || []).length >= 9 && !(__VLS_ctx.batchMainImageSelections[draft.id] || []).includes(item.image_url)),
                    ...{ class: ({ selected: (__VLS_ctx.batchMainImageSelections[draft.id] || []).includes(item.image_url) }) },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(item.image_url)),
                    alt: (item.sku || 'SKU 图'),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                (item.sku || 'SKU 图');
            }
            if (!__VLS_ctx.mainSkuItems(draft).length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "main-reference-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.batchMainImageEffectiveMode(draft) === 'random_sku' ? 'SKU 图' : '轮播图');
            if (__VLS_ctx.batchMainImageReferenceMode === 'random_carousel' && __VLS_ctx.batchMainImageEffectiveMode(draft) === 'random_sku') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "batch-carousel-skus" },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.batchMainImageReferenceItems(draft)))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    key: (item.image_url),
                    type: "button",
                    disabled: true,
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(item.image_url)),
                    alt: (item.sku || '参考图'),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                (item.sku || '参考图');
            }
            if (!__VLS_ctx.batchMainImageReferenceItems(draft).length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "batch-carousel-params" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea)({
        value: (__VLS_ctx.batchMainImageParams.prompt),
        rows: "2",
        maxlength: "1000",
        placeholder: "请输入首图创作要求",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.batchMainImageParams.provider),
    });
    for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.availableAiProviders))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (provider.provider),
            value: (provider.provider),
        });
        (provider.display_name);
        (provider.model);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.batchMainImageParams.ratio),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.batchMainImageParams.quality),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchMainImageDialog))
                    return;
                __VLS_ctx.showBatchMainImageDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.batchMainImageSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createBatchMainImageTasks) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.batchMainImageSaving),
    });
    (__VLS_ctx.batchMainImageSaving ? '创建中…' : '开始创作主图');
}
if (__VLS_ctx.showBatchImageReviewDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchImageReviewDialog))
                    return;
                !__VLS_ctx.batchImageReviewSaving && (__VLS_ctx.showBatchImageReviewDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card batch-image-review-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchImageReviewDialog))
                    return;
                __VLS_ctx.showBatchImageReviewDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.batchImageReviewSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.batchImageReviewType === 'carousel' ? '轮播图' : '首图');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    if (__VLS_ctx.batchImageReviewLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-review-toolbar" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.batchReviewChosenTasks());
        (__VLS_ctx.batchReviewTotalTasks());
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showBatchImageReviewDialog))
                        return;
                    if (!!(__VLS_ctx.batchImageReviewLoading))
                        return;
                    __VLS_ctx.selectAllBatchReviewTasks();
                } },
            ...{ class: "secondary" },
        });
        (__VLS_ctx.batchImageReviewType === 'carousel' ? '所有任务选全部' : '所有任务选首张');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "batch-review-list" },
        });
        for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.batchImageReviewDrafts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (draft.id),
                ...{ class: "batch-review-draft" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (draft.id);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                title: (draft.title),
            });
            (draft.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.batchReviewSelectedCount(draft));
            (__VLS_ctx.batchReviewTasks(draft).length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showBatchImageReviewDialog))
                            return;
                        if (!!(__VLS_ctx.batchImageReviewLoading))
                            return;
                        __VLS_ctx.selectAllBatchReviewTasks(draft);
                    } },
                ...{ class: "ghost" },
            });
            (__VLS_ctx.batchImageReviewType === 'carousel' ? '本草稿选全部' : '本草稿选首张');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showBatchImageReviewDialog))
                            return;
                        if (!!(__VLS_ctx.batchImageReviewLoading))
                            return;
                        __VLS_ctx.clearBatchReviewDraft(draft);
                    } },
                ...{ class: "ghost" },
            });
            for (const [task] of __VLS_getVForSourceType((__VLS_ctx.batchReviewTasks(draft)))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (task.id),
                    ...{ class: "batch-review-task" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (__VLS_ctx.batchImageReviewType === 'carousel' ? `SKU：${task.parameters?.source_sku || '—'}` : `首图任务 #${task.id}`);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                for (const [url] of __VLS_getVForSourceType((task.result_urls))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.showBatchImageReviewDialog))
                                    return;
                                if (!!(__VLS_ctx.batchImageReviewLoading))
                                    return;
                                __VLS_ctx.toggleBatchReviewResult(task, url);
                            } },
                        key: (url),
                        type: "button",
                        ...{ class: ({ selected: (__VLS_ctx.batchImageReviewSelections[task.id] || []).includes(url) }) },
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        src: (__VLS_ctx.imageUrl(url)),
                        alt: "候选图",
                    });
                    if ((__VLS_ctx.batchImageReviewSelections[task.id] || []).includes(url)) {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
                    }
                }
            }
            if (!__VLS_ctx.batchReviewTasks(draft).length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-review-footer" },
        });
        if (__VLS_ctx.batchImageReviewType === 'carousel') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "carousel-confirm-next-step" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "radio",
                value: "main_image_pending",
            });
            (__VLS_ctx.batchCarouselReviewNextStage);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "radio",
                value: "ready_to_publish",
            });
            (__VLS_ctx.batchCarouselReviewNextStage);
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "modal-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showBatchImageReviewDialog))
                        return;
                    if (!!(__VLS_ctx.batchImageReviewLoading))
                        return;
                    __VLS_ctx.showBatchImageReviewDialog = false;
                } },
            ...{ class: "ghost" },
            disabled: (__VLS_ctx.batchImageReviewSaving),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.confirmBatchImageReview) },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.batchImageReviewSaving),
        });
        (__VLS_ctx.batchImageReviewSaving ? '确认中…' : `确认审核 ${__VLS_ctx.batchReviewChosenTasks()} 个任务`);
    }
}
if (__VLS_ctx.showMyAccountDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMyAccountDialog))
                    return;
                __VLS_ctx.showMyAccountDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "80",
        placeholder: "请输入管理员名称",
    });
    (__VLS_ctx.myName);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "2",
        placeholder: "例如：CN",
    });
    (__VLS_ctx.myUserCode);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMyAccountDialog))
                    return;
                __VLS_ctx.showMyAccountDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveMyUserCode) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.myAccountSaving),
    });
    (__VLS_ctx.myAccountSaving ? '保存中…' : '保存');
}
if (__VLS_ctx.showMaterialDraftDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialDraftDialog))
                    return;
                __VLS_ctx.showMaterialDraftDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-draft-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialDraftDialog))
                    return;
                __VLS_ctx.showMaterialDraftDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.materialDraftAssets.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        value: (__VLS_ctx.materialDraftTemplate?.name || '—'),
        readonly: true,
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "material-draft-preview" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-preview-heading" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.materialDraftAssets.length);
    if (__VLS_ctx.materialDraftAssets.length > 1) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "material-draft-sort-hint" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-preview-images" },
    });
    for (const [asset, index] of __VLS_getVForSourceType((__VLS_ctx.materialDraftAssets))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onDragstart: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    __VLS_ctx.startMaterialDraftDrag($event, asset.id);
                } },
            ...{ onDragover: () => { } },
            ...{ onDrop: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    __VLS_ctx.dropMaterialDraftAsset(asset.id);
                } },
            ...{ onDragend: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    __VLS_ctx.draggedMaterialDraftAssetId = null;
                } },
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    __VLS_ctx.openImagePreview(asset.url, asset.name || asset.sku);
                } },
            type: "button",
            key: (asset.id),
            ...{ class: "material-draft-sort-item material-batch-sort-item" },
            ...{ class: ({ dragging: __VLS_ctx.draggedMaterialDraftAssetId === asset.id }) },
            draggable: "true",
            'aria-label': (`查看 ${asset.name || asset.sku} 大图`),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(asset.url)),
            alt: (asset.name || asset.sku),
            draggable: "false",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ({ 'is-first': index === 0 }) },
        });
        (index === 0 ? '首' : index + 1);
    }
    if (__VLS_ctx.materialDraftTemplate) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "material-draft-details" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onInput: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    if (!(__VLS_ctx.materialDraftTemplate))
                        return;
                    __VLS_ctx.materialDraftTitleEdited = true;
                } },
            minlength: "25",
            maxlength: "255",
            placeholder: "请输入 25-255 个字符，或使用 AI 生成",
        });
        (__VLS_ctx.materialDraftTitle);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-counter" },
            ...{ class: ({ invalid: __VLS_ctx.materialDraftTitle.length > 0 && __VLS_ctx.materialDraftTitle.length < 25 }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.materialDraftTitle.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "title-additional-requirements draft-title-generation-controls" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-title-generation-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    if (!(__VLS_ctx.materialDraftTemplate))
                        return;
                    __VLS_ctx.showDraftAdditionalRequirements = !__VLS_ctx.showDraftAdditionalRequirements;
                } },
            type: "button",
            ...{ class: "ghost" },
            'aria-expanded': (__VLS_ctx.showDraftAdditionalRequirements),
            'aria-controls': "draft-title-additional-requirements",
        });
        (__VLS_ctx.showDraftAdditionalRequirements ? '收起' : '展开');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-title-generate-group" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.generateMaterialDraftTitle) },
            type: "button",
            ...{ class: "secondary" },
            disabled: (__VLS_ctx.materialDraftTitleGenerating),
        });
        (__VLS_ctx.materialDraftTitleGenerating ? '生成中…' : 'AI 生成标题');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialDraftDialog))
                        return;
                    if (!(__VLS_ctx.materialDraftTemplate))
                        return;
                    __VLS_ctx.showDraftTitleHelp = !__VLS_ctx.showDraftTitleHelp;
                } },
            type: "button",
            ...{ class: "draft-title-help-button" },
            'aria-label': "标题生成说明",
            'aria-expanded': (__VLS_ctx.showDraftTitleHelp),
            'aria-controls': "draft-title-generation-help",
        });
        if (__VLS_ctx.showDraftTitleHelp) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                id: "draft-title-generation-help",
                ...{ class: "draft-title-generation-help" },
            });
        }
        if (__VLS_ctx.showDraftAdditionalRequirements) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                id: "draft-title-additional-requirements",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea)({
                value: (__VLS_ctx.materialDraftAdditionalRequirements),
                maxlength: "1000",
                placeholder: "例如：重点突出蓝色花卉图案",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.materialDraftProductDescription),
            maxlength: "5000",
            placeholder: "默认使用产品模版描述，可按商品修改",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-counter" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.materialDraftProductDescription.length);
    }
    if (__VLS_ctx.materialDraftTemplate) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "material-draft-sku-summary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (__VLS_ctx.libraryDraftMode ? '直接使用所选数据的基础 SKU；' : '直接使用素材入库时生成的永久 SKU；');
        (__VLS_ctx.materialDraftSizes.length ? __VLS_ctx.materialDraftSizes.join('、') : '默认规格');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.materialDraftSkuCount);
        if (!__VLS_ctx.libraryDraftMode) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-sku-list" },
        });
        for (const [asset] of __VLS_getVForSourceType((__VLS_ctx.materialDraftAssets))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (asset.id),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (asset.sku);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-draft-size-chart" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        if (__VLS_ctx.materialDraftSizeChartPreview) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.materialDraftSizeChartPreview),
                alt: "尺码图预览",
            });
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialDraftDialog))
                    return;
                __VLS_ctx.showMaterialDraftDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createDraftFromMaterialAssets) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.materialDraftSaving),
    });
    (__VLS_ctx.materialDraftSaving ? '创建中…' : '确认创建');
}
if (__VLS_ctx.showMaterialBatchDraftDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                    return;
                !__VLS_ctx.materialBatchSaving && (__VLS_ctx.showMaterialBatchDraftDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-batch-draft-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                    return;
                __VLS_ctx.showMaterialBatchDraftDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.materialBatchSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-batch-options" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        ...{ onChange: (__VLS_ctx.rebuildMaterialBatchGroups) },
        value: (__VLS_ctx.materialBatchGroupSize),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (5),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (6),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (7),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (8),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        ...{ onChange: (__VLS_ctx.rebuildMaterialBatchGroups) },
        value: (__VLS_ctx.materialBatchMode),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: "sequential",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: "random",
    });
    if (__VLS_ctx.draftSelectionAssets.length % __VLS_ctx.materialBatchGroupSize) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "material-batch-remainder" },
        });
        (__VLS_ctx.draftSelectionAssets.length % __VLS_ctx.materialBatchGroupSize);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "material-batch-groups" },
    });
    for (const [group, index] of __VLS_getVForSourceType((__VLS_ctx.materialBatchGroups))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (index),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (index + 1);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (group.assets.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "material-batch-sort-hint" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-preview-images material-batch-preview-images" },
        });
        for (const [asset, assetIndex] of __VLS_getVForSourceType((group.assets))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onDragstart: (...[$event]) => {
                        if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                            return;
                        __VLS_ctx.startMaterialBatchDrag($event, index, asset.id);
                    } },
                ...{ onDragover: () => { } },
                ...{ onDrop: (...[$event]) => {
                        if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                            return;
                        __VLS_ctx.dropMaterialBatchAsset(index, asset.id);
                    } },
                ...{ onDragend: (...[$event]) => {
                        if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                            return;
                        __VLS_ctx.draggedMaterialBatchAsset = null;
                    } },
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                            return;
                        __VLS_ctx.openImagePreview(asset.url, (asset.name || asset.sku) + ' · 草稿 ' + (index + 1));
                    } },
                key: (asset.id),
                type: "button",
                ...{ class: "material-draft-sort-item material-batch-sort-item" },
                ...{ class: ({ dragging: __VLS_ctx.draggedMaterialBatchAsset?.groupIndex === index && __VLS_ctx.draggedMaterialBatchAsset?.assetId === asset.id }) },
                draggable: "true",
                'aria-label': ('草稿 ' + (index + 1) + ' 第 ' + (assetIndex + 1) + ' 张图片：' + (asset.name || asset.sku) + '，点击查看大图或拖动调整顺序'),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(asset.url)),
                alt: (asset.name || asset.sku),
                draggable: "false",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ({ 'is-first': assetIndex === 0 }) },
            });
            (assetIndex === 0 ? '首' : assetIndex + 1);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-title-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onInput: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                        return;
                    group.edited = true;
                } },
            minlength: "25",
            maxlength: "255",
            placeholder: "请输入 25-255 个字符的商品标题",
        });
        (group.title);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
            ...{ class: ({ error: group.title.length > 0 && group.title.length < 25 }) },
        });
        (group.title.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "title-additional-requirements draft-title-generation-controls" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-title-generation-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                        return;
                    group.showAdditionalRequirements = !group.showAdditionalRequirements;
                } },
            type: "button",
            ...{ class: "ghost" },
            'aria-expanded': (group.showAdditionalRequirements),
            'aria-controls': ('batch-title-additional-requirements-' + index),
        });
        (group.showAdditionalRequirements ? '收起' : '展开');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-title-generate-group" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                        return;
                    __VLS_ctx.generateMaterialBatchTitle(group);
                } },
            type: "button",
            ...{ class: "secondary" },
            disabled: (group.generating),
        });
        (group.generating ? '生成中…' : 'AI 生成标题');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                        return;
                    group.showTitleHelp = !group.showTitleHelp;
                } },
            type: "button",
            ...{ class: "draft-title-help-button" },
            'aria-label': ('草稿 ' + (index + 1) + ' 标题生成说明'),
            'aria-expanded': (group.showTitleHelp),
            'aria-controls': ('batch-title-generation-help-' + index),
        });
        if (group.showTitleHelp) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                id: ('batch-title-generation-help-' + index),
                ...{ class: "draft-title-generation-help" },
            });
        }
        if (group.showAdditionalRequirements) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                id: ('batch-title-additional-requirements-' + index),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea)({
                value: (group.additionalRequirements),
                maxlength: "1000",
                placeholder: "例如：重点突出蓝色花卉图案",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialBatchDraftDialog))
                    return;
                __VLS_ctx.showMaterialBatchDraftDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.materialBatchSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createMaterialBatchDrafts) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.materialBatchSaving || !__VLS_ctx.materialBatchGroups.length),
    });
    (__VLS_ctx.materialBatchSaving ? '创建中…' : '确认创建 ' + __VLS_ctx.materialBatchGroups.length + ' 条草稿');
}
if (__VLS_ctx.showBatchCarouselDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchCarouselDialog))
                    return;
                !__VLS_ctx.batchCarouselSaving && (__VLS_ctx.showBatchCarouselDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card batch-carousel-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchCarouselDialog))
                    return;
                __VLS_ctx.showBatchCarouselDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.batchCarouselSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.selectedDrafts.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "batch-carousel-list" },
    });
    for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.selectedDrafts))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (draft.id),
            ...{ class: "batch-carousel-draft" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (draft.id);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            title: (draft.title),
        });
        (draft.title);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        ((__VLS_ctx.batchCarouselSelections[draft.id] || []).length);
        (draft.sku_items?.length || 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "batch-carousel-skus" },
        });
        for (const [item] of __VLS_getVForSourceType((draft.sku_items || []))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showBatchCarouselDialog))
                            return;
                        __VLS_ctx.toggleBatchCarouselSku(draft.id, item.sku);
                    } },
                key: (item.sku),
                type: "button",
                ...{ class: ({ selected: (__VLS_ctx.batchCarouselSelections[draft.id] || []).includes(item.sku) }) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.image_url)),
                alt: (item.sku),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            (item.sku);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "batch-carousel-hover" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.image_url)),
                alt: (`${item.sku} 放大图`),
            });
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "batch-carousel-params" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea)({
        value: (__VLS_ctx.batchCarouselParams.prompt),
        rows: "2",
        maxlength: "1000",
        placeholder: "请输入轮播图创作要求",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.batchCarouselParams.provider),
    });
    for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.availableAiProviders))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (provider.provider),
            value: (provider.provider),
        });
        (provider.display_name);
        (provider.model);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.batchCarouselParams.ratio),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.batchCarouselParams.quality),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showBatchCarouselDialog))
                    return;
                __VLS_ctx.showBatchCarouselDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.batchCarouselSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createBatchCarouselTasks) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.batchCarouselSaving),
    });
    (__VLS_ctx.batchCarouselSaving ? '创建中…' : '开始创作轮播图');
}
if (__VLS_ctx.showTiktokExportDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokExportDialog))
                    return;
                !__VLS_ctx.tiktokExportLoading && (__VLS_ctx.showTiktokExportDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card tiktok-export-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokExportDialog))
                    return;
                __VLS_ctx.showTiktokExportDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.tiktokExportLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.selectedDrafts.length);
    if (__VLS_ctx.tiktokExportIsLocal) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    }
    if (__VLS_ctx.tiktokExportLoading && !__VLS_ctx.tiktokExportOptions) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "tiktok-export-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeTiktokExportCatalog) },
            value: (__VLS_ctx.tiktokExportCatalogId),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
            disabled: true,
        });
        for (const [catalog] of __VLS_getVForSourceType((__VLS_ctx.tiktokExportCatalogs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (catalog.id),
                value: (catalog.id),
            });
            (catalog.name);
            (__VLS_ctx.tiktokCatalogTypeLabel(catalog.template_type));
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "export-field" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        /** @type {[typeof SearchableSelect, ]} */ ;
        // @ts-ignore
        const __VLS_6 = __VLS_asFunctionalComponent(SearchableSelect, new SearchableSelect({
            ...{ 'onChange': {} },
            modelValue: (__VLS_ctx.tiktokExportCategory),
            options: (__VLS_ctx.tiktokExportOptions?.categories || []),
            valueKey: "name",
            labelKey: "name",
            placeholder: "请选择商品类目",
            searchPlaceholder: "搜索类目名称，空格分隔多个关键词",
        }));
        const __VLS_7 = __VLS_6({
            ...{ 'onChange': {} },
            modelValue: (__VLS_ctx.tiktokExportCategory),
            options: (__VLS_ctx.tiktokExportOptions?.categories || []),
            valueKey: "name",
            labelKey: "name",
            placeholder: "请选择商品类目",
            searchPlaceholder: "搜索类目名称，空格分隔多个关键词",
        }, ...__VLS_functionalComponentArgsRest(__VLS_6));
        let __VLS_9;
        let __VLS_10;
        let __VLS_11;
        const __VLS_12 = {
            onChange: (__VLS_ctx.changeTiktokExportCategory)
        };
        var __VLS_8;
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0.01",
            max: "999999",
            step: "0.01",
            placeholder: "请输入售价",
        });
        (__VLS_ctx.tiktokExportDefaultPrice);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0",
            max: "999999",
            step: "1",
        });
        (__VLS_ctx.tiktokExportDefaultQuantity);
        if (__VLS_ctx.tiktokExportOptions?.capabilities?.supports_cod !== false) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
                ...{ class: "required" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: (__VLS_ctx.tiktokExportCod),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "Y",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: "N",
            });
        }
        if (__VLS_ctx.selectedTiktokCategoryAttributes.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "tiktok-attribute-section" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "tiktok-export-grid" },
            });
            for (const [field] of __VLS_getVForSourceType((__VLS_ctx.selectedTiktokCategoryAttributes))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                    key: (field.field),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "tiktok-attribute-label" },
                });
                (field.label);
                if (field.required) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
                        ...{ class: "required" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                    ...{ class: "multi-value-hint" },
                });
                (__VLS_ctx.tiktokAttributeMode(field));
                __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                    value: (__VLS_ctx.tiktokExportAttributes[field.field]),
                    type: "text",
                    maxlength: "500",
                    placeholder: (__VLS_ctx.tiktokAttributePlaceholder(field)),
                });
                if (field.options?.length) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                        ...{ class: "tiktok-supported-values" },
                    });
                    (field.options.join('、'));
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                        ...{ class: "tiktok-supported-values" },
                    });
                }
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "tiktok-product-overrides" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "tiktok-override-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.selectedDrafts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (draft.id),
                ...{ class: "tiktok-override-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (draft.id);
            (draft.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "number",
                min: "0.01",
                max: "999999",
                step: "0.01",
                placeholder: "使用默认售价",
            });
            (__VLS_ctx.tiktokExportOverrides[draft.id].price);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "number",
                min: "0",
                max: "999999",
                step: "1",
                placeholder: "使用默认库存",
            });
            (__VLS_ctx.tiktokExportOverrides[draft.id].quantity);
        }
    }
    if (__VLS_ctx.tiktokExportError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error material-draft-error" },
        });
        (__VLS_ctx.tiktokExportError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTiktokExportDialog))
                    return;
                __VLS_ctx.showTiktokExportDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.tiktokExportLoading || __VLS_ctx.tiktokSubmitting),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.exportSelectedDrafts) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.tiktokExportLoading || !__VLS_ctx.tiktokExportOptions),
    });
    (__VLS_ctx.tiktokExportLoading ? '生成中…' : '生成并下载');
    if (__VLS_ctx.tiktokExportIsLocal) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.submitSelectedDraftsToHubstudio) },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.tiktokExportLoading || __VLS_ctx.tiktokSubmitting || !__VLS_ctx.tiktokExportOptions),
        });
        (__VLS_ctx.tiktokSubmitting ? '创建任务中…' : '生成并自动上品');
    }
}
if (__VLS_ctx.showShopeeExportDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showShopeeExportDialog))
                    return;
                !__VLS_ctx.shopeeExportLoading && (__VLS_ctx.showShopeeExportDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card tiktok-export-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showShopeeExportDialog))
                    return;
                __VLS_ctx.showShopeeExportDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.shopeeExportLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.selectedDrafts.length);
    if (__VLS_ctx.shopeeExportLoading && !__VLS_ctx.shopeeExportOptions) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "tiktok-export-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeShopeeExportCatalog) },
            value: (__VLS_ctx.shopeeExportCatalogId),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
            disabled: true,
        });
        for (const [catalog] of __VLS_getVForSourceType((__VLS_ctx.shopeeCatalogs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (catalog.id),
                value: (catalog.id),
            });
            (catalog.name);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "export-field" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        /** @type {[typeof SearchableSelect, ]} */ ;
        // @ts-ignore
        const __VLS_13 = __VLS_asFunctionalComponent(SearchableSelect, new SearchableSelect({
            modelValue: (__VLS_ctx.shopeeExportCategoryId),
            options: (__VLS_ctx.shopeeExportOptions?.categories || []),
            valueKey: "id",
            labelKey: "name",
            placeholder: "请选择商品类目",
            searchPlaceholder: "搜索类目名称，空格分隔多个关键词",
        }));
        const __VLS_14 = __VLS_13({
            modelValue: (__VLS_ctx.shopeeExportCategoryId),
            options: (__VLS_ctx.shopeeExportOptions?.categories || []),
            valueKey: "id",
            labelKey: "name",
            placeholder: "请选择商品类目",
            searchPlaceholder: "搜索类目名称，空格分隔多个关键词",
        }, ...__VLS_functionalComponentArgsRest(__VLS_13));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0.10",
            max: "1000000000",
            step: "0.01",
            placeholder: "请输入售价",
        });
        (__VLS_ctx.shopeeExportDefaultPrice);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0",
            max: "10000000",
            step: "1",
        });
        (__VLS_ctx.shopeeExportDefaultQuantity);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "tiktok-attribute-section" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (__VLS_ctx.shopeeExportOptions?.shipping_channels?.[0]?.on_value || 'On');
        (__VLS_ctx.shopeeExportOptions?.shipping_channels?.[0]?.off_value || 'Off');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "shopee-channel-options" },
        });
        for (const [channel] of __VLS_getVForSourceType((__VLS_ctx.shopeeExportOptions?.shipping_channels || []))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                key: (channel.field),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "checkbox",
                value: (channel.field),
            });
            (__VLS_ctx.shopeeExportChannels);
            (channel.name);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "tiktok-product-overrides" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "tiktok-override-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.selectedDrafts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (draft.id),
                ...{ class: "tiktok-override-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (draft.id);
            (draft.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "number",
                min: "0.10",
                max: "1000000000",
                step: "0.01",
                placeholder: "使用默认售价",
            });
            (__VLS_ctx.shopeeExportOverrides[draft.id].price);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "number",
                min: "0",
                max: "10000000",
                step: "1",
                placeholder: "使用默认库存",
            });
            (__VLS_ctx.shopeeExportOverrides[draft.id].quantity);
        }
    }
    if (__VLS_ctx.shopeeExportError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error material-draft-error" },
        });
        (__VLS_ctx.shopeeExportError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showShopeeExportDialog))
                    return;
                __VLS_ctx.showShopeeExportDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.shopeeExportLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.exportSelectedDraftsToShopee) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.shopeeExportLoading || !__VLS_ctx.shopeeExportOptions),
    });
    (__VLS_ctx.shopeeExportLoading ? '生成中…' : '生成并下载');
}
if (__VLS_ctx.showDraftEditDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showDraftEditDialog))
                    return;
                __VLS_ctx.showDraftEditDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-draft-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showDraftEditDialog))
                    return;
                __VLS_ctx.showDraftEditDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        minlength: "25",
        maxlength: "255",
        placeholder: "请输入 25-255 个字符",
    });
    (__VLS_ctx.draftEditTitle);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: (__VLS_ctx.draftEditProductDescription),
        ...{ class: "draft-edit-description" },
        maxlength: "5000",
        placeholder: "请输入产品描述",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "draft-edit-section" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
        ...{ class: "draft-edit-hint" },
    });
    (__VLS_ctx.draftEditSkus.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "draft-edit-preview" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.draftEditSkus))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (item.sku),
            ...{ class: "draft-edit-image-item" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({
            title: (item.sku),
        });
        (item.sku);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showDraftEditDialog))
                        return;
                    __VLS_ctx.openImagePreview(item.image_url, item.sku);
                } },
            title: "放大查看",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(item.image_url)),
            alt: (item.sku),
        });
    }
    if (!__VLS_ctx.draftEditSkus.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "draft-edit-empty" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "draft-edit-section" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
        ...{ class: "draft-edit-hint" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "draft-edit-preview" },
    });
    for (const [url, index] of __VLS_getVForSourceType((__VLS_ctx.editingDraft?.image_urls))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (url),
            ...{ class: "draft-edit-image-item" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (index === 0 ? '首图' : __VLS_ctx.draftSkuForImage(__VLS_ctx.editingDraft, url));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showDraftEditDialog))
                        return;
                    __VLS_ctx.openImagePreview(url, __VLS_ctx.editingDraft?.title || '商品素材');
                } },
            title: "放大查看",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(url)),
            alt: (__VLS_ctx.editingDraft?.title || '商品素材'),
        });
    }
    if (__VLS_ctx.editingDraft?.size_chart_url) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-edit-section" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showDraftEditDialog))
                        return;
                    if (!(__VLS_ctx.editingDraft?.size_chart_url))
                        return;
                    __VLS_ctx.openImagePreview(__VLS_ctx.editingDraft.size_chart_url, '尺码图');
                } },
            ...{ class: "draft-edit-size-chart-button" },
            title: "放大查看",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            ...{ class: "draft-edit-size-chart" },
            src: (__VLS_ctx.imageUrl(__VLS_ctx.editingDraft.size_chart_url)),
            alt: "尺码图",
        });
    }
    if (__VLS_ctx.draftEditError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error material-draft-error" },
        });
        (__VLS_ctx.draftEditError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showDraftEditDialog))
                    return;
                __VLS_ctx.showDraftEditDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveDraftEdit) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.draftEditSaving),
    });
    (__VLS_ctx.draftEditSaving ? '保存中…' : '保存修改');
}
if (__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type !== 'sku_image') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type !== 'sku_image'))
                    return;
                __VLS_ctx.showTaskDetailDialog = false;
            } },
        ...{ class: "modal-backdrop image-result-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card image-result-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type !== 'sku_image'))
                    return;
                __VLS_ctx.showTaskDetailDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.taskTypeLabel(__VLS_ctx.viewingTask));
    (__VLS_ctx.viewingTask?.id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.source_sku ? `来源 SKU：${__VLS_ctx.viewingTask.parameters.source_sku}` : `参考 ${__VLS_ctx.viewingTask?.parameters?.reference_urls?.length || 0} 张${__VLS_ctx.viewingTask?.parameters?.reference_mode === 'random_sku' ? 'SKU 图' : __VLS_ctx.viewingTask?.parameters?.reference_mode === 'random_carousel' ? '轮播图' : '图片'}`);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type !== 'sku_image'))
                    return;
                __VLS_ctx.openImageWorkspaceFromTask(__VLS_ctx.viewingTask);
            } },
        ...{ class: "secondary" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "image-task-candidates" },
    });
    for (const [url] of __VLS_getVForSourceType((__VLS_ctx.viewingTask?.result_urls || []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: (url),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type !== 'sku_image'))
                        return;
                    __VLS_ctx.openImagePreview(url, '生成结果');
                } },
            ...{ class: "candidate-preview" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(url)),
            alt: "生成结果",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showTaskDetailDialog && __VLS_ctx.viewingTask?.task_type !== 'sku_image'))
                        return;
                    __VLS_ctx.applyImageTaskResult(__VLS_ctx.viewingTask, url);
                } },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.isTaskResultSelected(__VLS_ctx.viewingTask, url)),
        });
        (__VLS_ctx.isTaskResultSelected(__VLS_ctx.viewingTask, url) ? '已采用' : __VLS_ctx.viewingTask?.task_type === 'carousel' ? '采用为轮播图' : '采用为首图');
    }
    if (!(__VLS_ctx.viewingTask?.result_urls?.length)) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "empty" },
        });
    }
}
if (__VLS_ctx.showDraftImageDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showDraftImageDialog))
                    return;
                __VLS_ctx.showDraftImageDialog = false;
            } },
        ...{ class: "modal-backdrop image-workspace-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card image-workspace" },
        ...{ class: ({ 'carousel-image-workspace': __VLS_ctx.imageWorkspaceMode === 'carousel' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showDraftImageDialog))
                    return;
                __VLS_ctx.showDraftImageDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({
        ...{ class: "image-workspace-header" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "image-workspace-header-text" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    (__VLS_ctx.imageDraft?.id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.imageWorkspaceMode === 'carousel' ? '轮播图工作台' : '图片工作台');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.imageDraft?.title);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "chip purple" },
    });
    (__VLS_ctx.draftImagePreviewUrls.length);
    if (__VLS_ctx.imageWorkspaceMode === 'full') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
            ...{ class: "workspace-steps" },
            'aria-label': "制作流程",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-step" },
            ...{ class: ({ active: true, done: __VLS_ctx.imageDraft?.carousel_items?.length }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-step-divider" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-step" },
            ...{ class: ({ active: __VLS_ctx.imageDraft?.carousel_items?.length, done: __VLS_ctx.currentGeneratedMainImage }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-step-divider" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-step" },
            ...{ class: ({ active: __VLS_ctx.draftImagePreviewUrls.length }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    }
    if (__VLS_ctx.imageWorkspaceLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    else if (__VLS_ctx.imageDraft) {
        if (__VLS_ctx.imageDraft.published) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "image-lock-notice" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "image-workspace-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
            ...{ class: "image-workspace-main" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            id: "carousel-workspace-section",
            ...{ class: "workspace-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-card-header" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-step-badge" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-card-action-hint" },
        });
        (__VLS_ctx.imageDraft.using_sku_fallback ? '当前使用 SKU 图回退' : `当前 ${__VLS_ctx.imageDraft.carousel_items?.length || 0} 张`);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-subsection" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-subsection-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "workspace-subsection-count" },
        });
        (__VLS_ctx.selectedImageSkus.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-sku-scroll" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.imageDraftSkus))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                key: (item.sku),
                ...{ class: "workspace-sku-card" },
                ...{ class: ({ selected: __VLS_ctx.selectedImageSkus.includes(item.sku) }) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "workspace-sku-check" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                ...{ onChange: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        __VLS_ctx.toggleImageSku(item.sku);
                    } },
                type: "checkbox",
                disabled: (!__VLS_ctx.selectedImageSkus.includes(item.sku) && __VLS_ctx.selectedImageSkus.length >= 9),
                checked: (__VLS_ctx.selectedImageSkus.includes(item.sku)),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "workspace-sku-image" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.image_url)),
                alt: (item.sku),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "workspace-sku-info" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (item.sku);
        }
        if (!__VLS_ctx.imageDraftSkus.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "workspace-sku-empty" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-params" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-settings-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "workspace-prompt-field" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.carouselParams.prompt),
            rows: "2",
            maxlength: "1000",
            placeholder: "例如：保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-settings-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.carouselParams.provider),
        });
        for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.availableAiProviders))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (provider.provider),
                value: (provider.provider),
            });
            (provider.display_name);
            (provider.model);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.carouselParams.ratio),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.carouselParams.quality),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showDraftImageDialog))
                        return;
                    if (!!(__VLS_ctx.imageWorkspaceLoading))
                        return;
                    if (!(__VLS_ctx.imageDraft))
                        return;
                    __VLS_ctx.createDraftImageTasks('carousel');
                } },
            ...{ class: "primary workspace-create-button" },
            disabled: (!!__VLS_ctx.imageTaskCreatingType || !__VLS_ctx.selectedImageSkus.length),
        });
        (__VLS_ctx.imageTaskCreatingType === 'carousel' ? '创建中…' : '开始创作轮播图');
        if (__VLS_ctx.workspaceCarouselTasks().length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-task-panel" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-task-panel-head" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.refreshWorkspaceTasks) },
                ...{ class: "ghost workspace-task-refresh" },
                disabled: (__VLS_ctx.imageTasksRefreshing),
            });
            (__VLS_ctx.imageTasksRefreshing ? '刷新中…' : '刷新');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-task-list" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-task-row workspace-task-row-head carousel-task-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [task] of __VLS_getVForSourceType((__VLS_ctx.workspaceCarouselTasks()))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (task.id),
                    ...{ class: "workspace-task-row carousel-task-row" },
                });
                if (task.parameters?.print_url) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.showDraftImageDialog))
                                    return;
                                if (!!(__VLS_ctx.imageWorkspaceLoading))
                                    return;
                                if (!(__VLS_ctx.imageDraft))
                                    return;
                                if (!(__VLS_ctx.workspaceCarouselTasks().length))
                                    return;
                                if (!(task.parameters?.print_url))
                                    return;
                                __VLS_ctx.openImagePreview(task.parameters.print_url, '创作素材');
                            } },
                        type: "button",
                        ...{ class: "workspace-task-thumb" },
                        title: "查看创作素材",
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        src: (__VLS_ctx.imageUrl(task.parameters.print_url)),
                        alt: "创作素材",
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "workspace-task-dash" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "workspace-task-prompt" },
                    title: (task.parameters?.creative_requirement || ''),
                });
                (task.parameters?.creative_requirement || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "workspace-task-status" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "chip" },
                    ...{ class: (__VLS_ctx.taskStatusClass(task.status)) },
                });
                (__VLS_ctx.taskStatusLabel[task.status] || task.status || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (task.id);
                (task.submit_attempts || 0);
                if (task.result_urls?.[0]) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.showDraftImageDialog))
                                    return;
                                if (!!(__VLS_ctx.imageWorkspaceLoading))
                                    return;
                                if (!(__VLS_ctx.imageDraft))
                                    return;
                                if (!(__VLS_ctx.workspaceCarouselTasks().length))
                                    return;
                                if (!(task.result_urls?.[0]))
                                    return;
                                __VLS_ctx.openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`);
                            } },
                        type: "button",
                        ...{ class: "workspace-task-thumb" },
                        title: "查看结果图",
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        src: (__VLS_ctx.imageUrl(task.result_urls[0])),
                        alt: (`任务 #${task.id} 结果图`),
                    });
                }
                else {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "workspace-task-dash" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "workspace-task-message" },
                    ...{ class: ({ error: task.status === 'failed' }) },
                });
                (task.failure_reason || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "workspace-task-actions" },
                });
                if (__VLS_ctx.taskHasSuccessfulResult(task)) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.showDraftImageDialog))
                                    return;
                                if (!!(__VLS_ctx.imageWorkspaceLoading))
                                    return;
                                if (!(__VLS_ctx.imageDraft))
                                    return;
                                if (!(__VLS_ctx.workspaceCarouselTasks().length))
                                    return;
                                if (!(__VLS_ctx.taskHasSuccessfulResult(task)))
                                    return;
                                __VLS_ctx.toggleWorkspaceCarouselTask(task);
                            } },
                        ...{ class: (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0]) ? 'secondary' : 'primary') },
                        title: (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0]) ? '点击取消采用' : '点击采用'),
                    });
                    (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0]) ? '已采用' : '采用');
                }
                if (task.status === 'failed') {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(__VLS_ctx.showDraftImageDialog))
                                    return;
                                if (!!(__VLS_ctx.imageWorkspaceLoading))
                                    return;
                                if (!(__VLS_ctx.imageDraft))
                                    return;
                                if (!(__VLS_ctx.workspaceCarouselTasks().length))
                                    return;
                                if (!(task.status === 'failed'))
                                    return;
                                __VLS_ctx.retryWorkspaceTask(task);
                            } },
                        ...{ class: "secondary" },
                        disabled: (__VLS_ctx.retryingWorkspaceTaskId === task.id),
                    });
                    (__VLS_ctx.retryingWorkspaceTaskId === task.id ? '重试中…' : '重试');
                }
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-subsection" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-subsection-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "carousel-strip generated-carousel-strip" },
        });
        for (const [item, index] of __VLS_getVForSourceType((__VLS_ctx.adoptedCarouselItems))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (item.image_url),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "carousel-strip-index" },
            });
            (index + 1);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(item.image_url)),
                alt: (item.sku || 'AI 首图'),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (item.sku || 'AI 首图');
        }
        if (!__VLS_ctx.adoptedCarouselItems.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "carousel-empty" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "carousel-empty-icon" },
                'aria-hidden': "true",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        }
        if (__VLS_ctx.imageWorkspaceMode === 'full') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                id: "main-image-workspace-section",
                ...{ class: "workspace-card" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-card-header" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "workspace-step-badge" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "reference-mode-tabs" },
                role: "tablist",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                            return;
                        __VLS_ctx.selectMainReferenceMode('random_carousel');
                    } },
                type: "button",
                role: "tab",
                ...{ class: ({ active: __VLS_ctx.mainReferenceMode === 'random_carousel' }) },
                'aria-selected': (__VLS_ctx.mainReferenceMode === 'random_carousel'),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
                ...{ class: "reference-mode-icon" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                            return;
                        __VLS_ctx.selectMainReferenceMode('random_sku');
                    } },
                type: "button",
                role: "tab",
                ...{ class: ({ active: __VLS_ctx.mainReferenceMode === 'random_sku' }) },
                'aria-selected': (__VLS_ctx.mainReferenceMode === 'random_sku'),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
                ...{ class: "reference-mode-icon" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                            return;
                        __VLS_ctx.mainReferenceMode = 'manual';
                    } },
                type: "button",
                role: "tab",
                ...{ class: ({ active: __VLS_ctx.mainReferenceMode === 'manual' }) },
                'aria-selected': (__VLS_ctx.mainReferenceMode === 'manual'),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({
                ...{ class: "reference-mode-icon" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            if (__VLS_ctx.mainReferenceMode === 'manual') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "main-reference-groups" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "main-reference-row" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "reference-picker" },
                });
                for (const [item] of __VLS_getVForSourceType((__VLS_ctx.mainCarouselReferenceItems))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                        key: (item.image_url),
                        ...{ class: ({ selected: __VLS_ctx.selectedMainReferences.includes(item.image_url) }) },
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                        ...{ onChange: (...[$event]) => {
                                if (!(__VLS_ctx.showDraftImageDialog))
                                    return;
                                if (!!(__VLS_ctx.imageWorkspaceLoading))
                                    return;
                                if (!(__VLS_ctx.imageDraft))
                                    return;
                                if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                    return;
                                if (!(__VLS_ctx.mainReferenceMode === 'manual'))
                                    return;
                                __VLS_ctx.toggleMainReference(item.image_url);
                            } },
                        type: "checkbox",
                        checked: (__VLS_ctx.selectedMainReferences.includes(item.image_url)),
                        disabled: (__VLS_ctx.selectedMainReferences.length >= 9 && !__VLS_ctx.selectedMainReferences.includes(item.image_url)),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        src: (__VLS_ctx.imageUrl(item.image_url)),
                        alt: (item.sku || '轮播图'),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (item.sku || '轮播图');
                }
                if (!__VLS_ctx.mainCarouselReferenceItems.length) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                        ...{ class: "empty" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "main-reference-row" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "reference-picker" },
                });
                for (const [item] of __VLS_getVForSourceType((__VLS_ctx.mainSkuReferenceItems))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                        key: (item.image_url),
                        ...{ class: ({ selected: __VLS_ctx.selectedMainReferences.includes(item.image_url) }) },
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                        ...{ onChange: (...[$event]) => {
                                if (!(__VLS_ctx.showDraftImageDialog))
                                    return;
                                if (!!(__VLS_ctx.imageWorkspaceLoading))
                                    return;
                                if (!(__VLS_ctx.imageDraft))
                                    return;
                                if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                    return;
                                if (!(__VLS_ctx.mainReferenceMode === 'manual'))
                                    return;
                                __VLS_ctx.toggleMainReference(item.image_url);
                            } },
                        type: "checkbox",
                        checked: (__VLS_ctx.selectedMainReferences.includes(item.image_url)),
                        disabled: (__VLS_ctx.selectedMainReferences.length >= 9 && !__VLS_ctx.selectedMainReferences.includes(item.image_url)),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                        src: (__VLS_ctx.imageUrl(item.image_url)),
                        alt: (item.sku || 'SKU 图'),
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (item.sku || 'SKU 图');
                }
                if (!__VLS_ctx.mainSkuReferenceItems.length) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                        ...{ class: "empty" },
                    });
                }
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-params" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-settings-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "workspace-prompt-field" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: (__VLS_ctx.mainParams.prompt),
                rows: "2",
                maxlength: "1000",
                placeholder: "例如：以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-settings-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: (__VLS_ctx.mainParams.provider),
            });
            for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.availableAiProviders))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (provider.provider),
                    value: (provider.provider),
                });
                (provider.display_name);
                (provider.model);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: (__VLS_ctx.mainParams.ratio),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: (__VLS_ctx.mainParams.quality),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                            return;
                        __VLS_ctx.createDraftImageTasks('main_image');
                    } },
                ...{ class: "primary workspace-create-button" },
                disabled: (!!__VLS_ctx.imageTaskCreatingType || (!__VLS_ctx.mainCarouselReferenceItems.length && !__VLS_ctx.mainSkuReferenceItems.length)),
            });
            (__VLS_ctx.imageTaskCreatingType === 'main_image' ? '创建中…' : '开始创作首图');
            if (__VLS_ctx.workspaceMainTasks().length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "workspace-task-panel" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "workspace-task-panel-head" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.refreshWorkspaceTasks) },
                    ...{ class: "ghost workspace-task-refresh" },
                    disabled: (__VLS_ctx.imageTasksRefreshing),
                });
                (__VLS_ctx.imageTasksRefreshing ? '刷新中…' : '刷新');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "workspace-task-list" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "workspace-task-row workspace-task-row-head carousel-task-row" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                for (const [task] of __VLS_getVForSourceType((__VLS_ctx.workspaceMainTasks()))) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: (task.id),
                        ...{ class: "workspace-task-row carousel-task-row" },
                    });
                    if (task.parameters?.print_url) {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(__VLS_ctx.showDraftImageDialog))
                                        return;
                                    if (!!(__VLS_ctx.imageWorkspaceLoading))
                                        return;
                                    if (!(__VLS_ctx.imageDraft))
                                        return;
                                    if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                        return;
                                    if (!(__VLS_ctx.workspaceMainTasks().length))
                                        return;
                                    if (!(task.parameters?.print_url))
                                        return;
                                    __VLS_ctx.openImagePreview(task.parameters.print_url, '创作素材');
                                } },
                            type: "button",
                            ...{ class: "workspace-task-thumb" },
                            title: "查看创作素材",
                        });
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                            src: (__VLS_ctx.imageUrl(task.parameters.print_url)),
                            alt: "创作素材",
                        });
                    }
                    else {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                            ...{ class: "workspace-task-dash" },
                        });
                    }
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "workspace-task-prompt" },
                        title: (task.parameters?.creative_requirement || ''),
                    });
                    (task.parameters?.creative_requirement || '—');
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "workspace-task-status" },
                    });
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "chip" },
                        ...{ class: (__VLS_ctx.taskStatusClass(task.status)) },
                    });
                    (__VLS_ctx.taskStatusLabel[task.status] || task.status || '—');
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (task.id);
                    (task.submit_attempts || 0);
                    if (task.result_urls?.[0]) {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(__VLS_ctx.showDraftImageDialog))
                                        return;
                                    if (!!(__VLS_ctx.imageWorkspaceLoading))
                                        return;
                                    if (!(__VLS_ctx.imageDraft))
                                        return;
                                    if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                        return;
                                    if (!(__VLS_ctx.workspaceMainTasks().length))
                                        return;
                                    if (!(task.result_urls?.[0]))
                                        return;
                                    __VLS_ctx.openImagePreview(task.result_urls[0], `任务 #${task.id} 结果图`);
                                } },
                            type: "button",
                            ...{ class: "workspace-task-thumb" },
                            title: "查看结果图",
                        });
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                            src: (__VLS_ctx.imageUrl(task.result_urls[0])),
                            alt: (`任务 #${task.id} 结果图`),
                        });
                    }
                    else {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                            ...{ class: "workspace-task-dash" },
                        });
                    }
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "workspace-task-message" },
                        ...{ class: ({ error: task.status === 'failed' }) },
                    });
                    (task.failure_reason || '—');
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "workspace-task-actions" },
                    });
                    if (__VLS_ctx.taskHasSuccessfulResult(task)) {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(__VLS_ctx.showDraftImageDialog))
                                        return;
                                    if (!!(__VLS_ctx.imageWorkspaceLoading))
                                        return;
                                    if (!(__VLS_ctx.imageDraft))
                                        return;
                                    if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                        return;
                                    if (!(__VLS_ctx.workspaceMainTasks().length))
                                        return;
                                    if (!(__VLS_ctx.taskHasSuccessfulResult(task)))
                                        return;
                                    __VLS_ctx.toggleWorkspaceMainTask(task);
                                } },
                            ...{ class: (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0]) ? 'secondary' : 'primary') },
                            title: (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0]) ? '点击取消采用' : '点击采用'),
                        });
                        (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0]) ? '已采用' : '采用');
                    }
                    if (task.status === 'failed') {
                        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                            ...{ onClick: (...[$event]) => {
                                    if (!(__VLS_ctx.showDraftImageDialog))
                                        return;
                                    if (!!(__VLS_ctx.imageWorkspaceLoading))
                                        return;
                                    if (!(__VLS_ctx.imageDraft))
                                        return;
                                    if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                        return;
                                    if (!(__VLS_ctx.workspaceMainTasks().length))
                                        return;
                                    if (!(task.status === 'failed'))
                                        return;
                                    __VLS_ctx.retryWorkspaceTask(task);
                                } },
                            ...{ class: "secondary" },
                            disabled: (__VLS_ctx.retryingWorkspaceTaskId === task.id),
                        });
                        (__VLS_ctx.retryingWorkspaceTaskId === task.id ? '重试中…' : '重试');
                    }
                }
            }
            if (__VLS_ctx.currentGeneratedMainImage) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "main-image-preview adopted-main-image-preview" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(__VLS_ctx.currentGeneratedMainImage.image_url)),
                    alt: "AI 生成图片",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            }
        }
        if (__VLS_ctx.workspaceFailedTasks().length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "workspace-card" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-card-header" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "workspace-step-badge" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-task-actions" },
            });
            for (const [task] of __VLS_getVForSourceType((__VLS_ctx.workspaceFailedTasks()))) {
                (task.id);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.workspaceFailedTasks().length))
                                return;
                            __VLS_ctx.retryWorkspaceTask(task);
                        } },
                    ...{ class: "secondary" },
                    disabled: (__VLS_ctx.retryingWorkspaceTaskId === task.id),
                });
                (__VLS_ctx.retryingWorkspaceTaskId === task.id ? '重试中…' : `重试 #${task.id}`);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.workspaceFailedTasks().length))
                                return;
                            __VLS_ctx.ignoreWorkspaceTaskFailure(task);
                        } },
                    ...{ class: "ghost" },
                });
            }
        }
        if (__VLS_ctx.imageWorkspaceMode === 'full') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "workspace-card final-image-preview-card" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "workspace-card-header" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "workspace-step-badge" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "preview-count" },
            });
            (__VLS_ctx.draftImagePreviewUrls.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "carousel-strip" },
            });
            for (const [item, index] of __VLS_getVForSourceType((__VLS_ctx.draftFinalImageItems))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    ...{ onDragstart: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                return;
                            __VLS_ctx.draggedFinalImageUrl = item.image_url;
                        } },
                    ...{ onDragend: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                return;
                            __VLS_ctx.draggedFinalImageUrl = '';
                        } },
                    ...{ onDragover: () => { } },
                    ...{ onDrop: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                return;
                            __VLS_ctx.dropFinalImage(item.image_url);
                        } },
                    key: (item.image_url),
                    draggable: "true",
                    ...{ style: {} },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "carousel-strip-index" },
                    ...{ class: ({ 'is-main': index === 0 }) },
                });
                (index === 0 ? '首' : index + 1);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.imageWorkspaceMode === 'full'))
                                return;
                            __VLS_ctx.removeFinalImage(item.image_url);
                        } },
                    type: "button",
                    ...{ class: "carousel-strip-remove" },
                    title: "从最终商品图片中移除",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(item.image_url)),
                    alt: (`商品图片 ${index + 1}`),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (index === 0 ? '1 · 首图' : `${index + 1} · 轮播图`);
            }
            if (!__VLS_ctx.draftImagePreviewUrls.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "carousel-empty" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "carousel-empty-icon" },
                    'aria-hidden': "true",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "modal-actions image-workspace-actions" },
        });
        if (__VLS_ctx.imageDraft?.workflow_stage === 'carousel_pending') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "carousel-confirm-next-step" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "radio",
                value: "main_image_pending",
            });
            (__VLS_ctx.carouselConfirmNextStage);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "radio",
                value: "ready_to_publish",
            });
            (__VLS_ctx.carouselConfirmNextStage);
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.imageWorkspaceMode === 'carousel' ? '采用轮播图后点击确认，将保存轮播图。' : '采用、移除和拖动排序仅在当前弹窗暂存；确认后一次保存到草稿。');
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.confirmDraftImages) },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.imageConfirmSaving || !!__VLS_ctx.imageTaskCreatingType),
        });
        (__VLS_ctx.imageConfirmSaving ? '保存中…' : __VLS_ctx.imageDraft?.workflow_stage === 'carousel_pending' ? (__VLS_ctx.carouselConfirmNextStage === 'ready_to_publish' ? '确认轮播图并到待发布' : '确认轮播图并进入首图创作') : __VLS_ctx.imageDraft?.workflow_stage === 'main_image_pending' ? '确认主图并进入待发布' : '保存到草稿');
    }
}
if (__VLS_ctx.showMainApplyDialog && __VLS_ctx.pendingMainApply) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMainApplyDialog && __VLS_ctx.pendingMainApply))
                    return;
                __VLS_ctx.showMainApplyDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.mainRemoveSku),
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.imageDraft?.carousel_items || []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (item.image_url),
            value: (item.image_url),
        });
        (item.sku || 'AI 首图');
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMainApplyDialog && __VLS_ctx.pendingMainApply))
                    return;
                __VLS_ctx.showMainApplyDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMainApplyDialog && __VLS_ctx.pendingMainApply))
                    return;
                __VLS_ctx.applyImageTaskResult(__VLS_ctx.pendingMainApply.task, __VLS_ctx.pendingMainApply.url, __VLS_ctx.mainRemoveSku);
            } },
        ...{ class: "primary" },
    });
}
if (__VLS_ctx.showGroupDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showGroupDialog))
                    return;
                __VLS_ctx.showGroupDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    if (__VLS_ctx.showGroupDialog) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "modal-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onKeyup: (__VLS_ctx.createGroup) },
            placeholder: "例如：夏季服装",
        });
        (__VLS_ctx.newGroupName);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "modal-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showGroupDialog))
                        return;
                    if (!(__VLS_ctx.showGroupDialog))
                        return;
                    __VLS_ctx.showGroupDialog = false;
                } },
            ...{ class: "ghost" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.createGroup) },
            ...{ class: "primary" },
        });
    }
}
if (__VLS_ctx.showOperatorGroupDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showOperatorGroupDialog))
                    return;
                __VLS_ctx.showOperatorGroupDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.editingOperatorGroup ? '运营组更名' : '新增运营组');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.editingOperatorGroup ? '更改组名不会影响成员归属。' : '每组必须有一位组长；可以选择本公司已启用的普通运营。');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "80",
        placeholder: "请输入组名",
    });
    (__VLS_ctx.operatorGroupForm.name);
    if (!__VLS_ctx.editingOperatorGroup) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.operatorGroupForm.leader_user_id),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
        });
        for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members.filter(item => item.role === 'member' && item.is_active)))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (member.id),
                value: (member.id),
            });
            (member.name);
            (__VLS_ctx.operatorGroupName(member.group_id));
        }
    }
    if (!__VLS_ctx.editingOperatorGroup && !__VLS_ctx.members.some(item => item.role === 'member' && item.is_active)) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "operator-group-hint" },
        });
    }
    if (__VLS_ctx.operatorGroupError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error modal-error" },
        });
        (__VLS_ctx.operatorGroupError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showOperatorGroupDialog))
                    return;
                __VLS_ctx.showOperatorGroupDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveOperatorGroup) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.operatorGroupSaving),
    });
    (__VLS_ctx.operatorGroupSaving ? '保存中…' : '保存');
}
if (__VLS_ctx.showMemberDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMemberDialog))
                    return;
                __VLS_ctx.showMemberDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.editingMember ? '编辑成员' : '新增成员');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.editingMember ? '留空密码即可保持原密码不变。' : '姓名、用户代码、邮箱和密码为必填项。');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "80",
        placeholder: "请输入姓名",
    });
    (__VLS_ctx.memberForm.name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "2",
        placeholder: "例如：CN（两个字符）",
    });
    (__VLS_ctx.memberForm.user_code);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "email",
        placeholder: "name@example.com",
    });
    (__VLS_ctx.memberForm.email);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "password",
        minlength: "8",
        placeholder: (__VLS_ctx.editingMember ? '留空则不修改' : '至少 8 个字符'),
    });
    (__VLS_ctx.memberForm.password);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.memberForm.role),
        disabled: (__VLS_ctx.editingMember?.role === 'team_leader'),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: "member",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: "team_leader",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.memberForm.group_id),
        disabled: (__VLS_ctx.editingMember?.role === 'team_leader'),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (null),
    });
    for (const [group] of __VLS_getVForSourceType((__VLS_ctx.operatorGroups))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (group.id),
            value: (group.id),
        });
        (group.name);
    }
    if (__VLS_ctx.memberForm.role === 'team_leader' && __VLS_ctx.editingMember?.role !== 'team_leader') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "operator-group-hint" },
        });
    }
    if (__VLS_ctx.editingMember?.role === 'team_leader') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "operator-group-hint" },
        });
    }
    if (__VLS_ctx.memberFormError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error modal-error" },
        });
        (__VLS_ctx.memberFormError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMemberDialog))
                    return;
                __VLS_ctx.showMemberDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveMember) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.memberSaving),
    });
    (__VLS_ctx.memberSaving ? '保存中…' : '保存');
}
if (__VLS_ctx.showMemberCredentialDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMemberCredentialDialog))
                    return;
                __VLS_ctx.showMemberCredentialDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.credentialProvider?.credential_display_name || __VLS_ctx.credentialProvider?.display_name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.credentialMember?.name);
    (__VLS_ctx.credentialProvider?.provider === 'deepseek' ? '生成英文商品标题' : '创建和查询 AI 图像任务');
    if (__VLS_ctx.memberCredentialPreview()) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "credential-preview" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (__VLS_ctx.memberCredentialPreview());
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onKeyup: (__VLS_ctx.saveMemberCredential) },
        type: "password",
        maxlength: "2000",
        autocomplete: "new-password",
        placeholder: (__VLS_ctx.memberCredentialPreview() ? '输入新密钥以替换当前配置' : '请输入新的平台密钥'),
    });
    (__VLS_ctx.credentialApiKey);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions credential-modal-actions" },
    });
    if (__VLS_ctx.credentialMember?.ai_provider_credentials?.[__VLS_ctx.memberCredentialKey()]) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.clearMemberCredential) },
            ...{ class: "negative" },
            disabled: (__VLS_ctx.credentialSaving),
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMemberCredentialDialog))
                    return;
                __VLS_ctx.showMemberCredentialDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.credentialSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveMemberCredential) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.credentialSaving || !__VLS_ctx.credentialApiKey.trim()),
    });
    (__VLS_ctx.credentialSaving ? '保存中…' : '安全保存');
}
if (__VLS_ctx.showMiaoshouDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouDialog))
                    return;
                __VLS_ctx.showMiaoshouDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.company?.miaoshou_configured ? '更新' : '配置');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "255",
        autocomplete: "off",
        placeholder: "请输入 App ID",
    });
    (__VLS_ctx.miaoshouForm.app_id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onKeyup: (__VLS_ctx.saveMiaoshouAccount) },
        type: "password",
        maxlength: "500",
        autocomplete: "new-password",
        placeholder: "请输入 App Secret",
    });
    (__VLS_ctx.miaoshouForm.app_secret);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouDialog))
                    return;
                __VLS_ctx.showMiaoshouDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.miaoshouSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveMiaoshouAccount) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.miaoshouSaving || !__VLS_ctx.miaoshouForm.app_id.trim() || !__VLS_ctx.miaoshouForm.app_secret.trim()),
    });
    (__VLS_ctx.miaoshouSaving ? '保存中…' : '保存并同步');
}
if (__VLS_ctx.showHubstudioDialog && __VLS_ctx.user?.role === 'company_admin') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showHubstudioDialog && __VLS_ctx.user?.role === 'company_admin'))
                    return;
                __VLS_ctx.showHubstudioDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "255",
    });
    (__VLS_ctx.hubstudioForm.app_id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "password",
        maxlength: "2000",
    });
    (__VLS_ctx.hubstudioForm.app_secret);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "120",
    });
    (__VLS_ctx.hubstudioForm.group_code);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showHubstudioDialog && __VLS_ctx.user?.role === 'company_admin'))
                    return;
                __VLS_ctx.showHubstudioDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.hubstudioSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveHubstudioAccount) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.hubstudioSaving || !__VLS_ctx.hubstudioForm.app_id || !__VLS_ctx.hubstudioForm.app_secret || !__VLS_ctx.hubstudioForm.group_code),
    });
    (__VLS_ctx.hubstudioSaving ? '保存中…' : '安全保存');
}
if (__VLS_ctx.showShopManagersDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showShopManagersDialog))
                    return;
                __VLS_ctx.showShopManagersDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.managingShop?.name);
    for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members.filter(item => item.role === 'member' || item.role === 'team_leader')))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            key: (member.id),
            ...{ class: "manager-option" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            value: (member.id),
            type: "checkbox",
        });
        (__VLS_ctx.selectedManagerIds);
        (member.name);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (member.email);
    }
    if (!__VLS_ctx.members.some(item => item.role === 'member' || item.role === 'team_leader')) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "empty" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showShopManagersDialog))
                    return;
                __VLS_ctx.showShopManagersDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveShopManagers) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.shopManagersSaving),
    });
    (__VLS_ctx.shopManagersSaving ? '保存中…' : '保存分配');
}
if (__VLS_ctx.showTemplateDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "drawer-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "template-drawer" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.editingTemplate ? '编辑产品模板' : '新增产品模板');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTemplateDialog))
                    return;
                __VLS_ctx.showTemplateDialog = false;
            } },
        ...{ class: "drawer-close" },
        'aria-label': "关闭",
        disabled: (__VLS_ctx.templateSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
        ...{ class: "drawer-tabs" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTemplateDialog))
                    return;
                __VLS_ctx.templateFormTab = 'basic';
            } },
        ...{ class: ({ active: __VLS_ctx.templateFormTab === 'basic' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTemplateDialog))
                    return;
                __VLS_ctx.templateFormTab = 'product';
            } },
        ...{ class: ({ active: __VLS_ctx.templateFormTab === 'product' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTemplateDialog))
                    return;
                __VLS_ctx.templateFormTab = 'logistics';
            } },
        ...{ class: ({ active: __VLS_ctx.templateFormTab === 'logistics' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTemplateDialog))
                    return;
                __VLS_ctx.templateFormTab = 'ai-prompts';
            } },
        ...{ class: ({ active: __VLS_ctx.templateFormTab === 'ai-prompts' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "drawer-content" },
    });
    if (__VLS_ctx.templateFormTab === 'basic') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "drawer-form" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            placeholder: "例如：宽松短袖上衣",
        });
        (__VLS_ctx.newTemplateName);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.onCoverChange) },
            accept: "image/png,image/jpeg,image/webp",
            type: "file",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.newTemplateImage ? __VLS_ctx.newTemplateImage.name : __VLS_ctx.editingTemplate?.cover_url ? '保留当前图片' : '支持 JPG、PNG、WebP，最大 3MB');
        if (__VLS_ctx.newTemplateImagePreview) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "template-upload-preview" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.newTemplateImagePreview),
                alt: "模板图片预览",
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.newTemplateDescription),
            maxlength: "500",
            placeholder: "描述产品材质、版型和适用的印花区域",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: (__VLS_ctx.newTemplateGroupId),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (null),
            disabled: true,
        });
        for (const [group] of __VLS_getVForSourceType((__VLS_ctx.templateGroups))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (group.id),
                value: (group.id),
            });
            (group.name);
        }
    }
    else if (__VLS_ctx.templateFormTab === 'product') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "drawer-form product-info-form" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.newTemplateProductDescription),
            rows: "4",
            maxlength: "5000",
            placeholder: "填写商品详情页的产品描述",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "sku-form" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "sku-size-grid" },
        });
        for (const [_, index] of __VLS_getVForSourceType((__VLS_ctx.newSkuSizeOptions))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (index),
                ...{ class: "sku-size-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                maxlength: "50",
                placeholder: "例如：M",
            });
            (__VLS_ctx.newSkuSizeOptions[index]);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.newSkuSizeOptions[index].length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showTemplateDialog))
                            return;
                        if (!!(__VLS_ctx.templateFormTab === 'basic'))
                            return;
                        if (!(__VLS_ctx.templateFormTab === 'product'))
                            return;
                        __VLS_ctx.newSkuSizeOptions.splice(index, 1);
                    } },
                title: "删除尺码",
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.addSkuSize) },
            ...{ class: "sku-add-option" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
            ...{ class: "sku-total" },
        });
        (Math.max(1, __VLS_ctx.newSkuSizeOptions.filter(value => value.trim()).length));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.onSizeChartChange) },
            accept: "image/png,image/jpeg,image/webp",
            type: "file",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.newTemplateSizeChart ? __VLS_ctx.newTemplateSizeChart.name : __VLS_ctx.editingTemplate?.size_chart_url ? '保留当前尺码图' : '支持 JPG、PNG、WebP，最多上传 1 张，最大 3MB');
        if (__VLS_ctx.newTemplateSizeChartPreview) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "template-upload-preview" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.newTemplateSizeChartPreview),
                alt: "尺码图预览",
            });
        }
    }
    else if (__VLS_ctx.templateFormTab === 'ai-prompts') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "drawer-form ai-prompts-form" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.newTemplateTitleTemplate),
            rows: "4",
            maxlength: "500",
            placeholder: "例如：女款长袖连衣裙，突出印花与日常穿搭；如需提及材质，请写明具体材质",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        for (const [prompt, index] of __VLS_getVForSourceType((__VLS_ctx.newTemplateAiPrompts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                key: (index),
                ...{ class: "ai-prompt-editor" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (index + 1);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showTemplateDialog))
                            return;
                        if (!!(__VLS_ctx.templateFormTab === 'basic'))
                            return;
                        if (!!(__VLS_ctx.templateFormTab === 'product'))
                            return;
                        if (!(__VLS_ctx.templateFormTab === 'ai-prompts'))
                            return;
                        __VLS_ctx.removeTemplateAiPrompt(index);
                    } },
                type: "button",
                ...{ class: "danger" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                maxlength: "80",
                placeholder: "例如：自然布料贴合",
            });
            (prompt.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: (prompt.content),
                maxlength: "1000",
                placeholder: "描述印花贴合方式、细节、光影等创作要求",
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.addTemplateAiPrompt) },
            type: "button",
            ...{ class: "secondary ai-prompt-add" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "drawer-form logistics-form" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            title: "用于运费及配送计算",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "unit-input" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0.001",
            step: "0.001",
            placeholder: "请输入重量",
        });
        (__VLS_ctx.newPackageWeight);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "dimension-inputs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0.1",
            step: "0.1",
            placeholder: "长",
        });
        (__VLS_ctx.newPackageLength);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0.1",
            step: "0.1",
            placeholder: "宽",
        });
        (__VLS_ctx.newPackageWidth);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "0.1",
            step: "0.1",
            placeholder: "高",
        });
        (__VLS_ctx.newPackageHeight);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTemplateDialog))
                    return;
                __VLS_ctx.showTemplateDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.templateSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createTemplate) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.templateSaving),
    });
    (__VLS_ctx.templateSaving ? '上传中…' : (__VLS_ctx.editingTemplate ? '保存修改' : '确认新增'));
}
if (__VLS_ctx.previewImageUrl) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.previewImageUrl))
                    return;
                __VLS_ctx.previewImageUrl = '';
            } },
        ...{ class: "image-preview-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "image-preview-modal" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.previewImageUrl))
                    return;
                __VLS_ctx.previewImageUrl = '';
            } },
        ...{ class: "modal-close" },
        'aria-label': "关闭大图",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
        src: (__VLS_ctx.previewImageUrl),
        alt: (__VLS_ctx.previewImageAlt),
    });
}
if (__VLS_ctx.productLibraryOrderProduct) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (__VLS_ctx.closeProductLibraryOrders) },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card product-library-orders-dialog" },
        role: "dialog",
        'aria-modal': "true",
        'aria-labelledby': "product-library-orders-heading",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.closeProductLibraryOrders) },
        ...{ class: "modal-close" },
        'aria-label': "关闭订单详情",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        id: "product-library-orders-heading",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.productLibraryOrderProduct.sku);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "product-library-orders-table" },
        'aria-busy': (__VLS_ctx.productLibraryOrderLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "product-library-orders-head" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    for (const [order, index] of __VLS_getVForSourceType((__VLS_ctx.productLibraryOrders))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (index),
            ...{ class: "product-library-orders-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (new Date(order.ordered_at).toLocaleString());
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            title: (order.order_number),
        });
        (order.order_number);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            title: (order.shop_name),
        });
        (order.shop_name);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            title: (order.product_id),
        });
        (order.product_id);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (order.quantity);
    }
    if (!__VLS_ctx.productLibraryOrders.length && !__VLS_ctx.productLibraryOrderLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    if (__VLS_ctx.productLibraryOrderLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "product-library-orders-loading" },
            role: "status",
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
        ...{ class: "draft-pagination product-library-orders-pagination" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.productLibraryOrderCount);
    (__VLS_ctx.productLibraryOrderTotal);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        ...{ onChange: (__VLS_ctx.changeProductLibraryOrderPageSize) },
        value: (__VLS_ctx.productLibraryOrderPageSize),
        disabled: (__VLS_ctx.productLibraryOrderLoading),
    });
    for (const [size] of __VLS_getVForSourceType((__VLS_ctx.pageSizeOptions))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (size),
            value: (size),
        });
        (size);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.productLibraryOrderProduct))
                    return;
                __VLS_ctx.changeProductLibraryOrderPage(__VLS_ctx.productLibraryOrderPage - 1);
            } },
        disabled: (__VLS_ctx.productLibraryOrderLoading || __VLS_ctx.productLibraryOrderPage === 1),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.productLibraryOrderPage);
    (__VLS_ctx.productLibraryOrderPageCount);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.productLibraryOrderProduct))
                    return;
                __VLS_ctx.changeProductLibraryOrderPage(__VLS_ctx.productLibraryOrderPage + 1);
            } },
        disabled: (__VLS_ctx.productLibraryOrderLoading || __VLS_ctx.productLibraryOrderPage === __VLS_ctx.productLibraryOrderPageCount),
    });
}
if (__VLS_ctx.showProductLibraryTemplateDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showProductLibraryTemplateDialog))
                    return;
                !__VLS_ctx.productLibraryTemplateSaving && (__VLS_ctx.showProductLibraryTemplateDialog = false);
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card product-library-template-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showProductLibraryTemplateDialog))
                    return;
                __VLS_ctx.showProductLibraryTemplateDialog = false;
            } },
        ...{ class: "modal-close" },
        disabled: (__VLS_ctx.productLibraryTemplateSaving),
        'aria-label': "关闭批量设置模版",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.selectedProductLibraryIds.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.productLibraryTargetTemplateId),
        disabled: (__VLS_ctx.productLibraryTemplateSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (null),
        disabled: true,
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (item.id),
            value: (item.id),
        });
        (item.name);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showProductLibraryTemplateDialog))
                    return;
                __VLS_ctx.showProductLibraryTemplateDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.productLibraryTemplateSaving),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveProductLibraryTemplate) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.productLibraryTemplateSaving || !__VLS_ctx.productLibraryTargetTemplateId),
    });
    (__VLS_ctx.productLibraryTemplateSaving ? '保存中…' : '确认设置');
}
if (__VLS_ctx.toast) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "toast" },
        role: "alert",
        ...{ style: {} },
    });
    (__VLS_ctx.toast);
}
if (__VLS_ctx.showMaterialUploadDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialUploadDialog))
                    return;
                __VLS_ctx.showMaterialUploadDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-template-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialUploadDialog))
                    return;
                __VLS_ctx.showMaterialUploadDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.pendingMaterialUploadFiles.length);
    if (__VLS_ctx.materialUploading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ style: {} },
        });
        (__VLS_ctx.materialUploadedCount);
        (__VLS_ctx.materialUploadTotal);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: (__VLS_ctx.materialUploadTemplateId),
        disabled: (__VLS_ctx.materialUploading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (null),
        disabled: true,
    });
    for (const [template] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: (template.id),
            value: (template.id),
        });
        (template.name);
    }
    if (__VLS_ctx.materialUploadError) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ style: {} },
        });
        (__VLS_ctx.materialUploadError);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMaterialUploadDialog))
                    return;
                __VLS_ctx.showMaterialUploadDialog = false;
            } },
        ...{ class: "ghost" },
        disabled: (__VLS_ctx.materialUploading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.uploadMaterialAssets) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.materialUploading),
    });
    (__VLS_ctx.materialUploading ? '上传中…' : '确认上传');
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
    ...{ class: "site-footer" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.a, __VLS_intrinsicElements.a)({
    href: "https://beian.miit.gov.cn/",
    target: "_blank",
    rel: "noopener noreferrer",
});
/** @type {__VLS_StyleScopedClasses['login-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['login-card']} */ ;
/** @type {__VLS_StyleScopedClasses['brand-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['full']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-create-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-detail-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-property-list']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-property-head']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-property-row']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-input-mode-select']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['app-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['logo']} */ ;
/** @type {__VLS_StyleScopedClasses['content']} */ ;
/** @type {__VLS_StyleScopedClasses['context']} */ ;
/** @type {__VLS_StyleScopedClasses['member']} */ ;
/** @type {__VLS_StyleScopedClasses['account-button']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['hero']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['metrics']} */ ;
/** @type {__VLS_StyleScopedClasses['two-col']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['quick']} */ ;
/** @type {__VLS_StyleScopedClasses['quick']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['toolbar']} */ ;
/** @type {__VLS_StyleScopedClasses['toolbar-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['template-layout']} */ ;
/** @type {__VLS_StyleScopedClasses['groups']} */ ;
/** @type {__VLS_StyleScopedClasses['groups-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['add-group']} */ ;
/** @type {__VLS_StyleScopedClasses['template-group-item']} */ ;
/** @type {__VLS_StyleScopedClasses['template-group-delete']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['template-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['template-card']} */ ;
/** @type {__VLS_StyleScopedClasses['template-image']} */ ;
/** @type {__VLS_StyleScopedClasses['hasCover']} */ ;
/** @type {__VLS_StyleScopedClasses['template-image-button']} */ ;
/** @type {__VLS_StyleScopedClasses['template-image']} */ ;
/** @type {__VLS_StyleScopedClasses['template-description']} */ ;
/** @type {__VLS_StyleScopedClasses['template-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['danger']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['mode-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['active']} */ ;
/** @type {__VLS_StyleScopedClasses['pod-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['pod-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['personal-resource-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['personal-resource-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['requirement-label']} */ ;
/** @type {__VLS_StyleScopedClasses['prompt-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['pod-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['upload']} */ ;
/** @type {__VLS_StyleScopedClasses['floral']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-count']} */ ;
/** @type {__VLS_StyleScopedClasses['creative-asset-error']} */ ;
/** @type {__VLS_StyleScopedClasses['manage-assets']} */ ;
/** @type {__VLS_StyleScopedClasses['white-image-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['white-image-label']} */ ;
/** @type {__VLS_StyleScopedClasses['product-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['template-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['white-image-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['settings']} */ ;
/** @type {__VLS_StyleScopedClasses['settings-title']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-fields']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-field']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-field']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-field']} */ ;
/** @type {__VLS_StyleScopedClasses['estimate']} */ ;
/** @type {__VLS_StyleScopedClasses['upload-progress']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['full']} */ ;
/** @type {__VLS_StyleScopedClasses['creative-submit-error']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['task-type-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['task-type-tabs-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['task-type-tabs-label']} */ ;
/** @type {__VLS_StyleScopedClasses['task-type-tabs-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['task-type-tabs-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['task-center-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['task-filter-row']} */ ;
/** @type {__VLS_StyleScopedClasses['task-sku-search']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['task-search-button']} */ ;
/** @type {__VLS_StyleScopedClasses['task-batch-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['task-batch-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['task-table']} */ ;
/** @type {__VLS_StyleScopedClasses['refreshable-list']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['task-list-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['material-select-all']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['task-list-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['task-material-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['ai-model-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-task-id']} */ ;
/** @type {__VLS_StyleScopedClasses['copy-icon-button']} */ ;
/** @type {__VLS_StyleScopedClasses['task-progress-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['task-material-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['material-usage-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['material-filter-row']} */ ;
/** @type {__VLS_StyleScopedClasses['material-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['material-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['material-upload-button']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-upload-error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['material-list']} */ ;
/** @type {__VLS_StyleScopedClasses['refreshable-list']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['material-thead']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['material-select-all']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['material-trow']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['material-list-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['material-source-task']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['material-filter-row']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-work-status-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-export-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['task-table']} */ ;
/** @type {__VLS_StyleScopedClasses['refreshable-list']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-thead']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-trow']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-product-title']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-carousel-flag']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-status-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-trow-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact-action']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact-action']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact-action']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact-action']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact-action']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-category-description']} */ ;
/** @type {__VLS_StyleScopedClasses['material-usage-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-category-description']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-filter-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-filter-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-filter-options']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-filter-option']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-filter-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-search-button']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-export-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-selection-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-head']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-select-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-row']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-product-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-code']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-title']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-data']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-detail-button']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-section']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-category-description']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-section']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-stagnant-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-select-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-stagnant-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-product-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-code']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-stagnant-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-section']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-new-images-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-select-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-new-images-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-product-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-code']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-new-images-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-table']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-section']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-date']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-select-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-rank']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-product-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-image']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-code']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-title']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-shop-data']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-detail-button']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-ranking-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['material-usage-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['miaoshou-status']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-sync-time']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['collect-box-title']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-groups-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-group-list']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-group-card']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-group-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-groups-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['member-list-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['member-list-title']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['refreshable-list']} */ ;
/** @type {__VLS_StyleScopedClasses['member-list-scroll']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['member-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['member-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['member-row-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['credential-button']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['miaoshou-status']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['refreshable-list']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['hub-upload-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['catalog-type-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['refreshable-list']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['list-refresh-overlay']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['claim-materials-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['material-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['claim-result-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['material-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-select-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-table']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-head']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-row']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-images']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-progress']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-claim-progress']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['task-material-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['task-result-map']} */ ;
/** @type {__VLS_StyleScopedClasses['task-material-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-summary']} */ ;
/** @type {__VLS_StyleScopedClasses['add-assets']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-dialog-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-status']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-list']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-row']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-delete']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['personal-resources-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-pane']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-editor']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['danger']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-pane']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-editor']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['prompt-resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['danger']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['personal-resources-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['team-resources-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['team-resource-filters']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-owner-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-owner-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-query-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['team-resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['team-white-image']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['prompt-resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['team-resource-list']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-list']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-draft']} */ ;
/** @type {__VLS_StyleScopedClasses['main-reference-row']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-skus']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['main-reference-row']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-skus']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['main-reference-row']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-skus']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-params']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-image-review-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-review-toolbar']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-review-list']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-review-draft']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-review-task']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-review-footer']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-confirm-next-step']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sort-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sort-item']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-sort-item']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-details']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-counter']} */ ;
/** @type {__VLS_StyleScopedClasses['title-additional-requirements']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generation-controls']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generation-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generate-group']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-help-button']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generation-help']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-counter']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sku-summary']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sku-list']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-size-chart']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-options']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-remainder']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-groups']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-sort-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sort-item']} */ ;
/** @type {__VLS_StyleScopedClasses['material-batch-sort-item']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-title-row']} */ ;
/** @type {__VLS_StyleScopedClasses['title-additional-requirements']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generation-controls']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generation-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generate-group']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-help-button']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-title-generation-help']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-list']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-draft']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-skus']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-hover']} */ ;
/** @type {__VLS_StyleScopedClasses['batch-carousel-params']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-export-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-export-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['export-field']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-attribute-section']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-export-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-attribute-label']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['multi-value-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-supported-values']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-supported-values']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-product-overrides']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-override-head']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-override-row']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-export-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-export-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['export-field']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-attribute-section']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['shopee-channel-options']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-product-overrides']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-override-head']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-override-row']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-description']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-image-item']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-image-item']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-size-chart-button']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-size-chart']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['image-result-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['image-result-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['image-task-candidates']} */ ;
/** @type {__VLS_StyleScopedClasses['candidate-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-header']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-header-text']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['purple']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-steps']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-divider']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-divider']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['image-lock-notice']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-main']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-action-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-subsection']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-subsection-head']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-subsection-count']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-scroll']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-check']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-image']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-info']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-prompt-field']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-row']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-create-button']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-panel-head']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-refresh']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-list']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row-head']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-dash']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-prompt']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-status']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-dash']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-message']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-subsection']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-subsection-head']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['generated-carousel-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip-index']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['main-reference-groups']} */ ;
/** @type {__VLS_StyleScopedClasses['main-reference-row']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['main-reference-row']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-prompt-field']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-row']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-create-button']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-panel-head']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-refresh']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-list']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row-head']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-dash']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-prompt']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-status']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-dash']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-message']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['main-image-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['adopted-main-image-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['final-image-preview-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['preview-count']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip-index']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip-remove']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-confirm-next-step']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-group-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['required']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-group-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['operator-group-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-error']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['credential-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['credential-modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['manager-option']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['template-drawer']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-close']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-content']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-form']} */ ;
/** @type {__VLS_StyleScopedClasses['template-upload-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-form']} */ ;
/** @type {__VLS_StyleScopedClasses['product-info-form']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-form']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-size-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-size-row']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-add-option']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-total']} */ ;
/** @type {__VLS_StyleScopedClasses['template-upload-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-form']} */ ;
/** @type {__VLS_StyleScopedClasses['ai-prompts-form']} */ ;
/** @type {__VLS_StyleScopedClasses['ai-prompt-editor']} */ ;
/** @type {__VLS_StyleScopedClasses['danger']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['ai-prompt-add']} */ ;
/** @type {__VLS_StyleScopedClasses['drawer-form']} */ ;
/** @type {__VLS_StyleScopedClasses['logistics-form']} */ ;
/** @type {__VLS_StyleScopedClasses['unit-input']} */ ;
/** @type {__VLS_StyleScopedClasses['dimension-inputs']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['image-preview-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['image-preview-modal']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-orders-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-orders-table']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-orders-head']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-orders-row']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-orders-loading']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-orders-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['product-library-template-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['toast']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-template-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['site-footer']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            SearchableSelect: SearchableSelect,
            ShopDataHeading: ShopDataHeading,
            pageSizeOptions: pageSizeOptions,
            productLibraryPageSizeOptions: productLibraryPageSizeOptions,
            hubUploadPageSizeOptions: hubUploadPageSizeOptions,
            token: token,
            page: page,
            email: email,
            password: password,
            user: user,
            company: company,
            templates: templates,
            templateGroups: templateGroups,
            tasks: tasks,
            drafts: drafts,
            members: members,
            operatorGroups: operatorGroups,
            loading: loading,
            error: error,
            toast: toast,
            templateQuery: templateQuery,
            activeGroupId: activeGroupId,
            selectedTemplateId: selectedTemplateId,
            showGroupDialog: showGroupDialog,
            showTemplateDialog: showTemplateDialog,
            templateFormTab: templateFormTab,
            newGroupName: newGroupName,
            newTemplateName: newTemplateName,
            newTemplateDescription: newTemplateDescription,
            newTemplateTitleTemplate: newTemplateTitleTemplate,
            newTemplateProductDescription: newTemplateProductDescription,
            newTemplateSizeChart: newTemplateSizeChart,
            newTemplateSizeChartPreview: newTemplateSizeChartPreview,
            newTemplateGroupId: newTemplateGroupId,
            newTemplateImage: newTemplateImage,
            newTemplateImagePreview: newTemplateImagePreview,
            newPackageWeight: newPackageWeight,
            newPackageLength: newPackageLength,
            newPackageWidth: newPackageWidth,
            newPackageHeight: newPackageHeight,
            newSkuSizeOptions: newSkuSizeOptions,
            newTemplateAiPrompts: newTemplateAiPrompts,
            editingTemplate: editingTemplate,
            showMemberDialog: showMemberDialog,
            editingMember: editingMember,
            memberForm: memberForm,
            memberSaving: memberSaving,
            memberFormError: memberFormError,
            memberListRefreshing: memberListRefreshing,
            showOperatorGroupDialog: showOperatorGroupDialog,
            editingOperatorGroup: editingOperatorGroup,
            operatorGroupForm: operatorGroupForm,
            operatorGroupSaving: operatorGroupSaving,
            operatorGroupError: operatorGroupError,
            showMemberCredentialDialog: showMemberCredentialDialog,
            credentialMember: credentialMember,
            credentialProvider: credentialProvider,
            credentialApiKey: credentialApiKey,
            credentialSaving: credentialSaving,
            showMyAccountDialog: showMyAccountDialog,
            myName: myName,
            myUserCode: myUserCode,
            myAccountSaving: myAccountSaving,
            shopLoading: shopLoading,
            shopError: shopError,
            activeMiaoshouTab: activeMiaoshouTab,
            showMiaoshouDialog: showMiaoshouDialog,
            miaoshouForm: miaoshouForm,
            miaoshouSaving: miaoshouSaving,
            showHubstudioDialog: showHubstudioDialog,
            hubstudioSaving: hubstudioSaving,
            hubstudioForm: hubstudioForm,
            hubUploadTasks: hubUploadTasks,
            hubUploadTotal: hubUploadTotal,
            hubUploadPage: hubUploadPage,
            hubUploadPageSize: hubUploadPageSize,
            hubUploadCreatorId: hubUploadCreatorId,
            hubUploadLoading: hubUploadLoading,
            hubUploadError: hubUploadError,
            hubUploadTemplateId: hubUploadTemplateId,
            hubUploadTemplates: hubUploadTemplates,
            hubUploadPageCount: hubUploadPageCount,
            hubUploadStatusLabels: hubUploadStatusLabels,
            loadHubUploadTasks: loadHubUploadTasks,
            changeHubUploadPageSize: changeHubUploadPageSize,
            changeHubUploadCreator: changeHubUploadCreator,
            changeHubUploadPage: changeHubUploadPage,
            hubUploadEnvironment: hubUploadEnvironment,
            tiktokCatalogLoading: tiktokCatalogLoading,
            tiktokCatalogError: tiktokCatalogError,
            tiktokCatalogListRefreshing: tiktokCatalogListRefreshing,
            showTiktokCatalogDialog: showTiktokCatalogDialog,
            tiktokCatalogName: tiktokCatalogName,
            tiktokCatalogTypeTab: tiktokCatalogTypeTab,
            showTiktokCatalogDetailDialog: showTiktokCatalogDetailDialog,
            managingTiktokCatalog: managingTiktokCatalog,
            managingTiktokCatalogOptions: managingTiktokCatalogOptions,
            managingTiktokCategory: managingTiktokCategory,
            materialUploading: materialUploading,
            materialUploadError: materialUploadError,
            materialDownloading: materialDownloading,
            selectedMaterialAssetIds: selectedMaterialAssetIds,
            materialTemplateFilterId: materialTemplateFilterId,
            showMaterialDraftDialog: showMaterialDraftDialog,
            materialDraftTitle: materialDraftTitle,
            materialDraftProductDescription: materialDraftProductDescription,
            materialDraftSizeChartPreview: materialDraftSizeChartPreview,
            materialDraftTitleGenerating: materialDraftTitleGenerating,
            materialDraftSaving: materialDraftSaving,
            materialDraftAdditionalRequirements: materialDraftAdditionalRequirements,
            showDraftAdditionalRequirements: showDraftAdditionalRequirements,
            showDraftTitleHelp: showDraftTitleHelp,
            libraryDraftMode: libraryDraftMode,
            materialDraftTitleEdited: materialDraftTitleEdited,
            materialDraftAssets: materialDraftAssets,
            draggedMaterialDraftAssetId: draggedMaterialDraftAssetId,
            activeMaterialUsageTab: activeMaterialUsageTab,
            materialUsageTabs: materialUsageTabs,
            showMaterialBatchDraftDialog: showMaterialBatchDraftDialog,
            materialBatchGroupSize: materialBatchGroupSize,
            materialBatchMode: materialBatchMode,
            materialBatchGroups: materialBatchGroups,
            materialBatchSaving: materialBatchSaving,
            draggedMaterialBatchAsset: draggedMaterialBatchAsset,
            pendingMaterialUploadFiles: pendingMaterialUploadFiles,
            showMaterialUploadDialog: showMaterialUploadDialog,
            materialUploadTemplateId: materialUploadTemplateId,
            materialUploadedCount: materialUploadedCount,
            materialUploadTotal: materialUploadTotal,
            templateSaving: templateSaving,
            showDraftEditDialog: showDraftEditDialog,
            editingDraft: editingDraft,
            draftEditTitle: draftEditTitle,
            draftEditProductDescription: draftEditProductDescription,
            draftEditSaving: draftEditSaving,
            draftEditError: draftEditError,
            publishingDraftId: publishingDraftId,
            skippingCarouselDraftId: skippingCarouselDraftId,
            skippingMainImageDraftId: skippingMainImageDraftId,
            dispatchingDraftStage: dispatchingDraftStage,
            selectedDraftIds: selectedDraftIds,
            showTiktokExportDialog: showTiktokExportDialog,
            tiktokExportOptions: tiktokExportOptions,
            tiktokExportLoading: tiktokExportLoading,
            tiktokExportError: tiktokExportError,
            showShopeeExportDialog: showShopeeExportDialog,
            shopeeExportOptions: shopeeExportOptions,
            shopeeExportLoading: shopeeExportLoading,
            shopeeExportError: shopeeExportError,
            showMiaoshouPublishDialog: showMiaoshouPublishDialog,
            miaoshouPublishDraftIds: miaoshouPublishDraftIds,
            miaoshouPublishShopId: miaoshouPublishShopId,
            miaoshouPublishing: miaoshouPublishing,
            miaoshouPublishCompleted: miaoshouPublishCompleted,
            miaoshouPublishFailed: miaoshouPublishFailed,
            showBatchCarouselDialog: showBatchCarouselDialog,
            showBatchMainImageDialog: showBatchMainImageDialog,
            batchCarouselSaving: batchCarouselSaving,
            batchMainImageSaving: batchMainImageSaving,
            batchCarouselSkipping: batchCarouselSkipping,
            batchMainImageSkipping: batchMainImageSkipping,
            batchCarouselSelections: batchCarouselSelections,
            batchMainImageSelections: batchMainImageSelections,
            showBatchImageReviewDialog: showBatchImageReviewDialog,
            batchImageReviewLoading: batchImageReviewLoading,
            batchImageReviewSaving: batchImageReviewSaving,
            batchImageReviewType: batchImageReviewType,
            batchImageReviewDrafts: batchImageReviewDrafts,
            batchImageReviewSelections: batchImageReviewSelections,
            batchCarouselReviewNextStage: batchCarouselReviewNextStage,
            MAX_DRAFT_BATCH_SIZE: MAX_DRAFT_BATCH_SIZE,
            tiktokExportCatalogId: tiktokExportCatalogId,
            tiktokExportCategory: tiktokExportCategory,
            tiktokExportDefaultPrice: tiktokExportDefaultPrice,
            tiktokExportDefaultQuantity: tiktokExportDefaultQuantity,
            tiktokExportCod: tiktokExportCod,
            tiktokExportAttributes: tiktokExportAttributes,
            tiktokExportOverrides: tiktokExportOverrides,
            tiktokSubmitting: tiktokSubmitting,
            shopeeExportCatalogId: shopeeExportCatalogId,
            shopeeExportCategoryId: shopeeExportCategoryId,
            shopeeExportDefaultPrice: shopeeExportDefaultPrice,
            shopeeExportDefaultQuantity: shopeeExportDefaultQuantity,
            shopeeExportChannels: shopeeExportChannels,
            shopeeExportOverrides: shopeeExportOverrides,
            draftPageSize: draftPageSize,
            draftTemplateFilterId: draftTemplateFilterId,
            draftCreatorFilterId: draftCreatorFilterId,
            draftListRefreshing: draftListRefreshing,
            collectBoxItems: collectBoxItems,
            collectBoxTotal: collectBoxTotal,
            collectBoxLoading: collectBoxLoading,
            productLibraryItems: productLibraryItems,
            productLibraryTotal: productLibraryTotal,
            productLibraryPage: productLibraryPage,
            productLibraryPageSize: productLibraryPageSize,
            productLibraryLoading: productLibraryLoading,
            productLibraryImporting: productLibraryImporting,
            productLibraryDownloading: productLibraryDownloading,
            productLibraryStatisticsSubmitting: productLibraryStatisticsSubmitting,
            productLibraryStatisticsTask: productLibraryStatisticsTask,
            productLibraryRankingItems: productLibraryRankingItems,
            productLibraryRankingTotal: productLibraryRankingTotal,
            productLibraryRankingPage: productLibraryRankingPage,
            productLibraryRankingPageSize: productLibraryRankingPageSize,
            productLibraryRankingLoading: productLibraryRankingLoading,
            productLibraryRankingDate: productLibraryRankingDate,
            productLibraryRankingThroughDate: productLibraryRankingThroughDate,
            productLibraryRankingError: productLibraryRankingError,
            productLibraryShops: productLibraryShops,
            productLibraryShopsLoading: productLibraryShopsLoading,
            productLibraryAssigningId: productLibraryAssigningId,
            stagnantMaterials: stagnantMaterials,
            stagnantTotal: stagnantTotal,
            stagnantPage: stagnantPage,
            stagnantPageSize: stagnantPageSize,
            stagnantCreatorId: stagnantCreatorId,
            stagnantLoading: stagnantLoading,
            stagnantError: stagnantError,
            newImages: newImages,
            newImagesTotal: newImagesTotal,
            newImagesPage: newImagesPage,
            newImagesPageSize: newImagesPageSize,
            newImagesCreatorId: newImagesCreatorId,
            newImagesUsageStatus: newImagesUsageStatus,
            newImagesLoading: newImagesLoading,
            newImagesError: newImagesError,
            activeProductLibraryTab: activeProductLibraryTab,
            productLibraryTabs: productLibraryTabs,
            productLibraryRankingTabKeys: productLibraryRankingTabKeys,
            productLibraryTopTabKeys: productLibraryTopTabKeys,
            productLibraryCategoryDescriptions: productLibraryCategoryDescriptions,
            productLibrarySelectedShopIds: productLibrarySelectedShopIds,
            productLibraryShopSearch: productLibraryShopSearch,
            productLibraryShopFilterDetails: productLibraryShopFilterDetails,
            productLibraryShopOptions: productLibraryShopOptions,
            productLibraryShopSelectionLabel: productLibraryShopSelectionLabel,
            productLibraryTemplateFilter: productLibraryTemplateFilter,
            productLibrarySku: productLibrarySku,
            selectedProductLibraryIds: selectedProductLibraryIds,
            productLibraryBrokenImages: productLibraryBrokenImages,
            showProductLibraryTemplateDialog: showProductLibraryTemplateDialog,
            productLibraryTargetTemplateId: productLibraryTargetTemplateId,
            productLibraryTemplateSaving: productLibraryTemplateSaving,
            productLibraryOrderProduct: productLibraryOrderProduct,
            productLibraryOrders: productLibraryOrders,
            productLibraryOrderTotal: productLibraryOrderTotal,
            productLibraryOrderCount: productLibraryOrderCount,
            productLibraryOrderPage: productLibraryOrderPage,
            productLibraryOrderPageSize: productLibraryOrderPageSize,
            productLibraryOrderLoading: productLibraryOrderLoading,
            productLibraryFileInput: productLibraryFileInput,
            collectBoxConfigured: collectBoxConfigured,
            collectBoxLastSyncedAt: collectBoxLastSyncedAt,
            collectBoxInitialSyncedAt: collectBoxInitialSyncedAt,
            collectBoxQuery: collectBoxQuery,
            collectBoxPage: collectBoxPage,
            collectBoxPageSize: collectBoxPageSize,
            activeDraftTab: activeDraftTab,
            draftTotal: draftTotal,
            draftTabCounts: draftTabCounts,
            activeDraftWorkStatus: activeDraftWorkStatus,
            draftWorkStatusCounts: draftWorkStatusCounts,
            draftWorkStatusTabs: draftWorkStatusTabs,
            draftTabs: draftTabs,
            draftStatusLabels: draftStatusLabels,
            taskTypeLabels: taskTypeLabels,
            activeTaskType: activeTaskType,
            taskPageSize: taskPageSize,
            taskTotal: taskTotal,
            taskStatusCounts: taskStatusCounts,
            taskCreatorFilterId: taskCreatorFilterId,
            taskTypeTotals: taskTypeTotals,
            taskTypeFilteredTotals: taskTypeFilteredTotals,
            taskStatusFilter: taskStatusFilter,
            taskCreatedFrom: taskCreatedFrom,
            taskCreatedTo: taskCreatedTo,
            taskSkuQuery: taskSkuQuery,
            taskTemplateFilterId: taskTemplateFilterId,
            selectedTaskIds: selectedTaskIds,
            showBatchClaimDialog: showBatchClaimDialog,
            batchClaimLoading: batchClaimLoading,
            batchClaiming: batchClaiming,
            batchClaimCompleted: batchClaimCompleted,
            batchClaimTotal: batchClaimTotal,
            batchClaimFailed: batchClaimFailed,
            materialPageSize: materialPageSize,
            materialTotal: materialTotal,
            materialCreatorFilterId: materialCreatorFilterId,
            materialListRefreshing: materialListRefreshing,
            previewImageUrl: previewImageUrl,
            previewImageAlt: previewImageAlt,
            showDraftImageDialog: showDraftImageDialog,
            imageWorkspaceMode: imageWorkspaceMode,
            imageDraft: imageDraft,
            imageWorkspaceLoading: imageWorkspaceLoading,
            imageTasksRefreshing: imageTasksRefreshing,
            imageTaskCreatingType: imageTaskCreatingType,
            imageConfirmSaving: imageConfirmSaving,
            carouselConfirmNextStage: carouselConfirmNextStage,
            selectedImageSkus: selectedImageSkus,
            selectedMainReferences: selectedMainReferences,
            mainReferenceMode: mainReferenceMode,
            carouselParams: carouselParams,
            mainParams: mainParams,
            batchCarouselParams: batchCarouselParams,
            batchMainImageParams: batchMainImageParams,
            batchMainImageReferenceMode: batchMainImageReferenceMode,
            draggedFinalImageUrl: draggedFinalImageUrl,
            showMainApplyDialog: showMainApplyDialog,
            pendingMainApply: pendingMainApply,
            mainRemoveSku: mainRemoveSku,
            showShopManagersDialog: showShopManagersDialog,
            managingShop: managingShop,
            selectedManagerIds: selectedManagerIds,
            shopManagersSaving: shopManagersSaving,
            showTaskDetailDialog: showTaskDetailDialog,
            viewingTask: viewingTask,
            taskListRefreshing: taskListRefreshing,
            retryingTaskId: retryingTaskId,
            batchRetryingTasks: batchRetryingTasks,
            retryingWorkspaceTaskId: retryingWorkspaceTaskId,
            showClaimMaterialsDialog: showClaimMaterialsDialog,
            claimingTask: claimingTask,
            selectedClaimResultUrls: selectedClaimResultUrls,
            claimingMaterials: claimingMaterials,
            creativeAssets: creativeAssets,
            showCreativeAssetsDialog: showCreativeAssetsDialog,
            creativeAssetError: creativeAssetError,
            creativeSubmitError: creativeSubmitError,
            creativeRequirement: creativeRequirement,
            creativePromptIndex: creativePromptIndex,
            creativeProvider: creativeProvider,
            creativeRatio: creativeRatio,
            creativeQuality: creativeQuality,
            creativeUploading: creativeUploading,
            creativeUploadedCount: creativeUploadedCount,
            personalWhiteImages: personalWhiteImages,
            personalPrompts: personalPrompts,
            selectedWhiteImageId: selectedWhiteImageId,
            personalResourcesLoading: personalResourcesLoading,
            showPersonalResourcesDialog: showPersonalResourcesDialog,
            personalResourceTab: personalResourceTab,
            managedWhiteImages: managedWhiteImages,
            managedPrompts: managedPrompts,
            personalResourceSaving: personalResourceSaving,
            showTeamResourcesDialog: showTeamResourcesDialog,
            teamResourceTab: teamResourceTab,
            teamResourceUserId: teamResourceUserId,
            teamResourceTemplateId: teamResourceTemplateId,
            teamWhiteImages: teamWhiteImages,
            teamPrompts: teamPrompts,
            teamResourcesLoading: teamResourcesLoading,
            teamResourceQuery: teamResourceQuery,
            editingWhiteImage: editingWhiteImage,
            whiteImageForm: whiteImageForm,
            editingPersonalPrompt: editingPersonalPrompt,
            personalPromptForm: personalPromptForm,
            visibleNav: visibleNav,
            pageTitle: pageTitle,
            filteredTemplates: filteredTemplates,
            templateGroupIsEmpty: templateGroupIsEmpty,
            availableAiProviders: availableAiProviders,
            memberCredentialProviders: memberCredentialProviders,
            creativeCredentialError: creativeCredentialError,
            selectedWhiteImage: selectedWhiteImage,
            otherResourceOwners: otherResourceOwners,
            filteredTeamWhiteImages: filteredTeamWhiteImages,
            filteredTeamPrompts: filteredTeamPrompts,
            filteredMaterialAssets: filteredMaterialAssets,
            allCurrentMaterialAssetsSelected: allCurrentMaterialAssetsSelected,
            someCurrentMaterialAssetsSelected: someCurrentMaterialAssetsSelected,
            materialDraftTemplate: materialDraftTemplate,
            materialDraftSizes: materialDraftSizes,
            materialDraftSkuCount: materialDraftSkuCount,
            filteredDrafts: filteredDrafts,
            draftPageCount: draftPageCount,
            visibleDraftPage: visibleDraftPage,
            pagedDrafts: pagedDrafts,
            selectedDrafts: selectedDrafts,
            allPagedDraftsSelected: allPagedDraftsSelected,
            batchDispatchEligible: batchDispatchEligible,
            crossBorderManagedShops: crossBorderManagedShops,
            miaoshouAssignableShops: miaoshouAssignableShops,
            batchMiaoshouPublishEligible: batchMiaoshouPublishEligible,
            tiktokExportEligible: tiktokExportEligible,
            batchCarouselEligible: batchCarouselEligible,
            batchCarouselReviewEligible: batchCarouselReviewEligible,
            batchCarouselSkipEligible: batchCarouselSkipEligible,
            batchMainImageSkipEligible: batchMainImageSkipEligible,
            batchMainImageEligible: batchMainImageEligible,
            batchMainImageReviewEligible: batchMainImageReviewEligible,
            selectedTiktokCategoryAttributes: selectedTiktokCategoryAttributes,
            managingTiktokCategoryAttributes: managingTiktokCategoryAttributes,
            activeTiktokCatalogs: activeTiktokCatalogs,
            tiktokExportCatalogs: tiktokExportCatalogs,
            shopeeCatalogs: shopeeCatalogs,
            tiktokExportIsLocal: tiktokExportIsLocal,
            tiktokCatalogTypeLabel: tiktokCatalogTypeLabel,
            changeDraftPageSize: changeDraftPageSize,
            changeDraftTab: changeDraftTab,
            changeDraftWorkStatus: changeDraftWorkStatus,
            changeDraftPage: changeDraftPage,
            toggleDraftSelection: toggleDraftSelection,
            togglePagedDrafts: togglePagedDrafts,
            changeDraftTemplateFilter: changeDraftTemplateFilter,
            changeDraftCreatorFilter: changeDraftCreatorFilter,
            draftWorkSummary: draftWorkSummary,
            dispatchSelectedDrafts: dispatchSelectedDrafts,
            openBatchCarouselDialog: openBatchCarouselDialog,
            toggleBatchCarouselSku: toggleBatchCarouselSku,
            mainCarouselItems: mainCarouselItems,
            mainSkuItems: mainSkuItems,
            batchMainImageEffectiveMode: batchMainImageEffectiveMode,
            batchMainImageReferenceItems: batchMainImageReferenceItems,
            openBatchMainImageDialog: openBatchMainImageDialog,
            toggleBatchMainImageReference: toggleBatchMainImageReference,
            batchReviewTasks: batchReviewTasks,
            batchReviewSelectedCount: batchReviewSelectedCount,
            batchReviewTotalTasks: batchReviewTotalTasks,
            batchReviewChosenTasks: batchReviewChosenTasks,
            toggleBatchReviewResult: toggleBatchReviewResult,
            selectAllBatchReviewTasks: selectAllBatchReviewTasks,
            clearBatchReviewDraft: clearBatchReviewDraft,
            openBatchImageReview: openBatchImageReview,
            confirmBatchImageReview: confirmBatchImageReview,
            createBatchCarouselTasks: createBatchCarouselTasks,
            createBatchMainImageTasks: createBatchMainImageTasks,
            skipDraftCarousel: skipDraftCarousel,
            batchSkipDraftCarousel: batchSkipDraftCarousel,
            skipDraftMainImage: skipDraftMainImage,
            batchSkipDraftMainImage: batchSkipDraftMainImage,
            taskPageCount: taskPageCount,
            visibleTaskPage: visibleTaskPage,
            pagedTasks: pagedTasks,
            selectablePagedTasks: selectablePagedTasks,
            selectedClaimableTaskIds: selectedClaimableTaskIds,
            selectedRetryTaskIds: selectedRetryTaskIds,
            allSelectableTasksSelected: allSelectableTasksSelected,
            someSelectableTasksSelected: someSelectableTasksSelected,
            groupedBatchClaimItems: groupedBatchClaimItems,
            changeTaskPageSize: changeTaskPageSize,
            changeTaskPage: changeTaskPage,
            switchTaskType: switchTaskType,
            taskTypeLabel: taskTypeLabel,
            searchTasks: searchTasks,
            materialPageCount: materialPageCount,
            visibleMaterialPage: visibleMaterialPage,
            changeMaterialPageSize: changeMaterialPageSize,
            changeMaterialPage: changeMaterialPage,
            changeMaterialFilter: changeMaterialFilter,
            changeMaterialUsageTab: changeMaterialUsageTab,
            collectBoxPageCount: collectBoxPageCount,
            changeMiaoshouTab: changeMiaoshouTab,
            changeCollectBoxFilters: changeCollectBoxFilters,
            changeCollectBoxPage: changeCollectBoxPage,
            productLibraryPageCount: productLibraryPageCount,
            productLibraryRankingPageCount: productLibraryRankingPageCount,
            stagnantPageCount: stagnantPageCount,
            newImagesPageCount: newImagesPageCount,
            productLibraryOrderPageCount: productLibraryOrderPageCount,
            selectableProductLibraryItems: selectableProductLibraryItems,
            productLibrarySelectionLoading: productLibrarySelectionLoading,
            draftSelectionAssets: draftSelectionAssets,
            allPagedProductsSelected: allPagedProductsSelected,
            assignProductLibraryShop: assignProductLibraryShop,
            changeStagnantCreator: changeStagnantCreator,
            changeStagnantPageSize: changeStagnantPageSize,
            changeStagnantPage: changeStagnantPage,
            changeNewImagesFilters: changeNewImagesFilters,
            changeNewImagesPageSize: changeNewImagesPageSize,
            changeNewImagesPage: changeNewImagesPage,
            changeProductLibraryRankingPage: changeProductLibraryRankingPage,
            changeProductLibraryRankingPageSize: changeProductLibraryRankingPageSize,
            searchProductLibrary: searchProductLibrary,
            changeProductLibraryPageSize: changeProductLibraryPageSize,
            changeProductLibraryTab: changeProductLibraryTab,
            changeProductLibraryPage: changeProductLibraryPage,
            openProductLibraryOrders: openProductLibraryOrders,
            closeProductLibraryOrders: closeProductLibraryOrders,
            changeProductLibraryOrderPageSize: changeProductLibraryOrderPageSize,
            changeProductLibraryOrderPage: changeProductLibraryOrderPage,
            toggleProductLibrarySelection: toggleProductLibrarySelection,
            togglePagedProducts: togglePagedProducts,
            openProductLibraryTemplateDialog: openProductLibraryTemplateDialog,
            saveProductLibraryTemplate: saveProductLibraryTemplate,
            downloadProductLibraryTemplate: downloadProductLibraryTemplate,
            importProductLibrary: importProductLibrary,
            runProductLibraryStatistics: runProductLibraryStatistics,
            login: login,
            onCreativeAssetChange: onCreativeAssetChange,
            removeCreativeAsset: removeCreativeAsset,
            clearCreativeAssets: clearCreativeAssets,
            createTask: createTask,
            createGroup: createGroup,
            deleteTemplateGroup: deleteTemplateGroup,
            openTemplateDialog: openTemplateDialog,
            addSkuSize: addSkuSize,
            addTemplateAiPrompt: addTemplateAiPrompt,
            removeTemplateAiPrompt: removeTemplateAiPrompt,
            selectedTemplateAiPrompts: selectedTemplateAiPrompts,
            applyTemplateAiPrompt: applyTemplateAiPrompt,
            onCreativeTemplateChange: onCreativeTemplateChange,
            openPersonalResourcesDialog: openPersonalResourcesDialog,
            loadTeamTemplateResources: loadTeamTemplateResources,
            openTeamResourcesDialog: openTeamResourcesDialog,
            resetWhiteImageForm: resetWhiteImageForm,
            editWhiteImage: editWhiteImage,
            onWhiteImageFileChange: onWhiteImageFileChange,
            saveWhiteImage: saveWhiteImage,
            deleteWhiteImage: deleteWhiteImage,
            resetPersonalPromptForm: resetPersonalPromptForm,
            editPersonalPrompt: editPersonalPrompt,
            resourceTemplateName: resourceTemplateName,
            savePersonalPrompt: savePersonalPrompt,
            deletePersonalPrompt: deletePersonalPrompt,
            onCoverChange: onCoverChange,
            onSizeChartChange: onSizeChartChange,
            createTemplate: createTemplate,
            deleteTemplate: deleteTemplate,
            imageUrl: imageUrl,
            taskStatusLabel: taskStatusLabel,
            taskStatusClass: taskStatusClass,
            copyProviderTaskId: copyProviderTaskId,
            openTaskDetail: openTaskDetail,
            templateCoverUrl: templateCoverUrl,
            hasTemplateCover: hasTemplateCover,
            useTemplate: useTemplate,
            toggleMaterialAsset: toggleMaterialAsset,
            toggleAllCurrentMaterialAssets: toggleAllCurrentMaterialAssets,
            materialTemplateName: materialTemplateName,
            draftTemplateName: draftTemplateName,
            generateMaterialDraftTitle: generateMaterialDraftTitle,
            openMaterialDraftDialog: openMaterialDraftDialog,
            openProductLibraryDraftDialog: openProductLibraryDraftDialog,
            startMaterialDraftDrag: startMaterialDraftDrag,
            dropMaterialDraftAsset: dropMaterialDraftAsset,
            createDraftFromMaterialAssets: createDraftFromMaterialAssets,
            openMaterialBatchDraftDialog: openMaterialBatchDraftDialog,
            rebuildMaterialBatchGroups: rebuildMaterialBatchGroups,
            startMaterialBatchDrag: startMaterialBatchDrag,
            dropMaterialBatchAsset: dropMaterialBatchAsset,
            generateMaterialBatchTitle: generateMaterialBatchTitle,
            createMaterialBatchDrafts: createMaterialBatchDrafts,
            openDraftEditDialog: openDraftEditDialog,
            draftSkuForImage: draftSkuForImage,
            draftEditSkus: draftEditSkus,
            openImagePreview: openImagePreview,
            openTemplateCoverPreview: openTemplateCoverPreview,
            imageDraftSkus: imageDraftSkus,
            draftFinalImageItems: draftFinalImageItems,
            draftImagePreviewUrls: draftImagePreviewUrls,
            adoptedCarouselItems: adoptedCarouselItems,
            mainCarouselReferenceItems: mainCarouselReferenceItems,
            mainSkuReferenceItems: mainSkuReferenceItems,
            currentGeneratedMainImage: currentGeneratedMainImage,
            selectMainReferenceMode: selectMainReferenceMode,
            openCarouselImageWorkspace: openCarouselImageWorkspace,
            openFullImageWorkspace: openFullImageWorkspace,
            toggleImageSku: toggleImageSku,
            toggleMainReference: toggleMainReference,
            createDraftImageTasks: createDraftImageTasks,
            isWorkspaceTaskSelected: isWorkspaceTaskSelected,
            isTaskResultSelected: isTaskResultSelected,
            taskHasSuccessfulResult: taskHasSuccessfulResult,
            applyImageTaskResult: applyImageTaskResult,
            workspaceCarouselTasks: workspaceCarouselTasks,
            refreshWorkspaceTasks: refreshWorkspaceTasks,
            toggleWorkspaceCarouselTask: toggleWorkspaceCarouselTask,
            workspaceMainTasks: workspaceMainTasks,
            workspaceFailedTasks: workspaceFailedTasks,
            toggleWorkspaceMainTask: toggleWorkspaceMainTask,
            dropFinalImage: dropFinalImage,
            removeFinalImage: removeFinalImage,
            openImageWorkspaceFromTask: openImageWorkspaceFromTask,
            confirmDraftImages: confirmDraftImages,
            saveDraftEdit: saveDraftEdit,
            publishDraftToMiaoshou: publishDraftToMiaoshou,
            openBatchMiaoshouPublishDialog: openBatchMiaoshouPublishDialog,
            confirmMiaoshouPublish: confirmMiaoshouPublish,
            openTiktokExportDialog: openTiktokExportDialog,
            openShopeeExportDialog: openShopeeExportDialog,
            changeShopeeExportCatalog: changeShopeeExportCatalog,
            exportSelectedDraftsToShopee: exportSelectedDraftsToShopee,
            changeTiktokExportCategory: changeTiktokExportCategory,
            changeTiktokExportCatalog: changeTiktokExportCatalog,
            tiktokAttributeMode: tiktokAttributeMode,
            tiktokAttributePlaceholder: tiktokAttributePlaceholder,
            exportSelectedDrafts: exportSelectedDrafts,
            submitSelectedDraftsToHubstudio: submitSelectedDraftsToHubstudio,
            refreshTiktokCatalogList: refreshTiktokCatalogList,
            openTiktokCatalogCreateDialog: openTiktokCatalogCreateDialog,
            onTiktokCatalogFileChange: onTiktokCatalogFileChange,
            createTiktokCatalog: createTiktokCatalog,
            openTiktokCatalogDetail: openTiktokCatalogDetail,
            onTiktokInputModeChange: onTiktokInputModeChange,
            deleteTiktokCatalog: deleteTiktokCatalog,
            openClaimMaterialsDialog: openClaimMaterialsDialog,
            toggleClaimResult: toggleClaimResult,
            claimMaterials: claimMaterials,
            toggleTaskSelection: toggleTaskSelection,
            taskCanBeSelected: taskCanBeSelected,
            toggleAllSelectableTasks: toggleAllSelectableTasks,
            removeBatchClaimImage: removeBatchClaimImage,
            openBatchClaimDialog: openBatchClaimDialog,
            confirmBatchClaim: confirmBatchClaim,
            retryTaskResult: retryTaskResult,
            retrySelectedTasks: retrySelectedTasks,
            retryWorkspaceTask: retryWorkspaceTask,
            ignoreWorkspaceTaskFailure: ignoreWorkspaceTaskFailure,
            chooseMaterialUploadFiles: chooseMaterialUploadFiles,
            uploadMaterialAssets: uploadMaterialAssets,
            deleteSelectedMaterialAssets: deleteSelectedMaterialAssets,
            downloadSelectedMaterialAssets: downloadSelectedMaterialAssets,
            refreshMemberList: refreshMemberList,
            operatorGroupName: operatorGroupName,
            operatorGroupMembers: operatorGroupMembers,
            memberRoleLabel: memberRoleLabel,
            openOperatorGroupDialog: openOperatorGroupDialog,
            saveOperatorGroup: saveOperatorGroup,
            deleteOperatorGroup: deleteOperatorGroup,
            openMemberDialog: openMemberDialog,
            openMyAccountDialog: openMyAccountDialog,
            saveMyUserCode: saveMyUserCode,
            saveMember: saveMember,
            toggleMember: toggleMember,
            openMemberCredentialDialog: openMemberCredentialDialog,
            memberCredentialKey: memberCredentialKey,
            memberCredentialPreview: memberCredentialPreview,
            saveMemberCredential: saveMemberCredential,
            clearMemberCredential: clearMemberCredential,
            loadMiaoshouShops: loadMiaoshouShops,
            openMiaoshouDialog: openMiaoshouDialog,
            saveMiaoshouAccount: saveMiaoshouAccount,
            openShopManagersDialog: openShopManagersDialog,
            saveShopManagers: saveShopManagers,
            openHubstudioDialog: openHubstudioDialog,
            saveHubstudioAccount: saveHubstudioAccount,
            logout: logout,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
