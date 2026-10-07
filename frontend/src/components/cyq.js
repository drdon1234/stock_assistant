/**
 * 筹码分布（成本分布）估算：每根 K 线的成交按三角形分布摊到 [最低价, 最高价]（峰值在均价处），
 * 历史筹码按当日换手率衰减。与东方财富等行情软件的算法一致。
 *
 * @param {{open:number[], high:number[], low:number[], close:number[], turnover:number[], dates:string[]}} k
 * @param {number} end 计算截至的 K 线下标
 * @param {number} days 回看交易日数
 * @param {number} factor 价格刻度数
 */
export function calcChips(k, end, days = 210, factor = 150) {
  const start = Math.max(0, end - days + 1)
  let maxPrice = -Infinity
  let minPrice = Infinity
  for (let i = start; i <= end; i++) {
    maxPrice = Math.max(maxPrice, k.high[i])
    minPrice = Math.min(minPrice, k.low[i])
  }
  const accuracy = Math.max(0.01, (maxPrice - minPrice) / (factor - 1))
  const prices = Array.from({ length: factor }, (_, i) => +(minPrice + accuracy * i).toFixed(2))
  const chips = new Array(factor).fill(0)

  for (let i = start; i <= end; i++) {
    const open = k.open[i], close = k.close[i], high = k.high[i], low = k.low[i]
    const avg = (open + close + high + low) / 4
    const rate = Math.min(1, (k.turnover[i] || 0) / 100)
    for (let n = 0; n < factor; n++) chips[n] *= 1 - rate
    const g = Math.floor((avg - minPrice) / accuracy)
    if (high === low) {
      chips[g] += ((factor - 1) * rate) / 2 // 一字板：全部成交集中在一个价位
      continue
    }
    const peak = 2 / (high - low)
    const lo = Math.ceil((low - minPrice) / accuracy)
    const hi = Math.floor((high - minPrice) / accuracy)
    for (let j = lo; j <= hi; j++) {
      const price = minPrice + accuracy * j
      const weight = price <= avg
        ? (Math.abs(avg - low) < 1e-8 ? 1 : (price - low) / (avg - low))
        : (Math.abs(high - avg) < 1e-8 ? 1 : (high - price) / (high - avg))
      chips[j] += weight * peak * rate
    }
  }

  const total = chips.reduce((a, b) => a + b, 0)
  const costAt = (target) => {
    let sum = 0
    for (let i = 0; i < factor; i++) {
      if (sum + chips[i] > target) return minPrice + i * accuracy
      sum += chips[i]
    }
    return maxPrice
  }
  const range = (percent) => {
    const lo = costAt((total * (1 - percent)) / 2)
    const hi = costAt((total * (1 + percent)) / 2)
    return { low: lo, high: hi, concentration: lo + hi ? (hi - lo) / (lo + hi) : 0 }
  }
  const current = k.close[end]
  let profit = 0
  for (let i = 0; i < factor; i++) if (current >= prices[i]) profit += chips[i]

  return {
    date: k.dates[end],
    days: end - start + 1,
    prices,
    chips,
    current,
    profitRatio: total ? profit / total : 0,
    avgCost: costAt(total * 0.5),
    p90: range(0.9),
    p70: range(0.7),
  }
}
