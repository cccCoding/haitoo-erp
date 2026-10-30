<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import SearchableSelect from './SearchableSelect.vue'
import { categoryChoices, categoryEdits, type CategoryEdit } from './title-categories'

const props = defineProps<{ taskId: number; token: string; resolution: any; editable: boolean; disabled?: boolean }>()
const emit = defineEmits<{ changed: [resolution: any]; pending: [value: boolean]; refresh: [] }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const edits = ref<CategoryEdit[]>([]), baseline = ref(''), saving = ref(false), error = ref('')
const adjusting = ref<string[]>([])
let disposed = false
onBeforeUnmount(() => { disposed = true })
watch(() => props.resolution, value => {
  edits.value = categoryEdits(value?.items || []); baseline.value = JSON.stringify(edits.value); error.value = ''; adjusting.value = []
}, { immediate: true })
const dirty = computed(() => JSON.stringify(edits.value) !== baseline.value)
const originalEdits = computed(() => categoryEdits(props.resolution?.items || []))
function rowChanged(index: number) { return JSON.stringify(edits.value[index]) !== JSON.stringify(originalEdits.value[index]) }
function hasSelection(index: number) {
  const edit = edits.value[index]
  return !!edit?.selection && (edit.selection !== 'new' || !!edit.newName.trim())
}
function rowState(item: any, index: number) {
  if (!hasSelection(index)) return { label: '待选择', tone: 'pending' }
  if (rowChanged(index)) return { label: '待确认', tone: 'edited' }
  if (['disabled', 'conflict'].includes(item.match)) return { label: '需处理', tone: 'blocked' }
  return { label: item.match === 'alias' ? '别名匹配' : item.match === 'standard' ? '已匹配' : '已确认', tone: 'matched' }
}
function showSelector(item: any, index: number) {
  return props.editable && (rowState(item, index).tone !== 'matched' || adjusting.value.includes(item.source_key))
}
function selectedName(index: number) {
  const edit = edits.value[index]
  return edit.selection === 'new' ? edit.newName.trim() : props.resolution?.options.find((item:any) => item.id === edit.selection)?.name || ''
}
function showAlias(item: any, index: number) {
  const normalize = (value:string) => value.normalize('NFKC').toLocaleLowerCase().trim().replace(/\s+/g, ' ')
  return hasSelection(index) && !['standard', 'alias'].includes(item.match) && normalize(item.source) !== normalize(selectedName(index))
}
const unresolved = computed(() => (props.resolution?.items || []).filter((item:any,index:number) => ['pending','blocked'].includes(rowState(item,index).tone)).length)
const changedCount = computed(() => edits.value.filter((_,index) => rowChanged(index)).length)
const showSave = computed(() => dirty.value || !props.resolution?.ready)
watch(() => saving.value || dirty.value, value => emit('pending', value), { immediate: true })
const choices = computed(() => [{ value: 'new', label: '＋ 新建分类（入库时创建）' },
  ...(props.resolution?.options || []).filter((row:any) => row.enabled).map((row:any) => ({ value: row.id,
    label: `${row.name}${row.aliases.length ? ` · 别名：${row.aliases.join('、')}` : ''}` }))])
async function save() {
  if (saving.value || props.disabled) return
  saving.value = true; error.value = ''
  try {
    const body = { token: props.resolution.token, choices: categoryChoices(edits.value) }
    const { data } = await api.put(`/title-imports/${props.taskId}/categories`, body,
      { headers: { Authorization: `Bearer ${props.token}` } })
    if (disposed) return
    edits.value = categoryEdits(data.items); baseline.value = JSON.stringify(edits.value)
    adjusting.value = []
    emit('changed', data)
  } catch (e:any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || '分类确认失败' }
  finally { saving.value = false }
}
</script>

