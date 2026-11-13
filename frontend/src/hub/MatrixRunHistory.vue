<script setup lang="ts">
import {computed,ref,onMounted,nextTick} from 'vue'
import {dialogFocus as vDialogFocus} from '../dialog-focus'
import {listingSummary,label,runEnvironmentScope} from './matrix'
const props=defineProps<{scope:any;runs:any[];total:number;page:number;loading:boolean;error:string;scrollTop:number}>()
const emit=defineEmits<{close:[];refresh:[];page:[value:number];scroll:[value:number];open:[run:any,itemId:number|null]}>()
const list=ref<HTMLElement|null>(null)
const pages=computed(()=>Math.max(1,Math.ceil(props.total/20)))
const title=computed(()=>props.scope?'店铺运行记录':'全部运行记录')
const tasks=(value:string[])=>['listing.catalog','shop.collect'].filter(task=>value?.includes(task)).map(task=>task==='listing.catalog'?'自动上品':'店铺采集').join(' + ')||'—'
const date=(value:string)=>value?new Date(value).toLocaleDateString('zh-CN',{timeZone:'Asia/Hong_Kong'}):'—'
const time=(value:string)=>value?new Date(value).toLocaleTimeString('zh-CN',{timeZone:'Asia/Hong_Kong',hour12:false}):'—'
onMounted(async()=>{await nextTick();if(list.value)list.value.scrollTop=props.scrollTop})
function changePage(value:number){if(list.value)list.value.scrollTop=0;emit('page',value)}
</script>

<template>
<div class="modal-backdrop rh-backdrop" @click.self="emit('close')">
 <section v-dialog-focus="{close:()=>emit('close')}" class="modal-card rh-dialog" role="dialog" aria-modal="true" aria-labelledby="run-history-title">
  <header class="rh-header">
   <div class="rh-heading"><div><span class="rh-eyebrow">执行历史</span><h2 id="run-history-title">{{title}}</h2></div><button aria-label="关闭运行记录" @click="emit('close')">关闭 <span aria-hidden="true">×</span></button></div>
   <div v-if="scope" class="rh-context"><span class="rh-shop-icon" aria-hidden="true">店</span><div><h3>{{scope.shop?.name||scope.name}}</h3><p><span>环境 {{scope.name}}</span><span>编号 {{scope.container_code||'—'}}</span><span v-if="scope.site">站点 {{scope.site}}</span></p></div></div>
   <p v-if="scope" class="rh-hint">包含环境历史与当前店铺的关联执行，当次店铺身份以详情为准。</p>
  </header>
  <div class="rh-toolbar"><span>共 <b>{{total}}</b> 次运行 <small>按创建时间从新到旧 · UTC+8</small></span><button :disabled="loading" @click="emit('refresh')"><span aria-hidden="true">↻</span> {{loading?'更新中…':'刷新记录'}}</button></div>
  <div v-if="error" class="rh-error" role="alert"><span>{{error}}</span><button :disabled="loading" @click="emit('refresh')">重试</button></div>
  <div class="rh-columns" aria-hidden="true"><span>执行时间</span><span>运行 / 操作</span><span>批次状态</span><span>操作</span></div>
  <div ref="list" class="rh-list" :aria-busy="loading" @scroll="emit('scroll',($event.target as HTMLElement).scrollTop)">
   <article v-for="run in runs" :key="run.id" class="rh-record" :aria-label="`运行 #${run.id}`">
    <div class="rh-record-main">
     <div class="rh-time"><time :datetime="run.created_at">{{date(run.created_at)}}</time><small>{{time(run.created_at)}}</small></div>
     <div class="rh-task"><h3><span>#{{run.id}}</span>{{tasks(run.tasks)}}</h3><p><span class="rh-trigger">{{run.trigger==='scheduled'?'定时':'手动'}}</span><span>{{run.plan_name||'临时执行'}}</span><span v-if="run.operation_name&&run.operation_name!==run.plan_name&&run.operation_name!=='临时执行'&&run.operation_name!==tasks(run.tasks)">{{run.operation_name}}</span></p></div>
     <span class="rh-status" :class="run.status">{{label(run.status)}}</span>
     <button class="rh-detail" @click="emit('open',run,scope&&run.items.length===1?run.items[0].id:null)">详情 <span aria-hidden="true">→</span></button>
    </div>
    <div class="rh-record-content">
     <div v-if="scope" class="rh-items">
      <div v-for="item in run.items" :key="item.id" class="rh-item">
       <div class="rh-item-line"><span v-if="run.items.length>1" class="rh-environment">{{item.environment_name||`环境 #${item.environment_id}`}}</span><span class="rh-status" :class="item.status">{{label(item.status)}}</span><span class="rh-identity">{{item.shop?`${item.shop.name} / ${item.shop.site||'—'} / ${item.shop.external_id||'按环境归档'}`:'当次尚未识别店铺'}}</span><button v-if="run.items.length>1" class="rh-item-detail" :aria-label="`查看${item.environment_name||'环境'}详情`" @click="emit('open',run,item.id)">详情 →</button></div>
       <div class="rh-outcomes"><span>采集 <b>{{label(item.collection_status)}}</b></span><span>上品 <b>{{label(item.submission)}}</b></span><span v-if="item.result?.listing">{{listingSummary(item.result.listing)}}</span></div>
       <details v-if="item.error" class="rh-failure"><summary><span>{{item.error}}</span><small>展开</small></summary><p>{{item.error}}</p></details>
      </div>
     </div>
     <span v-else class="rh-environment-count">{{runEnvironmentScope(run.items)}}</span>
     <div class="rh-device"><span>设备 <b>{{run.device_name||`设备 #${run.agent_id}`}}</b></span><span>执行人 <b>{{run.owner_name||`成员 #${run.owner_id}`}}</b></span></div>
    </div>
   </article>
   <div v-if="!runs.length" class="rh-empty"><span aria-hidden="true">{{loading?'◌':'☷'}}</span><h3>{{loading?'正在加载运行记录…':error?'暂时无法加载':'暂无运行记录'}}</h3><p>{{loading?'请稍候':error?'请点击上方重试':scope?'此环境与关联店铺尚无执行历史':'创建运行后，可在这里查看执行结果。'}}</p></div>
   <details v-if="!scope" class="rh-legacy"><summary>历史固定 XLSX 上品记录</summary><slot name="legacy"/></details>
  </div>
  <footer class="rh-pagination"><span>第 {{page}} / {{pages}} 页</span><div><button :disabled="loading||page<=1" @click="changePage(page-1)">上一页</button><button :disabled="loading||page>=pages" @click="changePage(page+1)">下一页</button></div></footer>
 </section>
