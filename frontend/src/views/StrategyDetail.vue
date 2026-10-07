<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { NButton, NDatePicker, NEmpty, NInput, NSpin, NSwitch, NTabPane, NTabs, useMessage } from 'naive-ui'
import DataGrid from '../components/DataGrid.vue'
import Icon from '../components/Icon.vue'
import { api } from '../api'
import { fmtPct, fmtPercent, toDateString, trendClass } from '../format'
import { loadMeta, state } from '../store'
import {
  BASIS_LABELS, HEADLINE_HORIZON, KIND_LABELS, PAIRED, backtest, backtestOf, headlineStat, hitRate, hitRateLabel,
  loadBacktest,
} from '../strategy'

const route = useRoute()
const message = useMessage()
const key = route.params.key
const tab = ref('signals')
const signals = ref(null)
const loading = ref(false)
const date = ref(null)
const keyword = ref('')
const onlyAttention = ref(false)
const count = ref({ shown: 0, total: 0 })
const grid = ref(null)
const btError = ref('')

loadMeta()
loadBacktest().catch((e) => { btError.value = e.message })
const strategy = computed(() => state.meta?.strategies.find((s) => s.key === key))
const pair = computed(() => state.meta?.strategies.find((s) => s.key === PAIRED[key]))
const kind = computed(() => strategy.value?.kind || 'buy')
const dateSet = computed(() => new Set(signals.value?.dates || []))
watch(strategy, (s) => { if (s) document.title = `${s.name} · InStock` }, { immediate: true })

