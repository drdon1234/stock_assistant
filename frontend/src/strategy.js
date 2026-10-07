import { shallowRef } from 'vue'
import { api } from './api'

export const KIND_LABELS = { buy: '买入策略', sell: '卖出策略' }
export const BASIS_LABELS = { technical: '技术面', fundamental: '基本面' }
// 策略卡片与概览中重点展示的持有期（交易日）
export const HEADLINE_HORIZON = 20

// 买入策略与原作者配套的离场规则互相对应
const PAIRS = [['turtle', 'turtle_exit'], ['granville', 'granville_sell'], ['oversold', 'overbought']]
export const PAIRED = Object.fromEntries(PAIRS.flatMap(([a, b]) => [[a, b], [b, a]]))

// 回测统计在一次会话内只取一次（服务端另有 5 分钟缓存）
export const backtest = shallowRef(null)
let pending = null

export function loadBacktest() {
  if (!pending) {
    pending = api.backtest()
      .then((d) => { backtest.value = d })
      .catch((e) => {
        pending = null
        throw e
      })
  }
  return pending
}

export function backtestOf(key) {
  return backtest.value?.strategies.find((s) => s.strategy === key) || null
}

/** 重点展示的统计：优先 20 日；历史不足 20 日时取样本不为空的最长持有期。 */
export function headlineStat(key) {
  const stats = backtestOf(key)?.stats || []
  return stats.find((s) => s.horizon === HEADLINE_HORIZON && s.n > 0) || [...stats].reverse().find((s) => s.n > 0) || null
}

/** 卖出策略关注“信号后下跌的比例”，买入策略关注胜率。 */
export function hitRate(stat, kind) {
  if (stat?.win === null || stat?.win === undefined) return null
  return kind === 'sell' ? 100 - stat.win : stat.win
}

export const hitRateLabel = (kind) => (kind === 'sell' ? '下跌占比' : '胜率')
