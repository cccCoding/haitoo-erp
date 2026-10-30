import assert from 'node:assert/strict'
import { test } from 'node:test'
import { categoryChoices, categoryEdits, parseCategoryAliases } from '../src/title-categories.ts'

test('陌生分类必须明确归类，不能把空选择当作新建', () => {
  const edits = categoryEdits([{ source_key: 'a', source: '连身裙' }])
  assert.throws(() => categoryChoices(edits), /请为每个陌生分类/)
  edits[0].selection = 'new'
  assert.deepEqual(categoryChoices(edits), [{ source_key: 'a', target_id: null, new_name: '连身裙', save_alias: true }])
  edits[0].newName = '  '
  assert.throws(() => categoryChoices(edits), /请为每个陌生分类/)
})

test('已有分类用 ID 提交，支持仅本次导入映射', () => {
  const edits = categoryEdits([{ source_key: 'a', source: '女裙装', target_id: 7, save_alias: false }])
  edits[0].newName = '不应提交的旧输入'
  assert.deepEqual(categoryChoices(edits), [{ source_key: 'a', target_id: 7, new_name: null, save_alias: false }])
})

test('恢复拟新建方案；别名每行一个，保留名称内的逗号', () => {
  const edits = categoryEdits([{ source_key: 'a', source: '原分类', new_name: '  上衣  ', save_alias: true }])
  assert.equal(categoryChoices(edits)[0].new_name, '上衣')
  assert.deepEqual(parseCategoryAliases(' 上装 \r\nTops\n\n上装\nA,B\n'), ['上装', 'Tops', 'A,B'])
})
