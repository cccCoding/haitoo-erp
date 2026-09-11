import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import axios from 'axios';
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' });
const token = ref(localStorage.getItem('haitoro_token') || '');
const page = ref(new URLSearchParams(location.search).has('task_type') ? 'tasks' : 'dashboard');
const email = ref('');
const password = ref('');
const user = ref(null), company = ref(null), shops = ref([]), templates = ref([]), templateGroups = ref([]), tasks = ref([]), materialAssets = ref([]), drafts = ref([]), members = ref([]), aiProviders = ref([]);
const loading = ref(false), error = ref('');
const toast = ref('');
const templateQuery = ref(''), activeGroupId = ref(null), selectedTemplateId = ref(null);
const showGroupDialog = ref(false), showTemplateDialog = ref(false), templateFormTab = ref('basic'), newGroupName = ref(''), newTemplateName = ref(''), newTemplateDescription = ref(''), newTemplateTitleTemplate = ref(''), newTemplateProductDescription = ref(''), newTemplateSizeChart = ref(null), newTemplateSizeChartPreview = ref(''), newTemplateGroupId = ref(null), newTemplateImage = ref(null), newTemplateImagePreview = ref(''), newPackageWeight = ref(null), newPackageLength = ref(null), newPackageWidth = ref(null), newPackageHeight = ref(null), newSkuSizeOptions = ref([]), newTemplateAiPrompts = ref([]), editingTemplate = ref(null);
const showMemberDialog = ref(false), editingMember = ref(null), memberForm = ref({ name: '', user_code: '', email: '', password: '', is_active: true }), memberSaving = ref(false), memberFormError = ref('');
const showMemberCredentialDialog = ref(false), credentialMember = ref(null), credentialProvider = ref(null), credentialApiKey = ref(''), credentialSaving = ref(false);
const showMyAccountDialog = ref(false), myName = ref(''), myUserCode = ref(''), myAccountSaving = ref(false);
const managedShops = ref([]), shopLoading = ref(false), shopError = ref('');
const showMiaoshouDialog = ref(false), miaoshouForm = ref({ app_id: '', app_secret: '' }), miaoshouSaving = ref(false);
const tiktokCatalogs = ref([]), tiktokCatalogLoading = ref(false), tiktokCatalogError = ref('');
const showTiktokCatalogDialog = ref(false), tiktokCatalogName = ref(''), tiktokCatalogFile = ref(null);
const showTiktokCatalogDetailDialog = ref(false), managingTiktokCatalog = ref(null), managingTiktokCatalogOptions = ref(null), managingTiktokCategory = ref('');
const materialUploading = ref(false), materialUploadError = ref('');
const materialDownloading = ref(false);
const selectedMaterialAssetIds = ref([]), materialTemplateFilterId = ref(null), showMaterialDraftDialog = ref(false), materialDraftTemplateId = ref(null), materialDraftTitle = ref(''), materialDraftProductDescription = ref(''), materialDraftSizeChartPreview = ref(''), materialDraftTitleGenerating = ref(false), materialDraftSaving = ref(false);
const pendingMaterialUploadFiles = ref([]), showMaterialUploadDialog = ref(false), materialUploadTemplateId = ref(null);
const materialUploadedCount = ref(0), materialUploadTotal = ref(0), pendingMaterialUploadUrls = ref([]);
const MATERIAL_UPLOAD_CONCURRENCY = 8, MATERIAL_UPLOAD_MAX_FILES = 100, IMAGE_UPLOAD_RETRY = 2;
const templateSaving = ref(false);
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'], MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const showDraftEditDialog = ref(false), editingDraft = ref(null), draftEditTitle = ref(''), draftEditProductDescription = ref(''), draftEditSaving = ref(false), draftEditError = ref('');
const publishingDraftId = ref(null);
const selectedDraftIds = ref([]), showTiktokExportDialog = ref(false), tiktokExportOptions = ref(null), tiktokExportLoading = ref(false), tiktokExportError = ref('');
const MAX_TIKTOK_EXPORT_DRAFTS = 50;
const tiktokExportCatalogId = ref(null), tiktokExportCategory = ref(''), tiktokExportDefaultPrice = ref(null), tiktokExportDefaultQuantity = ref(999), tiktokExportCod = ref('Y'), tiktokExportAttributes = ref({}), tiktokExportOverrides = ref({});
const draftPageSize = ref(20), currentDraftPage = ref(1), draftTemplateFilterId = ref(null), draftCreatorFilterId = ref(null);
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
const taskPageSize = ref([20, 50, 100].includes(initialTaskPageSize) ? initialTaskPageSize : 20), currentTaskPage = ref(initialTaskPage > 0 ? initialTaskPage : 1), taskTotal = ref(0), taskActiveCount = ref(0), taskStatusCounts = ref({}), taskCreatorFilterId = ref(initialTaskCreator && initialTaskCreator !== 'all' ? Number(initialTaskCreator) || null : null);
const taskTypeTotals = ref({ sku_image: 0, carousel: 0, main_image: 0 });
const taskTypeFilteredTotals = ref({ sku_image: null, carousel: null, main_image: null });
const taskTabStates = ref({ sku_image: null, carousel: null, main_image: null });
const taskStatusFilter = ref(initialTaskStatus !== null && ['queued', 'running', 'awaiting_selection', 'completed', 'failed', ''].includes(initialTaskStatus) ? initialTaskStatus : 'awaiting_selection'), taskCreatedFrom = ref(initialTaskFrom), taskCreatedTo = ref(initialTaskTo);
const appliedTaskFilters = ref({ creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: initialTaskFrom ? new Date(initialTaskFrom).toISOString() : '', created_to: initialTaskTo ? new Date(initialTaskTo).toISOString() : '' });
const selectedTaskIds = ref([]), showBatchClaimDialog = ref(false), batchClaimItems = ref([]), batchClaimLoading = ref(false), batchClaiming = ref(false), batchClaimCompleted = ref(0), batchClaimTotal = ref(0), batchClaimFailed = ref(0);
const materialPageSize = ref(20), currentMaterialPage = ref(1), materialTotal = ref(0), materialCreatorFilterId = ref(null);
const creatorFiltersInitialized = ref(false);
const previewImageUrl = ref(''), previewImageAlt = ref('');
const showDraftImageDialog = ref(false), imageDraft = ref(null), imageWorkspaceLoading = ref(false), imageTasksRefreshing = ref(false), imageTaskCreatingType = ref(''), imageConfirmSaving = ref(false);
const selectedImageSkus = ref([]), selectedMainReferences = ref([]), mainReferenceMode = ref('random');
// 轮播图与首图任务使用各自独立的一套生成参数，互不干扰。
const carouselParams = ref({ prompt: '', provider: '', ratio: '1:1', quality: '1K' }), mainParams = ref({ prompt: '', provider: '', ratio: '1:1', quality: '1K' });
const draggedCarouselSku = ref(''), stagedFinalImageItems = ref(null), draggedFinalImageUrl = ref('');
const showMainApplyDialog = ref(false), pendingMainApply = ref(null), mainRemoveSku = ref('');
const showShopManagersDialog = ref(false), managingShop = ref(null), selectedManagerIds = ref([]), shopManagersSaving = ref(false);
const showTaskDetailDialog = ref(false), viewingTask = ref(null), taskDetailLoading = ref(false);
const taskListRefreshing = ref(false), retryingTaskId = ref(null);
const showClaimMaterialsDialog = ref(false), claimingTask = ref(null), selectedClaimResultUrls = ref([]), claimingMaterials = ref(false);
const defaultSkuSizes = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL'];
const defaultPackageLogistics = { weight: 0.28, length: 30, width: 16, height: 2 };
const creativeAssets = ref([]), showCreativeAssetsDialog = ref(false), creativeAssetError = ref(''), creativeSubmitError = ref(''), creativeRequirement = ref(''), creativePromptIndex = ref(''), creativeProvider = ref(''), creativeRatio = ref('1:1'), creativeQuality = ref('1K'), creativeUploading = ref(false), creativeUploadedCount = ref(0);
const personalWhiteImages = ref([]), personalPrompts = ref([]), selectedWhiteImageId = ref(null), personalResourcesLoading = ref(false);
const showPersonalResourcesDialog = ref(false), personalResourceTab = ref('white-images'), managedResourceUserId = ref(null), managedWhiteImages = ref([]), managedPrompts = ref([]), personalResourceSaving = ref(false);
const showTeamResourcesDialog = ref(false), teamResourceTab = ref('white-images'), teamResourceUserId = ref(null), teamResourceTemplateId = ref(null), teamWhiteImages = ref([]), teamPrompts = ref([]), teamResourcesLoading = ref(false), teamResourceQuery = ref('');
const editingWhiteImage = ref(null), whiteImageForm = ref({ template_id: null, name: '', file: null });
const editingPersonalPrompt = ref(null), personalPromptForm = ref({ template_id: null, name: '', content: '' });
const nav = [{ key: 'dashboard', icon: '◈', label: '工作台' }, { key: 'templates', icon: '▦', label: '产品模板' }, { key: 'pod', icon: '✦', label: 'AI创作' }, { key: 'tasks', icon: '◌', label: '任务中心' }, { key: 'materials', icon: '◈', label: '素材库' }, { key: 'drafts', icon: '▤', label: '商品草稿' }, { key: 'members', icon: '♙', label: '成员管理', adminOnly: true }, { key: 'shops', icon: '▣', label: '店铺管理', adminOnly: true }, { key: 'tiktok-catalogs', icon: '▧', label: 'TK类目管理', adminOnly: true }];
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }));
const visibleNav = computed(() => nav.filter(item => !item.adminOnly || user.value?.role === 'company_admin'));
const pageTitle = computed(() => nav.find(x => x.key === page.value)?.label || '');
const filteredTemplates = computed(() => templates.value.filter(t => (!activeGroupId.value || t.group_id === activeGroupId.value) && t.name.toLowerCase().includes(templateQuery.value.trim().toLowerCase())));
// 运营端接口只返回后台已启用的模型；这里再保留一次筛选，避免接口数据异常时将停用模型带入任务。
const availableAiProviders = computed(() => aiProviders.value.filter(provider => provider.enabled !== false));
const selectedCreativeProvider = computed(() => availableAiProviders.value.find(provider => provider.provider === creativeProvider.value));
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
const materialDraftSkuCount = computed(() => selectedMaterialAssets.value.length);
const filteredDrafts = computed(() => draftTemplateFilterId.value ? drafts.value.filter(draft => draft.template_id === draftTemplateFilterId.value) : drafts.value);
const draftPageCount = computed(() => Math.max(1, Math.ceil(filteredDrafts.value.length / draftPageSize.value)));
const visibleDraftPage = computed(() => Math.min(currentDraftPage.value, draftPageCount.value));
const pagedDrafts = computed(() => {
    const start = (visibleDraftPage.value - 1) * draftPageSize.value;
    return filteredDrafts.value.slice(start, start + draftPageSize.value);
});
const selectedDrafts = computed(() => drafts.value.filter(draft => selectedDraftIds.value.includes(draft.id)));
const allPagedDraftsSelected = computed(() => Boolean(pagedDrafts.value.length) && pagedDrafts.value.every(draft => selectedDraftIds.value.includes(draft.id)));
const selectedTiktokCategoryAttributes = computed(() => tiktokExportOptions.value?.attributes_by_category?.[tiktokExportCategory.value] || []);
const managingTiktokCategoryAttributes = computed(() => managingTiktokCatalogOptions.value?.attributes_by_category?.[managingTiktokCategory.value] || []);
function changeDraftPageSize() { currentDraftPage.value = 1; }
function toggleDraftSelection(draftId) {
    if (selectedDraftIds.value.includes(draftId)) {
        selectedDraftIds.value = selectedDraftIds.value.filter(id => id !== draftId);
        return;
    }
    if (selectedDraftIds.value.length >= MAX_TIKTOK_EXPORT_DRAFTS) {
        showToast(`一次最多选择 ${MAX_TIKTOK_EXPORT_DRAFTS} 条商品草稿`);
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
    const remaining = MAX_TIKTOK_EXPORT_DRAFTS - selectedDraftIds.value.length;
    const candidates = pageIds.filter(id => !selectedDraftIds.value.includes(id));
    const additions = candidates.slice(0, remaining);
    selectedDraftIds.value = [...selectedDraftIds.value, ...additions];
    if (additions.length < candidates.length) {
        showToast(`一次最多选择 ${MAX_TIKTOK_EXPORT_DRAFTS} 条商品草稿`);
    }
}
function changeDraftTemplateFilter() { currentDraftPage.value = 1; selectedDraftIds.value = []; }
async function changeDraftCreatorFilter() { currentDraftPage.value = 1; selectedDraftIds.value = []; await refreshDraftList(); }
async function refreshDraftList() {
    const { data } = await api.get('/drafts', { headers: headers.value, params: { creator_id: draftCreatorFilterId.value } });
    drafts.value = data;
    selectedDraftIds.value = selectedDraftIds.value.filter(id => data.some((draft) => draft.id === id));
}
const taskPageCount = computed(() => Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value)));
const visibleTaskPage = computed(() => Math.min(currentTaskPage.value, taskPageCount.value));
const pagedTasks = computed(() => tasks.value);
const claimablePagedTasks = computed(() => pagedTasks.value.filter(task => ['awaiting_selection', 'completed'].includes(task.status) && (task.result_count || task.result_urls?.length)));
const allClaimableTasksSelected = computed(() => Boolean(claimablePagedTasks.value.length) && claimablePagedTasks.value.every(task => selectedTaskIds.value.includes(task.id)));
const someClaimableTasksSelected = computed(() => !allClaimableTasksSelected.value && claimablePagedTasks.value.some(task => selectedTaskIds.value.includes(task.id)));
const groupedBatchClaimItems = computed(() => {
    const groups = new Map();
    batchClaimItems.value.forEach(item => {
        const group = groups.get(item.taskId) || { taskId: item.taskId, taskLabel: item.taskLabel, urls: [] };
        group.urls.push(item.url);
        groups.set(item.taskId, group);
    });
    return [...groups.values()];
});
function syncTaskUrl() { const url = new URL(location.href); url.searchParams.set('task_type', activeTaskType.value); url.searchParams.set('task_page', String(currentTaskPage.value)); url.searchParams.set('task_page_size', String(taskPageSize.value)); url.searchParams.set('task_creator', taskCreatorFilterId.value ? String(taskCreatorFilterId.value) : 'all'); url.searchParams.set('task_status', taskStatusFilter.value); taskCreatedFrom.value ? url.searchParams.set('task_from', taskCreatedFrom.value) : url.searchParams.delete('task_from'); taskCreatedTo.value ? url.searchParams.set('task_to', taskCreatedTo.value) : url.searchParams.delete('task_to'); history.replaceState({}, '', url); }
function clearTaskUrl() { const url = new URL(location.href); ['task_type', 'task_page', 'task_page_size', 'task_creator', 'task_status', 'task_from', 'task_to'].forEach(key => url.searchParams.delete(key)); history.replaceState({}, '', url); }
watch(page, value => value === 'tasks' ? syncTaskUrl() : clearTaskUrl());
function applyTaskPage(data) { tasks.value = data.items || []; taskTotal.value = data.total || 0; taskTypeTotals.value = { ...taskTypeTotals.value, ...(data.task_type_counts || {}) }; taskTypeFilteredTotals.value = { ...taskTypeFilteredTotals.value, [activeTaskType.value]: data.total || 0 }; taskActiveCount.value = data.active_count || 0; taskStatusCounts.value = data.status_counts || {}; currentTaskPage.value = data.page || 1; if (page.value === 'tasks')
    syncTaskUrl(); }
