import test from 'node:test'
import assert from 'node:assert/strict'
import * as Vue from 'vue'
import {compile} from '@vue/compiler-dom'
import {dialogFocus} from '../src/dialog-focus.ts'

// 使用真实 Vue 编译、更新和指令生命周期，模拟 DOM 宿主以验证弹窗切换顺序。
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.parent=null;this.isConnected=true}
 querySelectorAll(){return []}
 querySelector(){return null}
 focus(){}
}
const render=template=>new Function('Vue',compile(template,{mode:'function',prefixIdentifiers:true}).code)(Vue)
const Viewer={setup(){return()=>Vue.withDirectives(Vue.h('viewer'),[[dialogFocus,{close(){}}]])}}
const History={setup(){return()=>Vue.withDirectives(Vue.h('history'),[[dialogFocus,{close(){}}]])}}
const Flash={
 props:['itemId'],directives:{dialogFocus},
 setup(props){
  const open=Vue.ref(false)
  Vue.watch(()=>props.itemId,()=>{open.value=props.itemId!==null},{immediate:true})
  return {open,close(){open.value=false}}
 },
 render:render('<section>提醒</section><Teleport to="body"><div v-if="open"><section v-dialog-focus="{close}">活动明细</section></div></Teleport>'),
}
function mount(t,template,initialOverflow=''){
 const savedDocument=globalThis.document,savedElement=globalThis.HTMLElement
 globalThis.HTMLElement=Element
 const listeners=new Set(),body=new Element('body')
 globalThis.document={body:{style:{overflow:initialOverflow}},activeElement:null,
  addEventListener(type,handler){listeners.add(handler)},removeEventListener(type,handler){listeners.delete(handler)}}
 const renderer=Vue.createRenderer({
  createElement:tag=>new Element(tag),createText:()=>new Element('text'),createComment:()=>new Element('comment'),
  insert(el,parent,anchor){
   if(el.parent){const i=el.parent.children.indexOf(el);if(i>=0)el.parent.children.splice(i,1)}
   el.parent=parent;const i=parent.children.indexOf(anchor)
   if(i<0)parent.children.push(el);else parent.children.splice(i,0,el)
  },
  remove(el){if(el.parent){const i=el.parent.children.indexOf(el);if(i>=0)el.parent.children.splice(i,1)}el.isConnected=false},
  setElementText(){},setText(){},setComment(){},patchProp(){},
  parentNode:el=>el.parent,nextSibling:el=>el.parent?.children[el.parent.children.indexOf(el)+1]||null,
  querySelector:()=>body,
 })
 const dialog=Vue.ref(''),itemId=Vue.ref(null),showHistory=Vue.ref(false)
 const app=renderer.createApp({components:{Viewer,History,Flash},setup(){return {dialog,itemId,showHistory}},render:render(template)})
 app.mount(new Element('root'))
 t.after(()=>{
  try{app.unmount();assert.equal(document.body.style.overflow,initialOverflow);assert.equal(listeners.size,0)}
  finally{globalThis.document=savedDocument;globalThis.HTMLElement=savedElement}
 })
 return {dialog,itemId,showHistory,overflow:()=>document.body.style.overflow}
}

test('秒杀活动侧边窗返回详情并关闭后释放页面滚动锁',async t=>{
 const state=mount(t,'<section><Flash :item-id="itemId"/></section><Viewer v-if="dialog===\'run\' && itemId===null"/>')
 for(let i=0;i<2;i++){
  state.dialog.value='run';await Vue.nextTick();assert.equal(state.overflow(),'hidden')
  state.itemId.value=42;await Vue.nextTick();assert.equal(state.overflow(),'hidden')
  state.itemId.value=null;await Vue.nextTick();assert.equal(state.overflow(),'hidden')
  state.dialog.value='';await Vue.nextTick();assert.equal(state.overflow(),'')
 }
})
test('运行记录进入详情再返回并关闭后释放页面滚动锁',async t=>{
 const state=mount(t,'<section>主页面</section><History v-if="dialog===\'history\'"/><Viewer v-if="dialog===\'run\'"/>')
 for(const value of ['history','run','history','']){
  state.dialog.value=value;await Vue.nextTick()
  assert.equal(state.overflow(),value?'hidden':'')
 }
})
for(const closeFirst of ['viewer','history']){
 test(`叠加弹窗先关闭 ${closeFirst} 时保持锁定，最后关闭恢复原滚动状态`,async t=>{
  const state=mount(t,'<Viewer v-if="dialog"/><History v-if="showHistory"/>','scroll')
  state.dialog.value='run';await Vue.nextTick()
  state.showHistory.value=true;await Vue.nextTick();assert.equal(state.overflow(),'hidden')
  if(closeFirst==='viewer')state.dialog.value='';else state.showHistory.value=false
  await Vue.nextTick();assert.equal(state.overflow(),'hidden')
  state.dialog.value='';state.showHistory.value=false;await Vue.nextTick()
  assert.equal(state.overflow(),'scroll')
 })
}
test('页面卸载时清理全部弹窗并保留原有滚动锁',async t=>{
 const state=mount(t,'<Viewer v-if="dialog"/><History v-if="showHistory"/>','hidden')
 state.dialog.value='run';state.showHistory.value=true;await Vue.nextTick()
 assert.equal(state.overflow(),'hidden')
})
