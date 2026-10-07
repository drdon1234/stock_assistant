// 术语表：学习中心展示，数据表列头悬停提示也从这里取解释（cols 为对应的后端列名）。
export const TERM_CATEGORIES = ['交易规则', '行情基础', '估值', '财务', '股东与机构', '资金', '事件', '回测与统计']

export const TERMS = [
  // 交易规则
  { term: '交易时间', cat: '交易规则', desc: '沪深交易所交易日 9:30–11:30、13:00–15:00 连续竞价；9:15–9:25 开盘集合竞价，14:57–15:00 收盘集合竞价。' },
  { term: 'T+1', cat: '交易规则', desc: 'A 股当天买入的股票最早下一个交易日才能卖出，因此“次日开盘买入”是回测中最贴近实际的口径。' },
  { term: '涨跌停', cat: '交易规则', desc: '单日涨跌幅上限：主板 ±10%（风险警示股自 2025 年 7 月起也由 ±5% 调整为 ±10%），创业板与科创板 ±20%。触及涨停时往往难以买入，跌停时难以卖出。' },
  { term: '手', cat: '交易规则', desc: '1 手 = 100 股，买入数量须为 100 股的整数倍。本站成交量单位为手。' },
  { term: 'ST / *ST', cat: '交易规则', desc: '因财务或经营异常被实施风险警示的股票，*ST 表示存在退市风险，波动和风险都明显更大。' },
  { term: '红涨绿跌', cat: '交易规则', desc: 'A 股习惯用红色表示上涨、绿色表示下跌，与欧美市场相反。本站也遵循这一习惯。' },
  { term: '前复权', cat: '交易规则', desc: '把分红、送转导致的价格跳空调整掉，以当前价为基准向前修正历史价格，使 K 线连续。本站 K 线与技术指标均使用前复权数据。' },

  // 行情基础
  { term: '最新价', cat: '行情基础', cols: ['new_price'], desc: '最近一笔成交价；收盘后即当日收盘价。' },
  { term: '涨跌幅', cat: '行情基础', cols: ['change_rate'], desc: '（最新价 − 昨收）÷ 昨收。' },
  { term: '涨跌额', cat: '行情基础', cols: ['ups_downs'], desc: '最新价 − 昨收，单位元。' },
  { term: '成交量', cat: '行情基础', cols: ['volume'], desc: '当日成交的股数，单位手（100 股）。价格上涨同时放量通常被认为更可信。' },
  { term: '成交额', cat: '行情基础', cols: ['deal_amount'], desc: '当日成交的金额，反映资金参与程度。' },
  { term: '振幅', cat: '行情基础', cols: ['amplitude'], desc: '（最高价 − 最低价）÷ 昨收，衡量当日波动大小。' },
  { term: '换手率', cat: '行情基础', cols: ['turnoverrate'], desc: '成交量 ÷ 流通股本，衡量交易活跃度。长期高于 10% 通常意味着投机性较强。' },
  { term: '量比', cat: '行情基础', cols: ['volume_ratio'], desc: '当日每分钟平均成交量 ÷ 过去 5 日每分钟平均成交量。大于 1 为放量，小于 1 为缩量。' },
  { term: '开高低收', cat: '行情基础', cols: ['open_price', 'high_price', 'low_price', 'pre_close_price'], desc: '今开、最高、最低价与昨收价，是 K 线的四个要素。' },
  { term: '区间涨跌幅', cat: '行情基础', cols: ['speed_increase_60', 'speed_increase_all', 'changerate_3days', 'changerate_5days', 'changerate_10days', 'changerate_ty'], desc: '一段时间内的累计涨跌幅，用于观察中短期强弱。' },
  { term: '连涨/连跌天数', cat: '行情基础', cols: ['upnday', 'downnday'], desc: '截至当日连续上涨或下跌的交易日数。' },
  { term: 'K 线', cat: '行情基础', desc: '用开盘、收盘、最高、最低四个价格画出的“蜡烛”。收盘高于开盘为阳线（红），反之为阴线（绿）；实体上下的细线为影线。' },
  { term: '均线', cat: '行情基础', desc: '最近 N 个交易日收盘价的平均值。5/10 日看短线，20/60 日看中线，120/250 日看长线；股价在均线上方且均线向上视为上升趋势。' },
  { term: '成分股', cat: '行情基础', cols: ['is_hs300', 'is_sz50', 'is_zz500', 'is_zz1000', 'is_cy50'], desc: '是否属于该指数的成分股。沪深 300 代表大盘蓝筹，中证 500/1000 代表中小盘。' },
  { term: '行业 / 概念 / 板块', cat: '行情基础', cols: ['industry', 'concept', 'style', 'area'], desc: '行业是公司的主营业务分类；概念是市场热点题材，一只股票可属于多个概念。' },
  { term: '上市时间', cat: '行情基础', cols: ['listing_date'], desc: '上市不满一年的次新股历史数据较少，部分技术策略无法计算。' },

  // 估值
  { term: '市盈率 PE', cat: '估值', cols: ['pe9', 'pe', 'dtsyl', 'pettmdeducted'], desc: '总市值 ÷ 净利润，可粗略理解为按当前盈利“回本”需要的年数。TTM 用最近四个季度利润，静态用上一年度，动态用最新季度年化。亏损时为负，没有参考意义。不同行业的合理水平差别很大。' },
  { term: '预测市盈率', cat: '估值', cols: ['predict_pe_syear', 'predict_pe_nyear'], desc: '用分析师对今年或明年净利润的一致预测计算的市盈率。' },
  { term: '市净率 PB', cat: '估值', cols: ['pbnewmrq'], desc: '总市值 ÷ 净资产。低于 1 称为“破净”，常见于银行、钢铁等重资产行业。' },
  { term: '市销率 / 市现率', cat: '估值', cols: ['ps9', 'pcfjyxjl9'], desc: '总市值分别除以营业收入、经营现金流，适合评估暂时亏损或利润波动大的公司。' },
  { term: 'PEG', cat: '估值', cols: ['ycpeg'], desc: '市盈率 ÷ 盈利增长率（%）。彼得·林奇认为约等于 1 较合理，明显小于 1 可能被低估。' },
  { term: '企业价值倍数', cat: '估值', cols: ['enterprise_value_multiple'], desc: 'EV/EBITDA，企业价值 ÷ 息税折旧摊销前利润，排除了资本结构差异，便于跨公司比较。' },
  { term: '总市值 / 流通市值', cat: '估值', cols: ['total_market_cap', 'free_cap'], desc: '股价 × 总股本 / 流通股本。流通市值越小，股价越容易被资金推动、波动越大。' },
  { term: '股息率', cat: '估值', cols: ['zxgxl', 'bonusaward_yield'], desc: '近 12 个月每股现金分红 ÷ 股价，类似存款利率，是价值投资者关注的回报来源。' },
  { term: '破发 / 破净', cat: '估值', cols: ['is_issue_break', 'is_bps_break'], desc: '破发：股价跌破发行价；破净：股价跌破每股净资产。' },

  // 财务
  { term: '每股收益 EPS', cat: '财务', cols: ['basic_eps'], desc: '净利润 ÷ 总股本，每股赚了多少钱。' },
  { term: '每股净资产', cat: '财务', cols: ['bvps'], desc: '净资产 ÷ 总股本，每股对应的账面价值。' },
  { term: '每股公积金 / 未分配利润', cat: '财务', cols: ['per_capital_reserve', 'per_unassign_profit', 'per_surplus_reserve', 'per_retained_earning'], desc: '公司积累的资本公积与未分配利润，数值较高的公司具备送转或分红能力。' },
  { term: '每股现金流', cat: '财务', cols: ['per_netcash_operate', 'per_fcfe'], desc: '每股经营现金流与自由现金流。利润为正但现金流长期为负，需警惕利润质量。' },
  { term: '营业收入 / 净利润', cat: '财务', cols: ['total_operate_income', 'parent_netprofit', 'deduct_netprofit'], desc: '公司卖了多少钱、最终赚了多少钱。扣非净利润剔除了卖资产、政府补贴等一次性收益，更能反映主业。' },
  { term: 'ROE 净资产收益率', cat: '财务', cols: ['roe_weight'], desc: '净利润 ÷ 净资产，衡量股东投入的钱赚钱的效率。长期稳定在 15% 以上通常被视为优秀公司。' },
  { term: 'ROA / ROIC', cat: '财务', cols: ['jroa', 'roic'], desc: '总资产收益率与投入资本回报率，从不同角度衡量资本使用效率。' },
  { term: '毛利率 / 净利率', cat: '财务', cols: ['sale_gpr', 'sale_npr'], desc: '毛利率 =（收入 − 成本）÷ 收入，反映产品竞争力；净利率 = 净利润 ÷ 收入。' },
  { term: '增长率', cat: '财务', cols: ['netprofit_yoy_ratio', 'deduct_netprofit_growthrate', 'toi_yoy_ratio', 'netprofit_growthrate_3y', 'income_growthrate_3y', 'basiceps_yoy_ratio', 'total_profit_growthrate', 'operate_profit_growthrate', 'predict_netprofit_ratio', 'predict_income_ratio'], desc: '同比增长率与相对去年同期的比较；3 年复合增长率反映持续成长能力；预测值来自分析师一致预期。' },
  { term: '资产负债率', cat: '财务', cols: ['debt_asset_ratio', 'equity_ratio', 'equity_multiplier'], desc: '总负债 ÷ 总资产。过高意味着财务风险大；银行、地产等行业天然偏高。' },
  { term: '流动比率 / 速动比率', cat: '财务', cols: ['current_ratio', 'speed_ratio'], desc: '流动资产（速动比率再扣除存货）÷ 流动负债，衡量短期偿债能力。格雷厄姆要求流动比率不低于 2。' },
  { term: '总股本 / 流通股本', cat: '财务', cols: ['total_shares', 'free_shares'], desc: '公司全部股份与可在二级市场自由交易的股份。' },
  { term: '商誉', cat: '财务', cols: ['goodwill_scale', 'goodwill_assets_ratro'], desc: '并购时支付的高于被收购方净资产的溢价。商誉占净资产比例高的公司存在减值导致巨亏的风险。' },
  { term: '业绩预告', cat: '财务', cols: ['predict_type'], desc: '公司在正式财报前对业绩的预告类型，如预增、预减、扭亏、首亏等。' },

  // 股东与机构
  { term: '股东户数', cat: '股东与机构', cols: ['holder_newest', 'holder_ratio', 'hold_amount', 'avg_hold_num', 'holdnum_growthrate_3q', 'holdnum_growthrate_hy'], desc: '持股的账户数量。户数减少、户均持股增加，说明筹码向少数人集中。' },
  { term: '十大股东持股', cat: '股东与机构', cols: ['hold_ratio_count', 'free_hold_ratio'], desc: '前十大股东（或前十大流通股东）合计持股比例，越高说明股权越集中。' },
  { term: '机构持股', cat: '股东与机构', cols: ['allcorp_num', 'allcorp_fund_num', 'allcorp_qs_num', 'allcorp_qfii_num', 'allcorp_bx_num', 'allcorp_sb_num', 'allcorp_xt_num', 'allcorp_ratio', 'allcorp_fund_ratio', 'allcorp_qs_ratio', 'allcorp_qfii_ratio', 'allcorp_bx_ratio', 'allcorp_sb_ratio', 'allcorp_xt_ratio'], desc: '基金、券商、QFII、保险、社保、信托等机构的持股家数与比例。' },
  { term: '股东/高管增减持', cat: '股东与机构', cols: ['holder_change_3m', 'executive_change_3m'], desc: '近 3 个月重要股东与高管的增持或减持比例。内部人增持通常被视为积极信号。' },
  { term: '机构调研 / 评级', cat: '股东与机构', cols: ['org_survey_3m', 'org_rating'], desc: '近 3 个月接待机构调研的次数，以及券商研究员的综合评级。' },
  { term: '质押比例', cat: '股东与机构', cols: ['pledge_ratio', 'equity_pledge_1m', 'equity_pledge_3m', 'equity_pledge_6m', 'equity_pledge_1y'], desc: '股东把股票质押借款的比例。质押比例高的公司在股价大跌时有被强制平仓的风险。' },
  { term: '限售解禁', cat: '股东与机构', cols: ['limited_lift_f6m', 'limited_lift_f1y', 'limited_lift_6m', 'limited_lift_1y'], desc: '原本不能交易的限售股到期可以卖出，解禁前后可能面临抛售压力。' },
  { term: '定向增发 / 资产重组', cat: '股东与机构', cols: ['directional_seo_1m', 'directional_seo_3m', 'directional_seo_6m', 'directional_seo_1y', 'recapitalize_1m', 'recapitalize_3m', 'recapitalize_6m', 'recapitalize_1y'], desc: '向特定对象发行新股融资，或进行并购、资产置换等重大资本运作。' },
  { term: '沪深股通（北向资金）', cat: '股东与机构', cols: ['hold_ratio', 'mutual_netbuy_amt'], desc: '境外投资者经香港买卖 A 股的通道。常被视为“聪明钱”，但近年披露口径有所调整。' },
  { term: '股吧人气', cat: '股东与机构', cols: ['popularity_rank', 'rank_change', 'upp_days', 'down_days', 'new_high', 'new_down', 'newfans_ratio', 'bigfans_ratio', 'concern_rank_7days', 'browse_rank'], desc: '东方财富股吧的关注与浏览排名，反映散户关注度。人气过热常伴随短期高点。' },

  // 资金
  { term: '主力资金', cat: '资金', cols: ['fund_amount', 'fund_amount_3', 'fund_amount_5', 'fund_amount_10', 'net_inflow', 'netinflow_3days', 'netinflow_5days'], desc: '数据商按单笔成交金额把成交拆成超大单、大单、中单、小单，超大单与大单合称主力。净流入 = 主动买入额 − 主动卖出额。它是根据成交单大小推算的，并不等于机构账户的真实买卖，参考价值有限。' },
  { term: '超大单 / 大单 / 中单 / 小单', cat: '资金', desc: '按单笔成交金额大小划分的成交单类别，各数据商阈值略有不同。小单常被视为散户资金。' },
  { term: '净占比', cat: '资金', cols: ['fund_rate'], desc: '净流入额 ÷ 当日成交额，便于比较不同规模股票的资金流向强度。' },
  { term: '增仓占比', cat: '资金', cols: ['nowinterst_ratio', 'nowinterst_ratio_3d', 'nowinterst_ratio_5d'], desc: '主力净流入占流通市值的比例。' },
  { term: 'DDX / DDE', cat: '资金', cols: ['ddx', 'ddx_3d', 'ddx_5d', 'ddx_red_10d', 'dde'], desc: '大单动向指标：大单买入净量占流通盘的比例，正值（飘红）表示大单净买入。' },

  // 事件
  { term: '龙虎榜', cat: '事件', desc: '股票出现日涨跌幅偏离值达 7%、换手率达 20%、连续三日涨跌幅偏离累计 20% 等异常情况时，交易所公布当日买入、卖出金额最大的五家营业部或机构席位。' },
  { term: '龙虎榜净买额', cat: '事件', cols: ['net_amount_buy', 'sum_buy', 'sum_sell', 'lhb_amount', 'market_amount', 'net_amount_rate', 'sum_rate'], desc: '上榜席位的合计买入减卖出。净买额大、且有机构专用席位买入，通常被视为资金认可。' },
  { term: '上榜后涨跌', cat: '事件', cols: ['ranking_after_1', 'ranking_after_2', 'ranking_after_5', 'ranking_after_10'], desc: '上榜之后 1/2/5/10 个交易日的涨跌幅，用于观察龙虎榜资金的后续效果。' },
  { term: '大宗交易', cat: '事件', desc: '单笔数量或金额达到交易所规定标准的交易，在盘后单独撮合。大幅折价成交常意味着大股东或机构减持。' },
  { term: '折溢率', cat: '事件', cols: ['overflow_rate'], desc: '大宗交易成交价相对当日收盘价的偏离，负值为折价、正值为溢价。' },
  { term: '分红配送', cat: '事件', cols: ['plan_profile', 'convertible_total_rate', 'convertible_rate', 'convertible_transfer_rate', 'bonusaward_rate'], desc: '送股（利润转为股本）、转增（公积金转为股本）与现金分红，数值均按每 10 股计算。送转本身不改变公司价值。' },
  { term: '股权登记日 / 除权除息日', cat: '事件', cols: ['record_date', 'ex_dividend_date', 'plan_date', 'report_date', 'progress'], desc: '登记日收盘时持有股票才能获得分红送转；除权除息日股价按分红送转相应下调。' },
  { term: '集合竞价抢筹', cat: '事件', cols: ['bid_rate', 'bid_trust_amount', 'bid_deal_amount', 'bid_ratio', 'open_price'], desc: '开盘（9:15–9:25）或收盘（14:57–15:00）集合竞价阶段买盘委托明显强于卖盘的股票，反映资金的抢筹意愿。' },
  { term: '连板', cat: '事件', cols: ['limitup_day', 'limitup_board'], desc: '连续涨停的天数。连板股情绪高涨，但断板后的回撤也往往很大。' },
  { term: '涨停原因', cat: '事件', cols: ['title', 'reason'], desc: '数据商对当日涨停股所属题材与驱动因素的归纳，仅供了解市场热点。' },

  // 回测与统计
  { term: '信号', cat: '回测与统计', desc: '某只股票在某个交易日收盘后满足了某个策略的全部条件。信号只是候选，不等于买卖建议。' },
  { term: 'N 日收益', cat: '回测与统计', cols: ['ret_1', 'ret_3', 'ret_5', 'ret_10', 'ret_20', 'ret_60'], desc: '信号次日开盘价买入、持有 N 个交易日后按收盘价计算的收益。尚未走完 N 天的信号为空，数据会随时间自动补齐。' },
  { term: '基准收益', cat: '回测与统计', desc: '同一天全部 A 股按同样口径（次日开盘买入、持有 N 天）计算的等权平均收益，代表“随便买一只”的平均结果。' },
  { term: '超额收益', cat: '回测与统计', desc: '策略收益 − 同日基准收益。买入策略的超额收益为正说明比随便买更好；卖出策略的超额收益为负说明卖出后股价确实跑输市场，信号有效。' },
  { term: '胜率', cat: '回测与统计', desc: '收益为正的信号占比。胜率高不代表赚钱：趋势类策略胜率常低于 50%，靠少数大赚弥补多数小亏。' },
  { term: '样本数', cat: '回测与统计', desc: '参与统计的信号数量。样本太少（几十个以内）时统计结果偶然性很大。' },
  { term: '相对强度 RS', cat: '回测与统计', desc: '欧奈尔与 IBD 使用的排名：按近一年（最近一季权重更高）涨幅给全部股票排百分位，99 表示强于 99% 的股票。' },
  { term: 'ATR 平均真实波幅', cat: '回测与统计', desc: '真实波幅（当日最高最低价差与跳空缺口中的较大者）的 N 日平均，衡量股票正常的日波动幅度，常用于设置止损距离。' },
]

const BY_COL = {}
for (const t of TERMS) for (const c of t.cols || []) BY_COL[c] = t

/** 列的解释。资金流向等带周期后缀的列（fund_amount_super_5）按前缀匹配。 */
export function columnHelp(name) {
  if (BY_COL[name]) return BY_COL[name].desc
  const base = name.replace(/_(3|5|10)$/, '').replace(/_(super|large|medium|small)$/, '')
  if (base.startsWith('fund_amount')) return BY_COL.fund_amount.desc
  if (base.startsWith('fund_rate')) return BY_COL.fund_rate.desc
  return BY_COL[base]?.desc || ''
}
