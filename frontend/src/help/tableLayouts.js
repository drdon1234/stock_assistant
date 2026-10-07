// 宽表的列分组：表头分两层显示（分组名 + 短列名），并可在“列设置”中按组或按列显示/隐藏。
// groups：[{ title, cols, off? }]，off 为 true 表示该组默认隐藏；hidden 为默认隐藏的单列。
// 未列入任何分组的列归入“其他”。prefixGroups 为按列名前缀自动分组（资金流向的各周期）。
// 子列名去掉与分组名相同的前缀（“今日主力净流入”→“主力净流入”，“MACD DIF”→“DIF”），完整名称见悬停提示。

const range = (prefix, suffixes) => suffixes.map((s) => `${prefix}${s}`)

const INDICATOR_GROUPS = [
  { title: 'MACD', cols: ['macd', 'macds', 'macdh'] },
  { title: 'KDJ', cols: ['kdjk', 'kdjd', 'kdjj'] },
  { title: 'RSI', cols: ['rsi_6', 'rsi_12', 'rsi', 'rsi_24'] },
  { title: 'BOLL', cols: ['boll_ub', 'boll', 'boll_lb'] },
  { title: 'WR', cols: ['wr_6', 'wr_10', 'wr_14'], off: true },
  { title: 'CCI', cols: ['cci', 'cci_84'], off: true },
  { title: 'DMI', cols: ['pdi', 'mdi', 'dx', 'adx', 'adxr'], off: true },
  { title: 'BIAS', cols: ['bias', 'bias_12', 'bias_24'], off: true },
  { title: 'TRIX', cols: ['trix', 'trma'], off: true },
  { title: 'DMA', cols: ['dma', 'ama'], off: true },
  { title: 'CR', cols: ['cr', 'cr_ma1', 'cr_ma2', 'cr_ma3'], off: true },
  { title: 'VR', cols: ['vr', 'mavr'], off: true },
  { title: 'ROC', cols: ['roc', 'rocma', 'rocema'], off: true },
  { title: 'PSY', cols: ['psy', 'psyma'], off: true },
  { title: 'BRAR', cols: ['br', 'ar'], off: true },
  { title: 'MFI', cols: ['mfi', 'mfisma'], off: true },
  { title: 'OBV', cols: ['obv'], off: true },
  { title: 'EMV', cols: ['emv', 'emva'], off: true },
  { title: 'PPO', cols: ['ppo', 'ppos', 'ppoh'], off: true },
  { title: 'WT', cols: ['wt1', 'wt2'], off: true },
  { title: 'StochRSI', cols: ['stochrsi_k', 'stochrsi_d'], off: true },
  { title: 'RVI', cols: ['rvi', 'rvis'], off: true },
  { title: 'DPO', cols: ['dpo', 'madpo'], off: true },
  { title: 'VHF', cols: ['vhf'], off: true },
  { title: 'FI', cols: ['fi', 'force_2', 'force_13'], off: true },
  { title: 'ATR', cols: ['tr', 'atr'], off: true },
  { title: '均线类', cols: ['tema', 'vwma', 'mvwma'], off: true },
  { title: 'SuperTrend', cols: ['supertrend_ub', 'supertrend', 'supertrend_lb'], off: true },
  { title: 'SAR', cols: ['sar'], off: true },
  { title: 'ENE', cols: ['ene_ue', 'ene', 'ene_le'], off: true },
]

