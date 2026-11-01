<script setup lang="ts">
import { ref } from 'vue'
import TitleLibraryMarket from './TitleLibraryMarket.vue'
import { titleMarkets, type TitleSite } from './title-markets'

defineProps<{ token: string; user: any }>()
const site = ref<TitleSite>('MY')
</script>

<template>
  <section class="page title-library-shell">
    <label class="title-site-picker">词库站点<select v-model="site" aria-label="词库站点"><option v-for="market in titleMarkets" :key="market.site" :value="market.site">{{market.siteName}} · {{market.languageName}}</option></select></label>
    <TitleLibraryMarket :key="site" :site="site" :token="token" :user="user" />
  </section>
</template>

<style scoped>
.title-site-picker{display:flex;align-items:center;gap:12px;margin:0 0 16px;font-size:14px;white-space:nowrap}.title-site-picker select{width:auto;max-width:100%;padding:9px 12px;border:1px solid #e2dcf0;border-radius:8px;background:white;font:inherit;color:#302844}
</style>
