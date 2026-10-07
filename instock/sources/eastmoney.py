"""东方财富：资金流向(push2 列表)、数据中心(龙虎榜/大宗交易/分红)、选股器(xuangu)。这些信息没有同等的替代源。"""
import math
import random
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from instock import net

_DATACENTER = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
_XUANGU = 'https://data.eastmoney.com/dataapi/xuangu/list'

def _flow_fields(change, first, suffix):
    """资金流向字段：涨跌幅 + 主力/超大单/大单/中单/小单 的净额、净占比，字段号连续排列。"""
    names = ['fund_amount', 'fund_rate', 'fund_amount_super', 'fund_rate_super', 'fund_amount_large',
             'fund_rate_large', 'fund_amount_medium', 'fund_rate_medium', 'fund_amount_small', 'fund_rate_small']
    fields = {change: f'change_rate{suffix}'}
    fields.update({f'f{first + i}': f'{name}{suffix}' for i, name in enumerate(names)})
    return fields


# 个股/板块资金流向：周期 -> (排序字段, stat 参数, 字段映射)
_TODAY_FLOW = {'f3': 'change_rate', 'f62': 'fund_amount', 'f184': 'fund_rate', 'f66': 'fund_amount_super',
               'f69': 'fund_rate_super', 'f72': 'fund_amount_large', 'f75': 'fund_rate_large',
               'f78': 'fund_amount_medium', 'f81': 'fund_rate_medium', 'f84': 'fund_amount_small',
               'f87': 'fund_rate_small'}
STOCK_FLOW_PERIODS = {
    '今日': ('f62', _TODAY_FLOW),
    '3日': ('f267', _flow_fields('f127', 267, '_3')),
    '5日': ('f164', _flow_fields('f109', 164, '_5')),
    '10日': ('f174', _flow_fields('f160', 174, '_10')),
}
SECTOR_FLOW_PERIODS = {
    '今日': ('f62', '1', dict(_TODAY_FLOW, f204='stock_name')),
    '5日': ('f164', '5', dict(_flow_fields('f109', 164, '_5'), f257='stock_name_5')),
    '10日': ('f174', '10', dict(_flow_fields('f160', 174, '_10'), f260='stock_name_10')),
}


def _clist_url():
    # 与网页一致使用随机编号子域名，分散请求
    return f'https://{random.randint(1, 99)}.push2.eastmoney.com/api/qt/clist/get'


def _clist(params, fields):
    """分页拉取 push2 列表：先取首页得到总数，其余页在限流约束下并发获取。任一页失败即整体失败。"""
    params = dict(params, pn=1, pz=100, po=1, np=1, fltt=2, invt=2, fields=','.join(fields))
    data = net.get_json('em_quote', _clist_url(), params).get('data') or {}
    rows = list(data.get('diff') or [])
    if not rows:
        return pd.DataFrame(columns=list(fields.values()))
    pages = math.ceil((data.get('total') or 0) / len(rows))

    def page(pn):
        return (net.get_json('em_quote', _clist_url(), dict(params, pn=pn)).get('data') or {}).get('diff') or []

    with ThreadPoolExecutor(2) as pool:
        for page_rows in pool.map(page, range(2, pages + 1)):
            rows.extend(page_rows)
    df = pd.DataFrame.from_records(rows)
    return df[[f for f in fields if f in df.columns]].rename(columns=fields)


def stock_fund_flow(period):
    fid, fields = STOCK_FLOW_PERIODS[period]
    fields = dict({'f12': 'code', 'f14': 'name', 'f2': 'new_price'}, **fields)
    return _clist({'fid': fid, 'ut': 'b2884a393a59ad64002292a3e90d46a5',
                   'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,'
                         'm:0+t:7+f:!2,m:1+t:3+f:!2'}, fields)


def sector_fund_flow(period, concept):
    """行业(concept=False)或概念板块资金流向。"""
    fid, stat, fields = SECTOR_FLOW_PERIODS[period]
    fields = dict({'f14': 'name'}, **fields)
    return _clist({'fid': fid, 'stat': stat, 'ut': 'b2884a393a59ad64002292a3e90d46a5',
                   'fs': f"m:90 t:{3 if concept else 2}"}, fields)


def _datacenter(report, columns, filter_, sort_columns, sort_types='-1', page_size=500):
    params = {'reportName': report, 'columns': columns, 'filter': filter_, 'sortColumns': sort_columns,
              'sortTypes': sort_types, 'pageSize': page_size, 'pageNumber': 1, 'source': 'WEB', 'client': 'WEB'}
    result = net.get_json('em_data', _DATACENTER, params).get('result') or {}
    rows = list(result.get('data') or [])
    for page in range(2, (result.get('pages') or 1) + 1):
        rows.extend((net.get_json('em_data', _DATACENTER, dict(params, pageNumber=page)).get('result') or {})
                    .get('data') or [])
    return pd.DataFrame.from_records(rows)


def _pick(df, fields):
    if df.empty:
        return pd.DataFrame(columns=list(fields.values()))
    return df[list(fields)].rename(columns=fields)


