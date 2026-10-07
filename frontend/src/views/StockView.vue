<script setup>
import { computed, ref, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NEmpty, NSelect, NSpin, NSwitch, useMessage } from 'naive-ui'
import EChart from '../components/EChart.vue'
import Icon from '../components/Icon.vue'
import { calcChips } from '../components/cyq'
import { INDICATOR_LABELS, MAIN_OVERLAYS, SUB_INDICATORS } from '../components/indicatorCatalog'
import GuideButton from '../components/GuideButton.vue'
import PageGuide from '../components/PageGuide.vue'
import { patternDirection } from '../help/patterns'
import { api } from '../api'
import { SERIES_COLORS, colors } from '../colors'
import { fmtMoney, fmtNum, fmtPct, fmtPercent, fmtVol, trendClass } from '../format'
import { isMobile, state, toggleAttention } from '../store'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const code = route.params.code
const data = shallowRef(null)
const error = ref('')
const overlay = ref('none')
const sub = ref('MACD')
const showPatterns = ref(false)
const chips = shallowRef(null) // 仅供右侧信息面板展示
let chart = null
// 以下两个变量不做成响应式：光标移动、缩放时只局部更新图表，避免整张图重建
let currentChips = null
let zoom = null

const CYQ_DAYS = 210
const MA_COLORS = SERIES_COLORS

api.kline(code)
  .then((d) => {
    currentChips = calcChips(d, d.close.length - 1, CYQ_DAYS)
    chips.value = currentChips
    data.value = d
    document.title = `${d.name || code} · InStock`
  })
  .catch((e) => { error.value = e.message })

const n = computed(() => data.value?.close.length || 0)
const last = computed(() => {
  const d = data.value
  if (!d || n.value < 1) return null
  const i = n.value - 1
  const prev = i > 0 ? d.close[i - 1] : null
  return {
    date: d.dates[i], close: d.close[i], open: d.open[i], high: d.high[i], low: d.low[i], volume: d.volume[i],
    amount: d.amount[i], turnover: d.turnover[i], change: prev ? (d.close[i] / prev - 1) * 100 : null,
  }
})
const market = computed(() => (/^[569]/.test(code) ? 'sh' : 'sz'))
const isEtf = computed(() => /^[15]/.test(code))
const subConf = computed(() => SUB_INDICATORS.find((s) => s.key === sub.value))
const overlayConf = computed(() => MAIN_OVERLAYS.find((s) => s.key === overlay.value))
const subOptions = SUB_INDICATORS.map((s) => ({ label: s.key, value: s.key }))
const overlayOptions = [{ label: '主图无叠加', value: 'none' }, ...MAIN_OVERLAYS.map((s) => ({ label: s.key, value: s.key }))]

function windowSize() {
  return isMobile.value ? 60 : 120
}

function priceExtent(start, end) {
  const d = data.value
  let lo = Infinity
  let hi = -Infinity
  for (let i = Math.max(0, start); i <= Math.min(n.value - 1, end); i++) {
    lo = Math.min(lo, d.low[i])
    hi = Math.max(hi, d.high[i])
  }
  const pad = (hi - lo) * 0.04 || hi * 0.02
  return { min: +(lo - pad).toFixed(2), max: +(hi + pad).toFixed(2) }
}

function cyqSeriesData(result) {
  return result.prices.map((p, i) => [result.chips[i], p, p <= result.current ? 1 : 0])
}

