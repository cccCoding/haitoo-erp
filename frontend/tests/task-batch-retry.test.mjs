import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createTaskBatchRetrier, taskBatchRetryError } from '../src/task-batch-retry.ts'

const ids = count => Array.from({ length: count }, (_, index) => index + 1)
const httpError = (status, detail) => ({ response: { status, data: { detail } } })

function fixture(selected, submit = async batch => ({ total: batch.length }), refresh = async () => {}) {
  const state = { selected: [...selected], requests: [], messages: [], running: [], refreshes: 0 }
  const retrier = createTaskBatchRetrier({
    submit: batch => { state.requests.push([...batch]); return submit(batch) },
    onSucceeded: batch => { state.selected = state.selected.filter(id => !batch.includes(id)) },
    refresh: async () => { state.refreshes++; await refresh() },
    onMessage: message => state.messages.push(message),
    onRunningChange: running => state.running.push(running),
  })
  return { state, retrier }
}

test('1000 unique tasks are submitted once and only successful selections are cleared', async () => {
  const { state, retrier } = fixture([...ids(1000), 9999])
  await retrier.run([...ids(1000), 1, 1000])
  assert.deepEqual(state.requests, [ids(1000)])
  assert.deepEqual(state.selected, [9999])
  assert.deepEqual(state.running, [true, false])
  assert.equal(state.refreshes, 1)
  assert.deepEqual(state.messages, ['已将 1000 个失败任务重新入队'])
})

test('1001 tasks use sequential 1000 + 1 requests, snapshot the selection and reject duplicate clicks', async () => {
  let finishFirst
  const first = new Promise(resolve => { finishFirst = resolve })
  const selected = ids(1001)
  const { state, retrier } = fixture(selected, async batch => {
    if (batch.length === 1000) await first
    return { total: batch.length }
  })
  const run = retrier.run(selected)
  assert.deepEqual(state.requests, [ids(1000)])
  selected.splice(0, selected.length, 5000)
  state.selected.push(5000)
  await retrier.run([6000])
  assert.equal(state.requests.length, 1)
  finishFirst()
  await run
  assert.deepEqual(state.requests, [ids(1000), [1001]])
  assert.deepEqual(state.selected, [5000])
  assert.deepEqual(state.messages, ['已将 1001 个失败任务重新入队'])
})

test('a rejected middle batch stops subsequent batches and retains unsuccessful selections', async () => {
  const { state, retrier } = fixture(ids(2001), async batch => {
    if (batch[0] === 1001) throw httpError(400, '只有失败任务可以重试：1001, 1002')
    return { total: batch.length }
  })
  await retrier.run(ids(2001))
  assert.equal(state.requests.length, 2)
  assert.deepEqual(state.selected, ids(2001).slice(1000))
  assert.equal(state.refreshes, 0)
  assert.deepEqual(state.running, [true, false])
  assert.deepEqual(state.messages, ['已将 1000 个失败任务重新入队；后续批次已停止。部分任务已不是失败状态，请刷新列表后重试'])
})

test('network errors report an unconfirmed result without automatic retry or clearing selections', async () => {
  const { state, retrier } = fixture(ids(1001), async batch => {
    if (batch[0] === 1001) throw new Error('timeout')
    return { total: batch.length }
  })
  await retrier.run(ids(1001))
  assert.equal(state.requests.length, 2)
  assert.deepEqual(state.selected, [1001])
  assert.deepEqual(state.messages, ['已将 1000 个失败任务重新入队；后续批次已停止。网络异常，提交结果未确认，请刷新列表后查看'])
})

test('refresh failures preserve confirmed submission success', async () => {
  const { state, retrier } = fixture([1], undefined, async () => { throw new Error('refresh failed') })
  await retrier.run([1])
  assert.deepEqual(state.selected, [])
  assert.equal(state.requests.length, 1)
  assert.deepEqual(state.messages, ['已将 1 个失败任务重新入队；列表刷新失败，请刷新页面查看'])
  assert.deepEqual(state.running, [true, false])
})

test('validation errors and structured or lengthy details never expose input ID lists', () => {
  const detail = [{ type: 'too_long', loc: ['body', 'task_ids'], msg: 'too many', input: ids(1001) }]
  assert.equal(taskBatchRetryError(httpError(422, detail)), '每批最多重试 1000 个任务')
  assert.equal(taskBatchRetryError(httpError(422, [{ type: 'too_short', input: [] }])), '重试参数有误，请刷新任务列表后重试')
  assert.equal(taskBatchRetryError(httpError(422, 'invalid')), '重试参数有误，请刷新任务列表后重试')
  for (const detail of [{ input: ids(1000) }, '[1,2,3]', '{"task_ids":[1]}', 'x'.repeat(201), null]) {
    assert.equal(taskBatchRetryError(httpError(500, detail)), '批量重试任务失败，请稍后重试')
  }
  assert.equal(taskBatchRetryError(httpError(404, '任务不存在')), '任务不存在')
  assert.equal(taskBatchRetryError(httpError(401, '登录已失效')), '登录已失效')
})

test('empty selections send no request and a failed run releases the duplicate-click guard', async () => {
  let fail = true
  const { state, retrier } = fixture([1], async batch => {
    if (fail) throw httpError(404, '任务不存在')
    return { total: batch.length }
  })
  await retrier.run([])
  assert.equal(state.requests.length, 0)
  assert.deepEqual(state.messages, ['请至少选择一个失败任务'])
  await retrier.run([1])
  assert.deepEqual(state.selected, [1])
  fail = false
  await retrier.run([1])
  assert.equal(state.requests.length, 2)
  assert.deepEqual(state.selected, [])
  assert.deepEqual(state.running, [true, false, true, false])
})
