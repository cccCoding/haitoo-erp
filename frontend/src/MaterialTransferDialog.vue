<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { runMaterialTransfers, type MaterialTransferItem } from './material-transfer'
import { dialogFocus as vDialogFocus } from './dialog-focus'
const props = defineProps<{ visible: boolean; items: MaterialTransferItem[] }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const busy = ref(false)
let stopped = false
let version = 0
const counts = computed(() => ({ created: props.items.filter(item => item.outcome === 'created').length,
  duplicate: props.items.filter(item => item.outcome === 'duplicate').length,
  error: props.items.filter(item => item.outcome === 'error').length }))
const labels = { pending: '等待处理', running: '处理中…', created: '已创建', duplicate: '重复，已跳过', error: '失败' }
async function run() {
  if (busy.value) return
  busy.value = true
  const items = props.items, current = version
  try { await runMaterialTransfers(items, () => props.visible && !stopped && version === current && props.items === items) }
  finally {
    busy.value = false
    emit('changed')
    if (!stopped && props.visible && version !== current) void run()
  }
}
function retry() {
  for (const item of props.items) if (item.outcome === 'error') { item.outcome = 'pending'; item.error = '' }
  void run()
}
function forceSelected() {
  for (const item of props.items) if (item.selected && item.outcome === 'duplicate') {
    item.force = true; item.requestKey = crypto.randomUUID(); item.outcome = 'pending'; item.selected = false
  }
  void run()
}
watch([() => props.visible, () => props.items], ([visible]) => { version++; if (visible) void run() }, { flush: 'sync' })
onUnmounted(() => { stopped = true; version++ })
</script>
<template>
  <div v-if="visible" v-dialog-focus="{close:()=>emit('close')}" class="modal-backdrop" @click.self="emit('close')">
    <section class="modal-card transfer-dialog" role="dialog" aria-modal="true" aria-labelledby="transfer-title">
      <button class="modal-close" aria-label="关闭处理结果" @click="emit('close')">×</button>
      <h2 id="transfer-title">素材处理结果</h2>
      <p>已创建 {{counts.created}} 张 · 重复跳过 {{counts.duplicate}} 张 · 失败 {{counts.error}} 张</p>
      <p>相同图片默认跳过。选择“仍创建新素材/SKU”将共用已保存图片，不重复保存文件。</p>
      <div class="transfer-results">
        <article v-for="item in items" :key="item.id">
          <img v-if="item.preview" :src="item.preview" alt="素材预览" loading="lazy"/>
          <div><b>{{item.label}}</b><small>{{labels[item.outcome]}}</small><small v-if="item.error" class="error">{{item.error}}</small>
            <label v-if="item.outcome==='duplicate'"><input v-model="item.selected" type="checkbox" :disabled="busy"/>仍创建新素材/SKU</label>
          </div>
        </article>
      </div>
      <div class="modal-actions">
        <button class="ghost" @click="emit('close')">关闭</button>
        <button v-if="items.some(item=>item.outcome==='pending')" class="secondary" :disabled="busy" @click="run">继续处理</button>
        <button v-if="counts.error" class="secondary" :disabled="busy" @click="retry">重试失败项</button>
        <button class="primary" :disabled="busy || !items.some(item=>item.outcome==='duplicate' && item.selected)" @click="forceSelected">为选中的重复项创建新 SKU</button>
      </div>
      <p v-if="busy" role="status">正在处理。关闭后将停止提交剩余项目，已提交项目可能完成。</p>
    </section>
  </div>
</template>
<style scoped>
.transfer-dialog{position:relative;width:min(780px,calc(100vw - 32px))}.transfer-results{max-height:55vh;overflow:auto;display:grid;gap:10px}.transfer-results article{display:flex;gap:12px;border:1px solid #e7e3ee;border-radius:8px;padding:10px}.transfer-results img{width:64px;height:80px;object-fit:contain}.transfer-results article>div{min-width:0;display:grid;gap:6px;align-content:start}.transfer-results b,.transfer-results small{overflow-wrap:anywhere}.transfer-results label{display:flex;align-items:center;gap:8px}.transfer-results input{width:auto}.modal-actions{flex-wrap:wrap}.modal-actions button:disabled{opacity:.45;cursor:not-allowed}
</style>
