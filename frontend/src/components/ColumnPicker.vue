<script setup>
import { computed, ref } from 'vue'
import { NButton, NInput, NPopover, NTree } from 'naive-ui'
import Icon from './Icon.vue'
import { isMobile } from '../store'

// 列设置：按组或按列勾选要显示的列
const props = defineProps({
  groups: { type: Array, required: true },
  columns: { type: Object, required: true }, // useColumnVisibility 的返回值
})
const keyword = ref('')

const treeData = computed(() => {
  const nodes = []
  for (const g of props.groups) {
    const children = g.cols.map((c) => ({ key: c.name, label: c.label }))
    if (g.title) nodes.push({ key: `group:${g.title}`, label: `${g.title}（${children.length}）`, children })
    else nodes.push(...children)
  }
  return nodes
})
const checked = computed(() => [...props.columns.visible.value])
const filter = (pattern, node) => node.label.toLowerCase().includes(pattern.toLowerCase())

function update(keys) {
  props.columns.setVisible(keys.filter((k) => !k.startsWith('group:')))
}
</script>

<template>
  <NPopover trigger="click" :placement="isMobile ? 'bottom' : 'bottom-end'" :style="{ padding: 0 }" scrollable>
    <template #trigger>
      <NButton size="small">
        <template #icon><Icon name="columns" :size="15" /></template>
        列设置<span class="count">{{ columns.visible.value.size }}/{{ columns.total.value }}</span>
      </NButton>
    </template>
    <div class="picker">
      <div class="head">
        <NInput v-model:value="keyword" size="small" clearable placeholder="搜索列名" />
        <NButton size="small" quaternary :disabled="columns.isDefault.value" @click="columns.reset()">恢复默认</NButton>
        <NButton size="small" quaternary @click="columns.showAll()">全部</NButton>
      </div>
      <NTree class="tree" :data="treeData" checkable cascade block-line expand-on-click :pattern="keyword"
             :filter="filter" :show-irrelevant-nodes="false" :checked-keys="checked"
             :default-expanded-keys="[]" virtual-scroll @update:checked-keys="update" />
      <p class="muted tip">勾选整组或单列；设置保存在本机浏览器。导出 CSV 时只导出显示的列。</p>
    </div>
  </NPopover>
</template>

<style scoped>
.count { margin-left: 4px; color: var(--muted); font-size: 12px; }
.picker { width: 300px; max-width: calc(100vw - 32px); }
.head { display: flex; gap: 4px; padding: 10px 10px 6px; }
.tree { height: 360px; max-height: 55vh; padding: 0 6px; }
.tip { margin: 0; padding: 6px 12px 10px; font-size: 12px; border-top: 1px solid var(--border); }
</style>
