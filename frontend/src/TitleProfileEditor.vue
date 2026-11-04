<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { SUPPLY_TITLE_MINIMUM, SUPPLY_TITLE_MAXIMUM } from './supply-title-rules'
import SearchableSelect from './SearchableSelect.vue'
import { titleMarket, titleMarketParams, type TitleSite } from './title-markets'
import { titleTagLabel } from './title-labels'
import { resolveConfirmedChoice, type LegacyAttribute } from './title-confirmed-choices'

const props = withDefaults(defineProps<{ token: string; templateId: number; platform?: string; site?: TitleSite; readonly?: boolean; showFallback?: boolean }>(), { showFallback: false, platform: 'TikTok', site: 'MY', readonly: false })
const emit = defineEmits<{ saved: []; busy: [value: boolean] }>()
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
const market = computed(() => titleMarket(props.site))
const config = computed(() => ({ headers: { Authorization: `Bearer ${props.token}` } }))
const form = ref<any>({ category: '', gender: '', age_group: '', fallback_title: '' })
const attributes = ref<{ tag: string; value: string }[]>([]), tags = ref<string[]>([])
const categories = ref<{ name: string; localized_name?: string | null; enabled: boolean }[]>([])
type MaterialOption = { id: number; phrase: string; translation: string; categories: string[] }
type KeywordOption = MaterialOption & { code: string; tag: string; semantic_tag: string; status: string }
const materialOptions = ref<MaterialOption[]>([])
const keywordOptions = ref<KeywordOption[]>([]), attributeKeywordOptions = ref<KeywordOption[]>([])
const materialIds = ref<number[]>([]), legacyMaterial = ref(''), materialConflict = ref(''), legacyAudience = ref('')
const confirmedChoices = ref<{ kind: 'craft' | 'brand'; tag: string; ids: number[]; warning: string }[]>([
  { kind: 'craft', tag: '工艺', ids: [], warning: '' },
  { kind: 'brand', tag: '品牌', ids: [], warning: '' },
])
const normalized = (value: string) => value.normalize('NFKC').trim().toLowerCase()
const availableMaterials = computed(() => materialOptions.value.filter(item => item.categories.some(category => normalized(category) === normalized(form.value.category))))
const unavailableMaterialIds = computed(() => materialIds.value.filter(id => !availableMaterials.value.some(item => item.id === id)))
const forbiddenIds = ref<number[]>([]), forbiddenError = ref('')
const busy = ref(false), loaded = ref(false), error = ref(''), notice = ref('')
const selectorDisabled = computed(() => busy.value || props.readonly || !loaded.value)
const inCategory = (item: MaterialOption) => item.categories.some(category => normalized(category) === normalized(form.value.category))
const confirmedWords = (tag: string) => attributeKeywordOptions.value.filter(item => item.semantic_tag === tag && inCategory(item) && !forbiddenIds.value.includes(item.id))
const confirmedOptions = (tag: string) => confirmedWords(tag).map(item => ({ value: item.id, label: keywordLabel(item) }))
const unavailableConfirmedIds = (item: {tag: string; ids: number[]}) => item.ids.filter(id => !confirmedWords(item.tag).some(word => word.id === id))
const keywordLabel = (item: MaterialOption) => `${item.translation} · ${item.phrase}`
const materialChoices = computed(() => availableMaterials.value.map(item => ({ value: item.id, label: keywordLabel(item) })))
const tagChoices = computed(() => tags.value.map(tag => ({ value: tag, label: titleTagLabel(tag) })))
const attributeWords = (tag: string) => attributeKeywordOptions.value.filter(item => item.tag === tag && inCategory(item))
const attributeChoices = (tag: string) => attributeWords(tag).map(item => ({ value: item.phrase, label: keywordLabel(item) }))
const matchedAttribute = (item: {tag: string; value: string}) => attributeWords(item.tag).some(word => word.phrase === item.value)
const forbiddenChoices = computed(() => keywordOptions.value.filter(item => inCategory(item) || forbiddenIds.value.includes(item.id))
  .map(item => ({ value: item.id, label: `${keywordLabel(item)} · ${titleTagLabel(item.tag)} · ${item.code}` })))