async function loadSignals(day) {
  loading.value = true
  try {
    signals.value = await api.signals(day, key)
    date.value = signals.value.date
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

watch(date, (value, old) => { if (old && value && value !== signals.value?.date) loadSignals(value) })
loadSignals()

const bt = computed(() => backtestOf(key))
const headline = computed(() => headlineStat(key))
const horizon = computed(() => headline.value?.horizon ?? HEADLINE_HORIZON)
const benchmark = computed(() => Object.fromEntries((backtest.value?.benchmark || []).map((b) => [b.horizon, b])))
</script>

<template>
  <div class="page page-fill strategy-detail">
    <nav class="crumbs">
      <RouterLink :to="`/strategies/${kind}`">{{ KIND_LABELS[kind] }}</RouterLink>
      <span class="muted">/</span>
      <span>{{ strategy?.name || key }}</span>
    </nav>

    <NEmpty v-if="state.meta && !strategy" description="没有这个策略" class="card" style="padding: 48px 0" />

    <template v-else-if="strategy">
      <section class="card intro">
        <div class="intro-head">
          <h1>{{ strategy.name }}</h1>
          <span class="badge" :class="kind">{{ kind === 'sell' ? '卖出 / 风险信号' : '买入信号' }}</span>
          <span class="tag">{{ BASIS_LABELS[strategy.basis] }}</span>
        </div>
        <p class="plain">{{ strategy.plain }}</p>
        <dl>
          <dt>规则</dt><dd>{{ strategy.rule }}</dd>
          <template v-if="strategy.tips"><dt>使用提示</dt><dd>{{ strategy.tips }}</dd></template>
          <template v-if="pair"><dt>配套策略</dt><dd><RouterLink :to="`/strategy/${pair.key}`">{{ pair.name }}</RouterLink>（{{ KIND_LABELS[pair.kind] }}）</dd></template>
          <dt>出处</dt><dd class="muted">{{ strategy.source }}</dd>
        </dl>
        <div class="metrics">
          <div><span class="label">当日信号</span><span class="value">{{ signals ? signals.rows.length : '—' }}</span></div>
          <div><span class="label">历史信号</span><span class="value">{{ bt?.signals ?? '—' }}</span><span class="sub muted" v-if="bt">{{ bt.days }} 个交易日</span></div>
          <div><span class="label">{{ horizon }}日平均收益</span><span class="value" :class="trendClass(headline?.mean)">{{ fmtPct(headline?.mean) || '—' }}</span></div>
          <div><span class="label">{{ horizon }}日超额</span><span class="value" :class="trendClass(headline?.excess)">{{ fmtPct(headline?.excess) || '—' }}</span></div>
          <div><span class="label">{{ horizon }}日{{ hitRateLabel(kind) }}</span><span class="value">{{ fmtPercent(hitRate(headline, kind), 1) || '—' }}</span></div>
        </div>
      </section>

      <NTabs v-model:value="tab" type="line" size="small" class="tabs">
        <NTabPane name="signals" tab="信号列表" display-directive="show">
          <div class="toolbar sub">
            <NDatePicker v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small"
                         :is-date-disabled="(ts) => !dateSet.has(toDateString(ts))" :disabled="!signals?.dates.length"
                         style="width: 140px" placeholder="暂无数据" />
            <NInput v-model:value="keyword" size="small" clearable placeholder="筛选代码/名称" class="filter">
              <template #prefix><Icon name="search" :size="15" /></template>
            </NInput>
            <label class="switch"><NSwitch v-model:value="onlyAttention" size="small" /> 只看关注</label>
            <span class="spacer" />
            <span class="muted small">{{ count.shown }} / {{ count.total }} 条</span>
            <NButton size="small" @click="grid?.exportCsv(`${strategy.name}_${date}`)">
              <template #icon><Icon name="download" :size="15" /></template>导出
            </NButton>
          </div>
          <p class="muted small hint">N 日收益：信号次日开盘买入、持有 N 个交易日后的收益，尚未走完的周期为空，会随时间自动补齐。</p>
          <NSpin :show="loading" class="grid-wrap card">
            <DataGrid v-if="signals" ref="grid" :columns="signals.columns" :rows="signals.rows" :hidden="['date', 'strategy']"
                      :quick-filter="keyword" :only-attention="onlyAttention" @count="count = $event" />
          </NSpin>
        </NTabPane>
        <NTabPane name="backtest" tab="历史表现">
          <div class="card perf">
            <NEmpty v-if="btError || (backtest && !bt)" :description="btError || '这个策略还没有历史信号'" style="padding: 40px 0" />
            <NSpin v-else :show="!backtest">
              <div class="scroll">
                <table class="bt">
                  <thead>
                    <tr><th class="l">持有期</th><th>样本</th><th>平均收益</th><th>中位收益</th><th>{{ hitRateLabel(kind) }}</th><th>基准收益</th><th>超额收益</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in bt?.stats || []" :key="s.horizon">
                      <td class="l">{{ s.horizon }} 日</td>
                      <td>{{ s.n }}</td>
                      <td :class="trendClass(s.mean)">{{ fmtPct(s.mean) || '—' }}</td>
                      <td :class="trendClass(s.median)">{{ fmtPct(s.median) || '—' }}</td>
                      <td>{{ fmtPercent(hitRate(s, kind), 1) || '—' }}</td>
                      <td class="muted">{{ fmtPct(benchmark[s.horizon]?.mean) || '—' }}</td>
                      <td :class="trendClass(s.excess)"><b>{{ fmtPct(s.excess) || '—' }}</b></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="muted small note">
                <template v-if="kind === 'sell'">
                  卖出信号的收益表示“如果继续持有”的结果。超额收益为负（绿色）说明信号出现后股价跑输市场，及时卖出能避免损失；
                  超额接近 0 说明信号区分能力有限。
                </template>
                <template v-else>
                  超额收益为正说明这个策略选出的股票比同日随便买一只表现更好。中位收益比平均收益更能反映“典型”信号的结果，
                  两者差距大说明收益集中在少数大涨股上。
                </template>
                未扣除交易费用，也未考虑涨跌停无法成交，历史表现不代表未来。
                <RouterLink :to="{ path: '/learn', hash: '#backtest' }">如何看回测 →</RouterLink>
              </p>
            </NSpin>
          </div>
        </NTabPane>
      </NTabs>
    </template>
  </div>
</template>

<style scoped>
.strategy-detail { gap: 12px; }
.crumbs { display: flex; gap: 6px; font-size: 13px; }
.intro { padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; }
.intro-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.intro-head h1 { font-size: 18px; margin: 0 4px 0 0; }
.badge { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: var(--up-soft); color: var(--up); font-weight: 500; }
.badge.sell { background: var(--down-soft); color: var(--down); }
.tag { font-size: 11px; padding: 0 6px; border-radius: 4px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
.plain { margin: 0; font-size: 14px; line-height: 1.7; }
dl { display: grid; grid-template-columns: 72px 1fr; gap: 4px 12px; margin: 0; font-size: 13px; line-height: 1.7; }
dt { color: var(--muted); }
dd { margin: 0; }
.metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
.metrics div { display: flex; flex-direction: column; gap: 2px; }
.metrics .label { font-size: 12px; color: var(--muted); }
.metrics .value { font-size: 18px; font-weight: 650; }
.metrics .sub { font-size: 11px; }
.tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.tabs :deep(.n-tabs-pane-wrapper), .tabs :deep(.n-tab-pane) { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
.filter { width: 180px; }
.switch { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.small { font-size: 12px; }
.hint { margin: 0; }
.grid-wrap { flex: 1; min-height: 360px; overflow: hidden; }
.grid-wrap :deep(.n-spin-content) { height: 100%; }
.perf { padding: 4px 0; }
.scroll { overflow-x: auto; }
.bt { border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }
.bt th, .bt td { padding: 9px 12px; text-align: right; border-bottom: 1px solid var(--border); }
.bt th { color: var(--muted); font-weight: 500; font-size: 12px; }
.bt .l { text-align: left; }
.note { padding: 8px 16px 12px; margin: 0; line-height: 1.7; }
@media (max-width: 767px) {
  dl { grid-template-columns: 1fr; gap: 0; }
  dt { margin-top: 6px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics div:nth-child(2) { display: none; }
  .filter { width: 100%; order: 10; }
  .hint { display: none; }
}
</style>
