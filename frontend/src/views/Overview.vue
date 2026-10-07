<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { NEmpty, NSkeleton, NTabPane, NTabs, useMessage } from 'naive-ui'
import EChart from '../components/EChart.vue'
import { api } from '../api'
import { colors } from '../colors'
import { fmtMoney, fmtNum, fmtPct, trendClass } from '../format'
import { state } from '../store'

const message = useMessage()
const data = ref(null)
const loading = ref(true)
document.title = '市场概览 · InStock'

api.overview()
  .then((d) => { data.value = d })
  .catch((e) => message.error(`加载失败：${e.message}`))
  .finally(() => { loading.value = false })

const market = computed(() => data.value?.market)
const breadth = computed(() => {
  const m = market.value
  if (!m?.total) return null
  return { up: (m.up / m.total) * 100, flat: (m.flat / m.total) * 100, down: (m.down / m.total) * 100 }
})

const distributionOption = computed(() => {
  const m = market.value
  if (!m) return null
  const c = colors.value
  return {
    grid: { left: 8, right: 8, top: 24, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: m.distribution.map((d) => d.label), axisLabel: { color: c.muted, fontSize: 11 },
             axisLine: { lineStyle: { color: c.grid } }, axisTick: { show: false } },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'bar', barMaxWidth: 34,
      data: m.distribution.map((d, i) => ({ value: d.count, itemStyle: { color: i < 5 ? c.down : i === 5 ? c.flat : c.up, borderRadius: [4, 4, 0, 0] } })),
      label: { show: true, position: 'top', color: c.muted, fontSize: 11 },
    }],
  }
})

const flowOption = computed(() => {
  const ind = data.value?.industry
  if (!ind?.inflow) return null
  const c = colors.value
  const rows = [...ind.outflow.slice(0, 8).reverse(), ...ind.inflow.slice(0, 8).reverse()]
  return {
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => fmtMoney(v) },
    xAxis: { type: 'value', axisLabel: { color: c.muted, formatter: (v) => fmtMoney(v) }, splitLine: { lineStyle: { color: c.grid } } },
    yAxis: { type: 'category', data: rows.map((r) => r.name), axisLabel: { color: c.text }, axisTick: { show: false },
             axisLine: { lineStyle: { color: c.grid } } },
    series: [{ type: 'bar', barMaxWidth: 14,
               data: rows.map((r) => ({ value: r.fund_amount, itemStyle: { color: r.fund_amount >= 0 ? c.up : c.down, borderRadius: 3 } })) }],
  }
})

