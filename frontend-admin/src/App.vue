<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001' })
const token = ref(localStorage.getItem('haitoo_admin_token') || '')
const email = ref('owner@haitoo-demo.com'), password = ref('ChangeMe123!')
const user = ref<any>(null), overview = ref<any>(null), providers = ref<any[]>([]), companies = ref<any[]>([]), ledger = ref<any[]>([])
const loading = ref(false), saving = ref(''), error = ref('')
const activePage = ref<'overview' | 'companies' | 'models'>('overview')
const showCompanyForm = ref(false), selectedCompanyId = ref<number | null>(null)
const showMiaoshouForm = ref(false), miaoshouCompany = ref<any>(null)
const companyForm = ref({ name: '', admin_name: '', admin_email: '', admin_password: '', initial_points: 0 })
const rechargeForm = ref({ company_id: null as number | null, amount: null as number | null, note: '' })
const miaoshouForm = ref({ app_id: '', app_secret: '' })
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }))

async function loadAdmin() {
  const h = { headers: headers.value }
  const [me, stats, models, companyRows] = await Promise.all([api.get('/me', h), api.get('/admin/overview', h), api.get('/admin/ai-providers', h), api.get('/admin/companies', h)])
  if (me.data.user.role !== 'super_admin') throw new Error('该账号不是超级管理员')
  user.value = me.data.user; overview.value = stats.data; providers.value = models.data; companies.value = companyRows.data
}
async function login() {
  try {
    loading.value = true; error.value = ''
    const { data } = await api.post('/auth/login', { email: email.value, password: password.value })
    token.value = data.access_token; localStorage.setItem('haitoo_admin_token', token.value)
    await loadAdmin()
  } catch (e: any) {
    localStorage.removeItem('haitoo_admin_token'); token.value = ''
    error.value = e.response?.data?.detail || e.message || '登录失败，请使用超级管理员账号'
  } finally { loading.value = false }
}
async function saveProvider(provider: any) {
  try {
    saving.value = provider.provider; error.value = ''
    await api.put(`/admin/ai-providers/${provider.provider}`, { model: provider.model, enabled: provider.enabled, is_default: provider.is_default }, { headers: headers.value })
    await loadAdmin()
  } catch (e: any) { error.value = e.response?.data?.detail || '保存失败' }
  finally { saving.value = '' }
}
async function setDefault(provider: any) {
  providers.value.forEach(item => item.is_default = item.provider === provider.provider)
  await saveProvider(provider)
}
async function createCompany() { if (companyForm.value.admin_password.length < 8) { error.value = '公司管理员密码至少需要 8 个字符'; return } try { saving.value = 'company'; error.value = ''; await api.post('/admin/companies', companyForm.value, { headers: headers.value }); companyForm.value = { name: '', admin_name: '', admin_email: '', admin_password: '', initial_points: 0 }; showCompanyForm.value = false; await loadAdmin() } catch (e: any) { error.value = e.response?.data?.detail || '创建公司失败' } finally { saving.value = '' } }
async function recharge() { if (!rechargeForm.value.company_id || !rechargeForm.value.amount || !rechargeForm.value.note.trim()) return; try { saving.value = 'recharge'; error.value = ''; await api.post('/points/recharge', { ...rechargeForm.value, note: rechargeForm.value.note.trim() }, { headers: headers.value }); rechargeForm.value = { company_id: rechargeForm.value.company_id, amount: null, note: '' }; await loadAdmin(); await loadLedger(rechargeForm.value.company_id!) } catch (e: any) { error.value = e.response?.data?.detail || '充值失败' } finally { saving.value = '' } }
async function loadLedger(companyId: number) { selectedCompanyId.value = companyId; rechargeForm.value.company_id = companyId; ledger.value = (await api.get('/admin/points/ledger', { params: { company_id: companyId }, headers: headers.value })).data }
function openMiaoshou(company: any) { miaoshouCompany.value = company; miaoshouForm.value = { app_id: '', app_secret: '' }; showMiaoshouForm.value = true }
async function saveMiaoshou() { if (!miaoshouCompany.value || !miaoshouForm.value.app_id.trim() || !miaoshouForm.value.app_secret.trim()) return; try { saving.value = 'miaoshou'; error.value = ''; await api.put(`/admin/companies/${miaoshouCompany.value.id}/miaoshou-account`, miaoshouForm.value, { headers: headers.value }); showMiaoshouForm.value = false; await loadAdmin() } catch (e: any) { error.value = e.response?.data?.detail || '保存妙手账号失败' } finally { saving.value = '' } }
function logout() { localStorage.removeItem('haitoo_admin_token'); token.value = ''; user.value = null; overview.value = null; providers.value = []; companies.value = []; ledger.value = [] }
onMounted(() => token.value && loadAdmin().catch(logout))
</script>

