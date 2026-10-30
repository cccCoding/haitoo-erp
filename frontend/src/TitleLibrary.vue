<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import TitleDictionaryManager from './TitleDictionaryManager.vue'
import TitleTemplateManager from './TitleTemplateManager.vue'
import TitlePagination from './TitlePagination.vue'
import TitleKeywordEvidence from './TitleKeywordEvidence.vue'
import TitleImportCategories from './TitleImportCategories.vue'
import { titleTagLabel } from './title-labels'
import { dialogFocus as vDialogFocus } from './dialog-focus'
import './title-library-layout.css'

const props = defineProps<{ token: string; user: any }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const config = computed(() => ({ headers: { Authorization: `Bearer ${props.token}` } }))
const admin = computed(() => props.user?.role === 'company_admin')
const platform = 'TikTok'
const showImport = ref(false)
const importDialogBody = ref<HTMLElement | null>(null)
const tab = ref('templates'), updated = ref('')
const busy = ref(false), error = ref(''), notice = ref(''), search = ref(''), status = ref(''), category = ref(''), tagFilter = ref(''), page = ref(1), pageSize = ref(20)
const words = ref<any[]>([]), total = ref(0), tasks = ref<any[]>([]), stats = ref<any>({})
const taskPage = ref(1), taskPageSize = ref(20), taskTotal = ref(0), taskListLoading = ref(false)
const taskPageCount = computed(() => Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value)))
const file = ref<File | null>(null), kind = ref('titles'), note = ref('')
const preview = ref<any>(null), activeTask = ref<any>(null), reviewOffset = ref(0), selected = ref<number[]>([])
const taskDetailId = ref<number | null>(null), taskDetailLoading = ref(false), taskError = ref('')
const previewCategoryPending = ref(false), taskCategoryPending = ref(false)
const taskFailureCount = computed(() => Object.keys(activeTask.value?.result?.failed_rows || {}).length)
const reviewPageSize = ref(20), reviewCategory = ref(''), reviewTag = ref(''), reviewImported = ref('')
const canConfirmImport = computed(() => admin.value && activeTask.value?.kind === 'import' && ['review', 'completed'].includes(activeTask.value?.state))
const reviewTotal = computed(() => activeTask.value?.result?.filtered_total ?? activeTask.value?.result?.word_total ?? 0)
const reviewPageIndexes = computed<number[]>(() => (activeTask.value?.result?.words || []).filter((word:any) => !word.imported).map((word:any) => word.index))
const reviewPageSelection = computed(() => {
  const selectedIndexes = new Set(selected.value)
  const count = reviewPageIndexes.value.filter(index => selectedIndexes.has(index)).length
  return { all: count > 0 && count === reviewPageIndexes.value.length, some: count > 0 && count < reviewPageIndexes.value.length }
})
const previewColumns = computed(() => preview.value?.kind === 'keywords'
  ? [{ key: '马来语词语', label: '马来语词语' }, { key: '中文释义', label: '中文释义' }, { key: '适用品类', label: '产品分类' }, { key: '属性分类', label: '标签' }]
  : [{ key: '原标题', label: '商品标题' }, { key: '商品品类', label: '商品分类' }])
