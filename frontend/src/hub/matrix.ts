export const statusLabels:Record<string,string> = {queued:'排队中',running:'执行中',succeeded:'成功',partial_success:'部分成功',failed:'失败',cancelled:'已取消',permission_revoked:'权限已收回',manually_not_submitted:'已核对未提交',awaiting_attention:'待人工处理',not_started:'未提交',request_sent:'已发出提交',confirmed:'已确认',unknown:'结果未知',not_requested:'未采集',staged:'待校验',committed:'已同步',validation_failed:'校验失败',waiting_supply:'等待货盘',generating_file:'生成文件',file_ready:'文件就绪',prechecking:'预检查',collecting:'正在采集',uploading:'同步数据',waiting_login:'等待人工登录',submission_pending:'提交中',imported:'导入成功',connection_lost:'设备失联'}
export const label=(s:string)=>statusLabels[s] || s || '—'
export const display=(v:unknown)=>v===null || v===undefined ? '—' : typeof v==='number' ? v.toLocaleString('zh-CN') : String(v)
export const percent=(v:number|null|undefined)=>v===null || v===undefined ? '—' : `${(v*100).toFixed(2)}%`
export const filterParams=(filters:Record<string,unknown>)=>Object.fromEntries(Object.entries(filters).filter(([,value])=>value!==''&&value!==null&&value!==undefined))

// 展示校验字段和原因，不回显可能包含凭据的 input 或整个响应体。
export function matrixRequestError(error:unknown):string {
 const response=(error as {response?:{status?:number;data?:{detail?:unknown}}}|null)?.response
 const detail=response?.data?.detail
 if(typeof detail==='string'&&detail.trim())return detail
 const status=response?.status
 const suffix=status?`（HTTP ${status}）`:''
 if(Array.isArray(detail)){
  const messages=detail.flatMap((issue:unknown)=>{
   if(typeof issue==='string')return issue.trim()?[issue]:[]
   if(!issue||typeof issue!=='object')return []
   const {loc,msg,type}=issue as {loc?:unknown;msg?:unknown;type?:unknown}
   if(typeof msg!=='string'||!msg.trim())return []
   const field=Array.isArray(loc)?loc.filter(part=>typeof part==='string'||typeof part==='number').join('.'):''
   return [`${field?`${field}：`:''}${msg}${typeof type==='string'&&type?` [${type}]`:''}`]
  })
  if(messages.length)return `${status===422?'请求参数校验失败':'请求失败'}${suffix}：${messages.join('；')}`
 }
 return `请求失败${suffix}，请重试`
}
type MatrixDeviceStatus = {is_active:boolean;online:boolean;version:string;hub_identity?:string|null;hub_connected:boolean;sync_at?:string|null;paused:boolean;capabilities?:Record<string,string[]>;permissions?:{enabled:boolean;collect_enabled:boolean;listing_enabled:boolean}}
export function deviceSetup(device:MatrixDeviceStatus,config:{enabled:boolean;listing_enabled:boolean},now=Date.now()){
 const result=(code:string,title:string,description:string,canSync=false)=>({code,title,description,canSync})
 if(!device.is_active)return result('revoked','授权已撤销','此电脑需要重新在 ERP 授权后才能连接。')
 if(!device.online)return result('offline','等待电脑上线','请在此电脑启动连接器，保持电脑与网络在线。')
 if(device.version==='协议4')return result('upgrade','需要更新连接器','此电脑使用旧版执行器，请更新为新版连接器。')
 if(device.permissions?.enabled===false)return result('permission','未获得矩阵授权','请联系公司管理员为此账号启用“使用矩阵”。')
 if(!config.enabled)return result('disabled','等待启用矩阵','请联系平台管理员在 admin 公司配置中启用 TK 矩阵。')
 if(!device.hub_identity)return result('team','待配置团队 ID','填写当前 HubStudio 团队的稳定 ID，同一团队的电脑保持一致。')
 if(!device.hub_connected)return result('hub','等待连接 HubStudio','请在此电脑启动并登录 HubStudio，确认 Local API 已开启，再点击重新连接。',true)
 if(!device.sync_at)return result('sync','等待同步环境','点击同步环境，完整目录上传后会显示在 ERP 环境列表中。',true)
 const syncTime=Date.parse(device.sync_at)
 if(!Number.isFinite(syncTime)||now-syncTime>300000)return result('stale','环境目录待更新','最近五分钟内没有完成同步，请重新同步环境。',true)
 if(device.paused)return result('paused','已暂停接收新任务','环境仍可同步；恢复后继续接收 ERP 下发的新任务。',true)
 if(device.permissions&&!device.permissions.collect_enabled&&!device.permissions.listing_enabled)return result('operation_permission','仅可查看和同步环境','尚未获得采集或上品授权，请联系公司管理员。',true)
 const collect=device.permissions?.collect_enabled!==false&&!!device.capabilities?.['shop.collect']?.length
 const listing=device.permissions?.listing_enabled!==false&&config.listing_enabled&&!!device.capabilities?.['listing.catalog']?.length
 if(!collect&&!listing)return result('capabilities','环境可同步，执行能力未开放','可先同步和查看环境；采集或上品需设备开放对应站点能力。',true)
 return result('ready','基础连接已就绪','可在环境列表选择环境并创建方案，实际执行以预览校验为准。',true)
}
export function windowBuckets(windows:any[]=[],field:'impressions'|'clicks'|'ctr'){
 const groups=new Map<string,any[]>()
 for(const window of windows){
  const key=`${window.window_start||''}|${window.window_end||''}`
  const values=groups.get(key)||[]
  values.push(window)
  groups.set(key,values)
 }
 return [...groups.values()].map(values=>{
  const covered=values.filter(value=>value.impressions!=null&&value.clicks!=null)
  const impressions=covered.reduce((sum,value)=>sum+value.impressions,0)
  const clicks=covered.reduce((sum,value)=>sum+value.clicks,0)
  const totals={impressions:covered.length?impressions:null,clicks:covered.length?clicks:null,ctr:impressions>0?clicks/impressions:null}
  const value=totals[field]
  const prefix=groups.size>1?`[${values[0].window_start?.slice(0,10)}~${values[0].window_end?.slice(0,10)}] `:''
  return prefix+(field==='ctr'?percent(value):display(value))
 }).join(' · ')||'—'
}

