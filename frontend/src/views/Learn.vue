<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NInput } from 'naive-ui'
import Icon from '../components/Icon.vue'
import { MAIN_OVERLAYS, SUB_INDICATORS } from '../components/indicatorCatalog'
import { TERMS, TERM_CATEGORIES } from '../help/glossary'
import { DIR_LABELS, PATTERN_HELP } from '../help/patterns'
import { BASIS_LABELS, KIND_LABELS } from '../strategy'
import { loadMeta, state } from '../store'

const route = useRoute()
const router = useRouter()
const keyword = ref('')
document.title = '学习中心 · InStock'
loadMeta()

const SECTIONS = [
  { id: 'start', title: '快速上手' },
  { id: 'terms', title: '常用术语' },
  { id: 'indicators', title: '技术指标' },
  { id: 'patterns', title: 'K线形态' },
  { id: 'strategies', title: '买卖策略' },
  { id: 'backtest', title: '如何看回测' },
  { id: 'risk', title: '风险提示' },
]

const STEPS = [
  { title: '看大势', to: '/', text: '每天先看“市场概览”：上涨家数、涨跌幅中位数和成交额，判断当天是普涨、普跌还是分化。大势不好时，多数买入策略的效果都会变差。' },
  { title: '找候选', to: '/strategies/buy', text: '在“买入策略”中挑一个你理解其逻辑的策略，查看当天的信号股票。先看它的回测：超额收益是否为正、样本是否足够。' },
  { title: '细筛选', to: '/table/cn_stock_selection', text: '把候选股放到“综合选股”“每日股票数据”中按估值、财务等条件进一步筛选，排除 ST、亏损、高质押等风险较大的股票。' },
  { title: '看图表', to: null, text: '点击任意股票代码进入个股页，看 K 线所处的趋势、均线与成交量，确认信号所处的位置是否合理。' },
  { title: '做关注', to: '/attention', text: '把想跟踪的股票加入关注（点击 ☆）。关注的股票会在各数据表中高亮，并在策略页提示它们当天触发的信号。' },
  { title: '定卖点', to: '/strategies/sell', text: '买入前就想好怎么卖：设定止损价，并留意“卖出策略”对持仓股票给出的离场信号。' },
]

const q = computed(() => keyword.value.trim().toLowerCase())
const match = (...texts) => !q.value || texts.some((t) => t?.toLowerCase().includes(q.value))

const terms = computed(() => TERM_CATEGORIES
  .map((cat) => ({ cat, items: TERMS.filter((t) => t.cat === cat && match(t.term, t.desc)) }))
  .filter((g) => g.items.length))

const indicators = computed(() => [
  { title: '主图叠加（画在 K 线上）', items: MAIN_OVERLAYS.filter((i) => match(i.key, i.desc)) },
  { title: '副图指标（画在 K 线下方）', items: SUB_INDICATORS.filter((i) => match(i.key, i.desc)) },
].filter((g) => g.items.length))

const patterns = computed(() => {
  const list = (state.meta?.patterns || []).map((p) => ({ ...p, ...PATTERN_HELP[p.key] }))
  return ['bull', 'bear', 'both', 'neutral']
    .map((dir) => ({ dir, title: DIR_LABELS[dir], items: list.filter((p) => p.dir === dir && match(p.label, p.desc)) }))
    .filter((g) => g.items.length)
})

const strategies = computed(() => ['buy', 'sell']
  .map((kind) => ({
    kind,
    title: KIND_LABELS[kind],
    items: (state.meta?.strategies || []).filter((s) => s.kind === kind && match(s.name, s.plain, s.rule, s.source)),
  }))
  .filter((g) => g.items.length))

const searching = computed(() => !!q.value)
const empty = computed(() => searching.value && !terms.value.length && !indicators.value.length
  && !patterns.value.length && !strategies.value.length)

