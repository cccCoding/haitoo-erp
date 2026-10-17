import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deduplicatedImageUpload, imageSha256, runMaterialTransfers, transferItem } from '../src/material-transfer.ts'

test('Concurrent identical images share an upload and a failed upload can be retried', async () => {
  let calls = 0
  const upload = deduplicatedImageUpload(async (file, sha256) => {
    calls++
    await new Promise(resolve => setImmediate(resolve))
    if (calls === 1) throw new Error('临时失败')
    return `https://images.example/${sha256}.png`
  })
  const files = [new Blob(['same']), new Blob(['same'])]
  const failed = await Promise.allSettled(files.map(upload))
  assert.deepEqual(failed.map(result => result.status), ['rejected', 'rejected'])
  assert.equal(calls, 1)
  const urls = await Promise.all(files.map(upload))
  assert.equal(calls, 2)
  assert.equal(urls[0], urls[1])
  assert.equal(await upload(files[0]), urls[0])
  assert.equal(calls, 2)
  assert.notEqual(await upload(new Blob(['different'])), urls[0])
  assert.equal(calls, 3)
})

test('Actual file bytes determine the fingerprint', async()=>{
  assert.equal(await imageSha256(new Blob(['abc'])),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  assert.equal(await imageSha256(new Blob(['abc'])),await imageSha256(new Blob(['abc'])))
  assert.notEqual(await imageSha256(new Blob(['abc'])),await imageSha256(new Blob(['ABC'])))
})
test('Concurrency is capped at four and failures do not undo successful rows',async()=>{
  let active=0,peak=0
  const items=Array.from({length:12},(_,i)=>transferItem(String(i),async()=>{
    active++;peak=Math.max(peak,active)
    await new Promise(resolve=>setTimeout(resolve,1))
    active--
    if(i===2) throw new Error('网络失败')
    return {outcome:i%2 ? 'duplicate' : 'created'}
  }))
  await runMaterialTransfers(items,()=>true)
  assert.equal(peak,4)
  assert.equal(items[2].outcome,'error')
  assert.equal(items[1].outcome,'duplicate')
  assert.equal(items[0].outcome,'created')
})
test('Closing stops unscheduled rows, active requests complete, retry keeps request keys',async()=>{
  let open=true
  const keys=[]
  const items=Array.from({length:10},(_,i)=>transferItem(String(i),async(force,key)=>{
    keys.push(key)
    open=false
    return {outcome:'created'}
  }))
  const original=items[0].requestKey
  await runMaterialTransfers(items,()=>open)
  assert.equal(keys.length,1)
  assert.equal(items[0].outcome,'created')
  assert.equal(items[1].outcome,'pending')
  items[0].outcome='pending'
  await runMaterialTransfers([items[0]],()=>true)
  assert.equal(keys[1],original)
})
test('Forced creation is opt in and requires a new operation key',async()=>{
  const seen=[]
  const item=transferItem('same',async(force,key)=>{ seen.push([force,key]);return {outcome:force?'created':'duplicate'} })
  await runMaterialTransfers([item],()=>true)
  assert.equal(item.outcome,'duplicate')
  assert.equal(item.selected,false)
  const old=item.requestKey
  item.force=true;item.requestKey=crypto.randomUUID();item.outcome='pending'
  await runMaterialTransfers([item],()=>true)
  assert.equal(item.outcome,'created')
  assert.equal(seen[0][0],false)
  assert.equal(seen[1][0],true)
  assert.notEqual(seen[1][1],old)
})
