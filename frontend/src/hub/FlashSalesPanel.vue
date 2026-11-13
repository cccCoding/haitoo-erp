<script setup lang="ts">
import {ref,onMounted,onUnmounted,watch,computed} from 'vue'
import axios from 'axios'
import {dialogFocus as vDialogFocus} from '../dialog-focus'
import {display,label} from './matrix'
const props=defineProps<{token:string;itemId:number|null;canManage:boolean;environment?:any|null}>()
const emit=defineEmits<{'close-item':[];'close-store':[];changed:[];unauthorized:[]}>()
const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8000'})
const auth=()=>({headers:{Authorization:`Bearer ${props.token}`}})
const open=ref(false),busy=ref(false),loading=ref(false),error=ref(''),notice=ref('')
const activities=ref<any[]>([]),details=ref<any[]>([]),selected=ref<number[]>([]),unread=ref(0),unreadStores=ref(0),total=ref(0),page=ref(1)
const start=ref(''),end=ref(''),preview=ref<any>(null),key=ref(''),resolving=ref<any>(null)
const status=ref(''),counts=ref<Record<string,number>|null>(null),snapshot=ref<any>(null),activeSync=ref<any>(null),syncRunId=ref<number|null>(null),syncKey=ref('')
const statusOptions=[['','全部'],['scheduled','未开始'],['ongoing','进行中'],['expired','已结束'],['terminated','已终止']]
const platformLabels:Record<string,string>={scheduled:'未开始',ongoing:'进行中',expired:'已结束',terminated:'已终止',unknown:'待核对'}
const form=ref({action:'resume',verified_stage:'terminated',new_activity_id:'',starts_at:'',ends_at:'',evidence:''})
const isDetail=computed(()=>props.itemId!==null),isStore=computed(()=>!isDetail.value&&!!props.environment)
const eligibleCurrent=computed(()=>activities.value.filter(a=>a.can_renew))
const allCurrent=computed(()=>eligibleCurrent.value.length>0&&eligibleCurrent.value.every(a=>selected.value.includes(a.id)))
const title=computed(()=>isDetail.value?'秒杀续期活动明细':isStore.value?`${props.environment.name} · 秒杀活动`:'待处理的已结束秒杀活动')
const time=(value:string)=>value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Hong_Kong',hour12:false}):'—'
function duration(a:any){const hours=(Date.parse(a.ends_at)-Date.now())/3600000;if(!Number.isFinite(hours))return '—';return a.status==='ongoing'?(hours>0?`剩余 ${Math.ceil(hours)} 小时`:'等待同步复核'):a.status==='expired'?`已过期 ${Math.max(0,Math.floor(-hours))} 小时`:'—'}
function statusCount(value:string){if(!counts.value)return '—';return value?counts.value[value]||0:Object.values(counts.value).reduce((sum,n)=>sum+n,0)}
let timer:ReturnType<typeof setInterval>|undefined,disposed=false,request=0,detailRequest=0,reminderRequest=0,polling=false
function handle(e:any){if(e.response?.status===401)emit('unauthorized');error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'请求失败，请重试'}
async function loadReminder(){const id=++reminderRequest;try{const {data}=await api.get('/hub-v5/flash-sales/expired',{...auth(),params:{page_size:1}});if(disposed||id!==reminderRequest)return;unread.value=data.unread;unreadStores.value=data.environment_count||0}catch(e:any){if(e.response?.status===401)emit('unauthorized')}}
async function load(){
 const id=++request,scope=props.environment?.id;loading.value=true
 try{
  const {data}=await api.get(scope?`/hub-v5/environments/${scope}/flash-sales`:'/hub-v5/flash-sales/expired',{...auth(),params:{page:page.value,...(scope?{status:status.value}:{}),...(start.value?{start:new Date(start.value).toISOString()}:{}),...(end.value?{end:new Date(end.value).toISOString()}:{})}})
  if(disposed||id!==request||scope!==props.environment?.id)return
  activities.value=data.items;total.value=data.total
  selected.value=selected.value.filter(selectedId=>!data.items.some((a:any)=>a.id===selectedId&&!a.can_renew))
  if(scope){counts.value=data.counts;snapshot.value=data.snapshot;activeSync.value=data.active_sync;if(data.active_sync&&!syncRunId.value)syncRunId.value=data.active_sync.run_id}
 }catch(e){if(!disposed&&id===request)handle(e)}finally{if(id===request)loading.value=false}
}
async function loadDetails(){const id=++detailRequest,item=props.itemId;if(item===null)return;try{const {data}=await api.get(`/hub-v5/run-items/${item}/flash-sales`,auth());if(!disposed&&id===detailRequest&&item===props.itemId)details.value=data.items}catch(e){if(!disposed&&id===detailRequest)handle(e)}}
function reset(){++request;++detailRequest;error.value='';notice.value='';selected.value=[];activities.value=[];details.value=[];total.value=0;page.value=1;start.value='';end.value='';preview.value=null;key.value='';resolving.value=null;counts.value=null;snapshot.value=null;activeSync.value=null;syncRunId.value=null;syncKey.value=''}
async function showReminder(){reset();status.value='expired';open.value=true;await load()}
function close(){if(busy.value)return;++request;++detailRequest;loading.value=false;open.value=false;resolving.value=null;preview.value=null;if(isDetail.value)emit('close-item');if(isStore.value)emit('close-store')}
async function perform(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){handle(e)}finally{busy.value=false}}
function toggleAll(){const ids=eligibleCurrent.value.map(a=>a.id);selected.value=allCurrent.value?selected.value.filter(id=>!ids.includes(id)):[...new Set([...selected.value,...ids])]}
async function applyRange(){selected.value=[];preview.value=null;page.value=1;await load()}
async function changeStatus(value:string){if(busy.value)return;status.value=value;start.value='';end.value='';await applyRange()}
async function prepare(){await perform(async()=>{const {data}=await api.post('/hub-v5/flash-sales/expired/preview',{activity_ids:selected.value},auth());preview.value=data;key.value=crypto.randomUUID()})}
async function execute(){await perform(async()=>{
 await api.post('/hub-v5/manual/runs',{previews:preview.value.batches.map((b:any)=>({preview_token:b.preview_token,expected_revision:b.revision}))},{headers:{...auth().headers,'Idempotency-Key':key.value}})
 if(disposed)return
 preview.value=null;selected.value=[];notice.value='已创建独立续期运行，仅处理本次选择的已结束活动。';emit('changed');await Promise.all([load(),loadReminder()])
})}
async function dismiss(){await perform(async()=>{await api.post('/hub-v5/flash-sales/expired/dismiss',{activity_ids:selected.value},auth());selected.value=[];notice.value='已忽略所选提醒，仍可在活动列表重新选择续期。';await Promise.all([load(),loadReminder()])})}
async function sync(){await perform(async()=>{
 if(!props.environment)return
 if(!syncKey.value)syncKey.value=crypto.randomUUID()
 const {data}=await api.post(`/hub-v5/environments/${props.environment.id}/flash-sales/sync`,{},{headers:{...auth().headers,'Idempotency-Key':syncKey.value}})
 if(disposed)return
 syncRunId.value=data.id;activeSync.value={run_id:data.id,status:data.status,stage:'queued'};syncKey.value='';notice.value=`已创建只读同步 #${data.id}，可关闭抽屉，连接器会继续同步。`;emit('changed')
})}
async function pollSync(){const id=syncRunId.value;if(id===null)return;const {data}=await api.get(`/hub-v5/runs/${id}`,auth());if(id!==syncRunId.value||disposed)return;activeSync.value={run_id:id,status:data.status,stage:data.items?.[0]?.stage};if(!['queued','running'].includes(data.status)){syncRunId.value=null;activeSync.value=null;notice.value=data.status==='succeeded'?'秒杀活动已同步，列表和状态数量已更新。':`同步${label(data.status)}：${data.items?.[0]?.error||'请在运行记录中查看原因'}；仍展示上次完整数据。`;selected.value=[];await Promise.all([load(),loadReminder()]);emit('changed')}}
function resolve(row:any){resolving.value=row;form.value={action:'resume',verified_stage:row.new_activity_id?'draft_confirmed':row.terminated?'terminated':'pending',new_activity_id:row.new_activity_id||'',starts_at:'',ends_at:'',evidence:''}}
async function saveResolution(){await perform(async()=>{
 const f=form.value
 await api.post(`/hub-v5/flash-sales/${resolving.value.id}/resolve`,{action:f.action,evidence:f.evidence,...(f.action==='resume'?{verified_stage:f.verified_stage}:{}),...(f.new_activity_id?{new_activity_id:f.new_activity_id}:{}),...(f.action==='confirm-published'?{starts_at:new Date(f.starts_at).toISOString(),ends_at:new Date(f.ends_at).toISOString()}: {})},auth())
 resolving.value=null;notice.value='核对结果已保存';await loadDetails();emit('changed')
})}
watch([()=>props.itemId,()=>props.environment?.id],async()=>{reset();if(props.itemId!==null){open.value=true;await loadDetails()}else if(props.environment){status.value='';open.value=true;await load()}else open.value=false},{immediate:true})
onMounted(()=>{void loadReminder();timer=setInterval(async()=>{if(busy.value||polling||disposed)return;polling=true;try{if(open.value&&isStore.value&&!preview.value){await pollSync();await load()}else if(open.value&&isDetail.value&&!resolving.value)await loadDetails();await loadReminder()}catch(e){if(!disposed)handle(e)}finally{polling=false}},5000)})
onUnmounted(()=>{disposed=true;++request;++detailRequest;++reminderRequest;if(timer)clearInterval(timer)})
</script>

