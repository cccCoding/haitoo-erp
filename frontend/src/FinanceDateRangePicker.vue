<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { beijingInput, validateFinanceDateRange } from './finance'
import { financeDatePresets, financeMonth, financeMonthGrid, financeRangePreset, financeRangeSpan, financeWindowDays, shiftFinanceDate } from './finance'
import type { FinanceDatePreset } from './finance'

const props=defineProps<{start:string;end:string;disabled?:boolean}>()
const emit=defineEmits<{'update:start':[string];'update:end':[string]}>()
const root=ref<HTMLElement|null>(null),trigger=ref<HTMLButtonElement|null>(null),panel=ref<HTMLElement|null>(null)
const open=ref(false),draftStart=ref(''),draftEnd=ref(''),hoverDate=ref(''),pickingEnd=ref(false)
const chosenPreset=ref<FinanceDatePreset|null>(null),openedAt=ref(new Date())
const leftMonth=ref(financeMonth(beijingInput(new Date()))),focusDate=ref(''),today=ref('')
const panelStyle=ref<Record<string,string>>({})
const months=computed(()=>[leftMonth.value,financeMonth(leftMonth.value,1)])
const calendars=computed(()=>months.value.map(month=>({month,weeks:financeMonthGrid(month)})))
const draftError=computed(()=>validateFinanceDateRange(draftStart.value,draftEnd.value))
const previewRange=computed(()=>{
  const start=draftStart.value,end=draftEnd.value || (pickingEnd.value ? hoverDate.value : '')
  return start && end ? [start,end].sort() : [start,start]
})
const display=computed(()=>props.start && props.end ? `${props.start}  至  ${props.end}` : '请选择下单日期范围')
function monthLabel(month:string) { const [year,value]=month.split('-'); return `${year} 年 ${Number(value)} 月` }
function reposition() {
  if (!open.value || !trigger.value || !panel.value) return
  const rect=trigger.value.getBoundingClientRect(),width=Math.min(640,window.innerWidth-24)
  const height=Math.min(panel.value.scrollHeight,window.innerHeight-24)
  let top=rect.bottom+8
  if (top+height>window.innerHeight-12) top=Math.max(12,rect.top-height-8)
  if (window.innerWidth<=700) top=12
  panelStyle.value={width:`${width}px`,left:`${Math.max(12,Math.min(rect.left,window.innerWidth-width-12))}px`,
    top:`${top}px`,maxHeight:`${Math.max(0,window.innerHeight-top-12)}px`}
}
async function show() {
  if (props.disabled) return
  if (open.value) { close(); return }
  openedAt.value=new Date(); today.value=beijingInput(openedAt.value); draftStart.value=props.start; draftEnd.value=props.end
  chosenPreset.value=financeDatePresets.find(item=>{
    const range=financeRangePreset(item.key,openedAt.value)
    return range.start===props.start && range.end===props.end
  })?.key ?? null
  hoverDate.value=''; pickingEnd.value=false
  leftMonth.value=financeMonth(props.start || today.value); focusDate.value=props.start || today.value
  panelStyle.value={visibility:'hidden'}; open.value=true
  await nextTick(); reposition(); panel.value?.querySelector<HTMLInputElement>('input')?.focus()
}
function close(restoreFocus=true) { open.value=false; if (restoreFocus) trigger.value?.focus() }
function confirm() {
  if (draftError.value) return
  emit('update:start',draftStart.value); emit('update:end',draftEnd.value); close()
}
function clear() { emit('update:start',''); emit('update:end',''); close() }
function choose(date:string) {
  if (unavailable(date)) return
  chosenPreset.value=null
  focusDate.value=date
  if (!pickingEnd.value) { draftStart.value=date; draftEnd.value=''; pickingEnd.value=true }
  else {
    const dates=[draftStart.value,date].sort(); draftStart.value=dates[0]; draftEnd.value=dates[1]; pickingEnd.value=false
  }
  hoverDate.value=''
}
function unavailable(date:string) { return pickingEnd.value && !!draftStart.value && financeRangeSpan(draftStart.value,date)>financeWindowDays }
function inRange(date:string) { return previewRange.value[0] && date>=previewRange.value[0] && date<=previewRange.value[1] }
function endpoint(date:string) { return date===draftStart.value || date===draftEnd.value }
function presetActive(key:FinanceDatePreset) { return chosenPreset.value===key }
function preset(key:FinanceDatePreset) {
  chosenPreset.value=key
  const range=financeRangePreset(key,openedAt.value); draftStart.value=range.start; draftEnd.value=range.end
  leftMonth.value=financeMonth(range.start); focusDate.value=range.start; pickingEnd.value=false; hoverDate.value=''
}
function moveMonth(delta:number) {
  leftMonth.value=financeMonth(leftMonth.value,delta)
  if (focusDate.value<leftMonth.value || focusDate.value>=financeMonth(leftMonth.value,2)) focusDate.value=leftMonth.value
}
function edited(which:'start'|'end') {
  chosenPreset.value=null
  pickingEnd.value=false; hoverDate.value=''
  const value=which==='start' ? draftStart.value : draftEnd.value
  try { leftMonth.value=financeMonth(value); focusDate.value=value } catch {}
}
async function dayKey(event:KeyboardEvent,date:string) {
  const steps:Record<string,number>={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}
  if (!(event.key in steps)) return
  event.preventDefault()
  const next=shiftFinanceDate(date,steps[event.key])
  if (unavailable(next)) return
  focusDate.value=next
  if (next<months.value[0]) moveMonth(-1)
  if (next>=financeMonth(months.value[1],1)) moveMonth(1)
  await nextTick(); panel.value?.querySelector<HTMLButtonElement>(`button[data-date="${next}"]`)?.focus()
}
function outside(event:PointerEvent) {
  if (open.value && event.target instanceof Node && !root.value?.contains(event.target) && !panel.value?.contains(event.target)) close(false)
}
onMounted(()=>{document.addEventListener('pointerdown',outside);window.addEventListener('resize',reposition);window.addEventListener('scroll',reposition,true)})
onBeforeUnmount(()=>{document.removeEventListener('pointerdown',outside);window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true)})
</script>

