"""腾讯行情：批量实时报价、前复权日 K 线。限流宽松，是股票/ETF 行情和历史 K 线的数据源。"""
import datetime

import numpy as np
import pandas as pd

from instock import net

_QUOTE = 'https://qt.gtimg.cn/q='
_KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/newfqkline/get'
MAX_BARS = 800  # 接口单次最多返回的 K 线根数（请求更多反而返回更少）
_BATCH = 60  # 单次查询上限约 70 只


def symbol(code):
    return f"{'sh' if code.startswith(('5', '6', '9')) else 'sz'}{code}"


def _num(value, scale=1.0):
    try:
        return float(value) * scale
    except (TypeError, ValueError):
        return np.nan


def _parse_quote(f):
    price = _num(f[3])
    volume, amount = np.nan, np.nan
    parts = f[35].split('/')
    if len(parts) == 3:  # 价格/成交量(手)/成交额(元)，比单独字段精度高
        volume, amount = _num(parts[1]), _num(parts[2])
    return {
        'code': f[2], 'name': f[1],
        'new_price': price if price > 0 else np.nan,  # 停牌时为 0
        'change_rate': _num(f[32]), 'ups_downs': _num(f[31]),
        'volume': volume, 'deal_amount': amount,
        'amplitude': _num(f[43]), 'turnoverrate': _num(f[38]), 'volume_ratio': _num(f[49]),
        'open_price': _num(f[5]), 'high_price': _num(f[33]), 'low_price': _num(f[34]), 'pre_close_price': _num(f[4]),
        'dtsyl': _num(f[52]), 'pe9': _num(f[39]), 'pe': _num(f[53]), 'pbnewmrq': _num(f[46]),
        'speed_increase_60': _num(f[71]), 'speed_increase_all': _num(f[62]),
        'free_shares': _num(f[72]), 'total_shares': _num(f[73]),
        'free_cap': _num(f[44], 1e8), 'total_market_cap': _num(f[45], 1e8),  # 亿元 -> 元
        'quote_date': f[30][:8],
    }


def quotes(codes):
    """批量实时报价，列名同入库列；quote_date 为行情日期(yyyymmdd)。"""
    codes = list(codes)
    rows = []
    for i in range(0, len(codes), _BATCH):
        text = net.get('tencent', _QUOTE + ','.join(symbol(c) for c in codes[i:i + _BATCH])).content.decode(
            'gbk', errors='ignore')
        for line in text.split(';'):
            if '="' not in line:
                continue
            fields = line.split('="', 1)[1].rstrip('"').split('~')
            if len(fields) >= 74:
                rows.append(_parse_quote(fields))
    return pd.DataFrame(rows)


def _kline_page(code, end):
    """截至 end 的最近 MAX_BARS 根前复权日 K 线（接口忽略起始日期，只按根数往前取）。"""
    param = f'{symbol(code)},day,,{end.isoformat()},{MAX_BARS},qfq'
    data = (net.get_json('tencent', _KLINE, {'param': param}).get('data') or {}).get(symbol(code)) or {}
    return [r for r in (data.get('qfqday') or data.get('day') or []) if len(r) >= 9]


def kline(code, start, end=None):
    """[start, end] 的前复权日 K 线，超过单次上限时向前分段获取。成交量：手，成交额：元，换手率：%。"""
    end = end or datetime.date.today()
    rows = []
    for _ in range(30):  # 30 段约 100 年，防止异常数据死循环
        page = _kline_page(code, end)
        rows = page + rows
        if len(page) < MAX_BARS or page[0][0] <= start.isoformat():
            break
        end = datetime.date.fromisoformat(page[0][0]) - datetime.timedelta(days=1)
    df = pd.DataFrame([[r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[8]] for r in rows if r[0] >= start.isoformat()],
                      columns=['date', 'open', 'close', 'high', 'low', 'volume', 'turnover', 'amount'])
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce') * 1e4  # 万元 -> 元
    return df
