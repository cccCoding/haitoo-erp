<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'

type Metric = 'adopted_count' | 'download_count'
type Counts = Record<Metric, number>
type DailyRow = Counts & { date: string }
type Member = Counts & { id: number; name: string; role: string; is_active: boolean }
type Statistics = { summary: Counts; daily: DailyRow[]; members: Member[]; history_note: string }
type Series = { id: string; name: string; color: string; daily: DailyRow[] }

const props = defineProps<{ token: string }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const periods = [{ value: 'today', label: '今天' }, { value: 'yesterday', label: '昨天' }, { value: '7', label: '近7天' }, { value: '15', label: '近15天' }, { value: '30', label: '近30天' }]
const period = ref('7'), data = ref<Statistics | null>(null)
const loading = ref(false), error = ref(''), query = ref(''), sortKey = ref<Metric>('adopted_count')
const selectedIds = ref<number[]>([])
const memberDaily = ref<Record<number, DailyRow[]>>({})
const memberErrors = ref<Record<number, string>>({})
const pendingMembers = ref<number[]>([])
const memberRequests = new Map<number, AbortController>()
const visibleMetrics = ref<Record<Metric, boolean>>({ adopted_count: true, download_count: false })
const metrics: { key: Metric; label: string; color: string }[] = [
  { key: 'adopted_count', label: '已采用', color: '#7152dc' },
  { key: 'download_count', label: '下载', color: '#209f97' },
]
const colors = ['#7152dc', '#209f97', '#d97706', '#d34575', '#287ac0', '#738824', '#aa4cbd', '#896046']
const roles: Record<string, string> = { company_admin:'管理员', member:'普通运营', team_leader:'运营组长', designer:'普通美工', design_leader:'美工组长' }
let controller: AbortController | undefined
function abortMembers() {
  memberRequests.forEach(request => request.abort())
  memberRequests.clear()
  pendingMembers.value = []
}
async function loadMember(id: number) {
  if (!controller || controller.signal.aborted) return
  const parent = controller, request = new AbortController()
  memberRequests.get(id)?.abort()
  memberRequests.set(id, request)
  pendingMembers.value = [...new Set([...pendingMembers.value, id])]
  delete memberErrors.value[id]
  try {
    const response = await api.get<Statistics>('/operation-statistics', {
      headers: { Authorization: `Bearer ${props.token}` }, params: { period: period.value, member_id: id }, signal: request.signal,
    })
    if (!parent.signal.aborted && !request.signal.aborted) memberDaily.value[id] = response.data.daily
  } catch (e: any) {
    if (!parent.signal.aborted && !request.signal.aborted) memberErrors.value[id] = e.response?.data?.detail || '数据加载失败，请重试'
  } finally {
    if (memberRequests.get(id) === request) {
      memberRequests.delete(id)
      pendingMembers.value = pendingMembers.value.filter(pending => pending !== id)
    }
  }
}
async function load() {
  controller?.abort()
  abortMembers()
  const request = new AbortController(); controller = request
  loading.value = true; error.value = ''; hoveredIndex.value = null
  memberDaily.value = {}; memberErrors.value = {}
  try {
    const response = await api.get<Statistics>('/operation-statistics', {
      headers: { Authorization: `Bearer ${props.token}` }, params: { period: period.value }, signal: request.signal,
    })
    if (request.signal.aborted) return
    data.value = response.data
    selectedIds.value = selectedIds.value.filter(id => response.data.members.some(member => member.id === id))
    await Promise.all(selectedIds.value.map(loadMember))
  } catch (e: any) {
    if (!request.signal.aborted) { data.value = null; error.value = e.response?.data?.detail || '加载运营统计失败，请重试' }
  } finally { if (!request.signal.aborted) loading.value = false }
}
function closeMember(id: number) {
  selectedIds.value = selectedIds.value.filter(selected => selected !== id)
  memberRequests.get(id)?.abort()
  memberRequests.delete(id)
  pendingMembers.value = pendingMembers.value.filter(pending => pending !== id)
  delete memberErrors.value[id]
}
function clearMembers() { [...selectedIds.value].forEach(closeMember) }
function toggleMember(id: number) {
  if (selectedIds.value.includes(id)) return closeMember(id)
  selectedIds.value = [...selectedIds.value, id]
  if (!memberDaily.value[id]) void loadMember(id)
}
const rows = computed(() => data.value?.daily || [])
const selectedMembers = computed(() => (data.value?.members || []).filter(member => selectedIds.value.includes(member.id)))
const filteredMembers = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  return (data.value?.members || []).filter(member => member.name.toLocaleLowerCase().includes(keyword))
    .slice().sort((a, b) => b[sortKey.value] - a[sortKey.value] || a.id - b.id)
})
const memberColor = (id: number) => {
  const index = Math.max(0, data.value?.members.findIndex(member => member.id === id) ?? 0)
  return colors[index] || `hsl(${(index * 137.5) % 360} 55% 42%)`
}
const series = computed<Series[]>(() => selectedIds.value.length
  ? selectedMembers.value.filter(member => memberDaily.value[member.id]).map(member => ({ id: String(member.id), name: member.name, color: memberColor(member.id), daily: memberDaily.value[member.id] }))
  : [{ id: 'all', name: '全部成员', color: '#7152dc', daily: rows.value }])
