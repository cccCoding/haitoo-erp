<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'

const props = defineProps<{ token: string }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const period = ref('7'), memberId = ref<number | null>(null), data = ref<any>(null)
const loading = ref(false), error = ref('')
let controller: AbortController | undefined
const roles: Record<string, string> = { company_admin:'管理员', member:'普通运营', team_leader:'运营组长', designer:'普通美工', design_leader:'美工组长' }
async function load() {
  controller?.abort()
  const request = new AbortController(); controller = request
  loading.value = true; error.value = ''
  try {
    const response = await api.get('/operation-statistics', { headers:{ Authorization:`Bearer ${props.token}` }, params:{period:period.value, member_id:memberId.value}, signal:request.signal })
    if (!request.signal.aborted) data.value = response.data
  } catch (e:any) {
    if (!request.signal.aborted) error.value = e.response?.data?.detail || '加载运营统计失败，请重试'
  } finally { if (!request.signal.aborted) loading.value = false }
}
watch(() => [props.token, period.value, memberId.value], load, {immediate:true})
onBeforeUnmount(() => controller?.abort())
const rows = computed<any[]>(() => data.value?.daily || [])
const maxValue = computed(() => Math.max(4, Math.ceil(Math.max(0, ...rows.value.flatMap(row => [row.adopted_count, row.download_count])) / 4) * 4))
const x = (index:number) => rows.value.length === 1 ? 470 : 60 + index * 820 / (rows.value.length - 1)
const y = (value:number) => 245 - value / maxValue.value * 205
const points = (key:string) => rows.value.map((row,index) => `${x(index)},${y(row[key])}`).join(' ')
</script>

<template>
  <section class="page operation-statistics" :aria-busy="loading">
    <div class="toolbar statistics-filters">
      <label>统计周期<select v-model="period"><option value="today">今天</option><option value="yesterday">昨天</option><option value="7">近7天</option><option value="15">近15天</option><option value="30">近30天</option></select></label>
      <label>成员<select v-model="memberId"><option :value="null">全部成员</option><option v-for="member in data?.members || []" :key="member.id" :value="member.id">{{member.name}}{{member.is_active ? '' : '（已停用）'}}</option></select></label>
      <button class="secondary" :disabled="loading" @click="load">{{loading ? '加载中…' : '刷新统计'}}</button>
    </div>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <template v-if="data">
      <p class="statistics-note">{{data.date_from}} 至 {{data.date_to}} · 香港时间（UTC+8） · {{memberId ? data.members.find((m:any)=>m.id===memberId)?.name : '全部成员'}}</p>
      <div class="statistics-cards"><article><span>已采用 SKU 图</span><strong>{{data.summary.adopted_count.toLocaleString()}}</strong><small>按采用入库时间，归图片创作人</small></article><article><span>首次下载图片数</span><strong>{{data.summary.download_count.toLocaleString()}}</strong><small>归下载人，同一 SKU 重复下载不累加</small></article></div>
      <section class="statistics-chart"><h2>每日数量</h2><div class="statistics-legend"><span>● 已采用</span><span>● 首次下载</span></div>
        <svg viewBox="0 0 920 300" role="img" aria-label="每日采用和首次下载数量曲线">
          <g v-for="tick in [0,1,2,3,4]" :key="tick"><line x1="60" x2="880" :y1="40+tick*205/4" :y2="40+tick*205/4" stroke="#eceaf3"/><text x="48" :y="44+tick*205/4" text-anchor="end">{{Math.round(maxValue*(4-tick)/4)}}</text></g>
          <polyline :points="points('adopted_count')" fill="none" stroke="#7152dc" stroke-width="3"/><polyline :points="points('download_count')" fill="none" stroke="#209f97" stroke-width="3"/>
          <g v-for="(row,index) in rows" :key="row.date"><circle :cx="x(index)" :cy="y(row.adopted_count)" r="4" fill="#7152dc"><title>{{row.date}} 已采用 {{row.adopted_count}}</title></circle><circle :cx="x(index)" :cy="y(row.download_count)" r="4" fill="#209f97"><title>{{row.date}} 首次下载 {{row.download_count}}</title></circle><text v-if="rows.length<=7 || index===0 || index===rows.length-1 || index%5===0" :x="x(index)" y="275" text-anchor="middle">{{row.date.slice(5)}}</text></g>
        </svg>
        <details><summary>查看每日明细</summary><table><thead><tr><th>日期</th><th>已采用</th><th>首次下载</th></tr></thead><tbody><tr v-for="row in rows" :key="row.date"><td>{{row.date}}</td><td>{{row.adopted_count}}</td><td>{{row.download_count}}</td></tr></tbody></table></details>
      </section>
      <section class="statistics-members"><h2>成员统计</h2><table><thead><tr><th>成员</th><th>角色</th><th>状态</th><th>已采用 SKU 图</th><th>首次下载图片</th><th>日曲线</th></tr></thead><tbody><tr v-for="member in data.members" :key="member.id" :class="{selected:memberId===member.id}"><td>{{member.name}}</td><td>{{roles[member.role] || member.role}}</td><td>{{member.is_active ? '正常' : '已停用'}}</td><td>{{member.adopted_count}}</td><td>{{member.download_count}}</td><td><button class="ghost" @click="memberId=member.id">查看</button></td></tr></tbody></table></section>
      <p class="statistics-note">{{data.history_note}}</p>
    </template>
  </section>
</template>

<style scoped>
.statistics-filters{justify-content:flex-start;gap:16px;align-items:flex-end}.statistics-filters label{min-width:160px;font-size:13px}.statistics-filters button{margin-bottom:2px}.statistics-note{font-size:13px;color:#817b91;line-height:1.7}.statistics-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin:20px 0}.statistics-cards article,.statistics-chart,.statistics-members{padding:24px;border:1px solid #ebe9f3;border-radius:14px;background:white}.statistics-cards span,.statistics-cards small{display:block;color:#817b91}.statistics-cards strong{display:block;font-size:32px;margin:12px 0;color:#493292}.statistics-chart{margin-bottom:20px}.statistics-chart h2,.statistics-members h2{font-size:18px;margin:0 0 18px}.statistics-legend{display:flex;gap:18px;font-size:13px;color:#7152dc}.statistics-legend span+span{color:#209f97}.statistics-chart svg{width:100%;max-height:360px}.statistics-chart text{font-size:12px;fill:#817b91}.statistics-members{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:14px 12px;text-align:left;border-bottom:1px solid #eeeaf6}th{color:#817b91;background:#faf9fc}.selected{background:#f5f2ff}summary{cursor:pointer;color:#6d50cc;font-size:13px}@media(max-width:700px){.statistics-cards{grid-template-columns:1fr}.statistics-filters{flex-wrap:wrap}.statistics-chart,.statistics-members{padding:16px}}
</style>
