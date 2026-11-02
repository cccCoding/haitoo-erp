<script setup lang="ts">
import {ref,watch} from 'vue'
import {deviceSetup} from './matrix'
const props=defineProps<{devices:any[];config:{enabled:boolean;listing_enabled:boolean};busy:boolean;administrator?:boolean}>()
const emit=defineEmits<{save:[device:any,identity:string];command:[device:any,kind:string]}>()
const drafts=ref<Record<number,string>>({}),previous:Record<number,string>={}
watch(()=>props.devices,devices=>{for(const d of devices){if(!(d.id in drafts.value)||drafts.value[d.id]===previous[d.id])drafts.value[d.id]=d.hub_identity||'';previous[d.id]=d.hub_identity||''}},{immediate:true})
</script>
<template>
<div class="matrix-devices">
  <p v-if="!devices.length" class="md-empty">暂无设备，启动连接器并在 ERP 完成授权后会自动显示。</p>
  <article v-for="d in devices" :key="d.id" class="md-card">
    <div class="md-heading"><b :title="d.name">{{d.name}}</b><span class="md-badge" :class="{'is-online':d.online&&d.is_active}">{{!d.is_active?'已撤销':d.online?'连接器在线':'连接器离线'}}</span><small>{{d.user_name}} · {{d.version}}</small></div>
    <div class="md-status"><div><span>HubStudio</span><b :class="{'is-connected':d.hub_connected}">{{d.hub_connected?'已连接':'未连接'}}</b></div><div><span>环境同步</span><b>{{d.sync_at?new Date(d.sync_at).toLocaleString():'尚未同步'}}</b></div><div><span>任务接收</span><b>{{!d.is_active||!d.online?'不可接收':d.paused?'已暂停':deviceSetup(d,config).code==='ready'?'按方案接收':'未就绪'}}</b></div></div>
    <div class="md-guidance" :class="{'is-ready':deviceSetup(d,config).code==='ready'}"><b>{{deviceSetup(d,config).title}}</b><span>{{deviceSetup(d,config).description}}</span></div>
    <form v-if="d.version!=='协议4'&&d.is_active" class="md-connection" @submit.prevent="emit('save',d,drafts[d.id].trim())"><label :for="`matrix-team-${d.id}`">Hub 团队 ID</label><input :id="`matrix-team-${d.id}`" v-model="drafts[d.id]" required maxlength="120" placeholder="当前登录团队的稳定 ID"/><button :disabled="busy||!drafts[d.id]?.trim()||drafts[d.id]?.trim()===d.hub_identity">保存团队</button><small>同一 HubStudio 团队的电脑填写相同 ID，勿填环境编号。</small></form>
    <div class="md-footer"><small><template v-if="d.environment_count!=null">{{d.environment_count}} 个环境 · </template>采集 {{d.capabilities?.['shop.collect']?.join(' / ')||'未开放'}} · 上品 {{d.capabilities?.['listing.catalog']?.join(' / ')||'未开放'}}</small><div class="md-actions"><button class="md-primary" :disabled="busy||!deviceSetup(d,config).canSync" @click="emit('command',d,'refresh')">{{deviceSetup(d,config).code==='hub'?'重新连接':'同步环境'}}</button><button v-if="d.is_active&&d.version!=='协议4'" :disabled="busy" title="仅影响接收新任务，不中止运行中的任务" @click="emit('command',d,d.paused?'resume':'pause')">{{d.paused?'恢复接收':'暂停接收'}}</button><button v-if="administrator&&d.is_active" class="md-revoke" :disabled="busy" @click="emit('command',d,'revoke')">撤销授权</button></div></div>
  </article>
</div>
</template>
<style scoped>
.matrix-devices{min-width:0;color:#4f586c;font-size:12px}.matrix-devices *{box-sizing:border-box}
.md-card{display:flex;flex-direction:column;gap:9px;margin:10px 0;padding:14px;border:1px solid #e4e6ee;border-radius:8px;background:#fff}
.md-heading,.md-footer,.md-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.md-heading b{flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px}.md-heading>small{margin-left:auto}.md-badge{padding:2px 6px;border-radius:4px;background:#f0f1f5;color:#8a92a2;font-size:10px}.md-badge.is-online{background:#eaf7f0;color:#338260}
small{color:#8992a3;font-size:11px;line-height:1.7}.md-status{display:grid;grid-template-columns:.8fr 1.4fr .8fr;gap:12px;padding:10px 0;border-block:1px solid #f0f1f5}.md-status>div{display:flex;flex-direction:column;gap:5px;min-width:0}.md-status span{color:#8a92a2;font-size:11px}.md-status b{color:#727b8e;font-size:11px;font-weight:500;overflow-wrap:anywhere}.md-status .is-connected{color:#338260}
.md-guidance{display:flex;flex-direction:column;gap:4px;padding:9px 11px;border-radius:6px;background:#f7f5fc;font-size:11px;line-height:1.7;color:#858096}.md-guidance b{color:#7d68a4;font-weight:500}.md-guidance.is-ready{background:#f0f8f4}.md-guidance.is-ready b{color:#338260}
.md-connection{display:grid;grid-template-columns:86px minmax(0,1fr) auto;align-items:center;gap:6px 8px;margin:4px 0}.md-connection label{margin:0;font-size:12px;font-weight:400}.md-connection small{grid-column:2/-1}.md-connection input{display:block;width:100%;min-width:0;height:36px;margin:0;padding:7px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:inherit;font:inherit}
.matrix-devices button{display:inline-flex;align-items:center;justify-content:center;flex:none;gap:6px;width:auto;min-height:32px;margin:0;padding:5px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#687186;box-shadow:none;font:inherit;font-size:11px;line-height:20px;white-space:nowrap;cursor:pointer}.matrix-devices button:hover{border-color:#b6a7d9;color:#6043d4}.matrix-devices button:disabled{opacity:.45;cursor:not-allowed}.matrix-devices .md-primary{background:#6043d4;border-color:#6043d4;color:#fff}.matrix-devices .md-revoke{border-color:transparent;color:#a55d63}.md-connection button{min-height:36px}.md-footer{justify-content:space-between;padding-top:10px;border-top:1px solid #eff0f5}.md-empty{margin:0;padding:28px;text-align:center;color:#8992a3}.matrix-devices :is(button,input):focus-visible{outline:2px solid #7256e7;outline-offset:2px}
@media(max-width:700px){.md-heading b{flex-basis:100%}.md-status{grid-template-columns:1fr 1.2fr}.md-status>div:last-child{grid-column:1/-1;flex-direction:row;gap:8px}.md-connection{grid-template-columns:minmax(0,1fr) auto}.md-connection label,.md-connection small{grid-column:1/-1}.md-actions{width:100%}.md-card{padding:12px}}
</style>
