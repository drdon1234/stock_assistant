<script setup>
import { computed, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import {
  CellStyleModule, ClientSideRowModelModule, CsvExportModule, DateFilterModule, ExternalFilterModule,
  LocaleModule, ModuleRegistry, NumberFilterModule, QuickFilterModule, RenderApiModule, RowStyleModule, TextFilterModule,
  TooltipModule, colorSchemeDark, colorSchemeLight, themeQuartz,
} from 'ag-grid-community'
import { AG_GRID_LOCALE_CN } from '@ag-grid-community/locale'
import { NUMERIC_FORMATS, formatValue, trendClass } from '../format'
import { columnHelp } from '../help/glossary'
import { isDark, isMobile, state, toggleAttention } from '../store'

// 只注册用到的模块，减小打包体积
ModuleRegistry.registerModules([
  ClientSideRowModelModule, TextFilterModule, NumberFilterModule, DateFilterModule, QuickFilterModule,
  ExternalFilterModule, CsvExportModule, TooltipModule, CellStyleModule, RowStyleModule, RenderApiModule, LocaleModule,
])

const props = defineProps({
  columns: { type: Array, required: true }, // [{name, label, fmt, help?}]
  rows: { type: Array, required: true }, // 行为数组，顺序与 columns 一致
  sort: { type: Array, default: null }, // [列名, 是否降序]
  hidden: { type: Array, default: () => ['date'] },
  quickFilter: { type: String, default: '' },
  onlyAttention: { type: Boolean, default: false },
  groups: { type: Array, default: null }, // buildGroups 的结果：表头分两层显示
  visible: { type: Set, default: null }, // 要显示的列名，null 表示全部
})
const emit = defineEmits(['count'])
const router = useRouter()
const gridApi = shallowRef(null)

const index = computed(() => Object.fromEntries(props.columns.map((c, i) => [c.name, i])))
const codeIdx = computed(() => index.value.code)

const LONG_TEXT = new Set(['reason', 'concept', 'style', 'interpret', 'title', 'plan_profile'])

// 表头单行显示：按文字宽度估算列宽（中文约 13px，英文数字约 7.5px），另留出排序图标的位置
const textWidth = (text) => [...text].reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? 13 : 7.5), 0)
// 触屏设备的筛选图标始终显示，表头需要多留出图标宽度
const touch = window.matchMedia?.('(hover: none)').matches

function width(col, label) {
  const head = textWidth(label) + (touch ? 58 : 36)
  if (col.fmt === 'code') return isMobile.value ? 70 : 78
  if (col.name === 'name') return isMobile.value ? 84 : 96
  if (col.fmt === 'tags') return isMobile.value ? 220 : 300
  if (LONG_TEXT.has(col.name)) return 220
  if (col.fmt === 'text') return Math.max(110, Math.min(180, head))
  if (col.fmt === 'date') return Math.max(104, head)
  if (col.fmt === 'bool') return Math.max(64, Math.min(150, head))
  return Math.max(80, Math.min(160, head))
}

function dateComparator(filterDate, cell) {
  if (!cell) return -1
  const [y, m, d] = cell.split('-').map(Number)
  const value = new Date(y, m - 1, d).getTime()
  return value === filterDate.getTime() ? 0 : value < filterDate.getTime() ? -1 : 1
}

// 标签列：值为 [{label, dir}]，dir 为 up/down/flat
function tagsRenderer(p) {
  const box = document.createElement('span')
  box.className = 'tags'
  for (const t of p.value || []) {
    const tag = document.createElement('span')
    tag.className = `tag ${t.dir}`
    tag.textContent = t.label
    box.appendChild(tag)
  }
  return box
}

const tagsText = (tags) => (tags || []).map((t) => t.label).join(' ')

