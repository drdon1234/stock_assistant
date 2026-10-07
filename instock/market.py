"""行情与事件数据服务：组合数据源、主备切换和过滤，输出可直接入库的 DataFrame（列名同 schema）。

数据源选择原则：替代源能提供同等信息的用更稳定的源（行情、ETF、K 线用腾讯/新浪，不再请求东方财富 push2 行情列表
和 push2his K 线这两个极易封 IP 的接口）；东方财富独有的信息（分单资金流向、龙虎榜/大宗交易/分红明细、选股器）
仍用东方财富，资金流向在其不可用时降级为新浪/选股器数据。
"""
import datetime
import logging
import threading
import time

import numpy as np
import pandas as pd

from instock import db, net, schema, tradecal
from instock.sources import eastmoney as em
from instock.sources import sina, tdx, tencent, ths

log = logging.getLogger(__name__)

# 沪深主板 + 创业板，与综合选股范围一致（不含科创板、北交所、B 股）
_A_SHARE_PREFIX = ('600', '601', '603', '605', '000', '001', '002', '003', '300', '301')


def is_a_share(code):
    return str(code).startswith(_A_SHARE_PREFIX)


def _a_shares(df):
    return df[df['code'].astype(str).map(is_a_share)]


def _with_date(df, day):
    df = df.copy()
    df.insert(0, 'date', day)
    return df


_selection_cache = {'at': 0.0, 'df': None}
_selection_lock = threading.Lock()


def selection():
    """综合选股（选股器全量字段）。10 分钟内复用，供综合选股入库和备用行情共用。"""
    with _selection_lock:
        if _selection_cache['df'] is None or time.monotonic() - _selection_cache['at'] > 600:
            cols = schema.SELECTION.cols
            raw = em.xuangu([col.src for col in cols])
            df = raw.reindex(columns=[col.src for col in cols])
            df.columns = [col.name for col in cols]
            for col in cols:
                if col.fmt not in ('text', 'code', 'date', 'bool'):
                    df[col.name] = pd.to_numeric(df[col.name], errors='coerce')
            _selection_cache.update(at=time.monotonic(), df=df.drop_duplicates('code', keep='last'))
        return _selection_cache['df'].copy()


# 腾讯行情没有的基本面字段，从综合选股补充：每日股票数据列 -> 综合选股列
_SPOT_FROM_SELECTION = {
    'basic_eps': 'basic_eps', 'bvps': 'bvps', 'per_capital_reserve': 'per_capital_reserve',
    'per_unassign_profit': 'per_unassign_profit', 'roe_weight': 'roe_weight', 'sale_gpr': 'sale_gpr',
    'debt_asset_ratio': 'debt_asset_ratio', 'total_operate_income': 'total_operate_income',
    'toi_yoy_ratio': 'toi_yoy_ratio', 'parent_netprofit': 'parent_netprofit',
    'netprofit_yoy_ratio': 'netprofit_yoy_ratio', 'industry': 'industry', 'listing_date': 'listing_date',
}


_codes_cache = {}


def stock_codes():
    """沪深 A 股代码列表（新浪，含停牌股），每天只取一次；新浪不可用时用库中最近的列表。"""
    today = tradecal.now().date()
    if today not in _codes_cache:
        try:
            codes = [c for c in sina.node_codes('hs_a') if is_a_share(c)]
        except net.FetchError as e:
            codes = []
            log.warning('新浪股票列表不可用（%s），沿用库中最近一次的股票列表', e)
        if not codes:
            codes = db.read(f'SELECT code FROM {schema.STOCK_SPOT.name} WHERE date = '
                            f'(SELECT MAX(date) FROM {schema.STOCK_SPOT.name})')['code'].tolist()
            if not codes:
                raise net.FetchError('无法获取股票列表')
            return codes
        _codes_cache.clear()
        _codes_cache[today] = codes
    return _codes_cache[today]


def _fundamentals():
    """基本面列：优先用库中最近一次综合选股（盘中刷新不再请求东方财富），没有时实时抓取。"""
    cols = ', '.join(['code', *dict.fromkeys(_SPOT_FROM_SELECTION.values())])
    df = db.read(f'SELECT {cols} FROM {schema.SELECTION.name} WHERE date = '
                 f'(SELECT MAX(date) FROM {schema.SELECTION.name})')
    if df.empty:
        df = selection()[['code', *_SPOT_FROM_SELECTION.values()]]
    df = df.drop_duplicates('code')
    out = pd.DataFrame({'code': df['code']})
    for spot_col, sel_col in _SPOT_FROM_SELECTION.items():
        out[spot_col] = df[sel_col].to_numpy()
    return out


