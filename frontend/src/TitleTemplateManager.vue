<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import TitleProfileEditor from './TitleProfileEditor.vue'
import TitlePagination from './TitlePagination.vue'
import { dialogFocus as vDialogFocus } from './dialog-focus'

type TemplateConfiguration = { id: number; name: string; cover_url: string | null; is_platform: boolean; category: string; category_localized_name: string | null; gender: string | null; age_group: string | null; material: string; attributes: Record<string,string>; configuration_issues: string[]; ready: boolean }
const props = defineProps<{ token: string; admin: boolean; categories: { name: string; enabled: boolean }[] }>()
const emit = defineEmits<{ changed: [] }>()
const api = axios.create({baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000'})
const rows = ref<TemplateConfiguration[]>([]), total = ref(0), page = ref(1), pageSize = ref(20)
const search = ref(''), category = ref(''), state = ref(''), loading = ref(false), error = ref('')
const editing = ref<TemplateConfiguration|null>(null), editingBusy = ref(false)
let revision = 0, loadedPage = 1, loadedPageSize = 20
async function load() {
  const current = ++revision
  loading.value = true; error.value = ''
  try {
    const {data} = await api.get('/title-template-configurations', {headers:{Authorization:`Bearer ${props.token}`},params:{q:search.value,category:category.value,state:state.value,page:page.value,page_size:pageSize.value}})
    if(current!==revision)return
    rows.value = data.items; total.value = data.total;page.value=data.page||1;loadedPage=page.value;loadedPageSize=pageSize.value
  } catch(e:any) { if(current===revision){page.value=loadedPage;pageSize.value=loadedPageSize;error.value = typeof e.response?.data?.detail==='string'?e.response.data.detail:'读取模板配置失败'} }
  finally { if(current===revision)loading.value=false }
}
function filter(){page.value=1;void load()}
function changePage(value:number){if(loading.value)return;page.value=value;void load()}
function changePageSize(value:number){if(loading.value)return;pageSize.value=value;page.value=1;void load()}
function close(){if(!editingBusy.value)editing.value=null}
function saved(){editing.value=null;editingBusy.value=false;void load();emit('changed')}
watch(()=>props.token,()=>{page.value=1;void load()})
onMounted(()=>void load())
onUnmounted(()=>{revision++})
</script>

<template>
  <section class="template-config-panel">
    <p class="template-config-note">为每个模板确认产品分类、使用性别、年龄、面料和商品标签。未确认的属性请留空。词库生成前须完成产品分类、性别和年龄设置。</p>
    <form class="creative-resource-filters title-library-filters" @submit.prevent="filter">
      <label class="title-library-search">搜索<input v-model="search" placeholder="搜索模板名称" aria-label="搜索模板名称" /></label>
      <label>产品分类<select v-model="category" aria-label="模板产品分类筛选" @change="filter"><option value="">全部产品分类</option><option v-for="item in categories" :key="item.name" :value="item.name">{{item.name}}{{item.enabled?'':'（停用）'}}</option></select></label>
      <label>配置状态<select v-model="state" aria-label="模板配置状态" @change="filter"><option value="">全部配置状态</option><option value="ready">已配置</option><option value="incomplete">待完善</option></select></label>
      <div class="creative-resource-filter-actions"><button class="secondary" :disabled="loading">搜索</button></div>
    </form>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <div class="template-config-scroll creative-resource-table-wrap" :aria-busy="loading"><table class="title-library-table"><thead><tr><th>产品模板</th><th>产品分类</th><th>使用性别</th><th>年龄</th><th>面料</th><th>其他标签</th><th>配置状态</th><th>操作</th></tr></thead><tbody>
      <tr v-for="row in rows" :key="row.id">
        <td><div class="template-config-product"><img v-if="row.cover_url" :src="row.cover_url" alt="" loading="lazy" /><span><strong>{{row.name}}</strong><small v-if="row.is_platform">平台模板 · 当前公司配置</small><small v-else>ID {{row.id}}</small></span></div></td>
        <td>{{row.category||'待设置'}}<small v-if="row.category_localized_name">{{row.category_localized_name}}</small></td>
        <td>{{row.gender||'待设置'}}</td><td>{{row.age_group||'待设置'}}</td><td class="template-config-material">{{row.material||'未确认'}}</td>
        <td><div class="template-config-tags"><span v-for="(value,tag) in row.attributes" :key="tag">{{tag}}：{{value}}</span><small v-if="!Object.keys(row.attributes).length">—</small></div></td>
        <td><span class="template-config-state" :class="row.ready?'ready':'incomplete'">{{row.ready?'已配置':'待完善'}}</span><small v-if="row.configuration_issues.length" class="template-config-issues">{{row.configuration_issues.join('；')}}</small></td>
        <td><button class="ghost" :aria-label="`${admin?'配置':'查看'}模板 ${row.name}`" @click="editing=row;editingBusy=false">{{admin?'配置':'查看'}}</button></td>
      </tr>
    </tbody></table></div>
    <p v-if="!rows.length&&!loading" class="template-config-note">暂无符合条件的模板。</p>
    <p v-if="loading" class="template-config-note" role="status">正在读取模板…</p>
    <TitlePagination label="模板配置" :page="page" :page-size="pageSize" :total="total" :disabled="loading" @page="changePage" @page-size="changePageSize" />
    <div v-if="editing" class="modal-backdrop" @click.self="close"><section v-dialog-focus="{close,busy:editingBusy}" class="modal-card template-config-dialog" role="dialog" aria-modal="true" aria-labelledby="template-config-title">
      <div class="template-config-dialog-heading"><h2 id="template-config-title">{{editing.name}} · 词库配置</h2><button class="ghost" :disabled="editingBusy" aria-label="关闭模板词库配置" @click="close">×</button></div>
      <TitleProfileEditor :token="token" :template-id="editing.id" :readonly="!admin" @busy="editingBusy=$event" @saved="saved" />
    </section></div>
  </section>
</template>

<style scoped>
.template-config-panel{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;min-width:0}.template-config-heading,.template-config-pagination,.template-config-dialog-heading{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.template-config-heading,.template-config-dialog-heading{justify-content:space-between}.template-config-heading h3,.template-config-dialog-heading h2{margin:0}.template-config-heading>span,.template-config-note{font-size:13px;color:#756e82}.template-config-note{margin:0;line-height:1.7}.template-config-scroll{overflow:auto;max-height:650px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:12px;border-bottom:1px solid #ede9f2;vertical-align:middle}th{position:sticky;top:0;z-index:1;background:#f6f4fa;white-space:nowrap}td small{display:block;color:#81788d;margin-top:5px;line-height:1.6}.template-config-product{display:flex;gap:10px;align-items:center;min-width:150px}.template-config-product img{width:42px;height:50px;border-radius:6px;object-fit:cover}.template-config-product strong{font-weight:600}.template-config-material{min-width:100px;max-width:200px;overflow-wrap:anywhere}.template-config-tags{display:flex;gap:5px;flex-wrap:wrap;min-width:120px;max-width:260px}.template-config-tags>span{padding:3px 7px;border-radius:5px;background:#f3f0fb;color:#6c598d;line-height:1.5}.template-config-state{display:inline-flex;padding:3px 9px;border-radius:999px;white-space:nowrap}.template-config-state.ready{background:#e7f6ee;color:#206b43}.template-config-state.incomplete{background:#fff4df;color:#8b641e}.template-config-issues{min-width:130px;max-width:240px}.template-config-pagination{font-size:13px}.template-config-dialog{width:min(800px,calc(100vw - 24px));max-height:88vh;overflow:auto;display:grid;gap:20px}.template-config-dialog-heading{flex-wrap:nowrap;align-items:flex-start}.template-config-dialog-heading h2{font-size:21px}.template-config-dialog-heading button{font-size:24px;line-height:1}@media(max-width:700px){.template-config-dialog{padding:20px}.template-config-dialog-heading h2{font-size:19px}}
</style>
