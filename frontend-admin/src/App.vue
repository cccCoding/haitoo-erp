<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001' })
const token = ref(localStorage.getItem('haitoro_admin_token') || '')
const email = ref('owner@haitoro-demo.com'), password = ref('ChangeMe123!')
const user = ref<any>(null), overview = ref<any>(null), providers = ref<any[]>([]), companies = ref<any[]>([])
const loading = ref(false), saving = ref(''), error = ref('')
const toast = ref('')
const activePage = ref<'overview' | 'companies' | 'models'>('overview')
const showCompanyForm = ref(false)
const showMiaoshouForm = ref(false), miaoshouCompany = ref<any>(null)
const showProviderForm = ref(false)
const companyForm = ref({ name: '', admin_name: '', admin_email: '', admin_password: '' })
const miaoshouForm = ref({ app_id: '', app_secret: '' })
const providerForm = ref({ provider: '', display_name: '', model: '', enabled: false, is_default: false, batch_size: 1, max_concurrency: 1 })
const headers = computed(() => ({ Authorization: `Bearer ${token.value}` }))
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
    token.value = data.access_token; localStorage.setItem('haitoro_admin_token', token.value)
    await loadAdmin()
  } catch (e: any) {
    localStorage.removeItem('haitoro_admin_token'); token.value = ''
    error.value = e.response?.data?.detail || e.message || '登录失败，请使用超级管理员账号'
  } finally { loading.value = false }
}
async function saveProvider(provider: any) {
  try {
    saving.value = provider.provider; error.value = ''
    await api.put(`/admin/ai-providers/${provider.provider}`, { model: provider.model, enabled: provider.enabled, is_default: provider.is_default, batch_size: provider.batch_size, max_concurrency: provider.max_concurrency }, { headers: headers.value })
    await loadAdmin()
  } catch (e: any) { error.value = e.response?.data?.detail || '保存失败' }
  finally { saving.value = '' }
}
async function setDefault(provider: any) {
  providers.value.forEach(item => item.is_default = item.provider === provider.provider)
  await saveProvider(provider)
}
function openProviderForm(provider: any) { error.value = ''; providerForm.value = { provider: provider.provider, display_name: provider.display_name, model: provider.model, enabled: provider.enabled, is_default: provider.is_default, batch_size: provider.batch_size, max_concurrency: provider.max_concurrency }; showProviderForm.value = true }
async function saveProviderForm() { try { saving.value = providerForm.value.provider; error.value = ''; await api.put(`/admin/ai-providers/${providerForm.value.provider}`, { model: providerForm.value.model, enabled: providerForm.value.enabled, is_default: providerForm.value.is_default, batch_size: providerForm.value.batch_size, max_concurrency: providerForm.value.max_concurrency }, { headers: headers.value }); showProviderForm.value = false; await loadAdmin(); showToast('模型配置已保存') } catch (e: any) { error.value = e.response?.data?.detail || '保存失败' } finally { saving.value = '' } }
async function createCompany() { if (companyForm.value.admin_password.length < 8) { error.value = '公司管理员密码至少需要 8 个字符'; return } try { saving.value = 'company'; error.value = ''; await api.post('/admin/companies', companyForm.value, { headers: headers.value }); companyForm.value = { name: '', admin_name: '', admin_email: '', admin_password: '' }; showCompanyForm.value = false; await loadAdmin() } catch (e: any) { error.value = e.response?.data?.detail || '创建公司失败' } finally { saving.value = '' } }
function openMiaoshou(company: any) { miaoshouCompany.value = company; miaoshouForm.value = { app_id: '', app_secret: '' }; showMiaoshouForm.value = true }
async function saveMiaoshou() { if (!miaoshouCompany.value || !miaoshouForm.value.app_id.trim() || !miaoshouForm.value.app_secret.trim()) return; try { saving.value = 'miaoshou'; error.value = ''; await api.put(`/admin/companies/${miaoshouCompany.value.id}/miaoshou-account`, miaoshouForm.value, { headers: headers.value }); showMiaoshouForm.value = false; await loadAdmin() } catch (e: any) { error.value = e.response?.data?.detail || '保存妙手账号失败' } finally { saving.value = '' } }
let toastTimer: ReturnType<typeof setTimeout> | undefined
function showToast(message: string) { toast.value = message; if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = '' }, 3000) }
function logout() { localStorage.removeItem('haitoro_admin_token'); token.value = ''; user.value = null; overview.value = null; providers.value = []; companies.value = [] }
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
onMounted(() => token.value && loadAdmin().catch(logout))
</script>