<template>
<div v-if="unread>0" class="fs-entry" role="status"><span>{{unreadStores?`${unreadStores} 家店有`:'发现'}} {{unread}} 个已结束秒杀活动待处理</span><button type="button" @click="showReminder">处理已结束活动 →</button></div>
<Teleport to="body"><div v-if="open" class="modal-backdrop fs-backdrop" @click.self="close"><section v-dialog-focus="{close,busy}" class="modal-card fs-dialog" role="dialog" aria-modal="true" aria-labelledby="flash-title">
<header><div><span class="fs-eyebrow">{{isDetail?'活动执行记录':isStore?'店铺活动':'跨店铺待处理事项'}}</span><h2 id="flash-title">{{title}}</h2><p v-if="isStore" class="fs-meta">环境编号 {{environment.container_code}} · {{snapshot?`最近完整同步 ${time(snapshot.observed_at)}`:'尚未完整同步'}} · GMT+8</p></div><button type="button" :disabled="busy" aria-label="关闭秒杀活动" @click="close">关闭 ×</button></header>
<div class="fs-content">
<p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
<template v-if="isDetail">
<p>旧活动已终止时，取消处理不会恢复旧活动。未知操作结果须先核对平台，禁止直接重复发布。</p>
<div class="fs-table"><table><thead><tr><th>原活动 / ID</th><th>阶段</th><th>新活动 ID</th><th>新起止时间</th><th>异常 / 凭据</th><th>操作</th></tr></thead><tbody><tr v-for="r in details" :key="r.id"><td>{{r.name}}<small>{{r.external_id}}</small><small>原到期 {{time(r.original_ends_at)}}</small></td><td>{{label('flash_'+r.stage)}}<small v-if="r.terminated" class="error">旧活动已终止</small></td><td>{{r.new_activity_id||'—'}}</td><td>{{time(r.starts_at)}}<small>{{time(r.ends_at)}}</small></td><td>{{r.error||r.evidence||'—'}}</td><td><button v-if="canManage&&r.stage!=='published'" :disabled="busy" @click="resolve(r)">人工核对</button></td></tr></tbody></table></div>
<p v-if="!details.length">暂无已保存的活动续期记录。</p>
<form v-if="resolving" class="fs-form" @submit.prevent="saveResolution"><h3>核对活动 {{resolving.external_id}}</h3><label>处理方式<select v-model="form.action"><option value="resume">核对未发布后恢复</option><option value="confirm-published">确认已发布</option><option value="cancel">取消后续处理</option></select></label><label v-if="form.action==='resume'">已核实平台阶段<select v-model="form.verified_stage"><option v-if="!resolving.terminated" value="pending">尚未终止或复制</option><option value="terminated">旧活动已终止，尚未复制</option><option value="draft_confirmed">已复制并确认草稿</option></select></label><label v-if="form.action==='confirm-published'||form.verified_stage==='draft_confirmed'">新活动 / 草稿 ID<input v-model="form.new_activity_id" required maxlength="120"/></label><template v-if="form.action==='confirm-published'"><label>新开始时间（当前浏览器时区）<input v-model="form.starts_at" type="datetime-local" required/></label><label>新结束时间（当前浏览器时区）<input v-model="form.ends_at" type="datetime-local" required/></label></template><label>核对凭据<textarea v-model="form.evidence" required maxlength="1000" placeholder="填写平台核对结果、活动ID及时间等依据"/></label><div class="fs-actions"><button type="button" :disabled="busy" @click="resolving=null">返回</button><button class="primary" :disabled="busy">保存核对</button></div></form>
</template>
<template v-else-if="preview"><p>将创建独立续期运行，仅复制本次选择的 {{selected.length}} 个已到期活动，新活动持续 72 小时。</p><p v-for="(message,i) in preview.errors" :key="i" class="error">{{message}}</p><section v-for="b in preview.batches" :key="b.agent_id"><b>设备 #{{b.agent_id}}</b><p>{{b.environments.map((e:any)=>e.name).join('、')}}</p></section><div class="fs-actions"><button :disabled="busy" @click="preview=null">返回选择</button><button class="primary" :disabled="busy||!!preview.errors.length" @click="execute">确认创建续期运行</button></div></template>
<template v-else>
<div class="fs-toolbar"><div><p>{{isStore?'仅展示此店铺的商家秒杀活动，平台状态以最近完整同步为准。':'以下为最近72小时内已结束、尚未续期的商家秒杀活动。默认不勾选，可调整日期查询更早记录。'}}</p><small v-if="isStore">同步只读取活动数据；已结束活动须选择并确认后才会续期。</small></div><button v-if="isStore" class="primary" :disabled="busy||!!syncRunId||!!activeSync" @click="sync">{{syncRunId||activeSync?'正在同步…':'同步秒杀活动'}}</button></div>
<p v-if="activeSync" class="fs-sync" role="status">只读同步 #{{activeSync.run_id}} · {{label(activeSync.stage||activeSync.status)}}，关闭抽屉后继续执行。</p>
<div v-if="isStore" class="fs-tabs" role="tablist" aria-label="活动状态"><button v-for="[value,name] in statusOptions" :key="value" role="tab" :aria-selected="status===value" :class="{active:status===value}" :disabled="busy" @click="changeStatus(value)">{{name}} <span>{{statusCount(value)}}</span></button></div>
<form v-if="!isStore||status==='expired'" class="fs-range" @submit.prevent="applyRange"><label>结束时间从<input v-model="start" type="datetime-local"/></label><label>至<input v-model="end" type="datetime-local"/></label><button :disabled="busy||loading">查询</button><small>留空默认最近72小时；状态数量包含全部已同步历史。</small></form>
<div v-if="isStore&&!snapshot&&!loading" class="fs-empty"><b>尚未完整同步秒杀活动</b><p>点击“同步秒杀活动”后，可查看这家店铺的四种状态。未同步的数据不会显示为0。</p></div>
<div v-else-if="loading&&!activities.length" class="fs-empty" role="status">正在读取秒杀活动…</div>
<div v-else-if="!activities.length" class="fs-empty">{{snapshot&&snapshot.count===0?'已完成同步，此店铺没有商家秒杀活动。':'当前筛选范围没有活动。'}}</div>
<div v-if="activities.length" class="fs-table" :aria-busy="loading"><table><thead><tr><th><input type="checkbox" :checked="allCurrent" :disabled="!eligibleCurrent.length||busy" aria-label="选择当前页可续期的已结束活动" @change="toggleAll"/></th><th v-if="!isStore">店铺 / 环境</th><th>活动名称 / ID</th><th>平台状态</th><th>开始时间</th><th>结束时间</th><th>剩余 / 过期</th><th>商品数</th><th>续期结果</th></tr></thead><tbody><tr v-for="a in activities" :key="a.id"><td><input v-model="selected" type="checkbox" :value="a.id" :disabled="!a.can_renew||busy" :aria-label="`选择 ${a.name}`" :title="a.can_renew?'选择后确认续期':'仅尚未处理的已结束活动可选择续期'"/></td><td v-if="!isStore">{{a.environment_name}}<small>{{a.container_code}}</small></td><td class="fs-name">{{a.name}}<small>{{a.external_id}}</small></td><td><span class="fs-status" :class="a.status">{{platformLabels[a.status]||'待核对'}}</span></td><td>{{time(a.starts_at)}}</td><td>{{time(a.ends_at)}}</td><td>{{duration(a)}}</td><td>{{display(a.product_count)}}</td><td><details v-if="a.renewal"><summary>{{label('flash_'+a.renewal.stage)}}</summary><p v-if="a.renewal.new_activity_id">新活动 {{a.renewal.new_activity_id}}</p><p>{{a.renewal.error||a.renewal.evidence||'暂无附加记录'}}</p><p v-if="a.renewal.terminated" class="error">旧活动已终止</p></details><span v-else>{{a.can_renew?'待选择续期':'—'}}</span></td></tr></tbody></table></div>
<p v-if="isStore&&snapshot" class="fs-footnote">未开始、已终止活动仅查看；进行中活动按临期规则通过批量执行或运营计划续期。商品数未取得时显示“—”。</p>
<div v-if="!isStore||snapshot||activities.length" class="fs-pagination"><button :disabled="loading||page<=1||busy" @click="page--;load()">上一页</button><span>第 {{page}} 页 · 共 {{total}} 项</span><button :disabled="loading||page*50>=total||busy" @click="page++;load()">下一页</button></div>
<div v-if="eligibleCurrent.length||selected.length" class="fs-selection"><span>已选 <b>{{selected.length}}</b> 个已结束活动</span><button :disabled="busy||!selected.length" @click="dismiss">忽略所选提醒</button><button class="primary" :disabled="busy||!selected.length" @click="prepare">续期所选活动</button></div>