LHB_FIELDS = {
    'SECURITY_CODE': 'code', 'SECURITY_NAME_ABBR': 'name', 'EXPLAIN': 'interpret', 'CLOSE_PRICE': 'new_price',
    'CHANGE_RATE': 'change_rate', 'BILLBOARD_NET_AMT': 'net_amount_buy', 'BILLBOARD_BUY_AMT': 'sum_buy',
    'BILLBOARD_SELL_AMT': 'sum_sell', 'BILLBOARD_DEAL_AMT': 'lhb_amount', 'ACCUM_AMOUNT': 'market_amount',
    'DEAL_NET_RATIO': 'net_amount_rate', 'DEAL_AMOUNT_RATIO': 'sum_rate', 'TURNOVERRATE': 'turnoverrate',
    'FREE_MARKET_CAP': 'free_cap', 'EXPLANATION': 'reason', 'D1_CLOSE_ADJCHRATE': 'ranking_after_1',
    'D2_CLOSE_ADJCHRATE': 'ranking_after_2', 'D5_CLOSE_ADJCHRATE': 'ranking_after_5',
    'D10_CLOSE_ADJCHRATE': 'ranking_after_10',
}


def lhb(day):
    """龙虎榜：同一股票当日因多个原因上榜时合并原因为一行。"""
    d = day.isoformat()
    df = _pick(_datacenter('RPT_DAILYBILLBOARD_DETAILSNEW', ','.join(LHB_FIELDS),
                           f"(TRADE_DATE<='{d}')(TRADE_DATE>='{d}')", 'SECURITY_CODE'), LHB_FIELDS)
    if df.empty:
        return df
    reasons = df.groupby('code')['reason'].agg(lambda s: '；'.join(dict.fromkeys(s.dropna().astype(str))))
    df = df.drop_duplicates('code').set_index('code')
    df['reason'] = reasons
    return df.reset_index()


BLOCKTRADE_FIELDS = {
    'SECURITY_CODE': 'code', 'SECURITY_NAME_ABBR': 'name', 'CLOSE_PRICE': 'new_price', 'CHANGE_RATE': 'change_rate',
    'AVERAGE_PRICE': 'average_price', 'PREMIUM_RATIO': 'overflow_rate', 'DEAL_NUM': 'trade_number',
    'VOLUME': 'sum_volume', 'DEAL_AMT': 'sum_turnover', 'TURNOVERRATE': 'turnover_market_rate',
}


def blocktrade(day):
    """大宗交易每日统计（成交总量：万股，成交总额：万元）。"""
    d = day.isoformat()
    return _pick(_datacenter('RPT_BLOCKTRADE_STA', ','.join(BLOCKTRADE_FIELDS),
                             f"(TRADE_DATE>='{d}')(TRADE_DATE<='{d}')", 'TURNOVERRATE'), BLOCKTRADE_FIELDS)


BONUS_FIELDS = {
    'SECURITY_CODE': 'code', 'SECURITY_NAME_ABBR': 'name', 'IMPL_PLAN_PROFILE': 'plan_profile',
    'BONUS_IT_RATIO': 'convertible_total_rate', 'BONUS_RATIO': 'convertible_rate',
    'IT_RATIO': 'convertible_transfer_rate', 'PRETAX_BONUS_RMB': 'bonusaward_rate',
    'DIVIDENT_RATIO': 'bonusaward_yield', 'BASIC_EPS': 'basic_eps', 'BVPS': 'bvps',
    'PER_CAPITAL_RESERVE': 'per_capital_reserve', 'PER_UNASSIGN_PROFIT': 'per_unassign_profit',
    'PNP_YOY_RATIO': 'netprofit_yoy_ratio', 'TOTAL_SHARES': 'total_shares', 'PLAN_NOTICE_DATE': 'plan_date',
    'EQUITY_RECORD_DATE': 'record_date', 'EX_DIVIDEND_DATE': 'ex_dividend_date', 'ASSIGN_PROGRESS': 'progress',
    'NOTICE_DATE': 'report_date',
}


def bonus(report_date):
    """分红送配（report_date 为报告期，如 2025-12-31）。"""
    df = _pick(_datacenter('RPT_SHAREBONUS_DET', ','.join(BONUS_FIELDS),
                           f"(REPORT_DATE='{report_date.isoformat()}')", 'PLAN_NOTICE_DATE'), BONUS_FIELDS)
    # 接口给的股息率是小数，统一为百分比
    df['bonusaward_yield'] = pd.to_numeric(df['bonusaward_yield'], errors='coerce') * 100
    return df


def xuangu(fields, page_size=1000):
    """选股器全量数据（沪深主板+创业板），fields 为接口字段名列表，返回原字段名。"""
    params = {'sty': ','.join(fields), 'p': 1, 'ps': page_size, 'source': 'SELECT_SECURITIES', 'client': 'WEB',
              'filter': '(MARKET+in+("上交所主板","深交所主板","深交所创业板"))(NEW_PRICE>0)'}
    result = net.get_json('em_data', _XUANGU, params).get('result') or {}
    rows = list(result.get('data') or [])
    for page in range(2, math.ceil((result.get('count') or 0) / page_size) + 1):
        rows.extend((net.get_json('em_data', _XUANGU, dict(params, p=page)).get('result') or {}).get('data') or [])
    df = pd.DataFrame.from_records(rows)
    for col in ('CONCEPT', 'STYLE'):
        if col in df.columns:
            df[col] = df[col].map(lambda v: ', '.join(v) if isinstance(v, list) else v)
    return df
