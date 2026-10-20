<script setup lang="ts">
defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ set: [value: boolean] }>()
</script>
<template>
  <div class="infringement-actions">
    <button type="button" class="secondary" :disabled="disabled" @click="emit('set', true)">将已选设为侵权</button>
    <button type="button" class="secondary" :disabled="disabled" @click="emit('set', false)">将已选设为不侵权</button>
  </div>
</template>
<style scoped>
.infringement-actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.infringement-actions button{font-size:12px}
</style>