const option = computed(() => {
  const d = data.value
  if (!d) return null
  const c = colors.value
  const mobile = isMobile.value
  const cyqWidth = mobile ? 72 : 170
  const right = cyqWidth + 24
  const left = mobile ? 44 : 60
  const start = zoom ? zoom[0] : Math.max(0, n.value - windowSize())
  const end = zoom ? zoom[1] : n.value - 1
  const extent = priceExtent(start, end)
  const xIdx = [0, 1, 2]
  const category = (gridIndex, showLabel) => ({
    type: 'category', gridIndex, data: d.dates, boundaryGap: true,
    axisLine: { lineStyle: { color: c.grid } }, axisTick: { show: false },
    axisLabel: { show: showLabel, color: c.muted, fontSize: 11 }, splitLine: { show: false },
    axisPointer: { label: { show: showLabel } },
  })
  const valueAxis = (gridIndex, extra = {}) => ({
    type: 'value', gridIndex, scale: true, splitNumber: 3,
    axisLabel: { color: c.muted, fontSize: 11, ...(extra.axisLabel || {}) },
    splitLine: { lineStyle: { color: c.grid } }, ...extra,
  })
  const line = (name, values, color, xAxisIndex = 0, yAxisIndex = 0, extra = {}) => ({
    name, type: 'line', data: values, xAxisIndex, yAxisIndex, symbol: 'none', smooth: false,
    lineStyle: { width: 1.2, color }, itemStyle: { color }, emphasis: { disabled: true }, ...extra,
  })
  const series = [{
    name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
    data: d.close.map((close, i) => [d.open[i], close, d.low[i], d.high[i]]),
    itemStyle: { color: c.up, color0: c.down, borderColor: c.up, borderColor0: c.down },
  }]
  const legend = []
  Object.entries(d.ma).forEach(([key, values], i) => {
    const name = key.toUpperCase()
    legend.push(name)
    series.push(line(name, values, MA_COLORS[i % MA_COLORS.length]))
  })
  if (overlayConf.value) {
    overlayConf.value.lines.forEach((key, i) => {
      const name = INDICATOR_LABELS[key] || key
      legend.push(name)
      series.push(overlayConf.value.scatter
        ? { name, type: 'scatter', data: d.indicators[key], symbolSize: 3, itemStyle: { color: c.primary }, xAxisIndex: 0, yAxisIndex: 0 }
        : line(name, d.indicators[key], ['#1c7ed6', '#868e96', '#e64980'][i % 3], 0, 0, { lineStyle: { width: 1.2, type: i === 1 ? 'solid' : 'dashed', color: ['#1c7ed6', '#868e96', '#e64980'][i % 3] } }))
    })
  }
  if (showPatterns.value && d.patterns.length) {
    const groups = new Map()
    for (const p of d.patterns) {
      const g = groups.get(p.i) || { up: [], down: [], flat: [] }
      g[patternDirection(p.key, p.value)].push(p.label)
      groups.set(p.i, g)
    }
    const bull = []
    const bear = []
    const neutral = []
    groups.forEach((g, i) => {
      if (g.up.length) bull.push({ value: [i, d.high[i]], labels: g.up })
      if (g.down.length) bear.push({ value: [i, d.low[i]], labels: g.down })
      if (g.flat.length) neutral.push({ value: [i, d.high[i]], labels: g.flat })
    })
    const mark = (name, points, color, symbolRotate, offset, symbol = 'triangle') => ({
      name, type: 'scatter', data: points, xAxisIndex: 0, yAxisIndex: 0, symbol, symbolSize: symbol === 'circle' ? 5 : 7,
      symbolRotate, symbolOffset: [0, offset], itemStyle: { color, opacity: 0.85 }, z: 5,
      tooltip: { trigger: 'item', formatter: (p) => `${d.dates[p.value[0]]}<br/>${name}：${p.data.labels.join('、')}` },
    })
    series.push(mark('看涨形态', bull, c.up, 0, -10), mark('看跌形态', bear, c.down, 180, 10),
      mark('中性形态', neutral, c.muted, 0, bull.length ? -20 : -10, 'circle'))
  }
  const upDown = (i) => (d.close[i] >= d.open[i] ? c.up : c.down)
  series.push({
    name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
    data: d.volume.map((v, i) => ({ value: v, itemStyle: { color: upDown(i) } })),
  })
  Object.entries(d.vol_ma).forEach(([key, values], i) => series.push(line(`量${key.toUpperCase()}`, values, MA_COLORS[i], 1, 1)))
  const conf = subConf.value
  ;(conf.bars || []).forEach((key) => series.push({
    name: INDICATOR_LABELS[key] || key, type: 'bar', xAxisIndex: 2, yAxisIndex: 2, barMaxWidth: 3,
    data: d.indicators[key].map((v) => ({ value: v, itemStyle: { color: v >= 0 ? c.up : c.down } })),
  }))
  conf.lines.forEach((key, i) => series.push(line(INDICATOR_LABELS[key] || key, d.indicators[key], MA_COLORS[i % MA_COLORS.length], 2, 2)))

  const result = currentChips
  const step = result.prices[1] - result.prices[0] || 0.01
  series.push({
    id: 'cyq', name: '筹码', type: 'custom', xAxisIndex: 3, yAxisIndex: 3, silent: true, clip: true, // 超出当前价格区间的筹码不画到网格外
    data: cyqSeriesData(result),
    renderItem: (params, api) => {
      const start = api.coord([0, api.value(1)])
      const end = api.coord([api.value(0), api.value(1)])
      const height = Math.max(1, Math.abs(api.size([0, step])[1]) * 0.85)
      return {
        type: 'rect', shape: { x: start[0], y: start[1] - height / 2, width: Math.max(0, end[0] - start[0]), height },
        style: { fill: api.value(2) ? c.up : c.primary, opacity: 0.55 },
      }
    },
    encode: { x: 0, y: 1 },
  }, {
    id: 'cyq-avg', name: '平均成本', type: 'line', xAxisIndex: 3, yAxisIndex: 3, symbol: 'none', silent: true,
    lineStyle: { type: 'dashed', color: c.text, width: 1 },
    data: [[0, result.avgCost], [Math.max(...result.chips), result.avgCost]],
  })

  return {
    animation: false,
    legend: { data: legend, top: 2, left: left, itemWidth: 14, itemHeight: 8, textStyle: { color: c.muted, fontSize: 11 }, type: 'scroll', right: right },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross', label: { backgroundColor: '#555' } },
      backgroundColor: 'rgba(30,32,38,0.92)', borderWidth: 0, textStyle: { color: '#fff', fontSize: 12 },
      position: mobile ? (pt, params, el, rect, size) => [pt[0] < size.viewSize[0] / 2 ? size.viewSize[0] - size.contentSize[0] - 8 : 8, 30] : undefined,
      formatter: (params) => {
        const i = params[0]?.dataIndex
        if (i === undefined) return ''
        const prev = i > 0 ? d.close[i - 1] : null
        const chg = prev ? (d.close[i] / prev - 1) * 100 : null
        const rows = [
          ['开', fmtNum(d.open[i])], ['高', fmtNum(d.high[i])], ['低', fmtNum(d.low[i])], ['收', fmtNum(d.close[i])],
          ['涨跌', fmtPct(chg)], ['量', fmtVol(d.volume[i])], ['额', fmtMoney(d.amount[i])], ['换手', fmtPercent(d.turnover[i])],
        ]
        return `<b>${d.dates[i]}</b><br/>${rows.map(([k, v]) => `${k}&nbsp;&nbsp;<b>${v}</b>`).join('<br/>')}`
      },
    },
    axisPointer: { link: [{ xAxisIndex: xIdx }] },
    grid: [
      { left, right, top: 30, height: '50%' },
      { left, right, top: '61%', height: '11%' },
      { left, right, top: '76%', height: '14%' },
      { right: 8, width: cyqWidth, top: 30, height: '50%' },
    ],
    xAxis: [category(0, false), category(1, false), category(2, true),
      { type: 'value', gridIndex: 3, show: false, min: 0 }],
    yAxis: [
      valueAxis(0, { min: extent.min, max: extent.max, scale: false }),
      valueAxis(1, { splitNumber: 2, axisLabel: { formatter: (v) => fmtVol(v).replace('手', '') } }),
      valueAxis(2, { splitNumber: 2 }),
      { type: 'value', gridIndex: 3, min: extent.min, max: extent.max, position: 'right',
        axisLabel: { show: !mobile, color: c.muted, fontSize: 11 }, splitLine: { show: false }, axisLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: xIdx, startValue: start, endValue: end, minValueSpan: 20 },
      { type: 'slider', xAxisIndex: xIdx, bottom: 6, height: 16, startValue: start, endValue: end,
        borderColor: 'transparent', textStyle: { color: c.muted }, brushSelect: false },
    ],
    series,
  }
})

