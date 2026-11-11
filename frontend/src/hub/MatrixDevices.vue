<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {deviceSetup} from './matrix'
const updateLabels:Record<string,string>={idle:'等待检查',checking:'检查更新',downloading:'正在下载',waiting_idle:'等待当前任务完成',restart_requested:'正在重启',installed:'更新成功',rolled_back:'已恢复上一版本',retry:'下载失败，稍后重试',rejected:'包校验失败',no_trusted_keys:'更新公钥未配置',insufficient_space:'磁盘空间不足',installer_required:'请下载新版安装程序',up_to_date:'已是最新版本'}
function updateLabel(state:any){return updateLabels[state?.status]||'尚未上报'}
const props=defineProps<{devices:any[];config:{enabled:boolean;listing_enabled:boolean};busy:boolean;administrator?:boolean}>()
const emit=defineEmits<{save:[device:any,identity:string];command:[device:any,kind:string]}>()
const drafts=ref<Record<number,string>>({}),previous:Record<number,string>={}
const expanded=ref<Record<number,boolean>>({})
const deviceRows=computed(()=>props.devices.map(d=>({device:d,setup:deviceSetup(d,props.config)})))
watch(()=>props.devices,devices=>{for(const d of devices){if(!(d.id in drafts.value)||drafts.value[d.id]===previous[d.id])drafts.value[d.id]=d.hub_identity||'';previous[d.id]=d.hub_identity||''}},{immediate:true})
</script>
<template>
<div class="matrix-devices">
  <p v-if="!devices.length" class="md-empty">暂无设备，启动连接器并在 ERP 完成授权后会自动显示。</p>
  <article v-for="{device:d,setup} in deviceRows" :key="d.id" class="md-card">
    <div class="md-heading"><b :title="d.name">{{d.name}}</b><span class="md-badge" :class="{'is-online':d.online&&d.is_active}">{{!d.is_active?'已撤销':d.online?'在线':'离线'}}</span></div>
    <div class="md-overview">
      <div class="md-metrics"><span>成员 <b>{{d.user_name||'—'}}</b></span><span>环境 <b>{{d.environment_count??'—'}}</b></span><span>任务 <b>{{!d.is_active||!d.online?'不可接收':d.paused?'已暂停':setup.code==='ready'?'按方案接收':'未就绪'}}</b></span><span v-if="!['ready','offline','revoked','paused'].includes(setup.code)" class="md-attention">{{setup.title}}</span></div>
      <div class="md-actions"><button class="md-primary" :disabled="busy||!setup.canSync" @click="emit('command',d,'refresh')">{{setup.code==='hub'?'重新连接':'同步环境'}}</button><button class="md-toggle" :aria-expanded="!!expanded[d.id]" :aria-controls="`matrix-device-details-${d.id}`" :aria-label="`${expanded[d.id]?'收起':'查看'} ${d.name} 的设备详情`" @click="expanded[d.id]=!expanded[d.id]">{{expanded[d.id]?'收起详情':'查看详情'}}<span class="md-chevron" :class="{'is-expanded':expanded[d.id]}" aria-hidden="true">⌄</span></button></div>
    </div>
    <div v-show="expanded[d.id]" :id="`matrix-device-details-${d.id}`" class="md-details">
      <dl class="md-status"><div><dt>HubStudio</dt><dd :class="{'is-connected':d.hub_connected}">{{d.hub_connected?'已连接':'未连接'}}</dd></div><div><dt>环境同步</dt><dd>{{d.sync_at?new Date(d.sync_at).toLocaleString():'尚未同步'}}</dd></div><div><dt>设备 ID / 连接器版本</dt><dd>{{d.id}} / {{d.version||'—'}}</dd></div><div><dt>自动更新</dt><dd>{{updateLabel(d.update_state)}}<span v-if="d.update_state?.status==='downloading'&&d.update_state?.progress"> {{d.update_state.progress}}%</span><span v-if="d.update_state?.target_version"> · 目标 {{d.update_state.target_version}}</span><span v-if="d.update_state?.error_code"> · {{d.update_state.error_code}}</span></dd></div><div><dt>站点能力</dt><dd>采集 {{d.capabilities?.['shop.collect']?.join(' / ')||'未开放'}} · 上品 {{d.capabilities?.['listing.catalog']?.join(' / ')||'未开放'}}</dd></div></dl>
      <div class="md-guidance" :class="{'is-ready':setup.code==='ready'}"><b>{{setup.title}}</b><span>{{setup.description}}</span></div>
      <form v-if="d.version!=='协议4'&&d.is_active" class="md-connection" @submit.prevent="emit('save',d,drafts[d.id].trim())"><label :for="`matrix-team-${d.id}`">Hub 团队 ID</label><input :id="`matrix-team-${d.id}`" v-model="drafts[d.id]" required maxlength="120" placeholder="当前登录团队的稳定 ID"/><button :disabled="busy||!drafts[d.id]?.trim()||drafts[d.id]?.trim()===d.hub_identity">保存团队</button><small>同一 HubStudio 团队的电脑填写相同 ID，勿填环境编号。</small></form>
      <div v-if="d.is_active" class="md-detail-actions"><button v-if="d.version!=='协议4'" :disabled="busy" title="仅影响接收新任务，不中止运行中的任务" @click="emit('command',d,d.paused?'resume':'pause')">{{d.paused?'恢复接收':'暂停接收'}}</button><button v-if="administrator" class="md-revoke" :disabled="busy" @click="emit('command',d,'revoke')">撤销授权</button></div>
    </div>
  </article>
