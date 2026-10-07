<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { NButton, NDatePicker, NInput, NRadioButton, NRadioGroup, NSpin, NSwitch, NTooltip, useMessage } from 'naive-ui'
import DataGrid from '../components/DataGrid.vue'
import GuideButton from '../components/GuideButton.vue'
import Icon from '../components/Icon.vue'
import PageGuide from '../components/PageGuide.vue'
import { api } from '../api'
import { toDateString } from '../format'
import { DIR_LABELS, PATTERN_HELP, patternDirection } from '../help/patterns'
import { isMobile } from '../store'

// K 线形态宽表（61 列、绝大多数为空）改为每只股票一行、列出当天出现的形态
const TABLE = 'cn_stock_pattern'
const message = useMessage()
const raw = ref(null)
const loading = ref(false)
const date = ref(null)
const keyword = ref('')
const onlyAttention = ref(false)
const direction = ref('all')
const selected = ref(new Set())
const expanded = ref(false)
const count = ref({ shown: 0, total: 0 })
const grid = ref(null)
document.title = 'K线形态 · InStock'

const dateSet = computed(() => new Set(raw.value?.dates || []))
const patternCols = computed(() => (raw.value?.columns || [])
  .map((c, i) => ({ ...c, i }))
  .filter((c) => c.fmt === 'signal'))

const COLUMNS = [
  { name: 'code', label: '代码', fmt: 'code' },
  { name: 'name', label: '名称', fmt: 'text' },
  { name: 'bull', label: '看涨形态', fmt: 'tags', help: '传统上预示上涨的形态。“·确认”表示已被后续 K 线确认。' },
  { name: 'bear', label: '看跌形态', fmt: 'tags', help: '传统上预示下跌的形态。' },
  { name: 'neutral', label: '中性形态', fmt: 'tags', help: '十字星、纺锤线等本身不判断方向的形态，需要结合所处位置理解。' },
  { name: 'n_bull', label: '看涨数', fmt: 'int', help: '当天出现的看涨形态个数。' },
  { name: 'n_bear', label: '看跌数', fmt: 'int', help: '当天出现的看跌形态个数。' },
]

// 每只股票：[代码, 名称, 看涨标签, 看跌标签, 中性标签, 看涨数, 看跌数, 出现的“形态:方向”]
const allRows = computed(() => {
  if (!raw.value) return []
  const idx = Object.fromEntries(raw.value.columns.map((c, i) => [c.name, i]))
  return raw.value.rows.map((r) => {
    const tags = { up: [], down: [], flat: [] }
    const keys = new Set()
    for (const c of patternCols.value) {
      const v = r[c.i]
      if (!v) continue
      const dir = patternDirection(c.name, v)
      keys.add(`${c.name}:${dir}`)
      tags[dir].push({ label: Math.abs(v) >= 200 ? `${c.label}·确认` : c.label, dir })
    }
    return [r[idx.code], r[idx.name], tags.up, tags.down, tags.flat, tags.up.length, tags.down.length, keys]
  })
})

const rows = computed(() => allRows.value.filter((r) => {
  if (direction.value === 'bull' && !r[5]) return false
  if (direction.value === 'bear' && !r[6]) return false
  if (selected.value.size && ![...selected.value].some((k) => r[7].has(k))) return false
  return true
}))

// 当天各形态出现次数，按看涨/看跌/中性分组
const summary = computed(() => {
  const counts = {}
  for (const r of raw.value?.rows || []) {
    for (const c of patternCols.value) {
      const v = r[c.i]
      if (!v) continue
      const dir = patternDirection(c.name, v)
      const id = `${c.name}:${dir}`
      const item = counts[id] ||= { id, key: c.name, label: c.label, dir, n: 0 }
      item.n += 1
    }
  }
  const items = Object.values(counts).sort((a, b) => b.n - a.n)
  return [
    { dir: 'up', title: '看涨', items: items.filter((i) => i.dir === 'up') },
    { dir: 'down', title: '看跌', items: items.filter((i) => i.dir === 'down') },
    { dir: 'flat', title: '中性', items: items.filter((i) => i.dir === 'flat') },
  ].filter((g) => g.items.length)
})
const LIMIT = 8
const hasMore = computed(() => summary.value.some((g) => g.items.length > LIMIT))