<template>
  <section v-if="resolution" class="import-categories" aria-label="导入分类确认">
    <header class="category-heading">
      <div class="category-heading-copy"><div class="category-heading-title"><h3>分类确认</h3><span class="category-total">{{resolution.items.length}} 个分类</span></div><p>已匹配的分类可直接使用，其余请选择已有分类或新建。</p></div>
      <span class="category-summary" :class="unresolved?'pending':dirty?'edited':'matched'" role="status"><span class="status-dot" />{{unresolved?`${unresolved} 项待处理`:dirty?`${changedCount} 项待确认`:'分类已就绪'}}</span>
    </header>
    <div class="category-columns" aria-hidden="true"><span>文件中的分类</span><span /><span>归入标准分类</span><span>匹配状态</span></div>
    <div class="category-list">
      <article v-for="(item,index) in resolution.items" :key="item.source_key" class="category-row" :class="`category-row-${rowState(item,index).tone}`">
        <div class="category-source"><strong>{{item.source}}</strong><span>{{item.row_count.toLocaleString()}} 行</span></div>
        <svg class="category-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <div class="category-choice">
          <template v-if="showSelector(item,index)">
            <SearchableSelect v-model="edits[index].selection" :options="choices" :disabled="disabled||saving" :aria-label="`为${item.source}选择标准分类`" placeholder="选择已有分类或新建" search-placeholder="搜索标准名称或别名" />
            <label v-if="edits[index].selection==='new'" class="new-category-label">新分类名称<input v-model="edits[index].newName" maxlength="255" :disabled="disabled||saving" /></label>
            <label v-if="showAlias(item,index)" class="save-alias"><input v-model="edits[index].saveAlias" type="checkbox" :disabled="disabled||saving" />以后将“{{item.source}}”自动归入此分类</label>
            <div v-if="item.match==='unknown'&&!edits[index].selection&&item.suggestions.length" class="suggestions"><span>相似分类</span><button v-for="option in item.suggestions" :key="option.id" type="button" :disabled="disabled||saving" :title="'仅文字相似，请核对实际含义'" @click="edits[index].selection=option.id">{{option.name}}<span aria-hidden="true">↗</span></button></div>
          </template>
          <div v-else class="category-target"><span>{{selectedName(index)||item.target_name||'尚未归类'}}</span><button v-if="editable" type="button" :disabled="disabled||saving" :aria-label="`调整${item.source}的分类`" @click="adjusting.push(item.source_key)">调整</button></div>
          <p v-if="['disabled','conflict'].includes(item.match)&&!rowChanged(index)&&item.message" class="category-message">{{item.message}}</p>
        </div>
        <span class="category-state" :class="rowState(item,index).tone"><svg v-if="rowState(item,index).tone==='matched'" width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 10 3 3 7-7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg><span v-else class="status-dot" />{{rowState(item,index).label}}</span>
      </article>
    </div>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <footer class="category-footer"><p>新分类与别名将在选中结果入库时保存。</p><div v-if="editable" class="category-actions"><button type="button" class="category-refresh" :disabled="disabled||saving" @click="emit('refresh')"><svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M15.5 7A6 6 0 1 0 16 12M15.5 3.5V7H12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>重新匹配</button><button v-if="showSave" type="button" class="primary category-save" :disabled="disabled||saving||unresolved>0" @click="save">{{saving?'保存中…':'确认分类'}}</button></div></footer>
  </section>
</template>