function makeDef(col, i) {
  const help = col.help ?? columnHelp(col.name)
  const def = {
    colId: col.name, field: String(i), headerName: col.label, initialWidth: width(col, col.label),
    headerTooltip: help ? `${col.label}：${help}` : col.label,
    initialSort: props.sort && props.sort[0] === col.name ? (props.sort[1] ? 'desc' : 'asc') : null,
  }
  // 手机屏幕窄，只固定名称列
  if (col.name === 'name' || (col.fmt === 'code' && !isMobile.value)) def.pinned = 'left'
  if (col.fmt === 'code') {
    def.cellClass = 'code-link'
    def.onCellClicked = (p) => router.push(`/stock/${p.value}`)
    def.filter = 'agTextColumnFilter'
  } else if (col.fmt === 'tags') {
    def.cellRenderer = tagsRenderer
    def.sortable = false
    def.filter = 'agTextColumnFilter'
    def.filterValueGetter = (p) => tagsText(p.data[i])
    def.getQuickFilterText = (p) => tagsText(p.value)
    def.valueFormatter = (p) => tagsText(p.value)
    def.tooltipValueGetter = (p) => tagsText(p.value)
  } else if (NUMERIC_FORMATS.has(col.fmt)) {
    def.type = 'numericColumn'
    def.filter = 'agNumberColumnFilter'
    def.valueFormatter = (p) => formatValue(p.value, col.fmt)
    if (col.fmt === 'pct' || col.fmt === 'signal') def.cellClass = (p) => trendClass(p.value)
  } else if (col.fmt === 'date') {
    def.filter = 'agDateColumnFilter'
    def.filterParams = { comparator: dateComparator }
  } else if (col.fmt === 'bool') {
    def.valueFormatter = (p) => formatValue(p.value, 'bool')
    def.filter = 'agTextColumnFilter'
    def.filterValueGetter = (p) => (p.data[i] ? '是' : '否')
  } else {
    def.filter = 'agTextColumnFilter'
    if (LONG_TEXT.has(col.name)) def.tooltipField = String(i)
  }
  return def
}

const columnDefs = computed(() => {
  const defs = []
  if (codeIdx.value !== undefined) {
    defs.push({
      colId: '__star', headerName: '', width: isMobile.value ? 34 : 44, pinned: isMobile.value ? null : 'left', sortable: false, filter: false, resizable: false,
      suppressMovable: true, cellClass: 'star-cell',
      valueGetter: (p) => state.attention.has(p.data[codeIdx.value]),
      cellRenderer: (p) => (p.value ? '★' : '☆'),
      onCellClicked: (p) => toggleAttention(p.data[codeIdx.value]).then(() => p.api.refreshCells({ columns: ['__star'], force: true })),
    })
  }
  const byName = {}
  const fixed = [] // 不参与分组、始终显示在最前的列：代码、名称（无分组时为全部列）
  props.columns.forEach((col, i) => {
    if (props.hidden.includes(col.name)) return
    byName[col.name] = makeDef(col, i)
    if (!props.groups || col.fmt === 'code' || col.name === 'name') fixed.push(col.name)
  })
  const shown = (name) => !props.visible || props.visible.has(name)
  defs.push(...fixed.filter((name) => props.groups || shown(name)).map((name) => byName[name]))
  for (const g of props.groups || []) {
    const children = g.cols
      .filter((c) => byName[c.name] && shown(c.name) && !fixed.includes(c.name))
      .map((c) => ({ ...byName[c.name], headerName: c.short, initialWidth: width(c, c.short) }))
    if (!children.length) continue
    if (g.title) defs.push({ groupId: `g:${g.title}`, headerName: g.title, headerClass: 'group-head', marryChildren: true, stickyLabel: true, children })
    else defs.push(...children)
  }
  return defs
})

const theme = computed(() => themeQuartz.withPart(isDark.value ? colorSchemeDark : colorSchemeLight).withParams({
  fontFamily: 'inherit',
  fontSize: 13,
  headerFontSize: 12,
  headerHeight: 34,
  headerColumnBorder: true,
  rowHeight: isMobile.value ? 36 : 34,
  spacing: 5,
  wrapperBorderRadius: 0,
  wrapperBorder: false,
  accentColor: isDark.value ? '#4f8cff' : '#2563eb',
  backgroundColor: isDark.value ? '#17181c' : '#ffffff',
  headerBackgroundColor: isDark.value ? '#1d1f24' : '#f9fafb',
  oddRowBackgroundColor: isDark.value ? '#1a1b20' : '#fcfcfd',
}))

