import assert from 'node:assert/strict'
import { test } from 'node:test'
import { uploadCreativeImages } from '../src/creative-upload.ts'
import { deduplicatedImageUpload } from '../src/material-transfer.ts'

const invalidImage = () => ({ response: { status: 400, data: { code: 'invalid_image', detail: '图片内容损坏或不是有效图片' } } })
const asset = content => ({ file: new Blob([content]) })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))

test('Skips corrupt rows, processes later rows, preserves order and deduplicates URLs with four workers', async () => {
  const assets = ['slow', 'broken', 'fast', 'same', 'same', 'last'].map(asset)
  let active = 0, peak = 0
  const calls = []
  const upload = deduplicatedImageUpload(async file => {
    const content = await file.text()
    calls.push(content)
    active++; peak = Math.max(peak, active)
    await delay(content === 'slow' ? 30 : 5)
    active--
    if (content === 'broken') throw invalidImage()
    return `https://images.example/${content}`
  })
  assert.deepEqual(await uploadCreativeImages(assets, upload), [
    'https://images.example/slow', 'https://images.example/fast',
    'https://images.example/same', 'https://images.example/last',
  ])
  assert.equal(peak, 4)
  assert.equal(calls.filter(value => value === 'same').length, 1)
  assert.equal(assets[1].skippedReason, '图片内容损坏或不是有效图片')
  assert.equal(assets[1].uploadedUrl, undefined)
  assert.ok(assets[5].uploadedUrl)
})

test('All corrupt images produce no task URLs and count duplicate bad files separately', async () => {
  const assets = [asset('broken'), asset('broken'), asset('also broken')]
  const upload = deduplicatedImageUpload(async () => { await delay(5); throw invalidImage() })
  assert.deepEqual(await uploadCreativeImages(assets, upload), [])
  assert.equal(assets.filter(item => item.skippedReason).length, 3)
  assert.deepEqual(await uploadCreativeImages(assets, async () => assert.fail('Known bad images must not be retried')), [])
})

test('Network errors block submission, wait for other workers and preserve success and skip state for retry', async () => {
  const assets = ['network', 'broken', 'slow', 'later', 'last'].map(asset)
  const networkError = new Error('网络失败')
  await assert.rejects(uploadCreativeImages(assets, async file => {
    const content = await file.text()
    if (content === 'network') throw networkError
    if (content === 'broken') throw invalidImage()
    await delay(20)
    return `https://images.example/${content}`
  }), error => error === networkError)
  assert.ok(assets[2].uploadedUrl, 'The slow upload must finish before rejection')
  assert.ok(assets[4].uploadedUrl, 'Remaining workers must drain pending rows')
  assert.ok(assets[1].skippedReason)
  assert.equal(assets[0].skippedReason, undefined)
  const retried = []
  assert.deepEqual(await uploadCreativeImages(assets, async file => {
    const content = await file.text(); retried.push(content)
    return `https://images.example/${content}`
  }), ['network', 'slow', 'later', 'last'].map(value => `https://images.example/${value}`))
  assert.deepEqual(retried, ['network'])
})

test('Only the dedicated HTTP 400 code can skip an image', async () => {
  for (const error of [
    { response: { status: 400, data: { detail: '图片内容损坏或不是有效图片' } } },
    { response: { status: 400, data: { detail: '图片实际内容与上传信息不一致' } } },
    { response: { status: 503, data: { code: 'invalid_image' } } },
    { response: { status: 400, data: { detail: '图片授权无效或已过期，请重新选择文件' } } },
  ]) {
    const item = asset('valid')
    await assert.rejects(uploadCreativeImages([item], async () => { throw error }), actual => actual === error)
    assert.equal(item.skippedReason, undefined)
  }
})
