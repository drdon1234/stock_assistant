"""同花顺：涨停原因及详细解读。"""
import html
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from instock import net

_LIST = 'http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/'
_DETAIL = 'http://zx.10jqka.com.cn/event/harden/stockreason/id/{id}'
_FIELDS = {'code': 'code', 'name': 'name', 'reason': 'title', 'close': 'new_price', 'zhangfu': 'change_rate',
           'zhangdie': 'ups_downs', 'huanshou': 'turnoverrate', 'chengjiaoliang': 'volume',
           'chengjiaoe': 'deal_amount', 'ddejingliang': 'dde'}


def _detail(item_id):
    match = re.search(r"var data = '(.*?)';", net.get('ths', _DETAIL.format(id=item_id)).text)
    if not match:
        return ''
    text = html.unescape(html.unescape(match.group(1)))
    return re.sub(r'<[^>]+>', '', text).strip()


def limitup_reasons(day):
    rows = net.get_json('ths', _LIST.format(date=day.isoformat())).get('data') or []
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=list(_FIELDS.values()) + ['reason'])
    with ThreadPoolExecutor(3) as pool:
        details = list(pool.map(_detail, df['id']))
    df = df.reindex(columns=list(_FIELDS)).rename(columns=_FIELDS)
    df['reason'] = details
    return df