</div>
</template>

<style scoped>
.rh-backdrop{z-index:70;padding:16px;background:#19213a66;backdrop-filter:blur(3px)}
.rh-dialog{display:flex;flex-direction:column;width:min(1100px,calc(100vw - 32px));height:84vh;max-height:88vh;overflow:hidden;padding:0;border-radius:14px;background:#fff;color:#30374b;font-size:12px;line-height:1.6;box-shadow:0 24px 80px #17203a30}
.rh-dialog *{box-sizing:border-box}.rh-dialog button{display:inline-flex;align-items:center;justify-content:center;gap:8px;width:auto;min-height:32px;margin:0;padding:5px 11px;border:1px solid #e1e4ed;border-radius:6px;background:#fff;color:#616a7d;font:inherit;font-size:12px;cursor:pointer;flex-shrink:0;white-space:nowrap}.rh-dialog button:hover{background:#f7f4ff;border-color:#c9bdef;color:#6043d4}.rh-dialog button:disabled{opacity:.45;cursor:not-allowed}.rh-dialog button:focus-visible,.rh-dialog summary:focus-visible{outline:2px solid #7256e7;outline-offset:2px}
.rh-dialog>.rh-header{display:block;width:100%;height:auto;padding:20px 24px 16px;border-bottom:1px solid #e8eaf1;flex-shrink:0;background:linear-gradient(115deg,#fcfbff,#fff 65%)}.rh-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.rh-eyebrow{font-size:11px;color:#9299aa;letter-spacing:.4px}.rh-heading h2{margin:2px 0 0;font-size:19px;font-weight:650}.rh-context{display:flex;align-items:center;gap:12px;margin-top:18px;min-width:0}.rh-shop-icon{display:grid;place-items:center;width:40px;height:40px;border-radius:10px;background:#eee9fc;color:#7050d7;font-size:16px;flex-shrink:0}.rh-context h3{margin:0;font-size:15px;font-weight:600;overflow-wrap:anywhere}.rh-context p{display:flex;flex-wrap:wrap;gap:4px 18px;margin:2px 0 0;font-size:11px;color:#9299a8}.rh-header .rh-hint{margin:10px 0 0;color:#9299a8;font-size:11px}
.rh-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 24px;flex-shrink:0;color:#8791a3}.rh-toolbar b{color:#505b70;font-weight:600}.rh-toolbar small{margin-left:12px;font-size:10px;color:#a0a7b5}.rh-columns,.rh-record-main{display:grid;grid-template-columns:130px minmax(0,1fr) 110px 76px;align-items:center;gap:16px}.rh-columns{padding:9px 24px;background:#f8f9fc;border-top:1px solid #eef0f5;border-bottom:1px solid #eef0f5;color:#969eae;font-size:11px;flex-shrink:0}.rh-columns>span:last-child{text-align:right}.rh-list{flex:1;min-height:0;overflow:auto;scrollbar-gutter:stable}.rh-record{padding:16px 24px;border-bottom:1px solid #eceef4}.rh-record:hover{background:#fdfcfe}.rh-time time{display:block;color:#667287;font-size:12px}.rh-time small{display:block;margin-top:2px;color:#a0a7b5;font-size:11px}.rh-task{min-width:0}.rh-task h3{display:flex;align-items:baseline;gap:8px;margin:0;font-size:13px;font-weight:600;overflow-wrap:anywhere}.rh-task h3>span{color:#929aad;font-size:11px;font-weight:400;flex-shrink:0}.rh-task p{display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;margin:4px 0 0;color:#8d96a7;font-size:11px}.rh-trigger{border-radius:4px;padding:0 5px;background:#f0edf8;color:#8978b2;font-size:10px}.rh-status{display:inline-flex;justify-self:start;align-items:center;flex-shrink:0;border-radius:5px;padding:2px 7px;background:#f0f1f5;color:#7b8597;font-size:10px;white-space:nowrap}.rh-status.failed,.rh-status.permission_revoked{background:#fff0f0;color:#c34c58}.rh-status.succeeded{background:#eaf7f0;color:#26875e}.rh-status.running{background:#eee9ff;color:#6a4bd5}.rh-status.partial_success,.rh-status.awaiting_attention{background:#fff5df;color:#a67923}.rh-dialog .rh-detail{justify-self:end;color:#6043d4;border-color:#e4ddf5;background:#faf8ff}.rh-record-content{margin:10px 0 0 146px}.rh-items{display:flex;flex-direction:column;gap:10px}.rh-item{padding:10px 12px;background:#f8f9fc;border-radius:6px;min-width:0}.rh-item-line{display:flex;align-items:center;gap:8px;min-width:0}.rh-identity{font-size:11px;color:#7d889c;overflow-wrap:anywhere;min-width:0}.rh-environment{font-size:11px;color:#5b677d}.rh-dialog .rh-item-detail{margin-left:auto;padding:0 4px;min-height:24px;border:0;background:transparent;color:#7050d7;font-size:11px}.rh-outcomes{display:flex;align-items:center;flex-wrap:wrap;gap:6px 18px;margin-top:6px;font-size:10px;color:#9aa3b3}.rh-outcomes b{margin-left:4px;color:#748097;font-weight:400}.rh-device{display:flex;flex-wrap:wrap;gap:4px 20px;margin-top:8px;font-size:10px;color:#a0a8b6;overflow-wrap:anywhere}.rh-device b{margin-left:4px;color:#8993a5;font-weight:400}.rh-failure{margin-top:8px;border-radius:4px;padding:7px 9px;background:#fff0f1;color:#bc5662;font-size:11px}.rh-failure summary{display:flex;align-items:flex-start;gap:10px;cursor:pointer;list-style:none}.rh-failure summary>span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;flex:1;min-width:0}.rh-failure small{flex-shrink:0;color:#bb7b84;font-size:10px}.rh-failure[open] summary>span,.rh-failure[open] summary small{display:none}.rh-failure[open] summary:after{content:'收起异常';color:#bb7b84;font-size:10px}.rh-failure p{margin:5px 0 0;color:inherit;font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere}.rh-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 24px;border-top:1px solid #e8eaf1;flex-shrink:0;color:#929bab;font-size:11px;background:#fff}.rh-pagination>div{display:flex;gap:8px}.rh-empty{padding:56px 20px;text-align:center;color:#9ca4b3}.rh-empty>span{font-size:26px;color:#c1b7de}.rh-empty h3{margin:8px 0 0;font-size:13px;color:#7b8598;font-weight:500}.rh-empty p{margin:6px 0 0;color:#a0a7b5;font-size:11px}.rh-error{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 24px 12px;padding:8px 12px;border-radius:6px;background:#fff2f2;color:#b8515d;font-size:12px;overflow-wrap:anywhere}.rh-legacy{padding:16px 24px;color:#8791a3}.rh-legacy summary{cursor:pointer}.rh-environment-count{overflow-wrap:anywhere;font-size:11px;color:#929bad}
@media(max-width:700px){.rh-backdrop{padding:8px}.rh-dialog{width:calc(100vw - 16px);height:92dvh;max-height:92dvh}.rh-header{padding:14px 16px}.rh-heading h2{font-size:17px}.rh-context{margin-top:12px}.rh-context p{gap:3px 12px}.rh-toolbar{padding:10px 16px}.rh-toolbar small{display:block;margin:2px 0 0}.rh-columns{display:none}.rh-record{padding:14px 16px}.rh-record-main{grid-template-columns:minmax(0,1fr) auto;gap:8px 12px}.rh-time{grid-column:1;display:flex;gap:8px;align-items:baseline}.rh-time time,.rh-time small{font-size:10px;margin:0}.rh-task{grid-column:1;grid-row:2}.rh-record-main>.rh-status{grid-column:2;grid-row:1;justify-self:end}.rh-detail{grid-column:2;grid-row:2}.rh-record-content{margin:12px 0 0}.rh-item-line{flex-wrap:wrap}.rh-identity{font-size:10px;flex:1}.rh-pagination{padding:10px 16px}.rh-error{margin:0 16px 12px}.rh-header .rh-hint{font-size:10px}}
</style>
