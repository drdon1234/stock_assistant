<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NDatePicker, NInput, NSpin, NSwitch, useMessage } from 'naive-ui'
import DataGrid from '../components/DataGrid.vue'
import Icon from '../components/Icon.vue'
import { api } from '../api'

const route = useRoute()
const message = useMessage()
const data = ref(null)
const loading = ref(false)
const date = ref(null)
const keyword = ref('')
const onlyAttention = ref(false)
const count = ref({ shown: 0, total: 0 })
const grid = ref(null)

const dateSet = computed(() => new Set(data.value?.dates || []))
const hasCode = computed(() => data.value?.columns.some((c) => c.name === 'code'))

function toDateString(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function load(day) {
  loading.value = true
  try {
    data.value = await api.table(route.params.name, day)
    date.value = data.value.date
    document.title = `${data.value.label} · InStock`
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

watch(date, (value, old) => {
  if (old && value && value !== data.value?.date) load(value)
})

load()
</script>

<template>
  <div class="page page-fill table-page">
    <div class="toolbar">
      <h1>{{ data?.label || '数据' }}</h1>
      <NDatePicker v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small"
                   :is-date-disabled="(ts) => !dateSet.has(toDateString(ts))" :disabled="!data?.dates.length"
                   style="width: 140px" placeholder="暂无数据" />
      <NInput v-model:value="keyword" size="small" clearable placeholder="筛选代码/名称/任意内容" class="filter">
        <template #prefix><Icon name="search" :size="15" /></template>
      </NInput>
      <label v-if="hasCode" class="switch"><NSwitch v-model:value="onlyAttention" size="small" /> 只看关注</label>
      <span class="spacer" />
      <span class="muted count">{{ count.shown }} / {{ count.total }} 条</span>
      <NButton size="small" @click="grid?.resetFilters()">重置筛选</NButton>
      <NButton size="small" @click="grid?.exportCsv(`${data?.label}_${date}`)">
        <template #icon><Icon name="download" :size="15" /></template>导出
      </NButton>
    </div>
    <NSpin :show="loading" class="grid-wrap card">
      <DataGrid v-if="data" ref="grid" :columns="data.columns" :rows="data.rows" :sort="data.sort"
                :quick-filter="keyword" :only-attention="onlyAttention" @count="count = $event" />
    </NSpin>
  </div>
</template>

<style scoped>
.table-page { gap: 12px; }
.filter { width: 220px; }
.switch { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.count { font-size: 13px; }
.grid-wrap { flex: 1; min-height: 320px; overflow: hidden; }
.grid-wrap :deep(.n-spin-content) { height: 100%; }
@media (max-width: 767px) {
  .filter { width: 100%; order: 10; }
  .count { display: none; }
}
</style>