<style scoped>
.import-categories{min-width:0;border:1px solid #e8e4ef;border-radius:12px;background:#fff;color:#393247}
.category-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;height:auto;min-height:0;padding:18px 20px 16px;border:0;background:transparent}
.category-heading-copy{min-width:0}.category-heading-title{display:flex;align-items:center;gap:10px}.import-categories .category-heading h3{margin:0;font-size:15px;font-weight:650;line-height:1.5}.category-total{font-size:12px;color:#928a9e}
.import-categories .category-heading p{margin:5px 0 0;color:#8b8296;font-size:12px;line-height:1.6}
.category-summary,.category-state{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;font-size:11px;font-weight:500}.category-summary{flex-shrink:0;padding:5px 8px;border-radius:6px}.category-summary.pending{color:#ab771f;background:#fff7e8}.category-summary.edited{color:#7552c8;background:#f3effd}.category-summary.matched{color:#34846c;background:#edf7f2}
.status-dot{width:5px;height:5px;flex-shrink:0;border-radius:50%;background:currentColor}
.category-columns,.category-row{display:grid;grid-template-columns:minmax(90px,1fr) 16px minmax(200px,2fr) 74px;column-gap:14px;align-items:start;padding:13px 20px}
.category-columns{padding-top:9px;padding-bottom:9px;background:#faf9fc;border-top:1px solid #f0edf5;border-bottom:1px solid #f0edf5;color:#9a91a4;font-size:11px}.category-columns>span:last-child{text-align:right}
.category-row+.category-row{border-top:1px solid #f0edf5}.category-source{display:grid;gap:4px;padding-top:9px;min-width:0}.category-source strong{font-size:13px;font-weight:600;line-height:1.5;overflow-wrap:anywhere}.category-source>span{font-size:11px;color:#a098aa;font-variant-numeric:tabular-nums}
.category-arrow{margin-top:12px;color:#c5bece}.category-choice{display:grid;gap:9px;min-width:0}.category-choice :deep(.search-select-trigger){box-sizing:border-box;min-height:38px;padding:9px 11px;border-radius:8px;font-size:12px;font-weight:400}.category-choice :deep(.search-select-search input){box-sizing:border-box;font-size:12px;padding:8px 10px}.category-choice :deep(.search-select-option){font-size:12px}
.category-choice .new-category-label{display:grid;gap:5px;margin:0;font-size:11px;font-weight:400;color:#8b8296}.category-choice .new-category-label input{box-sizing:border-box;width:100%;min-width:0;margin:0;padding:9px 11px;font-size:12px;border:1px solid #e4deee;border-radius:8px}
.category-choice .save-alias{display:flex!important;align-items:flex-start;gap:6px;margin:0;font-size:11px;font-weight:400;line-height:1.6;color:#8c8299;overflow-wrap:anywhere}.category-choice .save-alias input{box-sizing:border-box;display:block!important;width:13px!important;height:13px;margin:2px 0 0!important;padding:0;flex-shrink:0;accent-color:#7455d8;border-radius:3px}
.category-target{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:38px;font-size:13px}.category-target>span{overflow-wrap:anywhere}.category-target>button{padding:4px 0;background:none;color:#a096b0;font-size:11px;white-space:nowrap;font-weight:400}.category-target>button:hover{color:#7455d8}
.category-state{justify-self:end;margin-top:12px;color:#96909e}.category-state.matched{color:#5a9a83}.category-state.pending{color:#b38a43}.category-state.edited{color:#8966d0}.category-state.blocked{color:#b66559}
.suggestions{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11px;color:#a198ab}.suggestions button{display:inline-flex;gap:5px;align-items:center;padding:3px 7px;border:1px solid #eae4f5;border-radius:5px;background:#faf8fe;color:#8769bc;font-size:11px;font-weight:400}.suggestions button:hover{border-color:#cbb9e9;background:#f4effc}
.import-categories .category-message{margin:0;color:#ab6751;font-size:11px;line-height:1.6}.import-categories>.error{margin:0;padding:0 20px 12px;font-size:12px;line-height:1.6;color:#b35a64}
.category-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;border-top:1px solid #f0edf5;background:#fcfbfd;border-radius:0 0 12px 12px}.import-categories .category-footer>p{margin:0;color:#aaa1b3;font-size:11px;line-height:1.6}.category-actions{display:flex;align-items:center;gap:14px;flex-shrink:0}.category-refresh{display:inline-flex;align-items:center;gap:5px;padding:5px 0;font-size:11px;color:#9d93ab;font-weight:400;background:none}.category-refresh:hover{color:#7455d8}.category-save{padding:8px 12px;border-radius:7px;font-size:12px;font-weight:500;white-space:nowrap}
.category-save:disabled{background:#eee9f7;color:#a99abb;box-shadow:none;cursor:not-allowed}
@media(max-width:600px){.category-heading{align-items:flex-start;padding:15px 14px}.category-heading-copy{flex:1}.category-heading-title{gap:7px}.category-summary{font-size:10px;padding:4px 6px}.category-columns{display:none}.category-row{grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:14px;border-top:1px solid #f0edf5}.category-source{display:flex;align-items:baseline;flex-wrap:wrap;gap:8px;padding:0}.category-arrow{display:none}.category-state{grid-column:2;grid-row:1;margin:1px 0 0}.category-choice{grid-column:1/-1;grid-row:2}.category-target{min-height:26px;padding-left:11px;border-left:2px solid #e6e0f0}.category-footer{align-items:flex-start;flex-wrap:wrap;padding:12px 14px;gap:8px}.category-actions{margin-left:auto}.category-heading p{max-width:240px}}
</style>
