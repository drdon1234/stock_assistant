// 副图指标：键为后端指标列名；bars 中的列画成红绿柱
export const SUB_INDICATORS = [
  { key: 'MACD', lines: ['macd', 'macds'], bars: ['macdh'], desc: 'DIF 上穿 DEA 为金叉，柱线由绿翻红表示动能转强（Gerald Appel）。' },
  { key: 'KDJ', lines: ['kdjk', 'kdjd', 'kdjj'], desc: 'K、D 高于 80 超买、低于 20 超卖，K 上穿 D 为金叉（George Lane 随机指标）。' },
  { key: 'RSI', lines: ['rsi_6', 'rsi_12', 'rsi', 'rsi_24'], desc: '高于 70 超买、低于 30 超卖（J. Welles Wilder）。' },
  { key: 'WR', lines: ['wr_6', 'wr_10', 'wr_14'], desc: '通达信刻度：高于 80 超卖、低于 20 超买（Larry Williams %R）。' },
  { key: 'CCI', lines: ['cci', 'cci_84'], desc: '高于 +100 进入强势区，低于 -100 进入弱势区（Donald Lambert）。' },
  { key: 'DMI', lines: ['pdi', 'mdi', 'adx', 'adxr'], desc: 'PDI 上穿 MDI 偏多；ADX 越高趋势越强（J. Welles Wilder）。' },
  { key: 'BIAS', lines: ['bias', 'bias_12', 'bias_24'], desc: '股价偏离均线的百分比，偏离过大有回归需求。' },
  { key: 'TRIX', lines: ['trix', 'trma'], desc: '三重指数平滑的变化率，过滤短期波动，用于判断中长期趋势。' },
  { key: 'PPO', lines: ['ppo', 'ppos'], bars: ['ppoh'], desc: '百分比形式的 MACD，可在不同价位股票间比较。' },
  { key: 'DMA', lines: ['dma', 'ama'], desc: '10 日与 50 日均线差及其均线，DIF 上穿 AMA 偏多。' },
  { key: 'CR', lines: ['cr', 'cr_ma1', 'cr_ma2', 'cr_ma3'], desc: '以昨日中间价衡量多空力量，低于 40 常为低位区域。' },
  { key: 'VR', lines: ['vr', 'mavr'], desc: '上涨日与下跌日成交量之比，40~70 低位、160~450 高位。' },
  { key: 'BRAR', lines: ['br', 'ar'], desc: 'AR 反映人气，BR 反映买卖意愿，数值过高过低均提示反转风险。' },
  { key: 'PSY', lines: ['psy', 'psyma'], desc: '近 12 日上涨天数占比，高于 75 偏热、低于 25 偏冷。' },
  { key: 'ROC', lines: ['roc', 'rocma', 'rocema'], desc: '12 日变动率，衡量价格动量。' },
  { key: 'MFI', lines: ['mfi', 'mfisma'], desc: '成交量加权的 RSI，高于 80 超买、低于 20 超卖（Gene Quong & Avrum Soudack）。' },
  { key: 'OBV', lines: ['obv'], desc: '能量潮：上涨日累加成交量、下跌日累减，用于观察量价背离（Joseph Granville）。' },
  { key: 'EMV', lines: ['emv', 'emva'], desc: '简易波动指标，结合价格变化与成交量衡量上涨难易度（Richard Arms）。' },
  { key: 'WT', lines: ['wt1', 'wt2'], desc: 'WaveTrend 波浪趋势，WT1 上穿 WT2 偏多（LazyBear）。' },
  { key: 'StochRSI', lines: ['stochrsi_k', 'stochrsi_d'], desc: 'RSI 的随机指标，更敏感的超买超卖（Tushar Chande & Stanley Kroll）。' },
  { key: 'RVI', lines: ['rvi', 'rvis'], desc: '相对活力指数，收盘相对开盘的强弱（John Ehlers）。' },
  { key: 'DPO', lines: ['dpo', 'madpo'], desc: '去趋势价格震荡，剔除长期趋势后观察周期。' },
  { key: 'VHF', lines: ['vhf'], desc: '十字过滤线，数值高表示趋势市、低表示震荡市（Adam White）。' },
  { key: 'FI', lines: ['force_2', 'force_13'], desc: '强力指数，价格变化乘以成交量（Alexander Elder）。' },
  { key: 'ATR', lines: ['tr', 'atr'], desc: '真实波幅及其均值，衡量波动大小（J. Welles Wilder）。' },
]

// 主图叠加
export const MAIN_OVERLAYS = [
  { key: 'BOLL', lines: ['boll_ub', 'boll', 'boll_lb'], desc: '布林带：20 日均线 ± 2 倍标准差（John Bollinger）。' },
  { key: 'ENE', lines: ['ene_ue', 'ene', 'ene_le'], desc: '轨道线：10 日均线上下 11% / 9%。' },
  { key: 'SuperTrend', lines: ['supertrend'], desc: 'ATR 通道的趋势跟踪线，价格在线上为多头（Olivier Seban）。' },
  { key: 'SAR', lines: ['sar'], scatter: true, desc: '抛物线转向，价格跌破 SAR 点为转弱信号（J. Welles Wilder）。' },
  { key: 'TEMA', lines: ['tema'], desc: '三重指数移动平均，滞后更小。' },
  { key: 'VWMA', lines: ['vwma'], desc: '成交量加权移动平均。' },
]

export const INDICATOR_LABELS = {
  macd: 'DIF', macds: 'DEA', macdh: 'MACD', kdjk: 'K', kdjd: 'D', kdjj: 'J', rsi_6: 'RSI6', rsi_12: 'RSI12',
  rsi: 'RSI14', rsi_24: 'RSI24', wr_6: 'WR6', wr_10: 'WR10', wr_14: 'WR14', cci: 'CCI14', cci_84: 'CCI84',
  pdi: 'PDI', mdi: 'MDI', adx: 'ADX', adxr: 'ADXR', bias: 'BIAS6', bias_12: 'BIAS12', bias_24: 'BIAS24',
  trix: 'TRIX', trma: 'TRMA', ppo: 'PPO', ppos: '信号线', ppoh: '柱', dma: 'DIF', ama: 'AMA', cr: 'CR',
  cr_ma1: 'MA1', cr_ma2: 'MA2', cr_ma3: 'MA3', vr: 'VR', mavr: 'MAVR', br: 'BR', ar: 'AR', psy: 'PSY',
  psyma: 'PSYMA', roc: 'ROC', rocma: 'MAROC', rocema: 'EMAROC', mfi: 'MFI', mfisma: 'MA', obv: 'OBV', emv: 'EMV',
  emva: 'MAEMV', wt1: 'WT1', wt2: 'WT2', stochrsi_k: 'K', stochrsi_d: 'D', rvi: 'RVI', rvis: '信号线', dpo: 'DPO',
  madpo: 'MADPO', vhf: 'VHF', force_2: 'FI2', force_13: 'FI13', tr: 'TR', atr: 'ATR', boll_ub: '上轨',
  boll: '中轨', boll_lb: '下轨', ene_ue: '上轨', ene: 'ENE', ene_le: '下轨', supertrend: 'SuperTrend', sar: 'SAR',
  tema: 'TEMA', vwma: 'VWMA',
}