const editing = ref<any>(null), editSynonyms = ref(''), editConflicts = ref(''), mergeTarget = ref('')
const evidence = ref<any>(null)
const dictionaryEntries = ref<any[]>([]), semanticTags = ref<string[]>([]), categoryFields = ref<string[]>(['品类','性别','年龄'])
const categories = computed(()=>dictionaryEntries.value.filter(row=>row.kind==='category'))
const tags = computed(()=>dictionaryEntries.value.filter(row=>row.kind==='tag'))
const editableTags = computed(()=>tags.value.filter(row=>editing.value?.tag!=='面料'||row.name!=='材质'))
const labels: Record<string,string> = {preview:'待确认上传',queued:'排队中',running:'处理中',review:'待确认入库',completed:'已完成',completed_with_errors:'部分失败',failed:'失败',cancelled:'已取消',pending:'未启用',enabled:'启用',disabled:'停用'}
let timer: ReturnType<typeof setInterval> | undefined, revision = 0, detailRequest = 0, disposed = false, refreshing = false
let loadedReviewCategory = '', loadedReviewTag = '', loadedReviewImported = ''
let loadedTaskPage = 1, loadedTaskPageSize = 20, loadedReviewOffset = 0, loadedReviewPageSize = 20, loadedWordPage = 1, loadedWordPageSize = 20
function failureMessage(e: any) { return typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || '操作失败' }
function failure(e: any) { error.value = failureMessage(e) }
function importKindLabel(task: any) { return task.import_kind === 'titles' ? '商品标题' : task.import_kind === 'keywords' ? '已整理关键词' : '—' }
async function load() {
  if (refreshing) return
  refreshing = true; taskListLoading.value = true; const current = revision
  try {
    const [market, list, jobs, statistics, dictionaries] = await Promise.all([
      api.get('/title-market', {...config.value,params:{platform:platform}}),
      api.get('/title-keywords', {...config.value,params:{platform:platform,search:search.value,status:status.value,category:category.value,tag:tagFilter.value,page:page.value,page_size:pageSize.value}}),
      api.get('/title-tasks', {...config.value,params:{platform:platform,kind:tab.value==='imports'?'import':'batch',page:taskPage.value,page_size:taskPageSize.value}}),
      api.get('/title-statistics', {...config.value,params:{platform:platform}}),
      api.get('/title-dictionaries', config.value),
    ])
    if (disposed || current !== revision) return
    updated.value=market.data.updated_at; dictionaryEntries.value=dictionaries.data.items;semanticTags.value=dictionaries.data.semantic_tags;categoryFields.value=dictionaries.data.category_fields||['品类','性别','年龄']
    words.value=list.data.items; total.value=list.data.total;page.value=list.data.page||1; tasks.value=jobs.data.items; taskTotal.value=jobs.data.total; taskPage.value=jobs.data.page||1; stats.value=statistics.data
    loadedTaskPage=taskPage.value;loadedTaskPageSize=taskPageSize.value
    loadedWordPage=page.value;loadedWordPageSize=pageSize.value
  } catch(e:any) { if(!disposed && current===revision){taskPage.value=loadedTaskPage;taskPageSize.value=loadedTaskPageSize;page.value=loadedWordPage;pageSize.value=loadedWordPageSize;failure(e)} }
  finally { refreshing=false; taskListLoading.value=false; if(!disposed && current!==revision)void load() }
}
async function action(run:()=>Promise<void>) {
  if(busy.value)return
  busy.value=true; error.value=''; notice.value=''
  try { await run() } catch(e:any){if(taskDetailId.value!==null)taskError.value=failureMessage(e);else failure(e)} finally{busy.value=false}
}
async function changeTaskPage(target: number) { if(taskListLoading.value)return;error.value='';taskPage.value=Math.min(Math.max(1,target),taskPageCount.value);revision++;await load() }
async function changeTaskPageSize(value:number) { if(taskListLoading.value)return;error.value='';taskPageSize.value=value;taskPage.value=1;revision++;await load() }
async function changeWordPage(value:number) { if(taskListLoading.value)return;error.value='';page.value=value;revision++;await load() }
async function changeWordPageSize(value:number) { if(taskListLoading.value)return;pageSize.value=value;await searchWords() }
async function searchWords(){error.value='';page.value=1;revision++;await load()}
function closeTask() { detailRequest++;taskDetailId.value=null;activeTask.value=null;taskDetailLoading.value=false;taskError.value='';selected.value=[];taskCategoryPending.value=false }
function openImport() { error.value=''; notice.value=''; preview.value=null; file.value=null; note.value=''; previewCategoryPending.value=false;showImport.value=true }
async function upload() {
  await action(async()=>{
    if(!file.value)throw new Error('请选择导入文件')
    const importKind=kind.value
    const body=new FormData();body.append('file',file.value);body.append('kind',importKind);body.append('note',note.value.trim());body.append('platform',platform)
    const {data}=await api.post('/title-imports',body,config.value);preview.value={...data,kind:importKind};await nextTick();importDialogBody.value?.scrollTo({top:0});notice.value=data.duplicate?'该文件已导入，复用已有任务':'请检查预览后开始提词';await load()
  })
}
async function viewExistingImport() {const id=preview.value.id;showImport.value=false;tab.value='imports';await nextTick();await openTask(id)}
async function refreshPreviewCategories() {await action(async()=>{const {data}=await api.get(`/title-tasks/${preview.value.id}`,config.value);preview.value={...preview.value,category_resolution:data.category_resolution}})}
async function taskCategoriesChanged(resolution:any) {activeTask.value.category_resolution=resolution;reviewCategory.value='';reviewOffset.value=0;selected.value=[];await openTask(activeTask.value.id,false)}
async function startImport() { await action(async()=>{const id=preview.value.id;await api.post(`/title-tasks/${id}/start`,{},config.value);preview.value=null;showImport.value=false;taskPage.value=1;revision++;tab.value='imports';await nextTick();await load();await openTask(id)}) }
async function openTask(id:number, reset=true) {
  if(reset){taskDetailId.value=id;activeTask.value=null;reviewOffset.value=0;loadedReviewOffset=0;loadedReviewPageSize=reviewPageSize.value;selected.value=[];reviewCategory.value='';reviewTag.value='';reviewImported.value='';loadedReviewCategory='';loadedReviewTag='';loadedReviewImported='';taskError.value='';notice.value=''}
  if(taskDetailId.value!==id)return
  const request=++detailRequest, current=revision, offset=reviewOffset.value
  taskDetailLoading.value=true
  try{const {data}=await api.get(`/title-tasks/${id}`,{...config.value,params:{offset,limit:reviewPageSize.value,category:reviewCategory.value,tag:reviewTag.value,imported:reviewImported.value||undefined}});if(!disposed&&current===revision&&request===detailRequest&&taskDetailId.value===id){activeTask.value=data;reviewOffset.value=data.result.offset??offset;loadedReviewOffset=reviewOffset.value;loadedReviewPageSize=reviewPageSize.value;loadedReviewCategory=reviewCategory.value;loadedReviewTag=reviewTag.value;loadedReviewImported=reviewImported.value;taskError.value=''}}
  catch(e:any){if(!disposed&&current===revision&&request===detailRequest&&taskDetailId.value===id){reviewOffset.value=loadedReviewOffset;reviewPageSize.value=loadedReviewPageSize;reviewCategory.value=loadedReviewCategory;reviewTag.value=loadedReviewTag;reviewImported.value=loadedReviewImported;taskError.value=failureMessage(e)}}
  finally{if(request===detailRequest)taskDetailLoading.value=false}
}
function changeReviewPage(value:number){if(busy.value||taskDetailLoading.value||!activeTask.value)return;reviewOffset.value=(value-1)*reviewPageSize.value;void openTask(activeTask.value.id,false)}
function changeReviewPageSize(value:number){if(busy.value||taskDetailLoading.value||!activeTask.value)return;reviewPageSize.value=value;reviewOffset.value=0;void openTask(activeTask.value.id,false)}
function changeReviewFilters(){if(busy.value||taskDetailLoading.value||!activeTask.value)return;reviewOffset.value=0;selected.value=[];void openTask(activeTask.value.id,false)}
async function taskAction(id:number, command:string) {taskError.value='';await action(async()=>{await api.post(`/title-tasks/${id}/${command}`,{},config.value);await openTask(id);await load()})}
async function confirmImport() {taskError.value='';await action(async()=>{const id=activeTask.value.id;await api.post(`/title-imports/${id}/confirm`,{selections:selected.value},config.value);notice.value='选中结果已入库并启用，可继续选择未入库词语';selected.value=[];await openTask(id,false);await load()})}
function selectPage() { selected.value=[...new Set([...selected.value,...activeTask.value.result.words.filter((w:any)=>!w.imported&&!['品牌','营销修饰'].includes(tags.value.find(t=>t.name===w.tag)?.semantic_tag||w.tag)).map((w:any)=>w.index)])] }
function toggleReviewPage(event:Event) {
  if(!canConfirmImport.value || busy.value || taskDetailLoading.value)return
  const pageIndexes = new Set(reviewPageIndexes.value)
  selected.value = (event.target as HTMLInputElement).checked
    ? [...new Set([...selected.value, ...pageIndexes])]
    : selected.value.filter(index => !pageIndexes.has(index))
}
function edit(word:any) { editing.value={...word,categories:[...word.categories]};editSynonyms.value=word.synonyms.join(',');editConflicts.value=word.conflicts.join(',');mergeTarget.value='' }
function split(value:string){return value.split(/[,，]/).map(s=>s.trim()).filter(Boolean)}
function showCategoryKeywords(value:string){category.value=value;search.value='';tagFilter.value='';status.value='';page.value=1;tab.value='words'}
async function saveWord() {await action(async()=>{
  const row=editing.value
  if(!row.categories.length)throw new Error('请至少选择一个产品分类')
  const conflictParts=split(editConflicts.value);if(conflictParts.some(s=>!/^\d+$/.test(s)))throw new Error('冲突关键词 ID 须为整数')
  await api.patch(`/title-keywords/${row.id}`,{phrase:row.phrase,translation:row.translation,tag:row.tag,categories:row.categories,synonyms:split(editSynonyms.value),conflicts:conflictParts.map(Number),priority:row.priority,is_borrowed:row.is_borrowed},config.value)
  editing.value=null;await load()
})}
async function mergeWord(){await action(async()=>{if(!/^\d+$/.test(mergeTarget.value))throw new Error('请填写目标关键词 ID');await api.post(`/title-keywords/${editing.value.id}/merge`,{target_id:Number(mergeTarget.value)},config.value);editing.value=null;await load()})}
function showEvidence(word:any){evidence.value=word}
async function setKeywordStatus(word:any){
  const nextStatus=word.status==='enabled'?'disabled':'enabled'
  await action(async()=>{
    await api.post(`/title-keywords/${word.id}/status`,{status:nextStatus,review_token:word.review_token},config.value)
    notice.value=nextStatus==='enabled'?'关键词已启用':'关键词已停用'
    await load()
  })
}
watch(tab,()=>{revision++;tasks.value=[];taskTotal.value=0;taskPage.value=1;loadedTaskPage=1;loadedTaskPageSize=taskPageSize.value;closeTask();void load()})
onMounted(()=>{void load();timer=setInterval(()=>{if(tasks.value.some(t=>['queued','running'].includes(t.state)))void load();if(activeTask.value&&['queued','running'].includes(activeTask.value.state)&&!taskDetailLoading.value&&!busy.value)void openTask(activeTask.value.id,false)},2500)})
onUnmounted(()=>{disposed=true;revision++;detailRequest++;if(timer)clearInterval(timer)})
</script>

