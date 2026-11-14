import test from 'node:test'
import assert from 'node:assert/strict'
import {display,percent,windowBuckets,filterParams,deviceSetup,sortMatrixRows,matrixRequestError} from '../src/hub/matrix.ts'

test('matrix request errors show validation fields and reasons without echoing submitted values',()=>{
 const message=matrixRequestError({response:{status:422,data:{detail:[
  {type:'extra_forbidden',loc:['body','flash_sale'],msg:'Extra inputs are not permitted',input:{secret:'private-value'}},
  {type:'int_parsing',loc:['body','environment_ids',0],msg:'Input should be a valid integer',input:'private-value'},
 ]}}})
 assert.equal(message,'请求参数校验失败（HTTP 422）：body.flash_sale：Extra inputs are not permitted [extra_forbidden]；body.environment_ids.0：Input should be a valid integer [int_parsing]')
 assert.equal(message.includes('private-value'),false)
})

test('matrix request errors preserve business messages and handle missing or malformed details',()=>{
 assert.equal(matrixRequestError({response:{status:409,data:{detail:'执行预览已过期或配置已修改，请重新预览'}}}),'执行预览已过期或配置已修改，请重新预览')
 assert.equal(matrixRequestError({response:{status:500,data:'Internal Server Error'}}),'请求失败（HTTP 500），请重试')
 assert.equal(matrixRequestError({response:{status:422,data:{detail:[null,{},42]}}}),'请求失败（HTTP 422），请重试')
 for(const error of [null,undefined,new Error('Network Error')])assert.equal(matrixRequestError(error),'请求失败，请重试')
})
test('an online connector is not ready when HubStudio or its execution capabilities are missing',()=>{
 const now=Date.now(),config={enabled:true,listing_enabled:false}
 const device={is_active:true,online:true,version:'5.1.0',hub_identity:'team',hub_connected:false,sync_at:null,paused:false,capabilities:{}}
 assert.equal(deviceSetup(device,config,now).code,'hub')
 assert.equal(deviceSetup(device,config,now).canSync,true)
 assert.equal(deviceSetup({...device,hub_connected:true},config,now).code,'sync')
 assert.equal(deviceSetup({...device,hub_connected:true,sync_at:new Date(now).toISOString()},config,now).code,'capabilities')
 assert.equal(deviceSetup({...device,hub_connected:true,sync_at:new Date(now).toISOString(),capabilities:{'listing.catalog':['MY']}},config,now).code,'capabilities')
 assert.equal(deviceSetup({...device,hub_connected:true,sync_at:new Date(now).toISOString(),capabilities:{'shop.collect':['MY']}},config,now).code,'ready')
})
test('setup guidance respects company configuration, revoked grants, pause and stale directories',()=>{
 const now=Date.now(),config={enabled:true,listing_enabled:true}
 const device={is_active:true,online:true,version:'5.1.0',hub_identity:'team',hub_connected:true,sync_at:new Date(now).toISOString(),paused:false,capabilities:{'shop.collect':['MY']}}
 for(const [change,code] of [[{is_active:false},'revoked'],[{online:false},'offline'],[{hub_identity:''},'team'],[{paused:true},'paused'],[{sync_at:new Date(now-300001).toISOString()},'stale']])assert.equal(deviceSetup({...device,...change},config,now).code,code)
 assert.equal(deviceSetup(device,{enabled:false,listing_enabled:false},now).code,'disabled')
})
test('empty device filters are omitted from HTTP query parameters',()=>{
 assert.deepEqual(filterParams({agent_id:'',q:'',site:null,group:undefined}),{})
 assert.deepEqual(filterParams({agent_id:7,q:'测试环境',exact:'1\n2'}),{agent_id:7,q:'测试环境',exact:'1\n2'})
})
test('matrix filters omit an unset collected value and preserve explicit boolean filters',()=>{
 assert.deepEqual(filterParams({q:'',site:'',group:'',ungrouped:false,collected:''}),{ungrouped:false})
 for(const collected of [false,true,'false','true']){
  assert.deepEqual(filterParams({ungrouped:false,collected}),{ungrouped:false,collected})
 }
})
test('unknown values remain different from real zero',()=>{assert.equal(display(null),'—');assert.equal(display(0),'0');assert.equal(percent(null),'—');assert.equal(percent(0),'0.00%')})
test('traffic cards combine markets in the same window without country prefixes',()=>{
 const windows=[{site:'MY',impressions:100,clicks:10},{site:'ID',impressions:900,clicks:0}]
 assert.equal(windowBuckets(windows,'impressions'),'1,000')
 assert.equal(windowBuckets(windows,'clicks'),'10')
 assert.equal(windowBuckets(windows,'ctr'),'1.00%')
})
test('traffic cards preserve unknown totals and explicit zero',()=>{
 assert.equal(windowBuckets([{site:'MY',impressions:null,clicks:null}],'impressions'),'—')
 assert.equal(windowBuckets([{site:'MY',impressions:0,clicks:0}],'clicks'),'0')
 assert.equal(windowBuckets([{site:'MY',impressions:0,clicks:0}],'ctr'),'—')
 assert.equal(windowBuckets([],'clicks'),'—')
})
test('traffic cards keep different date windows separate',()=>{
 const windows=[{site:'MY',window_start:'2026-10-01',window_end:'2026-11-01',impressions:100,clicks:5},{site:'MY',window_start:'2026-10-02',window_end:'2026-11-02',impressions:200,clicks:20}]
 assert.equal(windowBuckets(windows,'clicks'),'[2026-10-01~2026-11-01] 5 · [2026-10-02~2026-11-02] 20')
})

