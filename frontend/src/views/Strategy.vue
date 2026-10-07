<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NDatePicker, NEmpty, NSelect, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import DataGrid from '../components/DataGrid.vue'
import Icon from '../components/Icon.vue'
import { api } from '../api'
import { fmtPct, fmtPercent, trendClass } from '../format'
import { loadMeta, state } from '../store'

const route = useRoute()
const router = useRouter()
const message = useMessage()
document.title = '策略选股 · InStock'

const tab = ref(route.query.tab === 'backtest' ? 'backtest' : 'signals')
const strategy = ref(route.query.key || 'all')
const signals = ref(null)
const backtest = ref(null)
const loading = ref(false)
const date = ref(null)
const grid = ref(null)
const count = ref({ shown: 0, total: 0 })

loadMeta()
const strategies = computed(() => state.meta?.strategies || [])
const current = computed(() => strategies.value.find((s) => s.key === strategy.value))
const options = computed(() => [{ label: '全部策略', value: 'all' }, ...strategies.value.map((s) => ({ label: s.name, value: s.key }))])
const dateSet = computed(() => new Set(signals.value?.dates || []))

const strategyIdx = computed(() => signals.value?.columns.findIndex((c) => c.name === 'strategy') ?? -1)
const rows = computed(() => {
  if (!signals.value) return []
  const i = strategyIdx.value
  const names = Object.fromEntries(strategies.value.map((s) => [s.key, s.name]))
  return signals.value.rows
    .filter((r) => strategy.value === 'all' || r[i] === strategy.value)
    .map((r) => r.map((v, j) => (j === i ? names[v] || v : v)))
})

