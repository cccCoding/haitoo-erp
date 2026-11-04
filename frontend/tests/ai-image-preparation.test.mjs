import test from 'node:test'
import assert from 'node:assert/strict'
import { candidateUnavailable, createImagePreparer } from '../src/ai-image-preparation.ts'

test('ready files remain available after pending expiry', () => {
  assert.equal(candidateUnavailable({ state: 'ready', expires_at: 1 }, 100), false)
  assert.equal(candidateUnavailable({ state: 'pending', expires_at: 1 }, 100), true)
  assert.equal(candidateUnavailable({ state: 'invalid' }), true)
})

test('1000 candidates enqueue once, poll then return without image downloads', async () => {
  const calls = [], progress = []
  const client = {
    async post(url, data) { calls.push([url, data]); return { data: { id: 1, state: 'running', total: 1000, ready: 0, failed: 0, items: [] } } },
    async get(url) { calls.push([url]); return { data: { id: 1, state: 'ready', total: 1000, ready: 1000, failed: 0, items: [] } } },
  }
  const preparer = createImagePreparer(client, () => 'Bearer test', value => progress.push(value.ready), async () => {})
  const result = await preparer.prepare(Array.from({ length: 1000 }, (_, i) => i + 1))
  assert.equal(result.ready, 1000)
  assert.equal(calls[0][0], '/ai-image-preparations')
  assert.equal(calls[0][1].candidate_ids.length, 1000)
  assert.equal(calls[1][0], '/ai-image-preparations/1')
  assert.deepEqual(progress, [0, 1000])
})

test('partial failure preserves errors and does not report adoption', async () => {
  const client = { async post() { return { data: { id: 1, state: 'partial_failed', total: 2, ready: 1, failed: 1,
    items: [{ candidate_id: 2, state: 'expired', error: '已过期' }] } } } }
  const preparer = createImagePreparer(client, () => 'Bearer test', () => {})
  await assert.rejects(preparer.prepare([1, 2]), /已过期/)
})

test('cancel stops polling without cancelling the background copy', async () => {
  let reads = 0, preparer
  const client = {
    async post() { return { data: { id: 1, state: 'running', total: 1, ready: 0, failed: 0, items: [] } } },
    async get() { reads++; throw new Error('should not poll after cancellation') },
  }
  preparer = createImagePreparer(client, () => 'Bearer test', () => {}, async () => preparer.cancel())
  await assert.rejects(preparer.prepare([1]), /停止等待/)
  assert.equal(reads, 0)
})

test('resume queries an existing preparation without enqueueing or submitting adoption', async () => {
  let polls = 0
  const states = [], client = {
    async post() { throw new Error('恢复进度不能创建任务或提交审核') },
    async get(url) { assert.equal(url, '/ai-image-preparations/42'); polls++; return { data: { id: 42, state: polls < 2 ? 'running' : 'ready', total: 3, ready: polls < 2 ? 1 : 3, failed: 0, items: [] } } },
  }
  const preparer = createImagePreparer(client, () => 'Bearer test', data => states.push(data.ready), async () => {})
  assert.equal((await preparer.resume(42)).ready, 3)
  assert.deepEqual(states, [1, 3])
})

test('stale resume response after cancellation cannot update progress', async () => {
  let deliver, updated = false
  const client = { get() { return new Promise(resolve => { deliver = resolve }) } }
  const preparer = createImagePreparer(client, () => 'Bearer test', () => { updated = true })
  const result = preparer.resume(42)
  preparer.cancel()
  deliver({ data: { id: 42, state: 'ready', total: 1, ready: 1, failed: 0, items: [] } })
  await assert.rejects(result, /停止等待/)
  assert.equal(updated, false)
})

test('retry calls only the failed preparation and preserves successful items', async () => {
  const calls = [], client = {
    async post(url, body) { calls.push([url, body]); return { data: { id: 42, state: 'running', total: 3, ready: 2, failed: 0, items: [] } } },
    async get() { return { data: { id: 42, state: 'ready', total: 3, ready: 3, failed: 0, items: [] } } },
  }
  const states = [], preparer = createImagePreparer(client, () => 'Bearer test', data => states.push(data.ready), async () => {})
  await preparer.retry(42)
  assert.deepEqual(calls, [['/ai-image-preparations/42/retry', {}]])
  assert.deepEqual(states, [2, 3])
})

test('closing before enqueue responds retains the background job identity without continuing the review', async () => {
  let deliver, recorded = null, progressUpdates = 0
  const client = { post() { return new Promise(resolve => { deliver = resolve }) } }
  const preparer = createImagePreparer(client, () => 'Bearer test', () => { progressUpdates++ }, undefined, data => { recorded = data.id })
  const pending = preparer.prepare([1])
  preparer.cancel()
  deliver({ data: { id: 42, state: 'running', total: 1, ready: 0, failed: 0, items: [] } })
  await assert.rejects(pending, /停止等待/)
  assert.equal(recorded, 42)
  assert.equal(progressUpdates, 0)
})

test('changing account before enqueue responds does not save another account’s background job', async () => {
  let deliver, authorization = 'Bearer first', recorded = false
  const client = { post() { return new Promise(resolve => { deliver = resolve }) } }
  const preparer = createImagePreparer(client, () => authorization, () => {}, undefined, () => { recorded = true })
  const pending = preparer.prepare([1])
  authorization = 'Bearer second'; preparer.cancel()
  deliver({ data: { id: 42, state: 'running', total: 1, ready: 0, failed: 0, items: [] } })
  await assert.rejects(pending, /停止等待/)
  assert.equal(recorded, false)
})