export const TABLE_LAYOUTS = {
  cn_stock_spot: {
    groups: [
      { title: '行情', cols: ['new_price', 'change_rate', 'ups_downs', 'volume', 'deal_amount', 'amplitude', 'turnoverrate', 'volume_ratio'] },
      { title: '价格', cols: ['open_price', 'high_price', 'low_price', 'pre_close_price'], off: true },
      { title: '区间涨幅', cols: ['speed_increase_60', 'speed_increase_all'] },
      { title: '估值', cols: ['pe9', 'dtsyl', 'pe', 'pbnewmrq', 'total_market_cap', 'free_cap'] },
      { title: '每股指标', cols: ['basic_eps', 'bvps', 'per_capital_reserve', 'per_unassign_profit'], off: true },
      { title: '财务', cols: ['roe_weight', 'sale_gpr', 'debt_asset_ratio', 'total_operate_income', 'toi_yoy_ratio', 'parent_netprofit', 'netprofit_yoy_ratio'], off: true },
      { title: '股本', cols: ['total_shares', 'free_shares'], off: true },
      { title: '基本信息', cols: ['industry', 'listing_date'] },
    ],
    hidden: ['ups_downs', 'dtsyl', 'pe', 'free_cap'],
  },
  cn_stock_selection: {
    groups: [
      { title: '行情', cols: ['new_price', 'change_rate', 'volume_ratio', 'high_price', 'low_price', 'pre_close_price', 'volume', 'deal_amount', 'turnoverrate', 'amplitude'] },
      { title: '区间涨幅', cols: ['changerate_3days', 'changerate_5days', 'changerate_10days', 'changerate_ty', 'upnday', 'downnday', 'listing_yield_year', 'listing_volatility_year'] },
      { title: '所属板块', cols: ['industry', 'area', 'concept', 'style', 'listing_date', 'is_hs300', 'is_sz50', 'is_zz500', 'is_zz1000', 'is_cy50'] },
      { title: '估值', cols: ['pe9', 'pbnewmrq', 'pettmdeducted', 'ps9', 'pcfjyxjl9', 'predict_pe_syear', 'predict_pe_nyear', 'total_market_cap', 'free_cap', 'dtsyl', 'ycpeg', 'enterprise_value_multiple', 'zxgxl'] },
      { title: '每股指标', cols: ['basic_eps', 'bvps', 'per_netcash_operate', 'per_fcfe', 'per_capital_reserve', 'per_unassign_profit', 'per_surplus_reserve', 'per_retained_earning'], off: true },
      { title: '盈利能力', cols: ['parent_netprofit', 'deduct_netprofit', 'total_operate_income', 'roe_weight', 'jroa', 'roic', 'sale_gpr', 'sale_npr'], off: true },
      { title: '成长能力', cols: ['netprofit_yoy_ratio', 'deduct_netprofit_growthrate', 'toi_yoy_ratio', 'netprofit_growthrate_3y', 'income_growthrate_3y', 'predict_netprofit_ratio', 'predict_income_ratio', 'basiceps_yoy_ratio', 'total_profit_growthrate', 'operate_profit_growthrate', 'predict_type'], off: true },
      { title: '偿债能力', cols: ['debt_asset_ratio', 'equity_ratio', 'equity_multiplier', 'current_ratio', 'speed_ratio'], off: true },
      { title: '股本股东', cols: ['total_shares', 'free_shares', 'holder_newest', 'holder_ratio', 'hold_amount', 'avg_hold_num', 'holdnum_growthrate_3q', 'holdnum_growthrate_hy', 'hold_ratio_count', 'free_hold_ratio', 'holder_change_3m', 'executive_change_3m'], off: true },
      { title: '机构', cols: ['org_survey_3m', 'org_rating', 'allcorp_num', 'allcorp_fund_num', 'allcorp_qs_num', 'allcorp_qfii_num', 'allcorp_bx_num', 'allcorp_sb_num', 'allcorp_xt_num', 'allcorp_ratio', 'allcorp_fund_ratio', 'allcorp_qs_ratio', 'allcorp_qfii_ratio', 'allcorp_bx_ratio', 'allcorp_sb_ratio', 'allcorp_xt_ratio', 'mutual_netbuy_amt', 'hold_ratio'], off: true },
      { title: '资金', cols: ['net_inflow', 'netinflow_3days', 'netinflow_5days', 'nowinterst_ratio', 'nowinterst_ratio_3d', 'nowinterst_ratio_5d', 'ddx', 'ddx_3d', 'ddx_5d', 'ddx_red_10d'], off: true },
      { title: '技术信号', cols: ['macd_golden_fork', 'macd_golden_forkz', 'macd_golden_forky', 'kdj_golden_fork', 'kdj_golden_forkz', 'kdj_golden_forky', 'break_through', 'low_funds_inflow', 'high_funds_outflow', ...range('breakup_ma_', ['5days', '10days', '20days', '30days', '60days']), 'long_avg_array', 'short_avg_array', 'upper_large_volume', 'down_narrow_volume', 'one_dayang_line', 'two_dayang_lines', 'rise_sun', 'power_fulgun', 'restore_justice', 'down_7days', 'upper_8days', 'upper_9days', 'upper_4days', 'heaven_rule', 'upside_volume', 'bearish_engulfing', 'reversing_hammer', 'shooting_star', 'evening_star', 'first_dawn', 'pregnant', 'black_cloud_tops', 'morning_star', 'narrow_finish'], off: true },
      { title: '新高新低', cols: ['now_newhigh', 'now_newlow', ...range('high_recent_', ['3days', '5days', '10days', '20days', '30days']), ...range('low_recent_', ['3days', '5days', '10days', '20days', '30days']), ...range('win_market_', ['3days', '5days', '10days', '20days', '30days']), 'is_issue_break', 'is_bps_break'], off: true },
      { title: '资本运作', cols: ['limited_lift_f6m', 'limited_lift_f1y', 'limited_lift_6m', 'limited_lift_1y', ...range('directional_seo_', ['1m', '3m', '6m', '1y']), ...range('recapitalize_', ['1m', '3m', '6m', '1y']), ...range('equity_pledge_', ['1m', '3m', '6m', '1y']), 'pledge_ratio', 'goodwill_scale', 'goodwill_assets_ratro', 'par_dividend_pretax', 'par_dividend', 'par_it_equity'], off: true },
      { title: '人气', cols: ['popularity_rank', 'rank_change', 'upp_days', 'down_days', 'new_high', 'new_down', 'newfans_ratio', 'bigfans_ratio', 'concern_rank_7days', 'browse_rank'], off: true },
    ],
    hidden: ['high_price', 'low_price', 'pre_close_price', 'volume', 'amplitude', 'listing_yield_year', 'listing_volatility_year',
      'area', 'concept', 'style', 'listing_date', 'is_sz50', 'is_zz1000', 'is_cy50', 'pettmdeducted', 'ps9', 'pcfjyxjl9',
      'predict_pe_syear', 'predict_pe_nyear', 'free_cap', 'dtsyl', 'enterprise_value_multiple', 'upnday', 'downnday'],
    short: {
      listing_yield_year: '上市年化收益', listing_volatility_year: '上市年化波动', changerate_ty: '今年以来',
      ...Object.fromEntries(['3', '5', '10', '20', '30'].flatMap((d) => [
        [`high_recent_${d}days`, `近${d}日创新高`], [`low_recent_${d}days`, `近${d}日创新低`], [`win_market_${d}days`, `近${d}日跑赢`]])),
    },
  },
  cn_stock_fund_flow: { prefixGroups: { 今日: true, '3日': false, '5日': true, '10日': false } },
  cn_stock_fund_flow_industry: { prefixGroups: { 今日: true, '5日': false, '10日': false } },
  cn_stock_fund_flow_concept: { prefixGroups: { 今日: true, '5日': false, '10日': false } },
  cn_stock_lhb: {
    groups: [
      { title: '行情', cols: ['new_price', 'change_rate', 'turnoverrate', 'free_cap'] },
      { title: '龙虎榜', cols: ['net_amount_buy', 'sum_buy', 'sum_sell', 'lhb_amount', 'market_amount', 'net_amount_rate', 'sum_rate'] },
      { title: '上榜原因', cols: ['interpret', 'reason'] },
      { title: '上榜后涨跌', cols: ['ranking_after_1', 'ranking_after_2', 'ranking_after_5', 'ranking_after_10'] },
    ],
    hidden: ['market_amount', 'sum_rate'],
    short: { net_amount_buy: '净买额', sum_buy: '买入额', sum_sell: '卖出额', lhb_amount: '成交额', market_amount: '市场总成交',
      ranking_after_1: '1日', ranking_after_2: '2日', ranking_after_5: '5日', ranking_after_10: '10日' },
  },
  cn_stock_bonus: {
    groups: [
      { title: '分配方案', cols: ['plan_profile', 'convertible_total_rate', 'convertible_rate', 'convertible_transfer_rate', 'bonusaward_rate', 'bonusaward_yield'] },
      { title: '日期与进度', cols: ['progress', 'plan_date', 'record_date', 'ex_dividend_date', 'report_date'] },
      { title: '财务', cols: ['basic_eps', 'bvps', 'per_capital_reserve', 'per_unassign_profit', 'netprofit_yoy_ratio', 'total_shares'], off: true },
    ],
    hidden: ['convertible_rate', 'convertible_transfer_rate', 'report_date'],
    short: { convertible_total_rate: '送转合计', convertible_rate: '送股', convertible_transfer_rate: '转股', bonusaward_rate: '现金分红' },
  },
  cn_stock_indicators: {
    groups: [{ title: '行情', cols: ['close'] }, ...INDICATOR_GROUPS],
  },
}