<template>
  <div ref="root" class="finance-range-field">
    <span class="finance-range-label" id="finance-range-label">下单日期 <b>*</b></span>
    <button ref="trigger" class="finance-range-trigger" type="button" aria-label="下单日期范围" aria-haspopup="dialog" :aria-expanded="open" :disabled="disabled" @click="show" @keydown.esc.prevent="close()"><span aria-hidden="true">▦</span><span :class="{'is-placeholder':!start || !end}">{{display}}</span><span aria-hidden="true">⌄</span></button>
  </div>
  <Teleport to="body">
    <div v-if="open" ref="panel" class="finance-range-panel" :style="panelStyle" role="dialog" aria-label="选择下单日期范围" @keydown.esc.stop.prevent="close()">
      <aside class="finance-range-presets" aria-label="快捷日期范围"><button v-for="item in financeDatePresets" :key="item.key" type="button" :class="{active:presetActive(item.key)}" :aria-pressed="presetActive(item.key)" @click="preset(item.key)">{{item.label}}</button></aside>
      <div class="finance-range-main">
        <div class="finance-range-inputs"><label>开始日期<input v-model="draftStart" type="date" aria-label="开始日期" @change="edited('start')"/></label><span aria-hidden="true">→</span><label>结束日期<input v-model="draftEnd" type="date" aria-label="结束日期" @change="edited('end')"/></label></div>
        <div class="finance-range-calendars">
          <section v-for="(calendar,index) in calendars" :key="calendar.month" class="finance-range-calendar">
            <header><div v-if="index===0" class="finance-range-month-actions"><button type="button" aria-label="上一年" @click="moveMonth(-12)">«</button><button type="button" aria-label="上个月" @click="moveMonth(-1)">‹</button></div><span v-else class="finance-range-month-spacer"></span><h3>{{monthLabel(calendar.month)}}</h3><div v-if="index===1" class="finance-range-month-actions"><button type="button" aria-label="下个月" @click="moveMonth(1)">›</button><button type="button" aria-label="下一年" @click="moveMonth(12)">»</button></div><span v-else class="finance-range-month-spacer"></span></header>
            <div role="grid" :aria-label="monthLabel(calendar.month)">
              <div class="finance-range-week" role="row"><span v-for="day in ['日','一','二','三','四','五','六']" :key="day" role="columnheader">{{day}}</span></div>
              <div v-for="(week,weekIndex) in calendar.weeks" :key="weekIndex" class="finance-range-week" role="row">
                <div v-for="day in week" :key="day.date" role="gridcell" :aria-selected="day.inMonth && !!inRange(day.date)" :class="{'is-range':day.inMonth && inRange(day.date),'range-start':day.date===previewRange[0],'range-end':day.date===previewRange[1]}">
                  <button v-if="day.inMonth" type="button" :data-date="day.date" :aria-label="day.date" :aria-pressed="endpoint(day.date)" :aria-current="day.date===today ? 'date' : undefined" :tabindex="day.date===focusDate ? 0 : -1" :disabled="unavailable(day.date)" :class="{'is-endpoint':endpoint(day.date),'is-today':day.date===today}" @click="choose(day.date)" @mouseenter="hoverDate=day.date" @focus="focusDate=day.date" @keydown="dayKey($event,day.date)">{{day.day}}</button><span v-else class="is-other-month">{{day.day}}</span>
                </div>
              </div>
            </div>
          </section>
        </div>
        <footer><div class="finance-range-help" aria-live="polite"><span v-if="draftError && draftStart && draftEnd" class="finance-range-error">{{draftError}}</span><span v-else-if="pickingEnd">请选择结束日期</span><span v-else>北京时间 · 含首尾当天 · 最多一年（{{financeWindowDays}}天）</span></div><div class="finance-range-footer-actions"><button type="button" @click="clear">清空</button><button type="button" @click="close()">取消</button><button type="button" class="finance-range-confirm" :disabled="!!draftError" @click="confirm">确定</button></div></footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.finance-range-field{min-width:0}.finance-range-label{display:block;margin-bottom:8px;font-size:13px;color:#334155}.finance-range-label b{color:#dc2626}.finance-range-trigger{display:flex;align-items:center;gap:10px;width:100%;min-height:42px;padding:10px 12px;border:1px solid #dfe3ef;border-radius:10px;background:#fff;color:#334155;font:inherit;font-size:13px;box-shadow:none;text-align:left}.finance-range-trigger>span:nth-child(2){flex:1;min-width:0}.finance-range-trigger>span:first-child,.finance-range-trigger>span:last-child,.is-placeholder{color:#94a3b8}.finance-range-trigger:focus-visible,.finance-range-trigger[aria-expanded=true]{border-color:#7054e7;outline:none;box-shadow:0 0 0 3px #7054e71f}.finance-range-trigger:disabled{opacity:.5;cursor:not-allowed}
.finance-range-panel{position:fixed;z-index:40;display:flex;box-sizing:border-box;overflow:auto;border:1px solid #e2dff0;border-radius:14px;background:#fff;box-shadow:0 18px 50px #33265a29;font-family:inherit;color:#334155}.finance-range-panel *{box-sizing:border-box}.finance-range-panel button{font:inherit;cursor:pointer;box-shadow:none}.finance-range-panel button:focus-visible{outline:2px solid #7054e7;outline-offset:-2px}.finance-range-presets{flex:0 0 96px;padding:14px 8px;border-right:1px solid #e9e7f0;display:flex;flex-direction:column;gap:3px;background:#fcfbff}.finance-range-presets button{border:0;background:transparent;border-radius:7px;text-align:left;font-size:13px;color:#64748b;padding:10px 14px;white-space:nowrap}.finance-range-presets button:hover,.finance-range-presets button.active{background:#f1edff;color:#6043d4}.finance-range-main{flex:1;min-width:0}.finance-range-inputs{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid #eeeaf4}.finance-range-inputs label{flex:1;min-width:0;font-size:11px;color:#64748b}.finance-range-inputs input{display:block;width:100%;min-width:0;margin-top:6px;border:1px solid #dfe3ef;border-radius:8px;padding:9px 10px;font:inherit;font-size:13px;background:#fff;color:#334155}.finance-range-inputs input:focus{outline:none;border-color:#7054e7;box-shadow:0 0 0 2px #7054e71a}.finance-range-inputs>span{color:#94a3b8;margin-top:16px}.finance-range-calendars{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.finance-range-calendar{padding:14px 12px 16px;min-width:0}.finance-range-calendar+.finance-range-calendar{border-left:1px solid #eeeaf4}.finance-range-calendar header{display:flex;align-items:center;justify-content:space-between;gap:4px;margin-bottom:12px}.finance-range-calendar h3{font-size:14px;white-space:nowrap;margin:0;font-weight:600}.finance-range-month-actions{display:flex;width:48px;flex-shrink:0}.finance-range-month-actions button{border:0;background:transparent;color:#64748b;font-size:19px;padding:4px;width:24px;height:30px;border-radius:5px}.finance-range-month-actions button:hover{background:#f1edff;color:#6043d4}.finance-range-month-spacer{width:12px}.finance-range-week{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));align-items:center;text-align:center;font-size:12px}.finance-range-week[role=row]:first-child{color:#94a3b8;margin-bottom:8px}.finance-range-week>[role=columnheader]{padding:5px 0}.finance-range-week>[role=gridcell]{height:34px;margin:2px 0;display:flex;justify-content:center;align-items:center}.finance-range-week button{border:0;background:transparent;border-radius:50%;width:30px;height:30px;padding:0;font-size:12px;color:#334155}.finance-range-week button:hover{background:#e9e2ff}.finance-range-week button.is-today{font-weight:700;color:#6043d4}.finance-range-week button.is-endpoint{background:#7054e7;color:white;font-weight:600}.finance-range-week button:disabled{color:#cbd5e1;cursor:not-allowed}.finance-range-week .is-range{background:#f3f0ff}.finance-range-week .range-start{border-radius:18px 0 0 18px}.finance-range-week .range-end{border-radius:0 18px 18px 0}.finance-range-week .range-start.range-end{border-radius:18px}.is-other-month{color:#c0c4cf}.finance-range-panel footer{display:flex;justify-content:space-between;align-items:center;gap:10px;border-top:1px solid #eeeaf4;padding:12px 16px}.finance-range-help{font-size:11px;color:#94a3b8;line-height:1.6}.finance-range-error{color:#b91c1c}.finance-range-footer-actions{display:flex;gap:8px;flex-shrink:0}.finance-range-footer-actions button{border:1px solid transparent;border-radius:8px;padding:8px 12px;font-size:12px;background:#fff;color:#64748b}.finance-range-footer-actions .finance-range-confirm{background:#7054e7;color:#fff;border-color:#7054e7}.finance-range-confirm:disabled{opacity:.45;cursor:not-allowed}
@media(max-width:700px){.finance-range-panel{display:block}.finance-range-presets{padding:10px;flex-direction:row;flex-wrap:wrap;gap:4px;border-right:0;border-bottom:1px solid #eeeaf4}.finance-range-presets button{padding:7px 10px;font-size:12px}.finance-range-inputs{padding:12px;gap:8px}.finance-range-inputs input{padding:9px 6px}.finance-range-calendars{grid-template-columns:1fr}.finance-range-calendar+.finance-range-calendar{border-left:0;border-top:1px solid #eeeaf4}.finance-range-week button{width:32px;height:32px}.finance-range-calendar{padding:14px 16px}.finance-range-panel footer{position:sticky;bottom:0;flex-wrap:wrap;background:#fff;padding:12px}.finance-range-help{flex:1 1 100%}.finance-range-footer-actions{margin-left:auto}}
</style>
