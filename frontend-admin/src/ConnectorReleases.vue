<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
const props = defineProps<{token: string}>()
const emit = defineEmits<{unauthorized: []}>()
const api = axios.create({baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001'})
const rows = ref<any[]>([]), manifest = ref(''), artifact = ref<File | null>(null), installer = ref<File | null>(null)
const busy = ref(false), loaded = ref(false), error = ref(''), notice = ref('')
const uploadProgress = ref('')
const selectedFiles = ref<File[]>([]), manifestFile = ref<File | null>(null)
const releaseInfo = ref<{version: string; platform: string; arch: string; distribution?: string} | null>(null)
const fileInput = ref<HTMLInputElement | null>(null), dragDepth = ref(0)
const ready = computed(() => !!manifest.value && !!artifact.value && !!installer.value)
const fileSummary = computed(() => [
  {label: '签名清单', file: manifestFile.value},
  {label: '完整更新包', file: artifact.value},
  {label: '首次安装包', file: installer.value},
])
function clearFiles() {
  selectedFiles.value = []; manifestFile.value = null; manifest.value = ''
  artifact.value = null; installer.value = null; releaseInfo.value = null
  error.value = ''; notice.value = ''; dragDepth.value = 0
  if (fileInput.value) fileInput.value.value = ''
}
async function selectFiles(files: File[]) {
  if (busy.value || !files.length) return
  await perform(async () => {
    // 同名文件可重新选择；缺少的文件可继续补入。
    const combined = new Map(selectedFiles.value.map(file => [file.name, file]))
    for (const file of files) combined.set(file.name, file)
    selectedFiles.value = [...combined.values()]
    manifest.value = ''; manifestFile.value = null; artifact.value = null; installer.value = null; releaseInfo.value = null
    const all = selectedFiles.value
    if (all.length > 3) throw new Error('每次只上传一个系统和架构的三个文件。请清空后重新选择。')
    if (all.some(file => !/\.(json|zip|exe|dmg)$/i.test(file.name))) throw new Error('仅支持 JSON 清单、ZIP 更新包及 EXE / DMG / ZIP 安装包。请清空后重新选择。')
    const manifests = all.filter(file => /\.json$/i.test(file.name))
    if (manifests.length > 1) throw new Error('只能选择一份签名清单。请清空后重新选择。')
    if (!manifests.length) { notice.value = '已选择文件，请补入对应的 manifest.json 签名清单。'; return }
    const jsonFile = manifests[0]!
    if (jsonFile.size > 3 * 1024 * 1024) throw new Error('签名清单超过 3 MB，请检查文件是否正确。')
    const content = await jsonFile.text()
    let parsed: any
    try { parsed = JSON.parse(content.replace(/^\uFEFF/, '')) } catch { throw new Error('签名清单不是有效的 JSON，请重新选择构建生成的 manifest.json。') }
    if (!parsed || parsed.kind !== 'agent' || !/^\d+\.\d+\.\d+$/.test(parsed.version) ||
        !['windows/x64', 'macos/arm64', 'macos/x64'].includes(`${parsed.platform}/${parsed.arch}`) ||
        typeof parsed.installer?.filename !== 'string' || !Number.isSafeInteger(parsed.size) || parsed.size <= 0 ||
        !Number.isSafeInteger(parsed.installer.size) || parsed.installer.size <= 0) {
      throw new Error('清单缺少有效的连接器版本、系统、架构或安装包信息，请使用构建生成的签名清单。')
    }
    const binaries = all.filter(file => file !== jsonFile)
    const installFile = binaries.find(file => file.name === parsed.installer.filename)
    const updateFiles = binaries.filter(file => file !== installFile)
    if (updateFiles.length > 1) throw new Error(`未找到清单对应的首次安装包：${parsed.installer.filename}。请清空后重新选择。`)
    const updateFile = updateFiles[0]
    if (updateFile && !/\.zip$/i.test(updateFile.name)) throw new Error('完整更新包必须是 ZIP 文件，请清空后重新选择。')
    if (installFile && installFile.size !== parsed.installer.size) throw new Error('首次安装包大小与清单不一致，请选择同一次构建生成的文件。')
    if (updateFile && updateFile.size !== parsed.size) throw new Error('完整更新包大小与清单不一致，请选择同一次构建生成的文件。')
    manifestFile.value = jsonFile; manifest.value = content.replace(/^\uFEFF/, '')
    installer.value = installFile || null; artifact.value = updateFile || null
    releaseInfo.value = parsed
    notice.value = ready.value ? '三个文件已识别，可上传并保存草稿。' : '文件尚未齐全，请继续补入下方缺少的文件。'
  })
}
async function chooseFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  await selectFiles(files)
}
async function dropFiles(event: DragEvent) {
  dragDepth.value = 0
  await selectFiles(Array.from(event.dataTransfer?.files || []))
}
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
    if (!ready.value || !artifact.value || !installer.value) throw new Error('请先选择同一次构建生成的三个文件。')
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
  <div class="connector-releases" @dragover.prevent @drop.prevent>
    <section class="panel">
      <div class="heading"><div><h2>连接器版本</h2><p>统一管理 Windows 与 macOS。每次上传同时包含首次安装包和完整更新包，同版本内容不可替换。</p></div><button class="secondary" :disabled="busy" @click="refresh">{{busy?'处理中…':'刷新版本'}}</button></div>
      <p v-if="error" class="release-error" role="alert">{{error}}</p><p v-if="notice" class="release-notice" role="status">{{notice}}</p>
      <details><summary>上传新版本</summary><form class="release-form" @submit.prevent="upload">
        <div class="release-dropzone" :class="{'is-dragging': dragDepth > 0 && !busy, 'is-disabled': busy}"
          @dragenter.prevent="dragDepth++" @dragleave.prevent="dragDepth = Math.max(0, dragDepth - 1)"
          @dragover.prevent @drop.prevent.stop="dropFiles">
          <strong>将同一次构建的三个文件一起拖到这里</strong>
          <p id="release-file-help">签名清单 JSON + 完整更新包 ZIP + 首次安装包（EXE / DMG / 内部 ZIP）<br>每次上传一个系统和架构，缺少的文件可继续补入。</p>
          <input ref="fileInput" class="release-file-input" type="file" tabindex="-1" multiple accept=".json,.zip,.exe,.dmg" :disabled="busy" aria-label="选择连接器发布文件，可多选" aria-describedby="release-file-help" @change="chooseFiles" />
          <button type="button" class="secondary" :disabled="busy" @click="fileInput?.click()">选择文件（可多选）</button>
        </div>
        <div v-if="selectedFiles.length" class="release-selection" aria-live="polite">
          <div class="release-selection-heading"><strong v-if="releaseInfo">{{releaseInfo.version}} · {{releaseInfo.platform==='windows'?'Windows':'macOS'}} {{releaseInfo.arch==='arm64'?'Apple 芯片':'Intel / x64'}} · {{releaseInfo.distribution==='internal'?'内部 ZIP':'正式签名版'}}</strong><strong v-else>已选择 {{selectedFiles.length}} 个文件</strong><button type="button" class="secondary" :disabled="busy" @click="clearFiles">清空重选</button></div>
          <ul><li v-for="item in fileSummary" :key="item.label"><span>{{item.label}}</span><span v-if="item.file">{{item.file.name}} · {{(item.file.size/1024/1024).toFixed(2)}} MB</span><span v-else class="release-missing">待补入</span></li></ul>
          <p v-if="!releaseInfo">已选文件：{{selectedFiles.map(file => file.name).join('、')}}</p>
        </div>
        <p>正式版须完成系统代码签名和 Mac 公证；内部 ZIP 须用内部发布模式构建。上传后验证公司的更新包签名，私钥不上传。</p><button class="primary" :disabled="busy || !ready">{{busy?(uploadProgress||'处理中…'):'上传并保存草稿'}}</button>
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
.connector-releases{display:grid;gap:20px;min-width:0}.connector-releases>.panel{padding:24px}.connector-releases .heading{padding:0 0 18px}.connector-releases p{color:var(--admin-muted);font-size:12px;line-height:1.7}.heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.connector-releases h2{font-size:16px;margin:0 0 12px}.release-form{display:grid;gap:16px;margin-top:16px}.release-form label,.release-test label{display:grid;gap:8px;font-size:12px;min-width:0}.connector-releases input{width:100%;box-sizing:border-box}.release-dropzone{position:relative;display:grid;justify-items:center;gap:12px;padding:28px 20px;border:2px dashed var(--admin-border);border-radius:8px;background:var(--admin-canvas);text-align:center}.release-dropzone>strong{font-size:14px}.release-dropzone p{margin:0}.release-dropzone.is-dragging{border-color:var(--admin-primary);background:var(--admin-primary-soft)}.release-dropzone.is-disabled{opacity:.65}.release-dropzone .release-file-input{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;clip-path:inset(50%)}.release-dropzone:focus-within{outline:2px solid var(--admin-primary);outline-offset:2px}.release-dropzone button{justify-self:center}.release-selection{padding:16px;border:1px solid var(--admin-border);border-radius:8px;min-width:0}.release-selection-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:13px}.release-selection ul{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:10px}.release-selection li{display:grid;grid-template-columns:90px minmax(0,1fr);gap:12px;font-size:12px;line-height:1.7}.release-selection li span:last-child,.release-selection p{overflow-wrap:anywhere}.release-missing{color:var(--admin-muted)}.release-form button{justify-self:start}.release-row{padding:20px 0;border-top:1px solid var(--admin-border,#e2e8f0);min-width:0}.release-title,.release-buttons,.release-test{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.release-test{margin:16px 0;align-items:flex-end}.release-test label{flex:1;max-width:540px}.release-badge{font-size:12px;background:var(--admin-canvas);border-radius:6px;padding:4px 8px}.release-buttons{margin:12px 0}.connector-releases details{margin-top:16px}.connector-releases summary{cursor:pointer;font-size:13px}.connector-releases code,.release-row p{overflow-wrap:anywhere}.connector-releases .release-error{color:#b42318}.connector-releases .release-notice{color:#18794e}@media(max-width:600px){.connector-releases>.panel{padding:18px}.release-dropzone{padding:24px 12px}.release-selection li{grid-template-columns:1fr;gap:2px}.heading{flex-wrap:wrap}.release-test{align-items:stretch;flex-direction:column}.release-test label{width:100%}.release-buttons button{width:100%}}
</style>