let frame = 0
function onReady(instance) {
  chart = instance
  chart.on('updateAxisPointer', (e) => {
    const info = e.axesInfo?.find((a) => a.axisDim === 'x')
    if (!info || frame) return
    frame = requestAnimationFrame(() => {
      frame = 0
      const idx = Math.min(Math.max(0, info.value), n.value - 1)
      if (currentChips?.date === data.value.dates[idx]) return
      updateChips(calcChips(data.value, idx, CYQ_DAYS))
    })
  })
  chart.on('datazoom', () => {
    const dz = chart.getOption().dataZoom[0]
    const s = dz.startValue ?? Math.round((dz.start / 100) * (n.value - 1))
    const e = dz.endValue ?? Math.round((dz.end / 100) * (n.value - 1))
    zoom = [s, e]
    const extent = priceExtent(s, e)
    chart.setOption({ yAxis: [extent, {}, {}, extent] })
  })
}

function updateChips(result) {
  currentChips = result
  chips.value = result
  chart?.setOption({ series: [
    { id: 'cyq', data: cyqSeriesData(result) },
    { id: 'cyq-avg', data: [[0, result.avgCost], [Math.max(...result.chips), result.avgCost]] },
  ] })
}

const attention = computed(() => state.attention.has(code))
async function onAttention() {
  try {
    await toggleAttention(code)
  } catch (e) {
    message.error(e.message)
  }
}
</script>

