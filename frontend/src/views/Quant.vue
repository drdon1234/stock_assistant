<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  NButton, NDatePicker, NEmpty, NInput, NInputNumber, NProgress, NSelect, NSpin, NTabPane, NTabs, NTag, useDialog,
  useMessage,
} from 'naive-ui'
import DataGrid from '../components/DataGrid.vue'
import EChart from '../components/EChart.vue'
import GuideButton from '../components/GuideButton.vue'
import Icon from '../components/Icon.vue'
import PageGuide from '../components/PageGuide.vue'
import { api } from '../api'
import { SERIES_COLORS, colors } from '../colors'
import { fmtNum, fmtPct, toDateString, trendClass } from '../format'

const TEMPLATE = `# 示例：每周一买入沪深300中过去20日涨幅最大的10只股票（聚宽写法，可整段替换为自己的策略）
from jqdata import *


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(close_tax=0.0005, open_commission=0.0003, close_commission=0.0003,
                             min_commission=5), type='stock')
    g.count = 10
    run_weekly(rebalance, 1, time='open')


def rebalance(context):
    current = get_current_data()
    stocks = [s for s in get_index_stocks('000300.XSHG') if not current[s].paused and not current[s].is_st]
    prices = history(21, '1d', 'close', stocks)
    momentum = (prices.iloc[-1] / prices.iloc[0] - 1).dropna().sort_values(ascending=False)
    targets = list(momentum.index[:g.count])
    for s in list(context.portfolio.positions):
        if s not in targets:
            order_target_value(s, 0)
    for s in targets:
        order_target_value(s, context.portfolio.total_value / g.count)
    record(持仓数=len(context.portfolio.positions))
`

const STATES = {
  queued: ['排队中', 'default'], running: ['运行中', 'info'], done: ['已完成', 'success'],
  failed: ['失败', 'error'], canceled: ['已取消', 'warning'],
}
const METRICS = [
  ['total_return', '策略收益', 'pct'], ['annual_return', '年化收益', 'pct'], ['benchmark_return', '基准收益', 'pct'],
  ['excess_return', '超额收益', 'pct'], ['alpha', 'Alpha', 'num'], ['beta', 'Beta', 'num'],
  ['sharpe', '夏普比率', 'num'], ['sortino', '索提诺比率', 'num'], ['information_ratio', '信息比率', 'num'],
  ['volatility', '策略波动率', 'abs'], ['max_drawdown', '最大回撤', 'abs'], ['win_ratio', '胜率', 'ratio'],
  ['daily_win_ratio', '日胜率', 'ratio'], ['profit_loss_ratio', '盈亏比', 'num'], ['trades', '交易次数', 'int'],
]
const TRADE_COLUMNS = [
  { name: 'time', label: '时间', fmt: 'text' }, { name: 'security', label: '代码', fmt: 'text' },
  { name: 'name', label: '名称', fmt: 'text' }, { name: 'side', label: '方向', fmt: 'text' },
  { name: 'amount', label: '数量', fmt: 'int' }, { name: 'price', label: '成交价', fmt: 'price' },
  { name: 'value', label: '成交额', fmt: 'money' }, { name: 'commission', label: '佣金', fmt: 'num' },
  { name: 'tax', label: '印花税', fmt: 'num' }, { name: 'pnl', label: '平仓盈亏', fmt: 'num' },
]

const message = useMessage()
const dialog = useDialog()
document.title = '聚宽策略回测 · InStock'

const status = ref(null)
const jobs = ref([])
const selected = ref(null) // 任务 id；null 表示新建
const job = ref(null)
const loadingJob = ref(false)
const form = ref({ name: '我的策略', range: null, capital: 1000000, benchmark: '000300.XSHG', code: TEMPLATE })
const report = ref(null)
const submitting = ref(false)
const fileInput = ref(null)
const tab = ref('overview')
let timer = null

