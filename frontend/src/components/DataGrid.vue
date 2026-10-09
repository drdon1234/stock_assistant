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

// 列宽不提供手动调整，按表头与单元格文字的实际宽度计算，超过上限的表头换行。
// 手机上的上限更小，以便一屏多放几列
const CELL_PAD = { mobile: 6, desktop: 10 } // 单元格左右内边距，与主题参数一致
// 表头除文字外还要容纳排序图标（21px）与筛选按钮（16px）；两者都始终预留位置，排序或悬停时列名不会重新换行
const HEAD_ICONS = 37
const HEAD_LINE = 12 * 1.3 // 表头字号 × 行高
let ctx = null
let fontFamily = ''

function measure(text, size, weight = 400) {
  if (!ctx) {
    ctx = document.createElement('canvas').getContext('2d')
    fontFamily = getComputedStyle(document.body).fontFamily
  }
  ctx.font = `${weight} ${size}px ${fontFamily}`
  return ctx.measureText(text).width
}

// 表头文字按换行单位拆分后各段的宽度：中文逐字可断，连续的英文、数字和符号不断开
const tokenWidths = (text) => (text.match(/[\x21-\x7e]+|./gu) || []).map((t) => measure(t, 12, 500))

// 模拟浏览器换行，返回行数
function lineCount(text, avail) {
  let lines = 1
  let used = 0
  for (const w of tokenWidths(text)) {
    if (used > 0 && used + w > avail) [lines, used] = [lines + 1, w]
    else used += w
  }
  return lines
}

// 表头文字折成不超过 maxLines 行所需的最小宽度（不可断开的英文数字串至少要能完整放下）
const labelWidths = new Map()
function labelWidth(text, maxLines) {
  const key = `${maxLines}|${text}`
  if (!labelWidths.has(key)) {
    const tokens = tokenWidths(text)
    let avail = Math.ceil(Math.max(tokens.reduce((a, b) => a + b, 0) / maxLines, ...tokens))
    while (lineCount(text, avail) > maxLines) avail += 2
    labelWidths.set(key, avail + 1)
  }
  return labelWidths.get(key)
}

// 估算文字宽度用于挑选最长的单元格（中文约为英文数字的两倍宽），只对挑出的那个精确测量
const weight = (text) => [...text].reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? 2 : 1), 0)

function cellText(value, col) {
  if (value === null || value === undefined) return ''
  if (col.fmt === 'bool' || NUMERIC_FORMATS.has(col.fmt)) return formatValue(value, col.fmt)
  return String(value)
}

// 各列最长单元格的像素宽度
const contentWidths = computed(() => {
  const widths = {}
  props.columns.forEach((col, i) => {
    if (col.fmt === 'tags' || props.hidden.includes(col.name)) return
    let longest = ''
    let max = 0
    for (const row of props.rows) {
      const text = cellText(row[i], col)
      const w = text.length * 2 > max ? weight(text) : 0
      if (w > max) [max, longest] = [w, text]
    }
    widths[col.name] = Math.ceil(measure(longest, 13)) + 2
  })
  return widths
})

// 内容的列宽上限：超出的单元格以省略号结尾，悬停可看全文
function contentMax(col) {
  const m = isMobile.value
  if (col.name === 'name') return m ? 88 : 120
  if (LONG_TEXT.has(col.name)) return m ? 160 : 260
  if (col.fmt === 'text') return m ? 120 : 180
  return m ? 110 : 160
}

const cellPad = () => (isMobile.value ? CELL_PAD.mobile : CELL_PAD.desktop) * 2 + 2

// 表头单行放不下（超过上限）时折成两行；手机上为避免折成三行，可略放宽
function headerWidth(label) {
  const extra = HEAD_ICONS + cellPad()
  const [cap, wideCap] = isMobile.value ? [96, 120] : [160, 160]
  const single = labelWidth(label, 1) + extra
  return single <= cap ? single : Math.min(Math.max(labelWidth(label, 2) + extra, cap), wideCap)
}