<template>
  <section class="page title-library">
    <header class="title-library-heading"><div><p>马来西亚 · 马来语 <span v-if="updated" title="词库与标题配置最近一次保存的时间，包括保存模板属性、维护产品分类或标签、编辑或合并关键词、审核入库；上传预览、生成标题和刷新页面不会更新。按当前设备时区显示。">· 配置更新于 <time :datetime="updated">{{new Date(updated).toLocaleString()}}</time></span></p></div><div class="title-tools"><template v-if="admin"><button class="primary" :disabled="busy" @click="openImport">上传并预览</button></template></div></header>
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <div class="material-usage-tabs" role="tablist" aria-label="词库功能"><button v-for="item in [{key:'templates',label:'模板配置'},{key:'categories',label:'产品分类'},{key:'tags',label:'标签'},{key:'words',label:'关键词'},{key:'stats',label:'使用统计'},{key:'imports',label:'导入记录'}]" :id="`title-tab-${item.key}`" :key="item.key" role="tab" :aria-selected="tab===item.key" aria-controls="title-tab-content" :class="{active:tab===item.key}" @click="tab=item.key">{{item.label}}</button></div>
    <div id="title-tab-content" role="tabpanel" :aria-labelledby="`title-tab-${tab}`" class="title-tab-content">
    <TitleTemplateManager v-if="tab==='templates'" :token="token" :admin="admin" :categories="categories" @changed="load" />
    <TitleDictionaryManager v-if="tab==='categories'||tab==='tags'" :key="tab" :token="token" :kind="tab==='categories'?'category':'tag'" :entries="tab==='categories'?categories:tags" :semantic-tags="semanticTags" :admin="admin" @changed="load" @keywords="showCategoryKeywords" />
    <section v-if="tab==='words'" class="title-panel">
      <form class="creative-resource-filters title-library-filters" @submit.prevent="searchWords">
        <label class="title-library-search">搜索<input v-model="search" placeholder="搜索马来语或中文释义" aria-label="搜索关键词" /></label>
        <label>产品分类<select v-model="category" aria-label="产品分类筛选"><option value="">全部产品分类</option><option v-for="entry in categories" :key="entry.id" :value="entry.name">{{entry.name}}{{entry.enabled?'':'（停用）'}}</option></select></label>
        <label>标签<select v-model="tagFilter" aria-label="标签筛选"><option value="">全部标签</option><option v-for="entry in tags" :key="entry.id" :value="entry.name">{{titleTagLabel(entry.name)}}{{entry.enabled?'':'（停用）'}}</option></select></label>
        <label>状态<select v-model="status" aria-label="关键词状态"><option value="">全部状态</option><option value="enabled">启用</option><option value="disabled">停用</option></select></label>
        <div class="creative-resource-filter-actions"><button class="secondary" :disabled="taskListLoading">搜索</button></div>
      </form>
      <div class="title-scroll creative-resource-table-wrap"><table class="title-library-table"><thead><tr><th>编码</th><th>马来语词语</th><th>中文释义</th><th>产品分类</th><th>标签</th><th>原文频次</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="word in words" :key="word.id"><td>{{word.code}}</td><td>{{word.phrase}}<small v-if="word.is_borrowed">借词</small></td><td>{{word.translation}}</td><td>{{word.categories.join('、')}}</td><td>{{titleTagLabel(word.tag)}}<small v-if="categoryFields.includes(word.tag)">模板基础字段</small></td><td>{{word.title_frequency}}</td><td>{{labels[word.status]}}<small title="选词优先级，与启用状态独立">{{({preferred:'优先词',normal:'普通词',forbidden:'禁用词'} as Record<string,string>)[word.priority]}}</small></td><td><button class="ghost" @click="showEvidence(word)">来源</button><button v-if="admin" class="ghost" @click="edit(word)">编辑</button><button v-if="admin" class="ghost" :disabled="busy||taskListLoading" :aria-label="`${word.status==='enabled'?'停用':'启用'}关键词 ${word.code}`" @click="setKeywordStatus(word)">{{word.status==='enabled'?'停用':'启用'}}</button></td></tr></tbody></table></div>
      <p v-if="!words.length" class="empty">暂无关键词，请先导入并确认入库。</p><TitlePagination label="关键词" :page="page" :page-size="pageSize" :total="total" :disabled="taskListLoading" @page="changeWordPage" @page-size="changeWordPageSize" />
    </section>
    <section v-if="tab==='stats'" class="title-panel"><div class="title-stat-grid"><div v-for="(label,key) in {generated:'生成标题',adopted:'采纳标题',manual:'人工调整',high_similarity:'高相似标题',coverage_insufficient:'覆盖不足',attempts:'成文调用次数'}" :key="key"><strong>{{stats[key]||0}}</strong><span>{{label}}</span></div></div><p class="title-note">调用次数在请求前记录，可能包括失败请求，不等同于供应商账单。自然流效果需结合真实搜索曝光、点击和转化评估。</p></section>
    <section v-if="tab==='imports'||tab==='stats'" class="title-panel">
      <h3>{{tab==='imports'?'导入记录':'后台标题任务'}}</h3>
      <div class="title-task-table-wrap creative-resource-table-wrap" :aria-busy="taskListLoading">
        <table class="title-task-table title-library-table">
          <thead><tr><th scope="col">任务编号</th><th scope="col">{{tab==='imports'?'文件名称':'任务名称'}}</th><th scope="col">{{tab==='imports'?'导入内容':'任务类型'}}</th><th scope="col">状态</th><th scope="col">处理进度</th><th scope="col" title="已入库词数 / 本次提取的全部词源结果数">入库词数/提取词数</th><th scope="col">{{tab==='imports'?'上传时间':'创建时间'}}</th><th scope="col">备注</th><th scope="col">操作</th></tr></thead>
          <tbody>
            <tr v-for="task in tasks" :key="task.id">
              <td>#{{task.id}}</td><td><span class="title-task-filename" :title="task.filename">{{task.filename||'批量标题'}}</span></td>
              <td>{{task.kind==='import'?importKindLabel(task):'批量生成'}}</td>
              <td><span class="title-task-status" :class="`title-task-status-${task.state}`">{{labels[task.state]||task.state}}</span></td>
              <td>{{task.progress.completed||0}} / {{task.progress.total||0}}<small v-if="task.progress.failed">{{task.progress.failed}} 行失败</small></td>
              <td :title="task.kind==='import'?'已入库词数 / 本次提取的全部词源结果数':undefined">{{task.kind==='import'?`${task.result.imported_total??0} / ${task.result.word_total??'—'}`:'—'}}</td>
              <td class="title-task-time">{{task.created_at?new Date(task.created_at).toLocaleString():'—'}}</td>
              <td><span class="title-task-note-preview" :title="task.note">{{task.note||'—'}}</span></td>
              <td><button class="secondary" :aria-label="`查看任务 ${task.id} 详情`" @click="openTask(task.id)">查看详情</button></td>
            </tr>
            <tr v-if="!tasks.length"><td colspan="9" class="empty">{{taskListLoading?'正在加载…':'暂无记录。'}}</td></tr>
          </tbody>
        </table>
      </div>
      <TitlePagination :label="tab==='imports'?'导入记录':'后台标题任务'" :page="taskPage" :page-size="taskPageSize" :total="taskTotal" :disabled="taskListLoading" @page="changeTaskPage" @page-size="changeTaskPageSize" />
    </section>
    </div>
    <div v-if="taskDetailId!==null" class="modal-backdrop" @click.self="!busy&&closeTask()">
      <section v-dialog-focus="{close:closeTask,busy}" class="modal-card title-task-dialog" role="dialog" aria-modal="true" aria-labelledby="title-task-heading" :aria-busy="taskDetailLoading||busy">
        <div class="title-task-dialog-heading"><h2 id="title-task-heading">任务 #{{taskDetailId}} · 详情</h2><button class="secondary" aria-label="关闭任务详情" :disabled="busy" @click="closeTask">关闭</button></div>
        <div class="title-task-dialog-body">
        <p v-if="taskDetailLoading&&!activeTask" role="status">正在加载任务详情…</p>
        <p v-if="taskError" class="error" role="alert">{{taskError}}</p>
        <button v-if="taskError&&!activeTask" class="secondary" :disabled="taskDetailLoading" @click="openTask(taskDetailId)">重新加载</button>
        <section v-if="activeTask" class="title-task-detail">
          <div class="title-tools">
            <span class="title-task-status" :class="`title-task-status-${activeTask.state}`">{{labels[activeTask.state]||activeTask.state}}</span>
            <button v-if="admin&&activeTask.state==='preview'" class="secondary" :disabled="busy||taskDetailLoading||taskCategoryPending||!activeTask.category_resolution?.ready" @click="taskAction(activeTask.id,'start')">开始提词</button>
            <button v-if="['queued','running','preview'].includes(activeTask.state)" class="secondary" :disabled="busy||taskDetailLoading" @click="taskAction(activeTask.id,'cancel')">取消任务</button>
            <button v-if="(admin||activeTask.kind!=='import')&&(['failed','cancelled','completed_with_errors'].includes(activeTask.state)||Object.keys(activeTask.result.failed_rows||{}).length>0)" class="secondary" :disabled="busy||taskDetailLoading" @click="taskAction(activeTask.id,'retry')">重试失败项</button>
          </div>
          <dl class="title-task-metadata">
            <div><dt>{{activeTask.kind==='import'?'文件名称':'任务名称'}}</dt><dd>{{activeTask.filename||'批量标题'}}</dd></div>
            <div><dt>{{activeTask.kind==='import'?'导入内容':'任务类型'}}</dt><dd>{{activeTask.kind==='import'?importKindLabel(activeTask):'批量生成'}}</dd></div>
            <div><dt>{{activeTask.kind==='import'?'上传时间':'创建时间'}}</dt><dd>{{new Date(activeTask.created_at).toLocaleString()}}</dd></div>
            <div><dt>处理进度</dt><dd>{{activeTask.progress.completed||0}} / {{activeTask.progress.total||0}}<span v-if="activeTask.progress.failed"> · {{activeTask.progress.failed}} 行失败</span></dd></div>
          </dl>
          <p v-if="activeTask.note" class="title-note title-import-note">备注：{{activeTask.note}}</p>
          <TitleImportCategories v-if="activeTask.kind==='import'&&activeTask.category_resolution" :task-id="activeTask.id" :token="token" :resolution="activeTask.category_resolution" :editable="admin&&!['queued','running'].includes(activeTask.state)" :disabled="busy||taskDetailLoading" @changed="taskCategoriesChanged" @pending="taskCategoryPending=$event" @refresh="openTask(activeTask.id,false)" />
          <details v-if="activeTask.error||taskFailureCount" :key="activeTask.id" class="title-task-errors">
            <summary>错误信息<span v-if="taskFailureCount">（{{taskFailureCount}} 行失败）</span></summary>
            <div class="title-task-failures" role="region" aria-label="任务错误详情" tabindex="0">
              <p v-if="activeTask.error" class="error">{{activeTask.error}}</p>
              <p v-for="(message,row) in activeTask.result.failed_rows" :key="row" class="error">第 {{row}} 行：{{message}}</p>
            </div>
          </details>
          <template v-if="activeTask.result.words">
            <div class="title-tools title-review-filters">
              <label>品类<select v-model="reviewCategory" aria-label="提词结果品类筛选" :disabled="busy||taskDetailLoading" @change="changeReviewFilters"><option value="">全部品类</option><option v-for="value in activeTask.result.filter_categories" :key="value" :value="value">{{value}}</option></select></label>
              <label>分类<select v-model="reviewTag" aria-label="提词结果分类筛选" :disabled="busy||taskDetailLoading" @change="changeReviewFilters"><option value="">全部分类</option><option v-for="value in activeTask.result.filter_tags" :key="value" :value="value">{{titleTagLabel(value)}}</option></select></label>
              <label>是否已入库<select v-model="reviewImported" aria-label="提词结果入库状态筛选" :disabled="busy||taskDetailLoading" @change="changeReviewFilters"><option value="">全部</option><option value="true">已入库</option><option value="false">未入库</option></select></label>
            </div>
            <div class="title-tools"><span>提取 {{activeTask.result.word_total}} 个词源结果，已入库 {{activeTask.result.imported_total||0}} 项，已选 {{selected.length}} 项</span><button v-if="canConfirmImport" class="secondary" :disabled="busy||taskDetailLoading||!reviewPageIndexes.length" @click="selectPage">选择本页常规词</button><button v-if="selected.length" class="secondary" :disabled="busy" @click="selected=[]">清空选择</button></div>
            <div class="title-scroll title-task-review"><table><thead><tr><th scope="col"><label v-if="canConfirmImport" class="title-checkbox" title="选中或取消本页尚未入库的提词结果，保留其他页选择"><input type="checkbox" :checked="reviewPageSelection.all" :indeterminate="reviewPageSelection.some" :disabled="busy||taskDetailLoading||!reviewPageIndexes.length" aria-label="全选本页提词结果" @change="toggleReviewPage" /><span>全选本页</span></label><template v-else>选择</template></th><th>词语</th><th>中文释义</th><th>分类</th><th>品类</th><th>原文行 / 位置</th><th>原始标题</th><th>入库建议</th></tr></thead><tbody><tr v-for="word in activeTask.result.words" :key="word.index"><td><span v-if="word.imported" class="title-imported">已入库</span><input v-else-if="canConfirmImport" v-model="selected" type="checkbox" :value="word.index" :disabled="busy||taskDetailLoading" :aria-label="`选择 ${word.phrase}`" /></td><td>{{word.phrase}} {{word.is_borrowed?'（借词）':''}}</td><td>{{word.translation}}</td><td>{{titleTagLabel(word.tag)}}</td><td>{{word.categories.join('、')}}<small v-if="word.original_categories?.join('、')!==word.categories.join('、')">原分类：{{word.original_categories?.join('、')}}</small></td><td>{{word.row}} / {{word.position}}</td><td class="title-original">{{word.original_title}}</td><td>{{word.existing_code?`合并到 ${word.existing_code}`:'新增词'}}</td></tr><tr v-if="!activeTask.result.words.length"><td colspan="8" class="empty">当前筛选条件下暂无词语。</td></tr></tbody></table></div>
            <TitlePagination label="提词结果" :page="Math.floor(reviewOffset/reviewPageSize)+1" :page-size="reviewPageSize" :total="reviewTotal" :disabled="busy||taskDetailLoading" @page="changeReviewPage" @page-size="changeReviewPageSize" />
          </template>
          <div v-if="activeTask.result.items" class="title-task-results"><article v-for="item in activeTask.result.items" :key="item.key"><strong>商品组 {{item.key}}</strong><p>{{item.title||item.error}}</p><small>{{item.warnings?.join('；')}}</small></article></div>
        </section>
        </div>
        <footer v-if="canConfirmImport" class="title-task-dialog-footer">
          <div><p v-if="notice" class="title-import-success" role="status">{{notice}}</p><p class="title-note">入库即视为审核通过并启用，可分多次入库；后续可在关键词列表停用。</p></div>
          <button class="primary" :disabled="busy||taskDetailLoading||taskCategoryPending||!activeTask.category_resolution?.ready||!selected.length" @click="confirmImport">确认选中结果入库并启用<span v-if="selected.length">（{{selected.length}}）</span></button>
        </footer>
      </section>
    </div>
    <div v-if="showImport" class="modal-backdrop" @click.self="!busy&&(showImport=false)"><section v-dialog-focus="{close:()=>{if(!busy)showImport=false},busy}" class="modal-card title-edit-dialog title-import-dialog" role="dialog" aria-modal="true" aria-labelledby="title-import-heading">
      <header class="title-import-dialog-heading"><div><h2 id="title-import-heading">上传并预览</h2><p>{{preview ? (file?.name || '导入文件')+' · '+preview.rows.toLocaleString()+' 行数据' : '导入商品标题或关键词，补充你的标题词库。'}}</p></div><button type="button" class="title-import-close" :disabled="busy" aria-label="关闭导入弹窗" @click="showImport=false"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg></button></header>
      <div ref="importDialogBody" class="title-import-dialog-body">
      <form v-if="!preview" class="title-form" @submit.prevent="upload">
        <label>导入内容<select v-model="kind" aria-describedby="title-import-columns" @change="error='' "><option value="titles">商品标题</option><option value="keywords">已整理关键词</option></select></label>
        <div id="title-import-columns" class="title-import-columns" aria-live="polite">
          <strong>{{kind==='titles'?'商品标题':'已整理关键词'}}必填列</strong>
          <template v-if="kind==='titles'"><p>商品标题、商品分类。</p><p><b>选填列：</b>商品ID、链接。</p><p>商品标题使用马来语原文；商品分类建议与产品分类名称一致。</p></template>
          <template v-else><p>马来语词语、中文释义、产品分类、标签。</p><p><b>选填列：</b>商品ID、链接。</p><p>每行只填写一个标签，可填写品类、性别、年龄或已启用的标签名称。同一词需要多个标签时，请拆分为多行填写。</p></template>
        </div>
        <label>CSV / XLSX 文件<input type="file" accept=".csv,.xlsx" required aria-describedby="title-import-columns" @change="file=($event.target as HTMLInputElement).files?.[0]||null" /></label>
        <label>备注（选填）<textarea v-model="note" rows="3" maxlength="500" aria-label="备注" placeholder="例如：马来站女装标题整理，用于补充长袖相关词语" /></label>
        <p class="title-note">支持 UTF-8 CSV 或 XLSX 文件，最多 10,000 行、20MB。备注仅用于记录本次导入说明。</p>
        <div class="title-dialog-actions"><button type="button" :disabled="busy" @click="showImport=false">取消</button><button class="primary" :disabled="busy||!file">{{busy?'上传中…':'上传并预览'}}</button></div>
      </form>
      <section v-else class="title-form title-import-preview-content">
        <TitleImportCategories :task-id="preview.id" :token="token" :resolution="preview.category_resolution" :editable="preview.state==='preview'" :disabled="busy" @changed="preview.category_resolution=$event" @pending="previewCategoryPending=$event" @refresh="refreshPreviewCategories" />
        <section class="title-import-file-preview" aria-label="文件内容预览">
          <header class="title-import-file-heading"><h3><svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.3" /><path d="M3 8h14M8 8v9" stroke="currentColor" stroke-width="1.3" /></svg>文件预览</h3><span>展示 {{preview.preview.length}} / {{preview.rows.toLocaleString()}} 行</span></header>
          <div class="title-scroll title-import-file-scroll"><table class="title-import-preview" :class="{'title-import-preview-titles':preview.kind==='titles'}"><thead><tr><th scope="col">行号</th><th v-for="column in previewColumns" :key="column.key" scope="col">{{column.label}}</th></tr></thead><tbody><tr v-for="row in preview.preview" :key="row.row"><td>{{row.row}}</td><td v-for="column in previewColumns" :key="column.key">{{row.values[column.key]??row.values[column.label]??'—'}}</td></tr></tbody></table></div>
        </section>
        <p v-if="preview.note" class="title-note title-import-note">备注：{{preview.note}}</p>
        <p v-if="preview.duplicate" class="title-note">该文件已上传，将复用已有导入记录。</p>
      </section>
      <p v-if="error" class="error" role="alert">{{error}}</p>
      </div>
      <footer v-if="preview" class="title-import-dialog-footer"><div class="title-import-footer-info"><button type="button" class="title-import-reselect" :disabled="busy" @click="preview=null;file=null;previewCategoryPending=false">重新选择文件</button><span v-if="preview.state==='preview'&&(!preview.category_resolution?.ready||previewCategoryPending)">请先确认上方分类</span></div><div class="title-dialog-actions"><button class="secondary" :disabled="busy" @click="showImport=false">关闭</button><button v-if="preview.state==='preview'" class="primary" :disabled="busy||previewCategoryPending||!preview.category_resolution?.ready" @click="startImport">确认预览，开始提词</button><button v-else class="primary" :disabled="busy" @click="viewExistingImport">查看已有任务</button></div></footer>
    </section></div>
    <div v-if="editing" class="modal-backdrop" @click.self="!busy&&(editing=null)"><section v-dialog-focus="{close:()=>{if(!busy)editing=null},busy}" class="modal-card title-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="title-word-edit"><h2 id="title-word-edit">编辑 {{editing.code}}</h2><form class="title-form" @submit.prevent="saveWord"><label>马来语词语<input v-model="editing.phrase" required maxlength="160" /></label><label>中文释义<input v-model="editing.translation" required maxlength="255" /></label><label>属性归属<select v-model="editing.tag"><optgroup label="模板基础字段"><option v-for="field in categoryFields" :key="field" :value="field">{{field}}</option></optgroup><optgroup v-if="editing.tag==='面料'" label="历史标签"><option value="面料">面料</option></optgroup><optgroup label="标签（属性分类）"><option v-for="entry in editableTags" :key="entry.id" :value="entry.name" :disabled="!entry.enabled&&editing.tag!==entry.name">{{titleTagLabel(entry.name)}}{{entry.enabled?'':'（停用）'}}</option></optgroup></select></label><fieldset class="title-category-options"><legend>适用产品分类（至少选择一项）</legend><label v-for="entry in categories" :key="entry.id" class="title-checkbox"><input v-model="editing.categories" type="checkbox" :value="entry.name" :disabled="!entry.enabled&&!editing.categories.includes(entry.name)" />{{entry.name}}{{entry.enabled?'':'（停用）'}}</label></fieldset><label>同义表达（逗号分隔）<input v-model="editSynonyms" /></label><label>冲突词 ID（逗号分隔）<input v-model="editConflicts" /></label><div class="title-tools"><span class="title-note">启用状态：{{labels[editing.status]}}</span><select v-model="editing.priority" aria-label="优先级"><option value="normal">普通词</option><option value="preferred">优先词</option><option value="forbidden">禁用词</option></select><label class="title-checkbox"><input v-model="editing.is_borrowed" type="checkbox" />借词</label></div><div class="title-tools"><button type="button" :disabled="busy" @click="editing=null">取消</button><button class="primary" :disabled="busy">保存</button></div></form><details><summary>合并重复词</summary><p>仅合并相同含义的词；不同含义的词请保留。原编码和来源会留档。</p><input v-model="mergeTarget" placeholder="合并到目标关键词 ID" /><button :disabled="busy" @click="mergeWord">确认合并到目标词</button></details><p v-if="error" class="error">{{error}}</p></section></div>
    <div v-if="evidence" class="modal-backdrop" @click.self="evidence=null"><section v-dialog-focus="{close:()=>{evidence=null}}" class="modal-card title-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="title-evidence"><h2 id="title-evidence">{{evidence.phrase}} · 词源证据</h2><TitleKeywordEvidence :token="token" :keyword-id="evidence.id" /><div class="title-dialog-actions"><button @click="evidence=null">关闭</button></div></section></div>
  </section>