def stock_spot(day):
    """沪深 A 股行情（成交量：手）：新浪股票列表 + 腾讯批量报价 + 综合选股基本面。
    基本面不可用时只缺这些列，行情本身不受影响。"""
    df = tencent.quotes(stock_codes()).drop(columns='quote_date', errors='ignore')
    try:
        df = df.merge(_fundamentals(), on='code', how='left')
    except net.FetchError as e:
        log.warning('选股器不可用（%s），本次行情不含基本面', e)
    df = _with_date(_a_shares(df[df['new_price'].notna()]), day)
    df.attrs['fetched_at'] = tradecal.now()
    return df


def etf_spot(day):
    """ETF 行情：新浪 ETF 列表 + 腾讯批量报价。"""
    df = tencent.quotes(sina.node_codes('etf_hq_fund'))
    df = df.reindex(columns=[c.name for c in schema.ETF_SPOT.cols if c.name != 'date'])
    return _with_date(df[df['new_price'].notna()], day)


def _merge_periods(frames, key, drop=()):
    df = frames[0]
    for frame in frames[1:]:
        df = df.merge(frame.drop(columns=list(drop)), on=key, how='left')
    return df


def stock_fund_flow(day):
    try:
        df = _merge_periods([em.stock_fund_flow(p) for p in em.STOCK_FLOW_PERIODS], 'code', ('name', 'new_price'))
    except net.FetchError as e:
        log.warning('东方财富资金流向不可用（%s），改用选股器的主力净流入（无分单数据）', e)
        sel = selection()
        df = pd.DataFrame({
            'code': sel['code'], 'name': sel['name'], 'new_price': sel['new_price'],
            'change_rate': sel['change_rate'], 'fund_amount': sel['net_inflow'],
            'fund_rate': sel['net_inflow'] / sel['deal_amount'].replace(0, np.nan) * 100,
            'change_rate_3': sel['changerate_3days'], 'fund_amount_3': sel['netinflow_3days'],
            'change_rate_5': sel['changerate_5days'], 'fund_amount_5': sel['netinflow_5days'],
            'change_rate_10': sel['changerate_10days'],
        })
    df['new_price'] = pd.to_numeric(df['new_price'], errors='coerce')
    return _with_date(_a_shares(df[df['new_price'].notna()]), day)


def sector_fund_flow(day, concept):
    try:
        df = _merge_periods([em.sector_fund_flow(p, concept) for p in em.SECTOR_FLOW_PERIODS], 'name')
    except net.FetchError as e:
        log.warning('东方财富板块资金流不可用（%s），改用新浪（仅当日主力净流入）', e)
        df = sina.sector_fund_flow(concept)
    return _with_date(df, day)


def bonus_report_date(day):
    """当前最可能在实施分红的报告期：上半年看上年年报，下半年看当年中报。"""
    y, m = day.year, day.month
    if 2 <= m <= 6 or (m == 7 and day.day <= 25):
        return datetime.date(y - 1, 12, 31)
    if m >= 7:
        return datetime.date(y, 6, 30)
    return datetime.date(y - 1, 12, 31) if day.day > 25 else datetime.date(y - 1, 6, 30)


def bonus(day):
    return _with_date(_a_shares(em.bonus(bonus_report_date(day))), day)


def lhb(day):
    return _with_date(_a_shares(em.lhb(day)), day)


def blocktrade(day):
    df = _a_shares(em.blocktrade(day))
    # 接口单位为万股、万元，统一为股、元
    df['sum_volume'] = pd.to_numeric(df['sum_volume'], errors='coerce') * 1e4
    df['sum_turnover'] = pd.to_numeric(df['sum_turnover'], errors='coerce') * 1e4
    return _with_date(df, day)


def chip_race(day, closing):
    return _with_date(tdx.chip_race(day, closing), day)


def limitup_reasons(day):
    df = ths.limitup_reasons(day)
    df['deal_amount'] = pd.to_numeric(df['deal_amount'], errors='coerce') * 1e4  # 万元 -> 元
    return _with_date(df, day)
