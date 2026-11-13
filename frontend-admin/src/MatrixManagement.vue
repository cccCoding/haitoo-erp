<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import axios from 'axios'
import MatrixDevices from './hub/MatrixDevices.vue'
import TKMatrix from '../../frontend/src/hub/TKMatrix.vue'
import ConnectorReleases from './ConnectorReleases.vue'
import {filterParams,percent,display} from './hub/matrix'

const props=defineProps<{token:string;companies:{id:number;name:string;tk_matrix_enabled?:boolean}[]}>()
const emit=defineEmits<{unauthorized:[]}>()
const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8001'})
const route=useRoute(),router=useRouter()
const tabs=[{id:'overview',name:'总览统计'},{id:'devices',name:'设备管理'},{id:'user',name:'用户视角'},{id:'releases',name:'连接器版本'}] as const
type TabId=typeof tabs[number]['id']
const tab=computed<TabId>(()=>tabs.some(t=>t.id===route.query.tab)?String(route.query.tab) as TabId:'overview')
const companyId=ref<number|null>(null)
const enabledCompanies=computed(()=>props.companies.filter(company=>company.tk_matrix_enabled))
const viewUserId=ref<number|null>(null),viewSession=ref<{token:string;user:any}|null>(null),viewLoading=ref(false),viewError=ref('')
let viewSeq=0
const statsLoaded=ref(false)
const config=ref({enabled:false,listing_enabled:false})
const busy=ref(false),loading=ref(false),error=ref(''),notice=ref('')
const members=ref<any[]>([]),devices=ref<any[]>([]),deviceUser=ref('')
const connectorReleases=ref<InstanceType<typeof ConnectorReleases>|null>(null)
const dateString=(d:Date)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit'}).format(d)
const filters=ref({start:dateString(new Date(Date.now()-6*86400000)),end:dateString(new Date()),user_id:'',agent_id:'',site:'',task:''})
const stats=ref<any>({current:{},summary:{},by_member:[],daily:[]})
const filteredDevices=computed(()=>devices.value.filter(d=>!deviceUser.value||String(d.user_id)===String(deviceUser.value)))
const filterDevices=computed(()=>devices.value.filter(d=>!filters.value.user_id||String(d.user_id)===String(filters.value.user_id)))
const maxDaily=computed(()=>Math.max(1,...stats.value.daily.map((d:any)=>d.total)))
const cards=computed(()=>[
 {name:'授权成员',value:display(stats.value.current.authorized_members),hint:'公司当前授权人数'},
 {name:'在线设备',value:`${stats.value.current.online_devices??'—'} / ${stats.value.current.devices??'—'}`,hint:'当前在线 / 未撤销设备'},
 {name:'环境 / 店铺',value:`${stats.value.current.environments??'—'} / ${stats.value.current.shops??'—'}`,hint:'店铺按身份去重'},
 {name:'运行次数',value:display(stats.value.summary.total),hint:'所选日期内创建的运行'},
 {name:'运行成功率',value:percent(stats.value.summary.success_rate),hint:'成功 / 已结束，不含取消'},
 {name:'待人工处理',value:display(stats.value.summary.awaiting_attention),hint:'所选日期内的当前状态'},
])
const auth=()=>({headers:{Authorization:`Bearer ${props.token}`}})
const companyBase=(id:number)=>`/admin/matrix/companies/${id}`
let poll:ReturnType<typeof setInterval>|undefined,disposed=false,statsSeq=0,devicesSeq=0
function handle(e:any){
  if(e.response?.status===401)emit('unauthorized')
  if(e.response?.status===403)error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'仅平台管理员可查看'
  else error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'请求失败，请重试'
}
async function perform(fn:()=>Promise<void>){
  if(busy.value)return
  busy.value=true;error.value='';notice.value=''
  try{await fn()}catch(e){handle(e)}finally{busy.value=false}
}
function setTab(value:TabId){notice.value='';error.value='';void router.replace({query:{...route.query,tab:value}})}
function resetCompanyData(){statsSeq++;devicesSeq++;loading.value=false;error.value='';notice.value='';statsLoaded.value=false;stats.value={current:{},summary:{},by_member:[],daily:[]};members.value=[];devices.value=[];deviceUser.value='';filters.value.user_id='';filters.value.agent_id=''}
async function loadConfig(){
  const id=companyId.value
  if(!id)return
  const {data}=await api.get(`${companyBase(id)}/config`,auth())
  if(id===companyId.value&&!disposed)config.value=data
}
async function loadMembers(){
  const id=companyId.value
  if(!id){members.value=[];return}
  const {data}=await api.get(`${companyBase(id)}/members`,auth())
  if(id===companyId.value&&!disposed)members.value=data.items
}
async function loadDevices(){
  const seq=++devicesSeq,id=companyId.value
  if(!id){devices.value=[];return}
  const {data}=await api.get(`${companyBase(id)}/devices`,auth())
  if(seq===devicesSeq&&id===companyId.value&&!disposed)devices.value=data.items
}
async function loadStats(){
  const seq=++statsSeq,id=companyId.value
  if(!id)return
  loading.value=true
  try{
    const {data}=await api.get(`${companyBase(id)}/statistics`,{...auth(),params:filterParams(filters.value)})
    if(seq===statsSeq&&id===companyId.value&&!disposed){stats.value=data;statsLoaded.value=true}
  }finally{if(seq===statsSeq)loading.value=false}
}
async function loadCompany(){await Promise.all([loadConfig(),loadMembers(),loadDevices()])}
async function loadCompanyData(includeStats:boolean){
  const results=await Promise.allSettled([loadCompany(),includeStats?loadStats():Promise.resolve()])
  for(const result of results)if(result.status==='rejected')throw result.reason
}
async function refreshCompany(){await perform(()=>loadCompanyData(true))}
async function refreshDevices(){await perform(loadDevices)}
async function refresh(){
  if(tab.value==='releases'){await connectorReleases.value?.refresh();return}
  if(tab.value==='user'){await loadMembers();await loadUserView();return}
  if(!companyId.value)return
  if(tab.value==='devices')await perform(loadCompany)
  else await refreshCompany()
}
async function saveConnection(device:any,identity:string){
  await perform(async()=>{
    const id=companyId.value
    if(!id)return
    await api.put(`${companyBase(id)}/agents/${device.id}/connection`,{hub_identity:identity},auth())
    notice.value='团队配置已保存，等待连接器自动同步';await loadDevices()
  })
}
async function command(device:any,kind:string){
  await perform(async()=>{
    const id=companyId.value
    if(!id)return
    await api.post(`${companyBase(id)}/agents/${device.id}/commands`,{kind},auth())
    notice.value=kind==='retry_update'?'已请求设备重新尝试更新':kind==='refresh'?'已请求设备同步':kind==='revoke'?'设备授权已撤销':'设备接收状态已更新'
    await loadDevices()
  })
}
async function loadUserView(){
  const seq=++viewSeq,id=companyId.value,uid=viewUserId.value
  viewSession.value=null;viewError.value='';viewLoading.value=false
  if(!id||!uid)return
  viewLoading.value=true
  try{
    const {data}=await api.post(`${companyBase(id)}/users/${uid}/view`,{},auth())
    if(seq===viewSeq&&!disposed)viewSession.value=data
  }catch(e:any){if(seq===viewSeq&&!disposed){if(e.response?.status===401)emit('unauthorized');viewError.value=e.response?.data?.detail||'用户视角加载失败，请重试'}}
  finally{if(seq===viewSeq)viewLoading.value=false}
}
watch(viewUserId,()=>{void loadUserView()})
watch(enabledCompanies,companies=>{
  if(!companies.some(item=>item.id===companyId.value))companyId.value=companies[0]?.id??null
},{immediate:true})
watch(companyId,()=>{
  resetCompanyData();++viewSeq;viewUserId.value=null;viewSession.value=null;viewError.value='';viewLoading.value=false
  if(tab.value==='releases'||!companyId.value)return
  // 切换公司不受上一家公司刷新中的 busy 限制；旧请求由序号丢弃。
  void loadCompanyData(tab.value==='overview').catch(handle)
})
watch(tab,value=>{
  if(value==='releases'||!companyId.value)return
  if(value==='user'){void perform(loadMembers);return}
  if(value==='devices')void perform(loadCompany)
  else if(!statsLoaded.value)void loadCompanyData(true).catch(handle)
})
onMounted(()=>{
  if(companyId.value&&tab.value!=='releases')void loadCompanyData(tab.value==='overview').catch(handle)
  poll=setInterval(()=>{if(tab.value==='devices'&&!busy.value&&!disposed&&companyId.value)void loadDevices().catch(handle)},10000)
})
onUnmounted(()=>{disposed=true;++viewSeq;if(poll)clearInterval(poll)})
defineExpose({refresh})
</script>
<template>
<section class="matrix-management">
  <div class="panel mm-company">
    <div class="mm-company-form">
      <label>公司总览
        <select v-model="companyId" :disabled="!enabledCompanies.length">
          <option v-if="!enabledCompanies.length" :value="null">暂无已开通 TK 矩阵的公司</option>
          <option v-for="company in enabledCompanies" :key="company.id" :value="company.id">{{company.name}}</option>
        </select>
      </label>
      <label v-if="tab==='user'&&companyId">用户视角
        <select v-model="viewUserId"><option :value="null">请选择用户</option><option v-for="member in members" :key="member.id" :value="member.id" :disabled="!member.is_active||member.is_expired">{{member.name}} · {{member.user_code||`#${member.id}`}}{{!member.is_active?'（已停用）':member.is_expired?'（已过期）':!member.enabled?'（未授权）':''}}</option></select>
      </label>
    </div>
  </div>
  <nav class="mm-tabs" aria-label="矩阵管理页面">
    <button v-for="item in tabs" :key="item.id" type="button" :class="{active:tab===item.id}" :aria-current="tab===item.id?'page':undefined" @click="setTab(item.id)">{{item.name}}</button>
  </nav>
  <p v-if="error" class="mm-feedback mm-error" role="alert">{{error}}</p>
  <p v-if="notice" class="mm-feedback mm-notice" role="status">{{notice}}</p>
  <template v-if="tab==='releases'">
    <p class="mm-scope-note">连接器版本面向全平台，不随公司筛选；设备统计与设备管理按所选公司隔离。</p>
    <ConnectorReleases ref="connectorReleases" :token="token" @unauthorized="emit('unauthorized')"/>
  </template>
  <p v-else-if="!enabledCompanies.length" class="panel mm-empty">暂无已开通 TK 矩阵的公司，请先在公司管理中启用 TK 矩阵。</p>
  <template v-else>
    <template v-if="tab==='user'">
      <p class="mm-scope-note">按所选用户在 ERP 中的实际权限展示矩阵内容。此视角仅供只读排查，不能修改配置、同步设备或执行任务。</p>
      <p v-if="viewLoading" class="panel mm-empty" role="status">正在加载用户视角…</p>
      <div v-else-if="viewError" class="mm-feedback mm-error" role="alert">{{viewError}} <button class="secondary" @click="loadUserView">重新加载用户视角</button></div>
      <TKMatrix v-else-if="viewSession" :key="`${companyId}-${viewUserId}`" :token="viewSession.token" :user="viewSession.user" read-only tab-query-key="matrix_tab" @unauthorized="viewSession=null;viewError='用户视角会话已失效，请重新加载'"/>
      <p v-else class="panel mm-empty">请选择用户，查看该用户的 TK 矩阵。</p>
    </template>
    <template v-else-if="tab==='overview'">
      <form class="panel mm-filters" @submit.prevent="perform(loadStats)">
        <label>开始日期<input v-model="filters.start" type="date" required/></label>
        <label>结束日期<input v-model="filters.end" type="date" required/></label>
        <label>成员<select v-model="filters.user_id" @change="filters.agent_id=''"><option value="">全部成员</option><option v-for="m in members" :key="m.id" :value="m.id">{{m.name}}</option></select></label>
        <label>设备<select v-model="filters.agent_id"><option value="">全部设备</option><option v-for="d in filterDevices" :key="d.id" :value="d.id">{{d.name}}</option></select></label>
        <label>站点<select v-model="filters.site"><option value="">全部站点</option><option value="MY">MY</option><option value="unknown">未知站点</option></select></label>
        <label>任务类型<select v-model="filters.task"><option value="">全部类型</option><option value="shop.collect">店铺采集</option><option value="listing.catalog">自动上品</option></select></label>
        <button class="primary" type="submit" :disabled="busy||loading">{{loading?'统计中…':'查询'}}</button>
      </form>
      <p v-if="statsLoaded&&stats.start" class="mm-range">当前运行统计：{{stats.start}} 至 {{stats.end}} · 按运行创建日期筛选（香港时间）</p>
      <div class="mm-cards">
        <article v-for="c in cards" :key="c.name"><span>{{c.name}}</span><strong>{{c.value}}</strong><small>{{c.hint}}</small></article>
      </div>
      <section class="panel mm-panel">
        <div class="mm-section-title"><h2>每日运行</h2><small>按香港时间统计创建日期 · 设备与环境卡片显示当前状态</small></div>
        <div v-if="stats.summary.total" class="mm-chart" role="img" aria-label="所选日期的每日运行数量">
          <div v-for="d in stats.daily" :key="d.date" class="mm-chart-day" :title="`${d.date}：${d.total} 次运行`">
            <span>{{d.total}}</span><div class="mm-chart-track"><i :style="{height:`${d.total/maxDaily*100}%`}"/></div><small>{{d.date.slice(5)}}</small>
          </div>
        </div>
        <p v-else class="mm-empty">{{loading?'正在统计…':statsLoaded?'所选日期暂无运行记录':'请查询统计数据'}}</p>
      </section>
      <section class="panel mm-panel">
        <div class="mm-section-title"><h2>成员执行统计</h2><small>成功率按成功 /（成功 + 失败 + 部分成功）计算；取消不计入分母</small></div>
        <div class="mm-table-wrap"><table><thead><tr><th>成员</th><th>运行次数</th><th>排队中</th><th>执行中</th><th>成功</th><th>失败</th><th>部分成功</th><th>待人工</th><th>已取消</th><th>成功率</th></tr></thead><tbody><tr v-for="m in stats.by_member" :key="m.user_id"><td>{{m.name}}</td><td>{{m.total}}</td><td>{{m.queued}}</td><td>{{m.running}}</td><td>{{m.succeeded}}</td><td>{{m.failed}}</td><td>{{m.partial_success}}</td><td>{{m.awaiting_attention}}</td><td>{{m.cancelled}}</td><td>{{percent(m.success_rate)}}</td></tr><tr v-if="!stats.by_member.length"><td colspan="10" class="mm-empty">暂无符合筛选条件的运行</td></tr></tbody></table></div>
      </section>
    </template>
    <template v-else-if="tab==='devices'">
      <div class="panel mm-device-toolbar">
        <div class="mm-section-title"><div><h2>设备列表</h2><small>展示所选公司的全部连接器设备；仅平台管理员可撤销授权。</small></div><div class="mm-inline"><select v-model="deviceUser" aria-label="按成员筛选设备"><option value="">全部成员</option><option v-for="m in members" :key="m.id" :value="m.id">{{m.name}}</option></select><button class="secondary" :disabled="busy" @click="refreshDevices">{{busy?'刷新中…':'刷新设备'}}</button></div></div>
        <MatrixDevices :token="token" :devices="filteredDevices" :config="config" :busy="busy" :company-id="companyId" administrator @save="saveConnection" @command="command"/>
      </div>
    </template>
  </template>
