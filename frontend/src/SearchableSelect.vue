<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type OptionValue = string | number | null

const props = withDefaults(defineProps<{
  modelValue: OptionValue
  options: any[]
  valueKey?: string
  labelKey?: string
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  maxVisible?: number
}>(), {
  valueKey: 'value',
  labelKey: 'label',
  placeholder: '请选择',
  searchPlaceholder: '输入关键词搜索',
  disabled: false,
  maxVisible: 200,
})

const emit = defineEmits<{ 'update:modelValue': [OptionValue]; change: [OptionValue] }>()

const root = ref<HTMLElement | null>(null)
const listbox = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const open = ref(false)
const keyword = ref('')
const activeIndex = ref(0)

const normalizedOptions = computed(() => (props.options || []).map(option => ({
  value: (option?.[props.valueKey] ?? null) as OptionValue,
  label: String(option?.[props.labelKey] ?? ''),
})))

const selectedLabel = computed(() => normalizedOptions.value.find(option => option.value === props.modelValue)?.label || '')

const keywordTerms = computed(() => keyword.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean))

const matchedOptions = computed(() => {
  if (!keywordTerms.value.length) return normalizedOptions.value
  return normalizedOptions.value.filter(option => {
    const haystack = option.label.toLocaleLowerCase()
    return keywordTerms.value.every(term => haystack.includes(term))
  })
})

const visibleOptions = computed(() => matchedOptions.value.slice(0, props.maxVisible))
const hiddenCount = computed(() => matchedOptions.value.length - visibleOptions.value.length)

watch(() => props.options, () => {
  keyword.value = ''
  activeIndex.value = 0
})

watch(matchedOptions, () => {
  if (activeIndex.value >= visibleOptions.value.length) activeIndex.value = Math.max(0, visibleOptions.value.length - 1)
})

function highlightSegments(label: string) {
  const terms = keywordTerms.value
  if (!terms.length) return [{ text: label, match: false }]
  const haystack = label.toLocaleLowerCase()
  const flags = new Array<boolean>(label.length).fill(false)
  for (const term of terms) {
    let from = 0
    while (term) {
      const index = haystack.indexOf(term, from)
      if (index < 0) break
      for (let cursor = index; cursor < index + term.length; cursor += 1) flags[cursor] = true
      from = index + term.length
    }
  }
  const segments: { text: string; match: boolean }[] = []
  for (let index = 0; index < label.length; index += 1) {
    const last = segments[segments.length - 1]
    if (last && last.match === flags[index]) last.text += label[index]
    else segments.push({ text: label[index], match: flags[index] })
  }
  return segments
}

function indexOfSelected() {
  const index = matchedOptions.value.findIndex(option => option.value === props.modelValue)
  return index < 0 ? 0 : Math.min(index, props.maxVisible - 1)
}

async function openPanel() {
  if (props.disabled) return
  keyword.value = ''
  activeIndex.value = indexOfSelected()
  open.value = true
  await nextTick()
  searchInput.value?.focus()
  scrollActiveIntoView()
}

function closePanel() {
  open.value = false
  keyword.value = ''
}

function togglePanel() {
  if (open.value) closePanel()
  else void openPanel()
}

function selectOption(value: OptionValue) {
  emit('update:modelValue', value)
  emit('change', value)
  closePanel()
}

function scrollActiveIntoView() {
  void nextTick(() => {
    const element = listbox.value?.children[activeIndex.value] as HTMLElement | undefined
    element?.scrollIntoView({ block: 'nearest' })
  })
}

function moveActive(step: number) {
  if (!visibleOptions.value.length) return
  const total = visibleOptions.value.length
  activeIndex.value = (activeIndex.value + step + total) % total
  scrollActiveIntoView()
}

function onSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') { event.preventDefault(); moveActive(1); return }
  if (event.key === 'ArrowUp') { event.preventDefault(); moveActive(-1); return }
  if (event.key === 'Enter') {
    event.preventDefault()
    const option = visibleOptions.value[activeIndex.value]
    if (option) selectOption(option.value)
    return
  }
  if (event.key === 'Escape') { event.preventDefault(); closePanel() }
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    void openPanel()
  }
}

function onDocumentPointerDown(event: MouseEvent) {
  if (!open.value) return
  if (!root.value?.contains(event.target as Node)) closePanel()
}

onMounted(() => document.addEventListener('mousedown', onDocumentPointerDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocumentPointerDown))
</script>

<template>
  <div ref="root" class="search-select" :class="{ 'is-open': open, 'is-disabled': disabled }">
    <button
      type="button"
      class="search-select-trigger"
      :disabled="disabled"
      @click="togglePanel"
      @keydown="onTriggerKeydown"
    >
      <span class="search-select-value" :class="{ 'is-placeholder': !selectedLabel }">{{ selectedLabel || placeholder }}</span>
      <span class="search-select-caret" aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="search-select-panel">
      <div class="search-select-search">
        <input
          ref="searchInput"
          v-model="keyword"
          type="text"
          :placeholder="searchPlaceholder"
          @keydown="onSearchKeydown"
        />
      </div>
      <ul ref="listbox" class="search-select-list" role="listbox">
        <li
          v-for="(option, index) in visibleOptions"
          :key="String(option.value)"
          class="search-select-option"
          :class="{ 'is-active': index === activeIndex, 'is-selected': option.value === modelValue }"
          role="option"
          :aria-selected="option.value === modelValue"
          @mouseenter="activeIndex = index"
          @mousedown.prevent
          @click="selectOption(option.value)"
        >
          <span
            v-for="(segment, segmentIndex) in highlightSegments(option.label)"
            :key="segmentIndex"
            :class="{ 'search-select-hit': segment.match }"
          >{{ segment.text }}</span>
        </li>
        <li v-if="!visibleOptions.length" class="search-select-empty">{{ keyword.trim() ? '没有匹配的类目' : '暂无可选类目' }}</li>
      </ul>
      <div class="search-select-footer">
        <span>匹配 {{ matchedOptions.length }} / 共 {{ normalizedOptions.length }} 项</span>
        <span v-if="hiddenCount > 0">仅显示前 {{ visibleOptions.length }} 项，请继续输入关键词</span>
      </div>
    </div>
  </div>
</template>
