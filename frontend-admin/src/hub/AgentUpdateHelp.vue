<script setup lang="ts">
import {computed,ref,watch,onUnmounted} from 'vue'
import axios from 'axios'
import {updateRecovery,platformSteps} from './update-recovery'
const props=defineProps<{token:string;device?:any;distribution?:string;canRetry?:boolean;busy?:boolean;companyId?:number|null}>()
const state=computed(()=>props.device?.update_state)
const recovery=computed(()=>updateRecovery(state.value))
const channel=computed(()=>state.value?.distribution||props.distribution||'signed')
const guidance=ref(false),loading=ref(false),downloading=ref(''),error=ref(''),loaded=ref(false),requested=ref(false)
type Installer={id:number;platform:string;arch:string;version:string;filename:string;distribution:string}
const packages=ref<Installer[]>([])
const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8001'})
// 平台后台按所选公司读取安装包；ERP 公司端继续使用自己的矩阵入口。
const base=computed(()=>props.companyId?`/admin/matrix/companies/${props.companyId}`:'/hub-v5')
const retryBusy=ref(false)
let retryTimer:ReturnType<typeof setTimeout>|undefined
const controller=new AbortController()
const auth=()=>({headers:{Authorization:`Bearer ${props.token}`},signal:controller.signal})
async function load(){
 if(loading.value)return
 loading.value=true;error.value=''
 try{
  const {data}=await api.get(`${base.value}/agent-installers`,{...auth(),params:{distribution:channel.value,agent_id:props.device?.id}})
  packages.value=data.items.filter((p:Installer)=>!props.device?.platform||p.platform===props.device.platform)
  loaded.value=true
 }catch{if(!controller.signal.aborted)error.value='安装包列表读取失败，请重试。'}finally{loading.value=false}
}
async function show(){guidance.value=!guidance.value;if(guidance.value)await load()}
async function download(item:Installer){
 if(downloading.value)return
 downloading.value=item.filename;error.value=''
 try{
  const {data}=await api.get(`${base.value}/agent-installers/${item.platform}/${item.arch}/file`,{...auth(),params:{release_id:item.id,distribution:item.distribution,agent_id:props.device?.id},responseType:'blob'})
  if(controller.signal.aborted)return
  const url=URL.createObjectURL(data),link=document.createElement('a');link.href=url;link.download=item.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 }catch{if(!controller.signal.aborted)error.value='下载失败，版本可能已撤回。请刷新列表后重试。'}finally{downloading.value=''}
}
async function retry(){
 if(retryBusy.value||requested.value||!props.device?.id)return
 retryBusy.value=true;error.value=''
 try{
  await api.post(`${base.value}/agents/${props.device.id}/commands`,{kind:'retry_update'},auth())
  requested.value=true;if(retryTimer)clearTimeout(retryTimer);retryTimer=setTimeout(()=>{requested.value=false},60000)
 }catch(e:any){if(!controller.signal.aborted)error.value=e.response?.data?.detail||'重试请求未发送成功，请稍后再试。'}finally{retryBusy.value=false}
}
watch(()=>`${props.device?.id}:${state.value?.status}:${state.value?.failed_sha256}`,()=>{requested.value=false})
watch(()=>`${props.device?.id}:${channel.value}:${base.value}`,()=>{packages.value=[];loaded.value=false;if(guidance.value)void load()})
onUnmounted(()=>{controller.abort();if(retryTimer)clearTimeout(retryTimer)})
</script>
<template>
<section class="agent-update-help" aria-label="连接器更新处理">
 <div class="auh-heading"><strong>{{recovery.needed?'连接器更新未完成':'连接器更新与手动安装'}}</strong><span v-if="state?.target_version">目标版本 {{state.target_version}}</span></div>
 <p>{{recovery.needed?recovery.message:'可查看系统允许步骤和当前可用安装包。网页不能代替 Windows 或 macOS 授予运行许可。'}}</p>
 <div class="auh-actions"><button type="button" :aria-expanded="guidance" @click="show">{{guidance?'收起处理步骤':'查看处理步骤与手动安装包'}}</button><button v-if="recovery.canRetry&&canRetry" type="button" :disabled="busy||retryBusy||requested||!device?.online" @click="retry">{{requested?'已请求重试':retryBusy?'发送中…':'处理后重试更新'}}</button></div>
 <p v-if="requested" role="status">请求已发出；连接器会在收到命令且当前任务结束后重新检查，未处理的系统限制仍可能阻止启动。</p>
 <div v-if="guidance" class="auh-guide"><ol><li v-for="step in platformSteps(device?.platform||'',String(state?.error_code||''))" :key="step">{{step}}</li></ol><p>下载列表显示当前向此设备开放的最新版本，可能与上次失败版本不同。已撤回的版本不再提供。</p><p v-if="channel==='internal'">内部 ZIP 未经商业代码签名／Apple 公证，仍可能需要系统人工确认；更新包继续验证公司的签名和文件摘要。</p>
 <div class="auh-actions"><button type="button" :disabled="loading" @click="load">{{loading?'正在读取…':'刷新安装包'}}</button><button v-for="item in packages" :key="item.id" type="button" :disabled="!!downloading" @click="download(item)">{{downloading===item.filename?'下载中…':`下载 ${item.platform==='windows'?'Windows':'macOS'} ${item.arch==='arm64'?'Apple 芯片':'Intel / x64'} ${item.version}${item.distribution==='internal'?'（内部 ZIP）':''}`}}</button></div>
 <p v-if="loaded&&!packages.length&&!loading">当前暂无匹配安装包，请联系平台管理员上传或开放对应版本。</p></div><p v-if="error" class="auh-error" role="alert">{{error}}</p>
</section>
</template>
<style scoped>
.agent-update-help{margin:10px 0;padding:12px 14px;border:1px solid #ead8ba;border-radius:8px;background:#fffbf3;color:#785e36;font-size:12px;line-height:1.7;min-width:0}.auh-heading,.auh-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px}.auh-heading strong{font-weight:600}.auh-heading span{font-size:11px}.agent-update-help p{margin:8px 0;overflow-wrap:anywhere}.auh-actions button{width:auto;max-width:100%;min-height:34px;padding:5px 10px;border:1px solid #dcc9a8;border-radius:6px;background:#fff;color:#785e36;font:inherit;white-space:normal;cursor:pointer}.auh-actions button:disabled{opacity:.55;cursor:default}.auh-actions button:focus-visible{outline:2px solid var(--admin-primary,#2563eb);outline-offset:2px}.auh-guide{margin-top:12px;border-top:1px solid #ead8ba;padding-top:8px}.auh-guide ol{padding-left:20px;margin:8px 0}.auh-guide li{margin:6px 0}.auh-error{color:#a33636}@media(max-width:600px){.agent-update-help{padding:12px}.auh-actions{align-items:stretch;flex-direction:column}.auh-actions button{width:100%}}
</style>