const activeMetrics = computed(() => metrics.filter(metric => visibleMetrics.value[metric.key]))
const maxValue = computed(() => Math.max(4, Math.ceil(Math.max(0, ...series.value.flatMap(item => item.daily.flatMap(row => activeMetrics.value.map(metric => row[metric.key])))) / 4) * 4))
const isSingleDay = computed(() => rows.value.length === 1)
const chartTitle = computed(() => selectedIds.value.length ? `成员对比 · 已选${selectedIds.value.length}人` : `全部成员${isSingleDay.value ? '数量' : '趋势'}`)
const periodLabel = computed(() => periods.find(item => item.value === period.value)?.label)
const plot = ref<HTMLDivElement | null>(null), chartWidth = ref(700), hoveredIndex = ref<number | null>(null)
let resizeObserver: ResizeObserver | undefined
watch(plot, element => {
  resizeObserver?.disconnect()
  if (element) { chartWidth.value = Math.max(260, element.clientWidth); resizeObserver?.observe(element) }
})
onMounted(() => {
  resizeObserver = new ResizeObserver(entries => { chartWidth.value = Math.max(260, entries[0].contentRect.width) })
  if (plot.value) { chartWidth.value = Math.max(260, plot.value.clientWidth); resizeObserver.observe(plot.value) }
})
const plotLeft = 48, plotTop = 28, plotBottom = 270
const plotRight = computed(() => chartWidth.value - 24)
const plotSpan = computed(() => plotRight.value - plotLeft)
const x = (index: number) => rows.value.length <= 1 ? plotLeft + plotSpan.value / 2 : plotLeft + index * plotSpan.value / (rows.value.length - 1)
const y = (value: number) => plotBottom - value / maxValue.value * (plotBottom - plotTop)
const points = (daily: DailyRow[], key: Metric) => daily.map((row, index) => `${x(index)},${y(row[key])}`).join(' ')
const lineColor = (item: Series, key: Metric) => selectedIds.value.length ? item.color : metrics.find(metric => metric.key === key)!.color
const groupWidth = computed(() => plotSpan.value / Math.max(1, series.value.length))
const barWidth = computed(() => Math.min(32, groupWidth.value * .65 / Math.max(1, activeMetrics.value.length)))
const barCenter = (index: number) => plotLeft + groupWidth.value * (index + .5)
const barX = (index: number, metricIndex: number) => barCenter(index) + (metricIndex - activeMetrics.value.length / 2) * barWidth.value
function inspectChart(event: PointerEvent) {
  if (loading.value || !activeMetrics.value.length || !rows.value.length || !(event.currentTarget instanceof SVGSVGElement)) return
  const rect = event.currentTarget.getBoundingClientRect()
  const position = (event.clientX - rect.left) * chartWidth.value / rect.width
  hoveredIndex.value = isSingleDay.value ? 0 : Math.max(0, Math.min(rows.value.length - 1, Math.round((position - plotLeft) / plotSpan.value * (rows.value.length - 1))))
}
function inspectWithKeyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') { hoveredIndex.value = null; return }
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  if (loading.value || !activeMetrics.value.length || !rows.value.length) return
  hoveredIndex.value = event.key === 'Home' ? 0 : event.key === 'End' ? rows.value.length - 1 : Math.max(0, Math.min(rows.value.length - 1, (hoveredIndex.value ?? 0) + (event.key === 'ArrowRight' ? 1 : -1)))
}
const tooltipRows = computed(() => hoveredIndex.value === null ? [] : series.value.map(item => ({ ...item, row: item.daily[hoveredIndex.value!] })))
watch(() => [props.token, period.value], ([token], old) => {
  if (old && token !== old[0]) { selectedIds.value = []; data.value = null }
  void load()
}, { immediate: true })
watch([selectedIds, activeMetrics], () => { hoveredIndex.value = null })
onBeforeUnmount(() => { controller?.abort(); abortMembers(); resizeObserver?.disconnect() })
</script>