</section>
</template>
<style scoped>
.matrix-management{min-width:0}
.mm-tabs{display:flex;gap:24px;overflow:auto;margin-bottom:18px;border-bottom:1px solid var(--admin-border);background:transparent}
.mm-tabs button{width:auto;margin:0 0 -1px;padding:0 2px;min-height:42px;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:var(--admin-muted);font-size:13px;font-weight:500;white-space:nowrap;cursor:pointer}
.mm-tabs button:hover{color:var(--admin-primary)}
.mm-tabs button.active{border-bottom-color:var(--admin-primary);color:var(--admin-primary);font-weight:600}
.mm-feedback{margin:0 0 14px;padding:10px 14px;border-radius:8px;font-size:12px;line-height:1.7}
.mm-error{background:#fff1f2;color:#b4233b}
.mm-notice{background:#ecfdf5;color:#047857}
.mm-empty{padding:40px 24px;text-align:center;color:var(--admin-muted);font-size:13px}
.mm-scope-note{margin:0 0 14px;color:var(--admin-muted);font-size:12px;line-height:1.7}
.mm-company{margin-bottom:16px;padding:14px 18px}
.mm-company-form{display:flex;align-items:center;flex-wrap:wrap;gap:12px 16px}
.mm-company-form label{display:flex;align-items:center;gap:8px;color:#475569;font-size:12px;font-weight:600;white-space:nowrap}
.mm-company-form select{flex:0 1 220px;width:220px;min-width:0;height:36px;min-height:36px;padding:6px 10px}
.mm-company-form p{flex:1;min-width:220px;margin:0;color:var(--admin-muted);font-size:12px;line-height:1.7}
.mm-company-form p b{color:var(--admin-text);font-weight:600}
.mm-filters{display:flex;align-items:flex-end;flex-wrap:wrap;gap:10px 12px;margin:0 0 14px;padding:16px 18px}
.mm-filters label{display:flex;flex:1 1 138px;min-width:0;flex-direction:column;gap:6px;color:var(--admin-muted);font-size:11px}
.mm-filters input,.mm-filters select{height:38px;min-height:38px;padding:7px 10px;font-size:12px}
.mm-filters .primary{min-height:38px;flex:none}
.mm-range{margin:0 0 12px;color:var(--admin-muted);font-size:11px}
.mm-cards{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin-bottom:16px}
.mm-cards article{display:flex;flex-direction:column;gap:8px;min-width:0;padding:16px 18px;border:1px solid var(--admin-border);border-radius:var(--admin-radius);background:var(--admin-surface);box-shadow:0 2px 4px #17243b02}
.mm-cards span{color:var(--admin-muted);font-size:11px}
.mm-cards strong{color:var(--admin-text);font-size:24px;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.mm-cards small{color:#94a3b8;font-size:10px;line-height:1.6}
.mm-panel{margin-bottom:16px}
.mm-section-title{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 16px;padding:16px 20px;border-bottom:1px solid var(--admin-border)}
.mm-section-title h2{margin:0;font-size:15px;font-weight:600}
.mm-section-title small{color:var(--admin-muted);font-size:11px;line-height:1.7}
.mm-device-toolbar .mm-section-title{border-bottom:1px solid var(--admin-border)}
.mm-inline{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mm-inline select{width:190px;height:36px;min-height:36px;padding:6px 10px;font-size:12px}
.mm-inline .secondary{min-height:36px}
.mm-chart{display:flex;gap:10px;overflow:auto;padding:22px 20px 16px}
.mm-chart-day{display:flex;flex:1 0 32px;min-width:32px;flex-direction:column;align-items:center;gap:8px;font-size:10px;color:var(--admin-muted)}
.mm-chart-track{display:flex;align-items:flex-end;justify-content:center;width:100%;height:100px;border-bottom:1px solid #e6ebf2}
.mm-chart-track i{display:block;width:26px;max-width:75%;border-radius:4px 4px 0 0;background:#93b4fd}
.mm-chart-day span{color:var(--admin-primary);font-size:11px}
.mm-chart-day small{font-size:10px}
.mm-table-wrap{max-width:100%;overflow:auto}
table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:12px}
th,td{padding:11px 20px;border-bottom:1px solid #eef2f7;text-align:left;line-height:20px}
th{background:#f8fafc;color:var(--admin-muted);font-size:11px;font-weight:500}
tbody tr:hover{background:#fbfcfe}
td.mm-empty{white-space:normal}
@media(max-width:1400px){.mm-cards{grid-template-columns:repeat(3,minmax(0,1fr))}.mm-filters label{flex-basis:150px}}
@media(max-width:700px){.mm-tabs{gap:18px}.mm-cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.mm-cards article{padding:12px}.mm-cards strong{font-size:21px}.mm-company-form{flex-direction:column;align-items:stretch}.mm-company-form label{display:grid;grid-template-columns:auto minmax(0,1fr);width:100%}.mm-company-form select{width:100%;min-width:0;flex:none}.mm-filters{padding:14px}.mm-filters label{flex-basis:calc(50% - 6px)}.mm-filters label:has(input[type=date]){flex-basis:100%}.mm-filters .primary{width:100%}.mm-section-title{padding:14px}.mm-chart{padding:16px 12px}.mm-inline{width:100%}.mm-inline select{flex:1;width:auto;min-width:0}.mm-inline .secondary{flex:none}}
</style>