const benchmarks = computed(() => (status.value?.benchmarks || []).map((b) => ({ label: `${b.name} ${b.code}`, value: b.code })))
const dataRange = computed(() => status.value?.data)
const blocker = computed(() => {
  const s = status.value
  if (!s) return ''
  if (!s.data.ready) return '回测数据尚未准备好：管理员需先运行 python -m instock quant sync 回补历史数据（首次约数小时）。'
  if (!s.runner.alive) return '回测服务未运行：Docker 部署请启动 instock-backtest 容器，本地运行请执行 python -m instock quant runner。'
  if (!s.can_run) return '回测服务没有启用沙箱，只有管理员可以运行回测。'
  return ''
})
const outOfRange = (ts) => !!dataRange.value?.start && (toDateString(ts) < dataRange.value.start || toDateString(ts) > dataRange.value.end)
const active = computed(() => ['queued', 'running'].includes(job.value?.status?.state))

async function loadStatus() {
  try {
    status.value = await api.quantStatus()
    if (!form.value.range && status.value.data.end) {
      const end = status.value.data.end
      const start = `${Number(end.slice(0, 4)) - 3}${end.slice(4)}`
      form.value.range = [start < status.value.data.start ? status.value.data.start : start, end]
    }
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  }
}

async function loadJobs() {
  try {
    jobs.value = (await api.quantJobs()).items
  } catch (e) {
    message.error(`加载回测列表失败：${e.message}`)
  }
}

async function loadJob(id, quiet = false) {
  if (!quiet) loadingJob.value = true
  try {
    const data = await api.quantJob(id)
    if (selected.value === id) job.value = data
  } catch (e) {
    message.error(e.message)
  } finally {
    loadingJob.value = false
  }
}

function select(id) {
  selected.value = id
  job.value = null
  tab.value = 'overview'
  if (id) loadJob(id)
}

// 排队或运行中的任务每 2 秒刷新一次
watch(active, (on) => {
  clearInterval(timer)
  if (on) {
    timer = setInterval(async () => {
      await loadJob(selected.value, true)
      if (!active.value) loadJobs()
    }, 2000)
  }
})
onBeforeUnmount(() => clearInterval(timer))

function importFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    form.value.code = String(reader.result)
    form.value.name = file.name.replace(/\.(py|txt)$/i, '')
    report.value = null
  }
  reader.readAsText(file, 'utf-8')
  event.target.value = ''
}

async function runCheck() {
  try {
    report.value = await api.quantCheck(form.value.code)
    if (!report.value.errors.length && !report.value.warnings.length) message.success('没有发现兼容性问题')
  } catch (e) {
    message.error(e.message)
  }
}

async function submit() {
  if (!form.value.range) return message.warning('请选择回测区间')
  submitting.value = true
  try {
    const [start, end] = form.value.range
    const res = await api.quantSubmit({ name: form.value.name, code: form.value.code, start, end,
      capital: form.value.capital, benchmark: form.value.benchmark })
    report.value = res.check
    if (!res.job) return message.error('策略有错误，请先修改')
    message.success('已提交回测')
    await loadJobs()
    select(res.job.id)
  } catch (e) {
    message.error(e.message)
  } finally {
    submitting.value = false
  }
}

function copyToEditor() {
  form.value = { name: `${job.value.name} 副本`, range: [job.value.start, job.value.end], capital: job.value.capital,
    benchmark: job.value.benchmark, code: job.value.code }
  report.value = null
  select(null)
}

function remove(item) {
  const running = ['queued', 'running'].includes(item.status.state)
  dialog.warning({
    title: running ? '取消回测' : '删除回测',
    content: running ? `确定取消“${item.name}”？` : `确定删除“${item.name}”及其结果？`,
    positiveText: running ? '取消回测' : '删除', negativeText: '返回',
    onPositiveClick: async () => {
      try {
        await api.quantRemove(item.id)
        if (!running && selected.value === item.id) select(null)
        else if (selected.value === item.id) loadJob(item.id, true)
        loadJobs()
      } catch (e) {
        message.error(e.message)
      }
    },
  })
}

function fmtMetric(value, kind) {
  if (value === null || value === undefined) return '—'
  if (kind === 'pct') return fmtPct(value * 100)
  if (kind === 'abs') return `${(value * 100).toFixed(2)}%`
  if (kind === 'ratio') return `${(value * 100).toFixed(1)}%`
  if (kind === 'int') return String(value)
  return fmtNum(value, 3)
}
const metricClass = (value, kind) => (kind === 'pct' ? trendClass(value) : '')

const result = computed(() => job.value?.result)
const pct = (arr) => arr.map((v) => (v === null ? null : +(v * 100).toFixed(3)))

