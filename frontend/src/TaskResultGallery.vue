<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
const props = defineProps<{tasks:any[]; token:string}>()
const emit = defineEmits<{changed:[]; preview:[url:string]}>()
const selected = ref<string[]>([]), busy = ref(false), error = ref('')
const api = axios.create({baseURL:import.meta.env.VITE_API_URL || 'http://localhost:8000'})
const key = (id:number,url:string) => JSON.stringify([id,url])
const images = computed(() => props.tasks.flatMap(task => (task.result_urls || []).map((url:string) => ({task,url,key:key(task.id,url)}))))
const selectable = computed(() => images.value.filter(item=>item.task.can_review))
function selectAll() { selected.value = selected.value.length===selectable.value.length ? [] : selectable.value.map(item=>item.key) }
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
    <div class="result-gallery-grid"><article v-for="item in images" :key="item.key" :class="{rejected:review(item.task,item.url)?.rejected}">
      <label v-if="item.task.can_review" class="review-image-select"><input v-model="selected" :value="item.key" type="checkbox" :disabled="busy"/>选择结果图</label>
      <button class="result-preview" @click="emit('preview',item.url)"><img :src="imageUrl(item.url)" :alt="`任务 #${item.task.id} 结果图`"/></button>
      <small>任务 #{{item.task.id}}</small><strong v-if="review(item.task,item.url)?.rejected" class="error">不合格</strong>
      <small v-if="review(item.task,item.url)">{{review(item.task,item.url).marked_by_name}} · {{new Date(review(item.task,item.url).marked_at).toLocaleString()}}{{review(item.task,item.url).rejected ? '' : ' · 已取消标记'}}</small>
      <button v-if="item.task.can_review" class="ghost" :disabled="busy" @click="mark(!review(item.task,item.url)?.rejected,item)">{{review(item.task,item.url)?.rejected ? '取消不合格标记' : '标记不合格'}}</button>
    </article></div>
    <p v-if="!images.length" class="empty">暂无生成结果图。</p>
  </section>
</template>
<style scoped>
.result-review-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:12px 0;font-size:13px}.result-gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px}.result-gallery-grid article{display:flex;flex-direction:column;gap:8px;border:1px solid #e8e3f0;border-radius:10px;padding:12px}.result-gallery-grid article.rejected{border-color:#d24662;background:#fff8fa}.review-image-select{font-size:12px;display:flex;gap:8px;align-items:center}.result-preview{padding:0;width:100%;height:190px}.result-preview img{width:100%;height:100%;object-fit:contain}.result-gallery-grid small{font-size:12px;color:#817b91;overflow-wrap:anywhere}.result-gallery-grid .ghost{font-size:12px;padding:8px 0}
</style>
