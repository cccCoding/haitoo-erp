<script setup lang="ts">
import {ref,computed,onMounted,onUnmounted,watch,nextTick} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import axios from 'axios'
import {dialogFocus as vDialogFocus} from '../dialog-focus'
import {label,display,percent,windowBuckets,filterParams,deviceSetup,environmentSyncTargets,sortMatrixRows,runEnvironmentScope} from './matrix'
import AgentUpdateHelp from './AgentUpdateHelp.vue'
import {updateRecovery} from './update-recovery'
import AgentConnectionBanner from './AgentConnectionBanner.vue'
import MatrixDevices from './MatrixDevices.vue'
import MatrixRunViewer from './MatrixRunViewer.vue'
import FlashSalesPanel from './FlashSalesPanel.vue'
const flashItemId=ref<number|null>(null),flashEnvironment=ref<any>(null)
import MatrixRunHistory from './MatrixRunHistory.vue'
import {createRunViewer,formatRunLogs} from './run-viewer'
import PlanShopSelect from './PlanShopSelect.vue'
const props=defineProps<{token:string;user:any;readOnly?:boolean;tabQueryKey?:string}>()
const emit=defineEmits<{unauthorized:[];'access-change':[enabled:boolean]}>()
const route=useRoute(),router=useRouter()
const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8000'})
api.interceptors.request.use(config=>{
 if(props.readOnly&&(config.method||'get').toLowerCase()!=='get')throw {response:{status:403,data:{detail:'用户视角仅支持只读查看矩阵内容'}}}
 return config
})
const auth=()=>({headers:{Authorization:`Bearer ${props.token}`}})
const tab=computed(()=>route.query[props.tabQueryKey||'tab']==='data'?'data':route.query[props.tabQueryKey||'tab']==='automation'?'automation':'environments')
function setTab(value:string){void router.replace({query:{...route.query,[props.tabQueryKey||'tab']:value}})}
const devices=ref<any[]>([]),operations=ref<any[]>([]),plans=ref<any[]>([]),strategies=ref<any[]>([]),rows=ref<any[]>([]),runs=ref<any[]>([]),stats=ref<any>({windows:[]})
const catalogs=ref<any[]>([])
const listingStrategies=computed(()=>{
 const crossBorderIds=new Set(catalogs.value.filter(c=>c.template_type==='tiktok_cross_border'&&c.site==='MY').map(c=>c.id))
 return strategies.value.filter(s=>crossBorderIds.has(s.category_catalog_id)&&(s.title_site||'MY')==='MY')
})
const activeRun=ref<any>(null),runSummary=ref<Record<string,number>>({})
const configLoaded=ref(false)
const accessLoaded=ref(false),access=ref({enabled:false,collect_enabled:false,listing_enabled:false,view_scope:'own',is_admin:false})
const pairingCode=computed(()=>typeof route.query.hub_agent_pair==='string'?route.query.hub_agent_pair:'')
const config=ref({enabled:false,listing_enabled:false}),total=ref(0),page=ref(1),size=ref(50),loading=ref(false),busy=ref(false),error=ref(''),notice=ref('')
const groupOptions=ref<string[]>([])
const filters=ref({q:'',site:'',group:'',ungrouped:false,collected:''}),selected=ref<number[]>([]),allFiltered=ref(false)
const appliedFilters=ref({...filters.value}),selectedEnvs=new Map<number,any>()
const hideAccountNames=ref(true)
const viewer=createRunViewer(async id=>(await api.get(`/hub-v5/runs/${id}`,auth())).data,async(id,params)=>(await api.get(`/hub-v5/runs/${id}/events`,{...auth(),params})).data,()=>emit('unauthorized'))
const {run,events,itemId:runItemId,more:logsMore,loading:logsLoading,error:logsError}=viewer
const runView=ref<'overview'|'logs'>('overview'),logNotice=ref('')
const dialog=ref(''),previewData=ref<any>(null),runPage=ref(1),runTotal=ref(0)
const historyScope=ref<any>(null),historyRuns=ref<any[]>([]),historyPage=ref(1),historyTotal=ref(0),historyLoading=ref(false),historyError=ref(''),historyScroll=ref(0)
const runFromHistory=ref(false)
let historyRequest=0
let historyTrigger:HTMLElement|null=null
const taskNames=(tasks:string[])=>['listing.catalog','promotion.flash_sale.renew','promotion.flash_sale.collect','shop.collect'].filter(task=>tasks.includes(task)).map(task=>({'shop.collect':'店铺采集','listing.catalog':'自动上品','promotion.flash_sale.renew':'秒杀续期','promotion.flash_sale.collect':'同步秒杀活动'}[task])).join(' + ')
const timeText=(value:string)=>value?new Date(value).toLocaleString('zh-CN'):'—'
const detail=ref<any>(null),detailPage=ref(1),detailQ=ref(''),detailTotal=ref(0),shopId=ref<number|null>(null)
const expandedProductSkus=ref<Record<string,boolean>>({})
const editor=ref<any>({name:'',operation_id:null,agent_id:null,environment_ids:[],scheduled:false,time:'09:00',schedule_mode:'daily',interval_hours:2})
const planShops=ref<any[]>([]),planShopsLoading=ref(false),planShopsError=ref('')
let planShopRequest=0
const operationEditor=ref<any>({name:'',tasks:[],strategies:{}}),operationEditing=ref<number|null>(null)
const manual=ref<any>({tasks:[],strategies:{}})
const previewBatches=computed(()=>previewData.value?.batches||[])
const runPages=computed(()=>Math.max(1,Math.ceil(runTotal.value/20)))
const editing=ref<number|null>(null),resolution=ref({item:null as any,action:'retry'}),releaseFile=ref<File|null>(null),manifestText=ref(''),releaseEnabled=ref(false),releases=ref<any[]>([])
const pages=computed(()=>Math.max(1,Math.ceil(total.value/size.value)))
const ownDevices=computed(()=>devices.value.filter(d=>d.user_id===props.user.id&&d.version!=='协议4'&&d.is_active))
const syncPending=ref<{id:number;name:string;previous:string|null}[]>([]),syncMessage=ref(''),syncHelp=ref(false)
let syncDeadline=0,syncRequested=0,syncFailed=0
const feedbackSource=ref<'error'|'notice'|'sync'>('notice')
watch(error,value=>{if(value)feedbackSource.value='error'},{flush:'sync'})
watch(notice,value=>{if(value)feedbackSource.value='notice'},{flush:'sync'})
watch(syncMessage,value=>{if(value)feedbackSource.value='sync'},{flush:'sync'})
const feedbackMessage=computed(()=>feedbackSource.value==='error'?error.value:feedbackSource.value==='sync'?syncMessage.value:notice.value)

const selectedCount=computed(()=>allFiltered.value?total.value:selected.value.length)
const current=computed(()=>['run','resolve'].includes(dialog.value)?run.value:activeRun.value)
const cards=computed(()=>[
 ['已采集店铺',`${stats.value.collected||0} / ${stats.value.total||0}`],['在售商品',display(stats.value.active)],['有浏览商品',display(stats.value.with_views),productShare(stats.value.with_views),'views'],['零浏览商品',display(stats.value.zero_views),productShare(stats.value.zero_views),'zero-views'],
 ['总曝光',windowBuckets(stats.value.windows,'impressions')],['总点击',windowBuckets(stats.value.windows,'clicks'),`点击率 ${windowBuckets(stats.value.windows,'ctr')}`],['有违规店铺',`${stats.value.violations||0} / ${stats.value.violations_covered||0}`]])
const dataSort=ref<{key:string;direction:'asc'|'desc'|null}>({key:'',direction:null})
const visibleRows=computed(()=>tab.value==='data'?sortMatrixRows(rows.value,dataSort.value.key,dataSort.value.direction):rows.value)
const identityColumns=[{key:'name',label:'环境名 / 编号'},{key:'group',label:'分组'},{key:'site',label:'站点'}]
const dataColumns=[
 {key:'snapshot.active',label:'在售商品'},
 {key:'snapshot.with_views',label:'有浏览'},
 {key:'snapshot.zero_views',label:'零浏览'},
 {key:'snapshot.impressions',label:'曝光'},
 {key:'snapshot.clicks',label:'点击'},
 {key:'snapshot.ctr',label:'点击率'},
 {key:'snapshot.gmv',label:'GMV'},
 {key:'snapshot.sell_through_rate',label:'动销率'},
 {key:'snapshot.violations_score',label:'违规分'},
 {key:'snapshot.observed_at',label:'采集时间'},
]
function toggleDataSort(key:string){
 if(dataSort.value.key!==key){dataSort.value={key,direction:'asc'};return}
 dataSort.value=dataSort.value.direction==='asc'?{key,direction:'desc'}:{key:'',direction:null}
}
function sortAria(key:string):'none'|'ascending'|'descending'{
 if(dataSort.value.key!==key)return 'none'
 return dataSort.value.direction==='asc'?'ascending':'descending'
}
function sortIcon(key:string){return dataSort.value.key!==key?'':dataSort.value.direction==='asc'?'↑':'↓'}
function accountNameText(name:string){
 if(!hideAccountNames.value)return name
 const characters=Array.from(name)
 if(characters.length<=1)return characters.length?'****':''
 const visibleCount=characters.length>=6?2:1
 const suffix=characters.length>2?characters.slice(-visibleCount).join(''):''
 return `${characters.slice(0,visibleCount).join('')}****${suffix}`
}
function productShare(count:number|null|undefined){
 const active=stats.value.active
 return `占总商品 ${count==null||active==null||active===0?'—':`${(count/active*100).toFixed(1)}%`}`
}
let generation=0,poll:ReturnType<typeof setInterval>|undefined,disposed=false,polling=false
async function perform(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e:any){handle(e)}finally{busy.value=false}}
function handle(e:any){if(e.response?.status===401)emit('unauthorized');error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'请求失败，请重试'}
async function loadRows(){const id=++generation;loading.value=true;try{const {data}=await api.get('/hub-v5/environments',{...auth(),params:{...filterParams(appliedFilters.value),page:page.value,page_size:size.value}});if(disposed||id!==generation)return;rows.value=data.items;total.value=data.total;groupOptions.value=data.groups||[];if(page.value>pages.value){page.value=pages.value;await loadRows()}}catch(e){handle(e)}finally{if(id===generation)loading.value=false}}
async function loadRuns(){const {data}=await api.get('/hub-v5/runs',{...auth(),params:{page:runPage.value}});runs.value=data.items;runTotal.value=data.total;activeRun.value=data.active;runSummary.value=data.summary||{}}
async function loadDevices(){
 const {data}=await api.get('/hub-v5/agents',auth());devices.value=data
 if(syncPending.value.length&&!busy.value){
  syncPending.value=syncPending.value.filter(target=>{
   const device=data.find((d:any)=>d.id===target.id)
   const updated=Date.parse(device?.sync_at||'')
   return !Number.isFinite(updated)||updated<=(target.previous?Date.parse(target.previous):0)
  })
  const completed=syncRequested-syncFailed-syncPending.value.length
  if(!syncPending.value.length)syncMessage.value=`环境目录已更新：${completed} 台设备${syncFailed?`；${syncFailed} 台发送失败，请重试`:''}`
  else if(Date.now()>=syncDeadline){syncMessage.value=`${syncPending.value.map(d=>d.name).join('、')} 尚未完成同步，请检查连接器与 HubStudio 后重试`;syncPending.value=[];syncHelp.value=true}
  else syncMessage.value=`正在同步环境：${completed} / ${syncRequested-syncFailed} 台设备已更新${syncFailed?`；${syncFailed} 台发送失败`:''}`
 }
}
async function refresh(){await perform(async()=>{
 await Promise.all([
  loadDevices(),
  api.get('/hub-v5/config',auth()).then(({data})=>{config.value=data;configLoaded.value=true}),
  loadAutomation(),
  api.get('/supply/strategies',auth()).then(({data})=>{strategies.value=data}),
  api.get('/supply/catalogs',auth()).then(({data})=>{catalogs.value=data}),
  api.get('/hub-v5/shops/metrics',{...auth(),params:filterParams(appliedFilters.value)}).then(({data})=>{stats.value=data}),
  loadRows(),loadRuns(),
 ])
})}
async function authorizeConnector(){await perform(async()=>{
 await api.post('/hub-agent/pairings/complete',{code:pairingCode.value},auth())
 const {hub_agent_pair,...query}=route.query;await router.replace({query})
 notice.value='连接器已授权，正在等待电脑连接和环境同步';await loadDevices()
})}
async function saveConnection(device:any,identity:string){await perform(async()=>{
 const {data}=await api.put(`/hub-v5/agents/${device.id}/connection`,{hub_identity:identity},auth())
 devices.value=devices.value.map(d=>d.id===device.id?data:d)
 notice.value='连接配置已保存，连接器会自动同步当前团队的环境';await loadRows()
})}

