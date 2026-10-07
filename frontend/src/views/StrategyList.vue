<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NDatePicker, NEmpty, NSkeleton, NSpin, useMessage } from 'naive-ui'
import GuideButton from '../components/GuideButton.vue'
import Icon from '../components/Icon.vue'
import PageGuide from '../components/PageGuide.vue'
import { api } from '../api'
import { fmtPct, fmtPercent, toDateString, trendClass } from '../format'
import { loadMeta, state } from '../store'
import {
  BASIS_LABELS, HEADLINE_HORIZON, KIND_LABELS, backtest, backtestOf, headlineStat, hitRate, hitRateLabel, loadBacktest,
} from '../strategy'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const kind = route.params.kind
const title = KIND_LABELS[kind]
document.title = `${title} · InStock`

const signals = ref(null)
const loading = ref(false)
const date = ref(null)
const btError = ref('')

loadMeta()
loadBacktest().catch((e) => { btError.value = e.message })
const strategies = computed(() => (state.meta?.strategies || []).filter((s) => s.kind === kind))
const dateSet = computed(() => new Set(signals.value?.dates || []))

const idx = computed(() => Object.fromEntries((signals.value?.columns || []).map((c, i) => [c.name, i])))
const counts = computed(() => {
  const out = {}
  for (const r of signals.value?.rows || []) out[r[idx.value.strategy]] = (out[r[idx.value.strategy]] || 0) + 1
  return out
})

// 关注的股票今天触发了哪些本类策略
const watched = computed(() => {
  const keys = new Set(strategies.value.map((s) => s.key))
  const names = Object.fromEntries(strategies.value.map((s) => [s.key, s.name]))
  const byCode = new Map()
  for (const r of signals.value?.rows || []) {
    const code = r[idx.value.code]
    if (!keys.has(r[idx.value.strategy]) || !state.attention.has(code)) continue
    const item = byCode.get(code) || { code, name: r[idx.value.name], hits: [] }
    item.hits.push({ key: r[idx.value.strategy], name: names[r[idx.value.strategy]] })
    byCode.set(code, item)
  }
  return [...byCode.values()]
})

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

watch(date, (value, old) => { if (old && value && value !== signals.value?.date) loadSignals(value) })
loadSignals()

const horizons = computed(() => backtest.value?.horizons || [])
const cards = computed(() => strategies.value.map((s) => ({ ...s, stat: headlineStat(s.key) })))
const rows = computed(() => strategies.value.map((s) => ({ ...s, bt: backtestOf(s.key) })).filter((s) => s.bt))
const open = (key) => router.push(`/strategy/${key}`)
</script>

