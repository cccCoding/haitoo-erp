<script setup lang="ts">
import { computed } from 'vue'
import SearchableSelect from './SearchableSelect.vue'
import { styleOptions, type MaterialStyle } from './material-styles'

const props = defineProps<{
  modelValue: number | null
  styles: MaterialStyle[]
  templateId: number | null
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()
const options = computed(() => [{value:null, label:'未分组'}, ...styleOptions(props.styles, props.templateId)])
</script>

<template>
  <SearchableSelect :model-value="modelValue" :options="options" :disabled="disabled || !templateId"
    :placeholder="templateId ? '选择风格' : '请先选择产品模板'" search-placeholder="搜索风格或创建人"
    empty-label="暂无可选风格" no-match-label="没有匹配的风格"
    @update:model-value="emit('update:modelValue', $event as number | null)"/>
</template>
