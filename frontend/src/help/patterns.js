// K 线形态说明。键为后端形态列名（instock/analysis/patterns.py）。
// dir：bull 看涨、bear 看跌、both 双向（TA-Lib 以正负号区分）、neutral 中性（TA-Lib 虽给出正负号，
// 但正负只代表阴阳或固定为正，形态本身不判断方向，需要结合所处位置理解）。
// TA-Lib 的取值：±100 为普通信号，±200 为经过后续 K 线确认的信号（仅陷阱类形态）。
export const PATTERN_HELP = {
  two_crows: { dir: 'bear', desc: '上涨中先出现长阳线，随后跳空高开收出小阴线，第三根阴线开在第二根实体内、收进第一根阳线实体，上涨动能衰竭。' },
  upside_gap_two_crows: { dir: 'bear', desc: '长阳线后向上跳空出现小阴线，第三根阴线吞没第二根但收盘仍高于第一根，跳空缺口随时可能被回补。' },
  three_black_crows: { dir: 'bear', desc: '连续三根长阴线，每根都在前一根实体内开盘、收在最低价附近。出现在上涨后是强烈的看跌反转信号。' },
  identical_three_crows: { dir: 'bear', desc: '三只乌鸦的加强版：每根阴线的开盘价约等于前一根的收盘价，卖压更集中。' },
  three_line_strike: { dir: 'both', desc: '三根同方向的K线之后，第四根反向长K线一口气吞没前三根。原意是消化获利后的趋势延续，方向取决于前三根K线。' },
  dark_cloud_cover: { dir: 'bear', desc: '长阳线后次日高开低走收阴，收盘深入前一根阳线实体一半以下，像乌云遮住阳光，看跌反转。' },
  evening_doji_star: { dir: 'bear', desc: '暮星的变体：长阳线、跳空十字星、长阴线三根组合，中间为十字星，见顶信号比暮星更强。' },
  doji_star: { dir: 'both', desc: '一根长K线后跳空出现十字星，表示原趋势受阻、多空转为平衡。上涨后出现看跌，下跌后出现看涨。' },
  hanging_man: { dir: 'bear', desc: '上涨后出现小实体、长下影线的K线（外形与锤头相同），说明盘中曾遭大幅抛售，提示上涨可能见顶。' },
  hikkake_pattern: { dir: 'both', desc: '内包线之后出现一次假突破，随后价格反向突破。值为 ±200 表示已被后续K线确认。' },
  modified_hikkake_pattern: { dir: 'both', desc: '陷阱形态的修正版，要求内包线之前还有一根更窄的K线，过滤掉部分噪声信号。' },
  in_neck_pattern: { dir: 'bear', desc: '下跌中长阴线后低开收小阳，收盘仅略高于前一根阴线的收盘价，反弹无力，下跌大概率延续。' },
  on_neck_pattern: { dir: 'bear', desc: '与颈内线类似，小阳线收盘约等于前一根阴线的最低价，反弹更弱，属下跌延续形态。' },
  thrusting_pattern: { dir: 'bear', desc: '下跌中长阴线后收阳，收盘深入前阴线实体但未超过一半，反弹力度不足，偏向下跌延续。' },
  shooting_star: { dir: 'bear', desc: '上涨后出现小实体、长上影线的K线，说明冲高后被大量抛压打回，看跌反转。' },
  stalled_pattern: { dir: 'bear', desc: '连续三根阳线，但第三根实体明显变小或跳空后滞涨，上涨动能减弱。' },
  advance_block: { dir: 'bear', desc: '连续三根阳线，但实体逐根缩小、上影线逐根变长，表示上涨越来越吃力。' },
  high_wave_candle: { dir: 'neutral', desc: '实体很小、上下影线都很长，多空分歧极大。出现在大涨或大跌之后常预示变盘。' },
  engulfing_pattern: { dir: 'both', desc: '第二根K线的实体完全包住前一根相反颜色的实体。下跌后的阳包阴看涨，上涨后的阴包阳看跌。' },
  abandoned_baby: { dir: 'both', desc: '长K线后跳空出现十字星，次日再反向跳空，十字星被两侧缺口孤立，是罕见而强烈的反转信号。' },
  closing_marubozu: { dir: 'both', desc: '收盘一侧没有影线：阳线收在最高价、阴线收在最低价，收盘时一方完全占优。' },
  doji: { dir: 'neutral', desc: '开盘价与收盘价几乎相同，多空暂时平衡。本身不判断方向，出现在长期上涨或下跌后才有反转意义。' },
  up_down_gap: { dir: 'both', desc: '跳空后连续出现两根开盘价相近、大小相近的阳线，缺口未被回补，原方向大概率延续。' },
  long_legged_doji: { dir: 'neutral', desc: '上下影线都很长的十字星，盘中剧烈波动但收盘回到开盘价，市场犹豫不决。' },
  rickshaw_man: { dir: 'neutral', desc: '长脚十字的一种，开盘收盘位于全天波动区间的中部，多空完全均衡。' },
  marubozu: { dir: 'both', desc: '几乎没有上下影线的长实体K线（光头光脚），阳线代表买方全天主导，阴线代表卖方全天主导。' },
  three_inside_up_down: { dir: 'both', desc: '母子线之后，第三根K线向反方向突破第一根K线的收盘价，是对母子线反转的确认。' },
  three_outside_up_down: { dir: 'both', desc: '吞噬形态之后，第三根K线继续朝吞噬方向收盘，是对吞噬反转的确认。' },
  three_stars_in_the_south: { dir: 'bull', desc: '下跌中三根阴线的实体与下影线逐步缩小，最后一根为小实体，卖压逐渐衰竭，看涨反转。' },
  three_white_soldiers: { dir: 'bull', desc: '连续三根长阳线，每根在前一根实体内开盘、收在最高价附近，稳步推升，看涨。' },
  belt_hold: { dir: 'both', desc: '开盘即为全天最低（阳线）或最高（阴线）后一路单边收盘，出现在趋势末端时提示反转。' },
  breakaway: { dir: 'both', desc: '顺势跳空后连续几根K线延续原方向，第五根长K线反向收盘并回补缺口，趋势反转。' },
  concealing_baby_swallow: { dir: 'bull', desc: '下跌末端连续两根光头光脚阴线后，出现被吞没的跳空小阴线，卖方力量耗尽，罕见的看涨形态。' },
  counterattack: { dir: 'both', desc: '两根颜色相反的长K线收盘价几乎相同：第二根大幅跳空后反向拉回，原趋势受到强力反击。' },
  dragonfly_doji: { dir: 'neutral', desc: '开盘、收盘、最高价几乎相同，带长下影线的T字形十字星。出现在下跌末端时偏看涨。' },
  evening_star: { dir: 'bear', desc: '长阳线、跳空小实体、长阴线三根组合，阴线收盘深入第一根阳线实体，经典的见顶信号。' },
  gravestone_doji: { dir: 'neutral', desc: '开盘、收盘、最低价几乎相同，带长上影线的倒T字形十字星。出现在上涨末端时偏看跌。' },
  hammer: { dir: 'bull', desc: '下跌后出现小实体、长下影线（至少为实体两倍）的K线，说明盘中下探后被买盘拉回，看涨反转。' },
  harami_pattern: { dir: 'both', desc: '第二根小实体完全位于前一根长实体之内（母亲怀子），原趋势动能减弱，可能反转。' },
  harami_cross_pattern: { dir: 'both', desc: '母子线中第二根为十字星，趋势停顿的信号比普通母子线更强。' },
  homing_pigeon: { dir: 'bull', desc: '下跌中长阴线后出现完全位于其实体内的小阴线，卖压减轻，看涨。' },
  inverted_hammer: { dir: 'bull', desc: '下跌后出现小实体、长上影线的K线，说明买方开始尝试反攻，需要次日上涨确认。' },
  kicking: { dir: 'both', desc: '一根光头光脚K线后，反方向跳空出现另一根相反颜色的光头光脚K线，强烈反转信号。' },
  kicking_bull_bear: { dir: 'both', desc: '反冲形态，由两根光头光脚K线中实体较长的一根决定方向。' },
  ladder_bottom: { dir: 'bull', desc: '连续三根阴线逐级下跌，第四根带长上影线，第五根跳空高开收阳，下跌结束的信号。' },
  long_line_candle: { dir: 'both', desc: '实体明显长于近期平均水平的K线，阳线表示买方强势，阴线表示卖方强势。' },
  matching_low: { dir: 'bull', desc: '下跌中连续两根阴线收盘价相同，形成短期支撑，看涨。' },
  mat_hold: { dir: 'bull', desc: '长阳线后跳空，接着几根小K线回调但不跌破长阳线，随后再次长阳突破，上涨延续。' },
  morning_doji_star: { dir: 'bull', desc: '晨星的变体：长阴线、跳空十字星、长阳线三根组合，见底信号比晨星更强。' },
  morning_star: { dir: 'bull', desc: '长阴线、跳空小实体、长阳线三根组合，阳线收盘深入第一根阴线实体，经典的见底信号。' },
  piercing_pattern: { dir: 'bull', desc: '长阴线后次日低开高走收阳，收盘越过前阴线实体的一半，看涨反转（与乌云压顶相反）。' },
  rising_falling_three: { dir: 'both', desc: '一根长K线后三根左右的小K线反向整理但不超出长K线范围，随后再出现同向长K线突破，原趋势延续。' },
  separating_lines: { dir: 'both', desc: '两根颜色相反的K线开盘价相同，第二根顺原趋势方向大幅运行，原趋势延续。' },
  short_line_candle: { dir: 'neutral', desc: '实体与影线都明显短于近期平均水平的K线，表示交投清淡、观望情绪浓。' },
  spinning_top: { dir: 'neutral', desc: '小实体、上下影线长于实体的K线，多空力量接近，表示犹豫。' },
  stick_sandwich: { dir: 'bull', desc: '两根收盘价相同的阴线中间夹一根阳线，形成支撑位，看涨。' },
  takuri: { dir: 'bull', desc: '下影线极长（至少为实体三倍）、几乎没有上影线的K线，类似蜻蜓十字，下探后被强力拉回。' },
  tasuki_gap: { dir: 'both', desc: '跳空后第二根同向K线延续，第三根反向K线回补部分缺口但未完全回补，原趋势延续。' },
  tristar_pattern: { dir: 'both', desc: '连续三根十字星，中间一根跳空，罕见的反转信号。' },
  unique_3_river: { dir: 'bull', desc: '长阴线后出现创新低但收回的锤形阴线，第三根小阳线收在第二根实体下方，见底信号。' },
  upside_downside_gap: { dir: 'both', desc: '同向跳空的两根K线后，第三根反向K线回补缺口，原趋势通常延续。' },
}

export const DIR_LABELS = { bull: '看涨', bear: '看跌', both: '双向', neutral: '中性' }

/** 形态信号值的文字：中性形态不显示方向。 */
export function patternSignalText(key, value) {
  if (!value) return ''
  const confirmed = Math.abs(value) >= 200 ? '·确认' : ''
  if (PATTERN_HELP[key]?.dir === 'neutral') return `出现${confirmed}`
  return `${value > 0 ? '看涨' : '看跌'}${confirmed}`
}

/** 形态信号的方向：up 看涨、down 看跌、flat 中性。 */
export function patternDirection(key, value) {
  if (!value || PATTERN_HELP[key]?.dir === 'neutral') return 'flat'
  return value > 0 ? 'up' : 'down'
}
