import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createTaskPageLoader } from '../src/task-page-loader.ts'

function fixture() {
  const requests = [], pages = []
  const loader = createTaskPageLoader((params, signal) => new Promise((resolve, reject) => {
    requests.push({ params, signal, resolve, reject })
  }), page => pages.push(page))
  return { loader, requests, pages }
}

test('slow polling never overlaps another poll or foreground search', async () => {
  const { loader, requests, pages } = fixture()
  const first = loader.load({ page: 1 }, { background: true })
  await loader.load({ page: 1 }, { background: true })
  assert.equal(requests.length, 1)
  const search = loader.load({ creator: 2 })
  assert.equal(requests[0].signal.aborted, true)
  await loader.load({ page: 1 }, { background: true })
  assert.equal(requests.length, 2)
  requests[1].resolve('search')
  await search
  requests[0].resolve('stale poll')
  await first
  assert.deepEqual(pages, ['search'])
})

test('changing tabs discards late results even if cancellation is ignored', async () => {
  const { loader, requests, pages } = fixture()
  const sku = loader.load({ type: 'sku_image' })
  const carousel = loader.load({ type: 'carousel' })
  requests[0].resolve('SKU')
  await sku
  await loader.load({}, { background: true })
  assert.equal(requests.length, 2)
  requests[1].resolve('carousel')
  await carousel
  assert.deepEqual(pages, ['carousel'])
})

test('logging out or unmounting cancels and discards in-flight data', async () => {
  const { loader, requests, pages } = fixture()
  const old = loader.load({ user: 1 })
  loader.cancel()
  assert.equal(requests[0].signal.aborted, true)
  requests[0].resolve('old account')
  await old
  assert.deepEqual(pages, [])
  const next = loader.load({ user: 2 })
  requests[1].resolve('new account')
  await next
  assert.deepEqual(pages, ['new account'])
})

test('network and timeout failures propagate and allow the next request', async () => {
  const { loader, requests, pages } = fixture()
  const error = new Error('timeout')
  const failed = loader.load({})
  requests[0].reject(error)
  await assert.rejects(failed, error)
  const next = loader.load({}, { background: true })
  requests[1].resolve('retry')
  await next
  assert.deepEqual(pages, ['retry'])
})

test('cancellation errors do not surface as search failures', async () => {
  const { loader, requests, pages } = fixture()
  const old = loader.load({ page: 1 })
  const next = loader.load({ page: 2 })
  requests[0].reject(new Error('cancelled'))
  await old
  requests[1].resolve('page 2')
  await next
  assert.deepEqual(pages, ['page 2'])
})
