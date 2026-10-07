<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { NButton } from 'naive-ui'
import Icon from './Icon.vue'
import { PAGE_GUIDES } from '../help/pages'
import { guideOpen, toggleGuide } from './guide'

// 页面说明：首次进入时展开，关闭后记住；工具栏中的“说明”按钮可再次打开（GuideButton）
const props = defineProps({ id: { type: String, required: true } })
const guide = computed(() => PAGE_GUIDES[props.id])
const open = computed(() => guide.value && guideOpen(props.id))
</script>

<template>
  <div v-if="open" class="card guide" role="note">
    <div class="head">
      <Icon name="help" :size="16" class="icon" />
      <p class="summary">{{ guide.summary }}</p>
      <NButton quaternary circle size="tiny" class="close" aria-label="收起页面说明" @click="toggleGuide(id)">
        <Icon name="close" :size="14" />
      </NButton>
    </div>
    <ul v-if="guide.points?.length">
      <li v-for="p in guide.points" :key="p">{{ p }}</li>
    </ul>
    <div class="foot">
      <RouterLink v-if="guide.learn" :to="{ path: '/learn', hash: `#${guide.learn}` }">在学习中心了解更多 →</RouterLink>
      <span class="muted">收起后可点击标题旁的“说明”再次打开</span>
    </div>
  </div>
</template>

<style scoped>
.guide { padding: 12px 16px; border-left: 3px solid var(--primary); font-size: 13px; line-height: 1.7; }
.head { display: flex; align-items: flex-start; gap: 8px; }
.icon { color: var(--primary); margin-top: 3px; flex: none; }
.summary { margin: 0; flex: 1; }
.close { margin: -2px -6px 0 0; }
ul { margin: 6px 0 0; padding-left: 42px; color: var(--muted); }
.foot { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 6px 0 0 24px; font-size: 12px; }
@media (max-width: 767px) {
  ul { padding-left: 20px; }
  .foot { margin-left: 0; }
  .foot .muted { display: none; }
}
</style>