const active = ref(route.hash.slice(1) || 'start')
function scrollTo(id, smooth = true) {
  active.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
}
function go(id) {
  router.replace({ hash: `#${id}` })
  scrollTo(id)
}
// 数据加载后再定位到地址中的章节（内容高度会变化）
watch(() => state.meta, async (meta) => {
  if (!meta || !route.hash) return
  await nextTick()
  scrollTo(route.hash.slice(1), false)
}, { immediate: true })
</script>

<template>
  <div class="page learn">
    <div class="toolbar">
      <h1>学习中心</h1>
      <span class="muted small">从零开始了解页面里的数据、指标和策略</span>
      <span class="spacer" />
      <NInput v-model:value="keyword" size="small" clearable placeholder="搜索术语、指标、形态、策略" class="search">
        <template #prefix><Icon name="search" :size="15" /></template>
      </NInput>
    </div>

    <div class="layout">
      <nav class="toc" aria-label="章节">
        <a v-for="s in SECTIONS" :key="s.id" :href="`#${s.id}`" :class="{ active: active === s.id }"
           @click.prevent="go(s.id)">{{ s.title }}</a>
      </nav>

      <div class="body">
        <p v-if="empty" class="card empty muted">没有找到与“{{ keyword }}”相关的内容。</p>

        <section v-if="!searching" id="start" class="card section">
          <h2>快速上手</h2>
          <p class="lead">
            本站每天收盘后自动抓取全部 A 股的行情、资金和事件数据，计算技术指标与 K 线形态，并运行一组有文献出处的买入、卖出策略。
            下面是一个推荐的使用流程，每个页面顶部的“说明”按钮也会告诉你这个页面怎么看。
          </p>
          <ol class="steps">
            <li v-for="(s, i) in STEPS" :key="s.title">
              <span class="num">{{ i + 1 }}</span>
              <div>
                <strong><RouterLink v-if="s.to" :to="s.to">{{ s.title }}</RouterLink><template v-else>{{ s.title }}</template></strong>
                <p>{{ s.text }}</p>
              </div>
            </li>
          </ol>
          <h3>颜色与符号</h3>
          <ul class="plain-list">
            <li><span class="up">红色</span>表示上涨、<span class="down">绿色</span>表示下跌（A 股习惯，与欧美相反）。</li>
            <li>☆ / ★：点击加入或取消关注；关注的股票在表格中以浅黄色背景高亮。</li>
            <li>数据表中把鼠标移到列名上可以看到该列的解释；列头的漏斗图标用于按条件筛选。</li>
            <li>列很多的表（综合选股、技术指标、资金流向等）可以用右上角“列设置”选择要看的列。</li>
          </ul>
        </section>

        <section v-if="terms.length" id="terms" class="card section">
          <h2>常用术语</h2>
          <div v-for="g in terms" :key="g.cat" class="group">
            <h3>{{ g.cat }}</h3>
            <dl class="defs">
              <template v-for="t in g.items" :key="t.term">
                <dt>{{ t.term }}</dt>
                <dd>{{ t.desc }}</dd>
              </template>
            </dl>
          </div>
        </section>

        <section v-if="indicators.length" id="indicators" class="card section">
          <h2>技术指标</h2>
          <p v-if="!searching" class="lead">
            技术指标是用价格和成交量按固定公式算出的数值，大致分两类：<b>趋势类</b>（均线、MACD、BOLL、DMI 等）判断方向，
            适合在趋势行情中使用；<b>摆动类</b>（KDJ、RSI、WR、CCI 等）判断超买超卖，适合在震荡行情中使用。
            趋势强时摆动指标会长期“超买”或“超卖”，单独据此逆势操作是新手最常见的错误。本站指标按通达信/同花顺公式计算，
            可在个股页叠加显示，也可在“技术指标”数据表中按数值筛选。
          </p>
          <div v-for="g in indicators" :key="g.title" class="group">
            <h3>{{ g.title }}</h3>
            <dl class="defs">
              <template v-for="i in g.items" :key="i.key">
                <dt>{{ i.key }}</dt>
                <dd>{{ i.desc }}</dd>
              </template>
            </dl>
          </div>
        </section>

        <section v-if="patterns.length" id="patterns" class="card section">
          <h2>K线形态</h2>
          <p v-if="!searching" class="lead">
            蜡烛图形态源自日本米市，由一到五根 K 线的组合描述多空力量的变化。本站使用 TA-Lib 识别 61 种形态。
            形态只有出现在合适的位置才有意义：例如“锤头”要出现在下跌之后，“上吊线”要出现在上涨之后。
            研究表明多数单根、双根形态单独使用的预测力很弱，应与趋势、支撑阻力和成交量结合判断。
          </p>
          <div v-for="g in patterns" :key="g.dir" class="group">
            <h3 :class="g.dir">{{ g.title }}<span class="muted count">{{ g.items.length }}</span></h3>
            <dl class="defs">
              <template v-for="p in g.items" :key="p.key">
                <dt>{{ p.label }}</dt>
                <dd>{{ p.desc }}</dd>
              </template>
            </dl>
          </div>
          <p class="muted small">“双向”形态有看涨和看跌两种版本，以形态出现的方向区分；“中性”形态本身不判断方向。</p>
        </section>

        <section v-if="strategies.length" id="strategies" class="card section">
          <h2>买卖策略</h2>
          <template v-if="!searching">
            <p class="lead">
              每个策略都来自公开出版的交易书籍或研究，规则尽量忠实于原文。<b>买入策略</b>从全市场筛选符合入场条件的股票；
              <b>卖出策略</b>提示持有的股票出现了离场或风险信号。几个使用原则：
            </p>
            <ul class="plain-list">
              <li>信号只是候选，不是买卖建议；先理解策略的逻辑，再看它的历史回测。</li>
              <li>买入和卖出要成套使用：很多原作者都给出了配套的离场规则（如海龟交易法则配海龟离场）。</li>
              <li>无论使用哪个策略，都应控制单只股票的仓位，并预先设定止损。</li>
            </ul>
          </template>
          <div v-for="g in strategies" :key="g.kind" class="group">
            <h3><RouterLink :to="`/strategies/${g.kind}`">{{ g.title }}</RouterLink></h3>
            <div class="strategy" v-for="s in g.items" :key="s.key">
              <div class="strategy-head">
                <RouterLink :to="`/strategy/${s.key}`"><strong>{{ s.name }}</strong></RouterLink>
                <span class="tag">{{ BASIS_LABELS[s.basis] }}</span>
              </div>
              <p>{{ s.plain }}</p>
              <p class="muted small">规则：{{ s.rule }}</p>
              <p class="muted small">出处：{{ s.source }}</p>
            </div>
          </div>
        </section>

        <section v-if="!searching" id="backtest" class="card section">
          <h2>如何看回测</h2>
          <p class="lead">
            回测是把策略套用到历史数据上，统计信号出现后的实际表现。本站的口径是：信号日收盘后决策，<b>次日开盘价买入</b>，
            持有 N 个交易日后按收盘价计算收益。同时用同一天<b>全部 A 股按同样口径计算的平均收益</b>作为基准。
          </p>
          <dl class="defs">
            <dt>平均收益</dt><dd>所有信号收益的平均值，容易被少数大涨股拉高。</dd>
            <dt>中位收益</dt><dd>把收益从低到高排序后位于中间的值，更能代表“典型”信号的结果。</dd>
            <dt>胜率</dt><dd>收益为正的信号占比。趋势类策略胜率常低于 50%，靠少数大赚弥补多数小亏，胜率低不等于策略差。</dd>
            <dt>超额收益</dt><dd>策略收益 − 同日基准收益，是最重要的指标：牛市里随便买都赚钱，只有超额收益能说明策略本身有效。卖出策略的超额为负说明卖得对。</dd>
            <dt>样本数</dt><dd>信号太少（几十个以内）或只覆盖很短的时间时，结果可能只是运气。可以用命令行回补更长的历史区间。</dd>
          </dl>
          <h3>回测的局限</h3>
          <ul class="plain-list">
            <li>未扣除佣金、印花税和冲击成本；短线策略换手高，费用影响更大。</li>
            <li>未考虑一字涨停买不进、跌停卖不出、停牌等情况，实际结果通常比回测差。</li>
            <li>回补历史区间时股票池为当前在市的股票，期间已退市的股票不在其中（幸存者偏差），会让结果略显乐观。</li>
            <li>市场风格会变化，过去有效的策略未来可能失效；不同时期的表现差异可能很大。</li>
          </ul>
        </section>

        <section v-if="!searching" id="risk" class="card section">
          <h2>风险提示</h2>
          <ul class="plain-list">
            <li>本站所有数据、指标、形态和策略信号仅用于学习与研究，不构成任何投资建议。</li>
            <li>数据来自公开接口，可能存在延迟、缺失或错误，重要决策请以交易所和上市公司公告为准。</li>
            <li>股市有风险，投资需谨慎。只用亏得起的钱投资，避免借钱或加杠杆炒股。</li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.small { font-size: 12px; }
