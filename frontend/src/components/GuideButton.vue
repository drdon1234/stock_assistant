<script setup>
import { NButton, NTooltip } from 'naive-ui'
import Icon from './Icon.vue'
import { guideOpen, toggleGuide } from './guide'

defineProps({ id: { type: String, required: true } })
</script>

<template>
  <NTooltip>
    <template #trigger>
      <NButton size="small" quaternary :type="guideOpen(id) ? 'primary' : 'default'" class="guide-btn"
               :aria-pressed="guideOpen(id)" @click="toggleGuide(id)">
        <template #icon><Icon name="help" :size="16" /></template>说明
      </NButton>
    </template>
    {{ guideOpen(id) ? '收起页面说明' : '查看这个页面怎么用' }}
  </NTooltip>
</template>

<style scoped>
.guide-btn { padding: 0 6px; }
</style>