// 按连续步骤分组，保留重试、重复步骤和不同店铺之间的时间顺序。
export function groupRunEvents(events:any[]){
 const groups:{key:number;stage:string;itemId:number|null;attempt:number|null;events:any[]}[]=[]
 for(const event of events){
  const stage=event.payload.stage||event.kind,itemId=event.item_id??null,attempt=event.attempt_number??null
  const previous=groups[groups.length-1]
  if(previous&&previous.stage===stage&&previous.itemId===itemId&&previous.attempt===attempt)previous.events.push(event)
  else groups.push({key:event.seq,stage,itemId,attempt,events:[event]})
 }
 return groups
}

Object.assign(statusLabels,{
 opening_orders:'打开全部订单',collection_orders:'采集订单总数',
 checking_environment:'检查环境权限',starting_environment:'启动环境',connecting_browser:'连接浏览器',
 identity_confirmed:'店铺身份已确认',collection_window:'设置采集窗口',collecting_products:'采集商品和流量',
 collection_checked:'核对采集结果',validating_collection:'校验采集包',collection_committed:'快照已保存',
 downloading_file:'下载货盘文件',file_verified:'文件校验通过',checking_listing_result:'核对上品结果',
 'manual.resolve':'人工核对记录',expired:'租约已失效',
 'claimed':'领取任务','identity.confirmed':'店铺身份确认','item.result':'执行结果','precheck.failed':'预检查失败',
 'collection.committed':'采集快照已保存','collection.rejected':'采集数据校验失败',
 'listing.preparing':'准备上品货盘','submission.intent':'保存提交意图','listing.result':'平台上品结果',
 'lease.expired':'执行租约失效',checking_language:'检查页面语言',switching_language:'切换页面语言',
 verifying_language:'核对页面语言',language_ready:'页面语言就绪',closing_account_menu:'关闭账号菜单',
 account_menu_closed:'账号菜单已关闭',language_failed:'页面语言检查失败',logged_in:'登录就绪',upload_parsing:'解析上品文件'
})

export function environmentSyncTargets<T extends MatrixDeviceStatus&{user_id:number}>(devices:T[],userId:number,config:{enabled:boolean;listing_enabled:boolean}){
 return devices.filter(device=>device.user_id===userId&&deviceSetup(device,config).canSync)
}

Object.assign(statusLabels,{opening_shop:'打开商品管理页',environment_ready:'目标环境已就绪','environment.bound':'结果按环境归档'})

Object.assign(statusLabels,{collection_count:'读取在售商品总数'})

Object.assign(statusLabels,{waiting_verification:'等待人工安全验证'})

export function sortMatrixRows<T>(rows:T[],key:string,direction:'asc'|'desc'|null):T[]{
 if(!key||!direction)return rows
 function value(row:T):string|number|null{
  const raw=key.split('.').reduce((current:any,part)=>current?.[part],row)
  if(raw==null||raw==='')return null
  if(key==='snapshot.observed_at'){
   const timestamp=Date.parse(String(raw))
   return Number.isFinite(timestamp)?timestamp:null
  }
  if(key.startsWith('snapshot.')){
   const number=Number(raw)
   return Number.isFinite(number)?number:null
  }
  return String(raw)
 }
 return [...rows].sort((left,right)=>{
  const a=value(left),b=value(right)
  if(a===null)return b===null?0:1
  if(b===null)return -1
  const comparison=typeof a==='number'&&typeof b==='number'?a-b:String(a).localeCompare(String(b),'zh-CN',{numeric:true})
  return direction==='asc'?comparison:-comparison
 })
}

export function runEnvironmentScope(items:{environment_name?:string|null;container_code?:string|null;environment_id:number}[]){
 return items.map(item=>[item.environment_name||`环境 #${item.environment_id}`,item.container_code].filter(Boolean).join(' / ')).join('、')||'—'
}

Object.assign(statusLabels,{flash_scan:'扫描商家秒杀活动',flash_pending:'待处理',flash_prepared:'续期数据已准备',flash_terminate_intent:'准备终止',flash_terminated:'旧活动已终止',flash_copy_intent:'准备复制',flash_draft_confirmed:'草稿已确认',flash_publish_intent:'准备发布',flash_created:'新活动已创建，正在核对',flash_published:'新活动已发布',flash_unknown:'结果待核对',flash_failed:'续期失败',flash_skipped:'已跳过',flash_cancelled:'已取消',flash_attention:'待核对活动',flash_resolved:'人工核对完成'})

export function listingSummary(listing:any):string {
 if(!listing)return ''
 const accepted=listing.accepted_count ?? listing.accepted?.length ?? 0
 const total=listing.imported_count ?? ((listing.accepted?.length ?? 0)+(listing.rejected?.length ?? 0))
 return `成功 ${accepted} / 导入 ${total}`
}