.search { width: 260px; }
.layout { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 16px; align-items: start; }
.toc { position: sticky; top: 0; display: flex; flex-direction: column; gap: 2px; }
.toc a { padding: 7px 12px; border-radius: 8px; color: var(--muted); font-size: 13px; text-decoration: none; }
.toc a:hover { background: var(--surface); color: var(--text); }
.toc a.active { background: var(--surface); color: var(--primary); font-weight: 600; box-shadow: var(--shadow); }
.body { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.section { padding: 18px 22px; scroll-margin-top: 12px; }
.section h2 { font-size: 17px; margin: 0 0 10px; }
.section h3 { font-size: 14px; margin: 18px 0 8px; }
.section h3.bull { color: var(--up); }
.section h3.bear { color: var(--down); }
.count { font-weight: 400; font-size: 12px; margin-left: 6px; }
.lead { margin: 0 0 8px; line-height: 1.8; font-size: 14px; }
.defs { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 8px 16px; margin: 0; font-size: 13px; line-height: 1.7; }
.defs dt { font-weight: 600; }
.defs dd { margin: 0; color: var(--muted); }
.steps { list-style: none; padding: 0; margin: 12px 0 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.steps li { display: flex; gap: 10px; padding: 12px; border-radius: 8px; background: var(--surface-2); border: 1px solid var(--border); }
.steps .num {
  flex: none; width: 24px; height: 24px; border-radius: 50%; background: var(--primary); color: #fff;
  display: grid; place-items: center; font-size: 12px; font-weight: 600;
}
.steps p { margin: 4px 0 0; font-size: 13px; line-height: 1.6; color: var(--muted); }
.plain-list { margin: 0; padding-left: 20px; line-height: 1.9; font-size: 13px; }
.strategy { padding: 10px 0; border-bottom: 1px solid var(--border); }
.strategy:last-child { border-bottom: 0; }
.strategy p { margin: 4px 0 0; font-size: 13px; line-height: 1.6; }
.strategy-head { display: flex; align-items: center; gap: 8px; }
.tag { font-size: 11px; padding: 0 6px; border-radius: 4px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
.empty { padding: 32px; text-align: center; margin: 0; }
@media (max-width: 1023px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .toc { flex-direction: row; overflow-x: auto; position: static; gap: 4px; }
  .toc a { white-space: nowrap; background: var(--surface); border: 1px solid var(--border); }
}
@media (max-width: 767px) {
  .search { width: 100%; order: 10; }
  .toolbar .muted.small { display: none; }
  .section { padding: 14px 16px; }
  .defs { grid-template-columns: minmax(0, 1fr); gap: 0; }
  .defs dt { margin-top: 10px; }
}
</style>
