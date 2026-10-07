const isNum = (v) => typeof v === 'number' && Number.isFinite(v)

function scaled(v, units, digits = 2) {
  const abs = Math.abs(v)
  for (const [base, suffix] of units) {
    if (abs >= base) return `${(v / base).toFixed(digits)}${suffix}`
  }
  return v.toFixed(0)
}

export const fmtNum = (v, digits = 2) => (isNum(v) ? v.toFixed(digits) : '')
export const fmtPct = (v, digits = 2) => (isNum(v) ? `${v > 0 ? '+' : ''}${v.toFixed(digits)}%` : '')
export const fmtPercent = (v, digits = 2) => (isNum(v) ? `${v.toFixed(digits)}%` : '')
export const fmtMoney = (v) => (isNum(v) ? scaled(v, [[1e12, '万亿'], [1e8, '亿'], [1e4, '万']]) : '')
export const fmtVol = (v) => (isNum(v) ? scaled(v, [[1e8, '亿手'], [1e4, '万手']]) + (Math.abs(v) < 1e4 ? '手' : '') : '')
export const fmtShare = (v) => (isNum(v) ? scaled(v, [[1e8, '亿股'], [1e4, '万股']]) : '')

/** 按数据字典中的显示格式格式化单元格。 */
export function formatValue(v, fmt) {
  if (v === null || v === undefined) return ''
  switch (fmt) {
    case 'price': return fmtNum(v, v >= 1000 ? 1 : 2)
    case 'pct': return fmtPct(v)
    case 'percent': return fmtPercent(v)
    case 'money': return fmtMoney(v)
    case 'vol': return fmtVol(v)
    case 'share': return fmtShare(v)
    case 'int': return isNum(v) ? String(Math.round(v)) : ''
    case 'bool': return v ? '是' : '否'
    case 'signal': return v > 0 ? `看涨 ${v}` : v < 0 ? `看跌 ${-v}` : ''
    case 'num': return isNum(v) ? fmtNum(v, Math.abs(v) >= 1e5 ? 0 : 2) : ''
    default: return String(v)
  }
}

/** 涨跌着色：A 股习惯红涨绿跌。 */
export const trendClass = (v) => (!isNum(v) || v === 0 ? '' : v > 0 ? 'up' : 'down')

export const NUMERIC_FORMATS = new Set(['price', 'pct', 'percent', 'money', 'vol', 'share', 'int', 'num', 'signal'])

/** 时间戳转 YYYY-MM-DD（本地时区），用于日期选择器。 */
export function toDateString(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