function applyFilters(){appliedFilters.value={...filters.value,group:filters.value.ungrouped?'':filters.value.group};selectedEnvs.clear();selected.value=[];allFiltered.value=false;page.value=1;notice.value='筛选已更新，已清空选择';void refresh()}
async function toggle(id:number){
 if(allFiltered.value){await perform(async()=>{await materializeSelection();selected.value=selected.value.filter(value=>value!==id)});return}
 const env=rows.value.find(r=>r.id===id);if(env)selectedEnvs.set(id,env)
 selected.value=selected.value.includes(id)?selected.value.filter(v=>v!==id):[...selected.value,id]
}
function selectCurrent(){selectedEnvs.clear();selected.value=[];allFiltered.value=true}
function changeGroup(event:Event){const value=(event.target as HTMLSelectElement).value;filters.value.ungrouped=value==='ungrouped';filters.value.group=value.startsWith('group:')?value.slice(6):''}
async function materializeSelection(limit=Infinity){
 const targets:any[]=[]
 for(let currentPage=1;;currentPage++){
  const {data}=await api.get('/hub-v5/environments',{...auth(),params:{...filterParams(appliedFilters.value),page:currentPage,page_size:100}})
  if(data.total>limit){error.value='批量设置最多支持1000个环境，请缩小筛选范围';return false}
  targets.push(...data.items)
  if(targets.length>=data.total||!data.items.length)break
 }
 selectedEnvs.clear();for(const env of targets)selectedEnvs.set(env.id,env)
 selected.value=targets.map(env=>env.id);allFiltered.value=false
 return true
}
async function openOverrides(){await perform(async()=>{
 if(allFiltered.value&&!await materializeSelection(1000))return
 if(!selected.value.length)return
 if(selected.value.length>1000){error.value='批量设置最多支持1000个环境，请缩小筛选范围';return}
 overrideSite.value='keep';overrideActivity.value='keep';dialog.value='override'
})}
async function syncEnvironments(){
 if(syncPending.value.length||busy.value)return
 await perform(async()=>{
  syncMessage.value='正在检查在线设备…';syncHelp.value=false
  try{await loadDevices()}catch(e){syncMessage.value='在线设备读取失败，请重试';throw e}
  const targets=environmentSyncTargets(devices.value,props.user.id,config.value)
  if(!targets.length){syncMessage.value='暂无可同步的在线设备，请启动并授权连接器，并在设备管理中配置 Hub 团队 ID';syncHelp.value=true;return}
  syncRequested=targets.length;syncFailed=0;syncDeadline=Date.now()+60000
  for(const device of targets){
   try{await api.post(`/hub-v5/agents/${device.id}/commands`,{kind:'refresh'},auth());syncPending.value.push({id:device.id,name:device.name,previous:device.sync_at||null})}
   catch(e){syncFailed++;handle(e)}
  }
  syncMessage.value=syncPending.value.length?`已请求 ${syncPending.value.length} 台设备同步，等待环境目录更新${syncFailed?`；${syncFailed} 台发送失败`:''}`:'同步请求发送失败，请重试'
  if(!syncPending.value.length)syncHelp.value=true
 })
}
function openDevices(){error.value='';notice.value='';dialog.value='devices'}
function dismiss(){if(busy.value)return;if(['plan','operation','manual'].includes(dialog.value))return;if(dialog.value==='deletePlan'){dialog.value='plan';return}if(dialog.value==='deleteOperation'){dialog.value='operation';return}if(!busy.value)close()}
function close(){if(dialog.value==='resolve'){dialog.value='run';return}const restoreHistory=dialog.value==='history'||(dialog.value==='run'&&runFromHistory.value);viewer.close();++planShopRequest;++historyRequest;historyLoading.value=false;dialog.value='';previewData.value=null;resolution.value={item:null,action:'retry'};if(restoreHistory)void nextTick(()=>{if(historyTrigger?.isConnected)historyTrigger.focus()})}
async function command(device:any,kind:string){await perform(async()=>{await api.post(`/hub-v5/agents/${device.id}/commands`,{kind},auth());notice.value=kind==='retry_update'?'已请求重试更新，当前任务结束后检查；请先处理实际系统提示':kind==='refresh'?'已请求同步，完整目录上传后会显示在环境列表中':kind==='pause'?'已暂停此电脑接收新任务':kind==='resume'?'已恢复此电脑接收新任务':'已撤销此电脑授权';await Promise.all([loadDevices(),loadRows()])})}
async function loadPlanShops(){
 const request=++planShopRequest,agent=editor.value.agent_id
 planShops.value=[];planShopsError.value='';planShopsLoading.value=true
 try{
  if(!agent)return
  const {data}=await api.get('/hub-v5/plan-environments',{...auth(),params:{agent_id:agent}})
  if(request!==planShopRequest||disposed)return
  planShops.value=data.items
 }catch(e){if(request===planShopRequest){planShopsError.value='店铺加载失败，请重试';handle(e)}}
 finally{if(request===planShopRequest)planShopsLoading.value=false}
}
async function loadAutomation(){const [p,o]=await Promise.all([api.get('/hub-v5/plans',auth()),api.get('/hub-v5/operations',auth())]);plans.value=p.data;operations.value=o.data}
function changePlanDevice(){editor.value.environment_ids=[];void loadPlanShops()}
function edit(plan?:any){
 editing.value=plan?.id||null
 editor.value=plan?JSON.parse(JSON.stringify({...plan,expected_revision:plan.revision})):{name:'',operation_id:operations.value[0]?.id||null,agent_id:ownDevices.value[0]?.id||null,environment_ids:[],scheduled:false,time:'09:00',schedule_mode:'daily',interval_hours:2}
 if(!plan)changePlanOperation()
 dialog.value='plan';void loadPlanShops()
}
function changePlanOperation(){editor.value.schedule_mode=operations.value.find(o=>o.id===editor.value.operation_id)?.tasks?.join(',')==='promotion.flash_sale.renew'?'interval':'daily'}
async function savePlan(){await perform(async()=>{
 const e=editor.value
 if(!e.environment_ids.length){error.value='请选择计划执行的店铺';return}
 const payload={name:e.name,operation_id:e.operation_id,agent_id:e.agent_id,environment_ids:e.environment_ids,scheduled:e.scheduled,time:e.time,schedule_mode:e.schedule_mode||'daily',interval_hours:e.interval_hours||2,timezone:'Asia/Shanghai',...(editing.value?{expected_revision:e.expected_revision}:{})}
 await api.request({url:editing.value?`/hub-v5/plans/${editing.value}`:'/hub-v5/plans',method:editing.value?'PATCH':'POST',data:payload,...auth()});await loadAutomation();close()
})}
async function togglePlan(p:any){await perform(async()=>{await api.patch(`/hub-v5/plans/${p.id}`,{name:p.name,operation_id:p.operation_id,agent_id:p.agent_id,environment_ids:p.environment_ids,scheduled:!p.scheduled,time:p.time,schedule_mode:p.schedule_mode||'daily',interval_hours:p.interval_hours||2,expected_revision:p.revision},auth());await loadAutomation()})}
async function deletePlan(){if(dialog.value!=='deletePlan')return;await perform(async()=>{await api.delete(`/hub-v5/plans/${editing.value}`,{...auth(),params:{expected_revision:editor.value.expected_revision}});await loadAutomation();close()})}
function editOperation(o?:any){
 operationEditing.value=o?.id||null
 operationEditor.value=o?JSON.parse(JSON.stringify({...o,flash_sale:{threshold_hours:12,...o.flash_sale},strategies:{MY:null,...o.strategies}})):{name:'',tasks:access.value.collect_enabled?['shop.collect']:['listing.catalog'],strategies:{MY:null},flash_sale:{threshold_hours:12}}
 if(!listingStrategies.value.some(s=>s.id===Number(operationEditor.value.strategies.MY)))operationEditor.value.strategies.MY=null
 dialog.value='operation'
}
async function saveOperation(){await perform(async()=>{const o=operationEditor.value;const payload={name:o.name,tasks:o.tasks,flash_sale:o.flash_sale,strategies:o.tasks.includes('listing.catalog')&&o.strategies.MY?{MY:Number(o.strategies.MY)}:{},...(operationEditing.value?{expected_revision:o.revision}:{})};await api.request({url:operationEditing.value?`/hub-v5/operations/${operationEditing.value}`:'/hub-v5/operations',method:operationEditing.value?'PATCH':'POST',data:payload,...auth()});await loadAutomation();close()})}
async function deleteOperation(){if(dialog.value!=='deleteOperation')return;await perform(async()=>{await api.delete(`/hub-v5/operations/${operationEditing.value}`,{...auth(),params:{expected_revision:operationEditor.value.revision}});await loadAutomation();close()})}
let manualPreviewRequest=''
function openManual(){manual.value={tasks:[],strategies:{MY:null},flash_sale:{threshold_hours:12}};previewData.value=null;manualPreviewRequest='';executeKey.value='';dialog.value='manual'}
async function preview(p:any){await perform(async()=>{
 executeKey.value=''
 const {data}=await api.post(`/hub-v5/plans/${p.id}/preview`,{},auth());previewData.value={...data,batches:[data],environment_count:data.environments.length,manual:false}
 dialog.value='preview'
})}
async function submitManual(){await perform(async()=>{
 const payload={tasks:manual.value.tasks,flash_sale:manual.value.flash_sale,strategies:manual.value.tasks.includes('listing.catalog')&&manual.value.strategies.MY?{MY:Number(manual.value.strategies.MY)}:{},environment_ids:selected.value,all_filtered:allFiltered.value,filters:filterParams(appliedFilters.value)}
 const request=JSON.stringify(payload)
 if(request!==manualPreviewRequest||!previewData.value||previewData.value.errors.length){
  previewData.value=null;manualPreviewRequest='';executeKey.value=''
  const {data}=await api.post('/hub-v5/manual/preview',payload,auth())
  previewData.value={...data,manual:true};manualPreviewRequest=request
 }
 if(previewData.value.errors.length)return
 try{await createRuns()}catch(e:any){
  // 明确拒绝后重新校验，网络异常时保留原请求和幂等键供安全重试。
  if(e.response?.status>=400&&e.response?.status<500){previewData.value=null;manualPreviewRequest='';executeKey.value=''}
  throw e
 }
})}
const executeKey=ref('')
async function execute(){await perform(createRuns)}
async function createRuns(){
 if(!executeKey.value)executeKey.value=crypto.randomUUID()
 const headers={headers:{...auth().headers,'Idempotency-Key':executeKey.value}}
 let created:any[]=[]
 if(previewData.value.manual){const {data}=await api.post('/hub-v5/manual/runs',{previews:previewBatches.value.map((p:any)=>({preview_token:p.preview_token,expected_revision:p.revision}))},headers);created=data.items}
 else {const p=previewBatches.value[0];const {data}=await api.post(`/hub-v5/plans/${p.plan_id}/runs`,{preview_token:p.preview_token,expected_revision:p.revision},headers);created=[data]}
 viewer.close();run.value=null;events.value=[];close();executeKey.value='';runPage.value=1;notice.value=`已创建 ${created.length} 次运行，可在运行记录中查看进度`;await loadRuns()
}
async function loadHistory(){
 const request=++historyRequest;historyLoading.value=true;historyError.value=''
 try{const {data}=await api.get('/hub-v5/runs',{...auth(),params:{page:historyPage.value,...(historyScope.value?{environment_id:historyScope.value.id}:{})}})
 if(request!==historyRequest||disposed)return
 historyRuns.value=data.items;historyTotal.value=data.total
 }catch(e:any){if(request===historyRequest){if(e.response?.status===401)emit('unauthorized');historyError.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'运行记录加载失败，请重试'}}finally{if(request===historyRequest)historyLoading.value=false}
}
async function changeHistoryPage(value:number){historyPage.value=value;historyScroll.value=0;historyRuns.value=[];await loadHistory()}
async function openHistory(row?:any){historyTrigger=document.activeElement instanceof HTMLElement?document.activeElement:null;historyScroll.value=0;historyScope.value=row||null;historyPage.value=1;historyRuns.value=[];historyTotal.value=0;error.value='';dialog.value='history';await loadHistory()}
async function openRun(value:any,itemId:number|null=null,fromHistory=false,view:'overview'|'logs'='overview'){
 if(fromHistory){++historyRequest;historyLoading.value=false}runFromHistory.value=fromHistory;runView.value=view;logNotice.value='';dialog.value='run'
 await viewer.open(value,itemId)
}
async function selectRunItem(id:number|null){if(id===runItemId.value)return;logNotice.value='';await viewer.select(id)}
async function backToHistory(){viewer.close();dialog.value='history';await loadHistory()}
async function stopCurrent(){const target=current.value;if(!target)return;await perform(async()=>{await api.post(`/hub-v5/runs/${target.id}/stop`,{},auth());notice.value='已请求停止，正在等待设备安全结束';await logs();await loadRuns()})}
async function logs(){if(dialog.value==='run')await viewer.load()}
async function copyLogs(){
 const id=run.value?.id,scope=runItemId.value
 const show=(message:string)=>{if(dialog.value==='run'&&run.value?.id===id&&runItemId.value===scope)logNotice.value=message}
 try{await navigator.clipboard.writeText(formatRunLogs(events.value));show('当前范围日志已复制')}catch{show('复制失败，请检查浏览器剪贴板权限后重试')}
}
async function showShop(row:any){if(!row.shop)return;shopId.value=row.shop.id;detail.value=null;detailPage.value=1;detailQ.value='';await loadDetail();if(detail.value)dialog.value='shop'}
async function loadDetail(){await perform(async()=>{const {data}=await api.get(`/hub-v5/shops/${shopId.value}/snapshots`,{...auth(),params:{page:detailPage.value,q:detailQ.value}});detail.value=data;detailTotal.value=data.total;expandedProductSkus.value={}})}
function resolveItem(item:any){error.value='';resolution.value={item,action:item.submission==='unknown'||item.submission==='request_sent'?'confirm-submitted':run.value?.stop_requested?'cancel':item.submission==='confirmed'?'retransmit':'retry'};dialog.value='resolve'}
async function saveResolution(){await perform(async()=>{await api.post(`/hub-v5/run-items/${resolution.value.item.id}/resolve`,{action:resolution.value.action},auth());dialog.value='run';await logs();await Promise.all([loadRows(),loadRuns()])})}
async function downloadProducts(){await perform(async()=>{const {data}=await api.get(`/hub-v5/shops/${shopId.value}/export`,{...auth(),params:{q:detailQ.value},responseType:'blob'});const url=URL.createObjectURL(data);const a=document.createElement('a');a.href=url;a.download='店铺商品与SKU.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}
async function download(){await perform(async()=>{const {data}=await api.get('/hub-v5/exports',{...auth(),params:filterParams(appliedFilters.value),responseType:'blob'});const url=URL.createObjectURL(data);const a=document.createElement('a');a.href=url;a.download=`店铺数据-${new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Hong_Kong'})}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}
const overrideSite=ref('keep'),overrideActivity=ref('keep')
async function saveOverrides(){await perform(async()=>{if(allFiltered.value)throw Error();const targets=selected.value.map(id=>{const row=selectedEnvs.get(id)||rows.value.find(r=>r.id===id);if(!row)throw Error('所选环境已不可用，请重新选择');return {id,expected_revision:row.revision}});await api.patch('/hub-v5/environments/overrides',{environments:targets,...(overrideSite.value==='keep'?{}:{site:overrideSite.value||null}),...(overrideActivity.value==='keep'?{}:{activity_status:overrideActivity.value})},auth());selectedEnvs.clear();selected.value=[];close();await loadRows()})}

async function checkAccess(){
 const previous=access.value
 const {data}=await api.get('/hub-v5/access',auth());access.value=data;accessLoaded.value=true;emit('access-change',!!data.enabled)
 if(!data.enabled||previous.view_scope!==data.view_scope){selected.value=[];allFiltered.value=false;selectedEnvs.clear();viewer.close();run.value=null;events.value=[];historyRuns.value=[];historyScope.value=null;syncPending.value=[];syncMessage.value='';syncHelp.value=false;dialog.value='';close()}
 if(!data.enabled){devices.value=[];rows.value=[];plans.value=[];operations.value=[];runs.value=[];total.value=0}
 return !previous.enabled&&data.enabled
}
const canManageRun=(value:any)=>!props.readOnly&&value&&(access.value.is_admin||value.owner_id===props.user.id)
watch(()=>props.user.id,()=>{selected.value=[];allFiltered.value=false;void initialize()})
async function initialize(){try{await checkAccess();if(access.value.enabled)await refresh()}catch(e){handle(e);accessLoaded.value=true}}
onMounted(()=>{void initialize();poll=setInterval(async()=>{if(polling||busy.value||disposed)return;polling=true;try{const activated=await checkAccess();if(!access.value.enabled)return;if(activated){await refresh();return}await logs();await Promise.all([loadRuns(),loadDevices(),...(dialog.value==='history'&&!historyLoading.value?[loadHistory()]:[])]);if(tab.value==='automation')await loadAutomation();if(tab.value==='data')stats.value=(await api.get('/hub-v5/shops/metrics',{...auth(),params:filterParams(appliedFilters.value)})).data;await loadRows()}catch(e){handle(e)}finally{polling=false}},5000)})
defineExpose({refresh})
onUnmounted(()=>{viewer.close();disposed=true;++generation;if(poll)clearInterval(poll)})
</script>

<template>
<section class="matrix page">
  <div v-if="!accessLoaded" class="mx-access-state">正在读取矩阵权限…</div>
  <div v-else-if="!access.enabled" class="mx-access-state"><h2>尚未获得矩阵使用授权</h2><p>请联系公司管理员，为你的账号启用“使用矩阵”。</p><p v-if="error" class="error">{{error}}</p><button @click="initialize">重新检查授权</button></div>
  <template v-else>
  <FlashSalesPanel :key="user.id" :token="token" :read-only="readOnly" :item-id="flashItemId" :environment="flashEnvironment" :can-manage="!!canManageRun(run)" @close-item="flashItemId=null" @close-store="flashEnvironment=null" @changed="loadRuns();logs()" @unauthorized="emit('unauthorized')"/>
  <AgentConnectionBanner :token="token" :read-only="readOnly">
    <template #navigation>
      <nav class="mx-tabs" role="tablist" aria-label="矩阵页面">
        <button role="tab" :aria-selected="tab==='environments'" :class="{active:tab==='environments'}" @click="setTab('environments')">环境列表 <b>{{total}}</b></button>
        <button role="tab" :aria-selected="tab==='automation'" :class="{active:tab==='automation'}" @click="setTab('automation')">自动运营</button>
        <button role="tab" :aria-selected="tab==='data'" :class="{active:tab==='data'}" @click="setTab('data')">数据大屏 <b>{{stats.collected||0}}</b></button>
      </nav>
    </template>
    <span class="mx-device-count">{{devices.filter(d=>d.online).length}} 台设备在线</span>
    <button class="mx-device-button" @click="openDevices">设备管理</button>
    <button v-if="canManageRun(current)&&['running','queued'].includes(current.status)" class="mx-danger" :disabled="busy||current.stop_requested" @click="stopCurrent">{{current.stop_requested?'停止请求中':'停止当前运行'}}</button>
  </AgentConnectionBanner>
  <AgentUpdateHelp v-if="route.query.connector_update_help==='1'" :token="token" :read-only="readOnly" :distribution="route.query.distribution==='internal'?'internal':'signed'"/>
  <div v-if="devices.some(d=>updateRecovery(d.update_state).needed)" class="mx-notice" role="status">有连接器更新需要人工处理，当前版本和授权保留。<button @click="openDevices">查看设备更新指导</button></div>
  <div v-if="pairingCode&&!readOnly" class="mx-notice mx-pairing" role="status"><p>确认连接此电脑，连接器将同步 HubStudio 环境并接收矩阵任务。</p><button class="primary" :disabled="busy" @click="authorizeConnector">授权此电脑连接器</button></div>
  <template v-if="!dialog"><div v-if="feedbackMessage" class="mx-feedback" :class="{'is-error':feedbackSource==='error'}" :role="feedbackSource==='error'?'alert':'status'" aria-live="polite"><span>{{feedbackMessage}}</span><button v-if="feedbackSource==='sync'&&syncHelp" @click="openDevices">前往设备管理</button></div></template>
  <div v-if="configLoaded&&!config.enabled" class="mx-banner">公司矩阵功能尚未启用，请联系平台管理员开启。</div>
  <div v-if="tab==='data'" class="mx-summary mx-data-summary"><b>经营数据总览</b><button :disabled="busy" @click="download">导出 CSV</button><button :disabled="busy" @click="refresh">刷新数据</button></div>
  <div v-if="tab==='data'" class="mx-cards"><article v-for="[name,value,share,tone] in cards" :key="name" :class="tone"><span>{{name}}</span><strong>{{value}}</strong><small v-if="share">{{share}}</small></article></div>
  <section v-if="tab!=='automation'" class="mx-panel">
    <div v-if="tab==='environments'" class="mx-summary"><b>环境列表</b><span>共 {{total}} 个环境 · {{runSummary.running||0}} 项运行中 · {{runSummary.awaiting_attention||0}} 项待人工</span><button :disabled="busy" @click="refresh">刷新数据</button></div>
    <form class="mx-filters" @submit.prevent="applyFilters">
      <input v-model="filters.q" class="mx-filter-search" aria-label="搜索环境或店铺" placeholder="搜索环境、编号、店铺或账号"/>
      <select :value="filters.ungrouped?'ungrouped':filters.group?`group:${filters.group}`:''" class="mx-filter-group" aria-label="分组" @change="changeGroup"><option value="">全部分组</option><option v-for="group in groupOptions" :key="group" :value="group?`group:${group}`:'ungrouped'">{{group||'未分组'}}</option></select>
      <select v-model="filters.site" class="mx-filter-site" aria-label="站点"><option value="">全部站点</option><option>MY</option><option value="unknown">未知站点</option></select>
      <select v-model="filters.collected" aria-label="是否采集"><option value="">是否采集：全部</option><option value="true">已采集</option><option value="false">未采集</option></select>
      <div class="mx-filter-actions"><button type="submit" class="primary">筛选</button></div>
    </form>
    <div v-if="tab==='environments'" class="mx-toolbar"><button class="mx-sync" :disabled="readOnly||busy||!!syncPending.length" title="同步当前账号已配置团队的所有在线设备" @click="syncEnvironments"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 7v5h-5"/><path d="M20 12a8 8 0 1 1-2.3-5.7L20 9"/></svg>{{syncPending.length?'同步中…':'同步环境'}}</button><button :disabled="loading||busy||!total" title="选择当前筛选条件下的全部环境，包含其他分页" @click="selectCurrent">全选当前</button><button @click="selected=[];allFiltered=false">清空选择</button><button type="button" class="mx-hide-names" :aria-pressed="hideAccountNames" @click="hideAccountNames=!hideAccountNames"><span v-if="hideAccountNames" aria-hidden="true">✓</span>隐藏名称</button><button :disabled="readOnly||!selectedCount||busy||loading" @click="openOverrides">批量设置站点/活跃</button><button class="primary" :disabled="readOnly||!selectedCount||busy||!config.enabled" @click="openManual">批量执行</button><span class="mx-selected">已选 {{selectedCount}}</span></div>
    <div class="mx-table-wrap" :aria-busy="loading"><table><thead><tr><th v-if="tab==='environments'">选择</th><th v-for="column in identityColumns" :key="column.key" :aria-sort="tab==='data'?sortAria(column.key):undefined"><button v-if="tab==='data'" type="button" class="mx-sort-header" @click="toggleDataSort(column.key)">{{column.label}}<span aria-hidden="true">{{sortIcon(column.key)}}</span></button><template v-else>{{column.label}}</template></th><template v-if="tab==='environments'"><th>店铺</th><th>绑定账号</th><th title="当前上架的产品数量">产品</th><th title="管理订单－全部标签页的订单数量；历史快照显示近7天订单数；尚未采集时显示 —">订单</th><th>活跃</th><th>上品 / 执行</th><th>采集</th></template><template v-else><th v-for="column in dataColumns" :key="column.key" :aria-sort="sortAria(column.key)"><button type="button" class="mx-sort-header" @click="toggleDataSort(column.key)">{{column.label}}<span aria-hidden="true">{{sortIcon(column.key)}}</span></button></th></template><th>操作</th></tr></thead><tbody>
      <tr v-for="row in visibleRows" :key="row.id" :class="{selected:allFiltered||selected.includes(row.id)}"><td v-if="tab==='environments'"><input type="checkbox" :aria-label="`选择环境 ${row.container_code}`" :disabled="busy||loading" :checked="allFiltered||selected.includes(row.id)" @change="toggle(row.id)"/></td><td><b>{{row.name}}</b><small>{{row.container_code}}</small></td><td>{{row.group||'未分组'}}</td><td><span class="mx-tag">{{row.site||'未知'}}</span></td>
      <template v-if="tab==='environments'"><td>{{row.shop?.name||'待识别'}}<small>{{row.shop?.external_id}}</small></td><td>{{row.account_names.map(accountNameText).join(' / ')||'—'}}</td><td :title="row.snapshot?.observed_at">{{display(row.snapshot?.active)}}</td><td :title="row.snapshot?.orders_total!=null?'管理订单－全部标签页显示数量':row.snapshot?.orders==null?'尚未采集订单数据':`近7天订单：${row.snapshot.window_start} — ${row.snapshot.window_end}`">{{display(row.snapshot?.orders_total ?? row.snapshot?.orders)}}</td><td><span :class="{'mx-activity-normal':row.activity_status==='normal','mx-activity-closed':row.activity_status==='closed'}">{{row.activity_status==='normal'?'正常':row.activity_status==='closed'?'封店':'未检测'}}</span></td><td><span class="mx-state" :class="row.latest_item?.status">{{label(row.latest_item?.stage)}}</span><small>{{label(row.latest_item?.submission)}}</small></td><td>{{label(row.latest_item?.collection_status)}}<small v-if="row.snapshot?.stale">数据超过24小时</small></td></template>
      <template v-else><td>{{display(row.snapshot?.active)}}</td><td>{{display(row.snapshot?.with_views)}}</td><td>{{display(row.snapshot?.zero_views)}}</td><td>{{display(row.snapshot?.impressions)}}</td><td>{{display(row.snapshot?.clicks)}}</td><td>{{percent(row.snapshot?.ctr)}}</td><td :title="row.snapshot?.gmv_scope==='all_products'?'最近30天全部商品GMV':'在售商品已知GMV小计'">{{display(row.snapshot?.gmv)}} {{row.snapshot?.gmv!=null?row.snapshot.currency:''}}</td><td :title="row.snapshot?.sell_through_rate==null?'尚无商品销量数据':'有销量商品数 ÷ 已采集销量的商品数'">{{percent(row.snapshot?.sell_through_rate)}}</td><td>{{display(row.snapshot?.violations_score)}}</td><td>{{row.snapshot?.observed_at?new Date(row.snapshot.observed_at).toLocaleString():'未采集'}}<small v-if="row.snapshot?.stale">已过期</small></td></template>
      <td class="mx-row-actions"><button v-if="tab==='environments'" @click="openHistory(row)">运行记录</button><button v-else :disabled="!row.shop" @click="showShop(row)">商品明细</button><button :aria-label="`查看 ${row.name} 的秒杀活动`" @click="flashItemId=null;flashEnvironment=row">秒杀活动</button></td></tr>
      <tr v-if="!rows.length"><td :colspan="tab==='environments'?12:14" class="mx-empty">{{loading?'正在加载…':'暂无环境，请启动连接器，并在设备管理中配置连接和同步环境'}}</td></tr></tbody></table></div>
    <footer class="mx-pagination"><span>共 {{total}} 个环境</span><label>每页 <select v-model.number="size" @change="page=1;loadRows()"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label><button :disabled="page<=1||loading" @click="page--;loadRows()">上一页</button><span>{{page}} / {{pages}}</span><button :disabled="page>=pages||loading" @click="page++;loadRows()">下一页</button></footer>
  </section>
  <div v-if="tab==='automation'" class="mx-automation">
    <section class="mx-panel mx-auto-panel"><div class="mx-summary mx-operation-heading"><h2>操作方案 <small>{{operations.length}}</small></h2><a v-if="!readOnly" class="mx-strategy-link" href="/supply?tab=strategies">管理货盘策略 ↗</a><button class="primary" :disabled="readOnly||busy||!config.enabled||(!access.collect_enabled&&!access.listing_enabled)" @click="editOperation()">＋ 新建方案</button></div><p class="mx-panel-description">配置操作与货盘策略，供运营计划复用。</p>
      <div class="mx-auto-table-wrap"><table class="mx-auto-table mx-operation-table"><thead><tr><th>方案名称</th><th>执行操作</th><th>MY 货盘策略</th><th>关联计划</th><th>操作</th></tr></thead><tbody><tr v-for="o in operations" :key="o.id"><td><b :title="o.name">{{o.name}}</b></td><td>{{taskNames(o.tasks)}}</td><td><span :title="strategies.find(s=>s.id===Number(o.strategies.MY))?.name">{{o.tasks.includes('listing.catalog')?(strategies.find(s=>s.id===Number(o.strategies.MY))?.name||'未配置'):'—'}}</span></td><td>{{o.plans.length}} 个</td><td><button class="mx-text-button" :aria-label="`编辑操作方案 ${o.name}`" @click="editOperation(o)">{{readOnly?'查看':'编辑'}}</button></td></tr><tr v-if="!operations.length"><td colspan="5" class="mx-list-empty">暂无操作方案，点击右上角新建。</td></tr></tbody></table></div>
    </section>
    <section class="mx-panel mx-auto-panel"><div class="mx-summary"><h2>运营计划 <small>{{plans.length}}</small></h2><button class="primary" :disabled="readOnly||busy||!config.enabled||!operations.length" @click="edit()">＋ 新建计划</button></div><p class="mx-panel-description">固定店铺与执行时间，按计划自动运营。</p>
      <div class="mx-auto-table-wrap"><table class="mx-auto-table mx-plan-table"><thead><tr><th>计划 / 设备</th><th>操作方案</th><th>店铺</th><th>执行时间（UTC+8）</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="p in plans" :key="p.id"><td><b :title="p.name">{{p.name}}</b><small :title="devices.find(d=>d.id===p.agent_id)?.name">{{devices.find(d=>d.id===p.agent_id)?.name||'设备不可用'}}</small></td><td><span :title="p.operation_name">{{p.operation_name}}</span></td><td>{{p.environment_ids.length}} 个</td><td>{{p.schedule_mode==='interval'?`每 ${p.interval_hours} 小时`:`每日 ${p.time}`}}<small>{{p.next_fire_at?`下次 ${timeText(p.next_fire_at)}`:'定时已暂停'}}</small></td><td><span class="mx-status-pill" :class="{enabled:p.scheduled}">{{p.scheduled?'已启用':'已暂停'}}</span><small v-if="p.last_fire">{{({created:'已创建运行',missed:'已错过',skipped_busy:'前次未结束',failed:'预检失败',preparing:'准备中',cancelled_changed:'配置已修改'} as any)[p.last_fire.status]}}</small></td><td><div class="mx-auto-actions"><button :disabled="readOnly||busy||!config.enabled" @click="preview(p)">立即运行</button><button :disabled="readOnly||busy||!config.enabled" @click="togglePlan(p)">{{p.scheduled?'暂停':'启用'}}</button><button @click="edit(p)">{{readOnly?'查看':'编辑'}}</button></div></td></tr><tr v-if="!plans.length"><td colspan="6" class="mx-list-empty">{{operations.length?'暂无运营计划，点击右上角新建。':'先在左侧创建操作方案，再添加运营计划。'}}</td></tr></tbody></table></div>
    </section>
  </div>
  <div v-if="tab!=='data'" class="mx-bottom">
    <section class="mx-panel mx-runs-panel"><div class="mx-summary"><h2>全部运行记录 <small>{{runTotal}}</small></h2><button :disabled="busy" @click="perform(loadRuns)">刷新</button></div>
      <div class="mx-runs-scroll"><table class="mx-runs-table"><thead><tr><th>运行 / 操作</th><th>设备 / 范围</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="r in runs" :key="r.id" :class="{'is-current':run?.id===r.id}"><td><b>#{{r.id}} · {{taskNames(r.tasks)}}</b><small>{{r.plan_name||'临时执行'}} · {{r.trigger==='scheduled'?'定时':'手动'}}</small></td><td>{{r.device_name||`设备 #${r.agent_id}`}}<small class="mx-run-scope">{{runEnvironmentScope(r.items)}}</small></td><td><span class="mx-state" :class="r.status">{{label(r.status)}}</span></td><td>{{timeText(r.created_at)}}</td><td><div class="mx-row-actions"><button :disabled="busy" @click="openRun(r)">详情</button></div></td></tr><tr v-if="!runs.length"><td colspan="5" class="mx-list-empty">暂无运行记录</td></tr></tbody></table></div>
      <footer class="mx-pagination"><span>共 {{runTotal}} 次运行</span><button :disabled="busy||runPage<=1" @click="runPage--;perform(loadRuns)">上一页</button><span>{{runPage}} / {{runPages}}</span><button :disabled="busy||runPage>=runPages" @click="runPage++;perform(loadRuns)">下一页</button></footer>
    </section>
  </div>
  </template>
</section>
<MatrixRunHistory v-if="dialog==='history'&&access.enabled" :scope="historyScope" :runs="historyRuns" :total="historyTotal" :page="historyPage" :loading="historyLoading" :error="historyError" :scroll-top="historyScroll" @close="close" @refresh="loadHistory" @page="changeHistoryPage" @scroll="historyScroll=$event" @open="(value,itemId)=>openRun(value,itemId,true)"><template #legacy><slot name="legacy"/></template></MatrixRunHistory>
<MatrixRunViewer v-if="['run','resolve'].includes(dialog)&&access.enabled&&run&&flashItemId===null&&!flashEnvironment" :run="run" :events="events" :item-id="runItemId" v-model:view="runView" :loading="logsLoading" :error="logsError" :more="logsMore" :busy="busy" :from-history="runFromHistory" :can-manage="!!canManageRun(run)" :resolving="dialog==='resolve'" :notice="logNotice" @close="close" @back="backToHistory" @select="selectRunItem" @refresh="logs" @copy="copyLogs" @resolve="resolveItem" @flash-sales="flashItemId=$event">
<template #resolution><p v-if="error" class="error" role="alert">{{error}}</p><form class="mx-form" @submit.prevent="saveResolution"><p>请核对原环境及本次文件的真实平台结果；未知提交不得直接取消或重复导入。</p><label>处理方式<select v-model="resolution.action"><option value="confirm-submitted">确认未知部分已提交</option><option value="confirm-not-submitted">确认未提交并取消，不再执行</option><option value="retry" :disabled="run?.stop_requested||run?.owner_id!==user.id">确认未提交，再重试原文件</option><option value="retransmit" :disabled="run?.stop_requested||run?.owner_id!==user.id">仅重传原采集数据</option><option value="cancel">取消明确未提交项</option></select></label><button :disabled="busy" class="primary">保存核对结果</button></form></template>
</MatrixRunViewer>
<div v-if="dialog&&!['run','resolve','history'].includes(dialog)&&access.enabled" class="modal-backdrop mx-backdrop" @click.self="dismiss"><section :key="dialog" v-dialog-focus="{close:dismiss,busy}" class="modal-card mx-dialog" :class="{'mx-dialog-devices':dialog==='devices','mx-dialog-override':dialog==='override','mx-dialog-manual':dialog==='manual','mx-dialog-editor':['operation','plan'].includes(dialog),'mx-dialog-preview':dialog==='preview'}" role="dialog" aria-modal="true" aria-labelledby="matrix-dialog-title"><div class="mx-summary"><h2 id="matrix-dialog-title">{{({devices:'设备管理',plan:editing?'编辑运营计划':'新建运营计划',deletePlan:'删除运营计划',operation:operationEditing?'编辑操作方案':'新建操作方案',deleteOperation:'删除操作方案',manual:'临时批量执行',preview:'执行预览',run:'运行详情',history:historyScope?'店铺运行记录':'全部运行记录',shop:'商品明细',resolve:'人工核对',override:'批量设置站点/活跃',releases:'签名升级与插件分发'} as any)[dialog]}}</h2><button :disabled="busy" aria-label="关闭弹窗" @click="dialog==='deletePlan'?dialog='plan':dialog==='deleteOperation'?dialog='operation':close()">关闭</button></div>
<div v-if="feedbackMessage" class="mx-feedback" :class="{'is-error':feedbackSource==='error'}" :role="feedbackSource==='error'?'alert':'status'" aria-live="polite"><span>{{feedbackMessage}}</span><button v-if="feedbackSource==='sync'&&syncHelp" @click="openDevices">前往设备管理</button></div>
<template v-if="dialog==='devices'">
  <p class="mx-devices-intro">这里只显示你自己的电脑。连接 HubStudio 并同步环境后，即可回到环境列表操作。</p>
  <MatrixDevices :token="token" :user-id="user.id" :devices="devices" :config="config" :busy="busy" :read-only="readOnly" @save="saveConnection" @command="command"/>
</template>
<form v-if="dialog==='plan'" class="mx-form" @submit.prevent="savePlan">
<label>计划名称<input v-model="editor.name" required maxlength="120"/></label>
<label>操作方案<select v-model="editor.operation_id" required @change="changePlanOperation"><option v-for="o in operations" :key="o.id" :value="o.id">{{o.name}} · {{taskNames(o.tasks)}}</option></select></label>
<label>执行设备<select v-model="editor.agent_id" required @change="changePlanDevice"><option v-for="d in ownDevices" :key="d.id" :value="d.id">{{d.name}}</option></select></label>
<div class="mx-plan-shops"><span>计划执行店铺</span><PlanShopSelect v-model="editor.environment_ids" :options="planShops" :loading="planShopsLoading" :error="planShopsError" @retry="loadPlanShops()"/><small>固定名单，最多 1000 个环境。立即运行和定时执行均使用此名单。</small></div>
<label>调度方式<select v-model="editor.schedule_mode"><option value="daily">每日执行</option><option value="interval" :disabled="operations.find(o=>o.id===editor.operation_id)?.tasks?.join(',')!=='promotion.flash_sale.renew'">按间隔执行（仅秒杀续期方案）</option></select></label>
<label v-if="editor.schedule_mode!=='interval'">每日执行时间（UTC+8）<input v-model="editor.time" type="time" required/></label><label v-else>检查间隔<select v-model="editor.interval_hours"><option v-for="h in [2,4,6]" :key="h" :value="h">每 {{h}} 小时（UTC+8 整点）</option></select></label><p v-if="editor.schedule_mode==='interval'&&(operations.find(o=>o.id===editor.operation_id)?.flash_sale?.threshold_hours||12)<=editor.interval_hours" class="error">临期阈值不大于检查间隔，可能错过临期窗口。</p><label><input v-model="editor.scheduled" type="checkbox"/>启用定时执行</label>
<p>设备离线或暂停时错过不补跑；同一计划前次未结束则跳过；设备忙时按队列串行执行。暂停计划只停止未来触发。</p>
<div class="mx-actions"><button class="primary" :disabled="readOnly||busy||planShopsLoading||!!planShopsError||!editor.operation_id||!editor.environment_ids.length">保存计划</button><button v-if="editing&&!readOnly" type="button" class="mx-danger" :disabled="busy" @click="dialog='deletePlan'">删除计划</button></div></form>
<template v-if="dialog==='deletePlan'"><p>确定删除运营计划「{{editor.name}}」？未来不再定时触发，已创建的运行和历史记录保留。</p><div class="mx-actions"><button :disabled="busy" @click="dialog='plan'">取消</button><button class="mx-danger" :disabled="busy" @click="deletePlan">确认删除</button></div></template>
<form v-if="dialog==='operation'" class="mx-form" @submit.prevent="saveOperation">
<label>操作方案名称<input v-model="operationEditor.name" required maxlength="120"/></label><fieldset><legend>执行任务</legend><label><input v-model="operationEditor.tasks" type="checkbox" value="listing.catalog" :disabled="!access.listing_enabled&&!operationEditor.tasks.includes('listing.catalog')"/>自动上品</label><label><input v-model="operationEditor.tasks" type="checkbox" value="shop.collect" :disabled="!access.collect_enabled&&!operationEditor.tasks.includes('shop.collect')"/>店铺采集</label><label><input v-model="operationEditor.tasks" type="checkbox" value="promotion.flash_sale.renew"/>秒杀续期</label></fieldset>
<label v-if="operationEditor.tasks.includes('promotion.flash_sale.renew')">临期阈值（小时）<input v-model.number="operationEditor.flash_sale.threshold_hours" type="number" min="6" max="36" required/><small>默认12小时，可调6～36小时；新活动持续72小时。临期活动先终止再重新创建，原剩余时长不会叠加。自然到期活动只提示用户选择。</small></label>
<template v-if="operationEditor.tasks.includes('listing.catalog')"><label>马来西亚跨境货盘策略（MYR）<select v-model="operationEditor.strategies.MY" required><option :value="null">请选择货盘策略</option><option v-for="s in listingStrategies" :key="s.id" :value="s.id">{{s.name}} · {{s.link_count}} 链接 · {{s.sku_count}} SKU · {{s.price}}</option></select></label><a v-if="!readOnly" href="/supply?tab=strategies">管理货盘策略 ↗</a></template>
<p v-if="operationEditor.plans?.length">保存后将影响以下计划的未来运行：{{operationEditor.plans.map((p:any)=>p.name).join('、')}}。已创建运行继续使用原参数。</p>
<div class="mx-actions"><button class="primary" :disabled="readOnly||busy||!operationEditor.tasks.length">保存操作方案</button><button v-if="operationEditing&&!readOnly" type="button" class="mx-danger" :disabled="busy||!!operationEditor.plans?.length" @click="dialog='deleteOperation'">删除操作方案</button></div></form>
<template v-if="dialog==='deleteOperation'"><p>确定删除操作方案「{{operationEditor.name}}」？</p><div class="mx-actions"><button :disabled="busy" @click="dialog='operation'">取消</button><button class="mx-danger" :disabled="busy" @click="deleteOperation">确认删除</button></div></template>
<form v-if="dialog==='manual'" class="mx-form mx-manual-form" @submit.prevent="submitManual">
<p class="mx-manual-intro">已选择 <b>{{selectedCount}}</b> 个环境，系统自动分配执行设备。</p>
<fieldset class="mx-manual-tasks" :disabled="busy"><legend>选择操作</legend><div class="mx-task-options"><label><input v-model="manual.tasks" type="checkbox" value="listing.catalog" :disabled="!access.listing_enabled||!config.listing_enabled"/>1. 自动上品</label><label><input v-model="manual.tasks" type="checkbox" value="shop.collect" :disabled="!access.collect_enabled"/>3. 店铺采集</label><label><input v-model="manual.tasks" type="checkbox" value="promotion.flash_sale.renew"/>2. 秒杀续期</label></div></fieldset>
<label v-if="manual.tasks.includes('promotion.flash_sale.renew')">临期阈值（小时）<input v-model.number="manual.flash_sale.threshold_hours" type="number" min="6" max="36" required/><small>临期活动会先终止再重新创建，原剩余时长不会叠加。自然到期活动只生成提示，由你另行选择。</small></label>
<template v-if="manual.tasks.includes('listing.catalog')"><label>马来西亚跨境货盘策略（MYR）<select v-model="manual.strategies.MY" :disabled="busy" required><option :value="null">请选择货盘策略</option><option v-for="s in listingStrategies" :key="s.id" :value="s.id">{{s.name}} · {{s.link_count}} 链接 · {{s.price}}</option></select></label></template>
<p>{{manual.tasks.includes('listing.catalog')?'执行后将使用所选货盘策略向 TikTok 提交商品。':manual.tasks.includes('promotion.flash_sale.renew')?'将检查商家秒杀活动并续期临期活动，新活动持续72小时。':'执行后将采集所选环境的店铺数据。'}}</p>
<ul v-if="previewData?.manual&&previewData.errors.length" class="error"><li v-for="(message,i) in previewData.errors" :key="i">{{message}}</li></ul>
<div class="mx-manual-footer"><button type="button" :disabled="busy" @click="close">取消</button><button class="primary" :disabled="busy||!manual.tasks.length">{{busy?'提交中…':'创建并执行'}}</button></div></form>
<template v-if="dialog==='preview'&&previewData"><p>{{previewData.manual?'临时批量执行':'计划立即运行'}} · {{taskNames(previewData.tasks)}} · {{previewData.environment_count}} 个环境 · {{previewBatches.length}} 台设备</p><ul v-if="previewData.errors.length" class="error"><li v-for="(e,i) in previewData.errors" :key="i">{{e}}</li></ul><section v-for="batch in previewBatches" :key="batch.agent_id" class="mx-preview-batch"><h3>{{devices.find(d=>d.id===batch.agent_id)?.name||`设备 #${batch.agent_id}`}} <small>{{batch.environments.length}} 个环境</small></h3><div v-for="(s,site) in batch.strategies" :key="site" class="mx-device-card"><b>{{site}} · {{s.name}}</b><span>每店 {{s.link_count}} 个商品组 · {{s.sku_count}} SKU · 售价 {{s.price}} MYR</span></div><div class="mx-preview-env"><span v-for="e in batch.environments" :key="e.id">{{e.name}} / {{e.site}} / {{e.container_code}}</span></div></section><p>{{previewData.tasks.includes('listing.catalog')?'本次执行将使用已冻结的环境和货盘参数，并向 TikTok 提交商品。':previewData.tasks.includes('promotion.flash_sale.renew')?'本次会终止并复制临期商家秒杀活动，创建72小时的新活动；自然到期活动仅提示。':'本次仅采集店铺数据，不提交商品。'}}</p><div class="mx-manual-footer"><button :disabled="busy" @click="previewData.manual?dialog='manual':close()">{{previewData.manual?'返回调整':'取消'}}</button><button class="primary" :disabled="busy||previewData.errors.length>0" @click="execute">{{busy?'提交中…':'确认创建运行'}}</button></div></template>
<template v-if="dialog==='shop'&&detail"><p>快照 #{{detail.snapshot?.id||'—'}} · {{detail.snapshot?.observed_at||'尚未采集'}}</p><p v-if="['product_management','product_analysis'].includes(detail.snapshot?.collection_kind)">在售 {{display(detail.snapshot.active)}} 个商品 · 浏览次数 {{display(detail.snapshot.views)}} · SKU {{display(detail.snapshot.sku_count)}} 条 · {{detail.snapshot.views_covered}}/{{detail.snapshot.active}} 个商品提供浏览次数。浏览次数取平台近28天字段，未推断精确起止日期。</p><p v-if="detail.snapshot?.window_start">{{detail.snapshot.window_start}} — {{detail.snapshot.window_end}} · {{detail.snapshot.timezone}}<span v-if="detail.snapshot.collection_kind==='product_analysis'"> · 最近30天（含今天，结束时间为次日零点）</span></p><p v-if="detail.snapshot?.collection_kind==='product_analysis'&&detail.snapshot?.traffic_unknown>0">分析数据覆盖 {{detail.snapshot.traffic_covered}}/{{detail.snapshot.active}} 个在售商品 · 已知曝光 {{display(detail.snapshot.known_impressions)}} · 已知点击 {{display(detail.snapshot.known_clicks)}}。其余商品经ID查询后平台无记录，指标保持未知。</p><div class="mx-notice"><span v-for="(state,section) in detail.snapshot?.sections" :key="section">{{({identity:'执行目标',products:'商品分页与SKU',traffic:'商品流量',metrics:'经营指标',health:'健康状态'} as any)[section]}}：{{state==='completed'?'完成':state==='unsupported'?'暂不支持':'失败'}}　</span><p v-for="(reason,section) in detail.snapshot?.reasons" :key="section">{{reason}}</p></div><form class="mx-actions" @submit.prevent="detailPage=1;loadDetail()"><input v-model="detailQ" placeholder="商品名 / 商品ID" aria-label="搜索商品"/><button>搜索</button><button type="button" :disabled="busy||!detail.snapshot" @click="downloadProducts">导出商品及SKU CSV</button></form><div class="mx-product-details"><table><thead><tr><th>商品ID</th><th>名称</th><th>在售</th><th>浏览次数</th><th>曝光</th><th>点击</th><th>点击率</th><th>GMV</th><th>成交件数</th><th>SKU 数量</th><th>SKU 明细</th></tr></thead><tbody><tr v-for="p in detail.products" :key="p.external_id"><td>{{p.external_id}}</td><td class="mx-product-name">{{p.name}}</td><td>{{p.active?'是':'否'}}</td><td :title="p.views_reason||''">{{display(p.views)}}</td><td :title="p.traffic_reason||''">{{display(p.impressions)}}<small v-if="p.traffic_reason">平台无分析记录</small></td><td :title="p.traffic_reason||''">{{display(p.clicks)}}</td><td>{{percent(p.impressions>0&&p.clicks!=null?p.clicks/p.impressions:null)}}</td><td :title="p.traffic_reason||''">{{display(p.gmv)}} {{p.gmv!=null?detail.snapshot?.currency:''}}</td><td>{{display(p.sales_count)}}</td><td>{{display(p.sku_count)}}</td><td><details v-if="p.skus?.length" @toggle="expandedProductSkus[p.external_id]=($event.target as HTMLDetailsElement).open"><summary>查看 {{p.skus.length}} 条 SKU</summary><table v-if="expandedProductSkus[p.external_id]" class="mx-sku-details"><thead><tr><th>SKU ID</th><th>规格</th><th>商家SKU</th><th>库存</th><th>原价（MYR）</th><th>促销价（MYR）</th></tr></thead><tbody><tr v-for="(sku,i) in p.skus" :key="i"><td>{{sku.external_id||'—'}}</td><td>{{sku.name||'未单独展示'}}</td><td>{{sku.seller_sku||'—'}}</td><td>{{display(sku.stock)}}</td><td>{{sku.price}}</td><td>{{sku.sale_price||'—'}}</td></tr></tbody></table></details><span v-else>—</span></td></tr></tbody></table></div><div class="mx-pagination"><button :disabled="detailPage<=1" @click="detailPage--;loadDetail()">上一页</button><span>{{detailPage}} · 共{{detailTotal}}项</span><button :disabled="detailPage*50>=detailTotal" @click="detailPage++;loadDetail()">下一页</button></div></template>

<form v-if="dialog==='override'" class="mx-form" @submit.prevent="saveOverrides"><p>对已选 {{selectedCount}} 个环境设置站点或活跃状态，选择“不修改”将保留原值。共享环境的修改会同步影响其他使用者。</p><label>站点<select v-model="overrideSite"><option value="keep">不修改</option><option>MY</option><option value="">清除人工覆盖</option></select></label><label>活跃<select v-model="overrideActivity"><option value="keep">不修改</option><option value="normal">正常</option><option value="closed">封店</option><option value="unchecked">未检测</option></select></label><button class="primary" :disabled="busy||(overrideSite==='keep'&&overrideActivity==='keep')">保存</button></form>

</section></div>
</template>

<style scoped>
.matrix th .mx-sort-header{display:flex;align-items:center;justify-content:flex-start;gap:6px;width:100%;padding:0;border:0;background:transparent;color:inherit;font:inherit;text-align:left;white-space:nowrap;cursor:pointer}
.mx-sort-header span{font-size:13px;color:inherit}
.matrix th .mx-sort-header:hover{color:#7050dc}
.matrix th[aria-sort="ascending"] .mx-sort-header,.matrix th[aria-sort="descending"] .mx-sort-header{color:#7050dc;font-weight:600}
.mx-sort-header:focus-visible{outline:2px solid #7050dc;outline-offset:5px;border-radius:2px}

.mx-product-details{overflow:auto;max-height:55vh}.mx-product-details .mx-product-name{min-width:160px;max-width:260px;white-space:normal}.mx-sku-details{margin-top:10px}.mx-product-details summary{cursor:pointer;color:#7053c6}

.mx-automation{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:start;gap:16px;margin-top:16px}
.mx-auto-panel{min-width:0;overflow:hidden}
.mx-panel-description{margin:0;padding:12px 16px;color:#8a92a2;font-size:12px;line-height:1.7;border-bottom:1px solid #f0f1f5}
.mx-auto-table-wrap{overflow:auto;max-height:420px}
.mx-auto-table{table-layout:auto}.mx-operation-table{min-width:470px}.mx-plan-table{min-width:640px}
.matrix .mx-auto-table th,.matrix .mx-auto-table td{padding:12px;font-size:12px;vertical-align:middle;white-space:nowrap}
.matrix .mx-auto-table th{font-size:11px}.mx-auto-table td>b,.mx-auto-table td>span:not(.mx-status-pill),.mx-auto-table td>small{display:block;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mx-auto-table td>b{font-weight:500}.mx-auto-table td>small{max-width:180px}.mx-auto-table .mx-auto-actions{margin:0;flex-wrap:nowrap;gap:10px}
.mx-status-pill{flex:none;border-radius:4px;padding:2px 6px;font-size:11px;color:#8a92a2;background:#f2f3f7}
.mx-status-pill.enabled{background:#edf8f2;color:#33946c}
.mx-auto-actions{display:flex;gap:14px;margin-top:3px}
.matrix .mx-auto-actions button,.matrix .mx-text-button{min-height:26px;padding:2px 0;border:0;background:transparent;color:#7053c6;font-size:12px}
.mx-operation-heading .mx-strategy-link{margin-left:auto;padding:7px 10px;border:1px solid #e1e4ee;border-radius:6px;color:#7053c6;background:#fff;font-size:12px;line-height:18px;text-decoration:none;white-space:nowrap}.mx-operation-heading .mx-strategy-link:hover{background:#faf8ff;border-color:#c6bbe8}.matrix .mx-operation-heading button:first-of-type{margin-left:0}
.mx-list-empty{padding:36px 16px!important;text-align:center;color:#9aa3b2;font-size:12px;justify-content:center}
.mx-summary h2 small{margin-left:5px;font-size:11px;font-weight:400;color:#9aa3b2}
.mx-runs-panel{display:flex;flex-direction:column;min-width:0;overflow:hidden}
.mx-runs-scroll{flex:1;overflow:auto;max-height:390px}
.mx-runs-table{width:100%;border-collapse:collapse}.mx-runs-table th,.mx-runs-table td{padding:12px 14px;font-size:12px;text-align:left;border-bottom:1px solid #edf0f5;white-space:nowrap}
.mx-runs-table th{font-size:11px;font-weight:500;color:#8a92a2;background:#fafbfe}.mx-runs-table td b{font-size:12px;font-weight:500}.mx-runs-table td small{display:block;margin-top:5px;font-size:11px;color:#8a92a2}
.mx-runs-table td .mx-run-scope{max-width:480px;white-space:normal;overflow-wrap:anywhere}
.mx-runs-table tr.is-current{background:#f8f6fd}.mx-runs-table .mx-row-actions{display:flex;gap:10px}.mx-runs-table .mx-row-actions button{min-height:26px;padding:2px 0;border:0;background:transparent;color:#7053c6;font-size:12px}
.mx-runs-panel .mx-pagination{border-top:1px solid #edf0f5}
.mx-dialog.mx-dialog-manual{width:min(600px,calc(100vw - 32px))}.mx-dialog.mx-dialog-editor{width:min(680px,calc(100vw - 32px))}.mx-dialog.mx-dialog-preview{width:min(780px,calc(100vw - 32px))}
.mx-manual-intro{margin:0;color:#7a8394;font-size:13px}.mx-manual-intro b{color:#6043d4}
.mx-dialog .mx-manual-tasks{display:block;margin:0;padding:0;border:0}
.mx-manual-tasks legend{margin-bottom:10px;font-size:12px}.mx-task-options{display:flex;align-items:center;flex-wrap:wrap;gap:20px 36px;padding:16px;border-radius:8px;background:#f5f6fa}
.mx-dialog .mx-form .mx-task-options label{display:inline-flex;flex-direction:row;align-items:center;gap:9px;font-size:14px;font-weight:400;color:#4e5c71;cursor:pointer}
.mx-dialog .mx-task-options input[type=checkbox]{width:18px;height:18px}.mx-task-options label:has(input:disabled){opacity:.5;cursor:not-allowed}
.mx-manual-footer{display:flex;justify-content:flex-end;gap:10px;padding-top:16px;border-top:1px solid #edf0f5}.mx-preview-batch{margin-top:16px;border:1px solid #e4e6ee;border-radius:8px}.mx-preview-batch h3{display:flex;justify-content:space-between;margin:0;padding:12px 14px;font-size:13px;background:#fafbfe;border-radius:8px 8px 0 0}.mx-preview-batch h3 small{font-size:11px;color:#8a92a2;font-weight:400}.mx-preview-batch>.mx-device-card{margin:12px}

.mx-feedback{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 14px;margin:0 0 12px;background:#f2f5fc;border:1px solid #e5e7ee;border-radius:6px;color:#626d85;font-size:12px}
.mx-feedback button{flex-shrink:0}
.mx-feedback.is-error{background:#fff2f2;border-color:#f0d1d4;color:#b84a51}


.mx-dialog.mx-dialog-override{width:min(520px,96vw)}
.mx-dialog-override .mx-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.mx-dialog-override .mx-form>p{grid-column:1 / -1}
.mx-dialog-override .mx-form>button{grid-column:1 / -1;justify-self:end}

.mx-access-state{padding:36px 24px;border:1px solid #e5e7ee;border-radius:8px;background:#fff;font-size:13px;color:#7b8496}.mx-access-state h2{font-size:16px;color:#4e5669}.mx-access-state p{line-height:1.8}

.matrix{--mx-accent:#6043d4;--mx-teal:#008d81;--mx-line:#e5e7ee;min-width:0;background:#f6f7fb;color:#34394c}
.matrix.page{width:100%;max-width:none;margin:0;padding:16px 20px 24px;box-sizing:border-box}
.matrix *,.mx-dialog *{box-sizing:border-box}
.mx-summary,.mx-actions,.mx-toolbar,.mx-pagination,.mx-execute{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.matrix button,.mx-dialog button{display:inline-flex;align-items:center;justify-content:center;gap:6px;flex:none;width:auto;min-height:34px;margin:0;padding:6px 11px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#596174;box-shadow:none;font:inherit;font-size:12px;line-height:20px;white-space:nowrap;cursor:pointer}
.matrix button:hover,.mx-dialog button:hover{border-color:#c7bfdf;background:#faf9fd;color:var(--mx-accent,#6043d4)}
.matrix button:disabled,.mx-dialog button:disabled{opacity:.45;cursor:not-allowed}
.matrix button:focus-visible,.mx-dialog button:focus-visible{outline:2px solid #7256e7;outline-offset:2px}
.matrix .primary,.mx-dialog .primary{border-color:#6043d4;background:#6043d4;color:#fff}
.matrix .primary:hover,.mx-dialog .primary:hover{border-color:#5235c1;background:#5235c1;color:#fff}
.matrix .mx-danger,.mx-dialog .mx-danger{color:#b84a51;border-color:#edcdd0;background:#fff}
.mx-tabs{display:flex;align-items:stretch;align-self:stretch;gap:20px;min-width:0;margin:0;padding:0;background:transparent}
.matrix .mx-tabs button{gap:7px;width:auto;min-width:0;min-height:44px;margin:0 0 -1px;padding:0 2px;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;color:#778092;font-size:13px;font-weight:500}
.matrix .mx-tabs button.active{border-bottom-color:#6043d4;background:transparent;color:#6043d4;font-weight:600}
.mx-tabs b{min-width:20px;padding:1px 6px;border-radius:10px;background:#ebeef3;color:#7a8292;text-align:center;font-size:10px;font-weight:600;line-height:16px}
.mx-tabs button.active b{background:#ede8fb;color:#6043d4}
.mx-device-count{margin-right:2px;padding-left:12px;border-left:1px solid #e0e3eb;color:#7a8292;font-size:12px;line-height:18px;white-space:nowrap}
.matrix .mx-device-button{min-height:30px;padding:4px 10px}
.mx-panel{min-width:0;overflow:hidden;border:1px solid var(--mx-line);border-radius:8px;background:#fff}
.mx-summary{min-height:54px;padding:10px 16px;border-bottom:1px solid var(--mx-line)}
.mx-summary>b,.mx-summary h2{margin:0;font-size:14px;font-weight:600}
.mx-summary span{color:#8a92a2;font-size:12px;line-height:20px}
.mx-summary button:first-of-type{margin-left:auto}
.mx-filters{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:0;padding:12px 16px 8px}
/* 筛选控件默认保持紧凑宽度，新增下拉框也不吸收整行剩余空间。 */
.matrix .mx-filters input,.matrix .mx-filters select{display:block;flex:0 1 144px;width:144px;min-width:0;max-width:144px;height:36px;min-height:36px;margin:0;padding:7px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#50586b;font:inherit;font-size:12px;font-weight:400;line-height:20px}
.matrix .mx-filters .mx-filter-search{flex-basis:240px;width:240px;max-width:240px}
.matrix .mx-filters .mx-filter-group{flex-basis:160px;width:160px;max-width:160px}
.mx-filters input::placeholder{color:#989fac}
.mx-filters input:focus,.mx-filters select:focus{outline:none;border-color:#9f8ade;box-shadow:0 0 0 2px #6043d412}
.mx-filter-actions{display:flex;align-items:center;flex:none;gap:8px}
.mx-filter-actions button{min-height:36px}
.mx-toolbar{gap:8px;padding:8px 16px 12px;border-bottom:1px solid var(--mx-line);font-size:12px}
.mx-toolbar button{min-height:32px;padding:5px 10px}
.matrix .mx-hide-names{background:#ede8fb;border-color:#ede8fb;color:#6043d4}
.matrix .mx-hide-names:hover{background:#e3daf8;border-color:#e3daf8}
.matrix .mx-hide-names[aria-pressed="true"]{background:#6043d4;border-color:#6043d4;color:#fff}
.matrix .mx-hide-names[aria-pressed="true"]:hover{background:#5235c1;border-color:#5235c1}
.matrix .mx-sync{background:#2563eb;border-color:#2563eb;color:#fff;font-weight:600}
.matrix .mx-sync:hover{background:#1d4ed8;border-color:#1d4ed8;color:#fff}
.mx-selected{margin-left:auto;color:#7e719f;font-size:12px;font-weight:500;white-space:nowrap}
.mx-table-wrap{min-width:0;overflow:auto;max-height:58vh}
.mx-table-wrap:has(input[type="checkbox"]){max-height:calc(58vh * 2 / 3)}
.matrix table,.mx-dialog table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:12px}
.mx-table-wrap table{min-width:1080px}
.matrix th,.matrix td,.mx-dialog th,.mx-dialog td{padding:10px 12px;border-bottom:1px solid #edf0f5;text-align:left;line-height:20px}
.matrix th,.mx-dialog th{position:sticky;top:0;z-index:1;background:#f8f9fc;color:#7b8496;font-size:11px;font-weight:500}
.matrix td small{display:block;margin-top:2px;color:#929aaa;font-size:10px;line-height:16px}
.matrix tr.selected{background:#f5f1fd}
.mx-activity-normal{color:#15803d;font-weight:600}
.mx-activity-closed{color:#dc2626;font-weight:600}
.mx-tag{padding:3px 6px;border-radius:4px;background:#efedf8;color:#7765a3}
.mx-row-actions button{min-height:26px;padding:2px 5px;border:0;background:transparent;color:#6043d4}
.matrix .mx-empty{padding:48px 16px;text-align:center;color:#9aa3b2;font-size:12px}
.mx-pagination{min-height:52px;padding:10px 16px;justify-content:flex-end;font-size:12px;color:#8a92a2}
.mx-pagination>span:first-child{margin-right:auto}
.mx-pagination select{display:inline-block;width:65px;height:32px;min-height:32px;margin:0;padding:4px 8px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;font:inherit}
.mx-pagination button{min-height:32px;padding:5px 10px}
.mx-bottom{display:grid;grid-template-columns:minmax(0,1fr);align-items:stretch;gap:16px;margin-top:16px}
.mx-operations{display:flex;flex-direction:column;gap:12px;padding:16px;min-height:320px}
.mx-operations h2{margin:0;font-size:14px;font-weight:600}
.mx-operations>p{margin:0;color:#8a92a2;font-size:12px;line-height:1.7}
.mx-operations a{color:#756296;font-size:12px}
.mx-plans{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));align-items:stretch;gap:10px;min-height:100px}
.matrix .mx-plans>.mx-empty{display:flex;align-items:center;justify-content:center;grid-column:1/-1;min-height:100px;margin:0;padding:16px 12px}
.mx-plans article{min-width:0;min-height:100px;padding:12px;border:1px solid #e5e3ee;border-radius:6px}
.mx-plan-heading{display:flex;align-items:center;gap:8px;justify-content:space-between}
.mx-plan-heading label{display:flex;align-items:center;min-width:0;flex:1;margin:0;cursor:pointer}
.mx-plan-heading label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mx-plan-schedule{display:inline-flex;align-items:center;margin-top:6px;padding:2px 7px;border-radius:4px;background:#f3f4f8;color:#778095;font-size:11px;line-height:1.7}
.mx-plans article.chosen{border-color:#a08bdb;background:#faf8ff}
.mx-plans label{font-size:13px;font-weight:600}
.mx-plans input{width:auto;margin:0 7px 0 0;accent-color:#6043d4}
.mx-plans button{min-height:24px;padding:1px 3px;border:0;background:transparent;color:#6043d4}
.mx-plans small{display:block;margin-top:8px;color:#8a92a2;font-size:11px;line-height:1.8}
.mx-execute{margin-top:auto;justify-content:space-between;padding-top:12px;border-top:1px solid #edf0f5;font-size:12px;color:#8a92a2}
.mx-data-summary{min-height:46px;margin-bottom:12px;padding:0;border:0;border-radius:0;background:transparent}
.mx-cards{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;margin-bottom:14px}
.mx-cards article{padding:14px 12px;border:1px solid var(--mx-line);border-radius:8px;background:#fff}
.mx-cards article.views,.mx-cards article.zero-views{position:relative;overflow:hidden;box-shadow:0 1px 3px #14213d0a}
.mx-cards small{display:block;margin-top:6px;color:#94a0b7;font-size:12px}
.mx-cards span{display:block;color:#8a92a2;font-size:11px}
.mx-cards strong{display:block;margin-top:7px;font-size:19px;font-weight:600;overflow-wrap:anywhere}
.mx-banner,.mx-notice{margin:0 0 12px;padding:9px 12px;border-radius:6px;font-size:12px;line-height:1.7}
.mx-banner{background:#fff8e8;color:#a08343}.mx-notice{background:#edf7f3;color:#397a65}.mx-notice p{margin:0}
.mx-pairing{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.mx-alert{margin:0 0 12px;font-size:12px}
.mx-backdrop{z-index:70;padding:16px}
.mx-dialog{display:block;width:min(1000px,calc(100vw - 32px));max-height:90vh;overflow:auto;padding:20px;border-radius:12px;background:#fff;color:#34394c;box-shadow:0 24px 70px #1d16464d}
.mx-dialog-devices{width:min(800px,calc(100vw - 32px))}
.mx-dialog>.mx-summary{min-height:0;margin-bottom:16px;padding:0 0 14px}
.mx-dialog .mx-summary h2{margin:0;font-size:15px}
.mx-device-card{display:flex;flex-direction:column;gap:8px;margin:10px 0;padding:14px;border:1px solid #e4e6ee;border-radius:8px;font-size:12px}
.mx-device-card small{color:#8a92a2;font-size:11px;line-height:1.6}
.mx-device-heading{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.mx-device-heading b{min-width:0;font-size:13px;font-weight:600;overflow-wrap:anywhere}
.mx-device-heading>small{margin-left:auto}
.mx-device-badge{padding:1px 6px;border-radius:4px;background:#f0f1f5;color:#929aaa;font-size:10px;line-height:18px}
.mx-device-badge.is-online{background:#eaf7f0;color:#31916a}
.mx-device-connection{display:grid;grid-template-columns:86px minmax(0,1fr) auto;align-items:center;gap:6px 8px;margin:4px 0}
.mx-dialog .mx-device-connection label{margin:0;color:#737b8d;font-size:12px;font-weight:400}
.mx-device-connection small{grid-column:2/-1}
.mx-device-connection button{min-height:36px}
.mx-device-footer{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding-top:10px;border-top:1px solid #eff0f5}
.mx-device-footer button{min-height:30px;padding:4px 9px;font-size:11px}
.mx-devices-empty{padding:24px 12px;text-align:center}
.mx-dialog input:not([type=checkbox]):not([type=radio]),.mx-dialog select,.mx-dialog textarea{width:100%;min-width:0;margin:0;padding:7px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#50586b;font:inherit;font-size:12px;line-height:20px}
.mx-dialog input:not([type=checkbox]):not([type=radio]),.mx-dialog select{height:36px}
.mx-dialog input[type=checkbox],.mx-dialog input[type=radio]{display:inline-block;flex:none;width:14px;height:14px;margin:0;padding:0;accent-color:#6043d4}
.mx-form{display:flex;flex-direction:column;gap:16px}
.mx-dialog .mx-form label{display:flex;flex-direction:column;gap:7px;margin:0;font-size:12px;font-weight:500}
.mx-dialog .mx-form label:has(>input[type=checkbox]){flex-direction:row;align-items:center}
.mx-form fieldset{display:flex;flex-wrap:wrap;gap:20px;margin:0;padding:12px;border:1px solid #e1e7ec;border-radius:6px}
.mx-dialog .mx-form fieldset label{display:inline-flex;flex-direction:row;align-items:center}
.mx-plan-shops{display:flex;flex-direction:column;gap:7px;font-size:12px}.mx-plan-shops>small{line-height:1.6}
.mx-form textarea{resize:vertical}.mx-form small{max-height:90px;overflow:auto;overflow-wrap:anywhere;color:#8a92a2;font-size:11px}
.mx-preview-env{display:flex;flex-direction:column;gap:8px;max-height:240px;overflow:auto;padding:12px;font-size:12px}
.mx-state.succeeded{color:#31916a}.mx-state.awaiting_attention,.mx-state.failed{color:#b84a51}.mx-state.running{color:#7762bb}
@media(max-width:1500px){.mx-cards{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:1100px){.mx-bottom{grid-template-columns:1fr}}
@media(max-width:700px){
 .mx-automation{grid-template-columns:1fr}
 .matrix.page{padding:12px}
 .mx-tabs{gap:20px}.matrix .mx-tabs button{min-height:40px}
 .mx-device-count{padding-left:8px;font-size:11px}
 .mx-summary{gap:6px 10px;padding:10px 12px}.mx-summary span{font-size:11px}
 .mx-filters{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px 12px 8px}
 .matrix .mx-filters input,.matrix .mx-filters select,.matrix .mx-filters .mx-filter-group{width:100%;min-width:0;max-width:none}
 .matrix .mx-filters .mx-filter-search{grid-column:1/-1;width:100%;min-width:0;max-width:none}
 .mx-filter-actions{width:100%}.mx-filter-actions button{flex:1}
 .mx-toolbar{gap:6px;padding:8px 12px 12px}.mx-toolbar button{font-size:11px;padding:4px 8px}
 .mx-pagination{gap:6px;padding:10px 12px}.mx-pagination>span:first-child{width:100%;margin:0}
 .mx-cards{grid-template-columns:repeat(2,minmax(0,1fr))}
 .mx-dialog{padding:16px}.mx-device-connection{grid-template-columns:minmax(0,1fr) auto}.mx-device-connection label,.mx-device-connection small{grid-column:1/-1}
 .mx-device-heading>small{width:100%;margin:0}.mx-device-footer>.mx-actions{width:100%}
 .matrix .mx-sync{background:#2563eb;border-color:#2563eb;color:#fff;font-weight:600}
.matrix .mx-sync:hover{background:#1d4ed8;border-color:#1d4ed8;color:#fff}
.mx-selected{font-size:11px}
}
.mx-dialog .mx-devices-intro{margin:-3px 0 16px;color:#727c8f;font-size:12px;line-height:1.7}
.mx-company-settings{margin-bottom:18px;padding:12px 14px;border:1px solid #ebe7f3;border-radius:8px;background:#fbfaff}
.mx-section-heading{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px 12px}
.mx-section-heading h3{display:flex;align-items:center;gap:6px;margin:0;color:#4c5264;font-size:12px;font-weight:600}
.mx-section-heading h3 span{padding:0 6px;border-radius:8px;background:#efedf6;color:#8a7ca5;font-size:10px;line-height:17px}
.mx-section-heading>span{color:#8a92a2;font-size:11px}
.mx-section-heading>button{min-height:30px;padding:4px 10px;font-size:11px}
.mx-company-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 24px;margin-top:10px}
.mx-dialog .mx-setting-option{display:flex;align-items:flex-start;gap:8px;margin:0;padding:4px 0;font-weight:400;cursor:pointer}
.mx-setting-option input[type=checkbox]{margin-top:3px}
.mx-setting-option>span{display:flex;flex-direction:column;gap:4px}
.mx-setting-option b{color:#535b6e;font-size:12px;font-weight:500;line-height:20px}
.mx-setting-option small{color:#838b9c;font-size:11px;font-weight:400;line-height:18px}
.mx-setting-pending{display:block;margin-top:8px;color:#8a74ac;font-size:11px}
.mx-device-list-heading{margin-bottom:10px}
.mx-device-heading b{flex:1 1 180px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.mx-device-heading>small{flex:none}
.mx-connection-status{display:grid;grid-template-columns:.8fr 1.4fr .8fr;gap:12px;margin:3px 0;padding:10px 0;border-top:1px solid #f0f1f5;border-bottom:1px solid #f0f1f5}
.mx-connection-status>div{display:flex;flex-direction:column;gap:5px;min-width:0}
.mx-connection-status span{color:#8a92a2;font-size:11px;line-height:16px}
.mx-connection-status b{color:#636e82;font-size:11px;font-weight:500;line-height:18px;overflow-wrap:anywhere}
.mx-connection-status .is-connected{color:#338260}.mx-connection-status .is-pending{color:#b0843b}
.mx-device-guidance{display:flex;flex-direction:column;gap:4px;padding:9px 11px;border-radius:6px;background:#f7f5fc}
.mx-device-guidance b{color:#7d68a4;font-size:11px;font-weight:500;line-height:18px}
.mx-device-guidance span{color:#858096;font-size:11px;line-height:1.6}
.mx-device-guidance.is-ready{background:#f0f8f4}.mx-device-guidance.is-ready b{color:#3c8a68}.mx-device-guidance.is-ready span{color:#718d80}
.mx-device-feedback{margin:0 0 12px!important;padding:9px 12px;border-radius:6px;background:#edf7f3;color:#397a65!important;font-size:12px!important;line-height:1.7}
.mx-device-footer .mx-revoke{padding:4px 3px;border-color:transparent;background:transparent;color:#a55d63}
.mx-device-footer .mx-revoke:hover{background:#fff5f5;color:#ba434c}
.mx-device-advanced{margin-top:18px;border-top:1px solid #edf0f5;font-size:12px}
.mx-device-advanced>summary{width:max-content;padding:12px 0 0;color:#8a92a2;font-size:11px;cursor:pointer}
.mx-device-advanced>summary:focus-visible{outline:2px solid #7256e7;outline-offset:3px}
.mx-advanced-item{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:10px 12px;border-radius:6px;background:#f8f9fc}
.mx-advanced-item>div{min-width:0}.mx-advanced-item b{color:#727b8e;font-size:11px;font-weight:500}
.mx-dialog .mx-advanced-item p{margin:5px 0 0;color:#939aaa;font-size:11px;line-height:1.7}
.mx-advanced-item>button,.mx-device-advanced :slotted(button){display:inline-flex;align-items:center;justify-content:center;flex:none;width:auto;min-height:30px;margin:0;padding:4px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#727b8e;font:inherit;font-size:11px;line-height:20px;white-space:nowrap;cursor:pointer}
@media(max-width:700px){
 .mx-company-options{grid-template-columns:1fr;gap:6px}.mx-company-settings{padding:12px}
 .mx-device-list-heading>span{width:100%;font-size:10px}
 .mx-device-heading b{flex-basis:100%}.mx-device-heading>small{width:auto;margin-left:auto}
 .mx-connection-status{grid-template-columns:1fr 1.2fr;gap:10px}.mx-connection-status>div:last-child{grid-column:1/-1;flex-direction:row;gap:8px;align-items:center}
 .mx-advanced-item{align-items:flex-start;flex-direction:column;gap:8px}
}
</style>