const chartOption = computed(() => {
  const r = result.value
  if (!r) return null
  const c = colors.value
  const d = r.daily
  return {
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v) => (v === null || v === undefined ? '—' : `${v.toFixed(2)}%`) },
    legend: { data: ['策略收益', '基准收益', '回撤'], top: 0, textStyle: { color: c.muted } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [{ left: 56, right: 16, top: 30, height: '58%' }, { left: 56, right: 16, top: '74%', bottom: 40 }],
    xAxis: [
      { type: 'category', data: d.dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: c.grid } } },
      { type: 'category', data: d.dates, gridIndex: 1, axisLabel: { color: c.muted }, axisLine: { lineStyle: { color: c.grid } } },
    ],
    yAxis: [
      { scale: true, axisLabel: { color: c.muted, formatter: '{value}%' }, splitLine: { lineStyle: { color: c.grid } } },
      { gridIndex: 1, max: 0, axisLabel: { color: c.muted, formatter: '{value}%' }, splitLine: { lineStyle: { color: c.grid } } },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }, { type: 'slider', xAxisIndex: [0, 1], height: 18, bottom: 6 }],
    series: [
      { name: '策略收益', type: 'line', data: pct(d.returns), showSymbol: false, lineStyle: { width: 1.6 }, color: c.primary },
      { name: '基准收益', type: 'line', data: pct(d.benchmark), showSymbol: false, lineStyle: { width: 1.2 }, color: SERIES_COLORS[0] },
      { name: '回撤', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: pct(d.drawdown), showSymbol: false,
        lineStyle: { width: 1 }, areaStyle: { opacity: 0.25 }, color: c.down },
    ],
  }
})

const recordOption = computed(() => {
  const r = result.value
  const names = Object.keys(r?.records || {})
  if (!names.length) return null
  const c = colors.value
  return {
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: names, top: 0, textStyle: { color: c.muted } },
    grid: { left: 56, right: 16, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: r.daily.dates, axisLabel: { color: c.muted } },
    yAxis: { scale: true, axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.grid } } },
    dataZoom: [{ type: 'inside' }],
    series: names.map((n, i) => ({ name: n, type: 'line', data: r.records[n], showSymbol: false, connectNulls: true,
      color: SERIES_COLORS[(i + 1) % SERIES_COLORS.length] })),
  }
})

const statusLabel = (s) => STATES[s?.state] || [s?.state || '', 'default']
const jobReturn = (item) => item.status?.summary?.total_return

loadStatus()
loadJobs()
</script>

