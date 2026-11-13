<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { probeLocalAgent, type LocalAgentState } from './local-agent'

const props = defineProps<{ token: string; readOnly?: boolean }>()
const state = ref<LocalAgentState>('checking')
const checking = ref(false), downloading = ref(''), error = ref('')
const downloadStarted=ref('')
type Installer = {id: number; platform: 'windows' | 'macos'; arch: string; version: string; filename: string; size: number; distribution:string}
const installers = ref<Installer[]>([]), packagesLoaded = ref(false)
const api = axios.create({baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000'})
let poll: ReturnType<typeof setInterval> | undefined, disposed = false
let probe: AbortController | undefined
const requests = new AbortController()

async function check() {
  if (checking.value || disposed) return
  checking.value = true
  probe = new AbortController()
  const result = await probeLocalAgent(probe.signal)
  if (!disposed) {state.value = result; checking.value = false}
}
async function loadInstallers() {
  try {
    const {data} = await api.get('/hub-v5/agent-installers', {params:{distribution:'all'}, headers:{Authorization:`Bearer ${props.token}`}, signal:requests.signal})
    if (!disposed) {installers.value = data.items; packagesLoaded.value = true}
  } catch {
    if (!disposed) {packagesLoaded.value = true; error.value = '安装包列表读取失败，请稍后重试或联系管理员。'}
  }
}
async function download(item: Installer) {
  if (downloading.value) return
  downloading.value = item.filename; error.value = ''
  downloadStarted.value=''
  try {
    const {data} = await api.post(`/hub-v5/agent-installers/${item.platform}/${item.arch}/download-url`,null,{
      params:{release_id:item.id,distribution:item.distribution}, headers:{Authorization:`Bearer ${props.token}`}, signal:requests.signal,
    })
    if (disposed) return
    const anchor = document.createElement('a')
    anchor.href=data.url;anchor.referrerPolicy='no-referrer'
    document.body.appendChild(anchor);anchor.click();anchor.remove()
    downloadStarted.value=item.filename
  } catch {
    if (!disposed) error.value = '安装包下载失败，请重试；若尚未提供安装包，请联系管理员。'
  } finally {downloading.value = ''}
}
function recheck() {void check(); if (!installers.value.length) void loadInstallers()}
function focus() {void check()}
onMounted(() => {
  if(props.readOnly)return
  void check(); void loadInstallers()
  poll = setInterval(() => {if (document.visibilityState !== 'hidden') void check()}, 5000)
  window.addEventListener('focus', focus)
  document.addEventListener('visibilitychange', focus)
})
onUnmounted(() => {
  disposed = true; probe?.abort(); requests.abort(); if (poll) clearInterval(poll)
  window.removeEventListener('focus', focus)
  document.removeEventListener('visibilitychange', focus)
})
</script>

<template>
  <div class="local-agent">
    <div class="local-agent-row">
      <slot name="navigation"/>
      <div class="local-agent-actions">
        <span v-if="readOnly" class="local-agent-status">用户视角 · 本机连接器检测不适用</span>
        <span v-else class="local-agent-status" :class="`is-${state}`" role="status" aria-live="polite" aria-label="本机连接器状态">
          <i aria-hidden="true"/>
          {{state==='ready'?'连接器已启动':state==='checking'?'检测连接器…':state==='legacy'?'连接器需更新':'连接器未启动'}}
        </span>
        <button v-if="!readOnly" type="button" class="local-agent-recheck" :disabled="checking" aria-label="重新检测本机连接器" title="重新检测本机连接器" @click="recheck">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M16 7a6.3 6.3 0 1 0 .3 5M16 3.5V7h-3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <slot/>
      </div>
    </div>
    <aside v-if="state==='unreachable'||state==='legacy'" class="local-agent-notice" aria-label="连接器安装提示">
      <div class="local-agent-installers">
        <strong>{{state==='legacy'?'更新连接器以继续使用':'启动连接器以同步本机环境'}}</strong>
        <template v-for="platform in (['windows','macos'] as const)" :key="platform">
          <button v-for="item in installers.filter(i=>i.platform===platform)" :key="item.filename" type="button" :disabled="!!downloading" @click="download(item)">
            {{downloading===item.filename?'正在获取下载链接…':`下载 ${platform==='windows'?'Windows':'macOS'} 版${item.arch==='arm64'?(platform==='macos'?'（Apple 芯片）':'（ARM64）'):'（Intel / x64）'}${item.distribution==='internal'?' · 内部 ZIP':''}`}}
          </button>
          <span v-if="packagesLoaded&&!installers.some(i=>i.platform===platform)" class="local-agent-unavailable">{{platform==='windows'?'Windows':'macOS'}} 版暂未提供</span>
        </template>
      </div>
      <p v-if="downloadStarted" role="status">已请求浏览器下载 {{downloadStarted}}，请在浏览器下载列表查看进度。若下载失败，请重新点击下载。</p>
      <p>安装并启动连接器后，在 ERP 授权此电脑。之后连接器自动检查更新。若已启动仍未检测到，请允许浏览器访问本地网络。</p>
      <p v-if="error" role="alert">{{error}}</p>
    </aside>
  </div>
</template>

<style scoped>
.local-agent{min-width:0;margin:0 0 14px}
.local-agent-row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 20px;min-height:44px;border-bottom:1px solid #e5e7ee}
.local-agent-actions{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px;margin-left:auto;padding-bottom:8px}
.local-agent-status{display:inline-flex;align-items:center;gap:6px;color:#788192;font-size:12px;white-space:nowrap;line-height:20px}
.local-agent-status i{width:6px;height:6px;border-radius:50%;background:#9aa4b2}
.local-agent-status.is-ready{color:#28765f}.local-agent-status.is-ready i{background:#20a278}
.local-agent-status.is-legacy,.local-agent-status.is-unreachable{color:#996b24}.local-agent-status.is-legacy i,.local-agent-status.is-unreachable i{background:#cc943a}
.local-agent .local-agent-recheck{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px;min-height:0;margin:0;padding:5px;border:0;border-radius:6px;background:transparent;color:#8891a0}
.local-agent-recheck svg{width:16px;height:16px}.local-agent .local-agent-recheck:hover{background:#eeedf6;color:#6043d4}
.local-agent button:focus-visible{outline:2px solid #7256e7;outline-offset:2px}.local-agent button:disabled{opacity:.5;cursor:default}
.local-agent-notice{margin:12px 0 0;padding:12px 14px;border:1px solid #f0dfc4;border-radius:8px;background:#fffbf3;color:#94652d;font-size:12px}
.local-agent-installers{display:flex;align-items:center;gap:8px 12px;flex-wrap:wrap}.local-agent-installers strong{font-size:12px;font-weight:600}
.local-agent-installers button{width:auto;min-height:30px;margin:0;padding:5px 10px;border:1px solid #e7cfac;border-radius:6px;background:#fff;color:inherit;font:inherit;cursor:pointer}
.local-agent-unavailable{font-size:11px;color:#9c8a72}.local-agent-notice p{margin:7px 0 0;font-size:12px;line-height:1.6}
@media(max-width:700px){.local-agent-row{gap:8px}.local-agent-actions{width:100%;justify-content:flex-start;margin:0;padding:0 0 10px;gap:6px}.local-agent-notice{padding:10px 12px}}
</style>
