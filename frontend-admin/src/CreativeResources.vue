<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { dialogFocus as vDialogFocus } from './dialog-focus'

type ResourceType = 'prompts' | 'white-images'
interface Resource {
  id: number; name: string; user_id: number; template_id: number
  user_name: string | null; template_name: string | null; updated_at: number
  content?: string; image_url?: string
}
interface SizeResult { size_bytes: number | null; status: string }
const props = defineProps<{ token: string; companyId: number | null; companyName: string }>()
const emit = defineEmits<{ unauthorized: [] }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001' })
const resourceType = ref<ResourceType>('prompts')
const creatorId = ref(''), templateId = ref(''), query = ref('')
const templates = ref<{id: number; name: string}[]>([]), members = ref<{id: number; name: string}[]>([])
const filtersReady = ref(false)
const rows = ref<Resource[]>([]), total = ref(0), page = ref(1), pageSize = ref(20)
const loading = ref(false), error = ref(''), detail = ref<Resource | null>(null)
const sizes = ref<Record<number, SizeResult>>({})
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const headers = computed(() => ({ Authorization: `Bearer ${props.token}` }))
let requestId = 0, disposed = false, activeSizeRequests = 0
let controller = new AbortController()
let sizeQueue: number[][] = []

function imageUrl(url: string) { return url?.startsWith('/') ? `${api.defaults.baseURL}${url}` : url }
function date(value: number) { return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }
function sizeLabel(id: number) {
  const result = sizes.value[id]
  if (!result || result.status === 'loading') return '大小读取中'
  if (result.status !== 'available' || result.size_bytes === null) return '大小暂不可用'
  const bytes = result.size_bytes
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
function message(e: any, fallback: string) {
  if (e.response?.status === 401) emit('unauthorized')
  return typeof e.response?.data?.detail === 'string' ? e.response.data.detail : fallback
}
function closeDetail() { detail.value = null }
function invalidate() {
  requestId++; controller.abort(); controller = new AbortController(); sizeQueue = []; sizes.value = {}
  closeDetail()
}
function processSizeQueue() {
  while (!disposed && activeSizeRequests < 2 && sizeQueue.length) {
    const ids = sizeQueue.shift()!
    const generation = requestId, selectedCompany = props.companyId, signal = controller.signal
    activeSizeRequests++
    void api.get('/admin/data/creative-resources/white-image-sizes', {
      headers: headers.value, signal, params: { company_id: selectedCompany, image_ids: ids },
      paramsSerializer: { indexes: null },
    }).then(({ data }) => {
      if (generation !== requestId || disposed) return
      const results = new Map<number, SizeResult>(data.items.map((item: any) => [item.id, item]))
      for (const id of ids) sizes.value[id] = results.get(id) || { size_bytes: null, status: 'unavailable' }
    }).catch((e: any) => {
      if (generation !== requestId || disposed) return
      message(e, '大小暂不可用')
      for (const id of ids) sizes.value[id] = { size_bytes: null, status: 'unavailable' }
    }).finally(() => { activeSizeRequests--; processSizeQueue() })
  }
}
function queueSizes(ids: number[]) {
  for (const id of ids) sizes.value[id] = { size_bytes: null, status: 'loading' }
  for (let index = 0; index < ids.length; index += 20) sizeQueue.push(ids.slice(index, index + 20))
  processSizeQueue()
}
async function refresh(withFilters = true) {
  invalidate()
  const id = requestId
  rows.value = []; total.value = 0; error.value = ''; loading.value = false
  if (!props.companyId) return
  loading.value = true
  const options = { headers: headers.value, signal: controller.signal }
  try {
    const [list, filters] = await Promise.all([
      api.get('/admin/data/creative-resources', { ...options, params: {
        company_id: props.companyId, resource_type: resourceType.value,
        creator_id: creatorId.value || undefined, template_id: templateId.value || undefined,
        query: query.value.trim() || undefined, page: page.value, page_size: pageSize.value,
      } }),
      withFilters || !filtersReady.value ? api.get('/admin/data/creative-resources/filters', {
        ...options, params: { company_id: props.companyId },
      }) : Promise.resolve(null),
    ])
    if (id !== requestId || disposed) return
    rows.value = list.data.items; total.value = list.data.total; page.value = list.data.page
    if (filters) { templates.value = filters.data.templates; members.value = filters.data.members; filtersReady.value = true }
    if (resourceType.value === 'white-images') queueSizes(rows.value.map(row => row.id))
  } catch (e: any) {
    if (id === requestId && !disposed) error.value = message(e, '加载创作素材失败，请重试')
  } finally { if (id === requestId && !disposed) loading.value = false }
}
function search() { page.value = 1; void refresh(false) }
function reset() { creatorId.value = ''; templateId.value = ''; query.value = ''; search() }
function changeType(next: ResourceType) {
  if (resourceType.value === next) return
  resourceType.value = next; search()
}
function changePage(next: number) { page.value = next; void refresh(false) }
watch(() => [props.companyId, props.token], () => {
  resourceType.value = 'prompts'; creatorId.value = ''; templateId.value = ''; query.value = ''; page.value = 1
  templates.value = []; members.value = []; filtersReady.value = false; void refresh()
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { disposed = true; invalidate() })
defineExpose({ refresh })
</script>

<template>
  <section class="creative-resources">
    <nav class="creative-tabs" role="tablist" aria-label="创作素材类型">
      <button v-for="item in [{key:'prompts' as const,label:'创作要求'},{key:'white-images' as const,label:'白底图'}]" :id="`creative-tab-${item.key}`" :key="item.key" role="tab" :aria-selected="resourceType===item.key" aria-controls="creative-panel" :class="{active:resourceType===item.key}" @click="changeType(item.key)">{{item.label}}</button>
    </nav>
    <form class="creative-filters" @submit.prevent="search">
      <label>员工<select v-model="creatorId"><option value="">全部员工</option><option v-for="item in members" :key="item.id" :value="String(item.id)">{{item.name}}</option></select></label>
      <label>产品模板<select v-model="templateId"><option value="">全部模板</option><option v-for="item in templates" :key="item.id" :value="String(item.id)">{{item.name}}</option></select></label>
      <label class="creative-keyword">关键词<input v-model="query" type="search" maxlength="1000" :placeholder="resourceType==='prompts'?'搜索名称或创作要求':'搜索白底图名称'"/></label>
      <div class="creative-filter-actions"><button class="primary" type="submit" :disabled="loading || !companyId">{{loading?'加载中…':'搜索'}}</button><button class="secondary" type="button" :disabled="loading || !companyId" @click="reset">重置</button></div>
    </form>
    <section id="creative-panel" role="tabpanel" :aria-labelledby="`creative-tab-${resourceType}`" :aria-busy="loading">
      <header class="creative-heading"><h3>{{resourceType==='prompts'?'创作要求':'白底图'}}</h3><span v-if="!loading && !error && companyId">共 {{total}} 条 · 只读</span></header>
      <p v-if="error" class="creative-empty error" role="alert">{{error}} <button class="secondary" @click="refresh()">重试</button></p>
      <p v-else-if="loading" class="creative-empty" role="status">正在加载创作素材…</p>
      <p v-else-if="!companyId" class="creative-empty">请选择公司查看创作素材。</p>
      <p v-else-if="!rows.length" class="creative-empty">没有符合筛选条件的{{resourceType==='prompts'?'创作要求':'白底图'}}。</p>
      <div v-else class="creative-grid" :class="{'white-image-grid':resourceType==='white-images'}">
        <article v-for="row in rows" :key="row.id" class="creative-card">
          <button v-if="resourceType==='white-images'" class="creative-image" :aria-label="`放大白底图 ${row.name}`" @click="detail=row"><img :src="imageUrl(row.image_url || '')" :alt="row.name" loading="lazy"/></button>
          <div class="creative-card-body"><h3>{{row.name}}</h3><p v-if="resourceType==='prompts'" class="creative-excerpt">{{row.content}}</p><div class="creative-meta"><span>员工：{{row.user_name || '信息缺失'}}</span><span>模板：{{row.template_name || '信息缺失'}}</span><span>更新：{{date(row.updated_at)}}</span></div>
            <div v-if="resourceType==='white-images'" class="creative-size" aria-live="polite"><span>文件大小：{{sizeLabel(row.id)}}</span><button v-if="sizes[row.id] && !['available','loading'].includes(sizes[row.id].status)" class="secondary" @click="queueSizes([row.id])">重试</button></div>
            <button v-else class="secondary" @click="detail=row">查看详情</button>
          </div>
        </article>
      </div>
      <footer class="creative-pagination"><span v-if="!loading && !error && companyId">共 {{total}} 条</span><label>每页 <select v-model.number="pageSize" :disabled="loading || !companyId" @change="search"><option v-for="size in [20,50,100,200]" :key="size" :value="size">{{size}}</option></select> 条</label><button class="secondary" :disabled="loading || !companyId || page<=1" @click="changePage(page-1)">上一页</button><span>第 {{page}} / {{pageCount}} 页</span><button class="secondary" :disabled="loading || !companyId || page>=pageCount" @click="changePage(page+1)">下一页</button></footer>
    </section>
  </section>
  <div v-if="detail" v-dialog-focus="{close:closeDetail}" class="modal-backdrop" @click.self="closeDetail">
    <section class="creative-detail" role="dialog" aria-modal="true" aria-labelledby="creative-detail-title">
      <header><h2 id="creative-detail-title">{{detail.name}}</h2><button class="secondary" autofocus @click="closeDetail">关闭</button></header>
      <p>{{companyName}} · 只读</p><div class="creative-meta"><span>员工：{{detail.user_name || '信息缺失'}}</span><span>模板：{{detail.template_name || '信息缺失'}}</span><span>更新：{{date(detail.updated_at)}}</span></div>
      <template v-if="resourceType==='white-images'"><img :src="imageUrl(detail.image_url || '')" :alt="detail.name"/><div class="creative-size" aria-live="polite"><span>文件大小：{{sizeLabel(detail.id)}}</span><button v-if="sizes[detail.id] && !['available','loading'].includes(sizes[detail.id].status)" class="secondary" @click="queueSizes([detail.id])">重试</button></div></template>
      <p v-else class="creative-full-content">{{detail.content}}</p>
    </section>
  </div>
</template>