</div>
</template>
<style scoped>
.matrix-devices{min-width:0;color:#4f586c;font-size:12px}.matrix-devices *{box-sizing:border-box}
.md-card{display:flex;flex-direction:column;gap:10px;margin:10px 0;padding:14px;border:1px solid #e4e6ee;border-radius:8px;background:#fff}
.md-heading,.md-overview,.md-metrics,.md-actions,.md-detail-actions{display:flex;align-items:center;gap:8px}.md-heading b{flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px}.md-badge{flex:none;padding:2px 7px;border-radius:4px;background:#f0f1f5;color:#8a92a2;font-size:10px}.md-badge.is-online{background:#eaf7f0;color:#338260}
.md-overview{justify-content:space-between;flex-wrap:wrap;gap:10px 16px}.md-metrics{flex-wrap:wrap;gap:6px 20px;min-width:0;color:#8992a3;font-size:11px}.md-metrics b{margin-left:5px;color:#596377;font-weight:500;overflow-wrap:anywhere}.md-metrics .md-attention{color:#9b7835}.md-actions{flex:none;margin-left:auto}
small{color:#8992a3;font-size:11px;line-height:1.7}.md-details{border-top:1px solid #eff0f5;padding-top:12px}.md-status{display:grid;grid-template-columns:.8fr 1.2fr .8fr 1.2fr;gap:12px;margin:0 0 12px}.md-status>div{min-width:0}.md-status dt{color:#8a92a2;font-size:11px;margin-bottom:5px}.md-status dd{margin:0;color:#727b8e;font-size:11px;overflow-wrap:anywhere}.md-status .is-connected{color:#338260}
.md-guidance{display:flex;flex-direction:column;gap:4px;padding:9px 11px;border-radius:6px;background:#f7f5fc;font-size:11px;line-height:1.7;color:#858096}.md-guidance b{color:#7d68a4;font-weight:500}.md-guidance.is-ready{background:#f0f8f4}.md-guidance.is-ready b{color:#338260}
.md-connection{display:grid;grid-template-columns:86px minmax(0,1fr) auto;align-items:center;gap:6px 8px;margin:12px 0}.md-connection label{margin:0;font-size:12px;font-weight:400}.md-connection small{grid-column:2/-1}.md-connection input{display:block;width:100%;min-width:0;height:36px;margin:0;padding:7px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:inherit;font:inherit}
.matrix-devices button{display:inline-flex;align-items:center;justify-content:center;flex:none;gap:6px;width:auto;min-height:32px;margin:0;padding:5px 10px;border:1px solid #dfe2eb;border-radius:6px;background:#fff;color:#687186;box-shadow:none;font:inherit;font-size:11px;line-height:20px;white-space:nowrap;cursor:pointer}.matrix-devices button:hover{border-color:#b6a7d9;color:#6043d4}.matrix-devices button:disabled{opacity:.45;cursor:not-allowed}.matrix-devices .md-primary{background:#6043d4;border-color:#6043d4;color:#fff}.matrix-devices .md-toggle{border-color:transparent;color:#77668f}.md-chevron{display:inline-block;line-height:1}.md-chevron.is-expanded{transform:rotate(180deg)}.matrix-devices .md-revoke{border-color:transparent;color:#a55d63}.md-connection button{min-height:36px}.md-detail-actions{justify-content:flex-end;margin-top:12px;padding-top:10px;border-top:1px solid #eff0f5}.md-empty{margin:0;padding:28px;text-align:center;color:#8992a3}.matrix-devices :is(button,input):focus-visible{outline:2px solid #7256e7;outline-offset:2px}
@media(max-width:700px){.md-status{grid-template-columns:1fr 1fr}.md-connection{grid-template-columns:minmax(0,1fr) auto}.md-connection label,.md-connection small{grid-column:1/-1}.md-metrics{gap:6px 14px}.md-actions{width:100%;justify-content:flex-end}.md-card{padding:12px}}
</style>
