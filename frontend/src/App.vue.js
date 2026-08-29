import { computed, onMounted, onUnmounted, ref } from 'vue';
import axios from 'axios';
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' });
const token = ref(localStorage.getItem('haitoo_token') || '');
const page = ref('dashboard');
const email = ref('operator@haitoo-demo.com');
const password = ref('ChangeMe123!');
const user = ref(null), company = ref(null), shops = ref([]), templates = ref([]), templateGroups = ref([]), tasks = ref([]), materialAssets = ref([]), drafts = ref([]), points = ref(null), members = ref([]), aiProviders = ref([]);
const loading = ref(false), error = ref('');
const toast = ref('');
const templateQuery = ref(''), activeGroupId = ref(null), selectedTemplateId = ref(null);
const showGroupDialog = ref(false), showTemplateDialog = ref(false), templateFormTab = ref('basic'), newGroupName = ref(''), newTemplateName = ref(''), newTemplateDescription = ref(''), newTemplateTitleTemplate = ref(''), newTemplateProductDescription = ref(''), newTemplateSizeChart = ref(null), newTemplateSizeChartPreview = ref(''), newTemplateGroupId = ref(null), newTemplateImage = ref(null), newTemplateImagePreview = ref(''), newPackageWeight = ref(null), newPackageLength = ref(null), newPackageWidth = ref(null), newPackageHeight = ref(null), newSkuSizeOptions = ref([]), newTemplateAiPrompts = ref([]), editingTemplate = ref(null);
const showMemberDialog = ref(false), editingMember = ref(null), memberForm = ref({ name: '', user_code: '', email: '', password: '', is_active: true }), memberSaving = ref(false);
const showMyAccountDialog = ref(false), myName = ref(''), myUserCode = ref(''), myAccountSaving = ref(false);
const managedShops = ref([]), shopLoading = ref(false), shopError = ref('');
const materialUploading = ref(false), materialUploadError = ref('');
const selectedMaterialAssetIds = ref([]), showMaterialDraftDialog = ref(false), materialDraftTemplateId = ref(null), materialDraftTitle = ref(''), materialDraftProductDescription = ref(''), materialDraftSizeChart = ref(null), materialDraftSizeChartPreview = ref(''), materialDraftTitleGenerating = ref(false), materialDraftSaving = ref(false);
const materialDraftSkuPreviewItems = ref([]);
const showDraftEditDialog = ref(false), editingDraft = ref(null), draftEditTitle = ref(''), draftEditProductDescription = ref(''), draftEditSaving = ref(false), draftEditError = ref('');
const publishingDraftId = ref(null);
const draftPageSize = ref(20), currentDraftPage = ref(1);
const taskPageSize = ref(20), currentTaskPage = ref(1);
const ledgerPageSize = ref(20), currentLedgerPage = ref(1);
const previewImageUrl = ref(''), previewImageAlt = ref('');
const showShopManagersDialog = ref(false), managingShop = ref(null), selectedManagerIds = ref([]), shopManagersSaving = ref(false);
const showTaskDetailDialog = ref(false), viewingTask = ref(null);
const taskListRefreshing = ref(false), retryingTaskId = ref(null);
const showClaimMaterialsDialog = ref(false), claimingTask = ref(null), selectedClaimResultUrls = ref([]), claimingMaterials = ref(false);
const showTaskDraftDialog = ref(false), draftingTask = ref(null), taskDraftTitle = ref(''), taskDraftProductDescription = ref(''), taskDraftSizeChart = ref(null), taskDraftSizeChartPreview = ref(''), taskDraftTitleGenerating = ref(false), taskDraftSaving = ref(false), taskDraftSkuPreviewItems = ref([]);
const defaultSkuSizes = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL'];
const defaultPackageLogistics = { weight: 0.28, length: 30, width: 16, height: 2 };
const creativeAssets = ref([]), showCreativeAssetsDialog = ref(false), creativeAssetError = ref(''), creativeRequirement = ref(''), creativePromptIndex = ref(''), creativeProvider = ref(''), creativeRatio = ref('1:1'), creativeQuality = ref('1K');
const nav = [{ key: 'dashboard', icon: '◈', label: '工作台' }, { key: 'templates', icon: '▦', label: '产品模板' }, { key: 'pod', icon: '✦', label: 'AI创作' }, { key: 'tasks', icon: '◌', label: '任务中心' }, { key: 'materials', icon: '◈', label: '素材库' }, { key: 'drafts', icon: '▤', label: '商品草稿' }, { key: 'members', icon: '♙', label: '成员管理', adminOnly: true }, { key: 'shops', icon: '▣', label: '店铺管理', adminOnly: true }];
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }));
const visibleNav = computed(() => nav.filter(item => !item.adminOnly || user.value?.role === 'company_admin'));
const pageTitle = computed(() => nav.find(x => x.key === page.value)?.label || '');
const filteredTemplates = computed(() => templates.value.filter(t => (!activeGroupId.value || t.group_id === activeGroupId.value) && t.name.toLowerCase().includes(templateQuery.value.trim().toLowerCase())));
const estimatedCreativePoints = computed(() => creativeQuality.value === '2K' ? 20 : 12);
const selectedTemplate = computed(() => templates.value.find(t => t.id === selectedTemplateId.value));
const selectedMaterialAssets = computed(() => materialAssets.value.filter(asset => selectedMaterialAssetIds.value.includes(asset.id)));
const materialDraftTemplate = computed(() => templates.value.find(template => template.id === materialDraftTemplateId.value));
const materialDraftSizes = computed(() => {
    const options = materialDraftTemplate.value?.sku_specifications?.size?.options || [];
    return options.map((size) => String(size).trim()).filter(Boolean);
});
const materialDraftSkuCount = computed(() => selectedMaterialAssets.value.length);
const draftPageCount = computed(() => Math.max(1, Math.ceil(drafts.value.length / draftPageSize.value)));
const visibleDraftPage = computed(() => Math.min(currentDraftPage.value, draftPageCount.value));
const pagedDrafts = computed(() => {
    const start = (visibleDraftPage.value - 1) * draftPageSize.value;
    return drafts.value.slice(start, start + draftPageSize.value);
});
function changeDraftPageSize() { currentDraftPage.value = 1; }
const taskPageCount = computed(() => Math.max(1, Math.ceil(tasks.value.length / taskPageSize.value)));
const visibleTaskPage = computed(() => Math.min(currentTaskPage.value, taskPageCount.value));
const pagedTasks = computed(() => {
    const start = (visibleTaskPage.value - 1) * taskPageSize.value;
    return tasks.value.slice(start, start + taskPageSize.value);
});
function changeTaskPageSize() { currentTaskPage.value = 1; }
const ledgerEntries = computed(() => points.value?.ledger || []);
const ledgerPageCount = computed(() => Math.max(1, Math.ceil(ledgerEntries.value.length / ledgerPageSize.value)));
const visibleLedgerPage = computed(() => Math.min(currentLedgerPage.value, ledgerPageCount.value));
const pagedLedgerEntries = computed(() => {
    const start = (visibleLedgerPage.value - 1) * ledgerPageSize.value;
    return ledgerEntries.value.slice(start, start + ledgerPageSize.value);
});
function changeLedgerPageSize() { currentLedgerPage.value = 1; }
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
    const [me, s, t, g, task, material, d, p, providers] = await Promise.all([api.get('/me', h), api.get('/shops', h), api.get('/templates', h), api.get('/template-groups', h), api.get('/tasks', h), api.get('/material-assets', h), api.get('/drafts', h), api.get('/points', h), api.get('/ai-providers', h)]);
    user.value = me.data.user;
    company.value = me.data.company;
    shops.value = s.data;
    templates.value = t.data;
    templateGroups.value = g.data;
    tasks.value = task.data;
    materialAssets.value = material.data;
    drafts.value = d.data;
    points.value = p.data;
    aiProviders.value = providers.data;
    if (!creativeProvider.value)
        creativeProvider.value = aiProviders.value.find(item => item.is_default)?.provider || aiProviders.value[0]?.provider || '';
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
    if (viewingTask.value)
        viewingTask.value = tasks.value.find(task => task.id === viewingTask.value.id) || null;
}
async function login() { try {
    loading.value = true;
    error.value = '';
    const { data } = await api.post('/auth/login', { email: email.value, password: password.value });
    token.value = data.access_token;
    localStorage.setItem('haitoo_token', token.value);
    await refresh();
}
catch {
    error.value = '登录失败，请检查账号密码';
}
finally {
    loading.value = false;
} }
function onCreativeAssetChange(event) {
    const files = Array.from(event.target.files || []);
    const available = 1000 - creativeAssets.value.length;
    files.slice(0, available).forEach(file => creativeAssets.value.push({ id: `${file.name}-${file.lastModified}-${crypto.randomUUID()}`, file, preview: URL.createObjectURL(file) }));
    if (files.length)
        creativeAssetError.value = '';
    event.target.value = '';
}
function removeCreativeAsset(id) { const asset = creativeAssets.value.find(item => item.id === id); if (asset)
    URL.revokeObjectURL(asset.preview); creativeAssets.value = creativeAssets.value.filter(item => item.id !== id); }