<template>
  <div class="page quant">
    <div class="toolbar">
      <h1>聚宽策略回测</h1><GuideButton id="quant" />
      <span v-if="dataRange?.ready" class="muted small">数据 {{ dataRange.start }} ~ {{ dataRange.end }}</span>
    </div>
    <PageGuide id="quant" />
    <div v-if="blocker" class="card notice">{{ blocker }}</div>

    <div class="layout">
      <aside class="card jobs">
        <div class="card-title">
          <span>我的回测</span>
          <NButton size="small" type="primary" :secondary="selected !== null" @click="select(null)">
            <template #icon><Icon name="arrow" :size="15" /></template>新建
          </NButton>
        </div>
        <NEmpty v-if="!jobs.length" description="还没有回测" style="padding: 24px 0" />
        <button v-for="item in jobs" :key="item.id" class="job" :class="{ on: selected === item.id }" @click="select(item.id)">
          <span class="job-name">{{ item.name }}</span>
          <span class="job-meta">
            <NTag size="tiny" :bordered="false" :type="statusLabel(item.status)[1]">{{ statusLabel(item.status)[0] }}</NTag>
            <span v-if="jobReturn(item) !== undefined" :class="trendClass(jobReturn(item))">{{ fmtPct(jobReturn(item) * 100) }}</span>
            <span class="muted">{{ item.start.slice(0, 7) }} ~ {{ item.end.slice(0, 7) }}</span>
          </span>
        </button>
      </aside>

      <section v-if="selected === null" class="card editor">
        <div class="form">
          <label><span>名称</span><NInput v-model:value="form.name" maxlength="60" size="small" /></label>
          <label><span>回测区间</span>
            <NDatePicker v-model:formatted-value="form.range" type="daterange" value-format="yyyy-MM-dd" size="small"
                         :is-date-disabled="outOfRange" />
          </label>
          <label><span>初始资金</span>
            <NInputNumber v-model:value="form.capital" :min="1000" :step="100000" size="small" :show-button="false">
              <template #suffix>元</template>
            </NInputNumber>
          </label>
          <label><span>基准</span><NSelect v-model:value="form.benchmark" :options="benchmarks" size="small" /></label>
        </div>
        <div class="code-head">
          <span class="muted small">粘贴聚宽策略代码，或导入 .py 文件。只支持日线回测，财务、行业与分钟数据暂不可用。</span>
          <span class="spacer" />
          <input ref="fileInput" type="file" accept=".py,.txt" hidden @change="importFile" />
          <NButton size="small" @click="fileInput.click()">导入文件</NButton>
          <NButton size="small" @click="runCheck">检查兼容性</NButton>
          <NButton size="small" type="primary" :loading="submitting" :disabled="!!blocker" @click="submit">运行回测</NButton>
        </div>
        <div v-if="report && (report.errors.length || report.warnings.length || report.notes.length)" class="report">
          <div v-for="(item, i) in report.errors" :key="`e${i}`" class="down">✕ {{ item.line ? `第 ${item.line} 行：` : '' }}{{ item.message }}</div>
          <div v-for="(item, i) in report.warnings" :key="`w${i}`" class="warn">! {{ item.line ? `第 ${item.line} 行：` : '' }}{{ item.message }}</div>
          <div v-for="(item, i) in report.notes" :key="`n${i}`" class="muted">· {{ item.line ? `第 ${item.line} 行：` : '' }}{{ item.message }}</div>
        </div>
        <NInput v-model:value="form.code" type="textarea" class="code" :autosize="{ minRows: 18, maxRows: 40 }"
                spellcheck="false" placeholder="def initialize(context): ..." />
      </section>

      <section v-else class="detail">
        <NSpin :show="loadingJob && !job">
          <template v-if="job">
            <div class="card head">
              <div class="head-title">
                <h2>{{ job.name }}</h2>
                <NTag size="small" :bordered="false" :type="statusLabel(job.status)[1]">{{ statusLabel(job.status)[0] }}</NTag>
                <span class="spacer" />
                <NButton size="small" @click="copyToEditor">复制为新回测</NButton>
                <NButton size="small" @click="remove(job)">{{ active ? '取消' : '删除' }}</NButton>
              </div>
              <div class="muted small">
                {{ job.start }} ~ {{ job.end }} · 初始资金 {{ job.capital.toLocaleString() }} 元 · 基准 {{ job.benchmark }}
                · 提交于 {{ job.created }}<template v-if="job.status.elapsed"> · 用时 {{ job.status.elapsed }} 秒</template>
              </div>
              <div v-if="active" class="progress">
                <NProgress type="line" :percentage="Math.round((job.status.progress || 0) * 100)" :show-indicator="true" />
                <span class="muted small">{{ job.status.state === 'queued' ? '等待运行器执行…' : `已回测到 ${job.status.date || job.start}` }}</span>
              </div>
              <div v-if="job.status.state === 'failed' || job.status.state === 'canceled'" class="error">
                <b>{{ job.status.error }}</b>
                <div v-for="(f, i) in job.status.traceback || []" :key="i" class="mono">第 {{ f.line }} 行 {{ f.function }}：{{ f.code }}</div>
                <pre v-if="job.status.logs?.length" class="logs">{{ job.status.logs.join('\n') }}</pre>
              </div>
            </div>

            <template v-if="result">
              <div class="card metrics">
                <div v-for="[key, label, kind] in METRICS" :key="key">
                  <span class="label">{{ label }}</span>
                  <span class="value" :class="metricClass(result.summary[key], kind)">{{ fmtMetric(result.summary[key], kind) }}</span>
                </div>
              </div>
              <NTabs v-model:value="tab" type="line" size="small">
                <NTabPane name="overview" tab="收益曲线">
                  <div class="card chart"><EChart :option="chartOption" /></div>
                  <div v-if="recordOption" class="card chart small-chart"><EChart :option="recordOption" /></div>
                  <p class="muted small note">
                    最大回撤区间 {{ result.summary.max_drawdown_start || '—' }} ~ {{ result.summary.max_drawdown_end || '—' }}；
                    年化按 250 个交易日、无风险利率 4% 计算。
                  </p>
                </NTabPane>
                <NTabPane name="trades" :tab="`交易记录 ${result.trades.length}`" display-directive="show:lazy">
                  <div class="card grid-wrap">
                    <DataGrid :columns="TRADE_COLUMNS" :rows="result.trades" :hidden="[]" />
                  </div>
                  <p v-if="result.trades_truncated" class="muted small note">交易记录过多，只保留前 50000 条。</p>
                </NTabPane>
                <NTabPane name="positions" tab="期末持仓">
                  <div class="card scroll">
                    <table class="plain-table">
                      <thead><tr><th class="l">代码</th><th class="l">名称</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th></tr></thead>
                      <tbody>
                        <tr v-for="p in result.positions" :key="p.code">
                          <td class="l">{{ p.code }}</td><td class="l">{{ p.name }}</td><td>{{ p.amount }}</td>
                          <td>{{ fmtNum(p.avg_cost, 3) }}</td><td>{{ fmtNum(p.price, 3) }}</td><td>{{ fmtNum(p.value) }}</td>
                        </tr>
                        <tr v-if="!result.positions.length"><td colspan="6" class="muted l">期末空仓</td></tr>
                      </tbody>
                    </table>
                  </div>
                </NTabPane>
                <NTabPane name="logs" tab="日志">
                  <pre class="card logs">{{ result.logs.join('\n') || '没有日志' }}<template v-if="result.logs_dropped">