<template>
  <main v-if="!token" class="login-page">
    <section class="login-card"><div class="mark">H</div><p class="eyebrow">Haitoro PLATFORM</p><h1>超级管理员后台</h1><p>管理平台运行概况和印花贴合模型。</p><label>邮箱<input v-model="email" type="email" /></label><label>密码<input v-model="password" type="password" @keyup.enter="login" /></label><button class="primary" :disabled="loading" @click="login">{{ loading ? '登录中…' : '登录后台' }}</button><small>仅超级管理员可访问</small><p v-if="error" class="error">{{ error }}</p></section>
  </main>
  <main v-else class="shell">
    <aside><div class="brand"><span>H</span> Haitoro</div><p>平台后台</p><nav><button :class="{active:activePage==='overview'}" @click="activePage='overview'">概览</button><button :class="{active:activePage==='companies'}" @click="activePage='companies'">公司管理</button><button :class="{active:activePage==='models'}" @click="activePage='models'">模型管理</button></nav><div class="operator"><b>{{ user?.name }}</b><small>超级管理员</small><button @click="logout">退出登录</button></div></aside>
    <section class="content"><header><div><p class="eyebrow">PLATFORM ADMIN</p><h1>{{activePage==='overview'?'平台概览':activePage==='companies'?'公司管理':'模型管理'}}</h1></div><button class="refresh" @click="loadAdmin">↻ 刷新数据</button></header>
      <section class="page"><template v-if="activePage==='overview'"><div class="metrics"><article><span>公司</span><b>{{ overview?.companies ?? 0 }}</b><small>已开通企业</small></article><article><span>店铺</span><b>{{ overview?.shops ?? 0 }}</b><small>已授权店铺</small></article><article><span>平台用户</span><b>{{ overview?.users ?? 0 }}</b><small>含平台管理员</small></article><article><span>进行中任务</span><b>{{ overview?.running_tasks ?? 0 }}</b><small>累计 {{ overview?.tasks ?? 0 }} 个任务</small></article></div><section class="panel queue-health" :class="{'queue-alert':overview?.queue?.alert}"><div class="heading"><div><h2>印花批次队列</h2><p>告警阈值：待处理超过 200 批、最早等待超过 10 分钟，或近 15 分钟失败率超过 10%。</p></div><span class="queue-health-state">{{overview?.queue?.alert?'需要关注':'运行正常'}}</span></div><div class="queue-metrics"><article><span>待处理</span><b>{{overview?.queue?.queued ?? 0}}</b><small>其中重试 {{overview?.queue?.retrying ?? 0}} 批</small></article><article><span>运行中</span><b>{{overview?.queue?.running ?? 0}}</b><small>最早等待 {{overview?.queue?.oldest_wait_minutes ?? 0}} 分钟</small></article><article><span>近 1 小时吞吐</span><b>{{overview?.queue?.completed_prints_last_hour ?? 0}}</b><small>{{overview?.queue?.completed_batches_last_hour ?? 0}} 批印花</small></article><article><span>近 15 分钟失败率</span><b>{{overview?.queue?.failure_rate_15m ?? 0}}%</b><small>近 1 小时最终失败 {{overview?.queue?.failed_batches_last_hour ?? 0}} 批</small></article></div><div class="queue-model-table"><div class="queue-model-head"><span>平台</span><span>模型</span><span>待处理</span><span>运行中</span><span>最终失败</span></div><div v-for="item in overview?.queue?.model_backlog || []" :key="`${item.provider}-${item.model}`" class="queue-model-row"><b>{{item.provider}}</b><code>{{item.model}}</code><span>{{item.queued}}</span><span>{{item.running}}</span><span :class="item.failed?'bad':''">{{item.failed}}</span></div><p v-if="!(overview?.queue?.model_backlog?.length)" class="queue-empty">当前没有积压或失败批次。</p></div></section><section class="panel overview-note"><h2>管理入口</h2><p>在“公司管理”中开通公司并配置妙手账号；在“模型管理”中切换印花贴合模型。</p></section></template>
        <template v-else-if="activePage==='companies'"><section class="panel companies"><div class="heading heading-actions"><div><h2>公司与账号</h2><p>公司级妙手账号用于同步店铺并通过妙手 API 上架商品。</p></div><button class="primary compact" @click="showCompanyForm=true">＋ 开通公司</button></div><div class="company-table"><div class="company-head"><span>ID</span><span>公司</span><span>管理员账号</span><span>妙手 API Key</span><span>开通时间</span><span>操作</span></div><div v-for="company in companies" :key="company.id" class="company-row"><span>{{company.id}}</span><span><b>{{company.name}}</b></span><span><template v-for="admin in company.admin_users" :key="admin.id"><b>{{admin.name}}</b><small>{{admin.email}}</small></template><small v-if="!company.admin_users.length">未配置管理员</small></span><span :class="company.miaoshou_configured?'ok':'bad'">{{company.miaoshou_configured?'已配置':'待配置'}}</span><span>{{new Date(company.created_at).toLocaleDateString()}}</span><span class="company-actions"><button class="secondary" @click="openMiaoshou(company)">妙手 API Key</button></span></div></div></section></template>
        <section v-else class="panel model-panel">
          <div class="heading model-heading"><div><p class="section-kicker">AI CONFIGURATION</p><h2>印花贴合模型</h2><p>按模型配置请求规模与处理速度。修改后请单独保存对应模型。</p></div><div class="concurrency-legend"><b>什么是模型最大并发？</b><span>同一时刻允许该模型处理的 API 批次数；设为 2，代表最多同时跑 2 批任务。</span></div></div>
          <div class="provider-list"><div class="provider-list-head"><span>平台</span><span>模型标识</span><span>单次请求</span><span>最大并发</span><span>密钥状态</span><span>启用状态</span><span>操作</span></div><article v-for="provider in providers" :key="provider.provider" class="provider-row"><div><div class="provider-platform-name"><em v-if="provider.is_default">默认</em><b>{{ provider.display_name }}</b></div><small>{{ provider.credential_env || '未定义环境变量' }}</small></div><code>{{ provider.model }}</code><span>{{ provider.batch_size }} 张图</span><span>{{ provider.max_concurrency }} 批</span><span class="credential-status" :class="overview?.credential_status?.[provider.provider] ? 'is-ready' : 'is-missing'">{{ overview?.credential_status?.[provider.provider] ? '密钥就绪' : '缺少密钥' }}</span><div class="provider-enabled"><span :class="provider.enabled ? 'ok' : 'bad'">{{ provider.enabled ? '已启用' : '已停用' }}</span></div><div class="provider-row-actions"><button class="secondary" :disabled="!provider.enabled || provider.is_default || saving" @click="setDefault(provider)">设为默认</button><button class="primary compact" @click="openProviderForm(provider)">修改</button></div></article></div>
          <p v-if="!overview?.credential_status?.r2" class="notice">需要配置 R2 存储凭据和 <code>R2_PUBLIC_BASE_URL</code>。未配置时，图片无法上传，AI 任务将失败。</p>
        </section>
        <p v-if="error" class="error banner">{{ error }}</p>
      </section>
    </section>
  </main>
  <div v-if="showCompanyForm" class="modal-backdrop" @click.self="showCompanyForm=false"><section class="modal"><button class="close" @click="showCompanyForm=false">×</button><h2>开通公司</h2><p>创建公司和管理员账号。</p><p v-if="error" class="error">{{error}}</p><label>公司名称<input v-model="companyForm.name" maxlength="120" required /></label><label>管理员姓名<input v-model="companyForm.admin_name" maxlength="80" required /></label><label>管理员邮箱<input v-model="companyForm.admin_email" type="email" required /></label><label>初始密码<input v-model="companyForm.admin_password" type="password" minlength="8" placeholder="至少 8 个字符" required /><small>至少 8 个字符</small></label><button class="primary" :disabled="saving==='company'" @click="createCompany">{{saving==='company'?'开通中…':'确认开通'}}</button></section></div>
  <div v-if="showMiaoshouForm" class="modal-backdrop" @click.self="showMiaoshouForm=false"><section class="modal"><button class="close" @click="showMiaoshouForm=false">×</button><h2>配置妙手 API Key</h2><p>{{miaoshouCompany?.name}} 的 App ID 和 App Secret 会加密保存，店铺同步和商品上架均使用此 API Key。</p><label>App ID<input v-model="miaoshouForm.app_id" maxlength="255" /></label><label>App Secret<input v-model="miaoshouForm.app_secret" type="password" maxlength="500" /></label><button class="primary" :disabled="saving==='miaoshou'" @click="saveMiaoshou">{{saving==='miaoshou'?'保存中…':'安全保存'}}</button></section></div>
  <div v-if="showProviderForm" class="modal-backdrop" @click.self="showProviderForm=false"><section class="modal provider-modal"><button class="close" @click="showProviderForm=false">×</button><p class="section-kicker">模型配置</p><h2>修改 {{ providerForm.display_name }}</h2><p>调整前请确认服务商的并发与限流额度。取消不会保存任何改动。</p><label>模型标识<input v-model="providerForm.model" maxlength="120" placeholder="输入服务商提供的模型 ID" /></label><div class="modal-field-grid"><label>单次 API 印花图数量<input v-model.number="providerForm.batch_size" type="number" min="1" max="100" /><small>每个请求内处理的图片数。</small></label><label>模型最大并发<input v-model.number="providerForm.max_concurrency" type="number" min="1" max="32" /><small>同一时刻允许处理的批次数。</small></label></div><div class="modal-tip"><b>结果映射要求</b><span>只有服务商明确保证输出顺序与输入印花一致时才能设为大于 1；不确定时必须保持 1，避免结果关联错图。</span></div><div class="modal-tip"><b>并发示例</b><span>设为 2，表示该模型最多同时运行 2 批 API 请求；不确定时建议设为 1。</span></div><label class="modal-switch"><input v-model="providerForm.enabled" type="checkbox" /> 启用此模型</label><div class="modal-actions"><button class="secondary" :disabled="saving===providerForm.provider" @click="showProviderForm=false">取消</button><button class="primary" :disabled="saving===providerForm.provider" @click="saveProviderForm">{{saving===providerForm.provider?'保存中…':'保存修改'}}</button></div></section></div>
  <div v-if="toast" class="toast" role="alert" style="position:fixed;top:24px;left:50%;z-index:1000;transform:translateX(-50%);padding:12px 18px;border-radius:10px;background:#1e4a92;color:#fff;box-shadow:0 10px 28px #1e4a9240;font-size:14px">{{ toast }}</div>
</template>
