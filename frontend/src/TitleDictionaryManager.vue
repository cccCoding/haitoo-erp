<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import TitlePagination from './TitlePagination.vue'
import { titleTagLabel } from './title-labels'
import { dialogFocus as vDialogFocus } from './dialog-focus'
import SearchableSelect from './SearchableSelect.vue'
import { parseCategoryAliases } from './title-categories'

type Entry = { id: number; name: string; aliases?: string[]; merged_into_id?: number | null; description: string; localized_name: string | null; applicable_keyword_count?: number; semantic_tag: string | null; built_in: boolean; enabled: boolean; keyword_count: number; template_count: number; import_count: number; reference_count: number }
const props = defineProps<{ token: string; kind: 'category' | 'tag'; entries: Entry[]; semanticTags: string[]; admin: boolean }>()
const emit = defineEmits<{ changed: []; keywords: [category: string] }>()
const api = axios.create({baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000'})
const label = computed(()=>props.kind==='category'?'产品分类':'标签')
const search = ref(''), state = ref(''), error = ref(''), busy = ref(false), editing = ref<any>(null)
const rows = computed(()=>props.entries.filter(row=>!row.merged_into_id&&(!state.value||String(row.enabled)===state.value) && `${props.kind==='tag'?titleTagLabel(row.name):row.name} ${row.aliases?.join(' ')||''} ${row.localized_name||''} ${row.description}`.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
const aliasText = ref(''), selectedSources = ref<number[]>([]), mergeDialog = ref(false), mergeTarget = ref<number | null>(null), mergeSummary = ref<any>(null), mergeNotice = ref('')
const mergeOptions = computed(()=>props.entries.filter(row=>row.enabled&&!row.merged_into_id&&!selectedSources.value.includes(row.id)).map(row=>({value:row.id,label:row.name})))
watch(mergeTarget,()=>{mergeSummary.value=null;error.value=''})
watch(()=>props.kind,()=>{selectedSources.value=[];mergeDialog.value=false;mergeNotice.value=''})
watch(()=>props.entries,()=>{selectedSources.value=selectedSources.value.filter(id=>props.entries.some(row=>row.id===id&&!row.merged_into_id))})
const formName = computed({get:()=>props.kind==='tag'?titleTagLabel(editing.value?.name):editing.value?.name||'',set:value=>{if(editing.value)editing.value.name=value}})
const page=ref(1),pageSize=ref(20)
const pagedRows=computed(()=>rows.value.slice((page.value-1)*pageSize.value,page.value*pageSize.value))
function changePageSize(value:number){pageSize.value=value;page.value=1}
watch([search,state],()=>{page.value=1})
watch(()=>rows.value.length,()=>{page.value=Math.min(page.value,Math.max(1,Math.ceil(rows.value.length/pageSize.value)))})
const fixedIdentity = computed(()=>!!editing.value && !!(editing.value.built_in || editing.value.reference_count))
function edit(row?: Entry) {error.value='';aliasText.value=(row?.aliases||[]).join('\n');editing.value=row?{...row,localized_name:row.localized_name||''}:{name:'',description:'',localized_name:'',semantic_tag:'待分类',enabled:true}}
function openMerge(){error.value='';mergeTarget.value=null;mergeSummary.value=null;mergeDialog.value=true}
async function previewMerge(){
  if(busy.value||!mergeTarget.value)return
  busy.value=true;error.value=''
  try{const {data}=await api.post('/title-category-merges/preview',{source_ids:selectedSources.value,target_id:mergeTarget.value},{headers:{Authorization:`Bearer ${props.token}`}});mergeSummary.value=data}
  catch(e:any){failure(e)}finally{busy.value=false}
}
async function executeMerge(){
  if(busy.value||!mergeSummary.value)return
  busy.value=true;error.value=''
  try{await api.post('/title-category-merges',{source_ids:selectedSources.value,target_id:mergeTarget.value,token:mergeSummary.value.token},{headers:{Authorization:`Bearer ${props.token}`}});mergeNotice.value=`已将 ${selectedSources.value.length} 个分类合并到“${mergeSummary.value.target.name}”，旧名称保留为别名。`;mergeDialog.value=false;selectedSources.value=[];emit('changed')}
  catch(e:any){mergeSummary.value=null;failure(e)}finally{busy.value=false}
}
function failure(e:any){error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:e.message||'操作失败'}
async function save() {
  if(busy.value)return
  busy.value=true;error.value=''
  try{
    const form=editing.value
    const payload:any={name:form.name.trim(),description:form.description.trim(),enabled:form.enabled}
    if(!payload.name)throw new Error(`请输入${label.value}名称`)
    if(props.kind==='category'){
      payload.localized_name=form.localized_name.trim()
      payload.aliases=parseCategoryAliases(aliasText.value)
    }else payload.semantic_tag=form.semantic_tag
    const config={headers:{Authorization:`Bearer ${props.token}`}}
    if(form.id)await api.patch(`/title-dictionaries/${form.id}`,payload,config)
    else await api.post(`/title-dictionaries/${props.kind}`,payload,config)
    editing.value=null;emit('changed')
  }catch(e:any){failure(e)}finally{busy.value=false}
}
async function toggle(row:Entry){
  if(busy.value)return
  busy.value=true;error.value=''
  try{await api.patch(`/title-dictionaries/${row.id}`,{enabled:!row.enabled},{headers:{Authorization:`Bearer ${props.token}`}});emit('changed')}
  catch(e:any){failure(e)}finally{busy.value=false}
}
async function remove(row:Entry){
  if(busy.value||!confirm(`确定删除${label.value}“${row.name}”？`))return
  busy.value=true;error.value=''
  try{await api.delete(`/title-dictionaries/${row.id}`,{headers:{Authorization:`Bearer ${props.token}`}});emit('changed')}
  catch(e:any){failure(e)}finally{busy.value=false}
}
</script>

<template>
  <section class="dictionary-panel">
    <p class="dictionary-note">{{kind==='category'?'管理商品分类及站点名称，与平台类目映射分开。使用性别、年龄、面料和其他商品标签统一在模板配置中设置。':'标签对应关键词的属性分类。内置标签保留固定语义；新增标签需关联语义分类，确保选词仍依据真实商品属性。'}} 停用后停止后续使用，已提交任务保留原快照。</p>
    <div class="creative-resource-filters title-library-filters">
      <label class="title-library-search">搜索<input v-model="search" :aria-label="`搜索${label}`" :placeholder="`搜索${label}名称或说明`" /></label>
      <label>状态<select v-model="state" :aria-label="`${label}状态`"><option value="">全部状态</option><option value="true">启用</option><option value="false">停用</option></select></label>
      <div v-if="admin" class="creative-resource-filter-actions"><button class="primary" :disabled="busy" @click="edit()">新增{{label}}</button><button v-if="kind==='category'" class="secondary" :disabled="busy||!selectedSources.length" @click="openMerge">合并选中分类<span v-if="selectedSources.length">（{{selectedSources.length}}）</span></button><button v-if="selectedSources.length" class="ghost" :disabled="busy" @click="selectedSources=[]">清空选择</button></div>
      <span class="title-library-filter-total">共 {{rows.length}} 项</span>
    </div>
    <p v-if="error&&!editing&&!mergeDialog" class="error" role="alert">{{error}}</p>
    <p v-if="mergeNotice" class="dictionary-note" role="status">{{mergeNotice}}</p>
    <div class="dictionary-scroll creative-resource-table-wrap"><table class="title-library-table"><thead><tr><th v-if="admin&&kind==='category'">选择</th><th>{{label}}名称</th><th v-if="kind==='category'">马来语名称</th><th v-if="kind==='tag'">语义分类</th><th>说明</th><th :title="kind==='category'?'将本分类列为适用品类的关键词数量，包含待审核、启用及停用词；不重复统计已合并词。点击查看对应关键词。':'使用本标签的关键词数量。'">关键词引用</th><th>模板引用</th><th>导入引用</th><th>状态</th><th v-if="admin">操作</th></tr></thead><tbody><tr v-for="row in pagedRows" :key="row.id"><td v-if="admin&&kind==='category'"><input v-model="selectedSources" type="checkbox" :value="row.id" :disabled="busy" :aria-label="`选择合并分类 ${row.name}`" /></td><td>{{kind==='tag'?titleTagLabel(row.name):row.name}}<small v-if="row.built_in">内置标签</small><small v-if="row.aliases?.length">别名：{{row.aliases.join('、')}}</small></td><td v-if="kind==='category'"><span :class="{'dictionary-unset':!row.localized_name}">{{row.localized_name||'待设置'}}</span></td><td v-if="kind==='tag'">{{titleTagLabel(row.semantic_tag)}}</td><td class="dictionary-description">{{row.description||'—'}}</td><td><button v-if="kind==='category'" class="dictionary-count" :disabled="!(row.applicable_keyword_count??row.keyword_count)" :aria-label="`查看${row.name}适用关键词`" @click="emit('keywords',row.name)">{{row.applicable_keyword_count??row.keyword_count}}</button><template v-else>{{row.keyword_count}}</template></td><td>{{row.template_count}}</td><td>{{row.import_count}}</td><td><span class="dictionary-state" :class="row.enabled?'enabled':'disabled'">{{row.enabled?'启用':'停用'}}</span></td><td v-if="admin"><div class="dictionary-actions"><button class="ghost" :disabled="busy" @click="edit(row)">编辑</button><button class="ghost" :disabled="busy" @click="toggle(row)">{{row.enabled?'停用':'启用'}}</button><button v-if="!row.built_in&&!row.reference_count" class="danger" :disabled="busy" @click="remove(row)">删除</button></div></td></tr></tbody></table></div>
    <p v-if="!rows.length" class="dictionary-note">暂无符合条件的{{label}}。</p>
    <TitlePagination :label="label" :page="page" :page-size="pageSize" :total="rows.length" :disabled="busy" @page="page=$event" @page-size="changePageSize" />
    <p class="dictionary-note">{{kind==='category'?'已引用的分类名称不可修改；仍可编辑站点名称、说明或启停。仅未引用的分类可删除。':'已引用的名称和语义分类不可修改；可编辑说明或启停。仅未引用的自定义条目可删除。'}}</p>
    <div v-if="mergeDialog" class="modal-backdrop" @click.self="!busy&&(mergeDialog=false)"><section v-dialog-focus="{close:()=>{if(!busy)mergeDialog=false},busy}" class="modal-card dictionary-dialog" role="dialog" aria-modal="true" aria-labelledby="category-merge-heading"><h2 id="category-merge-heading">合并产品分类</h2><p class="dictionary-note">仅合并业务含义相同的分类。选中了 {{selectedSources.length}} 个源分类，目标分类必须已启用。合并不提供自动撤销。</p><SearchableSelect :model-value="mergeTarget" :options="mergeOptions" :disabled="busy" aria-label="合并目标分类" placeholder="选择保留的目标分类" @update:model-value="mergeTarget=typeof $event==='number'?$event:null" /><template v-if="mergeSummary"><div class="merge-preview"><h3>源分类</h3><article v-for="source in mergeSummary.sources" :key="source.id"><strong>{{source.name}}</strong><p>别名：{{source.aliases.join('、')||'无'}}；马来语名称：{{source.localized_name||'未设置'}}</p><p>说明：{{source.description||'无'}}</p></article><h3>保留的目标分类：{{mergeSummary.target.name}}</h3><p>别名：{{mergeSummary.target.aliases.join('、')||'无'}}；马来语名称：{{mergeSummary.target.localized_name||'未设置'}}</p><p>说明：{{mergeSummary.target.description||'无'}}</p><p>影响 {{mergeSummary.counts.keywords}} 个关键词、{{mergeSummary.counts.templates}} 个模板、{{mergeSummary.counts.imports}} 个待处理导入。</p><p>{{mergeSummary.notice}}</p></div></template><p v-if="error" class="error" role="alert">{{error}}</p><div class="dictionary-dialog-actions"><button :disabled="busy" @click="mergeDialog=false">取消</button><button v-if="!mergeSummary" class="primary" :disabled="busy||!mergeTarget" @click="previewMerge">预览合并影响</button><button v-else class="primary" :disabled="busy" @click="executeMerge">确认合并到“{{mergeSummary.target.name}}”</button></div></section></div>
    <div v-if="editing" class="modal-backdrop" @click.self="!busy&&(editing=null)"><section v-dialog-focus="{close:()=>{if(!busy)editing=null},busy}" class="modal-card dictionary-dialog" role="dialog" aria-modal="true" aria-labelledby="dictionary-editor-heading"><h2 id="dictionary-editor-heading">{{editing.id?'编辑':'新增'}}{{label}}</h2><form @submit.prevent="save"><label>{{label}}名称<input v-model="formName" required :maxlength="kind==='tag'?40:255" :readonly="fixedIdentity" /></label><label v-if="kind==='category'">马来西亚名称（马来语）<input v-model="editing.localized_name" maxlength="255" placeholder="例如：上衣填写 Baju" /><small>用于马来西亚站点的分类展示和词库标题品类表达；运营名称及已有引用保持不变。</small></label><label v-if="kind==='tag'">语义分类<select v-model="editing.semantic_tag" required :disabled="fixedIdentity"><option v-for="tag in semanticTags" :key="tag" :value="tag">{{titleTagLabel(tag)}}</option></select><small>用于匹配商品确认属性；品牌、营销等语义不会进入自动选词池。</small></label><label v-if="kind==='category'">分类别名<textarea v-model="aliasText" rows="4" placeholder="每行一个，例如：连身裙" /><small>用于导入识别与搜索，不会自动成为标题用词。合并保留的原分类名称不可移除。</small></label><label>说明<textarea v-model="editing.description" rows="3" maxlength="500" /></label><label class="dictionary-checkbox"><input v-model="editing.enabled" type="checkbox" />启用</label><p v-if="fixedIdentity" class="dictionary-note">{{kind==='category'?'该分类已被引用，名称已锁定；站点名称和说明仍可编辑。':'该条目为内置或已被引用，名称和语义分类已锁定。'}}</p><p v-if="error" class="error" role="alert">{{error}}</p><div class="dictionary-dialog-actions"><button type="button" :disabled="busy" @click="editing=null">取消</button><button class="primary" :disabled="busy">{{busy?'保存中…':'保存'}}</button></div></form></section></div>
  </section>
</template>

<style scoped>
.merge-preview{display:grid;gap:10px;font-size:13px;line-height:1.7}.merge-preview h3,.merge-preview p{margin:0}.merge-preview article{padding:10px;border:1px solid #e4deee;border-radius:8px}.dictionary-panel{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;min-width:0}.dictionary-heading,.dictionary-actions,.dictionary-dialog-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.dictionary-heading{justify-content:space-between}.dictionary-heading h3,.dictionary-dialog h2{margin:0}.dictionary-note,.dictionary-dialog small{margin:0;color:#756e82;font-size:13px;line-height:1.7}.dictionary-scroll{overflow:auto;max-height:560px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:12px;border-bottom:1px solid #ede9f2;vertical-align:middle}th{white-space:nowrap;background:#f6f4fa;position:sticky;top:0}td small{display:block;color:#81788d;margin-top:4px}.dictionary-description{max-width:260px;overflow-wrap:anywhere}.dictionary-count{padding:0;color:#6744d5;text-decoration:underline;text-underline-offset:3px}.dictionary-count:disabled{color:inherit;text-decoration:none;cursor:default}.dictionary-unset{color:#8b8497}.dictionary-state{display:inline-flex;padding:3px 8px;border-radius:999px;white-space:nowrap}.dictionary-state.enabled{background:#e7f6ee;color:#206b43}.dictionary-state.disabled{background:#ececf3;color:#686379}.dictionary-actions{flex-wrap:nowrap;gap:8px}.dictionary-actions button{white-space:nowrap}.dictionary-dialog{width:min(560px,calc(100vw - 24px));max-height:88vh;overflow:auto;display:grid;gap:20px}.dictionary-dialog form,.dictionary-dialog label{display:grid;gap:8px}.dictionary-dialog form{gap:16px}.dictionary-dialog-actions{justify-content:flex-end}.dictionary-checkbox{display:flex!important;gap:8px;align-items:center}.dictionary-checkbox input{width:auto!important}.dictionary-dialog input[readonly]{background:#f5f4f9;color:#81788d}.dictionary-dialog select:disabled{background:#f5f4f9}.dictionary-dialog input:not([type=checkbox]),.dictionary-dialog select,.dictionary-dialog textarea{box-sizing:border-box;min-width:0;border:1px solid #e2dcf0;border-radius:9px;padding:10px 12px;font:inherit;color:#302844}.dictionary-dialog label input:not([type=checkbox]),.dictionary-dialog label textarea,.dictionary-dialog label select{width:100%}@media(max-width:700px){.dictionary-heading{align-items:flex-start}}
</style>