</template>

<style scoped>
.title-library-heading{height:auto;padding:0;border:0;background:transparent}
.title-category-options{display:flex;flex-wrap:wrap;gap:12px;border:1px solid #e2dcf0;border-radius:9px;padding:12px}.title-category-options legend{font-size:13px;color:#756e82}.title-library .material-usage-tabs{margin:0;gap:8px;overflow-x:auto;min-width:0;padding-bottom:2px}.title-library .material-usage-tabs button{font-size:14px;line-height:1.4;white-space:nowrap;flex:none}.title-tab-content{display:grid;gap:18px;min-width:0}.title-dialog-actions{display:flex;justify-content:flex-end;gap:12px}
.title-edit-dialog input:not([type=checkbox]),.title-edit-dialog select,.title-edit-dialog textarea{box-sizing:border-box;border:1px solid #e2dcf0;border-radius:9px;padding:11px 12px;font:inherit;min-width:0;background:white;color:#302844}.title-tools>select{width:auto;min-width:130px}.title-library input:focus,.title-library select:focus,.title-library textarea:focus{outline:2px solid #c9b9ff;outline-offset:1px}.title-library input[type=checkbox]{width:16px;height:16px;accent-color:#6744d5}.title-tools>button{flex-shrink:0}.title-edit-dialog label input,.title-edit-dialog label select{width:100%}
.title-library{display:grid;gap:18px}.title-library-heading,.title-tools{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.title-library-heading{justify-content:space-between}.title-library h2,.title-library h3{margin:0}.title-library-heading p,.title-note{margin:0;font-size:13px;line-height:1.7;color:#756e82}.title-panel{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;min-width:0}.title-form{display:grid;gap:14px}.title-form label,.title-panel>details>label{display:grid;gap:6px}.title-form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.title-original{min-width:200px;max-width:340px;overflow-wrap:anywhere}.title-scroll{overflow:auto;max-height:520px}table{width:100%;border-collapse:collapse;font-size:13px;text-align:left}th{background:#f6f4fa;white-space:nowrap;position:sticky;top:0}th,td{padding:12px;border-bottom:1px solid #ede9f2;vertical-align:middle}td small{display:block;color:#81788d;margin-top:5px}.title-checkbox{display:flex!important;align-items:center;gap:6px}.title-checkbox input{width:auto}.title-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:16px}.title-stat-grid div{padding:20px;background:#fff;border:1px solid #e7e3f2;border-radius:12px;display:grid;gap:8px}.title-stat-grid strong{font-size:28px;color:#6544ce}.title-edit-dialog{width:min(760px,95vw);max-height:88vh;overflow:auto;display:grid;gap:20px}.title-evidence,.title-task-results article{border-bottom:1px solid #eee;padding:10px 0;overflow-wrap:anywhere}.title-evidence p{line-height:1.6}.title-evidence small{color:#81788d}.title-library details summary{cursor:pointer;font-weight:600;margin-bottom:12px}@media(max-width:700px){.title-dialog-actions{flex-wrap:wrap}}

.title-import-columns{padding:12px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;font-size:13px;line-height:1.7;color:#64748b}.title-import-columns strong{color:#334155}.title-import-columns p{margin:6px 0 0}.title-import-columns b{font-weight:600}.title-import-note{white-space:pre-wrap;overflow-wrap:anywhere}
.title-import-preview{table-layout:fixed;min-width:600px}.title-import-preview th:first-child{width:48px}.title-import-preview td{overflow-wrap:anywhere}.title-import-preview-titles{min-width:440px}.title-import-preview-titles th:last-child{width:120px}
.title-import-dialog{box-sizing:border-box;width:min(920px,calc(100vw - 32px));max-height:min(90vh,calc(100dvh - 32px));padding:0;display:flex;flex-direction:column;gap:0;overflow:hidden;border-radius:16px}
.title-import-dialog-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-shrink:0;padding:23px 24px 19px;border-bottom:1px solid #efebf4}.title-import-dialog-heading>div{min-width:0}.title-import-dialog .title-import-dialog-heading h2{margin:0;font-size:19px;font-weight:650;line-height:1.5}.title-import-dialog .title-import-dialog-heading p{margin:5px 0 0;font-size:12px;color:#a095ad;line-height:1.6;overflow-wrap:anywhere}.title-import-close{display:grid;place-items:center;flex-shrink:0;width:30px;height:30px;padding:0;border:0;border-radius:7px;background:#f7f5fa;color:#aaa0b4}.title-import-close:hover{background:#efebf6;color:#6d5c83}
.title-import-dialog-body{min-height:0;overflow:auto;overscroll-behavior:contain;padding:20px 24px 24px}.title-import-preview-content{gap:20px}.title-import-file-preview{min-width:0;border:1px solid #eae6f0;border-radius:12px;overflow:hidden}.title-import-file-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px}.title-import-dialog .title-import-file-heading h3{display:flex;align-items:center;gap:7px;margin:0;font-size:14px;font-weight:600;line-height:1.5}.title-import-file-heading svg{color:#a99cb9}.title-import-file-heading>span{font-size:11px;white-space:nowrap;color:#a69caf}.title-import-file-scroll{max-height:280px;border-top:1px solid #f0edf5}.title-import-dialog .title-import-preview{font-size:12px}.title-import-dialog .title-import-preview th{padding:10px 14px;background:#faf9fc;color:#9b91a6;font-size:11px;font-weight:500}.title-import-dialog .title-import-preview td{padding:12px 14px;border-color:#f0edf5;line-height:1.7;color:#60556f}.title-import-dialog .title-import-preview td:first-child{color:#aca2b6;font-variant-numeric:tabular-nums}.title-import-dialog .title-import-preview tr:last-child td{border-bottom:0}
.title-import-dialog-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0;padding:16px 24px;border-top:1px solid #efebf4;background:#fff}.title-import-footer-info{display:grid;gap:4px}.title-import-reselect{padding:3px 0;background:transparent;text-align:left;color:#998ca9;font-size:12px;font-weight:400}.title-import-reselect:hover{color:#7455d8}.title-import-footer-info>span{font-size:10px;color:#b5aabd}.title-import-dialog-footer .title-dialog-actions{gap:8px;flex-shrink:0}.title-import-dialog-footer .title-dialog-actions>button{padding:10px 15px;border-radius:8px;font-size:12px;font-weight:500}.title-import-dialog-footer .title-dialog-actions>.secondary{border:1px solid #e8e2f0;background:#fff;color:#9486a4}.title-import-dialog-footer .title-dialog-actions>.primary:disabled{opacity:1;background:#e4dcf4;color:#fff;box-shadow:none;cursor:not-allowed}
.title-import-dialog-heading,.title-import-file-heading{height:auto;min-height:0}.title-import-file-heading{border:0;background:#fff}
@media(max-width:600px){.title-import-dialog{width:calc(100vw - 24px);max-height:calc(100dvh - 24px);border-radius:13px}.title-import-dialog-heading{padding:17px 16px 14px}.title-import-dialog .title-import-dialog-heading h2{font-size:17px}.title-import-dialog-body{padding:16px}.title-import-dialog-footer{padding:12px 16px;gap:10px;align-items:center}.title-import-footer-info>span{display:none}.title-import-dialog-footer .title-dialog-actions{flex-wrap:nowrap;gap:6px}.title-import-dialog-footer .title-dialog-actions>button{padding:10px;font-size:11px}.title-import-file-heading{padding:12px 14px}.title-import-file-scroll{max-height:230px}}
.title-task-table-wrap{overflow:auto;min-width:0}.title-task-table{min-width:1120px}.title-task-table th,.title-task-table td{padding:14px 12px}.title-task-table button{white-space:nowrap}.title-task-filename{display:block;min-width:160px;max-width:220px;overflow-wrap:anywhere}.title-task-time{white-space:nowrap}.title-task-note-preview{display:-webkit-box;max-width:200px;min-width:120px;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere}.title-task-pagination{padding:0;flex-wrap:wrap}.title-library .title-task-pagination select{width:auto;padding:6px 26px 6px 9px;min-width:76px}
.title-task-status{display:inline-flex;align-items:center;white-space:nowrap;padding:5px 9px;border-radius:7px;font-size:12px;font-weight:600;color:#6c6480;background:#f0edf5}.title-task-status-preview{color:#6946c7;background:#f0eaff}.title-task-status-queued,.title-task-status-running{color:#3168af;background:#eaf2ff}.title-task-status-review,.title-task-status-completed_with_errors{color:#9b650e;background:#fff4da}.title-task-status-completed{color:#247a55;background:#e8f7ef}.title-task-status-failed{color:#bc3f50;background:#ffedf0}
.title-task-dialog{width:min(1280px,95vw);max-height:88vh;overflow:hidden;display:flex;flex-direction:column;gap:20px}.title-task-dialog-heading,.title-task-dialog-footer{flex-shrink:0}.title-task-dialog-body{overflow:auto;min-height:0;min-width:0;overscroll-behavior:contain}.title-task-dialog-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:18px;border-top:1px solid #ede9f2;background:#fff}.title-task-dialog-footer>button{flex-shrink:0}.title-task-dialog-footer p{margin:0}.title-task-dialog-footer .title-import-success{color:#247a55;margin-bottom:4px}.title-task-dialog .title-review-filters>label{display:grid;gap:6px;margin:0;min-width:160px}.title-task-dialog .title-review-filters select{width:100%;margin:0;padding:9px 12px}.title-task-dialog .title-task-review .title-checkbox{margin:0;line-height:1.5;white-space:nowrap}.title-task-dialog .title-task-review input[type=checkbox]{margin:0;flex-shrink:0}.title-imported{color:#247a55;white-space:nowrap;font-size:12px}@media(max-width:700px){.title-task-dialog-footer{flex-wrap:wrap}.title-task-dialog-footer>button{width:100%}.title-task-dialog .title-review-filters>label{flex:1;min-width:120px}}.title-task-dialog-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.title-task-dialog-heading>button{flex-shrink:0}.title-task-detail{display:grid;gap:18px;min-width:0}.title-task-detail>p{margin:0}.title-task-metadata{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0;padding:16px;background:#f8f6fc;border-radius:10px}.title-task-metadata dt{font-size:12px;color:#81788d}.title-task-metadata dd{margin:6px 0 0;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.title-task-review{max-height:45vh}.title-task-review table{min-width:1000px}
.title-task-errors{border:1px solid #f1dce2;border-radius:9px;min-width:0}.title-library .title-task-errors>summary{padding:12px 14px;margin:0;color:#bc3f50;font-size:13px}.title-task-errors>summary:focus-visible,.title-task-failures:focus-visible{outline:2px solid #c9b9ff;outline-offset:2px}.title-task-failures{box-sizing:border-box;display:grid;gap:12px;max-height:180px;overflow:auto;padding:0 14px 14px;font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;overscroll-behavior:contain}.title-task-failures .error{margin:0}@media(max-width:700px){.title-task-metadata{grid-template-columns:repeat(2,minmax(0,1fr))}.title-task-dialog-heading h2{font-size:20px}.title-task-pagination{justify-content:flex-start;gap:10px}}
</style>
