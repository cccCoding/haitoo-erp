<script setup lang="ts">
defineProps<{ isInfringing: boolean }>()
</script>
<template>
  <span class="infringement-state" :class="isInfringing ? 'infringing' : 'non-infringing'">{{isInfringing ? '侵权' : '不侵权'}}</span>
</template>