function forbiddenLabel(id: number) {
  const item = keywordOptions.value.find(item => item.id === id)
  return item ? keywordLabel(item) : `关键词 #${id}（已不可用）`
}
function materialLabel(id: number) {
  const item = keywordOptions.value.find(item => item.id === id)
  return item ? keywordLabel(item) : `关键词 #${id}（已不可用）`
}
function toggleMaterial(value: string | number | null) {
  if (selectorDisabled.value || typeof value !== 'number') return
  if (materialIds.value.includes(value)) materialIds.value = materialIds.value.filter(id => id !== value)
  else if (materialIds.value.length >= 100) { error.value = '最多选择 100 个面料关键词'; return }
  else materialIds.value = [...materialIds.value, value]
  legacyMaterial.value = ''; materialConflict.value = ''
}
function clearMaterials() { materialIds.value = []; legacyMaterial.value = ''; materialConflict.value = '' }
function toggleConfirmed(item: typeof confirmedChoices.value[number], value: string | number | null) {
  if (selectorDisabled.value || typeof value !== 'number') return
  if (item.ids.includes(value)) item.ids = item.ids.filter(id => id !== value)
  else if (item.ids.length >= 100) { error.value = `最多选择 100 个${item.tag}关键词`; return }
  else item.ids = [...item.ids, value]
  item.warning = ''
}
function clearConfirmed(item: typeof confirmedChoices.value[number]) {
  if (selectorDisabled.value) return
  item.ids = []; item.warning = ''
}
function toggleForbidden(value: string | number | null) {
  if (selectorDisabled.value || typeof value !== 'number') return
  forbiddenError.value = ''
  if (forbiddenIds.value.includes(value)) forbiddenIds.value = forbiddenIds.value.filter(id => id !== value)
  else if (forbiddenIds.value.length >= 200) forbiddenError.value = '最多选择 200 个禁用关键词'
  else forbiddenIds.value = [...forbiddenIds.value, value]
}
function selectForbiddenMatches(values: (string | number | null)[]) {
  if (selectorDisabled.value) return
  const ids = [...new Set([...forbiddenIds.value, ...values.filter((value): value is number => typeof value === 'number')])]
  if (ids.length > 200) { forbiddenError.value = `全选后共 ${ids.length} 个禁用关键词，超过 200 个上限，请缩小搜索范围或移除部分已选词`; return }
  forbiddenIds.value = ids
  forbiddenError.value = ''
}
function clearForbiddenMatches(values: (string | number | null)[]) {
  if (selectorDisabled.value) return
  const ids = new Set(values)
  forbiddenIds.value = forbiddenIds.value.filter(id => !ids.has(id))
  forbiddenError.value = ''
}
let revision = 0
watch(busy, value => emit('busy', value))
watch(() => [props.templateId, props.platform, props.site, props.token], async () => {
  const current = ++revision
  error.value = ''; notice.value = ''; busy.value = true; loaded.value = false
  forbiddenError.value = ''
  try {
    const { data } = await api.get(`/title-profiles/${props.templateId}`, { ...config.value, params: { platform: props.platform, ...titleMarketParams(props.site) } })
    if (current !== revision) return
    const definitions: { name: string; semantic_tag: string }[] = data.attribute_tags || []
    const semantic = (tag: string) => definitions.find(item => item.name === tag)?.semantic_tag || (tag === '面料' ? '材质' : tag)
    const legacyChoiceTags = new Set<string>(confirmedChoices.value.flatMap(item => (data[`${item.kind}_legacy_attributes`] || []).map((value: LegacyAttribute) => value.tag)))
    tags.value = (data.tags || []).filter((tag: string) => !['品类','性别','年龄','材质','面料','工艺','品牌'].includes(semantic(tag)))
    form.value = { ...data, gender: data.gender || '', age_group: data.age_group || '' }
    categories.value = data.category_options || (data.categories || []).map((name: string) => ({ name, enabled: true }))
    if (data.category && !categories.value.some(item => item.name === data.category)) categories.value.push({ name: data.category, enabled: false })
    const values = Object.entries(data.attributes || {}).map(([tag, value]) => ({ tag, value: String(value) }))
    attributes.value = values.filter(item => !['品类','性别','年龄','材质','工艺','品牌'].includes(semantic(item.tag)) && !legacyChoiceTags.has(item.tag))
    materialOptions.value = data.material_options || []
    keywordOptions.value = data.keyword_options || []
    attributeKeywordOptions.value = data.attribute_keyword_options || []
    forbiddenIds.value = [...new Set<number>(data.forbidden_keyword_ids || [])]
    for (const item of confirmedChoices.value) {
      const resolved = resolveConfirmedChoice(data[`${item.kind}_keyword_ids`] || [], data[`${item.kind}_legacy_attributes`] || [], confirmedWords(item.tag))
      item.ids = resolved.ids; item.warning = resolved.warning
    }
    for (const item of attributes.value) {
      item.value = attributeWords(item.tag).find(word => [word.phrase, word.translation].some(value => normalized(value) === normalized(item.value)))?.phrase || item.value
    }
    const savedMaterial = data.material || ''
    materialIds.value = [...new Set<number>(data.material_keyword_ids || [])]
    legacyMaterial.value = ''
    if (!materialIds.value.length && savedMaterial) {
      const matched = availableMaterials.value.find(item => [item.phrase, item.translation].some(value => normalized(value) === normalized(savedMaterial)))
      if (matched) materialIds.value = [matched.id]
      else legacyMaterial.value = savedMaterial
    }
    materialConflict.value = (data.conflicting_attributes || []).includes('材质') ? values.filter(item => semantic(item.tag) === '材质').map(item => `${item.tag==='材质'?'面料':item.tag}：${item.value}`).join('；') : ''
    legacyAudience.value = values.filter(item => ['性别','年龄'].includes(item.tag)).map(item => `${item.tag==='材质'?'面料':item.tag}：${item.value}`).join('；')
    forbiddenIds.value = [...new Set<number>(data.forbidden_keyword_ids || [])]
    loaded.value = true
  } catch (e: any) { if (current === revision) error.value = e.response?.data?.detail || '读取模板配置失败' }
  finally { if (current === revision) busy.value = false }
}, { immediate: true })
onUnmounted(() => { revision++; emit('busy', false) })
async function save() {
  if (props.readonly || busy.value || !loaded.value) return
  error.value = ''; notice.value = ''
  try {
    if (!form.value.category || !form.value.gender || !form.value.age_group) throw new Error('请选择产品分类、使用性别和年龄')
    if (materialConflict.value && !materialIds.value.length) throw new Error('请选择确认后的面料关键词，或明确清除未确认面料')
    if (legacyMaterial.value || unavailableMaterialIds.value.length) throw new Error('请选择当前产品分类下已启用的面料关键词，或清除不可用面料')
    if (materialIds.value.some(id => forbiddenIds.value.includes(id))) throw new Error('所选面料关键词不能同时禁用')
    for (const item of confirmedChoices.value) {
      if (item.warning || unavailableConfirmedIds(item).length) throw new Error(`请选择当前产品分类下已启用且未禁用的${item.tag}关键词，或清空${item.tag}选择`)
    }
    const confirmed: Record<string, string> = {}
    for (const item of attributes.value) {
      if (!item.tag || !item.value.trim()) throw new Error('请选择每项标签及对应关键词')
      if (!tags.value.includes(item.tag) || !matchedAttribute(item)) throw new Error('请选择当前产品分类下已启用的标签关键词，或删除未确认的标签')
      if (item.tag in confirmed) throw new Error('同一标签只能选择一次')
      confirmed[item.tag] = item.value.trim()
    }
    const fallback = form.value.fallback_title?.trim() || ''
    if (fallback && (Array.from(fallback).length < SUPPLY_TITLE_MINIMUM || Array.from(fallback).length > SUPPLY_TITLE_MAXIMUM)) throw new Error('请填写 25–230 个字符的货盘兜底标题')
    const payload = { platform: props.platform, ...titleMarketParams(props.site), category: form.value.category,
      gender: form.value.gender, age_group: form.value.age_group, attributes: confirmed,
      material_keyword_ids: materialIds.value,
      craft_keyword_ids: confirmedChoices.value.find(item => item.kind === 'craft')!.ids,
      brand_keyword_ids: confirmedChoices.value.find(item => item.kind === 'brand')!.ids,
      category_names: [], locked_keyword_ids: [], forbidden_keyword_ids: forbiddenIds.value,
      fallback_title: form.value.fallback_title?.trim() || null }
    busy.value = true
    await api.put(`/title-profiles/${props.templateId}`, payload, config.value)
    notice.value = '模板词库配置已保存'; emit('saved')
  } catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || '保存失败' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="title-profile-editor">
    <p>{{market.siteName}} · {{market.languageName}}。产品分类、性别和年龄用于词库匹配；工艺、品牌和面料须人工确认，未填写时 AI 不推断。请选择符合商品事实的已导入关键词。</p>
    <p v-if="legacyAudience" class="profile-warning">旧配置：{{legacyAudience}}。请按下方标准选项重新确认。</p>
    <form @submit.prevent="save">
      <fieldset :disabled="busy || readonly || !loaded">
        <div class="profile-basic-grid">
          <label class="profile-category">产品分类 <span class="profile-required">必填</span><select v-model="form.category" required><option value="" disabled>请选择产品分类</option><option v-for="category in categories" :key="category.name" :value="category.name" :disabled="!category.enabled">{{category.name}}{{category.localized_name?` · ${category.localized_name}`:''}}{{category.enabled?'':'（已停用或不存在）'}}</option></select></label>
          <label>使用性别 <span class="profile-required">必填</span><select v-model="form.gender" required><option value="" disabled>请选择使用性别</option><option v-for="gender in ['男','女','中性']" :key="gender" :value="gender">{{gender}}</option></select></label>
          <label>年龄 <span class="profile-required">必填</span><select v-model="form.age_group" required><option value="" disabled>请选择年龄</option><option v-for="age in ['成人','儿童']" :key="age" :value="age">{{age}}</option></select></label>
        </div>
        <div class="profile-select-field"><span>面料（选填，可多选）</span>
          <SearchableSelect :model-value="null" :multiple="true" :selected-values="materialIds" :options="materialChoices" :disabled="selectorDisabled" aria-label="面料" placeholder="未确认面料（留空）" search-placeholder="搜索面料关键词或中文释义" empty-label="暂无可选面料" no-match-label="没有匹配的面料关键词" @toggle="toggleMaterial" />
          <div v-if="materialIds.length" class="profile-keyword-chips" aria-label="已选面料关键词"><span v-for="id in materialIds" :key="id">{{materialLabel(id)}}{{unavailableMaterialIds.includes(id)?'（当前不可用）':''}}<button v-if="!readonly" type="button" :disabled="selectorDisabled" :aria-label="`移除面料关键词 ${materialLabel(id)}`" @click="toggleMaterial(id)">×</button></span></div>
          <small>可选择多个符合商品事实的面料关键词；每条标题随机使用其中一个。未确认请留空。</small>
          <button v-if="!readonly&&(materialIds.length||legacyMaterial||materialConflict)" type="button" class="ghost" :disabled="selectorDisabled" @click="clearMaterials">清空面料选择</button>
          <small v-if="loaded&&!availableMaterials.length">暂无可选面料，请先导入适用于本产品分类的面料关键词并启用。</small>
        </div>
        <p v-if="legacyMaterial" class="profile-warning">原面料“{{legacyMaterial}}”未匹配可选关键词，请重新选择或清空面料选择。</p>
        <p v-if="unavailableMaterialIds.length" class="profile-warning">部分已选面料已停用或不适用当前产品分类，请移除后重新选择。</p>
        <div v-if="materialConflict" class="profile-warning">旧面料配置有冲突：{{materialConflict}}。请选择确认后的面料关键词，或清空面料选择。</div>
        <div v-for="item in confirmedChoices" :key="item.kind" class="profile-select-field">
          <span>{{item.tag}}（选填，可多选）</span>
          <SearchableSelect :model-value="null" :multiple="true" :selected-values="item.ids" :options="confirmedOptions(item.tag)" :disabled="selectorDisabled" :aria-label="item.tag" :placeholder="`未确认${item.tag}（留空）`" :search-placeholder="`搜索${item.tag}关键词或中文释义`" :empty-label="`暂无可选${item.tag}`" :no-match-label="`没有匹配的${item.tag}关键词`" @toggle="toggleConfirmed(item, $event)" />
          <div v-if="item.ids.length" class="profile-keyword-chips" :aria-label="`已选${item.tag}关键词`"><span v-for="id in item.ids" :key="id">{{forbiddenLabel(id)}}{{unavailableConfirmedIds(item).includes(id)?'（当前不可用）':''}}<button v-if="!readonly" type="button" :disabled="selectorDisabled" :aria-label="`移除${item.tag}关键词 ${forbiddenLabel(id)}`" @click="toggleConfirmed(item, id)">×</button></span></div>
          <small>可选择多个符合商品事实的{{item.tag}}关键词；每条标题随机使用其中一个。未确认请留空。</small>
          <button v-if="!readonly&&(item.ids.length||item.warning)" type="button" class="ghost" :disabled="selectorDisabled" @click="clearConfirmed(item)">清空{{item.tag}}选择</button>
          <small v-if="loaded&&!confirmedWords(item.tag).length">暂无可选{{item.tag}}，请先导入适用于本产品分类的{{item.tag}}关键词并启用。</small>
          <p v-if="item.warning" class="profile-warning">旧{{item.tag}}配置未匹配可用关键词或存在冲突：{{item.warning}}。请重新选择或清空{{item.tag}}选择。</p>
          <p v-if="unavailableConfirmedIds(item).length" class="profile-warning">部分已选{{item.tag}}已停用、被禁用或不适用当前产品分类，请移除后重新选择。</p>
        </div>
        <div class="profile-attribute-heading"><strong>其他标签</strong><button v-if="!readonly" type="button" class="secondary" @click="attributes.push({tag:'',value:''})">添加标签</button></div>
        <div v-for="(item, index) in attributes" :key="index" class="profile-attribute-item">
          <div class="title-attribute-row">
            <SearchableSelect class="profile-attribute-tag" :model-value="item.tag" :options="tagChoices" :disabled="selectorDisabled" :aria-label="`标签 ${index+1}`" :placeholder="item.tag?`${titleTagLabel(item.tag)}（已停用或不存在）`:'选择标签'" search-placeholder="搜索标签名称" empty-label="暂无已启用的其他标签" no-match-label="没有匹配的标签" @update:model-value="item.tag=String($event??'');item.value=''" />
            <SearchableSelect class="profile-attribute-value" :model-value="item.value" :options="attributeChoices(item.tag)" :disabled="selectorDisabled||!item.tag" :aria-label="`标签关键词 ${index+1}`" :placeholder="item.value?`${item.value}（未匹配可选关键词）`:'选择已导入关键词'" search-placeholder="搜索标签关键词或中文释义" empty-label="本分类下暂无可选关键词，请先导入并启用" no-match-label="没有匹配的标签关键词" @update:model-value="item.value=String($event??'')" />
            <button v-if="!readonly" type="button" class="ghost" :aria-label="`删除标签 ${index+1}`" @click="attributes.splice(index,1)">删除</button>
          </div>
          <small v-if="item.value&&!matchedAttribute(item)" class="profile-warning">原值“{{item.value}}”未匹配可选关键词，请重新选择或删除本标签。</small>
        </div>
        <p v-if="!attributes.length" class="profile-empty">尚未设置其他标签。</p>
        <div class="profile-select-field"><span>禁用关键词（选填，可多选）</span>
          <SearchableSelect :model-value="null" :multiple="true" :bulk-selection="true" :selection-error="forbiddenError" :selected-values="forbiddenIds" :options="forbiddenChoices" :disabled="selectorDisabled" aria-label="禁用关键词" placeholder="选择禁用关键词" search-placeholder="搜索禁用关键词、中文释义、标签或编码" empty-label="本分类下暂无关键词" no-match-label="没有匹配的关键词" @toggle="toggleForbidden" @select-matched="selectForbiddenMatches" @clear-matched="clearForbiddenMatches" />
          <div v-if="forbiddenIds.length" class="profile-keyword-chips" aria-label="已选禁用关键词"><span v-for="id in forbiddenIds" :key="id">{{forbiddenLabel(id)}}<button v-if="!readonly" type="button" :disabled="selectorDisabled" :aria-label="`移除禁用关键词 ${forbiddenLabel(id)}`" @click="toggleForbidden(id)">×</button></span></div>
          <small>选中的关键词不会出现在本模板的词库标题中，最多选择 200 个。</small>
        </div>
        <label v-if="showFallback">{{market.languageName}}货盘兜底标题<textarea v-model="form.fallback_title" rows="2" :minlength="SUPPLY_TITLE_MINIMUM" :maxlength="SUPPLY_TITLE_MAXIMUM" /></label>
        <small v-if="showFallback">保存后即可用于货盘生成失败时兜底；未设置时使用公开货盘中配置的兜底标题。</small>
        <button v-if="!readonly" type="submit" class="primary profile-save">{{busy?'保存中…':'保存模板配置'}}</button>
      </fieldset>
    </form>
    <p v-if="busy&&!loaded" role="status">正在读取模板配置…</p>
    <p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
  </section>
</template>

<style scoped>
.title-profile-editor{display:grid;gap:12px;min-width:0}.title-profile-editor p{margin:0;color:#716b80;font-size:13px;line-height:1.7}.title-profile-editor fieldset{border:0;padding:0;display:grid;gap:18px;min-width:0}.title-profile-editor label{display:flex;flex-wrap:wrap;align-items:center;gap:7px;font-size:14px}.title-profile-editor input:not([type=checkbox]),.title-profile-editor select,.title-profile-editor textarea{box-sizing:border-box;width:100%;min-width:0;border:1px solid #e2dcf0;border-radius:9px;padding:10px 12px;font:inherit;background:white;color:#302844}.profile-basic-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.profile-category{grid-column:1/-1}.profile-required{font-size:11px;color:#8b7da5;font-weight:400}.title-profile-editor small{color:#81788d;font-size:12px;line-height:1.6}.profile-attribute-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.profile-attribute-heading strong{font-size:14px}.title-attribute-row{display:flex;gap:8px;align-items:center}.profile-select-field{display:grid;gap:7px;min-width:0;font-size:14px}.profile-select-field>.search-select,.title-attribute-row>.search-select{margin-top:0}.profile-attribute-item{display:grid;gap:7px}.title-attribute-row>.profile-attribute-tag{flex:0 0 160px;min-width:0}.title-attribute-row>.profile-attribute-value{flex:1;min-width:0}.title-attribute-row>button{flex:none}.profile-keyword-chips{display:flex;flex-wrap:wrap;gap:7px}.profile-keyword-chips>span{display:inline-flex;align-items:center;gap:7px;padding:5px 9px;background:#f2effb;border-radius:7px;color:#6047a4;font-size:12px;overflow-wrap:anywhere}.profile-keyword-chips button{border:0;background:transparent;color:inherit;padding:0 2px;font-size:18px;line-height:1;cursor:pointer}.title-profile-editor .profile-warning{padding:10px 12px;border-radius:8px;background:#fff6e6;color:#86631d;font-size:13px;line-height:1.7}.title-profile-editor .profile-empty{font-size:12px}.title-profile-editor details{padding:12px;background:#f8f7fb;border-radius:8px}.title-profile-editor details label{margin-top:12px}.profile-save{justify-self:end}.title-profile-editor .title-checkbox{display:flex;align-items:center}.title-checkbox input{width:auto;accent-color:#6744d5}@media(max-width:600px){.profile-basic-grid{grid-template-columns:minmax(0,1fr)}.title-attribute-row{flex-wrap:wrap}.title-attribute-row>.profile-attribute-tag{flex:1 1 100%}.title-attribute-row>.profile-attribute-value{flex:1 1 calc(100% - 55px)}}
</style>
