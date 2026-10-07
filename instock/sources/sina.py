"""新浪财经：交易日历、行情节点列表、板块资金流向（备用）。"""
import datetime
from pathlib import Path

import pandas as pd

from instock import net

_CALENDAR = 'https://finance.sina.com.cn/realstock/company/klc_td_sh.txt'
_API = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'


def trade_dates():
    """上交所交易日历（含当年已公布的未来交易日）。数据经混淆，需执行新浪的 JS 解码。"""
    from py_mini_racer import MiniRacer

    text = net.get('sina', _CALENDAR).text
    ctx = MiniRacer()
    ctx.eval((Path(__file__).with_name('sina_calendar.js')).read_text(encoding='utf-8'))
    dates = {datetime.date.fromisoformat(str(d)[:10]) for d in ctx.call('d', text.split('=')[1].split(';')[0].strip('"'))}
    dates.add(datetime.date(1992, 5, 4))  # 新浪日历缺失的交易日
    return sorted(dates)


def node_codes(node):
    """行情中心节点的代码列表：hs_a 沪深A股，etf_hq_fund ETF。"""
    codes, page = [], 1
    while True:
        rows = net.get_json('sina', _API + 'Market_Center.getHQNodeData',
                            {'page': page, 'num': 100, 'sort': 'symbol', 'asc': 1, 'node': node}) or []
        codes.extend(str(r['code']) for r in rows)
        if len(rows) < 100:
            return codes
        page += 1


def sector_fund_flow(concept):
    """板块当日资金流向（申万行业/概念），只有主力净流入，无分单拆分。"""
    rows = net.get_json('sina', _API + 'MoneyFlow.ssl_bkzj_bk',
                        {'page': 1, 'num': 1000, 'sort': 'netamount', 'asc': 0, 'fenlei': int(concept)}) or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # 新浪板块偶有重名，名称是主键需去重
    df = df.drop_duplicates('name')
    return pd.DataFrame({
        'name': df['name'],
        'change_rate': pd.to_numeric(df['avg_changeratio'], errors='coerce') * 100,
        'fund_amount': pd.to_numeric(df['netamount'], errors='coerce'),
        'fund_rate': pd.to_numeric(df['ratioamount'], errors='coerce') * 100,
        'stock_name': df['ts_name'],
    })
