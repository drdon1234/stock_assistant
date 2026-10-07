<script setup>
import { computed, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import {
  CellStyleModule, ClientSideRowModelModule, CsvExportModule, DateFilterModule, ExternalFilterModule, LocaleModule,
  ModuleRegistry, NumberFilterModule, QuickFilterModule, RenderApiModule, RowStyleModule, TextFilterModule,
  TooltipModule, colorSchemeDark, colorSchemeLight, themeQuartz,
} from 'ag-grid-community'
import { AG_GRID_LOCALE_CN } from '@ag-grid-community/locale'
import { NUMERIC_FORMATS, formatValue, trendClass } from '../format'
import { isDark, isMobile, state, toggleAttention } from '../store'

// 只注册用到的模块，减小打包体积
ModuleRegistry.registerModules([
  ClientSideRowModelModule, TextFilterModule, NumberFilterModule, DateFilterModule, QuickFilterModule,
  ExternalFilterModule, CsvExportModule, TooltipModule, CellStyleModule, RowStyleModule, RenderApiModule, LocaleModule,
])

const props = defineProps({
  columns: { type: Array, required: true }, // [{name, label, fmt}]
  rows: { type: Array, required: true }, // 行为数组，顺序与 columns 一致
  sort: { type: Array, default: null }, // [列名, 是否降序]
  hidden: { type: Array, default: () => ['date'] },
  quickFilter: { type: String, default: '' },
  onlyAttention: { type: Boolean, default: false },
})
const emit = defineEmits(['count'])
const router = useRouter()
const gridApi = shallowRef(null)

const index = computed(() => Object.fromEntries(props.columns.map((c, i) => [c.name, i])))
const codeIdx = computed(() => index.value.code)

const LONG_TEXT = new Set(['reason', 'concept', 'style', 'interpret', 'title', 'plan_profile'])

function width(col) {
  if (col.fmt === 'code') return isMobile.value ? 70 : 78
  if (col.name === 'name') return isMobile.value ? 84 : 96
  if (LONG_TEXT.has(col.name)) return 220
  if (col.fmt === 'text') return 110
  if (col.fmt === 'date') return 104
  if (col.fmt === 'bool') return 72
  return Math.max(84, Math.min(130, col.label.length * 13 + 24))
}

function dateComparator(filterDate, cell) {
  if (!cell) return -1
  const [y, m, d] = cell.split('-').map(Number)
  const value = new Date(y, m - 1, d).getTime()
  return value === filterDate.getTime() ? 0 : value < filterDate.getTime() ? -1 : 1
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
  props.columns.forEach((col, i) => {
    if (props.hidden.includes(col.name)) return
    const def = {
      colId: col.name, field: String(i), headerName: col.label, width: width(col),
      headerTooltip: col.label, sort: props.sort && props.sort[0] === col.name ? (props.sort[1] ? 'desc' : 'asc') : null,
    }
    // 手机屏幕窄，只固定名称列
    if (col.name === 'name' || (col.fmt === 'code' && !isMobile.value)) def.pinned = 'left'
    if (col.fmt === 'code') {
      def.cellClass = 'code-link'
      def.onCellClicked = (p) => router.push(`/stock/${p.value}`)
      def.filter = 'agTextColumnFilter'
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
    defs.push(def)
  })
  return defs
})

const theme = computed(() => themeQuartz.withPart(isDark.value ? colorSchemeDark : colorSchemeLight).withParams({
  fontFamily: 'inherit',
  fontSize: 13,
  headerFontSize: 12,
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
  const csv = gridApi.value?.getDataAsCsv({ columnKeys: columnDefs.value.filter((d) => d.colId !== '__star').map((d) => d.colId) })
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
             :default-col-def="{ sortable: true, resizable: true, wrapHeaderText: true, autoHeaderHeight: true, unSortIcon: false }"
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
</style>