function toDateString(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function loadSignals(day) {
  loading.value = true
  try {
    signals.value = await api.signals(day)
    date.value = signals.value.date
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function loadBacktest() {
  if (backtest.value) return
  try {
    backtest.value = await api.backtest()
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  }
}

watch(date, (value, old) => { if (old && value && value !== signals.value?.date) loadSignals(value) })
function syncQuery() {
  const query = {}
  if (strategy.value !== 'all') query.key = strategy.value
  if (tab.value === 'backtest') query.tab = 'backtest'
  router.replace({ query })
}

watch(strategy, syncQuery)
watch(tab, (t) => {
  syncQuery()
  if (t === 'backtest') loadBacktest()
}, { immediate: true })
loadSignals()

const backtestRows = computed(() => {
  const list = backtest.value?.strategies || []
  const order = strategies.value.map((s) => s.key)
  return [...list].sort((a, b) => order.indexOf(a.strategy) - order.indexOf(b.strategy))
})
const kindOf = (key) => strategies.value.find((s) => s.key === key)?.kind
</script>

<template>
  <div class="page page-fill strategy-page">
    <div class="toolbar">
      <h1>策略选股</h1>
      <NSelect v-model:value="strategy" :options="options" size="small" style="width: 180px" />
    </div>

    <div v-if="current" class="card intro">
      <div class="intro-head">
        <strong>{{ current.name }}</strong>
        <span class="badge" :class="current.kind">{{ current.kind === 'sell' ? '风险信号' : '买入信号' }}</span>
      </div>
      <p>{{ current.rule }}</p>
      <p class="muted source">出处：{{ current.source }}</p>
    </div>

    <NTabs v-model:value="tab" type="segment" size="small" class="tabs">
      <NTabPane name="signals" tab="每日信号" display-directive="show">
        <div class="toolbar sub">
          <NDatePicker v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small"
                       :is-date-disabled="(ts) => !dateSet.has(toDateString(ts))" :disabled="!signals?.dates.length"
                       style="width: 140px" placeholder="暂无数据" />
          <span class="muted small">收益列为信号次日开盘买入、持有 N 个交易日后的收益，数据随时间自动补齐</span>
          <span class="spacer" />
          <span class="muted small">{{ count.shown }} / {{ count.total }} 条</span>
          <NButton size="small" @click="grid?.exportCsv(`策略选股_${date}`)">
            <template #icon><Icon name="download" :size="15" /></template>导出
          </NButton>
        </div>
        <NSpin :show="loading" class="grid-wrap card">
          <DataGrid v-if="signals" ref="grid" :columns="signals.columns" :rows="rows" :sort="['strategy', false]"
                    @count="count = $event" />
        </NSpin>
      </NTabPane>
      <NTabPane name="backtest" tab="回测统计">
        <div class="card backtest">
          <NSpin :show="!backtest">
            <NEmpty v-if="backtest && !backtestRows.length" description="暂无回测数据" style="padding: 40px 0" />
            <div v-else class="scroll">
              <table class="bt">
                <thead>
                  <tr>
                    <th class="l" rowspan="2">策略</th>
                    <th rowspan="2">信号数</th>
                    <th v-for="h in backtest?.horizons" :key="h" colspan="2">{{ h }} 日</th>
                  </tr>
                  <tr>
                    <template v-for="h in backtest?.horizons" :key="h"><th>平均</th><th>胜率</th></template>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="backtest?.benchmark" class="bench">
                    <td class="l">全市场等权基准</td>
                    <td class="muted">—</td>
                    <template v-for="b in backtest.benchmark" :key="b.horizon">
                      <td :class="trendClass(b.mean)">{{ fmtPct(b.mean) }}<div class="muted tiny">{{ b.n }} 天</div></td>
                      <td class="muted">—</td>
                    </template>
                  </tr>
                  <tr v-for="r in backtestRows" :key="r.strategy" :class="{ active: r.strategy === strategy }"
                      @click="strategy = r.strategy">
                    <td class="l">{{ r.name }} <span v-if="kindOf(r.strategy) === 'sell'" class="badge sell">风险</span></td>
                    <td>{{ r.signals }}<div class="muted tiny">{{ r.days }} 天</div></td>
                    <template v-for="s in r.stats" :key="s.horizon">
                      <td>
                        <span :class="trendClass(s.mean)">{{ fmtPct(s.mean) }}</span>
                        <div class="tiny" :class="trendClass(s.excess)" :title="`相对基准超额收益，样本 ${s.n}`">超额 {{ fmtPct(s.excess) || '-' }}</div>
                      </td>
                      <td>{{ fmtPercent(s.win, 1) }}</td>
                    </template>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="muted small note">
              统计口径：信号日收盘后决策，次日开盘价买入，持有 N 个交易日按收盘价计算收益；超额收益为信号收益减去同日
              全市场等权基准（全部 A 股按同样口径计算的平均收益）。未扣除交易费用，也未考虑涨跌停无法成交等情况，
              历史统计不代表未来表现。
            </p>
          </NSpin>
        </div>
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
.strategy-page { gap: 12px; }
.intro { padding: 12px 16px; }
.intro p { margin: 6px 0 0; line-height: 1.6; }
.intro-head { display: flex; align-items: center; gap: 8px; }
.source { font-size: 12px; }
.badge { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: var(--up-soft); color: var(--up); font-weight: 500; }
.badge.sell { background: var(--down-soft); color: var(--down); }
.tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.tabs :deep(.n-tabs-pane-wrapper), .tabs :deep(.n-tab-pane) { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.sub { margin-top: 4px; }
.small { font-size: 12px; }
.tiny { font-size: 11px; }
.grid-wrap { flex: 1; min-height: 320px; overflow: hidden; }
.grid-wrap :deep(.n-spin-content) { height: 100%; }
.backtest { padding: 8px 0; }
.scroll { overflow-x: auto; }
.bt { border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }
.bt th, .bt td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--border); }
.bt th { color: var(--muted); font-weight: 500; font-size: 12px; }
.bt .l { text-align: left; position: sticky; left: 0; background: var(--surface); }
.bt tbody tr { cursor: pointer; }
.bt tbody tr:hover td, .bt tr.active td { background: var(--surface-2); }
.bt tr.bench td { background: var(--surface-2); font-weight: 500; cursor: default; }
.note { padding: 8px 16px 4px; margin: 0; line-height: 1.6; }
@media (max-width: 767px) {
  .sub .small:not(:last-child) { display: none; }
}
</style>
