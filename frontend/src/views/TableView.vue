<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NDatePicker, NInput, NSpin, NSwitch, useMessage } from 'naive-ui'
import ColumnPicker from '../components/ColumnPicker.vue'
import DataGrid from '../components/DataGrid.vue'
import GuideButton from '../components/GuideButton.vue'
import Icon from '../components/Icon.vue'
import PageGuide from '../components/PageGuide.vue'
import { useColumnVisibility } from '../components/columns'
import { api } from '../api'
import { buildGroups } from '../help/tableLayouts'
import { toDateString } from '../format'

const route = useRoute()
const message = useMessage()
const name = route.params.name
const data = ref(null)
const loading = ref(false)
const date = ref(null)
const keyword = ref('')
const onlyAttention = ref(false)
const count = ref({ shown: 0, total: 0 })
const grid = ref(null)

const dateSet = computed(() => new Set(data.value?.dates || []))
const hasCode = computed(() => data.value?.columns.some((c) => c.name === 'code'))
const HIDDEN = ['date']
const groups = computed(() => (data.value
  ? buildGroups(name, data.value.columns.filter((c) => !HIDDEN.includes(c.name)), ['code', 'name'])
  : []))
const columns = useColumnVisibility(name, groups)
// 列少的表不需要列设置
const wide = computed(() => columns.total.value > 12)

async function load(day) {
  loading.value = true
  try {
    data.value = await api.table(name, day)
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
      <GuideButton :id="name" />
      <NDatePicker v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small"
                   :is-date-disabled="(ts) => !dateSet.has(toDateString(ts))" :disabled="!data?.dates.length"
                   style="width: 140px" placeholder="暂无数据" />
      <NInput v-model:value="keyword" size="small" clearable placeholder="筛选代码/名称/任意内容" class="filter">
        <template #prefix><Icon name="search" :size="15" /></template>
      </NInput>
      <label v-if="hasCode" class="switch"><NSwitch v-model:value="onlyAttention" size="small" /> 只看关注</label>
      <span class="spacer" />
      <span class="muted count">{{ count.shown }} / {{ count.total }} 条</span>
      <ColumnPicker v-if="data && wide" :groups="groups" :columns="columns" />
      <NButton size="small" @click="grid?.resetFilters()">重置筛选</NButton>
      <NButton size="small" @click="grid?.exportCsv(`${data?.label}_${date}`)">
        <template #icon><Icon name="download" :size="15" /></template>导出
      </NButton>
    </div>
    <PageGuide :id="name" />
    <NSpin :show="loading" class="grid-wrap card">
      <DataGrid v-if="data" ref="grid" :columns="data.columns" :rows="data.rows" :sort="data.sort" :hidden="HIDDEN"
                :groups="wide ? groups : null" :visible="wide ? columns.visible.value : null"
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