<template>
  <main v-if="!token" class="login-page">
    <section class="login-card"><div class="mark">H</div><p class="eyebrow">HAITOO PLATFORM</p><h1>超级管理员后台</h1><p>管理平台运行概况和印花贴合模型。</p><label>邮箱<input v-model="email" type="email" /></label><label>密码<input v-model="password" type="password" @keyup.enter="login" /></label><button class="primary" :disabled="loading" @click="login">{{ loading ? '登录中…' : '登录后台' }}</button><small>仅超级管理员可访问</small><p v-if="error" class="error">{{ error }}</p></section>
  </main>
  <main v-else class="shell">
    <aside><div class="brand"><span>H</span> HAITOO</div><p>平台后台</p><nav><button :class="{active:activePage==='overview'}" @click="activePage='overview'">概览</button><button :class="{active:activePage==='companies'}" @click="activePage='companies'">公司管理</button><button :class="{active:activePage==='models'}" @click="activePage='models'">模型管理</button></nav><div class="operator"><b>{{ user?.name }}</b><small>超级管理员</small><button @click="logout">退出登录</button></div></aside>
    <section class="content"><header><div><p class="eyebrow">PLATFORM ADMIN</p><h1>{{activePage==='overview'?'平台概览':activePage==='companies'?'公司管理':'模型管理'}}</h1></div><button class="refresh" @click="loadAdmin">↻ 刷新数据</button></header>
      <section class="page"><template v-if="activePage==='overview'"><div class="metrics"><article><span>公司</span><b>{{ overview?.companies ?? 0 }}</b><small>已开通企业</small></article><article><span>店铺</span><b>{{ overview?.shops ?? 0 }}</b><small>已授权店铺</small></article><article><span>平台用户</span><b>{{ overview?.users ?? 0 }}</b><small>含平台管理员</small></article><article><span>进行中任务</span><b>{{ overview?.running_tasks ?? 0 }}</b><small>累计 {{ overview?.tasks ?? 0 }} 个任务</small></article></div><section class="panel overview-note"><h2>管理入口</h2><p>在“公司管理”中开通公司、充值及查询积分流水；在“模型管理”中切换印花贴合模型。</p></section></template>
        <template v-else-if="activePage==='companies'"><section class="panel companies"><div class="heading heading-actions"><div><h2>公司与账号</h2><p>公司级妙手账号用于同步店铺并通过妙手 API 上架商品。</p></div><button class="primary compact" @click="showCompanyForm=true">＋ 开通公司</button></div><div class="company-table"><div class="company-head"><span>公司</span><span>管理员账号</span><span>妙手账号</span><span>可用 / 冻结积分</span><span>操作</span></div><div v-for="company in companies" :key="company.id" class="company-row"><span><b>{{company.name}}</b><small>#{{company.id}} · {{new Date(company.created_at).toLocaleDateString()}}</small></span><span><template v-for="admin in company.admin_users" :key="admin.id"><b>{{admin.name}}</b><small>{{admin.email}}</small></template><small v-if="!company.admin_users.length">未配置管理员</small></span><span :class="company.miaoshou_configured?'ok':'bad'">{{company.miaoshou_configured?'已配置':'待配置'}}</span><span><b>{{company.points.available}}</b> / {{company.points.frozen}}</span><span class="company-actions"><button class="secondary" @click="openMiaoshou(company)">妙手账号</button><button class="secondary" @click="loadLedger(company.id)">积分管理</button></span></div></div></section><section v-if="selectedCompanyId" class="panel points-panel"><div class="heading"><div><h2>积分管理 · {{companies.find(c=>c.id===selectedCompanyId)?.name}}</h2><p>充值会立即写入公司积分流水。</p></div></div><div class="recharge-form"><label>充值积分<input v-model.number="rechargeForm.amount" type="number" min="1" placeholder="请输入积分" /></label><label>备注<input v-model="rechargeForm.note" maxlength="255" placeholder="例如：2026 年 8 月运营额度" /></label><button class="primary compact" :disabled="saving==='recharge'" @click="recharge">{{saving==='recharge'?'充值中…':'确认充值'}}</button></div><div class="ledger"><div class="ledger-head"><span>时间</span><span>类型 / 备注</span><span>变动</span><span>余额</span></div><div v-for="row in ledger" :key="row.id" class="ledger-row"><span>{{new Date(row.created_at).toLocaleString()}}</span><span><b>{{row.entry_type}}</b><small>{{row.note}}</small></span><strong :class="row.amount>0?'ok':'bad'">{{row.amount>0?'+':''}}{{row.amount}}</strong><span>{{row.balance_after}}</span></div><p v-if="!ledger.length" class="empty">暂无积分流水。</p></div></section></template>
        <section v-else class="panel"><div class="heading"><div><h2>印花贴合模型</h2><p>新建任务使用默认且已启用的模型。密钥仅由部署环境配置。</p></div></div><article v-for="provider in providers" :key="provider.provider" class="provider"><div class="provider-title"><h3>{{ provider.display_name }} <em v-if="provider.is_default">默认模型</em></h3><p>{{ provider.provider === 'seedream' ? 'SEEDREAM_API_KEY' : 'QWEN_API_KEY' }} · <strong :class="overview?.credential_status?.[provider.provider] ? 'ok' : 'bad'">{{ overview?.credential_status?.[provider.provider] ? '密钥已配置' : '未配置密钥' }}</strong></p></div><label>模型标识<input v-model="provider.model" maxlength="120" /></label><label class="switch"><input v-model="provider.enabled" type="checkbox" /> 启用</label><button class="secondary" :disabled="!provider.enabled || provider.is_default || saving" @click="setDefault(provider)">设为默认</button><button class="primary compact" :disabled="!!saving" @click="saveProvider(provider)">{{saving === provider.provider ? '保存中…' : '保存'}}</button></article><p v-if="!overview?.credential_status?.public_media_base_url" class="notice">需要配置 <code>PUBLIC_MEDIA_BASE_URL</code>。未配置时，模型服务无法读取模板与印花图片，任务将失败并自动退款。</p></section>
        <p v-if="error" class="error banner">{{ error }}</p>
      </section>
    </section>
  </main>
  <div v-if="showCompanyForm" class="modal-backdrop" @click.self="showCompanyForm=false"><section class="modal"><button class="close" @click="showCompanyForm=false">×</button><h2>开通公司</h2><p>创建公司、管理员账号和积分账户。</p><p v-if="error" class="error">{{error}}</p><label>公司名称<input v-model="companyForm.name" maxlength="120" required /></label><label>管理员姓名<input v-model="companyForm.admin_name" maxlength="80" required /></label><label>管理员邮箱<input v-model="companyForm.admin_email" type="email" required /></label><label>初始密码<input v-model="companyForm.admin_password" type="password" minlength="8" placeholder="至少 8 个字符" required /><small>至少 8 个字符</small></label><label>初始积分<input v-model.number="companyForm.initial_points" type="number" min="0" /></label><button class="primary" :disabled="saving==='company'" @click="createCompany">{{saving==='company'?'开通中…':'确认开通'}}</button></section></div>
  <div v-if="showMiaoshouForm" class="modal-backdrop" @click.self="showMiaoshouForm=false"><section class="modal"><button class="close" @click="showMiaoshouForm=false">×</button><h2>配置妙手账号</h2><p>{{miaoshouCompany?.name}} 的 App ID 和 App Secret 会加密保存，店铺同步和商品上架均使用此账号。</p><label>App ID<input v-model="miaoshouForm.app_id" maxlength="255" /></label><label>App Secret<input v-model="miaoshouForm.app_secret" type="password" maxlength="500" /></label><button class="primary" :disabled="saving==='miaoshou'" @click="saveMiaoshou">{{saving==='miaoshou'?'保存中…':'安全保存'}}</button></section></div>
</template>