const lists = computed(() => [
  { key: 'gainers', title: '涨幅榜', rows: data.value?.gainers || [] },
  { key: 'losers', title: '跌幅榜', rows: data.value?.losers || [] },
  { key: 'active', title: '成交额', rows: data.value?.active || [] },
])
const kindLabel = { buy: '买入', sell: '风险' }
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h1>市场概览</h1>
      <span v-if="data?.date" class="muted">数据日期 {{ data.date }}</span>
    </div>

    <NSkeleton v-if="loading" :repeat="3" height="120px" :sharp="false" style="border-radius: 10px" />
    <NEmpty v-else-if="!market" description="还没有行情数据：运行 python -m instock run 或启动调度进程后再来" class="card empty" />

    <template v-else>
      <section class="stats">
        <div class="card stat">
          <div class="label">上涨 / 下跌</div>
          <div class="value"><span class="up">{{ market.up }}</span> <span class="muted">/</span> <span class="down">{{ market.down }}</span></div>
          <div class="bar" v-if="breadth">
            <span class="seg up-bg" :style="{ width: breadth.up + '%' }" />
            <span class="seg flat-bg" :style="{ width: breadth.flat + '%' }" />
            <span class="seg down-bg" :style="{ width: breadth.down + '%' }" />
          </div>
        </div>
        <div class="card stat">
          <div class="label">涨停 / 跌停</div>
          <div class="value"><span class="up">{{ market.limit_up }}</span> <span class="muted">/</span> <span class="down">{{ market.limit_down }}</span></div>
          <div class="sub muted">平盘 {{ market.flat }} 家</div>
        </div>
        <div class="card stat">
          <div class="label">两市成交额</div>
          <div class="value">{{ fmtMoney(market.amount) }}</div>
          <div class="sub muted">共 {{ market.total }} 只股票</div>
        </div>
        <div class="card stat">
          <div class="label">涨跌幅中位数</div>
          <div class="value" :class="trendClass(market.median_change)">{{ fmtPct(market.median_change) }}</div>
          <div class="sub muted">反映多数个股表现</div>
        </div>
      </section>

      <section class="grid-2">
        <div class="card">
          <div class="card-title">涨跌分布</div>
          <div class="chart"><EChart v-if="distributionOption" :option="distributionOption" /></div>
        </div>
        <div class="card">
          <div class="card-title">
            策略信号 <span v-if="data.signals?.date" class="muted small">{{ data.signals.date }}</span>
          </div>
          <div class="card-body signals" v-if="data.signals?.items">
            <RouterLink v-for="s in data.signals.items" :key="s.key" :to="{ path: '/strategy', query: { key: s.key } }"
                        class="signal" :class="s.kind">
              <span class="name">{{ s.name }}</span>
              <span class="badge">{{ kindLabel[s.kind] }}</span>
              <span class="num">{{ s.count }}</span>
            </RouterLink>
          </div>
          <NEmpty v-else description="暂无策略结果" class="empty-inner" />
        </div>
      </section>

      <section class="grid-2">
        <div class="card">
          <NTabs type="line" size="small" class="tabs" animated>
            <NTabPane v-for="list in lists" :key="list.key" :name="list.key" :tab="list.title">
              <table class="rank">
                <tbody>
                  <tr v-for="r in list.rows" :key="r.code">
                    <td><RouterLink :to="`/stock/${r.code}`">{{ r.name }}</RouterLink> <span class="muted code">{{ r.code }}</span></td>
                    <td class="r">{{ fmtNum(r.new_price) }}</td>
                    <td class="r" :class="trendClass(r.change_rate)">{{ fmtPct(r.change_rate) }}</td>
                    <td class="r muted">{{ fmtMoney(r.deal_amount) }}</td>
                  </tr>
                </tbody>
              </table>
            </NTabPane>
          </NTabs>
        </div>
        <div class="card">
          <div class="card-title">
            行业资金流向 <span v-if="data.industry?.date" class="muted small">{{ data.industry.date }} · 主力净流入</span>
          </div>
          <div class="chart tall"><EChart v-if="flowOption" :option="flowOption" /><NEmpty v-else description="暂无数据" class="empty-inner" /></div>
        </div>
      </section>

      <section class="card" v-if="data.attention?.length">
        <div class="card-title">我的关注 <RouterLink to="/attention" class="small">全部</RouterLink></div>
        <div class="card-body chips">
          <RouterLink v-for="r in data.attention" :key="r.code" :to="`/stock/${r.code}`" class="chip">
            <span>{{ r.name }}</span>
            <span :class="trendClass(r.change_rate)">{{ fmtNum(r.new_price) }} {{ fmtPct(r.change_rate) }}</span>
          </RouterLink>
        </div>
      </section>
      <p v-else-if="!state.attention.size" class="muted small hint">提示：在任意数据表或个股页点击 ☆ 即可加入关注。</p>
    </template>
  </div>
</template>

<style scoped>
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.stat { padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; }
.stat .label { color: var(--muted); font-size: 13px; }
.stat .value { font-size: 24px; font-weight: 650; }
.stat .sub { font-size: 12px; }
.bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--border); }
.seg { display: block; height: 100%; }
.up-bg { background: var(--up); }
.down-bg { background: var(--down); }
.flat-bg { background: var(--muted); opacity: 0.4; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.chart { height: 240px; padding: 4px 8px; }
.chart.tall { height: 360px; }
.small { font-size: 12px; font-weight: 400; }
.signals { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.signal {
  display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 8px;
  background: var(--surface-2); border: 1px solid var(--border); color: var(--text); text-decoration: none;
}
.signal:hover { border-color: var(--primary); text-decoration: none; }
.signal .name { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.signal .badge { font-size: 11px; padding: 0 5px; border-radius: 4px; background: var(--up-soft); color: var(--up); }
.signal.sell .badge { background: var(--down-soft); color: var(--down); }
.signal .num { font-weight: 650; }
.tabs { padding: 4px 16px 8px; }
.rank { width: 100%; border-collapse: collapse; font-size: 13px; }
.rank td { padding: 7px 4px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.rank tr:last-child td { border-bottom: 0; }
.rank .r { text-align: right; }
.rank .code { font-size: 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex; gap: 8px; padding: 6px 10px; border-radius: 8px; background: var(--surface-2);
  border: 1px solid var(--border); color: var(--text); font-size: 13px; text-decoration: none;
}
.empty { padding: 48px 16px; }
.empty-inner { padding: 32px 0; }
.hint { margin: 0; }
@media (max-width: 1023px) {
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 767px) {
  .stats { gap: 10px; }
  .stat .value { font-size: 20px; }
  .rank td:nth-child(4) { display: none; }
}
</style>