function clearCreativeAssets() { creativeAssets.value.forEach(item => URL.revokeObjectURL(item.preview)); creativeAssets.value = []; showCreativeAssetsDialog.value = false; }
async function uploadCreativeAssets() { return Promise.all(creativeAssets.value.map(async (asset) => { const form = new FormData(); form.append('file', asset.file); const { data } = await api.post('/uploads/creative-asset', form, { headers: headers.value }); return data.url; })); }
async function createTask() { if (!creativeAssets.value.length) {
    creativeAssetError.value = '请先上传至少一张印花图，再开始印花贴合。';
    return;
} if (!creativeRequirement.value.trim()) {
    showToast('请填写创作要求');
    return;
} if (!selectedTemplateId.value || !creativeProvider.value)
    return; try {
    creativeAssetError.value = '';
    const print_urls = await uploadCreativeAssets();
    await api.post('/tasks', { template_id: selectedTemplateId.value, provider: creativeProvider.value, ratio: creativeRatio.value, quality: creativeQuality.value, print_url: print_urls[0], print_urls, creative_requirement: creativeRequirement.value.trim() }, { headers: headers.value });
    await refresh();
    page.value = 'tasks';
}
catch (e) {
    error.value = e.response?.data?.detail || '创建 AI 任务失败';
} }
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
function applyTemplateAiPrompt() { if (creativePromptIndex.value === '')
    return; const prompt = selectedTemplateAiPrompts()[Number(creativePromptIndex.value)]; if (prompt)
    creativeRequirement.value = prompt.content; }
function onCreativeTemplateChange() { creativePromptIndex.value = ''; creativeRequirement.value = ''; }
function onCoverChange(event) { const file = event.target.files?.[0] || null; newTemplateImage.value = file; newTemplateImagePreview.value = file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.cover_url); }
function onSizeChartChange(event) { const file = event.target.files?.[0] || null; newTemplateSizeChart.value = file; newTemplateSizeChartPreview.value = file ? URL.createObjectURL(file) : imageUrl(editingTemplate.value?.size_chart_url); }
async function uploadCover() { if (!newTemplateImage.value)
    return undefined; const form = new FormData(); form.append('file', newTemplateImage.value); const { data } = await api.post('/uploads/template-cover', form, { headers: headers.value }); return data.url; }
async function uploadSizeChart() { if (!newTemplateSizeChart.value)
    return undefined; const form = new FormData(); form.append('file', newTemplateSizeChart.value); const { data } = await api.post('/uploads/template-cover', form, { headers: headers.value }); return data.url; }