/** 由表结构和布局配置生成分组：[{ title, cols: [{ name, label, short }], off }]。 */
export function buildGroups(table, columns, fixed) {
  const layout = TABLE_LAYOUTS[table] || {}
  const byName = Object.fromEntries(columns.map((c) => [c.name, c]))
  const used = new Set(fixed)
  const groups = []
  const shortLabel = (col, title) => {
    if (layout.short?.[col.name]) return layout.short[col.name]
    if (title && col.label.startsWith(title)) {
      const rest = col.label.slice(title.length).trim()
      if (rest && !/^\d/.test(rest)) return rest
    }
    return col.label
  }
  if (layout.prefixGroups) {
    for (const [title, on] of Object.entries(layout.prefixGroups)) {
      const cols = columns.filter((c) => !used.has(c.name) && c.label.startsWith(title))
      cols.forEach((c) => used.add(c.name))
      if (cols.length) groups.push({ title, off: !on, cols: cols.map((c) => ({ ...c, short: shortLabel(c, title) })) })
    }
  }
  for (const g of layout.groups || []) {
    const cols = g.cols.filter((n) => byName[n] && !used.has(n)).map((n) => byName[n])
    cols.forEach((c) => used.add(c.name))
    if (cols.length) groups.push({ title: g.title, off: !!g.off, cols: cols.map((c) => ({ ...c, short: shortLabel(c, g.title) })) })
  }
  const rest = columns.filter((c) => !used.has(c.name))
  if (rest.length) {
    // 按周期分组的表（资金流向）剩余的是最新价等基础列，放在最前且不加分组名
    const lead = !!layout.prefixGroups || !groups.length
    const group = { title: lead ? '' : '其他', off: false, cols: rest.map((c) => ({ ...c, short: c.label })) }
    if (lead) groups.unshift(group)
    else groups.push(group)
  }
  const hidden = new Set(layout.hidden || [])
  for (const g of groups) for (const c of g.cols) c.defaultOn = !g.off && !hidden.has(c.name)
  return groups
}