function width(col, label) {
  if (col.fmt === 'tags') return isMobile.value ? 220 : 300
  const content = Math.min((contentWidths.value[col.name] ?? 0) + cellPad(), contentMax(col))
  return Math.max(content, headerWidth(label), 48)
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
    colId: col.name, field: String(i), headerName: col.label, width: width(col, col.label),
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
    def.tooltipField = String(i) // 超出列宽上限的文字以省略号结尾，悬停查看全文
  }
  return def
}

const columnDefs = computed(() => {
  const defs = []
  if (codeIdx.value !== undefined) {
    defs.push({
      colId: '__star', headerName: '', width: isMobile.value ? 30 : 40, minWidth: 30, pinned: isMobile.value ? null : 'left', sortable: false, filter: false,
      cellClass: 'star-cell',
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
      .map((c) => ({ ...byName[c.name], headerName: c.short, width: width(c, c.short) }))
    if (!children.length) continue
    if (g.title) defs.push({ groupId: `g:${g.title}`, headerName: g.title, headerClass: 'group-head', marryChildren: true, stickyLabel: true, children })
    else defs.push(...children)
  }
  return defs
})

// 表头高度按所有显示列中最多的行数统一设定，横向滚动时表头不会忽高忽低
const headerHeight = computed(() => {
  const lines = columnDefs.value.flatMap((d) => d.children || [d])
    .filter((d) => d.headerName)
    .map((d) => lineCount(d.headerName, d.width - HEAD_ICONS - cellPad()))
  const n = Math.max(1, ...lines)
  return n === 1 ? 34 : Math.ceil(n * HEAD_LINE + 12)
})

const theme = computed(() => themeQuartz.withPart(isDark.value ? colorSchemeDark : colorSchemeLight).withParams({
  fontFamily: 'inherit',
  fontSize: 13,
  headerFontSize: 12,
  headerHeight: 34,
  headerColumnBorder: true,
  rowHeight: isMobile.value ? 36 : 34,
  spacing: 5,
  cellHorizontalPadding: isMobile.value ? CELL_PAD.mobile : CELL_PAD.desktop,
  wrapperBorderRadius: 0,
  wrapperBorder: false,
  accentColor: isDark.value ? '#4f8cff' : '#2563eb',
  backgroundColor: isDark.value ? '#17181c' : '#ffffff',
  headerBackgroundColor: isDark.value ? '#1d1f24' : '#f9fafb',
  oddRowBackgroundColor: isDark.value ? '#1a1b20' : '#fcfcfd',
}))

// 列宽与列顺序固定，不提供拖动调整；表头文字超出列宽时换行
const DEFAULT_COL = { sortable: true, resizable: false, unSortIcon: false, wrapHeaderText: true }

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
  <AgGridVue class="grid" :theme="theme" :header-height="headerHeight" :group-header-height="34" :row-data="rows" :column-defs="columnDefs" :locale-text="AG_GRID_LOCALE_CN"
             :default-col-def="DEFAULT_COL""
             :quick-filter-text="quickFilter" :row-class-rules="rowClassRules" :tooltip-show-delay="300"
             :is-external-filter-present="isExternalFilterPresent" :does-external-filter-pass="doesExternalFilterPass"
             :suppress-movable-columns="true" :suppress-drag-leave-hides-columns="true" :animate-rows="false" :suppress-cell-focus="false" :enable-cell-text-selection="true"
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
.grid :deep(.ag-header-cell-text) { line-height: 1.3; }
/* 未排序时也预留排序图标的位置，点击排序不会让列名重新换行 */
.grid :deep(.ag-header-cell-sortable .ag-sort-indicator-container) { min-width: 21px; }
/* 筛选图标只在悬停或已筛选时显示（位置保留，显示时列名不会重新换行）；触屏设备始终显示 */
@media (hover: hover) {
  .grid :deep(.ag-header-cell:not(:hover) .ag-header-cell-filter-button:not(.ag-filter-active)) { visibility: hidden; }
}
</style>
