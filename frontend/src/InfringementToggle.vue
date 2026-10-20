<script setup lang="ts">
defineProps<{ modelValue: boolean; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>
<template>
  <button type="button" class="infringement-state infringement-toggle"
    :class="modelValue ? 'infringing' : 'non-infringing'" :disabled="disabled"
    :aria-pressed="modelValue" :aria-label="`是否侵权：${modelValue ? '侵权' : '不侵权'}`"
    :title="`点击设为${modelValue ? '不侵权' : '侵权'}`"
    @click.stop="emit('update:modelValue', !modelValue)">{{modelValue ? '侵权' : '不侵权'}}</button>
</template>
