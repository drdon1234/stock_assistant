"""选股策略。每个策略都给出规则与出处，规则尽量忠实于原始文献，参数取文献给出的数值。

技术面策略 check(b, i) 判断第 i 根 K 线收盘后是否满足条件（只使用 i 及之前的数据）；
基本面策略对当日综合选股数据做横截面筛选。
kind：buy 买入信号，sell 卖出/风险信号。卖出策略多为跌破类规则，只在首次跌破当日触发，避免下跌途中每天重复出现。
plain 为面向初学者的通俗解释，tips 为原作者给出的配套用法与注意事项。
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    kind: str
    rule: str
    source: str
    plain: str = ''
    tips: str = ''
    min_bars: int = 0
    check: Callable = None  # 技术面：check(bars, i) -> bool
    screen: Callable = None  # 基本面：screen(selection_df) -> 满足条件的行
    min_rs: int = 0  # 需要相对强度百分位不低于该值（横截面排名，在全部股票算完后过滤）


def _turtle(b, i):
    return b.close[i] > b.high[i - 55:i].max()


def _trend_template(b, i):
    c = b.close[i]
    ma50, ma150, ma200 = b.ma(50)[i], b.ma(150)[i], b.ma(200)[i]
    low52, high52 = b.low[i - 251:i + 1].min(), b.high[i - 251:i + 1].max()
    return (c > ma150 and c > ma200 and ma150 > ma200 and ma200 > b.ma(200)[i - 22]
            and ma50 > ma150 and c > ma50 and c >= 1.3 * low52 and c >= 0.75 * high52)


def _granville(b, i):
    ma200 = b.ma(200)
    window = slice(i - 9, i + 1)
    before = slice(i - 30, i - 4)
    return (ma200[i] > ma200[i - 20]
            and np.all(b.close[window] >= ma200[window])
            and np.min(b.low[window] / ma200[window]) <= 1.03
            and np.max(b.close[before] / ma200[before]) >= 1.08
            and b.close[i] > b.close[i - 1] and b.close[i] > b.open[i])


def _flat_base_breakout(b, i):
    base = slice(i - 25, i)
    pivot = b.high[base].max()
    prior_low = b.low[i - 85:i - 25].min()
    return (b.close[i] > pivot
            and b.low[base].min() >= 0.85 * pivot
            and pivot >= 1.2 * prior_low
            and b.volume[i] >= 1.5 * b.vol_ma(50)[i - 1])


def _high_tight_flag(b, i):
    p = i - 20 + int(np.argmax(b.high[i - 20:i]))  # 旗面起点：近 20 日最高点
    if i - p - 1 < 3:
        return False
    peak = b.high[p]
    return (b.close[i] > peak
            and peak >= 1.9 * b.low[p - 40:p + 1].min()
            and b.low[p + 1:i].min() >= 0.75 * peak)


def _id_nr4(b, i):
    rng = b.high[i - 3:i + 1] - b.low[i - 3:i + 1]
    return b.high[i] < b.high[i - 1] and b.low[i] > b.low[i - 1] and rng[-1] < rng[:-1].min()


def _rsi2(b, i):
    return b.close[i] > b.ma(200)[i] and b.rsi(2)[i] < 10


def _bollinger_squeeze(b, i):
    ind = b.indicators()
    width = (ind['boll_ub'] - ind['boll_lb']) / ind['boll']
    return np.nanmin(width[i - 5:i]) <= np.nanmin(width[i - 125:i]) and b.close[i] > ind['boll_ub'][i]


def _oversold(b, i):
    ind = b.indicators()
    return (ind['rsi'][i] < 30 and ind['kdjk'][i] < 20 and ind['kdjd'][i] < 20
            and ind['cci'][i] < -100 and ind['wr_14'][i] > 80)


def _overbought(b, i):
    ind = b.indicators()
    return (ind['rsi'][i] > 70 and ind['kdjk'][i] > 80 and ind['kdjd'][i] > 80
            and ind['cci'][i] > 100 and ind['wr_14'][i] < 20)


def _turtle_exit(b, i):
    return b.close[i] < b.low[i - 20:i].min() and b.close[i - 1] >= b.low[i - 21:i - 1].min()


def _chandelier_exit(b, i):
    stop = b.hhv(22) - 3 * b.atr(22)
    return b.close[i] < stop[i] and b.close[i - 1] >= stop[i - 1]


def _ma50_break(b, i):
    ma50 = b.ma(50)
    return (b.close[i] < ma50[i] and b.close[i - 1] >= ma50[i - 1]
            and b.volume[i] >= 1.5 * b.vol_ma(50)[i - 1])


def _granville_sell(b, i):
    ma200 = b.ma(200)
    return (ma200[i - 20] > ma200[i - 60] and ma200[i] <= ma200[i - 20]
            and b.close[i] < ma200[i] and b.close[i - 1] >= ma200[i - 1])


def _graham(df):
    pe, pb = df['pe9'], df['pbnewmrq']
    mask = ((df['total_operate_income'] >= 5e9) & (df['current_ratio'] >= 2)
            & (pe > 0) & (pe <= 15) & (pb > 0) & (pe * pb <= 22.5)
            & (df['zxgxl'] > 0) & (df['parent_netprofit'] > 0) & (df['netprofit_growthrate_3y'] > 0))
    return df[mask]


STRATEGIES = (
    Strategy(
        'turtle', '海龟交易法则', 'buy',
        '收盘价突破此前 55 个交易日的最高价（海龟系统二入场规则）。',
        'Curtis Faith,《Way of the Turtle》(2007)；唐奇安通道突破（Richard Donchian）',
        plain='股价创近 55 个交易日（约 3 个月）新高，说明可能开启新一轮上涨，趋势跟踪者顺势买入。',
        tips='原系统配合“海龟离场”（跌破 20 日最低价）离场，并以 2 倍 ATR 止损；突破失败很常见，胜率不高，靠少数大趋势获利。',
        min_bars=56, check=_turtle),
    Strategy(
        'trend_template', '趋势模板', 'buy',
        '股价在 150/200 日均线上方；150 日线在 200 日线上方；200 日线至少上行 1 个月；50 日线在 150、200 日线上方；'
        '股价在 50 日线上方；股价较 52 周低点至少高 30%、距 52 周高点不超过 25%；相对强度排名不低于 70。',
        'Mark Minervini,《Trade Like a Stock Market Wizard》(2013) 第 5 章 Trend Template',
        plain='只挑处在稳定上升趋势中、且比市场上大多数股票更强的“领涨股”。',
        tips='它是候选池而不是买点：作者建议在符合模板的股票中，再等待平台突破等具体买点。',
        min_bars=260, check=_trend_template, min_rs=70),
    Strategy(
        'granville', '葛兰碧均线回踩', 'buy',
        '200 日均线上行；此前股价明显高于均线（≥8%），近 10 日回落至距均线 3% 以内但收盘未跌破，当日收阳且上涨。',
        'Joseph Granville,《A Strategy of Daily Stock Market Timing for Maximum Profit》(1960) 移动平均线八大法则之买点三',
        plain='长期上升趋势中，股价回落到 200 日均线附近获得支撑后重新上涨，相当于上升途中的回调买点。',
        tips='若之后收盘有效跌破 200 日均线，买入理由即失效，可参考卖出策略“葛兰碧均线卖点”。',
        min_bars=230, check=_granville),
    Strategy(
        'flat_base_breakout', '平台放量突破', 'buy',
        '前期上涨至少 20% 后形成 5 周（25 个交易日）平台，平台回撤不超过 15%；当日收盘突破平台最高价，'
        '成交量不低于 50 日均量的 1.5 倍。',
        "William O'Neil,《How to Make Money in Stocks》(第 4 版, 2009) 平底形态（Flat Base）与突破放量规则",
        plain='股价上涨后横盘整理一个多月，然后放量突破整理区间，往往是新一段上涨的起点。',
        tips='欧奈尔建议在突破价上方 5% 以内买入，跌破买入价 7%~8% 无条件止损。',
        min_bars=86, check=_flat_base_breakout),
    Strategy(
        'high_tight_flag', '高而窄的旗形', 'buy',
        '约 2 个月（40 个交易日）内上涨至少 90% 形成旗杆，随后 3~20 日旗面整理回撤不超过 25%，当日收盘突破旗面顶部。',
        'Thomas Bulkowski,《Encyclopedia of Chart Patterns》(第 2 版, 2005) High and Tight Flags',
        plain='两个月内股价近乎翻倍，之后小幅回调整理，再次突破时常有强劲延续。形态罕见但历史表现突出。',
        tips='前期涨幅巨大，波动剧烈，务必设好止损。',
        min_bars=61, check=_high_tight_flag),
    Strategy(
        'id_nr4', '内包窄幅（ID/NR4）', 'buy',
        '当日为内包线（最高价低于前日、最低价高于前日），且振幅为近 4 日最窄，预示波动即将放大。',
        'Linda Raschke & Laurence Connors,《Street Smarts》(1995) ID/NR4；Toby Crabel 窄幅区间研究',
        plain='股价连续几天波动越来越小，像弹簧被压紧，预示随后可能出现较大波动；本身不判断方向。',
        tips='原文用法：次日向上突破当日最高价时买入、向下突破最低价时做空（A 股只能做多），需要结合趋势判断方向。',
        min_bars=5, check=_id_nr4),
    Strategy(
        'rsi2', 'RSI(2) 超跌回归', 'buy',
        '收盘价在 200 日均线上方（长期上升趋势），且 2 日 RSI 低于 10。',
        'Larry Connors & Cesar Alvarez,《Short Term Trading Strategies That Work》(2008)',
        plain='长期上升趋势中出现短期急跌，博取短线反弹（均值回归），通常只持有几天。',
        tips='原书离场规则：收盘价上穿 5 日均线时卖出。',
        min_bars=201, check=_rsi2),
    Strategy(
        'bollinger_squeeze', '布林带挤压突破', 'buy',
        '近 5 日内布林带宽度创 6 个月（125 日）新低，当日收盘突破布林上轨。',
        'John Bollinger,《Bollinger on Bollinger Bands》(2001) The Squeeze 与 Method I',
        plain='股价波动收窄到半年来最低后向上突破，即“久盘必动”中向上的一种。',
        tips='布林格建议用成交量等其他指标确认方向，假突破较常见。',
        min_bars=146, check=_bollinger_squeeze),
    Strategy(
        'oversold', '指标共振超卖', 'buy',
        'RSI(14)<30、KDJ 的 K 与 D 均<20、CCI(14)<-100、WR(14)>80 同时成立。',
        'J. Welles Wilder《New Concepts in Technical Trading Systems》(1978) RSI；George Lane 随机指标；'
        'Donald Lambert (1980) CCI；Larry Williams %R',
        plain='多个摆动指标同时显示超卖，说明短期跌得过急，可能出现反弹；但下跌趋势中股价可以持续超卖。',
        tips='更适合在震荡市或长期上升趋势中使用，不宜在单边下跌中逆势抄底。',
        min_bars=100, check=_oversold),
    Strategy(
        'graham', '格雷厄姆防御型', 'buy',
        '营业总收入≥50 亿；流动比率≥2；市盈率(TTM) 0~15；市盈率×市净率≤22.5；有股息；归母净利润为正且近 3 年复合增长为正。',
        'Benjamin Graham,《The Intelligent Investor》(1973 修订版) 第 14 章 防御型投资者选股标准',
        plain='格雷厄姆给普通投资者的保守选股标准：公司规模大、财务稳健、估值便宜、持续盈利并分红。',
        tips='原书还要求连续 20 年分红、10 年利润增长三分之一以上等，本系统按可得数据近似；结果每天变化很小，适合长期持有。',
        screen=_graham),
    Strategy(
        'turtle_exit', '海龟离场', 'sell',
        '收盘价跌破此前 20 个交易日的最低价（首次跌破当日触发），即海龟系统二的离场规则。',
        'Curtis Faith,《Way of the Turtle》(2007)；唐奇安通道（Richard Donchian）',
        plain='股价跌破近 20 个交易日（约一个月）的最低点，说明上涨趋势可能已经结束，趋势跟踪者在此离场。',
        tips='与买入策略“海龟交易法则”配对使用；离场后股价重新走强很常见，这是趋势跟踪为避免大幅回撤付出的代价。',
        min_bars=22, check=_turtle_exit),
    Strategy(
        'chandelier_exit', '吊灯止损', 'sell',
        '收盘价首次跌破“近 22 日最高价 − 3 × 22 日平均真实波幅(ATR)”。',
        'Chuck LeBeau 提出；Alexander Elder,《Come Into My Trading Room》(2002) Chandelier Exit',
        plain='以近期最高价为吊点，向下留出 3 倍日均波动作为止损线；股价跌破说明回撤已超出正常波动。止损线随股价创新高而上移。',
        tips='倍数越大越宽松、持有越久，原作者建议 3 倍；适合用来保护已有浮盈。',
        min_bars=23, check=_chandelier_exit),
    Strategy(
        'ma50_break', '放量跌破 50 日线', 'sell',
        '收盘价由上向下跌破 50 日均线，且成交量不低于 50 日均量的 1.5 倍。',
        "William O'Neil,《How to Make Money in Stocks》(第 4 版, 2009) 卖出规则：放量跌破 50 日均线",
        plain='机构投资者常把 50 日均线视为中期趋势的生命线，放量跌破往往意味着大资金正在卖出。',
        tips='欧奈尔同时强调：任何股票跌破买入价 7%~8% 都应无条件止损，不要等待技术信号。',
        min_bars=51, check=_ma50_break),
    Strategy(
        'granville_sell', '葛兰碧均线卖点', 'sell',
        '200 日均线此前上行、近 20 日走平或下行，收盘价由上向下跌破 200 日均线。',
        'Joseph Granville,《A Strategy of Daily Stock Market Timing for Maximum Profit》(1960) 移动平均线八大法则之卖点一',
        plain='长期均线由升转平，股价又跌破这条均线，说明长期趋势可能由上升转为下降。',
        tips='跌破后若几天内迅速收复均线，可能是假跌破；与买入策略“葛兰碧均线回踩”互为对应。',
        min_bars=261, check=_granville_sell),
    Strategy(
        'overbought', '指标共振超买', 'sell',
        'RSI(14)>70、KDJ 的 K 与 D 均>80、CCI(14)>100、WR(14)<20 同时成立。',
        '同“指标共振超卖”',
        plain='多个指标同时显示超买，说明短期涨得过急，回调风险加大；但强势股可能长时间处于超买。',
        tips='适合作为已持有股票的止盈、减仓提醒，不宜单独用来判断见顶。',
        min_bars=100, check=_overbought),
)

BY_KEY = {s.key: s for s in STRATEGIES}
TECHNICAL = tuple(s for s in STRATEGIES if s.check)
FUNDAMENTAL = tuple(s for s in STRATEGIES if s.screen)
