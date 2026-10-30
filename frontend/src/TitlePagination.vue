<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ page: number; pageSize: number; total: number; disabled?: boolean; label: string }>()
const emit = defineEmits<{ page: [value: number]; pageSize: [value: number] }>()
const sizes = [20, 50, 100, 500, 1000]
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
</script>

<template>
  <footer class="draft-pagination library-pagination" :aria-label="`${label}分页`">
    <span>共 {{total}} 条</span>
    <label>每页 <select :value="pageSize" :aria-label="`${label}每页条数`" :disabled="disabled" @change="emit('pageSize',Number(($event.target as HTMLSelectElement).value))"><option v-for="size in sizes" :key="size" :value="size">{{size}}</option></select> 条</label>
    <button type="button" :disabled="disabled||page<=1" @click="emit('page',page-1)">上一页</button>
    <span>第 {{page}} / {{pages}} 页</span>
    <button type="button" :disabled="disabled||page>=pages" @click="emit('page',page+1)">下一页</button>
  </footer>
</template>

<style scoped>
.library-pagination{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:0;flex-wrap:wrap;min-width:0}.library-pagination label{width:auto;display:flex;margin:0;line-height:1.5;align-items:center;gap:6px}.library-pagination>span{white-space:nowrap;line-height:1.5}.library-pagination select{box-sizing:border-box;display:inline-block;width:auto;min-width:76px;margin:0;padding:6px 26px 6px 9px;border:1px solid #e2dcf0;border-radius:7px;font:inherit;background:white;color:#302844}@media(max-width:700px){.library-pagination{justify-content:flex-start;gap:10px}}
</style>
