"""BaoStock（证券宝）：不复权日 K 线（含停牌、ST 标记）、复权因子、证券列表（含已退市）、交易日历、指数成分。
免费、无需注册，是回测历史数据的数据源。

官方客户端的收包循环没有超时，服务器断开连接时会空转占满 CPU，这里替换为带超时、断线即报错的实现。
客户端用模块级全局连接，同一进程内不能并发查询；需要并行时开多个进程，每个进程各自登录。
"""
import contextlib
import io
import logging
import zlib

import pandas as pd

log = logging.getLogger(__name__)

_TIMEOUT = 60
_END = b'<![CDATA[]]>\n'
_logged_in = False

# 指数代码（聚宽格式）：回测基准与 get_index_stocks 常用的指数
INDEXES = {
    '000001.XSHG': '上证指数', '000016.XSHG': '上证50', '000300.XSHG': '沪深300', '000905.XSHG': '中证500',
    '000852.XSHG': '中证1000', '399001.XSHE': '深证成指', '399006.XSHE': '创业板指', '000688.XSHG': '科创50',
}
# 可查询历史成分的指数 -> BaoStock 查询函数名
INDEX_MEMBERS = {'000300.XSHG': 'query_hs300_stocks', '000016.XSHG': 'query_sz50_stocks',
                 '000905.XSHG': 'query_zz500_stocks'}
_DAILY_FIELDS = 'date,open,high,low,close,preclose,volume,amount,tradestatus,isST'


def to_jq(code):
    """sh.600000 -> 600000.XSHG"""
    market, num = code.split('.')
    return f"{num}.{'XSHG' if market == 'sh' else 'XSHE'}"


def to_bs(code):
    """600000.XSHG -> sh.600000"""
    num, market = code.split('.')
    return f"{'sh' if market == 'XSHG' else 'sz'}.{num}"


def is_a_share(bs_code):
    """沪深 A 股（含科创板），不含 B 股。"""
    return bs_code.startswith(('sh.60', 'sh.68', 'sz.00', 'sz.30'))


def _send_msg(msg):
    import baostock.common.contants as cons
    import baostock.common.context as context

    sock = getattr(context, 'default_socket', None)
    if sock is None:
        raise ConnectionError('BaoStock 未登录')
    sock.settimeout(_TIMEOUT)
    sock.sendall((msg + '\n').encode('utf-8'))
    buf = bytearray()
    while not buf.endswith(_END):
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError('BaoStock 服务器断开了连接')
        buf += chunk
    head = bytes(buf[:cons.MESSAGE_HEADER_LENGTH]).decode('utf-8')
    parts = head.split(cons.MESSAGE_SPLIT)
    if parts[1] in cons.COMPRESSED_MESSAGE_TYPE_TUPLE:
        size = int(parts[2])
        body = zlib.decompress(bytes(buf[cons.MESSAGE_HEADER_LENGTH:cons.MESSAGE_HEADER_LENGTH + size]))
        return head + body.decode('utf-8')
    return bytes(buf).decode('utf-8')


def login():
    """登录（进程内只需一次）。官方客户端会向标准输出打印提示，这里屏蔽掉。"""
    global _logged_in
    import baostock as bs
    import baostock.util.socketutil as socketutil

    socketutil.send_msg = _send_msg
    with contextlib.redirect_stdout(io.StringIO()):
        result = bs.login()
    if result.error_code != '0':
        raise ConnectionError(f'BaoStock 登录失败：{result.error_msg}')
    _logged_in = True


def relogin():
    global _logged_in
    import baostock as bs
    with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()):
        bs.logout()
    _logged_in = False
    login()


def _query(name, *args, **kwargs):
    import baostock as bs
    if not _logged_in:
        login()
    with contextlib.redirect_stdout(io.StringIO()):
        rs = getattr(bs, name)(*args, **kwargs)
        rows = []
        while rs.error_code == '0' and rs.next():
            rows.append(rs.get_row_data())
    if rs.error_code != '0':
        raise RuntimeError(f'BaoStock {name} 失败：{rs.error_code} {rs.error_msg}')
    return pd.DataFrame(rows, columns=rs.fields)


def query(name, *args, retries=3, **kwargs):
    """带重连重试的查询。"""
    for attempt in range(retries):
        try:
            return _query(name, *args, **kwargs)
        except (ConnectionError, OSError, RuntimeError) as e:
            if attempt == retries - 1:
                raise
            log.warning('BaoStock %s 失败，重新登录后重试：%s', name, e)
            relogin()


def securities():
    """沪深 A 股（含已退市）与常用指数。列：code(聚宽格式) display_name start_date end_date type。"""
    df = query('query_stock_basic')
    stocks = df[(df['type'] == '1') & df['code'].map(is_a_share)]
    indexes = df[(df['type'] == '2') & df['code'].map(to_jq).isin(INDEXES)]
    out = pd.concat([stocks.assign(type='stock'), indexes.assign(type='index')], ignore_index=True)
    return pd.DataFrame({
        'code': out['code'].map(to_jq),
        'display_name': out['code_name'],
        'start_date': pd.to_datetime(out['ipoDate'], errors='coerce'),
        'end_date': pd.to_datetime(out['outDate'].replace('', None), errors='coerce'),
        'type': out['type'],
    })


def daily(code, start, end):
    """不复权日 K 线。停牌日也有一行（开高低收为昨收、量为 0）。量：股，额：元。"""
    df = query('query_history_k_data_plus', to_bs(code), _DAILY_FIELDS, start_date=start.isoformat(),
               end_date=end.isoformat(), frequency='d', adjustflag='3')
    if df.empty:
        return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'pre_close', 'volume', 'money',
                                     'paused', 'is_st'])
    num = {c: pd.to_numeric(df[c], errors='coerce') for c in ('open', 'high', 'low', 'close', 'preclose',
                                                              'volume', 'amount')}
    return pd.DataFrame({
        'date': pd.to_datetime(df['date']),
        'open': num['open'], 'high': num['high'], 'low': num['low'], 'close': num['close'],
        'pre_close': num['preclose'], 'volume': num['volume'], 'money': num['amount'],
        'paused': (df['tradestatus'] == '0').astype('int8'),
        'is_st': (df['isST'] == '1').astype('int8'),
    })


def adjust_factors(code):
    """除权除息日及其后复权因子（上市时为 1）。"""
    df = query('query_adjust_factor', to_bs(code), start_date='1990-01-01', end_date='2099-12-31')
    return pd.DataFrame({'date': pd.to_datetime(df['dividOperateDate']),
                         'factor': pd.to_numeric(df['backAdjustFactor'], errors='coerce')}).dropna()


def trade_days(start, end):
    df = query('query_trade_dates', start_date=start.isoformat(), end_date=end.isoformat())
    return pd.to_datetime(df.loc[df['is_trading_day'] == '1', 'calendar_date']).dt.date.tolist()


def index_members(index, day):
    """指数在 day 的成分股（聚宽格式代码，已排序）。"""
    df = query(INDEX_MEMBERS[index], date=day.isoformat())
    return sorted(df['code'].map(to_jq)) if not df.empty else []