<template>
  <div class="page strategy-list">
    <div class="toolbar">
      <h1><Icon :name="kind" :size="18" class="title-icon" :class="kind" />{{ title }}</h1>
      <GuideButton :id="`strategy-${kind}`" />
      <span class="spacer" />
      <span class="muted small">信号日期</span>
      <NDatePicker v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small"
                   :is-date-disabled="(ts) => !dateSet.has(toDateString(ts))" :disabled="!signals?.dates.length"
                   style="width: 140px" placeholder="暂无数据" />
    </div>
    <PageGuide :id="`strategy-${kind}`" />

    <div class="card watched">
      <div class="watched-title">
        <Icon name="star" :size="15" class="star" />
        我关注的股票 · {{ date || '—' }} 触发的{{ kind === 'sell' ? '卖出' : '买入' }}信号
      </div>
      <div v-if="watched.length" class="watched-list">
        <div v-for="w in watched" :key="w.code" class="watched-item">
          <RouterLink :to="`/stock/${w.code}`" class="stock">{{ w.name }} <span class="muted">{{ w.code }}</span></RouterLink>
          <RouterLink v-for="h in w.hits" :key="h.key" :to="`/strategy/${h.key}`" class="hit" :class="kind">{{ h.name }}</RouterLink>
        </div>
      </div>
      <p v-else-if="state.attention.size" class="muted small empty-line">关注的 {{ state.attention.size }} 只股票当天都没有触发{{ title }}。</p>
      <p v-else class="muted small empty-line">还没有关注的股票。在任意数据表或个股页点击 ☆ 关注后，这里会提示它们触发的信号。</p>
    </div>

    <NSpin :show="loading && !signals">
      <div class="cards">
        <RouterLink v-for="s in cards" :key="s.key" :to="`/strategy/${s.key}`" class="card strategy-card">
          <div class="card-head">
            <strong>{{ s.name }}</strong>
            <span class="tag">{{ BASIS_LABELS[s.basis] }}</span>
          </div>
          <p class="plain">{{ s.plain || s.rule }}</p>
          <div class="metrics">
            <div>
              <span class="label">当日信号</span>
              <span class="value">{{ signals ? counts[s.key] || 0 : '—' }}</span>
            </div>
            <div>
              <span class="label">{{ s.stat?.horizon ?? HEADLINE_HORIZON }}日超额</span>
              <span class="value" :class="trendClass(s.stat?.excess)">{{ fmtPct(s.stat?.excess) || '—' }}</span>
            </div>
            <div>
              <span class="label">{{ hitRateLabel(kind) }}</span>
              <span class="value">{{ fmtPercent(hitRate(s.stat, kind), 1) || '—' }}</span>
            </div>
          </div>
          <span class="more">查看信号与规则 <Icon name="arrow" :size="14" /></span>
        </RouterLink>
      </div>
    </NSpin>

    <section class="card">
      <div class="card-title">回测对比 <span class="muted small">点击行查看策略详情</span></div>
      <NSkeleton v-if="!backtest && !btError" text :repeat="4" style="margin: 12px 16px; width: auto" />
      <NEmpty v-else-if="btError || !rows.length" :description="btError || '暂无回测数据：需要先积累几天信号，或用命令行回补历史区间'"
              style="padding: 32px 0" />
      <div v-else class="scroll">
        <table class="bt">
          <thead>
            <tr>
              <th class="l" rowspan="2">策略</th>
              <th rowspan="2">信号数</th>
              <th v-for="h in horizons" :key="h" colspan="2">持有 {{ h }} 日</th>
            </tr>
            <tr>
              <template v-for="h in horizons" :key="h"><th>平均 / 超额</th><th>{{ hitRateLabel(kind) }}</th></template>
            </tr>
          </thead>
          <tbody>
            <tr v-if="backtest.benchmark" class="bench">
              <td class="l">全市场等权基准</td>
              <td class="muted">—</td>
              <template v-for="b in backtest.benchmark" :key="b.horizon">
                <td :class="trendClass(b.mean)">{{ fmtPct(b.mean) }}</td>
                <td class="muted">—</td>
              </template>
            </tr>
            <tr v-for="r in rows" :key="r.key" @click="open(r.key)">
              <td class="l">{{ r.name }}</td>
              <td>{{ r.bt.signals }}<div class="muted tiny">{{ r.bt.days }} 天</div></td>
              <template v-for="s in r.bt.stats" :key="s.horizon">
                <td>
                  <span :class="trendClass(s.mean)">{{ fmtPct(s.mean) || '—' }}</span>
                  <div class="tiny" :class="trendClass(s.excess)" :title="`样本 ${s.n}`">{{ fmtPct(s.excess) || '—' }}</div>
                </td>
                <td>{{ fmtPercent(hitRate(s, kind), 1) || '—' }}</td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted small note">
        统计口径：信号日收盘后决策，次日开盘价买入，持有 N 个交易日按收盘价计算收益；超额 = 信号收益 − 同日全市场等权平均收益。
        <template v-if="kind === 'sell'">卖出策略的收益表示“如果继续持有”的结果：收益与超额越低、下跌占比越高，说明卖出越及时。</template>
        <template v-else>超额为正才说明策略比随便买一只股票更好；样本少于几十个时结果偶然性很大。</template>
        未扣除交易费用，也未考虑涨跌停无法成交等情况，历史统计不代表未来表现。
        <RouterLink :to="{ path: '/learn', hash: '#backtest' }">如何看回测 →</RouterLink>
      </p>
    </section>
  </div>
</template>

<style scoped>
.title-icon { vertical-align: -3px; margin-right: 6px; }
.title-icon.buy { color: var(--up); }
.title-icon.sell { color: var(--down); }
.small { font-size: 12px; font-weight: 400; }
.tiny { font-size: 11px; }
.watched { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.watched-title { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.star { color: #f59f00; }
.watched-list { display: flex; flex-direction: column; gap: 6px; }
.watched-item { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; }
.stock { color: var(--text); font-weight: 500; min-width: 120px; }
.hit { font-size: 12px; padding: 1px 8px; border-radius: 4px; background: var(--up-soft); color: var(--up); }
.hit.sell { background: var(--down-soft); color: var(--down); }
.empty-line { margin: 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.strategy-card {
  padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; color: var(--text); text-decoration: none;
  transition: border-color 0.15s;
}
.strategy-card:hover { border-color: var(--primary); text-decoration: none; }
.card-head { display: flex; align-items: center; gap: 8px; }
.card-head strong { font-size: 15px; }
.tag { font-size: 11px; padding: 0 6px; border-radius: 4px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
.plain {
  margin: 0; font-size: 13px; line-height: 1.6; color: var(--muted); flex: 1;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.metrics div { display: flex; flex-direction: column; gap: 2px; }
.metrics .label { font-size: 11px; color: var(--muted); }
.metrics .value { font-size: 16px; font-weight: 650; }
.more { font-size: 12px; color: var(--primary); display: inline-flex; align-items: center; gap: 4px; }
.scroll { overflow-x: auto; }
.bt { border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }
.bt th, .bt td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--border); }
.bt th { color: var(--muted); font-weight: 500; font-size: 12px; }
.bt .l { text-align: left; position: sticky; left: 0; background: var(--surface); }
.bt tbody tr { cursor: pointer; }
.bt tbody tr:hover td { background: var(--surface-2); }
.bt tr.bench td { background: var(--surface-2); font-weight: 500; cursor: default; }
.note { padding: 8px 16px 12px; margin: 0; line-height: 1.7; }
@media (max-width: 767px) {
  .cards { grid-template-columns: minmax(0, 1fr); }
  .toolbar .muted.small { display: none; }
}
</style>
