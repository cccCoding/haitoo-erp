import assert from 'node:assert/strict'
import { test } from 'node:test'
import { reactive } from 'vue'
import { applySelectedStyle, commonStyleTemplate, styleOptions } from '../src/material-styles.ts'

test('Shared duplicate names and deleted sources stay selectable within their template', () => {
  const styles=[
    {id:1,template_id:1,name:'正面',created_by_name:'A',source_exists:true},
    {id:2,template_id:1,name:'正面',created_by_name:'B',source_exists:false},
    {id:3,template_id:2,name:'背面',created_by_name:'A',source_exists:true},
  ]
  const options=styleOptions(styles,1)
  assert.deepEqual(options.map(item=>item.value),[1,2])
  assert.match(options[0].label,/A/)
  assert.match(options[1].label,/B.*白底图已删除/)
  assert.notEqual(options[0].label,options[1].label)
  assert.equal(styleOptions(styles,null).length,3)
})

test('A batch can set a style only when every selected material has the same template', () => {
  assert.equal(commonStyleTemplate([]),null)
  assert.equal(commonStyleTemplate([{template_id:1},{template_id:1}]),1)
  assert.equal(commonStyleTemplate([{template_id:1},{template_id:2}]),null)
  assert.equal(commonStyleTemplate([{template_id:1},{template_id:null}]),null)
  assert.equal(commonStyleTemplate([{template_id:null}]),null)
})

test('Batch application and clearing update only selected images and preserve other metadata', () => {
  const items=reactive([
    {selected:true,style_id:null,is_infringing:true},
    {selected:false,style_id:2,is_infringing:false},
    {selected:true,style_id:3,is_infringing:false},
  ])
  applySelectedStyle(items,1)
  assert.deepEqual(items.map(item=>item.style_id),[1,2,1])
  assert.deepEqual(items.map(item=>item.is_infringing),[true,false,false])
  applySelectedStyle(items,null)
  assert.deepEqual(items.map(item=>item.style_id),[null,2,null])
})