<template>
  <section class="page operation-statistics" :aria-busy="loading">
    <div class="statistics-filters">
      <div class="period-control"><span>统计周期</span><div class="period-options" role="group" aria-label="统计周期"><button v-for="item in periods" :key="item.value" :aria-pressed="period===item.value" @click="period=item.value">{{item.label}}</button></div></div>
      <button class="secondary refresh-button" :disabled="loading" @click="load">{{loading ? '加载中…' : '刷新统计'}}</button>
    </div>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <template v-if="data">
      <section class="statistics-overview" aria-label="公司总览">
        <div class="overview-label"><strong>公司总览</strong><small>{{periodLabel}} · 全部成员</small></div>
        <div v-for="metric in metrics" :key="metric.key" class="overview-metric"><span>{{metric.key==='adopted_count' ? '已采用 SKU 图' : '下载图片数'}}</span><strong>{{data.summary[metric.key].toLocaleString()}}</strong><small>{{metric.key==='adopted_count' ? '按采用入库时间，归图片创作人' : '归下载人，同一 SKU 重复下载不累加'}}</small></div>
      </section>
      <div class="statistics-workspace">
        <section class="statistics-chart" aria-labelledby="statistics-chart-title">
          <div class="chart-heading"><div><h2 id="statistics-chart-title">{{chartTitle}}</h2><p>{{periodLabel}} · {{isSingleDay ? '柱状对比' : '每日数量'}}</p></div><div class="statistics-legend" role="group" aria-label="图表指标"><button v-for="metric in metrics" :key="metric.key" :aria-pressed="visibleMetrics[metric.key]" :class="{muted:!visibleMetrics[metric.key]}" @click="visibleMetrics[metric.key]=!visibleMetrics[metric.key]"><span class="legend-line" :class="{dashed:metric.key==='download_count'}" aria-hidden="true"/>{{metric.label}}</button></div></div>
          <div ref="plot" class="chart-plot" @pointerleave="hoveredIndex=null">
            <svg :viewBox="`0 0 ${chartWidth} 320`" role="img" tabindex="0" :aria-label="`${chartTitle}，左右方向键查看每日数据，Esc 关闭提示`" :aria-describedby="hoveredIndex!==null ? 'statistics-tooltip' : undefined" @pointermove="inspectChart" @pointerdown="inspectChart" @focus="!loading && activeMetrics.length && rows.length && (hoveredIndex=0)" @blur="hoveredIndex=null" @keydown="inspectWithKeyboard">
              <defs><pattern id="statistics-download-pattern" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="3" height="6" fill="white" opacity=".45"/></pattern></defs>
              <g v-for="tick in [0,1,2,3,4]" :key="tick"><line :x1="plotLeft" :x2="plotRight" :y1="y(maxValue*tick/4)" :y2="y(maxValue*tick/4)" stroke="#eceaf3"/><text :x="plotLeft-10" :y="y(maxValue*tick/4)+4" text-anchor="end">{{maxValue*tick/4}}</text></g>
              <template v-if="!loading && isSingleDay">
                <g v-for="(item,index) in series" :key="item.id" :data-series="item.id">
                  <g v-for="(metric,metricIndex) in activeMetrics" :key="metric.key" :data-metric="metric.key">
                    <rect :x="barX(index,metricIndex)" :y="Math.min(plotBottom-2,y(item.daily[0]?.[metric.key] || 0))" :width="barWidth-1" :height="Math.max(2,plotBottom-y(item.daily[0]?.[metric.key] || 0))" rx="3" :fill="lineColor(item,metric.key)"><title>{{item.name}} {{metric.label}} {{item.daily[0]?.[metric.key] || 0}}</title></rect>
                    <rect v-if="metric.key==='download_count'" :x="barX(index,metricIndex)" :y="Math.min(plotBottom-2,y(item.daily[0]?.[metric.key] || 0))" :width="barWidth-1" :height="Math.max(2,plotBottom-y(item.daily[0]?.[metric.key] || 0))" fill="url(#statistics-download-pattern)" pointer-events="none"/>
                  </g>
                  <text v-if="index%Math.max(1,Math.ceil(series.length/6))===0" :x="barCenter(index)" y="296" text-anchor="middle">{{item.name.length>6 ? `${item.name.slice(0,6)}…` : item.name}}</text>
                </g>
              </template>
              <template v-else-if="!loading">
                <line v-if="hoveredIndex!==null" :x1="x(hoveredIndex)" :x2="x(hoveredIndex)" :y1="plotTop" :y2="plotBottom" stroke="#b8afd2" stroke-dasharray="4 4"/>
                <g v-for="item in series" :key="item.id" :data-series="item.id"><g v-for="metric in activeMetrics" :key="metric.key" :data-metric="metric.key"><polyline :points="points(item.daily,metric.key)" fill="none" :stroke="lineColor(item,metric.key)" stroke-width="2.5" :stroke-dasharray="metric.key==='download_count' ? '7 5' : undefined"/><circle v-for="(row,index) in item.daily" :key="row.date" :cx="x(index)" :cy="y(row[metric.key])" :r="hoveredIndex===index ? 5 : rows.length>15 ? 2 : 3" :fill="lineColor(item,metric.key)"/></g></g>
                <template v-for="(row,index) in rows" :key="row.date"><text v-if="index===0 || index===rows.length-1 || index%Math.max(1,Math.ceil(rows.length/(chartWidth<450 ? 4 : 6)))===0 && index<rows.length-2" :x="x(index)" y="296" text-anchor="middle">{{row.date.slice(5)}}</text></template>
              </template>
            </svg>
            <div v-if="loading || !activeMetrics.length || !series.length" class="chart-message" role="status">{{loading ? '正在更新统计…' : !activeMetrics.length ? '点击“已采用”或“下载”显示数据' : pendingMembers.length ? '正在加载成员数据…' : '成员数据加载失败，请在成员列表中重试'}}</div>
            <div v-if="hoveredIndex!==null && activeMetrics.length && !loading && tooltipRows.length" id="statistics-tooltip" class="chart-tooltip" role="tooltip">
              <strong>{{rows[hoveredIndex]?.date}}</strong><table><thead><tr><th>成员</th><th v-for="metric in activeMetrics" :key="metric.key">{{metric.label}}</th></tr></thead><tbody><tr v-for="item in tooltipRows" :key="item.id"><td><span class="member-dot" :style="{background:item.color}"/>{{item.name}}</td><td v-for="metric in activeMetrics" :key="metric.key">{{item.row?.[metric.key] ?? '—'}}</td></tr></tbody></table>
            </div>
          </div>
          <div class="chart-selection"><div v-if="selectedMembers.length" class="statistics-comparison" aria-label="正在查看的成员"><button v-for="member in selectedMembers" :key="member.id" :aria-label="`移除 ${member.name}`" @click="closeMember(member.id)"><span class="member-dot" :style="{background:memberColor(member.id)}"/>{{member.name}}<small v-if="pendingMembers.includes(member.id)">加载中</small><span aria-hidden="true">×</span></button><button class="clear-members" @click="clearMembers">清空选择</button></div><span v-else>当前显示公司汇总，勾选成员开始对比</span></div>
          <p class="chart-hint">{{isSingleDay ? '悬停或轻触图表查看当天数据' : '悬停或轻触图表，比较同一天的成员数据'}} · {{isSingleDay ? '纯色已采用 / 斜纹下载' : '实线已采用 / 虚线下载'}}</p>
          <details><summary>查看每日明细</summary><div class="statistics-detail"><table><thead><tr><th>日期</th><template v-for="item in series" :key="item.id"><th>{{item.name}} · 已采用</th><th>{{item.name}} · 下载</th></template></tr></thead><tbody><tr v-for="(row,index) in rows" :key="row.date"><td>{{row.date}}</td><template v-for="item in series" :key="item.id"><td>{{item.daily[index]?.adopted_count ?? '—'}}</td><td>{{item.daily[index]?.download_count ?? '—'}}</td></template></tr></tbody></table></div></details>
        </section>
        <section class="statistics-members" aria-labelledby="statistics-members-title">
          <div class="members-heading"><h2 id="statistics-members-title">成员统计</h2><span>{{data.members.length}}人<span v-if="selectedIds.length"> · 已选{{selectedIds.length}}人</span></span></div>
          <p class="statistics-note">勾选成员对比，点击行也可选择</p>
          <input v-model="query" class="member-search" type="search" aria-label="搜索成员" placeholder="搜索成员姓名"/>
          <div class="members-scroll"><table><thead><tr><th>成员</th><th><button :aria-pressed="sortKey==='adopted_count'" @click="sortKey='adopted_count'">已采用<span v-if="sortKey==='adopted_count'"> ↓</span></button></th><th><button :aria-pressed="sortKey==='download_count'" @click="sortKey='download_count'">下载<span v-if="sortKey==='download_count'"> ↓</span></button></th></tr></thead><tbody><tr v-for="member in filteredMembers" :key="member.id" :class="{selected:selectedIds.includes(member.id)}" @click="toggleMember(member.id)"><td><label class="member-label" @click.stop><input type="checkbox" :checked="selectedIds.includes(member.id)" :aria-label="`对比 ${member.name}`" @change="toggleMember(member.id)"/><span><span class="member-name"><span class="member-dot" :style="{background:memberColor(member.id)}"/>{{member.name}}</span><small>{{roles[member.role] || member.role}}{{member.is_active ? '' : ' · 已停用'}}</small></span></label><small v-if="pendingMembers.includes(member.id)" class="member-loading" role="status">加载中…</small><div v-if="memberErrors[member.id]" class="member-error" role="alert">{{memberErrors[member.id]}}<button @click.stop="loadMember(member.id)">重试</button></div></td><td>{{member.adopted_count.toLocaleString()}}</td><td>{{member.download_count.toLocaleString()}}</td></tr><tr v-if="!filteredMembers.length"><td colspan="3" class="statistics-empty">{{data.members.length ? '未找到匹配成员' : '暂无成员统计'}}</td></tr></tbody></table></div>
          <div class="members-footer">{{selectedIds.length ? `已选 ${selectedIds.length} 人，数据同步显示在图表中` : '未选择成员时显示公司汇总'}}</div>
        </section>
      </div>
      <p class="statistics-note history-note">{{data.history_note}}</p>
    </template>
    <div v-else-if="loading" class="initial-loading" role="status">正在加载统计…</div>
  </section>