const rowClassRules = {
  'is-attention': (p) => codeIdx.value !== undefined && state.attention.has(p.data[codeIdx.value]),
}

function applyExternal() {
  gridApi.value?.onFilterChanged()
}

const isExternalFilterPresent = () => props.onlyAttention && codeIdx.value !== undefined
const doesExternalFilterPass = (node) => state.attention.has(node.data[codeIdx.value])

function updateCount() {
  if (gridApi.value) emit('count', { shown: gridApi.value.getDisplayedRowCount(), total: props.rows.length })
}

function onReady(event) {
  gridApi.value = event.api
  updateCount()
}

watch(() => props.onlyAttention, applyExternal)
watch(() => state.attention, () => {
  gridApi.value?.redrawRows()
  if (props.onlyAttention) applyExternal()
})
watch(() => props.rows, () => setTimeout(updateCount))

function exportCsv(filename) {
  const keys = columnDefs.value.flatMap((d) => d.children || [d]).filter((d) => d.colId !== '__star').map((d) => d.colId)
  const csv = gridApi.value?.getDataAsCsv({ columnKeys: keys, skipColumnGroupHeaders: true })
  if (!csv) return
  const url = URL.createObjectURL(new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: `${filename}.csv` })
  a.click()
  URL.revokeObjectURL(url)
}

function resetFilters() {
  gridApi.value?.setFilterModel(null)
}

defineExpose({ exportCsv, resetFilters })
</script>

<template>
  <AgGridVue class="grid" :theme="theme" :row-data="rows" :column-defs="columnDefs" :locale-text="AG_GRID_LOCALE_CN"
             :default-col-def="{ sortable: true, resizable: true, unSortIcon: false }"
             :quick-filter-text="quickFilter" :row-class-rules="rowClassRules" :tooltip-show-delay="300"
             :is-external-filter-present="isExternalFilterPresent" :does-external-filter-pass="doesExternalFilterPass"
             :animate-rows="false" :suppress-cell-focus="false" :enable-cell-text-selection="true"
             @grid-ready="onReady" @filter-changed="updateCount" @row-data-updated="updateCount" />
</template>

<style scoped>
.grid { width: 100%; height: 100%; }
.grid :deep(.code-link) { color: var(--primary); cursor: pointer; font-weight: 500; }
.grid :deep(.code-link:hover) { text-decoration: underline; }
.grid :deep(.star-cell) { cursor: pointer; color: #f59f00; text-align: center; font-size: 15px; }
.grid :deep(.is-attention) { --ag-background-color: rgba(245, 159, 0, 0.08); }
.grid :deep(.up) { color: var(--up); }
.grid :deep(.down) { color: var(--down); }
.grid :deep(.group-head .ag-header-group-cell-label) { font-weight: 600; }
.grid :deep(.tags) { display: inline-flex; gap: 4px; overflow: hidden; vertical-align: middle; }
.grid :deep(.tag) {
  padding: 0 6px; border-radius: 4px; font-size: 12px; line-height: 20px; white-space: nowrap;
  color: var(--muted); background: var(--surface-2); border: 1px solid var(--border);
}
.grid :deep(.tag.up) { color: var(--up); background: var(--up-soft); border-color: transparent; }
.grid :deep(.tag.down) { color: var(--down); background: var(--down-soft); border-color: transparent; }
/* 筛选图标只在悬停或已筛选时显示，给列名留出空间；触屏设备始终显示 */
@media (hover: hover) {
  .grid :deep(.ag-header-cell:not(:hover) .ag-header-cell-filter-button:not(.ag-filter-active)) { display: none; }
}
</style>
