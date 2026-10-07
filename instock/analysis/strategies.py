"""选股策略。每个策略都给出规则与出处，规则尽量忠实于原始文献，参数取文献给出的数值。

技术面策略 check(b, i) 判断第 i 根 K 线收盘后是否满足条件（只使用 i 及之前的数据）；
基本面策略对当日综合选股数据做横截面筛选。
kind：buy 买入信号，sell 卖出/风险信号。
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
        min_bars=56, check=_turtle),
    Strategy(
        'trend_template', '趋势模板', 'buy',
        '股价在 150/200 日均线上方；150 日线在 200 日线上方；200 日线至少上行 1 个月；50 日线在 150、200 日线上方；'
        '股价在 50 日线上方；股价较 52 周低点至少高 30%、距 52 周高点不超过 25%；相对强度排名不低于 70。',
        'Mark Minervini,《Trade Like a Stock Market Wizard》(2013) 第 5 章 Trend Template',
        min_bars=260, check=_trend_template, min_rs=70),
    Strategy(
        'granville', '葛兰碧均线回踩', 'buy',
        '200 日均线上行；此前股价明显高于均线（≥8%），近 10 日回落至距均线 3% 以内但收盘未跌破，当日收阳且上涨。',
        'Joseph Granville,《A Strategy of Daily Stock Market Timing for Maximum Profit》(1960) 移动平均线八大法则之买点三',
        min_bars=230, check=_granville),
    Strategy(
        'flat_base_breakout', '平台放量突破', 'buy',
        '前期上涨至少 20% 后形成 5 周（25 个交易日）平台，平台回撤不超过 15%；当日收盘突破平台最高价，'
        '成交量不低于 50 日均量的 1.5 倍。',
        "William O'Neil,《How to Make Money in Stocks》(第 4 版, 2009) 平底形态（Flat Base）与突破放量规则",
        min_bars=86, check=_flat_base_breakout),
    Strategy(
        'high_tight_flag', '高而窄的旗形', 'buy',
        '约 2 个月（40 个交易日）内上涨至少 90% 形成旗杆，随后 3~20 日旗面整理回撤不超过 25%，当日收盘突破旗面顶部。',
        'Thomas Bulkowski,《Encyclopedia of Chart Patterns》(第 2 版, 2005) High and Tight Flags',
        min_bars=61, check=_high_tight_flag),
    Strategy(
        'id_nr4', '内包窄幅（ID/NR4）', 'buy',
        '当日为内包线（最高价低于前日、最低价高于前日），且振幅为近 4 日最窄，预示波动即将放大。',
        'Linda Raschke & Laurence Connors,《Street Smarts》(1995) ID/NR4；Toby Crabel 窄幅区间研究',
        min_bars=5, check=_id_nr4),
    Strategy(
        'rsi2', 'RSI(2) 超跌回归', 'buy',
        '收盘价在 200 日均线上方（长期上升趋势），且 2 日 RSI 低于 10。',
        'Larry Connors & Cesar Alvarez,《Short Term Trading Strategies That Work》(2008)',
        min_bars=201, check=_rsi2),
    Strategy(
        'bollinger_squeeze', '布林带挤压突破', 'buy',
        '近 5 日内布林带宽度创 6 个月（125 日）新低，当日收盘突破布林上轨。',
        'John Bollinger,《Bollinger on Bollinger Bands》(2001) The Squeeze 与 Method I',
        min_bars=146, check=_bollinger_squeeze),
    Strategy(
        'oversold', '指标共振超卖', 'buy',
        'RSI(14)<30、KDJ 的 K 与 D 均<20、CCI(14)<-100、WR(14)>80 同时成立。',
        'J. Welles Wilder《New Concepts in Technical Trading Systems》(1978) RSI；George Lane 随机指标；'
        'Donald Lambert (1980) CCI；Larry Williams %R',
        min_bars=100, check=_oversold),
    Strategy(
        'overbought', '指标共振超买', 'sell',
        'RSI(14)>70、KDJ 的 K 与 D 均>80、CCI(14)>100、WR(14)<20 同时成立。',
        '同“指标共振超卖”',
        min_bars=100, check=_overbought),
    Strategy(
        'graham', '格雷厄姆防御型', 'buy',
        '营业总收入≥50 亿；流动比率≥2；市盈率(TTM) 0~15；市盈率×市净率≤22.5；有股息；归母净利润为正且近 3 年复合增长为正。',
        'Benjamin Graham,《The Intelligent Investor》(1973 修订版) 第 14 章 防御型投资者选股标准',
        screen=_graham),
)

BY_KEY = {s.key: s for s in STRATEGIES}
TECHNICAL = tuple(s for s in STRATEGIES if s.check)
FUNDAMENTAL = tuple(s for s in STRATEGIES if s.screen)