async function changeTaskPageSize() { currentTaskPage.value = 1; selectedTaskIds.value = []; syncTaskUrl(); await refreshTaskList(); }
async function changeTaskPage(targetPage) { currentTaskPage.value = Math.min(Math.max(1, targetPage), taskPageCount.value); selectedTaskIds.value = []; syncTaskUrl(); await refreshTaskList(); }
function taskQueryParams() { return { page: currentTaskPage.value, page_size: taskPageSize.value, task_type: activeTaskType.value, creator_id: appliedTaskFilters.value.creator_id ?? undefined, status: appliedTaskFilters.value.status || undefined, created_from: appliedTaskFilters.value.created_from || undefined, created_to: appliedTaskFilters.value.created_to || undefined }; }
function snapshotTaskTab() {
    taskTabStates.value[activeTaskType.value] = { page: currentTaskPage.value, pageSize: taskPageSize.value, creator: taskCreatorFilterId.value, status: taskStatusFilter.value, from: taskCreatedFrom.value, to: taskCreatedTo.value, applied: { ...appliedTaskFilters.value } };
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
    appliedTaskFilters.value = state?.applied || { creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: '', created_to: '' };
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
    appliedTaskFilters.value = { creator_id: taskCreatorFilterId.value, status: taskStatusFilter.value, created_from: toUtcIso(taskCreatedFrom.value), created_to: toUtcIso(taskCreatedTo.value) };
    currentTaskPage.value = 1;
    selectedTaskIds.value = [];
    syncTaskUrl();
    await refreshTaskList();
}
const materialPageCount = computed(() => Math.max(1, Math.ceil(materialTotal.value / materialPageSize.value)));
const visibleMaterialPage = computed(() => Math.min(currentMaterialPage.value, materialPageCount.value));
function applyMaterialPage(data) { materialAssets.value = data.items || []; materialTotal.value = data.total || 0; currentMaterialPage.value = data.page || 1; }
async function changeMaterialPageSize() { currentMaterialPage.value = 1; await refreshMaterialList(); }
async function changeMaterialPage(targetPage) { currentMaterialPage.value = Math.min(Math.max(1, targetPage), materialPageCount.value); await refreshMaterialList(); }
async function changeMaterialFilter() { currentMaterialPage.value = 1; await refreshMaterialList(); }
async function refreshMaterialList() {
    selectedMaterialAssetIds.value = [];
    const { data } = await api.get('/material-assets', { headers: headers.value, params: { page: currentMaterialPage.value, page_size: materialPageSize.value, creator_id: materialCreatorFilterId.value, template_id: materialTemplateFilterId.value } });
    applyMaterialPage(data);
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
    if (!creatorFiltersInitialized.value) {
        if (!initialTaskParams.has('task_creator'))
            taskCreatorFilterId.value = user.value.id;
        appliedTaskFilters.value.creator_id = taskCreatorFilterId.value;
        materialCreatorFilterId.value = user.value.id;
        draftCreatorFilterId.value = user.value.id;
        creatorFiltersInitialized.value = true;
    }
    const [s, t, g, task, material, d, providers, catalogs] = await Promise.all([api.get('/shops', h), api.get('/templates', h), api.get('/template-groups', h), api.get('/tasks', { ...h, params: taskQueryParams() }), api.get('/material-assets', { ...h, params: { page: currentMaterialPage.value, page_size: materialPageSize.value, creator_id: materialCreatorFilterId.value, template_id: materialTemplateFilterId.value } }), api.get('/drafts', { ...h, params: { creator_id: draftCreatorFilterId.value } }), api.get('/ai-providers', h), api.get('/tiktok-category-catalogs', h)]);
    shops.value = s.data;
    templates.value = t.data;
    templateGroups.value = g.data;
    applyTaskPage(task.data);
    applyMaterialPage(material.data);
    drafts.value = d.data;
    aiProviders.value = providers.data;
    tiktokCatalogs.value = catalogs.data;
    // 后台停用当前所选模型后，刷新时立即切换到仍启用的默认模型，避免提交已停用的值。
    if (!availableAiProviders.value.some(item => item.provider === creativeProvider.value)) {
        creativeProvider.value = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || '';
    }
    if (user.value.role === 'company_admin') {
        const [companyMembers, companyShops] = await Promise.all([api.get('/members', h), api.get('/shops/manage', h)]);
        members.value = companyMembers.data;
        managedShops.value = companyShops.data;
    }
    else {
        members.value = [];
        managedShops.value = [];
    }
    if (!selectedTemplateId.value && templates.value[0])
        selectedTemplateId.value = templates.value[0].id;
    if (selectedTemplateId.value)
        await loadMyTemplateResources(false);
}
async function login() { try {
    loading.value = true;
    error.value = '';
    const { data } = await api.post('/auth/login', { email: email.value, password: password.value });
    token.value = data.access_token;
    localStorage.setItem('haitoro_token', token.value);
    await refresh();
}
catch {
    error.value = '登录失败，请检查账号密码';
}
finally {
    loading.value = false;
} }
function onCreativeAssetChange(event) {
    if (creativeUploading.value) {
        showToast('图片上传处理中，请等待本轮上传结束');
        event.target.value = '';
        return;
    }
    const files = Array.from(event.target.files || []);
    const available = 500 - creativeAssets.value.length;
    const supported = files.filter(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size <= 5 * 1024 * 1024);
    supported.slice(0, available).forEach(file => creativeAssets.value.push({ id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`, file, preview: URL.createObjectURL(file) }));
    if (files.length <= available)
        creativeAssetError.value = '';
    if (supported.length !== files.length)
        creativeAssetError.value = '仅支持 JPG、PNG、WebP，且单张不能超过 5MB。';
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
        const { data } = await api.post('/tasks', { template_id: selectedTemplateId.value, white_image_id: selectedWhiteImageId.value, provider: creativeProvider.value, ratio: creativeRatio.value, quality: creativeQuality.value, print_url: print_urls[0], print_urls, creative_requirement: creativeRequirement.value.trim() }, { headers: headers.value });
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
function onWhiteImageFileChange(event) { whiteImageForm.value.file = event.target.files?.[0] || null; }
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
function onCoverChange(event) { const file = event.target.files?.[0] || null; newTemplateImage.value = file; newTemplateImagePreview.value = file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.cover_url); }
function onSizeChartChange(event) { const file = event.target.files?.[0] || null; newTemplateSizeChart.value = file; newTemplateSizeChartPreview.value = file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.size_chart_url); }
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
        { valid: Boolean(newTemplateTitleTemplate.value.trim() && newTemplateProductDescription.value.trim() && newTemplateSizeChart.value), tab: 'product', message: '请完整填写商品信息，并上传尺码图' },
        { valid: sizeOptions.length > 0 && newSkuSizeOptions.value.every(value => value.trim()), tab: 'sku', message: '请完整填写 SKU 尺码' },
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
    showToast('请完整填写 AI 提示词的名称和内容，或删除空白项');
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
    if (!materialDraftTemplateId.value || !selectedMaterialAssets.value[0])
        return;
    try {
        materialDraftTitleGenerating.value = true;
        const { data } = await api.post(`/templates/${materialDraftTemplateId.value}/generate-draft-title`, { image_url: selectedMaterialAssets.value[0].url }, { headers: headers.value });
        materialDraftTitle.value = data.title;
    }
    catch (e) {
        showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试');
    }
    finally {
        materialDraftTitleGenerating.value = false;
    }
}
function openMaterialDraftDialog() { if (!selectedMaterialTemplateId.value) {
    showToast('请选择属于同一产品模板的素材');
    return;
} materialDraftTemplateId.value = selectedMaterialTemplateId.value; materialDraftTitle.value = ''; materialDraftProductDescription.value = ''; materialDraftSizeChartPreview.value = ''; onMaterialDraftTemplateChange(); showMaterialDraftDialog.value = true; }
async function createDraftFromMaterialAssets() {
    if (!selectedMaterialAssetIds.value.length)
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
        await api.post('/drafts/from-material-assets', { material_asset_ids: selectedMaterialAssetIds.value, template_id: materialDraftTemplateId.value, title, product_description: materialDraftProductDescription.value.trim() || null }, { headers: headers.value });
        selectedMaterialAssetIds.value = [];
        showMaterialDraftDialog.value = false;
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
const imageDraftSkus = computed(() => {
    const seen = new Set();
    return (imageDraft.value?.sku_items || []).filter((item) => { if (!item.sku || !item.image_url || seen.has(item.sku))
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
const currentGeneratedMainImage = computed(() => (imageDraft.value?.carousel_items || []).find((item) => item.source_type === 'main_image') || null);
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
async function openDraftImageWorkspace(draft) {
    showDraftImageDialog.value = true;
    imageDraft.value = null;
    selectedImageSkus.value = [];
    selectedMainReferences.value = [];
    mainReferenceMode.value = 'random';
    resetFinalImageOrder();
    const defaultImageProvider = availableAiProviders.value.find(item => item.is_default)?.provider || availableAiProviders.value[0]?.provider || '';
    carouselParams.value = { prompt: '保持服装款式、颜色和印花准确，生成自然真实、适合电商展示的商品场景图', provider: defaultImageProvider, ratio: '1:1', quality: '1K' };
    mainParams.value = { prompt: '以参考图为基础生成突出商品主体的电商首图，背景简洁、光线自然，保持款式与颜色准确', provider: defaultImageProvider, ratio: '1:1', quality: '1K' };
    try {
        await loadImageWorkspace(draft.id);
    }
    catch (e) {
        showDraftImageDialog.value = false;
        showToast(e.response?.data?.detail || '加载图片制作台失败');
    }
}
function toggleImageSku(sku) {
    selectedImageSkus.value = selectedImageSkus.value.includes(sku) ? selectedImageSkus.value.filter(item => item !== sku) : [...selectedImageSkus.value, sku].slice(0, 9);
}
function toggleMainReference(url) { selectedMainReferences.value = selectedMainReferences.value.includes(url) ? selectedMainReferences.value.filter(item => item !== url) : [...selectedMainReferences.value, url]; }
async function createDraftImageTasks(type) {
    if (!imageDraft.value || imageDraft.value.locked)
        return;
    if (type === 'carousel' && !selectedImageSkus.value.length) {
        showToast('请至少选择一个 SKU');
        return;
    }
    if (type === 'main_image' && !(imageDraft.value.carousel_items?.length)) {
        showToast('请先保留至少一张 SKU 图或轮播图');
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
        const mainReferenceUrls = mainReferenceMode.value === 'manual' ? selectedMainReferences.value : (imageDraft.value.carousel_items || []).map((item) => item.image_url);
        const { data } = await api.post(`/drafts/${imageDraft.value.id}/image-tasks`, { task_type: type, source_skus: type === 'carousel' ? selectedImageSkus.value : [], reference_mode: mainReferenceMode.value, reference_urls: type === 'main_image' ? mainReferenceUrls : [], provider: params.provider, ratio: params.ratio, quality: params.quality, creative_requirement: params.prompt.trim() }, { headers: headers.value });
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
function stageCarouselTaskResult(task, url) {
    if (!imageDraft.value || imageDraft.value.locked)
        return;
    const sku = String(task.parameters?.source_sku || '');
    if (!sku) {
        showToast('该任务缺少来源 SKU');
        return;
    }
    const existing = (imageDraft.value.carousel_items || []).filter((item) => item.sku !== sku);
    if (existing.length >= 9) {
        showToast('商品最终图片最多 9 张，请先移除一张轮播图');
        return;
    }
    resetFinalImageOrder();
    imageDraft.value.carousel_items = [...existing, { sku, image_url: url, task_id: task.id }];
    imageDraft.value.using_sku_fallback = false;
    selectedMainReferences.value = selectedMainReferences.value.filter(referenceUrl => (imageDraft.value.carousel_items || []).some((item) => item.image_url === referenceUrl));
    showToast('已暂存为轮播图，确认后保存到草稿');
}
function stageMainTaskResult(task, url, removeSku) {
    if (!imageDraft.value || imageDraft.value.locked)
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
        await openDraftImageWorkspace({ id: Number(draftId) });
        if (!imageDraft.value)
            return;
    }
    if (task.task_type === 'main_image')
        stageMainTaskResult(task, url, removeSku);
    else
        stageCarouselTaskResult(task, url);
}
function removeCarouselImage(imageUrl) { if (!imageDraft.value || imageDraft.value.locked)
    return; resetFinalImageOrder(); const remaining = (imageDraft.value.carousel_items || []).filter((item) => item.image_url !== imageUrl); imageDraft.value.carousel_items = remaining.length ? remaining : skuFallbackCarouselItems(imageDraft.value); imageDraft.value.using_sku_fallback = !remaining.length; selectedMainReferences.value = selectedMainReferences.value.filter(url => (imageDraft.value.carousel_items || []).some((item) => item.image_url === url)); }
function removeMainImage() { if (!imageDraft.value || imageDraft.value.locked)
    return; resetFinalImageOrder(); const remaining = (imageDraft.value.carousel_items || []).filter((item) => item.source_type !== 'main_image'); imageDraft.value.carousel_items = remaining.length ? remaining : skuFallbackCarouselItems(imageDraft.value); imageDraft.value.using_sku_fallback = !remaining.length; }
function workspaceCarouselTasks() { return (imageDraft.value?.carousel_tasks || []).filter((task) => task && task.id); }
async function refreshWorkspaceTasks() { if (!imageDraft.value)
    return; try {
    await loadImageWorkspace(imageDraft.value.id, true);
}
catch (e) {
    showToast(e.response?.data?.detail || '刷新任务失败');
} }
function applyWorkspaceCarouselTask(task) {
    if (!imageDraft.value || imageDraft.value.locked)
        return;
    const url = task?.result_urls?.[0];
    if (!url) {
        showToast('该任务还没有可采用的生成结果');
        return;
    }
    stageCarouselTaskResult(task, url);
}
function workspaceMainTasks() { return (imageDraft.value?.main_image_tasks || []).filter((task) => task && task.id); }
function applyWorkspaceMainTask(task) {
    if (!imageDraft.value || imageDraft.value.locked)
        return;
    const url = task?.result_urls?.[0];
    if (!url) {
        showToast('该任务还没有可采用的生成结果');
        return;
    }
    stageMainTaskResult(task, url);
}
function dropCarousel(targetUrl) { if (!imageDraft.value || !draggedCarouselSku.value || draggedCarouselSku.value === targetUrl)
    return; const sourceUrl = draggedCarouselSku.value; resetFinalImageOrder(); const items = [...(imageDraft.value.carousel_items || [])]; const from = items.findIndex((item) => item.image_url === sourceUrl), to = items.findIndex((item) => item.image_url === targetUrl); if (from < 0 || to < 0)
    return; const [moved] = items.splice(from, 1); items.splice(to, 0, moved); imageDraft.value.carousel_items = items; imageDraft.value.using_sku_fallback = false; }
function dropFinalImage(targetUrl) { if (!draggedFinalImageUrl.value || draggedFinalImageUrl.value === targetUrl)
    return; const items = [...draftFinalImageItems.value]; const from = items.findIndex((item) => item.image_url === draggedFinalImageUrl.value), to = items.findIndex((item) => item.image_url === targetUrl); if (from < 0 || to < 0)
    return; const [moved] = items.splice(from, 1); items.splice(to, 0, moved); stagedFinalImageItems.value = items; draggedFinalImageUrl.value = ''; }
async function duplicateDraftForImages(draft) { try {
    const { data } = await api.post(`/drafts/${draft.id}/duplicate`, {}, { headers: headers.value });
    await refreshDraftList();
    await openDraftImageWorkspace(data);
    showToast('已复制为新版草稿');
}
catch (e) {
    showToast(e.response?.data?.detail || '复制草稿失败');
} }
async function openImageWorkspaceFromTask(task) { const draftId = task?.parameters?.draft_id; if (!draftId)
    return; showTaskDetailDialog.value = false; page.value = 'drafts'; await openDraftImageWorkspace({ id: draftId }); if (task.task_type === 'carousel' && task.parameters?.source_sku)
    selectedImageSkus.value = [task.parameters.source_sku]; await nextTick(); document.getElementById(task.task_type === 'main_image' ? 'main-image-workspace-section' : 'carousel-workspace-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
async function confirmDraftImages() { if (!imageDraft.value || imageDraft.value.locked)
    return; if (!draftFinalImageItems.value.length) {
    showToast('请至少保留一张 SKU 图或轮播图后再保存');
    return;
} try {
    imageConfirmSaving.value = true;
    const payload = { image_items: draftFinalImageItems.value.map((item) => ({ result_url: item.image_url, sku: item.sku || null, task_id: item.task_id || null })) };
    imageDraft.value = (await api.post(`/drafts/${imageDraft.value.id}/images/confirm`, payload, { headers: headers.value })).data;
    await refreshDraftList();
    showDraftImageDialog.value = false;
    showToast('商品图片已保存到草稿');
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
async function publishDraftToMiaoshou(draft) {
    if (draft.tiktok_collect_box_id)
        return;
    try {
        publishingDraftId.value = draft.id;
        const { data } = await api.post(`/drafts/${draft.id}/claim-to-tiktok`, {}, { headers: headers.value });
        await refresh();
        showToast(data.already_claimed ? '该商品已认领到 TikTok 采集箱' : `已发布公共草稿箱并认领到 TikTok（编号：${data.tiktok_collect_box_detail_id}）`);
    }
    catch (e) {
        const detail = e.response?.data?.detail || '发布至妙手或认领 TikTok 失败';
        showToast(`${detail}；草稿已保留，可稍后重试`);
    }
    finally {
        publishingDraftId.value = null;
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
    showTiktokExportDialog.value = true;
    tiktokExportLoading.value = true;
    tiktokExportError.value = '';
    tiktokExportCatalogId.value = tiktokCatalogs.value[0]?.id || null;
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
        tiktokExportOptions.value = (await api.get('/tiktok-export/options', { headers: headers.value, params: { category_catalog_id: tiktokExportCatalogId.value } })).data;
    }
    catch (e) {
        tiktokExportError.value = e.response?.data?.detail || e.message || '加载 TikTok 模板选项失败';
    }
    finally {
        tiktokExportLoading.value = false;
    }
}
function changeTiktokExportCategory() { tiktokExportAttributes.value = {}; }
async function changeTiktokExportCatalog() {
    tiktokExportCategory.value = '';
    tiktokExportAttributes.value = {};
    tiktokExportOptions.value = null;
    if (!tiktokExportCatalogId.value)
        return;
    try {
        tiktokExportLoading.value = true;
        tiktokExportError.value = '';
        tiktokExportOptions.value = (await api.get('/tiktok-export/options', { headers: headers.value, params: { category_catalog_id: tiktokExportCatalogId.value } })).data;
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
        return '输入模板支持的属性值；多个值用英文逗号分隔';
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
        showToast('TikTok 批量上传表格已生成');
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
        tiktokCatalogError.value = '请填写类目库名称并选择 TikTok XLSX 模板';
        return;
    }
    const form = new FormData();
    form.append('name', name);
    form.append('file', tiktokCatalogFile.value);
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        await api.post('/tiktok-category-catalogs', form, { headers: headers.value });
        showTiktokCatalogDialog.value = false;
        tiktokCatalogs.value = (await api.get('/tiktok-category-catalogs', { headers: headers.value })).data;
        showToast('TK 类目库已导入');
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '导入 TK 类目库失败';
    }
    finally {
        tiktokCatalogLoading.value = false;
    }
}
async function openTiktokCatalogDetail(catalog) {
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        const { data } = await api.get('/tiktok-export/options', { headers: headers.value, params: { category_catalog_id: catalog.id } });
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
        const { data } = await api.patch(`/tiktok-category-catalogs/${managingTiktokCatalog.value.id}`, {
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
    if (!confirm(`确定删除 TK 类目库“${catalog.name}”吗？`))
        return;
    try {
        tiktokCatalogLoading.value = true;
        tiktokCatalogError.value = '';
        await api.delete(`/tiktok-category-catalogs/${catalog.id}`, { headers: headers.value });
        tiktokCatalogs.value = tiktokCatalogs.value.filter(item => item.id !== catalog.id);
        showToast('TK 类目库已删除');
    }
    catch (e) {
        tiktokCatalogError.value = e.response?.data?.detail || '删除 TK 类目库失败';
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
function toggleAllClaimableTasks() { selectedTaskIds.value = allClaimableTasksSelected.value ? [] : claimablePagedTasks.value.map(task => task.id); }
function removeBatchClaimImage(taskId, url) { if (!batchClaiming.value)
    batchClaimItems.value = batchClaimItems.value.filter(item => item.taskId !== taskId || item.url !== url); }
async function openBatchClaimDialog() {
    if (!selectedTaskIds.value.length) {
        showToast('请至少选择一个可领取任务');
        return;
    }
    showBatchClaimDialog.value = true;
    batchClaimLoading.value = true;
    batchClaimItems.value = [];
    batchClaimCompleted.value = 0;
    batchClaimFailed.value = 0;
    try {
        const details = await Promise.all(selectedTaskIds.value.map(id => api.get(`/tasks/${id}`, { headers: headers.value }).then(response => response.data)));
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
    selectedTaskIds.value = [];
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
        showToast('仅支持 JPG、PNG、WebP，且单张不能超过 5MB');
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
function openMemberDialog(member) { editingMember.value = member || null; memberForm.value = { name: member?.name || '', user_code: member?.user_code || '', email: member?.email || '', password: '', is_active: member?.is_active ?? true }; memberFormError.value = ''; showMemberDialog.value = true; }
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
    try {
        memberSaving.value = true;
        error.value = '';
        const payload = { name, user_code: userCode, email };
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
function memberCredentialPreview() { return credentialMember.value?.ai_provider_credential_previews?.[credentialProvider.value?.provider] || ''; }
async function saveMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !credentialApiKey.value.trim()) {
    showToast('请输入平台密钥');
    return;
} try {
    credentialSaving.value = true;
    await api.put(`/members/${credentialMember.value.id}/ai-provider-credentials/${credentialProvider.value.provider}`, { api_key: credentialApiKey.value.trim() }, { headers: headers.value });
    showMemberCredentialDialog.value = false;
    await refresh();
    showToast(`${credentialProvider.value.display_name} 平台密钥已安全保存`);
}
catch (e) {
    showToast(e.response?.data?.detail || '保存平台密钥失败');
}
finally {
    credentialSaving.value = false;
} }
async function clearMemberCredential() { if (!credentialMember.value || !credentialProvider.value || !confirm(`确定清除 ${credentialMember.value.name} 的 ${credentialProvider.value.display_name} 平台密钥吗？`))
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
let toastTimer;
function showToast(message) { toast.value = message; if (toastTimer)
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = ''; }, 3000); }
function logout() { localStorage.removeItem('haitoro_token'); token.value = ''; user.value = null; taskCreatorFilterId.value = null; materialCreatorFilterId.value = null; draftCreatorFilterId.value = null; creatorFiltersInitialized.value = false; }
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
    taskResultPollingTimer = setInterval(refreshPendingTaskResults, 5000);
});
onUnmounted(() => taskResultPollingTimer && clearInterval(taskResultPollingTimer));
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
        ...{ class: "required" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "120",
        placeholder: "例如：穆斯林服装",
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
    (__VLS_ctx.user?.role === 'company_admin' ? '管理员' : '运营成员');
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
                key: (group.id),
                ...{ class: ({ selected: __VLS_ctx.activeGroupId === group.id }) },
            });
            (group.name);
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "template-image" },
                ...{ class: ({ hasCover: __VLS_ctx.hasTemplateCover(t) }) },
            });
            if (__VLS_ctx.hasTemplateCover(t)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.templateCoverUrl(t)),
                    alt: (t.name),
                });
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (t.name.includes('T恤') ? '♧' : '♔');
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            (t.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (t.is_platform ? 'blue' : 'purple') },
            });
            (t.is_platform ? '平台模板' : '公司私有');
            if (t.description) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "template-description" },
                });
                (t.description);
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (t.color_count);
            (t.sku_count);
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
        if (__VLS_ctx.activeTaskType === 'sku_image' && __VLS_ctx.selectedTaskIds.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "task-batch-bar" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedTaskIds.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openBatchClaimDialog) },
                ...{ class: "primary" },
                disabled: (__VLS_ctx.batchClaimLoading || __VLS_ctx.batchClaiming),
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-table task-table" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead task-list-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-checkbox material-select-all" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.toggleAllClaimableTasks) },
            type: "checkbox",
            checked: (__VLS_ctx.allClaimableTasksSelected),
            indeterminate: (__VLS_ctx.someClaimableTasksSelected),
            disabled: (!__VLS_ctx.claimablePagedTasks.length),
            'aria-label': "全选本页可领取任务",
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
            if (__VLS_ctx.activeTaskType === 'sku_image') {
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
                            if (!(__VLS_ctx.activeTaskType === 'sku_image'))
                                return;
                            __VLS_ctx.toggleTaskSelection(task.id);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedTaskIds.includes(task.id)),
                    disabled: (!['awaiting_selection', 'completed'].includes(task.status) || !(task.result_count || task.result_urls?.length)),
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
                    disabled: (__VLS_ctx.retryingTaskId === task.id),
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
        if (!__VLS_ctx.tasks.length) {
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
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (20),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (50),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (100),
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
                        if (!(__VLS_ctx.taskTotal))
                            return;
                        __VLS_ctx.changeTaskPage(__VLS_ctx.visibleTaskPage - 1);
                    } },
                disabled: (__VLS_ctx.visibleTaskPage === 1),
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
                disabled: (__VLS_ctx.visibleTaskPage === __VLS_ctx.taskPageCount),
            });
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
            ...{ class: "draft-table material-list" },
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
        if (!__VLS_ctx.filteredMaterialAssets.length) {
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
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (20),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (50),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (100),
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
                        if (!(__VLS_ctx.materialTotal))
                            return;
                        __VLS_ctx.changeMaterialPage(__VLS_ctx.visibleMaterialPage - 1);
                    } },
                disabled: (__VLS_ctx.visibleMaterialPage === 1),
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
                disabled: (__VLS_ctx.visibleMaterialPage === __VLS_ctx.materialPageCount),
            });
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
        if (__VLS_ctx.selectedDraftIds.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "draft-export-bar" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedDraftIds.length);
            (__VLS_ctx.MAX_TIKTOK_EXPORT_DRAFTS);
            if (__VLS_ctx.selectedDraftIds.length === 1) {
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
                            if (!(__VLS_ctx.selectedDraftIds.length === 1))
                                return;
                            __VLS_ctx.openDraftImageWorkspace(__VLS_ctx.selectedDrafts[0]);
                        } },
                    ...{ class: "secondary" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.openTiktokExportDialog) },
                ...{ class: "primary" },
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
                        if (!(__VLS_ctx.selectedDraftIds.length))
                            return;
                        __VLS_ctx.selectedDraftIds = [];
                    } },
                ...{ class: "ghost" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-table task-table" },
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
                disabled: (__VLS_ctx.selectedDraftIds.length >= __VLS_ctx.MAX_TIKTOK_EXPORT_DRAFTS && !__VLS_ctx.selectedDraftIds.includes(draft.id)),
            });
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
            });
            (draft.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.sku_items?.length || 1);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.source_task_id ? `#${draft.source_task_id}` : '素材库');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(draft.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.created_by_name || '历史记录缺失');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(draft.updated_at || draft.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.updated_by_name || '历史记录缺失');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.export_count || 0);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (draft.tiktok_collect_box_id ? 'blue' : 'orange') },
            });
            (draft.tiktok_collect_box_id ? '已认领到 TikTok' : draft.miaoshou_collect_box_id ? '待认领到 TikTok' : '待发布');
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
                        if (!(__VLS_ctx.page === 'drafts'))
                            return;
                        __VLS_ctx.openDraftEditDialog(draft);
                    } },
            });
            if (!draft.tiktok_collect_box_id) {
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
                            if (!(!draft.tiktok_collect_box_id))
                                return;
                            __VLS_ctx.publishDraftToMiaoshou(draft);
                        } },
                    ...{ class: "primary compact-action" },
                    disabled: (__VLS_ctx.publishingDraftId === draft.id),
                });
                (__VLS_ctx.publishingDraftId === draft.id ? '处理中…' : '发布至妙手');
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (draft.tiktok_collect_box_id);
            }
        }
        if (!__VLS_ctx.filteredDrafts.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "empty" },
            });
            (__VLS_ctx.drafts.length ? '没有符合筛选条件的商品草稿。' : '暂无商品草稿，请先在任务中心领取素材，或上传本地素材。');
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.filteredDrafts.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeDraftPageSize) },
                value: (__VLS_ctx.draftPageSize),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (20),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (50),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (100),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (500),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (1000),
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
                        if (!!(!__VLS_ctx.filteredDrafts.length))
                            return;
                        __VLS_ctx.currentDraftPage = __VLS_ctx.visibleDraftPage - 1;
                    } },
                disabled: (__VLS_ctx.visibleDraftPage === 1),
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
                        if (!!(!__VLS_ctx.filteredDrafts.length))
                            return;
                        __VLS_ctx.currentDraftPage = __VLS_ctx.visibleDraftPage + 1;
                    } },
                disabled: (__VLS_ctx.visibleDraftPage === __VLS_ctx.draftPageCount),
            });
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
                    if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                        return;
                    __VLS_ctx.openMemberDialog();
                } },
            ...{ class: "primary" },
        });
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
        for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (member.id),
                ...{ class: "trow" },
                ...{ style: {} },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (member.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (member.user_code || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (member.role === 'company_admin' ? '公司管理员' : '普通成员');
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
            if (member.role === 'member') {
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
                            if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(member.role === 'member'))
                                return;
                            __VLS_ctx.openMemberDialog(member);
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
                            if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            if (!(member.role === 'member'))
                                return;
                            __VLS_ctx.toggleMember(member);
                        } },
                    ...{ class: (member.is_active ? 'negative' : 'positive') },
                });
                (member.is_active ? '停用' : '启用');
            }
            for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.aiProviders))) {
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
                            if (!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                                return;
                            __VLS_ctx.openMemberCredentialDialog(member, provider);
                        } },
                    key: (provider.provider),
                    ...{ class: "credential-button" },
                    ...{ class: (member.ai_provider_credentials?.[provider.provider] ? 'configured' : 'missing') },
                });
                (provider.display_name);
                (member.ai_provider_credentials?.[provider.provider] ? '已配置' : '待配置');
            }
        }
        if (!__VLS_ctx.members.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    else if (__VLS_ctx.page === 'shops' && __VLS_ctx.user?.role === 'company_admin') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "miaoshou-status" },
            ...{ class: (__VLS_ctx.company?.miaoshou_configured ? 'configured' : 'missing') },
        });
        (__VLS_ctx.company?.miaoshou_configured ? '妙手 API Key 已配置' : '请先配置妙手 API Key');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "shop-actions" },
        });
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
        if (__VLS_ctx.shopError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "error" },
            });
            (__VLS_ctx.shopError);
        }
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
        for (const [shop] of __VLS_getVForSourceType((__VLS_ctx.managedShops))) {
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
                        if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!(__VLS_ctx.page === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.openShopManagersDialog(shop);
                    } },
            });
        }
        if (!__VLS_ctx.managedShops.length && !__VLS_ctx.shopLoading) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
            (__VLS_ctx.company?.miaoshou_configured ? '暂无已同步店铺，点击“同步妙手店铺”开始获取。' : '配置妙手 API Key 后即可同步店铺。');
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.openTiktokCatalogCreateDialog) },
            ...{ class: "primary" },
        });
        if (__VLS_ctx.tiktokCatalogError) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "error" },
            });
            (__VLS_ctx.tiktokCatalogError);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-table" },
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
        for (const [catalog] of __VLS_getVForSourceType((__VLS_ctx.tiktokCatalogs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (catalog.id),
                ...{ class: "trow tiktok-catalog-grid" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (catalog.name);
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
                        if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!!(__VLS_ctx.page === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.openTiktokCatalogDetail(catalog);
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
                        if (!!(__VLS_ctx.page === 'members' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!!(__VLS_ctx.page === 'shops' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        if (!(__VLS_ctx.page === 'tiktok-catalogs' && __VLS_ctx.user?.role === 'company_admin'))
                            return;
                        __VLS_ctx.deleteTiktokCatalog(catalog);
                    } },
                ...{ class: "negative" },
                disabled: (__VLS_ctx.tiktokCatalogLoading),
            });
        }
        if (!__VLS_ctx.tiktokCatalogs.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
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
        (__VLS_ctx.editingWhiteImage ? '不重新选择则保留当前图片' : 'JPG、PNG、WebP，最大 5MB');
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
    (__VLS_ctx.selectedMaterialAssetIds.length);
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
    (__VLS_ctx.selectedMaterialAssets.length);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-preview-images" },
    });
    for (const [asset] of __VLS_getVForSourceType((__VLS_ctx.selectedMaterialAssets))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            key: (asset.id),
            src: (__VLS_ctx.imageUrl(asset.url)),
            alt: (asset.name),
        });
    }
    if (__VLS_ctx.materialDraftTemplate) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "material-draft-details" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-title-row" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            minlength: "25",
            maxlength: "255",
            placeholder: "请输入 25-255 个字符，或使用 AI 生成",
        });
        (__VLS_ctx.materialDraftTitle);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.generateMaterialDraftTitle) },
            ...{ class: "secondary" },
            disabled: (__VLS_ctx.materialDraftTitleGenerating),
        });
        (__VLS_ctx.materialDraftTitleGenerating ? '生成中…' : 'AI 生成标题');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.materialDraftProductDescription),
            maxlength: "5000",
            placeholder: "默认使用产品模版描述，可按商品修改",
        });
    }
    if (__VLS_ctx.materialDraftTemplate) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "material-draft-sku-summary" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (__VLS_ctx.materialDraftSizes.length ? __VLS_ctx.materialDraftSizes.join('、') : '默认规格');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.materialDraftSkuCount);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-draft-sku-list" },
        });
        for (const [asset] of __VLS_getVForSourceType((__VLS_ctx.selectedMaterialAssets))) {
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
        for (const [catalog] of __VLS_getVForSourceType((__VLS_ctx.tiktokCatalogs))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (catalog.id),
                value: (catalog.id),
            });
            (catalog.name);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({
            ...{ class: "required" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (__VLS_ctx.changeTiktokExportCategory) },
            value: (__VLS_ctx.tiktokExportCategory),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: "",
            disabled: true,
        });
        for (const [category] of __VLS_getVForSourceType((__VLS_ctx.tiktokExportOptions?.categories || []))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (category.name),
                value: (category.name),
            });
            (category.name);
        }
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
        disabled: (__VLS_ctx.tiktokExportLoading),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.exportSelectedDrafts) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.tiktokExportLoading || !__VLS_ctx.tiktokExportOptions),
    });
    (__VLS_ctx.tiktokExportLoading ? '生成中…' : '生成并下载');
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
    (__VLS_ctx.viewingTask?.parameters?.source_sku ? `来源 SKU：${__VLS_ctx.viewingTask.parameters.source_sku}` : `参考 ${__VLS_ctx.viewingTask?.parameters?.reference_urls?.length || 0} 张轮播图`);
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.imageDraft?.title);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "chip" },
        ...{ class: (__VLS_ctx.imageDraft?.locked ? 'orange' : 'purple') },
    });
    (__VLS_ctx.imageDraft?.locked ? '图片已锁定' : `${__VLS_ctx.draftImagePreviewUrls.length} / 9 张`);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
        ...{ class: "workspace-steps" },
        'aria-label': "制作流程",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "workspace-step" },
        ...{ class: ({ active: true, done: __VLS_ctx.selectedImageSkus.length || __VLS_ctx.imageDraft?.carousel_items?.length }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "workspace-step-divider" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "workspace-step" },
        ...{ class: ({ active: __VLS_ctx.imageDraft?.carousel_items?.length, done: __VLS_ctx.imageDraft?.carousel_items?.length }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "workspace-step-divider" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "workspace-step" },
        ...{ class: ({ active: __VLS_ctx.currentGeneratedMainImage }) },
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
    if (__VLS_ctx.imageWorkspaceLoading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "empty" },
        });
    }
    else if (__VLS_ctx.imageDraft) {
        if (__VLS_ctx.imageDraft.locked) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "image-lock-notice" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        if (!(__VLS_ctx.imageDraft.locked))
                            return;
                        __VLS_ctx.duplicateDraftForImages(__VLS_ctx.imageDraft);
                    } },
                ...{ class: "primary" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "image-workspace-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
            ...{ class: "image-workspace-main" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "workspace-card workspace-sku-card-section" },
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
                disabled: (__VLS_ctx.imageDraft.locked || (!__VLS_ctx.selectedImageSkus.includes(item.sku) && __VLS_ctx.selectedImageSkus.length >= 9)),
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                ...{ class: "workspace-sku-status" },
                ...{ class: (__VLS_ctx.imageDraft.carousel_items?.some((carousel) => carousel.sku === item.sku) ? 'done' : 'pending') },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.i, __VLS_intrinsicElements.i)({});
            (__VLS_ctx.imageDraft.carousel_items?.some((carousel) => carousel.sku === item.sku) ? '当前轮播图' : '可生成');
        }
        if (!__VLS_ctx.imageDraftSkus.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "workspace-sku-empty" },
            });
        }
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
            ...{ class: "carousel-strip" },
        });
        for (const [item, index] of __VLS_getVForSourceType((__VLS_ctx.imageDraft.carousel_items || []))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ onDragstart: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        __VLS_ctx.draggedCarouselSku = item.image_url;
                    } },
                ...{ onDragover: () => { } },
                ...{ onDrop: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        __VLS_ctx.dropCarousel(item.image_url);
                    } },
                key: (item.image_url),
                draggable: "true",
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
                            return;
                        __VLS_ctx.removeCarouselImage(item.image_url);
                    } },
                disabled: (__VLS_ctx.imageDraft.locked),
            });
        }
        if (!__VLS_ctx.imageDraft.carousel_items?.length) {
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
                            __VLS_ctx.applyWorkspaceCarouselTask(task);
                        } },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.imageDraft.locked || !task.result_urls?.length || __VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0])),
                });
                (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls?.[0]) ? '已采用' : '采用');
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
                            __VLS_ctx.openTaskDetail(task);
                        } },
                    ...{ class: "secondary" },
                });
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-params" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-params-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-card-footer" },
        });
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
            ...{ class: "primary" },
            disabled: (__VLS_ctx.imageDraft.locked || !!__VLS_ctx.imageTaskCreatingType || !__VLS_ctx.selectedImageSkus.length),
        });
        (__VLS_ctx.imageTaskCreatingType === 'carousel' ? '创建中…' : '开始创作轮播图');
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
        if (__VLS_ctx.currentGeneratedMainImage) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.removeMainImage) },
                ...{ class: "ghost workspace-card-action" },
                disabled: (__VLS_ctx.imageDraft.locked),
            });
        }
        if (__VLS_ctx.currentGeneratedMainImage) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "main-image-preview" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(__VLS_ctx.currentGeneratedMainImage.image_url)),
                alt: "AI 生成图片",
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
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
                    __VLS_ctx.mainReferenceMode = 'random';
                } },
            type: "button",
            role: "tab",
            ...{ class: ({ active: __VLS_ctx.mainReferenceMode === 'random' }) },
            'aria-selected': (__VLS_ctx.mainReferenceMode === 'random'),
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
                ...{ class: "reference-picker" },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.imageDraft.carousel_items || []))) {
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
                            if (!(__VLS_ctx.mainReferenceMode === 'manual'))
                                return;
                            __VLS_ctx.toggleMainReference(item.image_url);
                        } },
                    type: "checkbox",
                    checked: (__VLS_ctx.selectedMainReferences.includes(item.image_url)),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(item.image_url)),
                    alt: (item.sku || 'AI 首图'),
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (item.sku || 'AI 首图');
            }
            if (!(__VLS_ctx.imageDraft.carousel_items?.length)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
        }
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
                ...{ class: "workspace-task-row workspace-task-row-head" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [task] of __VLS_getVForSourceType((__VLS_ctx.workspaceMainTasks()))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (task.id),
                    ...{ class: "workspace-task-row" },
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
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.workspaceMainTasks().length))
                                return;
                            __VLS_ctx.applyWorkspaceMainTask(task);
                        } },
                    ...{ class: "primary" },
                    disabled: (__VLS_ctx.imageDraft.locked || !task.result_urls?.length || __VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls[0])),
                });
                (__VLS_ctx.isWorkspaceTaskSelected(task, task.result_urls?.[0]) ? '已采用' : '采用');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.showDraftImageDialog))
                                return;
                            if (!!(__VLS_ctx.imageWorkspaceLoading))
                                return;
                            if (!(__VLS_ctx.imageDraft))
                                return;
                            if (!(__VLS_ctx.workspaceMainTasks().length))
                                return;
                            __VLS_ctx.openTaskDetail(task);
                        } },
                    ...{ class: "secondary" },
                });
            }
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-params" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-params-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "workspace-card-footer" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.showDraftImageDialog))
                        return;
                    if (!!(__VLS_ctx.imageWorkspaceLoading))
                        return;
                    if (!(__VLS_ctx.imageDraft))
                        return;
                    __VLS_ctx.createDraftImageTasks('main_image');
                } },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.imageDraft.locked || !!__VLS_ctx.imageTaskCreatingType || !__VLS_ctx.imageDraft.carousel_items?.length),
        });
        (__VLS_ctx.imageTaskCreatingType === 'main_image' ? '创建中…' : '开始创作首图');
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
                        __VLS_ctx.draggedFinalImageUrl = item.image_url;
                    } },
                ...{ onDragend: (...[$event]) => {
                        if (!(__VLS_ctx.showDraftImageDialog))
                            return;
                        if (!!(__VLS_ctx.imageWorkspaceLoading))
                            return;
                        if (!(__VLS_ctx.imageDraft))
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "modal-actions image-workspace-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.confirmDraftImages) },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.imageDraft.locked || __VLS_ctx.imageConfirmSaving || !!__VLS_ctx.imageTaskCreatingType),
        });
        (__VLS_ctx.imageConfirmSaving ? '保存中…' : '确认并保存到草稿');
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
    (__VLS_ctx.editingMember ? '姓名、用户代码、邮箱为必填项；留空密码即可保持原密码不变。' : '姓名、用户代码、邮箱为必填项；新成员将作为普通成员加入当前公司。');
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
    (__VLS_ctx.credentialProvider?.display_name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.credentialMember?.name);
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
    if (__VLS_ctx.credentialMember?.ai_provider_credentials?.[__VLS_ctx.credentialProvider?.provider]) {
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
    for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members.filter(item => item.role === 'member')))) {
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
    if (!__VLS_ctx.members.some(item => item.role === 'member')) {
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
                __VLS_ctx.templateFormTab = 'sku';
            } },
        ...{ class: ({ active: __VLS_ctx.templateFormTab === 'sku' }) },
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
        (__VLS_ctx.newTemplateImage ? __VLS_ctx.newTemplateImage.name : __VLS_ctx.editingTemplate?.cover_url ? '保留当前图片' : '支持 JPG、PNG、WebP，最大 5MB');
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            maxlength: "500",
            placeholder: "例如：突出材质、款式与适用场景，不包含夸大宣传",
        });
        (__VLS_ctx.newTemplateTitleTemplate);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: (__VLS_ctx.newTemplateProductDescription),
            maxlength: "5000",
            placeholder: "填写商品详情页的产品描述",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.onSizeChartChange) },
            accept: "image/png,image/jpeg,image/webp",
            type: "file",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.newTemplateSizeChart ? __VLS_ctx.newTemplateSizeChart.name : __VLS_ctx.editingTemplate?.size_chart_url ? '保留当前尺码图' : '支持 JPG、PNG、WebP，最多上传 1 张，最大 5MB');
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
    else if (__VLS_ctx.templateFormTab === 'sku') {
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
                        if (!!(__VLS_ctx.templateFormTab === 'product'))
                            return;
                        if (!(__VLS_ctx.templateFormTab === 'sku'))
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
    }
    else if (__VLS_ctx.templateFormTab === 'ai-prompts') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "drawer-form ai-prompts-form" },
        });
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
                        if (!!(__VLS_ctx.templateFormTab === 'sku'))
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
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['template-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['template-card']} */ ;
/** @type {__VLS_StyleScopedClasses['template-image']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
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
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['task-search-button']} */ ;
/** @type {__VLS_StyleScopedClasses['task-batch-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['task-table']} */ ;
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
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['material-filter-row']} */ ;
/** @type {__VLS_StyleScopedClasses['material-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['material-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['material-upload-button']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-upload-error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['material-list']} */ ;
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
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['material-filter-row']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-template-filter']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-export-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['task-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-thead']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-trow']} */ ;
/** @type {__VLS_StyleScopedClasses['material-checkbox']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-product-title']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact-action']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['member-row-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['credential-button']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['miaoshou-status']} */ ;
/** @type {__VLS_StyleScopedClasses['shop-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['tiktok-catalog-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
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
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-details']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-title-row']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sku-summary']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-sku-list']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-size-chart']} */ ;
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
/** @type {__VLS_StyleScopedClasses['workspace-steps']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-divider']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-divider']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-divider']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['image-lock-notice']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-main']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card-section']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-action-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-scroll']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-check']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-image']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-info']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-status']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-sku-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-action-hint']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip-index']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty-icon']} */ ;
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
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params-head']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-prompt-field']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-footer']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-action']} */ ;
/** @type {__VLS_StyleScopedClasses['main-image-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-mode-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['reference-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-panel-head']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-refresh']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-list']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row-head']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-dash']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-status']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-thumb']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-dash']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-message']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-params-head']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-prompt-field']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-settings-row']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-footer']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card']} */ ;
/** @type {__VLS_StyleScopedClasses['final-image-preview-card']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-card-header']} */ ;
/** @type {__VLS_StyleScopedClasses['workspace-step-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['preview-count']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-strip-index']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['carousel-empty-icon']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['image-workspace-actions']} */ ;
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
/** @type {__VLS_StyleScopedClasses['required']} */ ;
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
/** @type {__VLS_StyleScopedClasses['template-upload-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-form']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-size-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-size-row']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-add-option']} */ ;
/** @type {__VLS_StyleScopedClasses['sku-total']} */ ;
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
/** @type {__VLS_StyleScopedClasses['toast']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-template-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
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
            aiProviders: aiProviders,
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
            showMemberCredentialDialog: showMemberCredentialDialog,
            credentialMember: credentialMember,
            credentialProvider: credentialProvider,
            credentialApiKey: credentialApiKey,
            credentialSaving: credentialSaving,
            showMyAccountDialog: showMyAccountDialog,
            myName: myName,
            myUserCode: myUserCode,
            myAccountSaving: myAccountSaving,
            managedShops: managedShops,
            shopLoading: shopLoading,
            shopError: shopError,
            showMiaoshouDialog: showMiaoshouDialog,
            miaoshouForm: miaoshouForm,
            miaoshouSaving: miaoshouSaving,
            tiktokCatalogs: tiktokCatalogs,
            tiktokCatalogLoading: tiktokCatalogLoading,
            tiktokCatalogError: tiktokCatalogError,
            showTiktokCatalogDialog: showTiktokCatalogDialog,
            tiktokCatalogName: tiktokCatalogName,
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
            selectedDraftIds: selectedDraftIds,
            showTiktokExportDialog: showTiktokExportDialog,
            tiktokExportOptions: tiktokExportOptions,
            tiktokExportLoading: tiktokExportLoading,
            tiktokExportError: tiktokExportError,
            MAX_TIKTOK_EXPORT_DRAFTS: MAX_TIKTOK_EXPORT_DRAFTS,
            tiktokExportCatalogId: tiktokExportCatalogId,
            tiktokExportCategory: tiktokExportCategory,
            tiktokExportDefaultPrice: tiktokExportDefaultPrice,
            tiktokExportDefaultQuantity: tiktokExportDefaultQuantity,
            tiktokExportCod: tiktokExportCod,
            tiktokExportAttributes: tiktokExportAttributes,
            tiktokExportOverrides: tiktokExportOverrides,
            draftPageSize: draftPageSize,
            currentDraftPage: currentDraftPage,
            draftTemplateFilterId: draftTemplateFilterId,
            draftCreatorFilterId: draftCreatorFilterId,
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
            previewImageUrl: previewImageUrl,
            previewImageAlt: previewImageAlt,
            showDraftImageDialog: showDraftImageDialog,
            imageDraft: imageDraft,
            imageWorkspaceLoading: imageWorkspaceLoading,
            imageTasksRefreshing: imageTasksRefreshing,
            imageTaskCreatingType: imageTaskCreatingType,
            imageConfirmSaving: imageConfirmSaving,
            selectedImageSkus: selectedImageSkus,
            selectedMainReferences: selectedMainReferences,
            mainReferenceMode: mainReferenceMode,
            carouselParams: carouselParams,
            mainParams: mainParams,
            draggedCarouselSku: draggedCarouselSku,
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
            availableAiProviders: availableAiProviders,
            creativeCredentialError: creativeCredentialError,
            selectedWhiteImage: selectedWhiteImage,
            otherResourceOwners: otherResourceOwners,
            filteredTeamWhiteImages: filteredTeamWhiteImages,
            filteredTeamPrompts: filteredTeamPrompts,
            selectedMaterialAssets: selectedMaterialAssets,
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
            selectedTiktokCategoryAttributes: selectedTiktokCategoryAttributes,
            managingTiktokCategoryAttributes: managingTiktokCategoryAttributes,
            changeDraftPageSize: changeDraftPageSize,
            toggleDraftSelection: toggleDraftSelection,
            togglePagedDrafts: togglePagedDrafts,
            changeDraftTemplateFilter: changeDraftTemplateFilter,
            changeDraftCreatorFilter: changeDraftCreatorFilter,
            taskPageCount: taskPageCount,
            visibleTaskPage: visibleTaskPage,
            pagedTasks: pagedTasks,
            claimablePagedTasks: claimablePagedTasks,
            allClaimableTasksSelected: allClaimableTasksSelected,
            someClaimableTasksSelected: someClaimableTasksSelected,
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
            login: login,
            onCreativeAssetChange: onCreativeAssetChange,
            removeCreativeAsset: removeCreativeAsset,
            clearCreativeAssets: clearCreativeAssets,
            createTask: createTask,
            createGroup: createGroup,
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
            createDraftFromMaterialAssets: createDraftFromMaterialAssets,
            openDraftEditDialog: openDraftEditDialog,
            draftSkuForImage: draftSkuForImage,
            draftEditSkus: draftEditSkus,
            openImagePreview: openImagePreview,
            imageDraftSkus: imageDraftSkus,
            draftFinalImageItems: draftFinalImageItems,
            draftImagePreviewUrls: draftImagePreviewUrls,
            currentGeneratedMainImage: currentGeneratedMainImage,
            openDraftImageWorkspace: openDraftImageWorkspace,
            toggleImageSku: toggleImageSku,
            toggleMainReference: toggleMainReference,
            createDraftImageTasks: createDraftImageTasks,
            isWorkspaceTaskSelected: isWorkspaceTaskSelected,
            isTaskResultSelected: isTaskResultSelected,
            applyImageTaskResult: applyImageTaskResult,
            removeCarouselImage: removeCarouselImage,
            removeMainImage: removeMainImage,
            workspaceCarouselTasks: workspaceCarouselTasks,
            refreshWorkspaceTasks: refreshWorkspaceTasks,
            applyWorkspaceCarouselTask: applyWorkspaceCarouselTask,
            workspaceMainTasks: workspaceMainTasks,
            applyWorkspaceMainTask: applyWorkspaceMainTask,
            dropCarousel: dropCarousel,
            dropFinalImage: dropFinalImage,
            duplicateDraftForImages: duplicateDraftForImages,
            openImageWorkspaceFromTask: openImageWorkspaceFromTask,
            confirmDraftImages: confirmDraftImages,
            saveDraftEdit: saveDraftEdit,
            publishDraftToMiaoshou: publishDraftToMiaoshou,
            openTiktokExportDialog: openTiktokExportDialog,
            changeTiktokExportCategory: changeTiktokExportCategory,
            changeTiktokExportCatalog: changeTiktokExportCatalog,
            tiktokAttributeMode: tiktokAttributeMode,
            tiktokAttributePlaceholder: tiktokAttributePlaceholder,
            exportSelectedDrafts: exportSelectedDrafts,
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
            toggleAllClaimableTasks: toggleAllClaimableTasks,
            removeBatchClaimImage: removeBatchClaimImage,
            openBatchClaimDialog: openBatchClaimDialog,
            confirmBatchClaim: confirmBatchClaim,
            retryTaskResult: retryTaskResult,
            chooseMaterialUploadFiles: chooseMaterialUploadFiles,
            uploadMaterialAssets: uploadMaterialAssets,
            deleteSelectedMaterialAssets: deleteSelectedMaterialAssets,
            downloadSelectedMaterialAssets: downloadSelectedMaterialAssets,
            openMemberDialog: openMemberDialog,
            openMyAccountDialog: openMyAccountDialog,
            saveMyUserCode: saveMyUserCode,
            saveMember: saveMember,
            toggleMember: toggleMember,
            openMemberCredentialDialog: openMemberCredentialDialog,
            memberCredentialPreview: memberCredentialPreview,
            saveMemberCredential: saveMemberCredential,
            clearMemberCredential: clearMemberCredential,
            loadMiaoshouShops: loadMiaoshouShops,
            openMiaoshouDialog: openMiaoshouDialog,
            saveMiaoshouAccount: saveMiaoshouAccount,
            openShopManagersDialog: openShopManagersDialog,
            saveShopManagers: saveShopManagers,
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
