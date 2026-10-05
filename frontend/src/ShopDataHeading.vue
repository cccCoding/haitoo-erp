<script setup lang="ts">
import { ref } from 'vue'

const dialog = ref<HTMLDialogElement | null>(null)
</script>

<template>
  <span class="shop-data-heading">
    店铺数据
    <button type="button" class="shop-data-info" aria-label="查看店铺数据格式说明" aria-haspopup="dialog" @click="dialog?.showModal()">
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.5" stroke="currentColor" stroke-width="1.5"/><path d="M10 9v5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="10" cy="6" r="1" fill="currentColor"/></svg>
    </button>
  </span>
  <Teleport to="body">
    <dialog ref="dialog" class="shop-data-help" aria-label="店铺数据格式说明" @click.self="dialog?.close()">
      <section>
        <button type="button" class="shop-data-help-close" aria-label="关闭店铺数据格式说明" autofocus @click="dialog?.close()">×</button>
        <h2>店铺数据格式</h2>
        <p class="shop-data-format">店铺名称-产品ID-销量</p>
        <p>每个店铺与产品 ID 独立展示一行。</p>
        <p>例如：示例店铺-123456-80，表示该店铺的产品 123456 在当前统计范围内销量为 80 件。</p>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.shop-data-heading{display:flex;align-items:center;gap:6px}
.shop-data-info{display:grid;place-items:center;flex:none;width:24px;height:24px;margin:0;padding:2px;border:0;border-radius:50%;background:transparent;color:#858092;cursor:pointer}
.shop-data-info:hover{background:#eeeaff;color:#6043d4}
.shop-data-info:focus-visible{outline:2px solid #6043d4;outline-offset:2px}
.shop-data-info svg{width:18px;height:18px}
.shop-data-help{width:min(420px,calc(100vw - 32px));max-height:calc(100vh - 32px);margin:auto;padding:0;border:0;border-radius:16px;background:#fff;color:#25233a;box-shadow:0 20px 60px #25233a33;overflow:auto}
.shop-data-help::backdrop{background:#16132966}
.shop-data-help section{position:relative;padding:28px}
.shop-data-help h2{margin:0 28px 18px 0;font-size:18px}
.shop-data-help p{margin:12px 0 0;font-size:14px;line-height:1.7;color:#6d687c}
.shop-data-help .shop-data-format{padding:10px 12px;border-radius:8px;background:#f5f2ff;color:#6043d4;font-weight:600}
.shop-data-help-close{position:absolute;top:14px;right:14px;width:28px;height:28px;margin:0;padding:0;border:0;border-radius:8px;background:transparent;color:#858092;font-size:24px;line-height:1;cursor:pointer}
.shop-data-help-close:hover{background:#eeeaff;color:#6043d4}
</style>
