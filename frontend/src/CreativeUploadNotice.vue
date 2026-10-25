<script setup lang="ts">
import type { CreativeSubmissionNotice } from './creative-upload'
defineProps<{ notice: CreativeSubmissionNotice | null }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <section v-if="notice" class="creative-upload-notice" aria-label="印花素材处理结果">
    <div class="notice-heading">
      <p role="status">{{ notice.message }}</p>
      <button type="button" aria-label="关闭素材处理提示" @click="$emit('close')">关闭</button>
    </div>
    <details v-if="notice.skipped.length">
      <summary>查看已跳过的 {{ notice.skipped.length }} 张损坏图片</summary>
      <ul><li v-for="item in notice.skipped" :key="item.id"><strong>{{ item.name }}</strong><span>{{ item.reason }}</span></li></ul>
    </details>
  </section>
</template>

<style scoped>
.creative-upload-notice{margin:0 0 18px;padding:14px 16px;border:1px solid #e2d8b4;border-radius:12px;background:#fffbee;color:#665120;font-size:13px;line-height:1.6}
.notice-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.notice-heading p{margin:0;overflow-wrap:anywhere}
.notice-heading button{flex-shrink:0;border:0;background:transparent;color:inherit;cursor:pointer;font:inherit}
summary{cursor:pointer;margin-top:8px}
ul{margin:8px 0;padding-left:20px;max-height:240px;overflow:auto}
li{padding:3px 0;overflow-wrap:anywhere}
li strong{margin-right:10px}
li span,small{color:#75643c}
</style>
