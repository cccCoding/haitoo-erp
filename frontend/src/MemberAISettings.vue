<script setup lang="ts">
import { computed, ref } from 'vue'
import { dialogFocus as vDialogFocus } from './dialog-focus'

const props = defineProps<{ member: any; providers: any[]; companyStorageId: string; directEnabled: boolean; client: any; authorization: Record<string, string> }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const tab = ref('grsai'), mode = ref(props.member.grsai_storage_mode || 'inherit'), storageId = ref(props.member.grsai_storage_id || '')
const apiKey = ref(''), saving = ref(false), error = ref(''), notice = ref('')
const orderedProviders = computed(() => [...props.providers].sort((a, b) => {
  const order = ['grsai', 'deepseek']
  const rank = (item: any) => { const index = order.indexOf(item.credential_provider || item.provider); return index < 0 ? order.length : index }
  return rank(a) - rank(b)
}))
const provider = computed(() => props.providers.find(item => (item.credential_provider || item.provider) === tab.value))
const configured = computed(() => !!props.member.ai_provider_credentials?.[tab.value])
const preview = computed(() => props.member.ai_provider_credential_previews?.[tab.value] || '')
function selectTab(value: string) { if (!saving.value) { tab.value = value; apiKey.value = ''; error.value = ''; notice.value = '' } }
function close() { if (!saving.value) { apiKey.value = ''; emit('close') } }
function message(exc: any) { return typeof exc.response?.data?.detail === 'string' ? exc.response.data.detail : '保存失败，请稍后重试' }
async function save() {
  if (saving.value) return
  error.value = ''; notice.value = ''
  if (tab.value === 'storage' && mode.value === 'custom' && !storageId.value.trim()) { error.value = '请填写存储库 ID'; return }
  if (tab.value !== 'storage' && !apiKey.value.trim()) { error.value = '请输入平台密钥'; return }
  saving.value = true
  try {
    if (tab.value === 'storage') await props.client.put(`/members/${props.member.id}/grsai-storage`, { mode: mode.value, storage_id: mode.value === 'custom' ? storageId.value.trim() : null }, { headers: props.authorization })
    else await props.client.put(`/members/${props.member.id}/ai-provider-credentials/${provider.value.provider}`, { api_key: apiKey.value.trim() }, { headers: props.authorization })
    apiKey.value = ''; notice.value = tab.value === 'storage' ? '存储设置已保存，后续新任务使用此设置。' : '平台密钥已安全保存。'
    emit('changed')
  } catch (exc) { error.value = message(exc) }
  finally { saving.value = false }
}
async function clearKey() {
  if (saving.value || !provider.value || !confirm(`确定清除 ${props.member.name} 的 ${provider.value.credential_display_name || provider.value.display_name} 平台密钥吗？`)) return
  saving.value = true; error.value = ''; notice.value = ''
  try { await props.client.delete(`/members/${props.member.id}/ai-provider-credentials/${provider.value.provider}`, { headers: props.authorization }); apiKey.value = ''; notice.value = '平台密钥已清除。'; emit('changed') }
  catch (exc) { error.value = message(exc) }
  finally { saving.value = false }
}
</script>

<template>
  <div class="modal-backdrop" @click.self="close">
    <section v-dialog-focus="{close, busy:saving}" class="modal-card ai-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="member-ai-title">
      <header class="ai-settings-header"><div><span class="ai-settings-eyebrow">成员设置</span><h2 id="member-ai-title">{{member.name}} 的 AI 配置</h2><p>管理图片存储方式与模型平台密钥。</p></div><button type="button" class="ai-dialog-close" :disabled="saving" aria-label="关闭 AI 配置" @click="close">关闭</button></header>
      <nav class="ai-settings-tabs" aria-label="AI 配置分类"><button v-for="item in orderedProviders" :key="item.credential_provider || item.provider" type="button" :aria-pressed="tab===(item.credential_provider || item.provider)" :class="{active:tab===(item.credential_provider || item.provider)}" :disabled="saving" @click="selectTab(item.credential_provider || item.provider)">{{item.credential_display_name || item.display_name}} 密钥</button><button type="button" :aria-pressed="tab==='storage'" :class="{active:tab==='storage'}" :disabled="saving" @click="selectTab('storage')">图片储存</button></nav>
      <form @submit.prevent="save">
        <div class="ai-settings-body">
          <template v-if="tab==='storage'">
            <fieldset class="ai-storage-modes" :disabled="saving"><legend>存储方式</legend>
              <label :class="{selected:mode==='inherit'}"><input v-model="mode" type="radio" value="inherit"/><span><b>使用公司默认</b><small>{{companyStorageId ? '随公司默认设置生效，新成员推荐使用。' : '公司尚未配置默认存储库，将使用原转存流程。'}}</small></span></label>
              <label :class="{selected:mode==='custom'}"><input v-model="mode" type="radio" value="custom"/><span><b>单独配置</b><small>为此成员指定 Grsai 存储库。</small></span></label>
              <label :class="{selected:mode==='legacy'}"><input v-model="mode" type="radio" value="legacy"/><span><b>使用原转存流程</b><small>生成结果通过业务服务器转存。</small></span></label>
            </fieldset>
            <label v-if="mode==='custom'" class="ai-settings-field">Grsai 存储库 ID<input v-model="storageId" maxlength="120" :disabled="saving" placeholder="填写此成员使用的存储库 ID"/><small>须属于该成员 API Key 可访问的账号，并指向本环境的候选桶。</small></label>
            <p v-if="!directEnabled && mode!=='legacy'" class="ai-settings-note">直存开关尚未启用，当前新任务仍使用原转存流程。</p>
          </template>
          <template v-else-if="provider"><div class="ai-key-status"><strong>{{provider.credential_display_name || provider.display_name}} 平台密钥</strong><span class="ai-storage-badge" :class="{enabled:configured}">{{configured ? '已配置' : '未配置'}}</span></div><p class="ai-settings-help">{{tab==='deepseek' ? '用于生成商品标题。' : '用于创建和查询 AI 图像任务。'}}密钥加密保存，仅展示脱敏预览。</p><p v-if="preview" class="ai-key-preview">当前密钥 <code>{{preview}}</code></p><label class="ai-settings-field">API Key<input v-model="apiKey" type="password" maxlength="2000" autocomplete="new-password" :disabled="saving" :placeholder="configured ? '输入新密钥以替换当前配置' : '请输入平台密钥'"/></label></template>
          <p v-if="error" class="ai-settings-feedback error" role="alert">{{error}}</p><p v-if="notice" class="ai-settings-feedback success" role="status">{{notice}}</p>
        </div>
        <footer class="ai-settings-footer"><button v-if="tab!=='storage' && configured" type="button" class="ai-key-remove" :disabled="saving" @click="clearKey">清除密钥</button><span></span><button type="button" class="ghost" :disabled="saving" @click="close">完成</button><button type="submit" class="primary" :disabled="saving || (tab==='storage' ? mode==='custom' && !storageId.trim() : !apiKey.trim())">{{saving ? '保存中…' : '保存设置'}}</button></footer>
      </form>
    </section>
  </div>
</template>
