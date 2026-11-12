<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'
const props = defineProps<{token: string}>()
const emit = defineEmits<{unauthorized: []}>()
const api = axios.create({baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001'})
const rows = ref<any[]>([]), manifest = ref(''), artifact = ref<File | null>(null), installer = ref<File | null>(null)
const busy = ref(false), loaded = ref(false), error = ref(''), notice = ref('')
const uploadProgress = ref('')
const testing = ref<Record<number, string>>({})
const labels: Record<string, string> = {uploading: '等待文件上传', draft: '草稿', test: '测试设备可用', stable: '稳定版', withdrawn: '已撤回'}
const auth = () => ({headers: {Authorization: `Bearer ${props.token}`}})
async function perform(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e: any) {
    if (e.response?.status === 401) emit('unauthorized')
    error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : (e.message === 'Network Error' ? '文件直传失败，请检查网络及私有存储的跨域配置，再重试。' : e.message || '请求失败，请重试')
  } finally {busy.value = false; uploadProgress.value = ''}
}
async function load() {
  rows.value = (await api.get('/admin/connector-releases', auth())).data
  for (const row of rows.value) testing.value[row.id] = row.test_agent_ids.join(', ')
  loaded.value = true
}
async function refresh() { await perform(load) }
async function upload() {
  await perform(async () => {
    if (!artifact.value || !installer.value) return
    const parsed = JSON.parse(manifest.value)
    if (installer.value.name !== parsed.installer?.filename) throw new Error('请选择与清单一致的首次安装包')
    const {data: pending} = await api.post('/admin/connector-releases/uploads', parsed, auth())
    if (pending.uploads) {
      for (const [kind, file] of [['update', artifact.value], ['installer', installer.value]] as const) {
        uploadProgress.value = kind === 'update' ? '正在上传更新包' : '正在上传安装包'
        await axios.put(pending.uploads[kind], file, {headers: {'Content-Type':'application/octet-stream'},
          onUploadProgress: event => {uploadProgress.value = `${kind === 'update' ? '更新包' : '安装包'} ${Math.round((event.loaded / (event.total || file.size)) * 100)}%`}})
      }
      uploadProgress.value = '正在校验并归档'
      await api.post(`/admin/connector-releases/${pending.id}/complete`, {}, auth())
    }
    await load(); uploadProgress.value = ''
    notice.value = '已上传为草稿。请先在测试设备验证，再开放稳定版。'
  })
}
async function change(row: any, stage: string) {
  await perform(async () => {
    const ids = (testing.value[row.id] || '').split(/[,，\s]+/).filter(Boolean).map(Number)
    if (stage === 'test' && (!ids.length || ids.some(id => !Number.isSafeInteger(id) || id <= 0))) throw new Error('请输入有效的测试设备 ID，以逗号分隔')
    await api.put(`/admin/connector-releases/${row.id}/stage`, {stage, revision: row.revision, test_agent_ids: stage === 'test' ? ids : []}, auth())
    await load(); notice.value = stage === 'withdrawn' ? '已停止此版本的新下载与更新；已安装设备保留当前版本。' : '发布状态已保存'
  })
}
onMounted(refresh)
defineExpose({refresh})
</script>
<template>
  <div class="connector-releases">
    <section class="panel">
      <div class="heading"><div><h2>连接器版本</h2><p>统一管理 Windows 与 macOS。每次上传同时包含首次安装包和完整更新包，同版本内容不可替换。</p></div><button class="secondary" :disabled="busy" @click="refresh">{{busy?'处理中…':'刷新版本'}}</button></div>
      <p v-if="error" class="release-error" role="alert">{{error}}</p><p v-if="notice" class="release-notice" role="status">{{notice}}</p>
      <details><summary>上传新版本</summary><form class="release-form" @submit.prevent="upload">
        <label>签名清单 JSON<textarea v-model="manifest" rows="6" required :disabled="busy" placeholder="粘贴构建流水线生成的 manifest.json" /></label>
        <div class="release-files"><label>完整更新包 ZIP<input type="file" accept=".zip" required :disabled="busy" @change="artifact=($event.target as HTMLInputElement).files?.[0]||null" /></label><label>首次安装包（EXE / DMG / 内部 ZIP）<input type="file" accept=".exe,.dmg,.zip" required :disabled="busy" @change="installer=($event.target as HTMLInputElement).files?.[0]||null" /></label></div>
        <p>正式版须完成系统代码签名和 Mac 公证；内部 ZIP 须用内部发布模式构建。两种模式均验证公司的更新包签名，私钥不上传。</p><button class="primary" :disabled="busy">{{busy?(uploadProgress||'处理中…'):'校验并保存草稿'}}</button>
      </form></details>
    </section>
    <section class="panel">
      <h2>发布记录</h2><p v-if="!loaded">{{busy?'正在加载版本…':'列表尚未加载，请重试。'}}</p><p v-else-if="!rows.length">暂无版本，请先上传正式安装包及更新包。</p>
      <article v-for="row in rows" :key="row.id" class="release-row">
        <div class="release-title"><strong>{{row.version}} · {{row.manifest.distribution==='internal'?'内部 ZIP':'正式签名版'}} · {{row.platform==='windows'?'Windows': 'macOS'}} {{row.arch==='arm64'?'Apple 芯片':'Intel / x64'}}</strong><span class="release-badge">{{labels[row.stage]}}</span></div>
        <p v-if="row.stage==='uploading'">上传尚未完成。重新上传同一份清单和文件即可继续；该版本不会分发给设备。</p><p>{{row.manifest.installer.filename}} · {{(row.manifest.installer.size/1024/1024).toFixed(1)}} MB</p>
        <form v-if="['draft','test'].includes(row.stage)" class="release-test" @submit.prevent="change(row,'test')"><label>测试设备 ID（ERP 设备详情中的 ID，逗号分隔）<input v-model="testing[row.id]" required pattern="[0-9,，\s]+" :disabled="busy" /></label><button class="secondary" :disabled="busy">开放给测试设备</button></form>
        <div class="release-buttons"><button v-if="['draft','test'].includes(row.stage)" class="primary" :disabled="busy" @click="change(row,'stable')">向所有公司开放稳定版</button><button v-if="row.stage!=='withdrawn'" class="secondary" :disabled="busy" @click="change(row,'withdrawn')">撤回此版本</button></div>
        <details><summary>发布记录与签名摘要</summary><code>{{row.manifest.sha256}}</code><p v-for="(event,i) in row.history" :key="i">{{event.at}} UTC · 管理员 {{event.actor_id}} · {{event.action}}<span v-if="event.test_agent_ids?.length"> · 设备 {{event.test_agent_ids.join(', ')}}</span></p></details>
      </article>
    </section>
  </div>
</template>
<style scoped>
.connector-releases{display:grid;gap:20px;min-width:0}.connector-releases>.panel{padding:24px}.connector-releases .heading{padding:0 0 18px}.connector-releases p{color:var(--admin-muted);font-size:12px;line-height:1.7}.heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.connector-releases h2{font-size:16px;margin:0 0 12px}.release-form{display:grid;gap:16px;margin-top:16px}.release-form label,.release-test label{display:grid;gap:8px;font-size:12px;min-width:0}.release-files{display:grid;grid-template-columns:1fr 1fr;gap:16px}.connector-releases input,.connector-releases textarea{width:100%;box-sizing:border-box}.release-form textarea{resize:vertical;font-family:monospace;border:1px solid var(--admin-border);border-radius:8px;padding:10px;background:var(--admin-surface);color:var(--admin-text)}.release-form button{justify-self:start}.release-row{padding:20px 0;border-top:1px solid var(--admin-border,#e2e8f0);min-width:0}.release-title,.release-buttons,.release-test{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.release-test{margin:16px 0;align-items:flex-end}.release-test label{flex:1;max-width:540px}.release-badge{font-size:12px;background:var(--admin-canvas);border-radius:6px;padding:4px 8px}.release-buttons{margin:12px 0}.connector-releases details{margin-top:16px}.connector-releases summary{cursor:pointer;font-size:13px}.connector-releases code,.release-row p{overflow-wrap:anywhere}.connector-releases .release-error{color:#b42318}.connector-releases .release-notice{color:#18794e}@media(max-width:600px){.connector-releases>.panel{padding:18px}.release-files{grid-template-columns:1fr}.heading{flex-wrap:wrap}.release-test{align-items:stretch;flex-direction:column}.release-test label{width:100%}.release-buttons button{width:100%}}
</style>
