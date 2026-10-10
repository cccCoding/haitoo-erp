<script setup lang="ts">
import { computed, ref } from 'vue'
import { dialogFocus as vDialogFocus } from './dialog-focus'

const props = defineProps<{
  items: any[]; groups: {id: number; name: string}[]; companyName: string
  imageUrl: (url: string) => string; loading: boolean; error: string; hasCompany: boolean
}>()
const groupId = ref<number | null>(null), query = ref('')
const detail = ref<any>(null)
const visibleItems = computed(() => props.items.filter(item =>
  (groupId.value === null || item.group_id === groupId.value) && item.name.toLowerCase().includes(query.value.trim().toLowerCase())))
function groupName(id: number) { return props.groups.find(item => item.id === id)?.name || '未分类' }
function closeDetail() { detail.value = null }
function reset() { groupId.value = null; query.value = ''; closeDetail() }
defineExpose({ reset })
</script>

<template>
  <section class="template-library" :aria-busy="loading">
    <label class="template-search">搜索模板<input v-model="query" type="search" placeholder="搜索模板名称" /></label>
    <div class="template-layout">
      <nav class="template-groups" aria-label="模板分类">
        <h3>模板分类</h3>
        <button :class="{active:groupId===null}" :aria-pressed="groupId===null" @click="groupId=null">全部模板</button>
        <button v-for="group in groups" :key="group.id" :class="{active:groupId===group.id}" :aria-pressed="groupId===group.id" @click="groupId=group.id">{{group.name}}</button>
      </nav>
      <section class="template-content">
        <header><h3>{{groupId===null ? '全部模板' : groupName(groupId)}}</h3><span v-if="!loading && !error">共 {{visibleItems.length}} 个模板 · 只读</span></header>
        <p v-if="loading" class="template-empty" role="status">正在加载模板…</p>
        <p v-else-if="!hasCompany" class="template-empty">请选择公司查看模板。</p>
        <p v-else-if="!visibleItems.length && !error" class="template-empty">没有符合筛选条件的模板。</p>
        <div v-else-if="!error" class="template-grid">
          <article v-for="item in visibleItems" :key="item.id" class="template-card">
            <button class="template-image" :aria-label="`查看 ${item.name} 详情`" @click="detail=item"><img v-if="item.cover_url" :src="imageUrl(item.cover_url)" :alt="item.name" loading="lazy"/><span v-else>暂无图片</span></button>
            <div class="template-card-body"><small>{{companyName}} · {{groupName(item.group_id)}}</small><h3>{{item.name}}</h3><p :title="item.description">{{item.description || '暂无模板描述'}}</p><button class="secondary" @click="detail=item">查看详情</button></div>
          </article>
        </div>
      </section>
    </div>
  </section>
  <div v-if="detail" v-dialog-focus="{close:closeDetail}" class="modal-backdrop" @click.self="closeDetail">
    <section class="template-detail" role="dialog" aria-modal="true" aria-labelledby="template-detail-title">
      <header><h2 id="template-detail-title">{{detail.name}}</h2><button class="secondary" autofocus @click="closeDetail">关闭</button></header>
      <p class="template-meta">{{companyName}} · {{groupName(detail.group_id)}} · 只读</p>
      <img v-if="detail.cover_url" class="detail-image" :src="imageUrl(detail.cover_url)" :alt="detail.name"/>
      <h3>模板信息</h3><p>{{detail.description || '暂无模板描述'}}</p>
      <h3>商品信息</h3><p>{{detail.product_description || '暂无产品描述'}}</p><p>尺码：{{detail.sku_specifications?.size?.options?.join('、') || '未设置'}}</p>
      <img v-if="detail.size_chart_url" class="detail-image" :src="imageUrl(detail.size_chart_url)" alt="尺码图"/><p v-else>暂无尺码图</p>
      <h3>物流信息</h3><p>包裹重量：{{detail.package_weight ?? '未设置'}} kg</p><p>包裹尺寸（长 × 宽 × 高）：{{detail.package_length ?? '—'}} × {{detail.package_width ?? '—'}} × {{detail.package_height ?? '—'}} cm</p>
      <h3>AI 提示词</h3><h4>AI 生成标题要求</h4><p>{{detail.title_template || '未设置'}}</p><h4>AI 生成素材提示</h4>
      <div v-for="(prompt,index) in detail.ai_prompts || []" :key="index"><h4>{{prompt.name}}</h4><p>{{prompt.content}}</p></div><p v-if="!detail.ai_prompts?.length">暂无素材提示词</p>
    </section>
  </div>
</template>

<style scoped>
.template-library { padding:24px; }
.template-search { display:grid; gap:7px; width:min(320px,100%); margin-bottom:20px; color:var(--admin-muted); font-size:12px; }
.template-search input { padding:9px 12px; }
.template-layout { display:grid; grid-template-columns:180px minmax(0,1fr); gap:24px; align-items:start; }
.template-groups { padding:16px; border:1px solid var(--admin-border); border-radius:var(--admin-radius); background:var(--admin-surface); }
h3 { margin:0 0 14px; font-size:16px; }
.template-groups button { display:block; width:100%; padding:10px; border-radius:8px; text-align:left; background:transparent; color:var(--admin-muted); overflow-wrap:anywhere; }
.template-groups button.active { color:var(--admin-primary); background:var(--admin-primary-soft); }
.template-content { min-width:0; }
.template-content header, .template-detail header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }
.template-content header h3 { margin:0; }
.template-content header span, .template-meta { color:var(--admin-muted); font-size:12px; }
.template-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:20px; }
.template-card { overflow:hidden; border:1px solid var(--admin-border); border-radius:var(--admin-radius); background:var(--admin-surface); }
.template-image { display:grid; place-items:center; width:100%; height:220px; overflow:hidden; padding:0; background:var(--admin-primary-soft); color:var(--admin-muted); }
.template-image img { display:block; width:100%; height:220px; min-width:0; object-fit:contain; }
.template-card-body { padding:16px; }
.template-card-body small { color:var(--admin-muted); font-size:11px; }
.template-card-body h3 { margin:8px 0; overflow-wrap:anywhere; }
.template-card-body p { display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; color:var(--admin-muted); font-size:12px; line-height:1.7; min-height:60px; }
.template-empty { padding:40px 16px; text-align:center; color:var(--admin-muted); }
.template-detail { width:min(760px,100%); max-height:calc(100dvh - 48px); overflow:auto; padding:24px; border:1px solid var(--admin-border); border-radius:var(--admin-radius); background:var(--admin-surface); }
.template-detail h2 { margin:0; font-size:21px; overflow-wrap:anywhere; }
.template-detail h3 { margin-top:24px; }
.template-detail h4 { font-size:13px; }
.template-detail p { white-space:pre-wrap; overflow-wrap:anywhere; font-size:13px; color:var(--admin-muted); }
.detail-image { display:block; max-width:100%; max-height:400px; margin:16px auto; object-fit:contain; }
@media(max-width:760px) {
  .template-library { padding:20px 0; }
  .template-layout { grid-template-columns:1fr; gap:16px; }
  .template-groups { display:flex; flex-wrap:wrap; gap:8px; }
  .template-groups h3 { flex-basis:100%; margin-bottom:4px; }
  .template-groups button { width:auto; max-width:100%; }
  .template-grid { grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); }
  .template-detail { padding:20px; max-height:calc(100dvh - 32px); }
}
</style>
