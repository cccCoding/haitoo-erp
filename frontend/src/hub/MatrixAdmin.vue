<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import axios from 'axios'
import MatrixDevices from './MatrixDevices.vue'
import MatrixReleaseManager from './MatrixReleaseManager.vue'
import {filterParams,percent,display} from './matrix'
const props=defineProps<{token:string}>(),emit=defineEmits<{unauthorized:[]}>()
const route=useRoute(),router=useRouter(),api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8000'})
const tabs=[{id:'overview',name:'总览统计'},{id:'devices',name:'设备管理'},{id:'settings',name:'功能设置'}]
const tab=computed(()=>tabs.some(t=>t.id===route.query.tab)?String(route.query.tab):'overview')
const statsLoaded=ref(false)
const config=ref({enabled:false,listing_enabled:false})
const ready=ref(false),forbidden=ref(false),busy=ref(false),loading=ref(false),error=ref(''),notice=ref('')
const members=ref<any[]>([]),devices=ref<any[]>([]),deviceUser=ref('')
const dateString=(d:Date)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit'}).format(d)
const filters=ref({start:dateString(new Date(Date.now()-6*86400000)),end:dateString(new Date()),user_id:'',agent_id:'',site:'',task:''})
const stats=ref<any>({current:{},summary:{},by_member:[],daily:[]})
const filteredDevices=computed(()=>devices.value.filter(d=>!deviceUser.value||String(d.user_id)===String(deviceUser.value)))
const filterDevices=computed(()=>devices.value.filter(d=>!filters.value.user_id||String(d.user_id)===String(filters.value.user_id)))
const maxDaily=computed(()=>Math.max(1,...stats.value.daily.map((d:any)=>d.total)))
const cards=computed(()=>[
 {name:'公司授权成员',value:display(stats.value.current.authorized_members),hint:'公司当前授权人数'},
 {name:'在线设备',value:`${stats.value.current.online_devices??'—'} / ${stats.value.current.devices??'—'}`,hint:'当前在线 / 未撤销设备'},
 {name:'环境 / 店铺',value:`${stats.value.current.environments??'—'} / ${stats.value.current.shops??'—'}`,hint:'店铺按身份去重'},
 {name:'运行次数',value:display(stats.value.summary.total),hint:'所选日期内创建的运行'},
 {name:'运行成功率',value:percent(stats.value.summary.success_rate),hint:'成功 / 已结束，不含取消'},
 {name:'待人工处理',value:display(stats.value.summary.awaiting_attention),hint:'所选日期内的当前状态'},
])
const auth=()=>({headers:{Authorization:`Bearer ${props.token}`}})
let poll:ReturnType<typeof setInterval>|undefined,disposed=false
function handle(e:any){if(e.response?.status===401)emit('unauthorized');if(e.response?.status===403)error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'仅公司管理员可查看';else error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'请求失败，请重试'}
async function perform(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await fn()}catch(e){handle(e)}finally{busy.value=false}}
function setTab(value:string){notice.value='';error.value='';void router.replace({query:{...route.query,tab:value}})}
async function loadDevices(){const {data}=await api.get('/hub-v5/admin/devices',auth());if(!disposed)devices.value=data.items}
async function loadStats(){if(loading.value)return;loading.value=true;try{const {data}=await api.get('/hub-v5/admin/statistics',{...auth(),params:filterParams(filters.value)});if(!disposed){stats.value=data;statsLoaded.value=true}}finally{loading.value=false}}
async function loadMembers(){const {data}=await api.get('/hub-v5/admin/members',auth());if(disposed)return;members.value=data.items}
async function refresh(){await perform(async()=>{const results=await Promise.allSettled([
 api.get('/hub-v5/config',auth()).then(({data})=>{if(!disposed)config.value=data}),
 loadMembers(),loadDevices(),loadStats(),
]);for(const result of results)if(result.status==='rejected')throw result.reason})}