function validateNewTemplate() {
    const sizeOptions = newSkuSizeOptions.value.map(value => value.trim()).filter(Boolean);
    const validations = [
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
    const cover_url = (await uploadCover()) ?? editingTemplate.value?.cover_url ?? null;
    const size_chart_url = (await uploadSizeChart()) ?? editingTemplate.value?.size_chart_url ?? null;
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
    error.value = e.response?.data?.detail || '保存模板失败';
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
        tasks.value = (await api.get('/tasks', { headers: headers.value })).data;
        if (viewingTask.value)
            viewingTask.value = tasks.value.find(task => task.id === viewingTask.value.id) || null;
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
function openTaskDetail(task) { viewingTask.value = task; showTaskDetailDialog.value = true; }
function templateCoverUrl(template) { if (template?.cover_url)
    return imageUrl(template.cover_url); return template?.name === '白色 T恤正面' ? '/template-white-tshirt-front.png' : '/template-tshirt.svg'; }
function hasTemplateCover(template) { return Boolean(template?.cover_url || template?.name === '白色 T恤正面'); }
function useTemplate(template) { selectedTemplateId.value = template.id; page.value = 'pod'; }
function toggleMaterialAsset(assetId) { selectedMaterialAssetIds.value = selectedMaterialAssetIds.value.includes(assetId) ? selectedMaterialAssetIds.value.filter(id => id !== assetId) : [...selectedMaterialAssetIds.value, assetId]; }
function randomSkuSuffix() { const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'; return Array.from(crypto.getRandomValues(new Uint8Array(6)), value => alphabet[value % alphabet.length]).join(''); }
function refreshMaterialDraftSkuPreview() {
    materialDraftSkuPreviewItems.value = materialDraftTemplate.value
        ? selectedMaterialAssets.value.map(asset => ({ image_url: asset.url, size: null, sku: `M05L${user.value?.user_code?.toUpperCase() || '??'}${randomSkuSuffix()}` }))
        : [];
}
function onMaterialDraftTemplateChange() {
    refreshMaterialDraftSkuPreview();
    const template = materialDraftTemplate.value;
    materialDraftTitle.value = template ? `${template.name} POD 商品` : '';
    materialDraftProductDescription.value = template?.product_description || '';
    materialDraftSizeChart.value = null;
    materialDraftSizeChartPreview.value = imageUrl(template?.size_chart_url);
}
function onMaterialDraftSizeChartChange(event) { const file = event.target.files?.[0] || null; materialDraftSizeChart.value = file; materialDraftSizeChartPreview.value = file ? URL.createObjectURL(file) : imageUrl(materialDraftTemplate.value?.size_chart_url); }
async function uploadMaterialDraftSizeChart() { if (!materialDraftSizeChart.value)
    return undefined; const form = new FormData(); form.append('file', materialDraftSizeChart.value); const { data } = await api.post('/uploads/draft-size-chart', form, { headers: headers.value }); return data.url; }
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
function openMaterialDraftDialog() { materialDraftTemplateId.value = null; materialDraftTitle.value = ''; materialDraftProductDescription.value = ''; materialDraftSizeChart.value = null; materialDraftSizeChartPreview.value = ''; materialDraftSkuPreviewItems.value = []; showMaterialDraftDialog.value = true; }
function openTaskDraftDialog(task) {
    const template = templates.value.find(item => item.id === task.template_id);
    if (!template || !task.selected_result_url) {
        showToast('任务缺少产品模板或已选结果图');
        return;
    }
    draftingTask.value = task;
    taskDraftTitle.value = `${template.name} POD 商品`;
    taskDraftProductDescription.value = template.product_description || '';
    taskDraftSizeChart.value = null;
    taskDraftSizeChartPreview.value = imageUrl(template.size_chart_url);
    taskDraftSkuPreviewItems.value = [{ image_url: task.selected_result_url, size: null, sku: `M05L${user.value?.user_code?.toUpperCase() || '??'}${randomSkuSuffix()}` }];
    showTaskDraftDialog.value = true;
}
function onTaskDraftSizeChartChange(event) {
    const file = event.target.files?.[0] || null;
    taskDraftSizeChart.value = file;
    const template = templates.value.find(item => item.id === draftingTask.value?.template_id);
    taskDraftSizeChartPreview.value = file ? URL.createObjectURL(file) : imageUrl(template?.size_chart_url);
}
async function uploadTaskDraftSizeChart() {
    if (!taskDraftSizeChart.value)
        return undefined;
    const form = new FormData();
    form.append('file', taskDraftSizeChart.value);
    const { data } = await api.post('/uploads/draft-size-chart', form, { headers: headers.value });
    return data.url;
}
async function generateTaskDraftTitle() {
    if (!draftingTask.value?.template_id || !draftingTask.value?.selected_result_url)
        return;
    try {
        taskDraftTitleGenerating.value = true;
        const { data } = await api.post(`/templates/${draftingTask.value.template_id}/generate-draft-title`, { image_url: draftingTask.value.selected_result_url }, { headers: headers.value });
        taskDraftTitle.value = data.title;
    }
    catch (e) {
        showToast(e.response?.data?.detail || 'AI 生成标题失败，请稍后重试');
    }
    finally {
        taskDraftTitleGenerating.value = false;
    }
}
async function createTaskDraft() {
    if (!draftingTask.value || !taskDraftTitle.value.trim()) {
        showToast('请生成或填写商品标题');
        return;
    }
    try {
        taskDraftSaving.value = true;
        const template = templates.value.find(item => item.id === draftingTask.value.template_id);
        const size_chart_url = (await uploadTaskDraftSizeChart()) ?? template?.size_chart_url ?? null;
        await api.post(`/tasks/${draftingTask.value.id}/draft`, { title: taskDraftTitle.value.trim(), product_description: taskDraftProductDescription.value.trim() || null, size_chart_url, sku_items: taskDraftSkuPreviewItems.value }, { headers: headers.value });
        showTaskDraftDialog.value = false;
        await refresh();
        page.value = 'drafts';
        showToast('商品草稿已创建');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '创建商品草稿失败');
    }
    finally {
        taskDraftSaving.value = false;
    }
}
async function createDraftFromMaterialAssets() {
    if (!selectedMaterialAssetIds.value.length)
        return;
    if (!materialDraftTemplateId.value) {
        showToast('请选择产品模板');
        return;
    }
    if (!materialDraftTitle.value.trim()) {
        showToast('请生成或填写商品标题');
        return;
    }
    try {
        materialDraftSaving.value = true;
        const size_chart_url = (await uploadMaterialDraftSizeChart()) ?? materialDraftTemplate.value?.size_chart_url ?? null;
        const { data: draft } = await api.post('/drafts/from-material-assets', { material_asset_ids: selectedMaterialAssetIds.value, template_id: materialDraftTemplateId.value, title: materialDraftTitle.value.trim(), product_description: materialDraftProductDescription.value.trim() || null, size_chart_url, sku_items: materialDraftSkuPreviewItems.value }, { headers: headers.value });
        const { data: publishResult } = await api.post(`/drafts/${draft.id}/claim-to-tiktok`, {}, { headers: headers.value });
        selectedMaterialAssetIds.value = [];
        showMaterialDraftDialog.value = false;
        await refresh();
        page.value = 'drafts';
        showToast(`已发布公共草稿箱并认领到 TikTok（编号：${publishResult.tiktok_collect_box_detail_id}）`);
    }
    catch (e) {
        showToast(e.response?.data?.detail || '创建、发布或认领 TikTok 失败；草稿已保留，可在商品待发布页重试');
    }
    finally {
        materialDraftSaving.value = false;
    }
}
function openDraftEditDialog(draft) { editingDraft.value = draft; draftEditTitle.value = draft.title; draftEditProductDescription.value = draft.product_description || ''; draftEditError.value = ''; showDraftEditDialog.value = true; }
function draftSkuForImage(draft, imageUrl) { return draft?.sku_items?.find((item) => item.image_url === imageUrl)?.sku || '—'; }
function openImagePreview(url, alt) { previewImageUrl.value = imageUrl(url); previewImageAlt.value = alt; }
async function saveDraftEdit() {
    if (!editingDraft.value || !draftEditTitle.value.trim()) {
        draftEditError.value = '请输入商品标题';
        return;
    }
    try {
        draftEditSaving.value = true;
        draftEditError.value = '';
        await api.put(`/drafts/${editingDraft.value.id}`, { title: draftEditTitle.value.trim(), product_description: draftEditProductDescription.value.trim() || null }, { headers: headers.value });
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
        showToast(e.response?.data?.detail || '发布并认领 TikTok 失败，请稍后重试');
    }
    finally {
        publishingDraftId.value = null;
    }
}
function openClaimMaterialsDialog(task) { claimingTask.value = task; selectedClaimResultUrls.value = []; showClaimMaterialsDialog.value = true; }
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
async function retryTaskResult(task) {
    try {
        retryingTaskId.value = task.id;
        await api.post(`/tasks/${task.id}/retry-result`, {}, { headers: headers.value });
        await refreshTaskList();
        showToast('已开始重新获取结果');
    }
    catch (e) {
        showToast(e.response?.data?.detail || '重新获取结果失败');
    }
    finally {
        retryingTaskId.value = null;
    }
}
async function uploadMaterialAssets(event) {
    const input = event.target;
    const files = Array.from(input.files || []);
    input.value = '';
    if (!files.length)
        return;
    try {
        materialUploading.value = true;
        materialUploadError.value = '';
        const form = new FormData();
        files.forEach(file => form.append('files', file));
        await api.post('/material-assets/upload', form, { headers: headers.value });
        await refresh();
    }
    catch (e) {
        materialUploadError.value = e.response?.data?.detail || '上传素材失败，请稍后重试';
    }
    finally {
        materialUploading.value = false;
    }
}
async function deleteSelectedMaterialAssets() {
    const assetIds = [...selectedMaterialAssetIds.value];
    if (!assetIds.length || !confirm(`确定从素材库删除选中的 ${assetIds.length} 张图片吗？`))
        return;
    try {
        await Promise.all(assetIds.map(assetId => api.delete(`/material-assets/${assetId}`, { headers: headers.value })));
        materialAssets.value = materialAssets.value.filter(item => !assetIds.includes(item.id));
        selectedMaterialAssetIds.value = [];
        showToast(`已删除 ${assetIds.length} 张素材`);
    }
    catch (e) {
        await refresh();
        showToast(e.response?.data?.detail || '删除素材失败，请稍后重试');
    }
}
function openMemberDialog(member) { editingMember.value = member || null; memberForm.value = { name: member?.name || '', user_code: member?.user_code || '', email: member?.email || '', password: '', is_active: member?.is_active ?? true }; showMemberDialog.value = true; }
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
async function saveMember() { if (!memberForm.value.name.trim() || !memberForm.value.email.trim() || (!editingMember.value && memberForm.value.password.length < 8))
    return; const userCode = memberForm.value.user_code.trim(); if (userCode && [...userCode].length !== 2) {
    showToast('用户代码必须恰好为两个字符');
    return;
} try {
    memberSaving.value = true;
    error.value = '';
    const payload = { name: memberForm.value.name.trim(), user_code: userCode || null, email: memberForm.value.email.trim() };
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
    error.value = message;
    showToast(message);
}
finally {
    memberSaving.value = false;
} }
async function toggleMember(member) { try {
    await api.put(`/members/${member.id}`, { is_active: !member.is_active }, { headers: headers.value });
    await refresh();
}
catch (e) {
    error.value = e.response?.data?.detail || '更新成员状态失败';
} }
async function loadMiaoshouShops() { try {
    shopLoading.value = true;
    shopError.value = '';
    await api.post('/miaoshou/shops', {}, { headers: headers.value });
    await refresh();
}
catch (e) {
    shopError.value = e.response?.data?.detail || '获取妙手店铺失败';
}
finally {
    shopLoading.value = false;
} }
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
function logout() { localStorage.removeItem('haitoo_token'); token.value = ''; user.value = null; }
api.interceptors.response.use(response => response, requestError => {
    if (requestError.response?.data?.detail === '登录已失效') {
        logout();
        showToast('登录已失效，请重新登录');
    }
    return Promise.reject(requestError);
});
let taskResultPollingTimer;
async function refreshPendingTaskResults() {
    if (!token.value || !tasks.value.some(task => ['queued', 'running'].includes(task.status)))
        return;
    try {
        tasks.value = (await api.get('/tasks', { headers: headers.value })).data;
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
    });
    (__VLS_ctx.email);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "password",
    });
    (__VLS_ctx.password);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.login) },
        ...{ class: "primary full" },
        disabled: (__VLS_ctx.loading),
    });
    (__VLS_ctx.loading ? '登录中…' : '登录');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    if (__VLS_ctx.error) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error" },
        });
        (__VLS_ctx.error);
    }
}
else {
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
                    if (!!(!__VLS_ctx.token))
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
                    if (!!(!__VLS_ctx.token))
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
        (__VLS_ctx.tasks.filter(t => t.status === 'awaiting_selection').length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.drafts.length);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.points?.available ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
        (__VLS_ctx.points?.frozen ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "two-col" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.token))
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
            (task.parameters.quality);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip blue" },
            });
            (task.status === 'awaiting_selection' ? '待领取' : '处理中');
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.token))
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
                    if (!!(!__VLS_ctx.token))
                        return;
                    if (!(__VLS_ctx.page === 'dashboard'))
                        return;
                    __VLS_ctx.page = 'points';
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
                        if (!!(!__VLS_ctx.token))
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
                        if (!!(!__VLS_ctx.token))
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
                    if (!!(!__VLS_ctx.token))
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
                        if (!!(!__VLS_ctx.token))
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
                        if (!!(!__VLS_ctx.token))
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
                            if (!!(!__VLS_ctx.token))
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
                            if (!!(!__VLS_ctx.token))
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
            ...{ class: "pod-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "requirement-label" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        if (__VLS_ctx.selectedTemplateAiPrompts().length) {
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
            for (const [prompt, index] of __VLS_getVForSourceType((__VLS_ctx.selectedTemplateAiPrompts()))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: (`${prompt.name}-${index}`),
                    value: (String(index)),
                });
                (prompt.name);
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
                        if (!!(!__VLS_ctx.token))
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
                        if (!!(!__VLS_ctx.token))
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "product-preview template-preview" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.templateCoverUrl(__VLS_ctx.selectedTemplate)),
            alt: (__VLS_ctx.selectedTemplate?.name || '产品模板'),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.selectedTemplate?.name);
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
        });
        for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.aiProviders))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: (provider.provider),
                value: (provider.provider),
            });
            (provider.display_name);
            (provider.model);
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.createTask) },
            ...{ class: "primary full" },
        });
    }
    else if (__VLS_ctx.page === 'tasks') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.refreshTaskList) },
            ...{ class: "secondary" },
            disabled: (__VLS_ctx.taskListRefreshing),
        });
        (__VLS_ctx.taskListRefreshing ? '刷新中…' : '↻ 刷新列表');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "draft-table task-table" },
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [task] of __VLS_getVForSourceType((__VLS_ctx.pagedTasks))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (task.id),
                ...{ class: "trow" },
                ...{ style: {} },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (task.id);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.parameters?.task_type || '替换印花');
            if (task.parameters?.print_urls?.[0] || task.parameters?.print_url) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.parameters?.print_urls?.[0] || task.parameters?.print_url))
                                return;
                            __VLS_ctx.openImagePreview(task.parameters?.print_urls?.[0] || task.parameters?.print_url, '创作素材');
                        } },
                    type: "button",
                    ...{ class: "task-material-thumbnail" },
                    title: "查看创作素材",
                    'aria-label': "查看创作素材大图",
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                    src: (__VLS_ctx.imageUrl(task.parameters?.print_urls?.[0] || task.parameters?.print_url)),
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
                            if (!!(!__VLS_ctx.token))
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
                ...{ class: "chip" },
                ...{ class: (__VLS_ctx.taskStatusClass(task.status)) },
            });
            (__VLS_ctx.taskStatusLabel[task.status] || task.status || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (task.result_urls?.length || 0);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ({ error: task.failure_reason }) },
            });
            (task.failure_reason || '—');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "task-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
            if (task.provider === 'grsai' && task.status === 'failed' && task.failure_reason === 'grsai 任务查询超时，请稍后重试') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.provider === 'grsai' && task.status === 'failed' && task.failure_reason === 'grsai 任务查询超时，请稍后重试'))
                                return;
                            __VLS_ctx.retryTaskResult(task);
                        } },
                    ...{ class: "secondary" },
                    disabled: (__VLS_ctx.retryingTaskId === task.id),
                });
                (__VLS_ctx.retryingTaskId === task.id ? '获取中…' : '重新获取结果');
            }
            if (['awaiting_selection', 'completed'].includes(task.status)) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(['awaiting_selection', 'completed'].includes(task.status)))
                                return;
                            __VLS_ctx.openClaimMaterialsDialog(task);
                        } },
                    ...{ class: "secondary" },
                });
            }
            if (task.status === 'completed') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.page === 'dashboard'))
                                return;
                            if (!!(__VLS_ctx.page === 'templates'))
                                return;
                            if (!!(__VLS_ctx.page === 'pod'))
                                return;
                            if (!(__VLS_ctx.page === 'tasks'))
                                return;
                            if (!(task.status === 'completed'))
                                return;
                            __VLS_ctx.openTaskDraftDialog(task);
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
        if (__VLS_ctx.tasks.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.tasks.length);
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (500),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (1000),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.tasks.length))
                            return;
                        __VLS_ctx.currentTaskPage = __VLS_ctx.visibleTaskPage - 1;
                    } },
                disabled: (__VLS_ctx.visibleTaskPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.visibleTaskPage);
            (__VLS_ctx.taskPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.page === 'dashboard'))
                            return;
                        if (!!(__VLS_ctx.page === 'templates'))
                            return;
                        if (!!(__VLS_ctx.page === 'pod'))
                            return;
                        if (!(__VLS_ctx.page === 'tasks'))
                            return;
                        if (!(__VLS_ctx.tasks.length))
                            return;
                        __VLS_ctx.currentTaskPage = __VLS_ctx.visibleTaskPage + 1;
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "primary material-upload-button" },
            ...{ class: ({ disabled: __VLS_ctx.materialUploading }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.uploadMaterialAssets) },
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
                ...{ onClick: (__VLS_ctx.deleteSelectedMaterialAssets) },
                ...{ class: "negative" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "material-grid" },
        });
        for (const [asset] of __VLS_getVForSourceType((__VLS_ctx.materialAssets))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
                key: (asset.id),
                ...{ class: "material-card" },
                ...{ class: ({ selected: __VLS_ctx.selectedMaterialAssetIds.includes(asset.id) }) },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "material-select-mark" },
            });
            (__VLS_ctx.selectedMaterialAssetIds.includes(asset.id) ? '✓' : '');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.imageUrl(asset.url)),
                alt: (asset.name),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (asset.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (asset.source_task_id ? `来源任务 #${asset.source_task_id}` : '本地上传');
            (new Date(asset.created_at).toLocaleDateString());
        }
        if (!__VLS_ctx.materialAssets.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
    }
    else if (__VLS_ctx.page === 'drafts') {
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
                    if (!!(!__VLS_ctx.token))
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "draft-table" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "thead draft-thead" },
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
        for (const [draft] of __VLS_getVForSourceType((__VLS_ctx.pagedDrafts))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (draft.id),
                ...{ class: "trow draft-trow" },
            });
            if (draft.image_urls?.[0]) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
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
            (new Date(draft.updated_at || draft.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (draft.updated_by_name || '历史记录缺失');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (draft.tiktok_collect_box_id ? 'blue' : 'orange') },
            });
            (draft.tiktok_collect_box_id ? '已认领到 TikTok' : draft.miaoshou_collect_box_id ? '待认领到 TikTok' : '待发布');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
                            if (!!(!__VLS_ctx.token))
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
                (__VLS_ctx.publishingDraftId === draft.id ? '处理中…' : '发布并认领 TikTok');
            }
            else {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (draft.tiktok_collect_box_id);
            }
        }
        if (!__VLS_ctx.drafts.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "empty" },
            });
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.drafts.length);
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
                        if (!!(!__VLS_ctx.token))
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
                        if (!!(!__VLS_ctx.drafts.length))
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
                        if (!!(!__VLS_ctx.token))
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
                        if (!!(!__VLS_ctx.drafts.length))
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
                    if (!!(!__VLS_ctx.token))
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (member.email);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "chip" },
                ...{ class: (member.is_active ? 'blue' : 'orange') },
            });
            (member.is_active ? '启用中' : '已停用');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(member.created_at).toLocaleDateString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
                        __VLS_ctx.openMemberDialog(member);
                    } },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
                        __VLS_ctx.toggleMember(member);
                    } },
                ...{ class: (member.is_active ? 'negative' : 'positive') },
            });
            (member.is_active ? '停用' : '启用');
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.loadMiaoshouShops) },
            ...{ class: "primary" },
            disabled: (__VLS_ctx.shopLoading),
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
                        if (!!(!__VLS_ctx.token))
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
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "page" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "points-grid" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            ...{ class: "balance" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.points?.available ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            ...{ class: "balance muted" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.points?.frozen ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            ...{ class: "rule" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel ledger" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.pagedLedgerEntries))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (row.id),
                ...{ class: "ledger-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (row.entry_type);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (new Date(row.created_at).toLocaleString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (row.note);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "ledger-actor" },
            });
            (row.actor_name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({
                ...{ class: (row.amount > 0 ? 'positive' : 'negative') },
            });
            (row.amount > 0 ? '+' : '');
            (row.amount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (row.balance_after);
        }
        if (__VLS_ctx.ledgerEntries.length) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.footer, __VLS_intrinsicElements.footer)({
                ...{ class: "draft-pagination" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.ledgerEntries.length);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (__VLS_ctx.changeLedgerPageSize) },
                value: (__VLS_ctx.ledgerPageSize),
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
                        if (!!(!__VLS_ctx.token))
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
                        if (!(__VLS_ctx.ledgerEntries.length))
                            return;
                        __VLS_ctx.currentLedgerPage = __VLS_ctx.visibleLedgerPage - 1;
                    } },
                disabled: (__VLS_ctx.visibleLedgerPage === 1),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.visibleLedgerPage);
            (__VLS_ctx.ledgerPageCount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
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
                        if (!(__VLS_ctx.ledgerEntries.length))
                            return;
                        __VLS_ctx.currentLedgerPage = __VLS_ctx.visibleLedgerPage + 1;
                    } },
                disabled: (__VLS_ctx.visibleLedgerPage === __VLS_ctx.ledgerPageCount),
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
if (__VLS_ctx.showTaskDetailDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog))
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
                if (!(__VLS_ctx.showTaskDetailDialog))
                    return;
                __VLS_ctx.showTaskDetailDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.viewingTask?.id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.task_type || '替换印花');
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
                    if (!(__VLS_ctx.showTaskDetailDialog))
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "draft-edit-section" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.ratio || '—');
    (__VLS_ctx.viewingTask?.parameters?.quality || '—');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.parameters?.creative_requirement || '未填写');
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.viewingTask?.provider_task_id || '—');
    if (__VLS_ctx.viewingTask?.failure_reason) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error" },
        });
        (__VLS_ctx.viewingTask.failure_reason);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDetailDialog))
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
    (__VLS_ctx.creativeAssets.length);
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
    (__VLS_ctx.creativeAssets.length);
    (__VLS_ctx.creativeAssets.length);
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        ...{ onChange: (__VLS_ctx.onMaterialDraftTemplateChange) },
        value: (__VLS_ctx.materialDraftTemplateId),
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
            maxlength: "180",
            placeholder: "请生成或填写商品标题",
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
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.materialDraftSkuPreviewItems))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (item.sku),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (item.sku);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: "material-draft-size-chart" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            ...{ onChange: (__VLS_ctx.onMaterialDraftSizeChartChange) },
            accept: "image/png,image/jpeg,image/webp",
            type: "file",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.materialDraftSizeChart ? __VLS_ctx.materialDraftSizeChart.name : __VLS_ctx.materialDraftTemplate?.size_chart_url ? '默认使用产品模版尺码图，可重新选择一张图片' : '可上传 1 张尺码图，支持 JPG、PNG、WebP，最大 5MB');
        if (__VLS_ctx.materialDraftSizeChartPreview) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
                src: (__VLS_ctx.materialDraftSizeChartPreview),
                alt: "尺码图预览",
            });
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
if (__VLS_ctx.showTaskDraftDialog) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDraftDialog))
                    return;
                __VLS_ctx.showTaskDraftDialog = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal-card material-draft-dialog" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDraftDialog))
                    return;
                __VLS_ctx.showTaskDraftDialog = false;
            } },
        ...{ class: "modal-close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.draftingTask?.id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        value: (__VLS_ctx.templates.find(template => template.id === __VLS_ctx.draftingTask?.template_id)?.name || '历史模板已删除'),
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-preview-images" },
    });
    if (__VLS_ctx.draftingTask?.selected_result_url) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.imageUrl(__VLS_ctx.draftingTask.selected_result_url)),
            alt: "任务已选结果图",
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "material-draft-details" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-title-row" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "180",
        placeholder: "请生成或填写商品标题",
    });
    (__VLS_ctx.taskDraftTitle);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.generateTaskDraftTitle) },
        ...{ class: "secondary" },
        disabled: (__VLS_ctx.taskDraftTitleGenerating),
    });
    (__VLS_ctx.taskDraftTitleGenerating ? '生成中…' : 'AI 生成标题');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: (__VLS_ctx.taskDraftProductDescription),
        maxlength: "5000",
        placeholder: "默认使用产品模版描述，可按商品修改",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "material-draft-sku-summary" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "material-draft-sku-list" },
    });
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.taskDraftSkuPreviewItems))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (item.sku),
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (item.sku);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: "material-draft-size-chart" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onChange: (__VLS_ctx.onTaskDraftSizeChartChange) },
        accept: "image/png,image/jpeg,image/webp",
        type: "file",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    (__VLS_ctx.taskDraftSizeChart ? __VLS_ctx.taskDraftSizeChart.name : __VLS_ctx.taskDraftSizeChartPreview ? '默认使用产品模版尺码图，可重新选择一张图片' : '可上传 1 张尺码图，支持 JPG、PNG、WebP，最大 5MB');
    if (__VLS_ctx.taskDraftSizeChartPreview) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.taskDraftSizeChartPreview),
            alt: "尺码图预览",
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showTaskDraftDialog))
                    return;
                __VLS_ctx.showTaskDraftDialog = false;
            } },
        ...{ class: "ghost" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createTaskDraft) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.taskDraftSaving),
    });
    (__VLS_ctx.taskDraftSaving ? '创建中…' : '确认创建');
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
        maxlength: "180",
        placeholder: "请输入商品标题",
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "draft-edit-preview" },
    });
    for (const [url] of __VLS_getVForSourceType((__VLS_ctx.editingDraft?.image_urls))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (url),
            ...{ class: "draft-edit-image-item" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (__VLS_ctx.draftSkuForImage(__VLS_ctx.editingDraft, url));
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
    (__VLS_ctx.editingMember ? '留空密码即可保持原密码不变。' : '新成员将作为普通成员加入当前公司。');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "80",
        placeholder: "请输入姓名",
    });
    (__VLS_ctx.memberForm.name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "2",
        placeholder: "例如：CN",
    });
    (__VLS_ctx.memberForm.user_code);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
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
    for (const [member] of __VLS_getVForSourceType((__VLS_ctx.members))) {
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
    if (!__VLS_ctx.members.length) {
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
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createTemplate) },
        ...{ class: "primary" },
    });
    (__VLS_ctx.editingTemplate ? '保存修改' : '确认新增');
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
/** @type {__VLS_StyleScopedClasses['login-shell']} */ ;
/** @type {__VLS_StyleScopedClasses['login-card']} */ ;
/** @type {__VLS_StyleScopedClasses['brand-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['full']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
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
/** @type {__VLS_StyleScopedClasses['blue']} */ ;
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
/** @type {__VLS_StyleScopedClasses['requirement-label']} */ ;
/** @type {__VLS_StyleScopedClasses['prompt-picker']} */ ;
/** @type {__VLS_StyleScopedClasses['pod-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['upload']} */ ;
/** @type {__VLS_StyleScopedClasses['floral']} */ ;
/** @type {__VLS_StyleScopedClasses['asset-count']} */ ;
/** @type {__VLS_StyleScopedClasses['creative-asset-error']} */ ;
/** @type {__VLS_StyleScopedClasses['manage-assets']} */ ;
/** @type {__VLS_StyleScopedClasses['product-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['template-preview']} */ ;
/** @type {__VLS_StyleScopedClasses['settings']} */ ;
/** @type {__VLS_StyleScopedClasses['settings-title']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-fields']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-field']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-field']} */ ;
/** @type {__VLS_StyleScopedClasses['parameter-field']} */ ;
/** @type {__VLS_StyleScopedClasses['estimate']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['full']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['task-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['task-material-thumbnail']} */ ;
/** @type {__VLS_StyleScopedClasses['ai-model-cell']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-task-id']} */ ;
/** @type {__VLS_StyleScopedClasses['copy-icon-button']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['task-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['material-upload-button']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-upload-error']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-bar']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['negative']} */ ;
/** @type {__VLS_StyleScopedClasses['ghost']} */ ;
/** @type {__VLS_StyleScopedClasses['material-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['material-card']} */ ;
/** @type {__VLS_StyleScopedClasses['material-select-mark']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-trow']} */ ;
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
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['section-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-table']} */ ;
/** @type {__VLS_StyleScopedClasses['thead']} */ ;
/** @type {__VLS_StyleScopedClasses['trow']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['points-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['balance']} */ ;
/** @type {__VLS_StyleScopedClasses['balance']} */ ;
/** @type {__VLS_StyleScopedClasses['muted']} */ ;
/** @type {__VLS_StyleScopedClasses['rule']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['ledger']} */ ;
/** @type {__VLS_StyleScopedClasses['ledger-row']} */ ;
/** @type {__VLS_StyleScopedClasses['ledger-actor']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-pagination']} */ ;
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
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['material-draft-preview-images']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
/** @type {__VLS_StyleScopedClasses['chip']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
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
/** @type {__VLS_StyleScopedClasses['material-draft-dialog']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-close']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-description']} */ ;
/** @type {__VLS_StyleScopedClasses['draft-edit-section']} */ ;
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
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            token: token,
            page: page,
            email: email,
            password: password,
            user: user,
            templates: templates,
            templateGroups: templateGroups,
            tasks: tasks,
            materialAssets: materialAssets,
            drafts: drafts,
            points: points,
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
            showMyAccountDialog: showMyAccountDialog,
            myName: myName,
            myUserCode: myUserCode,
            myAccountSaving: myAccountSaving,
            managedShops: managedShops,
            shopLoading: shopLoading,
            shopError: shopError,
            materialUploading: materialUploading,
            materialUploadError: materialUploadError,
            selectedMaterialAssetIds: selectedMaterialAssetIds,
            showMaterialDraftDialog: showMaterialDraftDialog,
            materialDraftTemplateId: materialDraftTemplateId,
            materialDraftTitle: materialDraftTitle,
            materialDraftProductDescription: materialDraftProductDescription,
            materialDraftSizeChart: materialDraftSizeChart,
            materialDraftSizeChartPreview: materialDraftSizeChartPreview,
            materialDraftTitleGenerating: materialDraftTitleGenerating,
            materialDraftSaving: materialDraftSaving,
            materialDraftSkuPreviewItems: materialDraftSkuPreviewItems,
            showDraftEditDialog: showDraftEditDialog,
            editingDraft: editingDraft,
            draftEditTitle: draftEditTitle,
            draftEditProductDescription: draftEditProductDescription,
            draftEditSaving: draftEditSaving,
            draftEditError: draftEditError,
            publishingDraftId: publishingDraftId,
            draftPageSize: draftPageSize,
            currentDraftPage: currentDraftPage,
            taskPageSize: taskPageSize,
            currentTaskPage: currentTaskPage,
            ledgerPageSize: ledgerPageSize,
            currentLedgerPage: currentLedgerPage,
            previewImageUrl: previewImageUrl,
            previewImageAlt: previewImageAlt,
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
            showTaskDraftDialog: showTaskDraftDialog,
            draftingTask: draftingTask,
            taskDraftTitle: taskDraftTitle,
            taskDraftProductDescription: taskDraftProductDescription,
            taskDraftSizeChart: taskDraftSizeChart,
            taskDraftSizeChartPreview: taskDraftSizeChartPreview,
            taskDraftTitleGenerating: taskDraftTitleGenerating,
            taskDraftSaving: taskDraftSaving,
            taskDraftSkuPreviewItems: taskDraftSkuPreviewItems,
            creativeAssets: creativeAssets,
            showCreativeAssetsDialog: showCreativeAssetsDialog,
            creativeAssetError: creativeAssetError,
            creativeRequirement: creativeRequirement,
            creativePromptIndex: creativePromptIndex,
            creativeProvider: creativeProvider,
            creativeRatio: creativeRatio,
            creativeQuality: creativeQuality,
            visibleNav: visibleNav,
            pageTitle: pageTitle,
            filteredTemplates: filteredTemplates,
            selectedTemplate: selectedTemplate,
            selectedMaterialAssets: selectedMaterialAssets,
            materialDraftTemplate: materialDraftTemplate,
            materialDraftSizes: materialDraftSizes,
            materialDraftSkuCount: materialDraftSkuCount,
            draftPageCount: draftPageCount,
            visibleDraftPage: visibleDraftPage,
            pagedDrafts: pagedDrafts,
            changeDraftPageSize: changeDraftPageSize,
            taskPageCount: taskPageCount,
            visibleTaskPage: visibleTaskPage,
            pagedTasks: pagedTasks,
            changeTaskPageSize: changeTaskPageSize,
            ledgerEntries: ledgerEntries,
            ledgerPageCount: ledgerPageCount,
            visibleLedgerPage: visibleLedgerPage,
            pagedLedgerEntries: pagedLedgerEntries,
            changeLedgerPageSize: changeLedgerPageSize,
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
            onCoverChange: onCoverChange,
            onSizeChartChange: onSizeChartChange,
            createTemplate: createTemplate,
            deleteTemplate: deleteTemplate,
            imageUrl: imageUrl,
            taskStatusLabel: taskStatusLabel,
            taskStatusClass: taskStatusClass,
            refreshTaskList: refreshTaskList,
            copyProviderTaskId: copyProviderTaskId,
            openTaskDetail: openTaskDetail,
            templateCoverUrl: templateCoverUrl,
            hasTemplateCover: hasTemplateCover,
            useTemplate: useTemplate,
            toggleMaterialAsset: toggleMaterialAsset,
            onMaterialDraftTemplateChange: onMaterialDraftTemplateChange,
            onMaterialDraftSizeChartChange: onMaterialDraftSizeChartChange,
            generateMaterialDraftTitle: generateMaterialDraftTitle,
            openMaterialDraftDialog: openMaterialDraftDialog,
            openTaskDraftDialog: openTaskDraftDialog,
            onTaskDraftSizeChartChange: onTaskDraftSizeChartChange,
            generateTaskDraftTitle: generateTaskDraftTitle,
            createTaskDraft: createTaskDraft,
            createDraftFromMaterialAssets: createDraftFromMaterialAssets,
            openDraftEditDialog: openDraftEditDialog,
            draftSkuForImage: draftSkuForImage,
            openImagePreview: openImagePreview,
            saveDraftEdit: saveDraftEdit,
            publishDraftToMiaoshou: publishDraftToMiaoshou,
            openClaimMaterialsDialog: openClaimMaterialsDialog,
            toggleClaimResult: toggleClaimResult,
            claimMaterials: claimMaterials,
            retryTaskResult: retryTaskResult,
            uploadMaterialAssets: uploadMaterialAssets,
            deleteSelectedMaterialAssets: deleteSelectedMaterialAssets,
            openMemberDialog: openMemberDialog,
            openMyAccountDialog: openMyAccountDialog,
            saveMyUserCode: saveMyUserCode,
            saveMember: saveMember,
            toggleMember: toggleMember,
            loadMiaoshouShops: loadMiaoshouShops,
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