function toggle(key) {
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

function help(key) {
  const h = PATTERN_HELP[key]
  return h ? `${DIR_LABELS[h.dir]}｜${h.desc}` : ''
}

async function load(day) {
  loading.value = true
  try {
    raw.value = await api.table(TABLE, day)
    date.value = raw.value.date
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

watch(date, (value, old) => {
  if (old && value && value !== raw.value?.date) {
    selected.value = new Set()
    load(value)
  }
})

load()
</script>

<template>
  <div class="page page-fill pattern-page">
    <div class="toolbar">
      <h1>K线形态</h1>
      <GuideButton :id="TABLE" />
      <NDatePicker v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small"
                   :is-date-disabled="(ts) => !dateSet.has(toDateString(ts))" :disabled="!raw?.dates.length"
                   style="width: 140px" placeholder="暂无数据" />
      <NInput v-model:value="keyword" size="small" clearable placeholder="筛选代码/名称/形态" class="filter">
        <template #prefix><Icon name="search" :size="15" /></template>
      </NInput>
      <NRadioGroup v-model:value="direction" size="small">
        <NRadioButton value="all">全部</NRadioButton>
        <NRadioButton value="bull">含看涨</NRadioButton>
        <NRadioButton value="bear">含看跌</NRadioButton>
      </NRadioGroup>
      <label class="switch"><NSwitch v-model:value="onlyAttention" size="small" /> 只看关注</label>
      <span class="spacer" />
      <span class="muted count">{{ count.shown }} / {{ allRows.length }} 只</span>
      <NButton size="small" @click="grid?.exportCsv(`K线形态_${date}`)">
        <template #icon><Icon name="download" :size="15" /></template>导出
      </NButton>
    </div>
    <PageGuide :id="TABLE" />

    <div v-if="summary.length" class="card summary" :class="{ collapsed: !expanded }">
      <div v-for="g in summary" :key="g.dir" class="group">
        <span class="group-title" :class="g.dir">{{ g.title }}</span>
        <div class="chips">
          <NTooltip v-for="item in (expanded ? g.items : g.items.slice(0, LIMIT))" :key="item.id"
                    :disabled="isMobile" style="max-width: 320px">
            <template #trigger>
              <button type="button" class="chip" :class="[g.dir, { active: selected.has(item.id) }]"
                      :aria-pressed="selected.has(item.id)" @click="toggle(item.id)">
                {{ item.label }}<b>{{ item.n }}</b>
              </button>
            </template>
            {{ help(item.key) }}
          </NTooltip>
        </div>
      </div>
      <div class="summary-foot">
        <NButton v-if="hasMore" size="tiny" quaternary @click="expanded = !expanded">{{ expanded ? '收起' : '展开全部形态' }}</NButton>
        <NButton v-if="selected.size" size="tiny" quaternary type="primary" @click="selected = new Set()">清除形态筛选（{{ selected.size }}）</NButton>
        <span class="muted">点击形态只看出现该形态的股票；悬停查看形态含义</span>
        <RouterLink :to="{ path: '/learn', hash: '#patterns' }">形态图鉴 →</RouterLink>
      </div>
    </div>

    <NSpin :show="loading" class="grid-wrap card">
      <DataGrid v-if="raw" ref="grid" :columns="COLUMNS" :rows="rows" :hidden="[]" :sort="['n_bull', true]"
                :quick-filter="keyword" :only-attention="onlyAttention" @count="count = $event" />
    </NSpin>
  </div>
</template>

<style scoped>
.pattern-page { gap: 12px; }
.filter { width: 200px; }
.switch { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.count { font-size: 13px; }
.summary { padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; }
.group { display: flex; gap: 10px; align-items: flex-start; }
.group-title { flex: none; width: 34px; font-size: 12px; font-weight: 600; line-height: 26px; }
.group-title.up { color: var(--up); }
.group-title.down { color: var(--down); }
.group-title.flat { color: var(--muted); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 8px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text); font: inherit; font-size: 12px;
  cursor: pointer;
}
.chip b { font-weight: 600; color: var(--muted); }
.chip:hover { border-color: var(--primary); }
.chip.active { border-color: var(--primary); background: var(--primary); color: #fff; }
.chip.active b { color: #fff; }
.summary-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: 12px; padding-left: 44px; }
.grid-wrap { flex: 1; min-height: 320px; overflow: hidden; }
.grid-wrap :deep(.n-spin-content) { height: 100%; }
@media (max-width: 767px) {
  .filter { width: 100%; order: 10; }
  .count { display: none; }
  .summary-foot { padding-left: 0; }
  .summary-foot .muted { display: none; }
  .collapsed .chips { max-height: 60px; overflow: hidden; }
}
</style>
