<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
const props = defineProps<{tasks:any[]; token:string}>()
const emit = defineEmits<{changed:[]; preview:[url:string]}>()
const selected = ref<string[]>([]), busy = ref(false), error = ref('')
const broken = ref<Record<string,boolean>>({})
function candidate(task:any,url:string) { return task.result_images?.find((item:any)=>item.source_url===url) }
function displayUrl(task:any,url:string) { return candidate(task,url)?.display_url || url }
function availability(task:any,url:string) {
  const item=candidate(task,url)
  if(item?.state==='ready') return '已永久保存'
  if(item?.state==='invalid') return item.error || '候选图不可采用'
  if(item?.state==='expired' || item?.expires_at && item.expires_at<=Date.now()) return '候选图已过期，无法采用'
  return item?.expires_at ? `保留至 ${new Date(item.expires_at).toLocaleDateString()}` : ''
}
const api = axios.create({baseURL:import.meta.env.VITE_API_URL || 'http://localhost:8000'})
const key = (id:number,url:string) => JSON.stringify([id,url])
const images = computed(() => props.tasks.flatMap(task => (task.result_urls || []).map((url:string,index:number) => ({task,url,index,key:key(task.id,url)}))))
const selectable = computed(() => images.value.filter(item=>item.task.can_review))
const allSelected = computed(() => selectable.value.length>0 && selectable.value.every(item=>selected.value.includes(item.key)))
function selectAll() { selected.value = allSelected.value ? [] : selectable.value.map(item=>item.key) }
function review(task:any,url:string) { return task.result_reviews?.find((item:any)=>item.url===url) }
async function mark(rejected:boolean, only?:{task:any;url:string}) {
  if (busy.value) return
  const items = only ? [{task_id:only.task.id,url:only.url}] : images.value.filter(item=>selected.value.includes(item.key) && item.task.can_review).map(item=>({task_id:item.task.id,url:item.url}))
  if (!items.length) return
  busy.value=true; error.value=''
  try {
    for (let offset=0;offset<items.length;offset+=1000) await api.post('/tasks/result-reviews',{items:items.slice(offset,offset+1000),rejected},{headers:{Authorization:`Bearer ${props.token}`}})
    selected.value=[]
  } catch(e:any) {error.value=e.response?.data?.detail || '标记失败，请刷新后重试'}
  finally {busy.value=false;emit('changed')}
}
function imageUrl(url:string) { return /^https?:\/\//i.test(url) ? url : `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${url}` }
</script>
<template>
  <section class="result-gallery" :aria-busy="busy">
    <div v-if="selectable.length" class="result-review-toolbar"><button class="secondary" :disabled="busy" @click="selectAll">全选／取消全选</button><span>已选 {{selected.length}} 张</span><button class="secondary" :disabled="busy || !selected.length" @click="mark(true)">批量标记不合格</button><button class="ghost" :disabled="busy || !selected.length" @click="mark(false)">批量取消标记</button></div>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <div class="result-review-table-wrap">
      <table class="result-review-table" aria-label="结果图质量标记列表">
        <thead><tr><th class="result-select-cell"><input v-if="selectable.length" type="checkbox" :checked="allSelected" :indeterminate="!allSelected && selected.length>0" :disabled="busy" aria-label="全选可标记结果图" @change="selectAll"/><span v-else>选择</span></th><th>结果图</th><th>任务编号</th><th>质量状态</th><th>标记信息</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in images" :key="item.key" :class="{rejected:review(item.task,item.url)?.rejected,selected:selected.includes(item.key)}">
            <td class="result-select-cell"><input v-if="item.task.can_review" v-model="selected" :value="item.key" type="checkbox" :disabled="busy" :aria-label="`选择任务 ${item.task.id} 第 ${item.index+1} 张结果图`"/><span v-else>—</span></td>
            <td><button type="button" class="result-preview" :aria-label="`查看任务 ${item.task.id} 第 ${item.index+1} 张结果图大图`" @click="emit('preview',displayUrl(item.task,item.url))"><img :src="imageUrl(displayUrl(item.task,item.url))" :alt="`任务 #${item.task.id} 结果图 ${item.index+1}`" @error="broken[item.key]=true" @load="broken[item.key]=false"/></button><small>{{availability(item.task,item.url)}}</small><small v-if="broken[item.key]">图片加载失败</small></td>
            <td class="result-task-cell">#{{item.task.id}}</td>
            <td><span class="result-quality-status" :class="{rejected:review(item.task,item.url)?.rejected}">{{review(item.task,item.url)?.rejected ? '不合格' : review(item.task,item.url) ? '已取消标记' : '未标记'}}</span></td>
            <td class="result-review-info"><template v-if="review(item.task,item.url)"><span>{{review(item.task,item.url).marked_by_name}}</span><small>{{new Date(review(item.task,item.url).marked_at).toLocaleString()}}</small></template><span v-else>—</span></td>
            <td class="result-review-actions"><button v-if="item.task.can_review" type="button" class="ghost" :disabled="busy" @click="mark(!review(item.task,item.url)?.rejected,item)">{{review(item.task,item.url)?.rejected ? '取消不合格标记' : '标记不合格'}}</button><span v-else>—</span></td>
          </tr>
          <tr v-if="!images.length"><td colspan="6" class="result-review-empty">暂无生成结果图。</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
<style scoped>
.result-review-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:12px 0;font-size:13px}
.result-review-table-wrap{max-height:55vh;overflow:auto;border:1px solid #e8e3f0;border-radius:10px}
.result-review-table{width:100%;min-width:720px;border-collapse:collapse;font-size:13px;text-align:left}
.result-review-table th{position:sticky;top:0;z-index:1;background:#faf9fc;color:#817b91;font-size:12px;white-space:nowrap}
.result-review-table th,.result-review-table td{padding:12px 14px;border-bottom:1px solid #eeeaf5;vertical-align:middle}
.result-review-table tbody tr:last-child td{border-bottom:0}
.result-review-table tr.selected{background:#f8f5ff}.result-review-table tr.rejected{background:#fff8fa}
.result-review-table .result-select-cell{width:48px;text-align:center;padding-left:12px;padding-right:12px}
.result-select-cell input{width:16px;height:16px;margin:0;accent-color:#7054e7;cursor:pointer}
.result-preview{display:block;width:76px;height:90px;padding:0;border:1px solid #ebe7f1;border-radius:7px;background:white;overflow:hidden}
.result-preview img{display:block;width:100%;height:100%;object-fit:contain}
.result-task-cell{font-weight:600;white-space:nowrap}
.result-quality-status{display:inline-block;padding:4px 7px;border-radius:6px;background:#f0edf5;color:#817b91;font-size:12px;white-space:nowrap}.result-quality-status.rejected{background:#fce7ec;color:#c53e5b;font-weight:600}
.result-review-info{min-width:150px;overflow-wrap:anywhere}.result-review-info small{display:block;margin-top:5px;font-size:12px;color:#817b91}
.result-review-actions{white-space:nowrap}.result-review-actions button{padding:8px 0;font-size:12px}.result-review-actions button:disabled{cursor:wait;opacity:.6}
.result-review-table .result-review-empty{padding:36px;text-align:center;color:#817b91}
</style>