<template>
  <div class="page stock-page">
    <div class="toolbar head">
      <NButton quaternary circle size="small" @click="router.back()" aria-label="返回"><Icon name="back" /></NButton>
      <h1>{{ data?.name || code }} <span class="muted code">{{ code }}</span></h1>
      <template v-if="last">
        <span class="price" :class="trendClass(last.change)">{{ fmtNum(last.close) }}</span>
        <span class="chg" :class="trendClass(last.change)">{{ fmtPct(last.change) }}</span>
        <span class="muted small">{{ last.date }}</span>
      </template>
      <span class="spacer" />
      <GuideButton id="stock" />
      <NButton size="small" :type="attention ? 'warning' : 'default'" secondary @click="onAttention">
        {{ attention ? '★ 已关注' : '☆ 关注' }}
      </NButton>
      <NButton size="small" tag="a" :href="`https://quote.eastmoney.com/${market}${code}.html`" target="_blank" quaternary>
        行情<Icon name="external" :size="13" />
      </NButton>
      <NButton v-if="!isEtf" size="small" tag="a" quaternary target="_blank"
               :href="`https://emweb.securities.eastmoney.com/PC_HSF10/OperationsRequired/Index?code=${market.toUpperCase()}${code}`">
        资料<Icon name="external" :size="13" />
      </NButton>
    </div>

    <PageGuide id="stock" />
    <NEmpty v-if="error" :description="error" class="card" style="padding: 48px 0" />
    <NSpin v-else :show="!data" class="body">
      <div class="controls toolbar">
        <NSelect v-model:value="overlay" :options="overlayOptions" size="small" style="width: 128px" />
        <NSelect v-model:value="sub" :options="subOptions" size="small" style="width: 116px" />
        <label class="switch"><NSwitch v-model:value="showPatterns" size="small" /> K 线形态</label>
        <span class="muted small desc">{{ subConf?.desc }}</span>
      </div>
      <div class="layout">
        <div class="card chart-card">
          <EChart v-if="option" :option="option" @ready="onReady" />
        </div>
        <aside v-if="chips" class="card cyq">
          <div class="card-title">筹码分布 <span class="muted small">{{ chips.date }}</span></div>
          <div class="card-body">
            <div class="row"><span>获利比例</span><b>{{ fmtPercent(chips.profitRatio * 100) }}</b></div>
            <div class="profit-bar">
              <span class="win" :style="{ width: chips.profitRatio * 100 + '%' }" />
            </div>
            <div class="row"><span>平均成本</span><b>{{ fmtNum(chips.avgCost) }}</b></div>
            <div class="row"><span>90% 成本</span><b>{{ fmtNum(chips.p90.low) }} - {{ fmtNum(chips.p90.high) }}</b></div>
            <div class="row"><span>集中度</span><b>{{ fmtPercent(chips.p90.concentration * 100) }}</b></div>
            <div class="row"><span>70% 成本</span><b>{{ fmtNum(chips.p70.low) }} - {{ fmtNum(chips.p70.high) }}</b></div>
            <div class="row"><span>集中度</span><b>{{ fmtPercent(chips.p70.concentration * 100) }}</b></div>
            <div class="row muted"><span>统计交易日</span><span>{{ chips.days }}</span></div>
            <p class="muted tip">在 K 线上移动光标可查看任一天的筹码分布。</p>
          </div>
        </aside>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.stock-page { gap: 12px; }
.head h1 { display: flex; align-items: baseline; gap: 8px; }
.code { font-size: 13px; font-weight: 400; }
.price { font-size: 22px; font-weight: 700; }
.chg { font-weight: 600; }
.small { font-size: 12px; }
.body { flex: 1; }
.controls { margin-bottom: 10px; }
.switch { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.desc { flex: 1; min-width: 200px; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 240px; gap: 12px; }
.chart-card { height: calc(100vh - 210px); min-height: 520px; padding: 4px; }
.cyq .row { display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; }
.profit-bar { height: 8px; border-radius: 4px; background: rgba(79, 140, 255, 0.35); overflow: hidden; margin: 2px 0 6px; }
.profit-bar .win { display: block; height: 100%; background: var(--up); opacity: 0.75; }
.tip { font-size: 12px; margin: 10px 0 0; line-height: 1.5; }
@media (max-width: 1023px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 767px) {
  .price { font-size: 18px; }
  .chart-card { height: 72vh; min-height: 440px; }
  .desc { display: none; }
}
</style>