test('device readiness distinguishes member authorization from installed capabilities',()=>{
 const now=Date.now(),config={enabled:true,listing_enabled:true}
 const device={is_active:true,online:true,version:'5.1.0',hub_identity:'team',hub_connected:true,sync_at:new Date(now).toISOString(),paused:false,capabilities:{'shop.collect':['MY']},permissions:{enabled:false,collect_enabled:false,listing_enabled:false}}
 assert.equal(deviceSetup(device,config,now).code,'permission')
 assert.equal(deviceSetup(device,config,now).canSync,false)
 device.permissions.enabled=true
 assert.equal(deviceSetup(device,config,now).code,'operation_permission')
 assert.equal(deviceSetup(device,config,now).canSync,true)
 device.permissions.collect_enabled=true
 assert.equal(deviceSetup(device,config,now).code,'ready')
})

test('step groups preserve interleaved shops, retries and repeated stages',async()=>{
 const {groupRunEvents}=await import('../src/hub/matrix.ts')
 const event=(seq,item,attempt,stage)=>({seq,item_id:item,attempt_number:attempt,payload:{stage}})
 const groups=groupRunEvents([event(1,4,1,'collecting'),event(2,4,1,'collecting'),event(3,5,1,'collecting'),event(4,4,2,'collecting'),event(5,4,2,'uploading'),event(6,4,2,'collecting')])
 assert.deepEqual(groups.map(g=>[g.key,g.itemId,g.attempt,g.events.length]),[[1,4,1,2],[3,5,1,1],[4,4,2,1],[5,4,2,1],[6,4,2,1]])
 assert.equal(groupRunEvents([{seq:7,kind:'precheck.failed',payload:{message:'环境不可访问'}}])[0].stage,'precheck.failed')
})

test('one-click environment sync targets only eligible devices owned by the current member',async()=>{
 const {environmentSyncTargets}=await import('../src/hub/matrix.ts')
 const config={enabled:true,listing_enabled:false}
 const base={id:1,user_id:7,is_active:true,online:true,version:'5.1.1',hub_identity:'team',hub_connected:true,sync_at:new Date().toISOString(),paused:false,capabilities:{'shop.collect':['MY']}}
 const devices=[base,{...base,id:2,user_id:8},{...base,id:3,online:false},{...base,id:4,hub_identity:''},{...base,id:5,is_active:false},{...base,id:6,version:'协议4'},{...base,id:7,hub_connected:false},{...base,id:8,paused:true},{...base,id:9,permissions:{enabled:false,collect_enabled:false,listing_enabled:false}}]
 assert.deepEqual(environmentSyncTargets(devices,7,config).map(d=>d.id),[1,7,8])
 assert.deepEqual(environmentSyncTargets(devices,7,{...config,enabled:false}),[])
})

test('matrix sorting handles numeric amounts, keeps unknowns last and preserves default order',()=>{
 const rows=[{id:1,snapshot:{gmv:'10.00'}},{id:2,snapshot:null},{id:3,snapshot:{gmv:'2.50'}},{id:4,snapshot:{gmv:'0.00'}}]
 assert.deepEqual(sortMatrixRows(rows,'snapshot.gmv','asc').map(row=>row.id),[4,3,1,2])
 assert.deepEqual(sortMatrixRows(rows,'snapshot.gmv','desc').map(row=>row.id),[1,3,4,2])
 assert.deepEqual(sortMatrixRows(rows,'',null).map(row=>row.id),[1,2,3,4])
 assert.deepEqual(rows.map(row=>row.id),[1,2,3,4])
})
test('matrix sorting supports natural text, timestamps and stable ties',()=>{
 const rows=[{id:1,name:'女装10',snapshot:{clicks:1,observed_at:'2026-11-09T09:00:00+08:00'}},{id:2,name:'女装2',snapshot:{clicks:1,observed_at:'2026-11-09T02:00:00Z'}}]
 assert.deepEqual(sortMatrixRows(rows,'name','asc').map(row=>row.id),[2,1])
 assert.deepEqual(sortMatrixRows(rows,'snapshot.observed_at','asc').map(row=>row.id),[1,2])
 assert.deepEqual(sortMatrixRows(rows,'snapshot.clicks','desc').map(row=>row.id),[1,2])
})

test('run scope lists frozen environment names and codes with a fallback for missing names',async()=>{
 const {runEnvironmentScope}=await import('../src/hub/matrix.ts')
 assert.equal(runEnvironmentScope([{environment_id:1,environment_name:'马来店铺 A',container_code:'env-1'}]),'马来店铺 A / env-1')
 assert.equal(runEnvironmentScope([{environment_id:1,environment_name:'店铺 A'},{environment_id:2,container_code:'env-2'}]),'店铺 A、环境 #2 / env-2')
 assert.equal(runEnvironmentScope([]),'—')
 assert.deepEqual(filterParams({collected:false,q:''}),{collected:false})
})

test('listing quantity receipt shows accepted products over imported file total',async()=>{
 const {listingSummary}=await import('../src/hub/matrix.ts')
 assert.equal(listingSummary({accepted_count:6,imported_count:10,accepted:[],rejected:[]}), '成功 6 / 导入 10')
 assert.equal(listingSummary({accepted:[0,1],rejected:[]}), '成功 2 / 导入 2')
})
