<script setup lang="ts" generic="T extends string | number | null">
import { computed } from 'vue'
import SearchableSelect from './SearchableSelect.vue'

const props = withDefaults(defineProps<{
  modelValue: T
  templates: { id: number | string; name: string }[]
  allLabel?: string
  stringValue?: boolean
  unmatched?: boolean
  disabled?: boolean
  required?: boolean
  ariaLabel?: string
}>(), { allLabel: '', stringValue: false, unmatched: false, disabled: false, required: false, ariaLabel: '产品模板' })
const emit = defineEmits<{ 'update:modelValue': [T]; change: [T] }>()
const options = computed(() => [
  ...(props.allLabel ? [{ value: props.stringValue ? '' : null, label: props.allLabel }] : []),
  ...(props.unmatched ? [{ value: 'unmatched', label: '未匹配' }] : []),
  ...props.templates.map(item => ({ value: props.stringValue ? String(item.id) : item.id, label: item.name })),
])
</script>

<template>
  <SearchableSelect class="template-select" :model-value="modelValue" :options="options"
    :disabled="disabled" :required="required" :aria-label="ariaLabel"
    placeholder="请选择产品模板" search-placeholder="搜索模板名称"
    empty-label="暂无可选模板" no-match-label="没有匹配的模板"
    @update:model-value="emit('update:modelValue', $event as T)" @change="emit('change', $event as T)"/>
</template>

<style scoped>
.template-select{position:relative;width:100%;min-width:0;max-width:100%;margin-top:7px;--template-primary:var(--admin-primary,#7054e7);--template-border:var(--admin-border,#e2dff0);--template-text:var(--admin-text,#25233a);--template-muted:var(--admin-muted,#9892a7);--template-soft:var(--admin-primary-soft,#f3efff)}
.template-select.is-open{z-index:30}
.template-select :deep(.search-select-trigger){display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;min-height:var(--admin-control-height,38px);margin:0;padding:9px 11px;border:1px solid var(--template-border);border-radius:8px;background:#fff;color:var(--template-text);font:inherit;font-size:13px;font-weight:600;text-align:left;cursor:pointer}
.template-select :deep(.search-select-trigger:focus-visible),.template-select.is-open :deep(.search-select-trigger){outline:none;border-color:var(--template-primary);box-shadow:0 0 0 3px color-mix(in srgb,var(--template-primary) 13%,transparent)}
.template-select :deep(.search-select-trigger:disabled){opacity:.6;cursor:not-allowed}
.template-select :deep(.search-select-value){min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.template-select :deep(.search-select-value.is-placeholder),.template-select :deep(.search-select-caret){color:var(--template-muted)}
.template-select :deep(.search-select-panel){position:absolute;z-index:30;top:calc(100% + 6px);left:0;right:0;min-width:0;padding:10px;border:1px solid var(--template-border);border-radius:12px;background:#fff;box-shadow:0 14px 36px #30295424}
.template-select :deep(.search-select-search input){display:block;box-sizing:border-box;width:100%;min-width:0;max-width:100%;height:auto;min-height:38px;margin:0;padding:9px 11px;border:1px solid var(--template-border);border-radius:8px;background:#fff;color:var(--template-text);font:inherit;font-size:13px}
.template-select :deep(.search-select-search input:focus){outline:none;border-color:var(--template-primary)}
.template-select :deep(.search-select-list){max-height:240px;margin:8px 0 0;padding:0;overflow:auto;list-style:none}
.template-select :deep(.search-select-option){padding:9px 10px;border-radius:8px;color:var(--template-text);font-size:13px;font-weight:400;line-height:1.5;cursor:pointer;overflow-wrap:anywhere}
.template-select :deep(.search-select-option.is-active){background:var(--template-soft)}
.template-select :deep(.search-select-option.is-selected){color:var(--template-primary);font-weight:700}
.template-select :deep(.search-select-hit){border-radius:3px;background:#fff3bf}
.template-select :deep(.search-select-empty){padding:12px 10px;color:var(--template-muted);font-size:12px;font-weight:400}
.template-select :deep(.search-select-footer){display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;margin-top:8px;color:var(--template-muted);font-size:11px;font-weight:400;line-height:1.4}
</style>
