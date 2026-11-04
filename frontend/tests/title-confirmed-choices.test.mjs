import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveConfirmedChoice } from '../src/title-confirmed-choices.ts'

const options = [
  { id: 1, phrase: 'sulaman', translation: '刺绣', semantic_tag: '工艺', categories: ['连衣裙'] },
  { id: 2, phrase: 'Acme', translation: '艾克', semantic_tag: '品牌', categories: ['连衣裙'] },
]

test('旧工艺、品牌匹配原词或释义，保留品牌大小写', () => {
  assert.deepEqual(resolveConfirmedChoice([], [{ tag: '制作工艺', value: ' 刺绣 ' }], options), { ids: [1], warning: '' })
  assert.deepEqual(resolveConfirmedChoice([], [{ tag: '商标', value: 'ＡＣＭＥ' }], options), { ids: [2], warning: '' })
  assert.equal(options[1].phrase, 'Acme')
})

test('无法匹配或冲突的旧值等待人工处理，不静默丢弃', () => {
  const unmatched = resolveConfirmedChoice([], [{ tag: '工艺', value: '未知' }], options)
  assert.deepEqual(unmatched.ids, [])
  assert.match(unmatched.warning, /未知/)
  const conflict = resolveConfirmedChoice([], [{ tag: '工艺', value: '刺绣' }, { tag: '针法', value: '蕾丝' }], options)
  assert.deepEqual(conflict.ids, [])
  assert.match(conflict.warning, /针法：蕾丝/)
})

test('已保存多选优先保留不可用 ID，供界面提示重新选择', () => {
  assert.deepEqual(resolveConfirmedChoice([1, 999, 1], [{ tag: '工艺', value: '旧值' }], options), { ids: [1, 999], warning: '' })
  assert.deepEqual(resolveConfirmedChoice([], [], options), { ids: [], warning: '' })
})
