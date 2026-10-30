import assert from 'node:assert/strict'
import { test } from 'node:test'
import { reactive } from 'vue'
import {
  batchTitleRequest, createBatchTitleGenerator, emptyTitleGenerationProgress,
  hasValidBatchTitles, isFatalTitleGenerationError, isUnfinishedTitle,
} from '../src/batch-title-generation.ts'

const title = id => `Floral Long Sleeve Everyday Dress ${id}`
const groups = count => reactive(Array.from({ length: count }, (_, id) => ({
  id, title: `Original manually edited product title ${id}`, edited: true,
  titleStatus: 'idle', titleError: '',
})))
const tick = () => new Promise(resolve => setImmediate(resolve))
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function fixture(items, generate, onFatal = () => {}) {
  const progress = reactive(emptyTitleGenerationProgress())
  return { progress, generator: createBatchTitleGenerator({
    progress, generate, isCurrent: group => items.includes(group), onFatal,
  }) }
}

test('400 groups: at most ten requests, out-of-order results update their own titles, no automatic creation', async () => {
  const items = groups(400)
  const requests = []
  let active = 0, maximum = 0
  const { generator, progress } = fixture(items, (group, signal) => {
    const pending = deferred()
    active++
    maximum = Math.max(maximum, active)
    assert.equal(signal.aborted, false)
    requests.push({ id: group.id, ...pending })
    return pending.promise.finally(() => { active-- })
  })
  const run = generator.run(items)
  assert.equal(progress.running, true)
  assert.deepEqual(requests.map(item => item.id), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
  assert.equal(items[10].titleStatus, 'queued')
  requests[2].resolve(title(2))
  await tick()
  assert.equal(items[2].title, title(2))
  assert.equal(items[0].title, 'Original manually edited product title 0')
  assert.equal(progress.completed, 1)
  let processed = 0
  while (progress.running) {
    const available = requests.slice(processed)
    processed = requests.length
    for (const request of available) request.resolve(title(request.id))
    await tick()
  }
  await run
  assert.equal(maximum, 10)
  assert.equal(requests.length, 400)
  assert.equal(progress.succeeded, 400)
  assert.equal(progress.completed, 400)
  assert.equal(progress.failed, 0)
  for (const group of items) assert.equal(group.title, title(group.id))
})

test('partial failure preserves old title, continues queue, retries only unfinished groups', async () => {
  const items = groups(8)
  let retrying = false
  const calls = []
  const { generator, progress } = fixture(items, async group => {
    calls.push(group.id)
    if (!retrying && group.id === 1) throw { response: { status: 502, data: { detail: '模拟服务失败' } } }
    return title(group.id)
  })
  await generator.run(items)
  assert.equal(progress.succeeded, 7)
  assert.equal(progress.failed, 1)
  assert.equal(progress.completed, 8)
  assert.equal(items[1].title, 'Original manually edited product title 1')
  assert.equal(items[1].titleError, '模拟服务失败')
  assert.equal(items[1].titleStatus, 'failed')
  retrying = true
  calls.length = 0
  await generator.run(items.filter(isUnfinishedTitle))
  assert.deepEqual(calls, [1])
  assert.equal(progress.succeeded, 1)
  assert.equal(items[1].titleError, '')
  assert.equal(items[1].title, title(1))
})

test('stop preserves successes, aborts in-flight requests, ignores late replies, and allows immediate retry', async () => {
  const items = groups(17)
  const requests = []
  const { generator, progress } = fixture(items, (group, signal) => {
    const pending = deferred()
    requests.push({ id: group.id, signal, ...pending })
    return pending.promise
  })
  const oldRun = generator.run(items)
  requests[0].resolve(title(0))
  await tick()
  generator.stop()
  assert.equal(progress.running, false)
  assert.equal(progress.succeeded, 1)
  assert.equal(progress.stopped, 16)
  assert.equal(items[0].titleStatus, 'success')
  assert.equal(requests[1].signal.aborted, true)
  assert.equal(requests.length, 11)
  const newRun = generator.run(items.filter(isUnfinishedTitle))
  for (const request of requests.slice(0, 11)) request.resolve('Obsolete title that must never be applied')
  await oldRun
  assert.equal(items[1].title, 'Original manually edited product title 1')
  assert.equal(progress.completed, 0)
  let processed = 11
  while (progress.running) {
    const available = requests.slice(processed)
    processed = requests.length
    for (const request of available) request.resolve(title(request.id))
    await tick()
  }
  await newRun
  assert.equal(progress.total, 16)
  assert.equal(progress.succeeded, 16)
  assert.equal(items[0].title, title(0))
})

test('reset and reopen with different groups isolates old successes, failures, and finalizers', async () => {
  const items = groups(3)
  const requests = []
  const fatalMessages = []
  const { generator, progress } = fixture(items, () => {
    const pending = deferred()
    requests.push(pending)
    return pending.promise
  }, message => fatalMessages.push(message))
  const oldRun = generator.run(items)
  generator.reset()
  items.splice(0, items.length, ...groups(1).map(group => ({ ...group, id: 99 })))
  const newRun = generator.run(items)
  requests[0].resolve('Obsolete response for the previous dialog')
  requests[1].reject({ response: { status: 401, data: { detail: '旧登录错误' } } })
  requests[2].reject(new Error('old network failure'))
  await oldRun
  assert.equal(progress.running, true)
  assert.equal(progress.completed, 0)
  assert.equal(items[0].titleStatus, 'running')
  assert.deepEqual(fatalMessages, [])
  requests[3].resolve(title(99))
  await newRun
  assert.equal(items[0].title, title(99))
})

for (const [status, detail] of [[401, '登录已失效'], [400, '尚未配置个人 DeepSeek 密钥，请联系公司管理员在成员管理中配置']]) {
  test(`fatal ${status} stops queue and emits one centralized message`, async () => {
    const items = groups(20)
    const requests = []
    const fatalMessages = []
    const { generator, progress } = fixture(items, () => {
      const pending = deferred()
      requests.push(pending)
      return pending.promise
    }, message => fatalMessages.push(message))
    const run = generator.run(items)
    requests[0].reject({ response: { status, data: { detail } } })
    await tick()
    assert.equal(progress.running, false)
    assert.equal(requests.length, 10)
    assert.equal(progress.failed, 1)
    assert.equal(progress.stopped, 19)
    assert.equal(progress.error, detail)
    assert.deepEqual(fatalMessages, [detail])
    requests[1].reject({ response: { status, data: { detail } } })
    for (const request of requests.slice(2)) request.resolve('Late title should not replace original titles')
    await run
    assert.equal(progress.failed, 1)
    assert.deepEqual(fatalMessages, [detail])
  })
}

test('duplicate clicks do not start a second run; single group uses the same lifecycle', async () => {
  const items = groups(2)
  const pending = deferred()
  let calls = 0
  const { generator, progress } = fixture(items, () => { calls++; return pending.promise })
  const run = generator.run([items[1]])
  await generator.run(items)
  assert.equal(calls, 1)
  assert.equal(progress.total, 1)
  assert.equal(items[0].titleStatus, 'idle')
  pending.resolve(title(1))
  await run
  assert.equal(items[1].titleStatus, 'success')
})

test('removed group cannot receive a response and further requests stop', async () => {
  const items = groups(14)
  const requests = []
  const { generator, progress } = fixture(items, () => {
    const pending = deferred()
    requests.push(pending)
    return pending.promise
  })
  const removed = items[0]
  const run = generator.run(items)
  items.splice(0, 1)
  requests[0].resolve(title(0))
  await tick()
  assert.equal(progress.running, false)
  assert.equal(requests.length, 10)
  assert.equal(removed.title, 'Original manually edited product title 0')
  for (const request of requests) request.resolve(title(1))
  await run
})

test('invalid AI result fails without overwriting and unexpected errors have a readable fallback', async () => {
  const items = groups(3)
  const { generator, progress } = fixture(items, async group => {
    if (group.id === 0) return 'short'
    if (group.id === 1) return 'A'.repeat(256)
    throw new Error('network error')
  })
  await generator.run(items)
  assert.equal(progress.failed, 3)
  assert.match(items[0].titleError, /25–255/)
  assert.match(items[2].titleError, /请稍后重试/)
  assert.equal(items[0].title, 'Original manually edited product title 0')
})

test('both request sources use their own first image/source and trimmed temporary requirements', () => {
  assert.deepEqual(batchTitleRequest(12, false, { id: 8, url: 'https://image/first.jpg' }, '  blue flowers  '), {
    url: '/templates/12/generate-draft-title',
    payload: { image_url: 'https://image/first.jpg', additional_requirements: 'blue flowers' },
  })
  for (const source_type of ['product', 'material']) {
    assert.deepEqual(batchTitleRequest(12, true, { id: 8, source_type, url: 'https://image/first.jpg' }, ''), {
      url: '/product-library/generate-draft-title',
      payload: { source_type, id: 8, additional_requirements: '' },
    })
  }
  assert.equal(isFatalTitleGenerationError({ response: { status: 400, data: { detail: '首图不存在' } } }), false)
})

test('creation title validation trims whitespace and accepts 25–255 only', () => {
  const items = groups(2)
  assert.equal(hasValidBatchTitles([]), false)
  items[0].title = `  ${'A'.repeat(25)}  `
  items[1].title = 'B'.repeat(255)
  assert.equal(hasValidBatchTitles(items), true)
  items[0].title = ` ${'A'.repeat(24)} `
  assert.equal(hasValidBatchTitles(items), false)
  items[0].title = 'A'.repeat(25)
  items[1].title = 'B'.repeat(256)
  assert.equal(hasValidBatchTitles(items), false)
})

test('accepted prompt results clear library metadata; cancelled responses preserve it', async () => {
  const items = groups(1)
  items[0].generation_id = 17
  const progress = reactive(emptyTitleGenerationProgress())
  let accepted = 0
  const pending = deferred()
  const generator = createBatchTitleGenerator({
    progress, generate: () => pending.promise, isCurrent: group => items.includes(group), onFatal: () => {},
    onGenerated: group => { accepted++; group.generation_id = undefined },
  })
  const cancelled = generator.run(items)
  generator.stop()
  pending.resolve(title(0))
  await cancelled
  assert.equal(accepted, 0)
  assert.equal(items[0].generation_id, 17)
  const successful = createBatchTitleGenerator({
    progress, generate: async () => title(0), isCurrent: group => items.includes(group), onFatal: () => {},
    onGenerated: group => { accepted++; group.generation_id = undefined },
  })
  await successful.run(items)
  assert.equal(accepted, 1)
  assert.equal(items[0].generation_id, undefined)
  assert.equal(items[0].title, title(0))
})
