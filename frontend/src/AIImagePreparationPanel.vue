<script setup lang="ts">
import { computed } from 'vue'
import type { AIPreparation } from './ai-image-preparation'

const props = defineProps<{ progress: AIPreparation | null; busy?: boolean; submitting?: boolean; error?: string; continueReview?: boolean }>()
defineEmits<{ retry: []; adjust: []; background: [] }>()
const failures = computed(() => props.progress?.items.filter(item => ['failed', 'invalid', 'expired'].includes(item.state)) || [])
const retryable = computed(() => failures.value.some(item => item.state === 'failed'))
const completed = computed(() => (props.progress?.ready || 0) + (props.progress?.failed || 0))
const title = computed(() => props.submitting ? '正在提交审核' : props.busy ? '正在永久保存图片' : failures.value.length || props.error ? '部分图片尚未保存' : '图片已永久保存')
</script>

<template>
  <section class="image-preparation-panel" :class="{ 'has-error': failures.length || error }" aria-label="图片永久保存进度" :aria-busy="!!busy || !!submitting">
    <div class="image-preparation-heading" role="status" aria-live="polite">
      <div><strong>{{title}}</strong><p>{{submitting ? '图片已保存，正在提交审核结果。' : busy ? continueReview ? '保存完成后将继续审核，请稍候。' : '保存完成后，请返回此处确认审核。' : failures.length || error ? '审核尚未提交，已保存的图片会保留。' : '请确认审核，完成后图片才会正式采用。'}}</p></div>
      <span v-if="progress" class="image-preparation-count"><small>已处理 </small>{{completed}}<small> / {{progress.total}}</small></span>
    </div>
    <progress v-if="progress" :value="completed" :max="progress.total || 1" aria-label="已处理图片数量"></progress>
    <div v-if="progress" class="image-preparation-stats"><span>已保存 <b>{{progress.ready}}</b> 张</span><span v-if="progress.failed" class="error">未成功 <b>{{progress.failed}}</b> 张</span><span v-if="completed < progress.total">待处理 <b>{{progress.total - completed}}</b> 张</span></div>
    <p v-if="error" class="image-preparation-error" role="alert">{{error}}</p>
    <details v-if="failures.length" class="image-preparation-failures"><summary>查看 {{failures.length}} 张未成功图片</summary><ul><li v-for="item in failures" :key="item.candidate_id"><b>图片 #{{item.candidate_id}}</b><span>{{item.error || (item.state==='expired' ? '图片已过期，请重新选择' : '保存失败，请重试')}}</span></li></ul></details>
    <div v-if="!submitting" class="image-preparation-actions">
      <template v-if="!busy && (failures.length || error)"><button v-if="retryable" type="button" class="primary" @click="$emit('retry')">重试失败图片</button><button type="button" class="ghost" @click="$emit('adjust')">返回调整选择</button></template>
      <button v-if="busy" type="button" class="ghost" @click="$emit('background')">后台继续</button>
    </div>
  </section>
</template>
