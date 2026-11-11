import test from 'node:test'
import assert from 'node:assert/strict'
import {createRunViewer,formatRunLogs} from '../src/hub/run-viewer.ts'
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}}
const event=(seq,item_id=null)=>({seq,item_id,created_at:'2026-11-11T10:00:00Z',payload:{message:`event ${seq}`}})
test('switching runs ignores a delayed response and clears previous content immediately',async()=>{
 const first=deferred()
 const session=createRunViewer(async id=>id===1?first.promise:{id,items:[{id:20}]},async id=>[event(id)])
 const opening=session.open({id:1});await session.open({id:2})
 first.resolve({id:1,items:[{id:10}]});await opening
 assert.equal(session.run.value.id,2);assert.deepEqual(session.events.value.map(e=>e.seq),[2])
})
test('environment changes retain all environments, reject stale scope events and omit batch events via server filtering',async()=>{
 const oldScope=deferred(),calls=[]
 const session=createRunViewer(async()=>({id:1,items:[{id:10},{id:20}]}),async(id,params)=>{
  calls.push({...params});if(params.item_id===10)return oldScope.promise
  return params.item_id===20?[event(4,20)]:[event(1),event(2,10)]
 })
 await session.open({id:1});const switching=session.select(10)
 assert.equal(session.events.value.length,0)
 await session.select(20);oldScope.resolve([event(3,10)]);await switching
 assert.equal(session.run.value.items.length,2);assert.deepEqual(session.events.value.map(e=>e.item_id),[20])
 await session.select(null);assert.equal('item_id' in calls[calls.length-1],false)
 assert.deepEqual(session.events.value.map(e=>e.seq),[1,2])
})
test('closing invalidates pending responses and prevents further log requests',async()=>{
 const result=deferred();let calls=0
 const session=createRunViewer(async()=>result.promise,async()=>{calls++;return [event(1)]})
 const opening=session.open({id:1});session.close();result.resolve({id:1,items:[{id:10}]});await opening
 await session.load();assert.equal(session.events.value.length,0);assert.equal(calls,1);assert.equal(session.loading.value,false)
})
test('pagination uses the last sequence, deduplicates and copies every loaded event',async()=>{
 const params=[];const first=Array.from({length:500},(_,i)=>event(i+1,10))
 const session=createRunViewer(async()=>({id:1,items:[]}),async(id,p)=>{params.push(p);return p.after_seq?[event(500,10),event(501,10)]:first})
 await session.open({id:1},10);assert.equal(session.more.value,true)
 await session.load();assert.deepEqual(params[1],{after_seq:500,item_id:10});assert.equal(session.events.value.length,501);assert.equal(session.more.value,false)
 assert.equal(formatRunLogs(session.events.value).split('\n').length,501)
})
test('failed opening shows no previous run data, retries current scope and clears the error',async()=>{
 let fail=false
 const session=createRunViewer(async id=>{if(fail)throw Error('offline');return {id,items:[{id:10}]}},async()=>[event(1)])
 await session.open({id:1});fail=true;await session.open({id:2},20)
 assert.equal(session.run.value.id,2);assert.equal(session.run.value.items.length,0);assert.equal(session.events.value.length,0);assert.ok(session.error.value)
 fail=false;await session.load();assert.equal(session.error.value,'');assert.equal(session.itemId.value,20)
})
test('a late failure from the previous scope does not replace current content or error state',async()=>{
 const previous=deferred()
 const session=createRunViewer(async id=>({id,items:[]}),async(id,p)=>p.item_id===10?previous.promise:[event(1,20)])
 const opening=session.open({id:1},10);await session.select(20)
 previous.reject(new Error('old scope failed'));await opening
 assert.equal(session.error.value,'');assert.equal(session.loading.value,false);assert.equal(session.events.value[0].item_id,20)
})
test('refresh failures retain already loaded logs and successful retry resumes from the last sequence',async()=>{
 let fail=false;const calls=[]
 const session=createRunViewer(async()=>({id:1,items:[]}),async(id,p)=>{calls.push(p.after_seq);if(fail)throw Error('offline');return p.after_seq?[event(2)]:[event(1)]})
 await session.open({id:1});fail=true;await session.load()
 assert.equal(session.events.value.length,1);assert.ok(session.error.value)
 fail=false;await session.load();assert.deepEqual(calls,[0,1,1]);assert.deepEqual(session.events.value.map(e=>e.seq),[1,2]);assert.equal(session.error.value,'')
})
