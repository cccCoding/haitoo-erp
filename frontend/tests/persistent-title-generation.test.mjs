import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPersistentTitleGenerator } from '../src/persistent-title-generation.ts'
import { emptyTitleGenerationProgress } from '../src/batch-title-generation.ts'

const title = 'Gaun Lengan Panjang Corak Bunga'
const group = id => ({ id, title: 'Original product title remains here', titleStatus: 'idle', titleError: '' })
const tick = () => new Promise(resolve => setImmediate(resolve))
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes }); return {promise,resolve} }

test('one durable request coordinates groups, protects manual titles, and carries provenance', async () => {
  const groups=[group(1),{...group(2),manualTitle:true},group(3)]
  let submitted
  const progress=emptyTitleGenerationProgress()
  const generator=createPersistentTitleGenerator({progress,submit:async items=>{submitted=items;return{id:17}},
    poll:async()=>({state:'completed',result:{items:{'1':{title,generation_id:40,warnings:['按首图描述'],keywords:[{id:2,phrase:'gaun'}]},'3':{title,generation_id:41}}}}),
    cancel:async()=>{},isCurrent:g=>groups.includes(g),onError:assert.fail,delay:tick})
  await generator.run(groups)
  assert.deepEqual(submitted,[groups[0],groups[2]])
  assert.equal(groups[0].title,title)
  assert.equal(groups[0].generation_id,40)
  assert.equal(groups[0].titleKeywords[0].id,2)
  assert.equal(groups[1].title,'Original product title remains here')
  assert.equal(groups[2].title,title)
  assert.equal(groups[2].titleStatus,'success')
  assert.equal(progress.succeeded,2)
  assert.equal(progress.running,false)
})

test('stop before submit responds cancels newly created task and never writes stale results', async () => {
  const pending=deferred(), item=group(1), cancelled=[]
  const progress=emptyTitleGenerationProgress()
  const generator=createPersistentTitleGenerator({progress,submit:()=>pending.promise,
    poll:()=>{throw new Error('cancelled task must not be polled')},cancel:async id=>cancelled.push(id),isCurrent:()=>true,onError:assert.fail})
  const running=generator.run([item]);generator.stop();pending.resolve({id:22});await running
  assert.deepEqual(cancelled,[22]);assert.equal(item.titleStatus,'stopped');assert.notEqual(item.title,title)
})

test('partial failure retains original title and reports per-group error', async () => {
  const groups=[group(1),group(2)], progress=emptyTitleGenerationProgress()
  const generator=createPersistentTitleGenerator({progress,submit:async()=>({id:19}),
    poll:async()=>({state:'completed_with_errors',result:{items:{'1':{title,generation_id:1},'2':{state:'failed',error:'预算已用尽'}}}}),
    cancel:async()=>{},isCurrent:()=>true,onError:assert.fail})
  await generator.run(groups)
  assert.equal(groups[0].titleStatus,'success');assert.equal(groups[1].titleStatus,'failed')
  assert.equal(groups[1].title,'Original product title remains here');assert.equal(groups[1].titleError,'预算已用尽')
  assert.equal(progress.completed,2);assert.equal(progress.failed,1)
})

test('late poll after cancellation cannot overwrite manually changed title', async () => {
  const pending=deferred(), item=group(1)
  const generator=createPersistentTitleGenerator({progress:emptyTitleGenerationProgress(),submit:async()=>({id:23}),
    poll:()=>pending.promise,cancel:async()=>{},isCurrent:()=>true,onError:assert.fail})
  const run=generator.run([item]);await tick();generator.stop();item.title='Manually preserved product title'
  pending.resolve({state:'completed',result:{items:{'1':{title}}}});await run
  assert.equal(item.title,'Manually preserved product title')
})
