import test from 'node:test'
import assert from 'node:assert/strict'
import {healthState,probeLocalAgent,LOCAL_AGENT_URL} from '../src/hub/local-agent.ts'

test('local probe requires Agent marker and protocol, not a cloud heartbeat',()=>{
  assert.equal(healthState({status:'ready',application:'haitoo-hub-agent',protocol:5,mode:'connector'}),'ready')
  assert.equal(healthState({status:'ready'}),'legacy')
  assert.equal(healthState({status:'ready',application:'haitoo-hub-agent',protocol:5}),'legacy')
  assert.equal(healthState({online:true}),'unreachable')
})
test('probe never sends ERP credentials to loopback and validates HTTP response',async()=>{
  const result=await probeLocalAgent(undefined,async(url,options)=>{
    assert.equal(url,`${LOCAL_AGENT_URL}/health`)
    assert.equal(options.credentials,'omit');assert.equal(options.headers,undefined)
    assert.equal(options.redirect,'error')
    return new Response(JSON.stringify({status:'ready',application:'haitoo-hub-agent',protocol:5,mode:'connector'}))
  })
  assert.equal(result,'ready')
  assert.equal(await probeLocalAgent(undefined,async()=>new Response('{}',{status:503})),'unreachable')
  assert.equal(await probeLocalAgent(undefined,async()=>{throw new TypeError('refused')}),'unreachable')
})
test('probe can be cancelled when page is unmounted',async()=>{
  const abort=new AbortController();abort.abort()
  assert.equal(await probeLocalAgent(abort.signal,async(_,options)=>{
    assert.equal(options.signal.aborted,true);throw new DOMException('aborted','AbortError')
  }),'unreachable')
})