</template>

<style scoped>
.operation-statistics{width:100%;min-width:0}
.statistics-filters,.period-control,.period-options{display:flex;align-items:center;gap:12px}
.statistics-filters{justify-content:space-between;margin-bottom:20px}
.period-control>span{font-size:13px;color:#655e76;white-space:nowrap}
.period-options{gap:4px;padding:4px;border:1px solid #e7e3f2;border-radius:11px;background:#fff}
.period-options button{padding:8px 14px;border-radius:7px;font-size:13px;white-space:nowrap;color:#6f687e}
.period-options button[aria-pressed=true]{background:#eee9ff;color:#6041ca;font-weight:700}
.refresh-button{font-size:13px;white-space:nowrap}
.statistics-overview{display:grid;grid-template-columns:minmax(140px,.65fr) repeat(2,minmax(0,1fr));gap:24px;margin-bottom:20px;padding:22px 24px;background:#fff;border:1px solid #ebe9f3;border-radius:14px}
.overview-label{display:flex;flex-direction:column;justify-content:center;gap:8px}
.overview-label strong{font-size:15px}
.overview-label small,.overview-metric span,.overview-metric small{color:#817b91;font-size:12px}
.overview-metric{border-left:1px solid #eeebf5;padding-left:24px}
.overview-metric span,.overview-metric small{display:block;line-height:1.6}
.overview-metric strong{display:block;color:#493292;font-size:30px;margin:4px 0}
.statistics-workspace{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:20px;align-items:start}
.statistics-chart,.statistics-members{min-width:0;border:1px solid #ebe9f3;border-radius:14px;background:#fff}
.statistics-chart{padding:24px}
.chart-heading,.members-heading{display:flex;justify-content:space-between;gap:12px;align-items:center}
h2{font-size:17px;margin:0}
.chart-heading p{margin:7px 0 0;color:#817b91;font-size:12px}
.statistics-legend{display:flex;gap:8px;flex-shrink:0}
.statistics-legend button{display:inline-flex;align-items:center;gap:6px;padding:7px 9px;border:1px solid #d8d0ef;border-radius:8px;color:#5f48b6;background:#f6f3ff;font-size:12px}
.statistics-legend button.muted{border-color:#e7e3ed;color:#888191;background:#fff}
.statistics-legend button.muted .legend-line{opacity:.35}
.legend-line{width:18px;border-top:3px solid currentColor}
.legend-line.dashed{border-top-style:dashed}
.chart-plot{position:relative;margin-top:16px}
.chart-plot svg{display:block;width:100%;height:320px;touch-action:pan-y;outline-offset:3px}
.chart-plot text{font-size:11px;fill:#817b91}
.chart-message{position:absolute;inset:0;display:grid;place-items:center;padding:24px;background:#ffffffd9;color:#817b91;text-align:center;font-size:13px;pointer-events:none}
.chart-tooltip{position:absolute;right:12px;top:8px;max-width:calc(100% - 24px);max-height:235px;overflow:auto;padding:12px;background:#fff;border:1px solid #e2dcef;border-radius:10px;box-shadow:0 8px 25px #3929601f;font-size:12px}
.chart-tooltip>strong{font-size:12px}
.chart-tooltip table{margin-top:7px}
.chart-tooltip td,.chart-tooltip th{padding:7px 9px}
.chart-tooltip td:first-child{max-width:140px;overflow-wrap:anywhere}
.chart-tooltip th:not(:first-child),.chart-tooltip td:not(:first-child){text-align:right}
.chart-selection{border-top:1px solid #eeebf5;padding-top:14px;min-height:48px;font-size:12px;color:#817b91}
.statistics-comparison{display:flex;flex-wrap:wrap;gap:7px}
.statistics-comparison button{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid #e6e0f3;border-radius:7px;font-size:12px;color:#514662;background:#faf9fd}
.statistics-comparison .clear-members{border:0;background:none;color:#7051ce}
.statistics-comparison small{color:#817b91}
.statistics-comparison button>span:last-child{font-size:16px;line-height:1}
.member-dot{display:inline-block;width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-right:5px}
.statistics-comparison .member-dot{margin:0}
.chart-hint{font-size:11px;color:#817b91;margin:12px 0 16px;line-height:1.7}
.statistics-members{padding-top:20px;overflow:hidden}
.members-heading,.statistics-members>.statistics-note{margin-left:18px;margin-right:18px}
.members-heading>span{font-size:12px;color:#817b91}
.statistics-note{font-size:12px;color:#817b91;line-height:1.8}
.statistics-members>.statistics-note{margin-top:8px;margin-bottom:14px}
.member-search{display:block;width:calc(100% - 36px);margin:0 18px 16px;padding:10px 12px;border:1px solid #e3deee;border-radius:8px;font-size:13px;background:#fcfbfe;min-width:0}
.members-scroll{max-height:350px;overflow:auto;scrollbar-gutter:stable}
.members-scroll thead{position:sticky;top:0;z-index:1}
.members-scroll th:first-child{width:60%}
.members-scroll th,.members-scroll td{padding:13px 14px}
.members-scroll th:not(:first-child),.members-scroll td:not(:first-child){text-align:right;font-variant-numeric:tabular-nums}
.members-scroll th button{padding:0;white-space:nowrap;font-size:12px}
.members-scroll th button[aria-pressed=true]{color:#6041ca}
.members-scroll tbody tr{cursor:pointer}
.members-scroll tbody tr:hover{background:#faf8ff}
.members-scroll .selected{background:#f5f1ff}
.member-label{display:flex;align-items:center;gap:9px;cursor:pointer}
.member-label input{width:15px;height:15px;flex-shrink:0;margin:0;accent-color:#7152dc;cursor:pointer}
.member-label>span{min-width:0}
.member-name{display:flex;align-items:center;overflow-wrap:anywhere;font-size:13px;color:#443b55}
.member-label small{display:block;font-size:10px;color:#817b91;margin:5px 0 0 13px;line-height:1.5}
.member-loading{display:block;font-size:11px;color:#817b91;margin:6px 0 0 24px}
.member-error{font-size:11px;color:#c1445b;margin:6px 0 0 24px;line-height:1.6}
.member-error button{color:#7152dc;text-decoration:underline;padding:3px 5px}
.members-footer{padding:14px 18px;border-top:1px solid #eeebf5;font-size:11px;color:#817b91;line-height:1.7}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{padding:12px;text-align:left;border-bottom:1px solid #eeeaf6}
th{color:#817b91;background:#faf9fc;font-weight:500;white-space:nowrap}
.statistics-detail{overflow-x:auto;max-height:320px}
.statistics-detail td{white-space:nowrap}
summary{cursor:pointer;color:#6d50cc;font-size:12px}
.statistics-empty{text-align:center!important;color:#817b91;padding:36px 12px!important;cursor:default}
.history-note{margin:16px 0 0}
.initial-loading{padding:80px 20px;text-align:center;color:#817b91}
button:focus-visible,input:focus-visible,svg:focus-visible{outline:2px solid #7152dc;outline-offset:3px}
@media(max-width:1100px){.statistics-workspace{grid-template-columns:minmax(0,1fr) 310px;gap:14px}.statistics-chart{padding:20px 16px}.chart-heading{align-items:flex-start;flex-direction:column}.statistics-overview{gap:16px;padding:20px}.overview-metric{padding-left:16px}}
@media(max-width:850px){.statistics-workspace{grid-template-columns:minmax(0,1fr)}.statistics-members{order:-1}.members-scroll{max-height:220px}.statistics-overview{grid-template-columns:repeat(2,minmax(0,1fr))}.overview-label{grid-column:1/-1;flex-direction:row;justify-content:space-between;align-items:center}.overview-metric{padding:0;border:0}.statistics-filters{align-items:flex-start;gap:12px}.period-control{align-items:flex-start;flex-direction:column;gap:8px}}
@media(max-width:500px){.operation-statistics{padding:20px 14px}.statistics-filters{flex-wrap:wrap}.period-options{gap:0;width:100%}.period-control{width:100%}.period-options button{flex:1;padding:8px 10px}.refresh-button{margin-left:auto}.statistics-overview{padding:16px;gap:14px}.overview-metric strong{font-size:26px}.overview-metric small{font-size:10px}.statistics-chart{padding:18px 12px}.chart-heading{gap:12px}.chart-tooltip{right:4px;max-width:calc(100% - 8px)}.chart-plot svg{height:320px}}
</style>