</template>
</div></section></div></Teleport>
</template>

<style scoped>
.fs-entry{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:12px 16px;margin:12px 0;border:1px solid #eadbb6;border-radius:8px;background:#fffaf0;color:#856429;font-size:13px}.fs-entry button{margin-left:auto!important}
.fs-backdrop{z-index:90;display:flex;justify-content:flex-end;align-items:stretch;padding:0;background:#18213a55}.fs-dialog{display:flex;flex-direction:column;width:min(1180px,calc(100vw - 40px));height:100dvh;max-height:100dvh;margin:0;padding:0;overflow:hidden;border-radius:14px 0 0 14px;background:#fff;color:#495368;box-shadow:-12px 0 60px #18213a25}.fs-dialog header{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;padding:24px 28px;border-bottom:1px solid #e8eaf1;flex-shrink:0}.fs-eyebrow{display:block;margin-bottom:6px;color:#8a93a4;font-size:11px}.fs-dialog header>div{min-width:0;overflow-wrap:anywhere}.fs-dialog h2{font-size:19px;margin:0;color:#30384e}.fs-dialog .fs-meta{margin:8px 0 0;color:#8991a2;font-size:12px}.fs-content{padding:20px 28px;overflow:auto;flex:1;min-height:0}.fs-dialog p{font-size:12px;line-height:1.7}.fs-dialog button{width:auto;min-height:34px;margin:0;padding:6px 12px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#5e6175;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}.fs-dialog button:disabled{opacity:.45;cursor:not-allowed}.fs-dialog button.primary{background:#6043d4;color:white;border-color:#6043d4}.fs-toolbar{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:20px}.fs-toolbar p{margin:0 0 4px}.fs-toolbar small,.fs-footnote{color:#8c95a6;font-size:11px}.fs-tabs{display:flex;gap:20px;border-bottom:1px solid #e7e9f0;margin-bottom:18px;overflow:auto}.fs-dialog .fs-tabs button{padding:10px 0;border:0;border-bottom:2px solid transparent;border-radius:0;color:#8891a2}.fs-dialog .fs-tabs button.active{border-bottom-color:#6043d4;color:#6043d4;font-weight:600}.fs-tabs span{padding:2px 6px;margin-left:4px;border-radius:4px;background:#f3f1f9;font-size:11px}.fs-range,.fs-actions{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin:16px 0}.fs-range small{font-size:11px;color:#9099aa}.fs-table{overflow:auto;border:1px solid #e7e9f0;border-radius:8px}.fs-table table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:12px}.fs-table th,.fs-table td{padding:12px;border-bottom:1px solid #edf0f5;text-align:left;vertical-align:top}.fs-table th{background:#f8f9fc;color:#929aab;font-weight:500}.fs-table tbody tr:last-child td{border-bottom:0}.fs-table small{display:block;margin-top:5px;color:#969eae;font-size:10px}.fs-table .fs-name{min-width:165px;max-width:230px;white-space:normal;overflow-wrap:anywhere;color:#46516a}.fs-table details{max-width:220px;white-space:normal;overflow-wrap:anywhere}.fs-table summary{cursor:pointer;color:#6a50c5}.fs-status{display:inline-block;padding:2px 7px;border-radius:4px;background:#f0f1f5;color:#89909e;white-space:nowrap}.fs-status.ongoing{background:#e9f7ef;color:#2d9664}.fs-status.scheduled{background:#eef3ff;color:#4c75bd}.fs-status.terminated{background:#fff0f0;color:#b86269}.fs-pagination,.fs-selection{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:16px 0;color:#929aaa;font-size:12px}.fs-selection{position:sticky;bottom:-20px;padding:16px;background:#fff;border-top:1px solid #e7e9f0;margin:0 -28px -20px}.fs-selection>span{margin-right:auto;color:#626e86}.fs-selection b{color:#6043d4}.fs-empty{text-align:center;padding:55px 20px;border:1px dashed #e0e4ee;border-radius:8px;color:#9aa2b2;font-size:13px}.fs-empty b{color:#778299;font-weight:500}.fs-sync{padding:10px 14px;background:#f2f0fb;border-radius:6px;color:#7157bd}.fs-form{display:grid;gap:12px;margin-top:20px;padding:16px;background:#f7f6fb}.fs-form label,.fs-range label{display:flex;flex-direction:column;gap:6px;font-size:12px}.fs-dialog input:not([type=checkbox]),.fs-dialog select,.fs-dialog textarea{padding:8px;border:1px solid #dfe2eb;border-radius:5px;font:inherit;max-width:100%;margin:0}.fs-dialog input[type=checkbox]{width:15px;height:15px}.fs-dialog .error{color:#b84a51}.fs-dialog button:focus-visible,.fs-dialog input:focus-visible,.fs-dialog select:focus-visible,.fs-dialog summary:focus-visible{outline:2px solid #7050dc;outline-offset:2px}
@media(max-width:700px){.fs-dialog{width:100vw;border-radius:0}.fs-dialog header{padding:18px 16px;gap:10px}.fs-dialog header>div{min-width:0;overflow-wrap:anywhere}.fs-dialog h2{font-size:17px}.fs-content{padding:16px}.fs-meta{max-width:250px;line-height:1.7}.fs-toolbar{align-items:flex-start;flex-wrap:wrap;gap:12px}.fs-tabs{gap:8px}.fs-tabs span{padding:2px 4px;margin-left:3px}.fs-range label{min-width:0;flex:1 1 140px}.fs-selection{margin:0 -16px -16px;bottom:-16px;padding:12px 16px;flex-wrap:wrap}.fs-selection>span{flex:1 1 100%;margin:0}.fs-table{max-width:100%}.fs-dialog .fs-meta{font-size:11px}}
</style>
