import { computed, onMounted, ref } from 'vue';
import axios from 'axios';
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001' });
const token = ref(localStorage.getItem('haitoo_admin_token') || '');
const email = ref('owner@haitoo-demo.com'), password = ref('ChangeMe123!');
const user = ref(null), overview = ref(null), providers = ref([]), companies = ref([]), ledger = ref([]), nonAiPointRules = ref([]);
const loading = ref(false), saving = ref(''), error = ref('');
const activePage = ref('overview');
const showCompanyForm = ref(false), selectedCompanyId = ref(null);
const showMiaoshouForm = ref(false), miaoshouCompany = ref(null);
const showRuleForm = ref(false), editingRule = ref(null);
const pointConfigTab = ref('non-ai');
const companyForm = ref({ name: '', admin_name: '', admin_email: '', admin_password: '', initial_points: 0 });
const rechargeForm = ref({ company_id: null, amount: null, note: '' });
const miaoshouForm = ref({ app_id: '', app_secret: '' });
const ruleForm = ref({ operation_code: '', display_name: '', points: 0, enabled: true, description: '' });
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }));
async function loadAdmin() {
    const h = { headers: headers.value };
    const [me, stats, models, companyRows, rules] = await Promise.all([api.get('/me', h), api.get('/admin/overview', h), api.get('/admin/ai-providers', h), api.get('/admin/companies', h), api.get('/admin/non-ai-point-rules', h)]);
    if (me.data.user.role !== 'super_admin')
        throw new Error('该账号不是超级管理员');
    user.value = me.data.user;
    overview.value = stats.data;
    providers.value = models.data;
    companies.value = companyRows.data;
    nonAiPointRules.value = rules.data;
}
async function login() {
    try {
        loading.value = true;
        error.value = '';
        const { data } = await api.post('/auth/login', { email: email.value, password: password.value });
        token.value = data.access_token;
        localStorage.setItem('haitoo_admin_token', token.value);
        await loadAdmin();
    }
    catch (e) {
        localStorage.removeItem('haitoo_admin_token');
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
        await api.put(`/admin/ai-providers/${provider.provider}`, { model: provider.model, enabled: provider.enabled, is_default: provider.is_default }, { headers: headers.value });
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
async function createCompany() { if (companyForm.value.admin_password.length < 8) {
    error.value = '公司管理员密码至少需要 8 个字符';
    return;
} try {
    saving.value = 'company';
    error.value = '';
    await api.post('/admin/companies', companyForm.value, { headers: headers.value });
    companyForm.value = { name: '', admin_name: '', admin_email: '', admin_password: '', initial_points: 0 };
    showCompanyForm.value = false;
    await loadAdmin();
}
catch (e) {
    error.value = e.response?.data?.detail || '创建公司失败';
}
finally {
    saving.value = '';
} }
async function recharge() { if (!rechargeForm.value.company_id || !rechargeForm.value.amount || !rechargeForm.value.note.trim())
    return; try {
    saving.value = 'recharge';
    error.value = '';
    await api.post('/points/recharge', { ...rechargeForm.value, note: rechargeForm.value.note.trim() }, { headers: headers.value });
    rechargeForm.value = { company_id: rechargeForm.value.company_id, amount: null, note: '' };
    await loadAdmin();
    await loadLedger(rechargeForm.value.company_id);
}
catch (e) {
    error.value = e.response?.data?.detail || '充值失败';
}
finally {
    saving.value = '';
} }
async function loadLedger(companyId) { selectedCompanyId.value = companyId; rechargeForm.value.company_id = companyId; ledger.value = (await api.get('/admin/points/ledger', { params: { company_id: companyId }, headers: headers.value })).data; }
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
function openRuleForm(rule) { editingRule.value = rule || null; ruleForm.value = { operation_code: rule?.operation_code || '', display_name: rule?.display_name || '', points: rule?.points ?? 0, enabled: rule?.enabled ?? true, description: rule?.description || '' }; showRuleForm.value = true; }
async function saveRule() { if (!ruleForm.value.display_name.trim() || (!editingRule.value && !ruleForm.value.operation_code.trim()))
    return; try {
    saving.value = 'rule';
    error.value = '';
    const payload = { ...ruleForm.value, operation_code: ruleForm.value.operation_code.trim(), display_name: ruleForm.value.display_name.trim(), description: ruleForm.value.description.trim() || null };
    if (editingRule.value)
        await api.put(`/admin/non-ai-point-rules/${editingRule.value.id}`, payload, { headers: headers.value });
    else
        await api.post('/admin/non-ai-point-rules', payload, { headers: headers.value });
    showRuleForm.value = false;
    await loadAdmin();
}
catch (e) {
    error.value = e.response?.data?.detail || '保存积分消耗配置失败';
}
finally {
    saving.value = '';
} }
async function deleteRule(rule) { if (!confirm(`确定删除「${rule.display_name}」吗？`))
    return; try {
    saving.value = `delete-${rule.id}`;
    error.value = '';
    await api.delete(`/admin/non-ai-point-rules/${rule.id}`, { headers: headers.value });
    await loadAdmin();
}
catch (e) {
    error.value = e.response?.data?.detail || '删除积分消耗配置失败';
}
finally {
    saving.value = '';
} }
function logout() { localStorage.removeItem('haitoo_admin_token'); token.value = ''; user.value = null; overview.value = null; providers.value = []; companies.value = []; ledger.value = []; nonAiPointRules.value = []; }
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(!__VLS_ctx.token))
                    return;
                __VLS_ctx.activePage = 'non-ai-points';
            } },
        ...{ class: ({ active: __VLS_ctx.activePage === 'non-ai-points' }) },
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
    (__VLS_ctx.activePage === 'overview' ? '平台概览' : __VLS_ctx.activePage === 'companies' ? '公司管理' : __VLS_ctx.activePage === 'models' ? '模型管理' : '积分配置');
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
        for (const [company] of __VLS_getVForSourceType((__VLS_ctx.companies))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (company.id),
                ...{ class: "company-row" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (company.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (company.id);
            (new Date(company.created_at).toLocaleDateString());
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
            (company.points.available);
            (company.points.frozen);
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.activePage === 'overview'))
                            return;
                        if (!(__VLS_ctx.activePage === 'companies'))
                            return;
                        __VLS_ctx.loadLedger(company.id);
                    } },
                ...{ class: "secondary" },
            });
        }
        if (__VLS_ctx.selectedCompanyId) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: "panel points-panel" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.companies.find(c => c.id === __VLS_ctx.selectedCompanyId)?.name);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "recharge-form" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "number",
                min: "1",
                placeholder: "请输入积分",
            });
            (__VLS_ctx.rechargeForm.amount);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                maxlength: "255",
                placeholder: "例如：2026 年 8 月运营额度",
            });
            (__VLS_ctx.rechargeForm.note);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.recharge) },
                ...{ class: "primary compact" },
                disabled: (__VLS_ctx.saving === 'recharge'),
            });
            (__VLS_ctx.saving === 'recharge' ? '充值中…' : '确认充值');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "ledger" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "ledger-head" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.ledger))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (row.id),
                    ...{ class: "ledger-row" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (new Date(row.created_at).toLocaleString());
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (row.entry_type);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (row.note);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({
                    ...{ class: (row.amount > 0 ? 'ok' : 'bad') },
                });
                (row.amount > 0 ? '+' : '');
                (row.amount);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (row.balance_after);
            }
            if (!__VLS_ctx.ledger.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
        }
    }
    else if (__VLS_ctx.activePage === 'non-ai-points') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel point-config" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "point-config-tabs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.activePage === 'overview'))
                        return;
                    if (!!(__VLS_ctx.activePage === 'companies'))
                        return;
                    if (!(__VLS_ctx.activePage === 'non-ai-points'))
                        return;
                    __VLS_ctx.pointConfigTab = 'ai';
                } },
            ...{ class: ({ active: __VLS_ctx.pointConfigTab === 'ai' }) },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(!__VLS_ctx.token))
                        return;
                    if (!!(__VLS_ctx.activePage === 'overview'))
                        return;
                    if (!!(__VLS_ctx.activePage === 'companies'))
                        return;
                    if (!(__VLS_ctx.activePage === 'non-ai-points'))
                        return;
                    __VLS_ctx.pointConfigTab = 'non-ai';
                } },
            ...{ class: ({ active: __VLS_ctx.pointConfigTab === 'non-ai' }) },
        });
        if (__VLS_ctx.pointConfigTab === 'ai') {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "heading" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: "empty" },
            });
        }
        else {
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
                        if (!!(__VLS_ctx.activePage === 'companies'))
                            return;
                        if (!(__VLS_ctx.activePage === 'non-ai-points'))
                            return;
                        if (!!(__VLS_ctx.pointConfigTab === 'ai'))
                            return;
                        __VLS_ctx.openRuleForm();
                    } },
                ...{ class: "primary compact" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "rule-table" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "rule-head" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [rule] of __VLS_getVForSourceType((__VLS_ctx.nonAiPointRules))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (rule.id),
                    ...{ class: "rule-row" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.b, __VLS_intrinsicElements.b)({});
                (rule.display_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (rule.operation_code);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (rule.points);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: (rule.enabled ? 'ok' : 'bad') },
                });
                (rule.enabled ? '启用' : '停用');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "rule-description" },
                });
                (rule.description || '—');
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "company-actions" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.activePage === 'overview'))
                                return;
                            if (!!(__VLS_ctx.activePage === 'companies'))
                                return;
                            if (!(__VLS_ctx.activePage === 'non-ai-points'))
                                return;
                            if (!!(__VLS_ctx.pointConfigTab === 'ai'))
                                return;
                            __VLS_ctx.openRuleForm(rule);
                        } },
                    ...{ class: "secondary" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(!__VLS_ctx.token))
                                return;
                            if (!!(__VLS_ctx.activePage === 'overview'))
                                return;
                            if (!!(__VLS_ctx.activePage === 'companies'))
                                return;
                            if (!(__VLS_ctx.activePage === 'non-ai-points'))
                                return;
                            if (!!(__VLS_ctx.pointConfigTab === 'ai'))
                                return;
                            __VLS_ctx.deleteRule(rule);
                        } },
                    ...{ class: "secondary delete" },
                    disabled: (__VLS_ctx.saving === `delete-${rule.id}`),
                });
            }
            if (!__VLS_ctx.nonAiPointRules.length) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: "empty" },
                });
            }
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: "panel" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "heading" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        for (const [provider] of __VLS_getVForSourceType((__VLS_ctx.providers))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: (provider.provider),
                ...{ class: "provider" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "provider-title" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            (provider.display_name);
            if (provider.is_default) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.em, __VLS_intrinsicElements.em)({});
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (provider.provider === 'seedream' ? 'SEEDREAM_API_KEY' : 'QWEN_API_KEY');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({
                ...{ class: (__VLS_ctx.overview?.credential_status?.[provider.provider] ? 'ok' : 'bad') },
            });
            (__VLS_ctx.overview?.credential_status?.[provider.provider] ? '密钥已配置' : '未配置密钥');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                maxlength: "120",
            });
            (provider.model);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                ...{ class: "switch" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
                type: "checkbox",
            });
            (provider.enabled);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(!__VLS_ctx.token))
                            return;
                        if (!!(__VLS_ctx.activePage === 'overview'))
                            return;
                        if (!!(__VLS_ctx.activePage === 'companies'))
                            return;
                        if (!!(__VLS_ctx.activePage === 'non-ai-points'))
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
                        if (!!(__VLS_ctx.activePage === 'non-ai-points'))
                            return;
                        __VLS_ctx.saveProvider(provider);
                    } },
                ...{ class: "primary compact" },
                disabled: (!!__VLS_ctx.saving),
            });
            (__VLS_ctx.saving === provider.provider ? '保存中…' : '保存');
        }
        if (!__VLS_ctx.overview?.credential_status?.public_media_base_url) {
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
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "number",
        min: "0",
    });
    (__VLS_ctx.companyForm.initial_points);
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
if (__VLS_ctx.showRuleForm) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showRuleForm))
                    return;
                __VLS_ctx.showRuleForm = false;
            } },
        ...{ class: "modal-backdrop" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: "modal" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.showRuleForm))
                    return;
                __VLS_ctx.showRuleForm = false;
            } },
        ...{ class: "close" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.editingRule ? '编辑' : '新增');
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "120",
        placeholder: "例如：发布商品",
    });
    (__VLS_ctx.ruleForm.display_name);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "80",
        disabled: (!!__VLS_ctx.editingRule),
        placeholder: "例如：product_publish",
    });
    (__VLS_ctx.ruleForm.operation_code);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "number",
        min: "0",
        max: "1000000",
    });
    (__VLS_ctx.ruleForm.points);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        maxlength: "255",
        placeholder: "选填",
    });
    (__VLS_ctx.ruleForm.description);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: "modal-switch" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "checkbox",
    });
    (__VLS_ctx.ruleForm.enabled);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.saveRule) },
        ...{ class: "primary" },
        disabled: (__VLS_ctx.saving === 'rule'),
    });
    (__VLS_ctx.saving === 'rule' ? '保存中…' : '保存配置');
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
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['points-panel']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['recharge-form']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact']} */ ;
/** @type {__VLS_StyleScopedClasses['ledger']} */ ;
/** @type {__VLS_StyleScopedClasses['ledger-head']} */ ;
/** @type {__VLS_StyleScopedClasses['ledger-row']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['point-config']} */ ;
/** @type {__VLS_StyleScopedClasses['point-config-tabs']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['heading-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
/** @type {__VLS_StyleScopedClasses['compact']} */ ;
/** @type {__VLS_StyleScopedClasses['rule-table']} */ ;
/** @type {__VLS_StyleScopedClasses['rule-head']} */ ;
/** @type {__VLS_StyleScopedClasses['rule-row']} */ ;
/** @type {__VLS_StyleScopedClasses['rule-description']} */ ;
/** @type {__VLS_StyleScopedClasses['company-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['secondary']} */ ;
/** @type {__VLS_StyleScopedClasses['delete']} */ ;
/** @type {__VLS_StyleScopedClasses['empty']} */ ;
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['heading']} */ ;
/** @type {__VLS_StyleScopedClasses['provider']} */ ;
/** @type {__VLS_StyleScopedClasses['provider-title']} */ ;
/** @type {__VLS_StyleScopedClasses['switch']} */ ;
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
/** @type {__VLS_StyleScopedClasses['close']} */ ;
/** @type {__VLS_StyleScopedClasses['modal-switch']} */ ;
/** @type {__VLS_StyleScopedClasses['primary']} */ ;
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
            ledger: ledger,
            nonAiPointRules: nonAiPointRules,
            loading: loading,
            saving: saving,
            error: error,
            activePage: activePage,
            showCompanyForm: showCompanyForm,
            selectedCompanyId: selectedCompanyId,
            showMiaoshouForm: showMiaoshouForm,
            miaoshouCompany: miaoshouCompany,
            showRuleForm: showRuleForm,
            editingRule: editingRule,
            pointConfigTab: pointConfigTab,
            companyForm: companyForm,
            rechargeForm: rechargeForm,
            miaoshouForm: miaoshouForm,
            ruleForm: ruleForm,
            loadAdmin: loadAdmin,
            login: login,
            saveProvider: saveProvider,
            setDefault: setDefault,
            createCompany: createCompany,
            recharge: recharge,
            loadLedger: loadLedger,
            openMiaoshou: openMiaoshou,
            saveMiaoshou: saveMiaoshou,
            openRuleForm: openRuleForm,
            saveRule: saveRule,
            deleteRule: deleteRule,
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
