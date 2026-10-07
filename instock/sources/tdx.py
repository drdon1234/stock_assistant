"""通达信：竞价抢筹（早盘/尾盘）。"""
import datetime

import pandas as pd

from instock import net

_URL = 'http://excalc.icfqs.com:7616/TQLEX?Entry=HQServ.hq_nlp'
_TOKEN = '6679f5cadca97d68245a086793fc1bfc0a50b487487c812f'
_COLUMNS = ['code', 'name', 'pre_close_price', 'open_price', 'deal_amount', 'bid_rate', 'bid_trust_amount',
            'bid_deal_amount', 'new_price', '_', 'limitup_day', 'limitup_board']


def chip_race(day, closing):
    """closing=False 早盘抢筹，True 尾盘抢筹；按抢筹委托金额排序取前 100。"""
    query = {'funcId': 20, 'offset': 0, 'count': 100, 'sort': 1, 'period': int(closing), 'Token': _TOKEN,
             'modname': 'JJQC'}
    if day != datetime.date.today():  # 当天数据不带日期参数
        query['date'] = day.strftime('%Y%m%d')
    rows = net.post_json('tdx', _URL, json=[query]).get('datas') or []
    df = pd.DataFrame(rows, columns=_COLUMNS)
    if df.empty:
        return df
    df['pre_close_price'] = df['pre_close_price'] / 10000
    df['open_price'] = df['open_price'] / 10000
    df['bid_rate'] = (df['bid_rate'] * 100).round(2)
    df['new_price'] = df['new_price'].round(2)
    df['change_rate'] = ((df['new_price'] / df['pre_close_price'] - 1) * 100).round(2)
    df['bid_ratio'] = (df['bid_deal_amount'] / df['deal_amount'] * 100).round(2)
    return df.drop(columns='_')
