import { computed, onMounted, ref } from 'vue';
import axios from 'axios';
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001' });
const token = ref(localStorage.getItem('haitoro_admin_token') || '');
const email = ref('owner@haitoro-demo.com'), password = ref('ChangeMe123!');
const user = ref(null), overview = ref(null), providers = ref([]), companies = ref([]);
const queueSettings = ref({ submit_interval_seconds: 1, result_interval_seconds: 5 });
const loading = ref(false), saving = ref(''), error = ref('');
const toast = ref('');
const activePage = ref('overview');
const showCompanyForm = ref(false);
const showMiaoshouForm = ref(false), miaoshouCompany = ref(null);
const showProviderForm = ref(false);
const companyForm = ref({ name: '', admin_name: '', admin_email: '', admin_password: '' });
const miaoshouForm = ref({ app_id: '', app_secret: '' });
const providerForm = ref({ provider: '', display_name: '', model: '', enabled: false, is_default: false, images_per_task: 1 });
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }));
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
async function loadAdmin() {
    const h = { headers: headers.value };
    const [me, stats, models, companyRows, queue] = await Promise.all([api.get('/me', h), api.get('/admin/overview', h), api.get('/admin/ai-providers', h), api.get('/admin/companies', h), api.get('/admin/task-queue-settings', h)]);
    if (me.data.user.role !== 'super_admin')
        throw new Error('该账号不是超级管理员');
    user.value = me.data.user;
    overview.value = stats.data;
    providers.value = models.data;
    companies.value = companyRows.data;
    queueSettings.value = queue.data;
}
async function login() {
    try {
        loading.value = true;
        error.value = '';
        const { data } = await api.post('/auth/login', { email: email.value, password: password.value });
        token.value = data.access_token;
        localStorage.setItem('haitoro_admin_token', token.value);
        await loadAdmin();
    }
    catch (e) {
        localStorage.removeItem('haitoro_admin_token');
        token.value = '';
        error.value = e.response?.data?.detail || e.message || '登录失败，请使用超级管理员账号';
    }
    finally {
        loading.value = false;
    }
}
async function saveProvider(provider) {
    try {
        saving.value = provider.provider;
        error.value = '';
        await api.put(`/admin/ai-providers/${provider.provider}`, { model: provider.model, enabled: provider.enabled, is_default: provider.is_default, images_per_task: provider.images_per_task }, { headers: headers.value });
        await loadAdmin();
    }
    catch (e) {
        error.value = e.response?.data?.detail || '保存失败';
    }
    finally {
        saving.value = '';
    }
}
async function setDefault(provider) {
    providers.value.forEach(item => item.is_default = item.provider === provider.provider);
    await saveProvider(provider);
}
function openProviderForm(provider) { error.value = ''; providerForm.value = { provider: provider.provider, display_name: provider.display_name, model: provider.model, enabled: provider.enabled, is_default: provider.is_default, images_per_task: provider.images_per_task }; showProviderForm.value = true; }
async function saveProviderForm() { try {
    saving.value = providerForm.value.provider;
    error.value = '';
    await api.put(`/admin/ai-providers/${providerForm.value.provider}`, { model: providerForm.value.model, enabled: providerForm.value.enabled, is_default: providerForm.value.is_default, images_per_task: providerForm.value.images_per_task }, { headers: headers.value });
    showProviderForm.value = false;
    await loadAdmin();
    showToast('模型配置已保存');
}
catch (e) {
    error.value = e.response?.data?.detail || '保存失败';
}
finally {
    saving.value = '';
} }
async function saveQueueSettings() { try {
    saving.value = 'queue';
    error.value = '';
    await api.put('/admin/task-queue-settings', queueSettings.value, { headers: headers.value });
    await loadAdmin();
    showToast('任务间隔已保存');
}
catch (e) {
    error.value = e.response?.data?.detail || '保存失败';
}
finally {
    saving.value = '';
} }
async function createCompany() { if (companyForm.value.admin_password.length < 8) {
    error.value = '公司管理员密码至少需要 8 个字符';
    return;
} try {
    saving.value = 'company';
    error.value = '';
    await api.post('/admin/companies', companyForm.value, { headers: headers.value });
    companyForm.value = { name: '', admin_name: '', admin_email: '', admin_password: '' };
    showCompanyForm.value = false;
    await loadAdmin();
}
catch (e) {
    error.value = e.response?.data?.detail || '创建公司失败';
}
finally {
    saving.value = '';
} }
function openMiaoshou(company) { miaoshouCompany.value = company; miaoshouForm.value = { app_id: '', app_secret: '' }; showMiaoshouForm.value = true; }
async function saveMiaoshou() { if (!miaoshouCompany.value || !miaoshouForm.value.app_id.trim() || !miaoshouForm.value.app_secret.trim())
    return; try {
    saving.value = 'miaoshou';
    error.value = '';
    await api.put(`/admin/companies/${miaoshouCompany.value.id}/miaoshou-account`, miaoshouForm.value, { headers: headers.value });
    showMiaoshouForm.value = false;
    await loadAdmin();
}
catch (e) {
    error.value = e.response?.data?.detail || '保存妙手账号失败';
}
finally {
    saving.value = '';
} }
let toastTimer;
function showToast(message) { toast.value = message; if (toastTimer)
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = ''; }, 3000); }
function logout() { localStorage.removeItem('haitoro_admin_token'); token.value = ''; user.value = null; overview.value = null; providers.value = []; companies.value = []; }
api.interceptors.response.use(response => response, requestError => {
    if (requestError.response?.data?.detail === '登录已失效') {
        logout();
        showToast('登录已失效，请重新登录');
    }
    return Promise.reject(requestError);
});
onMounted(() => token.value && loadAdmin().catch(logout));
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
if (!__VLS_ctx.token) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
        ...{ class: "login-page" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "login-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "mark" },
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
        ...{ onKeyup: (__VLS_ctx.login) },
        type: "password",
    });
    (__VLS_ctx.password);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.login) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.loading),
    });
    (__VLS_ctx.loading ? '登录中…' : '登录后台');
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
        ...{ class: "shell" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "brand" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.token))
                    return;
                __VLS_ctx.activePage = 'overview';
            } },
        ...{ class: ({ active: __VLS_ctx.activePage === 'overview' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.token))
                    return;
                __VLS_ctx.activePage = 'companies';
            } },
        ...{ class: ({ active: __VLS_ctx.activePage === 'companies' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.token))
                    return;
                __VLS_ctx.activePage = 'models';
            } },
        ...{ class: ({ active: __VLS_ctx.activePage === 'models' }) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "operator" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    (__VLS_ctx.user?.name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.logout) },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "content" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "eyebrow" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
    (__VLS_ctx.activePage === 'overview' ? '平台概览' : __VLS_ctx.activePage === 'companies' ? '公司管理' : '模型管理');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.loadAdmin) },
        ...{ class: "refresh" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "page" },
    });
    if (__VLS_ctx.activePage === 'overview') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "metrics" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.companies ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.shops ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.users ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.running_tasks ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.overview?.tasks ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel queue-health" },
            ...{ class: ({ 'queue-alert': __VLS_ctx.overview?.queue?.alert }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "queue-health-state" },
        });
        (__VLS_ctx.overview?.queue?.alert ? '需要关注' : '运行正常');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "queue-metrics" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.queue?.queued ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.overview?.queue?.retrying ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.queue?.running ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.overview?.queue?.oldest_wait_minutes ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.queue?.completed_prints_last_hour ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.overview?.queue?.completed_tasks_last_hour ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
        (__VLS_ctx.overview?.queue?.failure_rate_15m ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.overview?.queue?.failed_tasks_last_hour ?? 0);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "queue-model-table" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "queue-model-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.overview?.queue?.model_backlog || []))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (`${item.provider}-${item.model}`),
                ...{ class: "queue-model-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (item.provider);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (item.model);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (item.queued);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (item.running);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: (item.failed ? 'bad' : '') },
            });
            (item.failed);
        }
        if (!(__VLS_ctx.overview?.queue?.model_backlog?.length)) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "queue-empty" },
            });
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel overview-note" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    }
    else if (__VLS_ctx.activePage === 'companies') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel companies" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "heading heading-actions" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.activePage === 'overview'))
                        return;
                    if (!(__VLS_ctx.activePage === 'companies'))
                        return;
                    __VLS_ctx.showCompanyForm = true;
                } },
            ...{ class: "primary compact" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "company-table" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "company-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [company] of __VLS_getVForSourceType((__VLS_ctx.companies))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (company.id),
                ...{ class: "company-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (company.id);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (company.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [admin] of __VLS_getVForSourceType((company.admin_users))) {
                (admin.id);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (admin.name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (admin.email);
            }
            if (!company.admin_users.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: (company.miaoshou_configured ? 'ok' : 'bad') },
            });
            (company.miaoshou_configured ? '已配置' : '待配置');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (new Date(company.created_at).toLocaleDateString());
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "company-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.activePage === 'overview'))
                            return;
                        if (!(__VLS_ctx.activePage === 'companies'))
                            return;
                        __VLS_ctx.openMiaoshou(company);
                    } },
                ...{ class: "secondary" },
            });
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel model-panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "heading model-heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "section-kicker" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "queue-setting-form" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "1",
            max: "3600",
        });
        (__VLS_ctx.queueSettings.submit_interval_seconds);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
            type: "number",
            min: "1",
            max: "3600",
        });
        (__VLS_ctx.queueSettings.result_interval_seconds);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.saveQueueSettings) },
            ...{ class: "secondary" },
            disabled: (__VLS_ctx.saving === 'queue'),
        });
        (__VLS_ctx.saving === 'queue' ? '保存中…' : '保存任务间隔');
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "provider-list" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "provider-list-head" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.providers))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (provider.provider),
                ...{ class: "provider-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "provider-platform-name" },
            });
            if (provider.is_default) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (provider.display_name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (provider.credential_env || '未定义环境变量');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (provider.model);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (provider.images_per_task);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "credential-status" },
                ...{ class: (__VLS_ctx.overview?.credential_status?.[provider.provider] ? 'is-ready' : 'is-missing') },
            });
            (__VLS_ctx.overview?.credential_status?.[provider.provider] ? '密钥就绪' : '缺少密钥');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "provider-enabled" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: (provider.enabled ? 'ok' : 'bad') },
            });
            (provider.enabled ? '已启用' : '已停用');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "provider-row-actions" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.activePage === 'overview'))
                            return;
                        if (!!(__VLS_ctx.activePage === 'companies'))
                            return;
                        __VLS_ctx.setDefault(provider);
                    } },
                ...{ class: "secondary" },
                disabled: (!provider.enabled || provider.is_default || __VLS_ctx.saving),
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.activePage === 'overview'))
                            return;
                        if (!!(__VLS_ctx.activePage === 'companies'))
                            return;
                        __VLS_ctx.openProviderForm(provider);
                    } },
                ...{ class: "primary compact" },
            });
        }
        if (!__VLS_ctx.overview?.credential_status?.r2) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "notice" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        }
    }
    if (__VLS_ctx.error) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error banner" },
        });
        (__VLS_ctx.error);
    }
}
if (__VLS_ctx.showCompanyForm) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showCompanyForm))
                    return;
                __VLS_ctx.showCompanyForm = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showCompanyForm))
                    return;
                __VLS_ctx.showCompanyForm = false;
            } },
        ...{ class: "close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    if (__VLS_ctx.error) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "error" },
        });
        (__VLS_ctx.error);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "120",
        required: true,
    });
    (__VLS_ctx.companyForm.name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "80",
        required: true,
    });
    (__VLS_ctx.companyForm.admin_name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "email",
        required: true,
    });
    (__VLS_ctx.companyForm.admin_email);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "password",
        minlength: "8",
        placeholder: "至少 8 个字符",
        required: true,
    });
    (__VLS_ctx.companyForm.admin_password);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.createCompany) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.saving === 'company'),
    });
    (__VLS_ctx.saving === 'company' ? '开通中…' : '确认开通');
}
if (__VLS_ctx.showMiaoshouForm) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouForm))
                    return;
                __VLS_ctx.showMiaoshouForm = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showMiaoshouForm))
                    return;
                __VLS_ctx.showMiaoshouForm = false;
            } },
        ...{ class: "close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.miaoshouCompany?.name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "255",
    });
    (__VLS_ctx.miaoshouForm.app_id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "password",
        maxlength: "500",
    });
    (__VLS_ctx.miaoshouForm.app_secret);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveMiaoshou) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.saving === 'miaoshou'),
    });
    (__VLS_ctx.saving === 'miaoshou' ? '保存中…' : '安全保存');
}
if (__VLS_ctx.showProviderForm) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showProviderForm))
                    return;
                __VLS_ctx.showProviderForm = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal provider-modal" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showProviderForm))
                    return;
                __VLS_ctx.showProviderForm = false;
            } },
        ...{ class: "close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "section-kicker" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.providerForm.display_name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "120",
        placeholder: "输入服务商提供的模型 ID",
    });
    (__VLS_ctx.providerForm.model);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-field-grid" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "number",
        min: "1",
        max: "100",
    });
    (__VLS_ctx.providerForm.images_per_task);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-tip" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: "modal-switch" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "checkbox",
    });
    (__VLS_ctx.providerForm.enabled);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "modal-actions" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showProviderForm))
                    return;
                __VLS_ctx.showProviderForm = false;
            } },
        ...{ class: "secondary" },
        disabled: (__VLS_ctx.saving === __VLS_ctx.providerForm.provider),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveProviderForm) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.saving === __VLS_ctx.providerForm.provider),
    });
    (__VLS_ctx.saving === __VLS_ctx.providerForm.provider ? '保存中…' : '保存修改');
}
if (__VLS_ctx.toast) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "toast" },
        role: "alert",
        ...{ style: {} },
    });
    (__VLS_ctx.toast);
}
/** @type {__VLS_StyleScopedClasses['login-page']} */ ;
/** @type {__VLS_StyleScopedClasses['login-card']} */ ;
/** @type {__VLS_StyleScopedClasses['mark']} */ ;
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['shell']} */ ;
/** @type {__VLS_StyleScopedClasses['brand']} */ ;
/** @type {__VLS_StyleScopedClasses['operator']} */ ;
/** @type {__VLS_StyleScopedClasses['content']} */ ;
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
/** @type {__VLS_StyleScopedClasses['refresh']} */ ;
/** @type {__VLS_StyleScopedClasses['page']} */ ;
/** @type {__VLS_StyleScopedClasses['metrics']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-health']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-health-state']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-metrics']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-model-table']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-model-head']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-model-row']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-empty']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['overview-note']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['companies']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact']} */ ;
/** @type {__VLS_StyleScopedClasses['company-table']} */ ;
/** @type {__VLS_StyleScopedClasses['company-head']} */ ;
/** @type {__VLS_StyleScopedClasses['company-row']} */ ;
/** @type {__VLS_StyleScopedClasses['company-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['model-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['model-heading']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['queue-setting-form']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-list']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-list-head']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-row']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-platform-name']} */ ;
/** @type {__VLS_StyleScopedClasses['credential-status']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-enabled']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-row-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact']} */ ;
/** @type {__VLS_StyleScopedClasses['notice']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['banner']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal']} */ ;
/** @type {__VLS_StyleScopedClasses['close']} */ ;
/** @type {__VLS_StyleScopedClasses['error']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal']} */ ;
/** @type {__VLS_StyleScopedClasses['close']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-backdrop']} */ ;
/** @type {__VLS_StyleScopedClasses['modal']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-modal']} */ ;
/** @type {__VLS_StyleScopedClasses['close']} */ ;
/** @type {__VLS_StyleScopedClasses['section-kicker']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-field-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-tip']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-switch']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['toast']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            token: token,
            email: email,
            password: password,
            user: user,
            overview: overview,
            providers: providers,
            companies: companies,
            queueSettings: queueSettings,
            loading: loading,
            saving: saving,
            error: error,
            toast: toast,
            activePage: activePage,
            showCompanyForm: showCompanyForm,
            showMiaoshouForm: showMiaoshouForm,
            miaoshouCompany: miaoshouCompany,
            showProviderForm: showProviderForm,
            companyForm: companyForm,
            miaoshouForm: miaoshouForm,
            providerForm: providerForm,
            loadAdmin: loadAdmin,
            login: login,
            setDefault: setDefault,
            openProviderForm: openProviderForm,
            saveProviderForm: saveProviderForm,
            saveQueueSettings: saveQueueSettings,
            createCompany: createCompany,
            openMiaoshou: openMiaoshou,
            saveMiaoshou: saveMiaoshou,
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