async function saveConnection(device:any,identity:string){await perform(async()=>{await api.put(`/hub-v5/agents/${device.id}/connection`,{hub_identity:identity},auth());notice.value='团队配置已保存，等待连接器自动同步';await loadDevices()})}
async function command(device:any,kind:string){await perform(async()=>{await api.post(`/hub-v5/agents/${device.id}/commands`,{kind},auth());notice.value=kind==='refresh'?'已请求设备同步':kind==='revoke'?'设备授权已撤销':'设备接收状态已更新';await loadDevices()})}
onMounted(async()=>{try{const {data}=await api.get('/hub-v5/access',auth());if(!data.is_admin){forbidden.value=true;return}ready.value=true;await refresh();poll=setInterval(()=>{if(!busy.value&&!disposed)void loadDevices().catch(handle)},10000)}catch(e){handle(e)}})
onUnmounted(()=>{disposed=true;if(poll)clearInterval(poll)})
</script>
<template>
<section class="matrix-admin page">
  <div v-if="forbidden" class="ma-panel ma-empty">仅公司管理员可进入矩阵管理。</div>
  <template v-else>
    <nav class="ma-tabs" aria-label="矩阵后台页面"><button v-for="t in tabs" :key="t.id" :class="{active:tab===t.id}" :aria-current="tab===t.id?'page':undefined" @click="setTab(t.id)">{{t.name}}</button></nav>
    <p v-if="error" class="ma-error" role="alert">{{error}}</p><p v-if="notice" class="ma-notice" role="status">{{notice}}</p>
    <div v-if="!ready" class="ma-panel ma-empty">正在读取管理员权限…</div>
    <template v-else-if="tab==='overview'">
      <form class="ma-filters ma-panel" @submit.prevent="perform(loadStats)"><label>开始日期<input v-model="filters.start" type="date" required/></label><label>结束日期<input v-model="filters.end" type="date" required/></label><label>成员<select v-model="filters.user_id" @change="filters.agent_id='' "><option value="">全部成员</option><option v-for="m in members" :key="m.id" :value="m.id">{{m.name}}</option></select></label><label>设备<select v-model="filters.agent_id"><option value="">全部设备</option><option v-for="d in filterDevices" :key="d.id" :value="d.id">{{d.name}}</option></select></label><label>站点<select v-model="filters.site"><option value="">全部站点</option><option>MY</option><option value="unknown">未知站点</option></select></label><label>任务类型<select v-model="filters.task"><option value="">全部类型</option><option value="shop.collect">店铺采集</option><option value="listing.catalog">自动上品</option></select></label><button class="ma-primary" :disabled="busy||loading">{{loading?'统计中…':'查询'}}</button></form>
      <p v-if="statsLoaded&&stats.start" class="ma-result-range">当前运行统计：{{stats.start}} 至 {{stats.end}} · 按运行创建日期筛选</p><div class="ma-cards"><article v-for="c in cards" :key="c.name"><span>{{c.name}}</span><strong>{{c.value}}</strong><small>{{c.hint}}</small></article></div>
      <div class="ma-panel"><div class="ma-section-title"><h2>每日运行</h2><small>按香港时间统计创建日期 · 设备与环境卡片显示当前状态</small></div><div v-if="stats.summary.total" class="ma-chart" role="img" aria-label="所选日期的每日运行数量"><div v-for="d in stats.daily" :key="d.date" class="ma-chart-day" :title="`${d.date}：${d.total} 次运行`"><span>{{d.total}}</span><div class="ma-chart-track"><i :style="{height:`${d.total/maxDaily*100}%`}"/></div><small>{{d.date.slice(5)}}</small></div></div><p v-else class="ma-empty">{{loading?'正在统计…':statsLoaded?'所选日期暂无运行记录':'请查询统计数据'}}</p></div>
      <div class="ma-panel"><div class="ma-section-title"><h2>成员执行统计</h2><small>成功率按成功 /（成功 + 失败 + 部分成功）计算；取消不计入分母</small></div><div class="ma-table-wrap"><table><thead><tr><th>成员</th><th>运行次数</th><th>排队中</th><th>执行中</th><th>成功</th><th>失败</th><th>部分成功</th><th>待人工</th><th>已取消</th><th>成功率</th></tr></thead><tbody><tr v-for="m in stats.by_member" :key="m.user_id"><td>{{m.name}}</td><td>{{m.total}}</td><td>{{m.queued}}</td><td>{{m.running}}</td><td>{{m.succeeded}}</td><td>{{m.failed}}</td><td>{{m.partial_success}}</td><td>{{m.awaiting_attention}}</td><td>{{m.cancelled}}</td><td>{{percent(m.success_rate)}}</td></tr><tr v-if="!stats.by_member.length"><td colspan="10" class="ma-empty">暂无符合筛选条件的运行</td></tr></tbody></table></div></div>

    </template>
    <template v-else-if="tab==='devices'"><div class="ma-section-title"><div></div><div class="ma-inline"><select v-model="deviceUser" aria-label="按成员筛选设备"><option value="">全部成员</option><option v-for="m in members" :key="m.id" :value="m.id">{{m.name}}</option></select><button :disabled="busy" @click="perform(loadDevices)">刷新</button></div></div><MatrixDevices :devices="filteredDevices" :config="config" :busy="busy" administrator @save="saveConnection" @command="command"/></template>
    <template v-else-if="tab==='settings'"><details class="ma-panel ma-advanced"><summary>连接器版本与站点插件</summary><MatrixReleaseManager :token="token" @unauthorized="emit('unauthorized')"/></details></template>
  </template>
