<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import TitlePagination from './TitlePagination.vue'

const props = defineProps<{ token: string; keywordId: number }>()
const api = axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8000'})
const rows = ref<any[]>([]), total = ref(0), page = ref(1), pageSize = ref(20), loading = ref(false), error = ref('')
let revision = 0, loadedPage = 1, loadedPageSize = 20
async function load() {
  const current=++revision;loading.value=true;error.value=''
  try {
    const {data}=await api.get(`/title-keywords/${props.keywordId}/evidence`,{headers:{Authorization:`Bearer ${props.token}`},params:{page:page.value,page_size:pageSize.value}})
    if(current!==revision)return
    rows.value=data.items;total.value=data.total;page.value=data.page||1;loadedPage=page.value;loadedPageSize=pageSize.value
  } catch(e:any){if(current===revision){page.value=loadedPage;pageSize.value=loadedPageSize;error.value=typeof e.response?.data?.detail==='string'?e.response.data.detail:'读取词源失败'}}
  finally{if(current===revision)loading.value=false}
}
function changePage(value:number){if(loading.value)return;page.value=value;void load()}
function changeSize(value:number){if(loading.value)return;pageSize.value=value;page.value=1;void load()}
watch(()=>[props.keywordId,props.token],()=>{page.value=1;loadedPage=1;rows.value=[];total.value=0;void load()},{immediate:true})
onUnmounted(()=>{revision++})
</script>

<template>
  <section class="keyword-evidence-list" :aria-busy="loading">
    <p v-if="error" class="error" role="alert">{{error}} <button type="button" :disabled="loading" @click="load">重新加载</button></p>
    <div class="keyword-evidence-scroll">
      <article v-for="(item,index) in rows" :key="index"><p>{{item.original_title}}</p><small>{{item.original_phrase}} · 原文位置 {{item.position}} · 第 {{item.import_id}} 批</small><p>{{item.source_name}} · {{item.period_basis==='import_date'?'导入日期':'数据日期'}}：{{item.period}} · {{item.source_product}}</p><p v-if="item.note" class="keyword-evidence-note">备注：{{item.note}}</p></article>
      <p v-if="loading&&!rows.length" role="status">正在读取词源…</p><p v-else-if="!rows.length&&!error">暂无词源记录。</p>
    </div>
    <TitlePagination label="词源证据" :page="page" :page-size="pageSize" :total="total" :disabled="loading" @page="changePage" @page-size="changeSize" />
  </section>
</template>

<style scoped>
.keyword-evidence-list{display:grid;gap:16px;min-width:0}.keyword-evidence-scroll{overflow:auto;max-height:40vh}.keyword-evidence-scroll article{border-bottom:1px solid #eee;padding:12px 0;overflow-wrap:anywhere}.keyword-evidence-scroll p{margin:6px 0;line-height:1.6}.keyword-evidence-scroll small{color:#81788d}.keyword-evidence-note{white-space:pre-wrap}.keyword-evidence-list>p{margin:0}
</style>
