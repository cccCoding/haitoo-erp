import test from 'node:test'
import assert from 'node:assert/strict'
import { invalidateTitleMarket, titleMarketParams } from '../src/title-markets.ts'
import { emptyTitleGenerationProgress, hasValidBatchTitles } from '../src/batch-title-generation.ts'
import { createPersistentTitleGenerator } from '../src/persistent-title-generation.ts'

const group = (extra = {}) => ({ id: 1, title: 'Daster Lengan Panjang Motif Bunga',
  titleStatus: 'success', titleError: '', generation_id: 42,
  titleWarnings: ['覆盖不足'], titleKeywords: [{ id: 1 }], ...extra })

test('切换站点保留文本、清除旧关联，禁止直接提交，反复切换仍保持失效状态', () => {
  const groups = [group()]
  const original = groups[0].title
  invalidateTitleMarket(groups)
  assert.equal(groups[0].title, original)
  assert.equal(groups[0].generation_id, undefined)
  assert.deepEqual(groups[0].titleKeywords, [])
  assert.deepEqual(groups[0].titleWarnings, [])
  assert.equal(groups[0].titleMarketStale, true)
  assert.equal(hasValidBatchTitles(groups), false)
  invalidateTitleMarket(groups)
  assert.equal(hasValidBatchTitles(groups), false)
})

test('手动确认标题和普通提示词结果不因切换而失效', () => {
  const groups = [group({ manualTitle: true }), group({ id: 2, generation_id: undefined })]
  invalidateTitleMarket(groups)
  assert.equal(groups[0].manualTitle, true)
  assert.equal(groups[0].generation_id, undefined)
  assert.equal(hasValidBatchTitles(groups), true)
})

test('重新生成成功恢复提交，失败继续保留旧文本和失效状态', async () => {
  const groups = [group(), group({ id: 2 })]
  invalidateTitleMarket(groups)
  const generator = createPersistentTitleGenerator({
    progress: emptyTitleGenerationProgress(), submit: async () => ({ id: 10 }),
    poll: async () => ({ state: 'completed_with_errors', result: { items: {
      1: { title: 'Daster Wanita Lengan Panjang', generation_id: 55 },
      2: { state: 'failed', error: '语言校验失败' },
    } } }),
    cancel: async () => {}, isCurrent: () => true, onError: () => {},
  })
  await generator.run(groups)
  assert.equal(groups[0].titleMarketStale, false)
  assert.equal(groups[0].generation_id, 55)
  assert.equal(groups[1].titleMarketStale, true)
  assert.equal(groups[1].title, 'Daster Lengan Panjang Motif Bunga')
  assert.equal(hasValidBatchTitles(groups), false)
})

test('取消后迟到的旧站点响应不能恢复旧关联或覆盖文本', async () => {
  let resolvePoll
  let startedPoll
  const polling = new Promise(resolve => { startedPoll = resolve })
  const groups = [group()]
  const generator = createPersistentTitleGenerator({
    progress: emptyTitleGenerationProgress(), submit: async () => ({ id: 10 }),
    poll: () => { startedPoll(); return new Promise(resolve => { resolvePoll = resolve }) },
    cancel: async () => {}, isCurrent: () => true, onError: () => {},
  })
  const pending = generator.run(groups)
  await polling
  generator.reset()
  invalidateTitleMarket(groups)
  resolvePoll({ state: 'completed', result: { items: { 1: { title: 'Gaun Wanita Lengan Panjang', generation_id: 99 } } } })
  await pending
  assert.equal(groups[0].title, 'Daster Lengan Panjang Motif Bunga')
  assert.equal(groups[0].generation_id, undefined)
  assert.equal(groups[0].titleMarketStale, true)
  assert.deepEqual(titleMarketParams('ID'), { site: 'ID', language: 'id' })
})