</section>
</template>
<style scoped>
.matrix-admin{--ma-purple:#6043d4;box-sizing:border-box;width:100%;max-width:none;margin:0;padding:16px 20px 28px;background:#f6f7fb;color:#4e586c;font-size:12px}.matrix-admin *{box-sizing:border-box}.ma-section-title,.ma-inline{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px 16px}
.matrix-admin button{display:inline-flex;align-items:center;justify-content:center;flex:none;width:auto;min-height:34px;margin:0;padding:6px 11px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#697286;box-shadow:none;font:inherit;line-height:20px;white-space:nowrap;cursor:pointer}.matrix-admin button:disabled{opacity:.45;cursor:not-allowed}.matrix-admin button:hover{border-color:#b6a7d9;color:#6043d4}.matrix-admin .ma-primary{border-color:#6043d4;background:#6043d4;color:#fff}.matrix-admin :is(button,input,select,summary):focus-visible{outline:2px solid #7256e7;outline-offset:2px}
.ma-tabs{display:flex;gap:24px;overflow:auto;margin-bottom:16px;padding:0;border-bottom:1px solid #e5e7ee;background:transparent}.matrix-admin .ma-tabs button{width:auto;margin:0 0 -1px;padding:0 2px;min-height:42px;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:#8790a1;font-size:13px}.matrix-admin .ma-tabs button.active{border-bottom-color:#6043d4;color:#6043d4;font-weight:600}
.ma-panel{min-width:0;margin-bottom:16px;border:1px solid #e5e7ee;border-radius:8px;background:#fff;overflow:hidden}.ma-filters{display:flex;align-items:flex-end;flex-wrap:wrap;gap:10px;margin:0 0 14px;padding:14px 16px}.ma-filters label{display:flex;flex:1 1 125px;min-width:0;flex-direction:column;gap:6px;color:#8992a3;font-size:11px}.matrix-admin input:not([type=checkbox]),.matrix-admin select{display:block;width:100%;min-width:0;height:36px;margin:0;padding:7px 9px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#667085;font:inherit;font-size:12px}.ma-filters button{min-height:36px}.matrix-admin input[type=checkbox]{flex:none;width:14px;height:14px;margin:0;accent-color:#6043d4}.matrix-admin input[type=checkbox]:disabled{opacity:.5}
.ma-result-range{margin:0 0 12px;color:#969eae;font-size:11px}.ma-cards{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:16px}.ma-cards article{display:flex;flex-direction:column;gap:10px;min-width:0;padding:16px;border:1px solid #e5e7ee;border-radius:8px;background:#fff}.ma-cards span{color:#828b9d;font-size:11px}.ma-cards strong{color:#41485b;font-size:24px;font-weight:600}.ma-cards small{color:#a0a7b5;font-size:10px;line-height:1.6}.ma-section-title{padding:14px 16px;border-bottom:1px solid #edf0f5}.ma-section-title h2{margin:0;font-size:13px;font-weight:600}.ma-section-title small,.ma-section-title p{margin:6px 0 0;color:#959dac;font-size:11px;line-height:1.7}.matrix-admin .ma-search{flex:0 1 230px}.ma-table-wrap{max-width:100%;overflow:auto}.matrix-admin table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:12px}.matrix-admin th,.matrix-admin td{padding:11px 16px;border-bottom:1px solid #edf0f5;text-align:left;line-height:20px}.matrix-admin th{background:#f8f9fc;color:#858e9f;font-size:11px;font-weight:500}.matrix-admin td b{font-size:12px;font-weight:500}.matrix-admin td small{display:block;color:#959dac;font-size:10px}.matrix-admin td select{min-width:165px}.matrix-admin .ma-empty{padding:32px 16px;text-align:center;color:#9aa2b1}.ma-muted{color:#9aa2b1;font-size:11px}.ma-dirty{background:#fcfaff}.ma-footnote{margin:0;padding:12px 16px;color:#929aab;font-size:11px;line-height:1.7}
.ma-chart{display:flex;gap:10px;overflow:auto;padding:22px 20px 16px}.ma-chart-day{display:flex;flex:1 0 32px;min-width:32px;flex-direction:column;align-items:center;gap:8px;font-size:10px;color:#969eae}.ma-chart-track{display:flex;align-items:flex-end;justify-content:center;width:100%;height:100px;border-bottom:1px solid #eeebf6}.ma-chart-track i{display:block;width:26px;max-width:75%;border-radius:4px 4px 0 0;background:#aa98e4}.ma-chart-day span{color:#7f729d;font-size:11px}.ma-chart-day small{font-size:10px}
.ma-error,.ma-notice{margin:0 0 12px;padding:10px 12px;border-radius:6px;line-height:1.7}.ma-error{background:#fff1f0;color:#b75c60}.ma-notice{background:#edf7f3;color:#397a65}.ma-inline{justify-content:flex-start}.ma-inline select{width:170px}.ma-inline .ma-search{width:220px}
.ma-settings .ma-options{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:20px 16px}.ma-options label{display:flex;align-items:flex-start;gap:9px;margin:0;cursor:pointer}.ma-options label>input{margin-top:3px}.ma-options label>span{display:flex;flex-direction:column;gap:7px}.ma-options b{font-size:12px;font-weight:500}.ma-options small{color:#929aab;font-size:11px;line-height:1.7}.ma-advanced{padding:14px 16px}.ma-advanced summary{width:max-content;max-width:100%;color:#818a9c;font-size:12px;cursor:pointer}.ma-advanced[open] summary{margin-bottom:16px}.ma-advanced>p{color:#929aab;font-size:11px;line-height:1.7}.ma-advanced :slotted(button){min-height:32px;padding:5px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#727b8e;font:inherit;cursor:pointer}
@media(max-width:1400px){.ma-cards{grid-template-columns:repeat(3,minmax(0,1fr))}.ma-filters label{flex-basis:140px}}@media(max-width:700px){.matrix-admin{padding:12px}.ma-tabs{gap:20px}.ma-cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ma-cards article{padding:12px}.ma-cards strong{font-size:21px}.ma-section-title{gap:10px;padding:12px}.ma-filters{padding:12px}.ma-filters label{flex-basis:calc(50% - 5px)}.ma-filters label:has(input[type=date]){flex-basis:100%}.ma-filters button{width:100%}.ma-settings .ma-options{grid-template-columns:1fr;gap:18px}.ma-section-title>small{width:100%}.matrix-admin .ma-search{flex-basis:100%}}
</style>
