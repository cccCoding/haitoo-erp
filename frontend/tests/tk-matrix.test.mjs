import test from 'node:test'
import assert from 'node:assert/strict'
import {display,percent,windowBuckets,filterParams,deviceSetup} from '../src/hub/matrix.ts'
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
test('unknown values remain different from real zero',()=>{assert.equal(display(null),'—');assert.equal(display(0),'0');assert.equal(percent(null),'—');assert.equal(percent(0),'0.00%')})
test('traffic buckets keep different markets separate',()=>{assert.equal(windowBuckets([{site:'MY',ctr:.1},{site:'ID',ctr:0}],'ctr'),'MY 10.00% · ID 0.00%')})

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