… 另有 {{ result.logs_dropped }} 条日志未保留</template></pre>
                </NTabPane>
                <NTabPane name="code" tab="策略代码">
                  <pre class="card logs">{{ job.code }}</pre>
                </NTabPane>
              </NTabs>
            </template>
          </template>
        </NSpin>
      </section>
    </div>
  </div>
</template>

<style scoped>
.quant { gap: 12px; }
.small { font-size: 12px; }
.notice { padding: 10px 14px; font-size: 13px; border-left: 3px solid #f59f00; }
.layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 12px; align-items: start; }
.jobs { display: flex; flex-direction: column; max-height: calc(100vh - 150px); overflow: auto; }
.job {
  display: flex; flex-direction: column; gap: 4px; padding: 9px 14px; border: 0; border-top: 1px solid var(--border);
  background: none; color: inherit; font: inherit; text-align: left; cursor: pointer;
}
.job:hover { background: var(--surface-2); }
.job.on { background: var(--surface-2); box-shadow: inset 3px 0 0 var(--primary); }
.job-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.editor { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.form { display: grid; grid-template-columns: 1.2fr 1.6fr 1fr 1.2fr; gap: 10px; }
.form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.code-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.spacer { flex: 1; }
.code :deep(textarea), .mono, .logs { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace; font-size: 12.5px; }
.report { font-size: 13px; line-height: 1.8; padding: 8px 12px; border-radius: 8px; background: var(--surface-2); }
.warn { color: #d9480f; }
.detail { min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.detail :deep(.n-spin-content) { display: flex; flex-direction: column; gap: 12px; }
.head { padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; }
.head-title { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.head-title h2 { font-size: 17px; margin: 0; }
.progress { display: flex; flex-direction: column; gap: 4px; }
.error { font-size: 13px; color: var(--down); display: flex; flex-direction: column; gap: 4px; }
.error b { color: var(--up); }
.metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px 16px; padding: 14px 16px; }
.metrics div { display: flex; flex-direction: column; gap: 2px; }
.metrics .label { font-size: 12px; color: var(--muted); }
.metrics .value { font-size: 17px; font-weight: 650; }
.chart { height: 400px; padding: 8px 4px 0; }
.small-chart { height: 220px; margin-top: 12px; }
.note { margin: 8px 2px 0; }
.grid-wrap { height: 480px; overflow: hidden; }
.scroll { overflow-x: auto; }
.plain-table { border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }
.plain-table th, .plain-table td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border); }
.plain-table th { color: var(--muted); font-weight: 500; font-size: 12px; }
.plain-table .l { text-align: left; }
.logs { margin: 0; padding: 12px 14px; max-height: 520px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
@media (max-width: 1100px) {
  .form { grid-template-columns: 1fr 1fr; }
  .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .layout { grid-template-columns: 1fr; }
  .jobs { max-height: 260px; }
  .form { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .chart { height: 320px; }
}
</style>
