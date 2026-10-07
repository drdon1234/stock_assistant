"""分钟数据：通达信分时解析、时刻映射、盘中按分钟价撮合、分钟线（无未来数据、合成、复权）、分钟级回测与同步续传。"""
import numpy as np
import pytest

from instock.quant import child, minute, store
from instock.sources import tdxhq
from test_quant import DAYS, quant_data, run  # noqa: F401  复用日线测试数据

NO_MINUTE_DAY = 45


def _path(prev, close):
    """从开盘价线性走到收盘价的 240 个分钟收盘价。"""
    return prev + (close - prev) * np.arange(1, 241) / 240


@pytest.fixture(scope='module')
def minute_data(quant_data):  # noqa: F811
    """为 600000 生成分钟数据（停牌日与 NO_MINUTE_DAY 没有）。"""
    raw = store.read_raw('600000.XSHG')
    dates, prices, volumes = [], [], []
    for i, r in raw.iterrows():
        if r.paused or i == NO_MINUTE_DAY:
            continue
        dates.append(int(r.date.strftime('%Y%m%d')))
        prices.append(_path(r.open, r.close))
        volumes.append(np.full(240, 100))
    minute.save('600000.XSHG', 2022, dates, prices, volumes)
    state = store.load_state()
    state['minute'] = {'scope': 'index', 'start': DAYS[0].isoformat(), 'end': DAYS[-1].isoformat(), 'stocks': 1}
    store.save_state(state)
    return raw


def _encode(value):
    """通达信变长有符号整数编码（解析器的逆运算）。"""
    sign, value = (0x40 if value < 0 else 0), abs(value)
    out = [(value & 0x3f) | sign]
    value >>= 6
    while value:
        out[-1] |= 0x80
        out.append(value & 0x7f)
        value >>= 7
    return bytes(out)


def test_tdx_minute_parser():
    prices = [1234, 1240, 1199, 100000]
    body = len(prices).to_bytes(2, 'little') + b'\0' * 4
    last = 0
    for price, vol in zip(prices, (5, 300, 70000, 1)):
        body += _encode(price - last) + _encode(0) + _encode(vol)
        last = price
    p, v = tdxhq.parse_minutes(body)
    assert p.tolist() == [12.34, 12.40, 11.99, 1000.0] and v.tolist() == [5, 300, 70000, 1]


def test_point_index():
    assert minute.point_index(570) == -1 and minute.point_index(571) == 0
    assert minute.point_index(690) == 119 and minute.point_index(780) == 119  # 午休沿用 11:30
    assert minute.point_index(781) == 120 and minute.point_index(890) == 229 and minute.point_index(900) == 239


BUY_1450 = '''
def initialize(context):
    run_daily(buy, '14:50')

def buy(context):
    if not context.portfolio.positions:
        record(seen=get_current_data()['600000.XSHG'].last_price)
        order('600000.XSHG', 100)
'''


def test_intraday_fill_uses_minute_price(minute_data):
    raw = minute_data
    i = 2
    result = run(BUY_1450, start=DAYS[i], end=DAYS[i])
    expected = _path(raw.open[i], raw.close[i])[minute.point_index(14 * 60 + 50)]
    assert result['trades'][0][5] == pytest.approx(expected, abs=1e-4)
    assert result['records']['seen'][0] == pytest.approx(expected, abs=1e-4)
    # 没有分钟数据的日期：按收盘价近似并提示
    result = run(BUY_1450, start=DAYS[NO_MINUTE_DAY], end=DAYS[NO_MINUTE_DAY])
    assert result['trades'][0][5] == pytest.approx(raw.close[NO_MINUTE_DAY])
    assert any('没有分钟数据' in line for line in result['logs'])


LOOK_1000 = '''
def initialize(context):
    run_daily(look, '10:00')

def look(context):
    b = get_bars('600000.XSHG', 3, '1m', ['date', 'open', 'close'])
    record(last_time=b['date'][-1].hour * 100 + b['date'][-1].minute, last_close=b['close'][-1])
    five = attribute_history('600000.XSHG', 2, '5m', ['open', 'close', 'high', 'low', 'volume'], fq=None)
    record(five_open=five['open'].iloc[-1], five_close=five['close'].iloc[-1], five_vol=five['volume'].iloc[-1],
           five_time=five.index[-1].hour * 100 + five.index[-1].minute)
    y = get_price('600000.XSHG', end_date=context.current_dt.date(), count=1, frequency='1m', fields=['close'],
                  fq=None)
    record(prev_day_close=y['close'].iloc[-1])
    pre = get_price('600000.XSHG', end_date=context.current_dt, count=271, frequency='1m', fields=['close'])
    raw = get_price('600000.XSHG', end_date=context.current_dt, count=271, frequency='1m', fields=['close'], fq=None)
    record(pre_first=pre['close'].iloc[0], raw_first=raw['close'].iloc[0])
'''


def test_minute_bars_no_future_aggregate_and_adjust(minute_data):
    raw = minute_data
    i = 3
    rec = {k: v[0] for k, v in run(LOOK_1000, start=DAYS[i], end=DAYS[i])['records'].items()}
    path = _path(raw.open[i], raw.close[i])
    assert rec['last_time'] == 1000 and rec['last_close'] == pytest.approx(path[29], abs=1e-4)
    assert rec['five_time'] == 1000  # 09:56~10:00 这根刚走完
    assert rec['five_open'] == pytest.approx(path[24], abs=1e-4)
    assert rec['five_close'] == pytest.approx(path[29], abs=1e-4)
    assert rec['five_vol'] == 5 * 100 * 100
    assert rec['prev_day_close'] == pytest.approx(raw.close[i - 1], abs=1e-4)  # 只有日期的 end_date 不含当天
    # 跨除权日：前复权以回测当天为基准扣除分红（DIVIDEND=30 当天派 0.5 元；271 根回溯到第 29 天最后一分钟）
    rec = {k: v[0] for k, v in run(LOOK_1000, start=DAYS[31], end=DAYS[31])['records'].items()}
    assert rec['raw_first'] - rec['pre_first'] == pytest.approx(0.5 * rec['raw_first'] / raw.close[29], abs=0.01)


MINUTE_MODE = '''
def initialize(context):
    g.n = 0
    run_daily(lambda c: setattr(g, 'bars', getattr(g, 'bars', 0) + 1), 'every_bar')

def handle_data(context, data):
    g.n += 1
    if context.current_dt.hour == 14 and context.current_dt.minute == 0:
        record(close=data['600000.XSHG'].close, last=get_current_data()['600000.XSHG'].last_price)

def after_trading_end(context):
    record(n=g.n, bars=g.bars)
'''


def test_minute_frequency_handle_data(minute_data):
    raw = minute_data
    i = 4
    result = child.run_strategy(MINUTE_MODE, DAYS[i], DAYS[i], 1_000_000, frequency='minute')
    rec = {k: v[0] for k, v in result['records'].items()}
    assert rec['n'] == 240 and rec['bars'] == 240
    expected = _path(raw.open[i], raw.close[i])[minute.point_index(14 * 60)]
    assert rec['close'] == pytest.approx(expected, abs=1e-4) and rec['last'] == pytest.approx(expected, abs=1e-4)


def test_minute_sync_resumes_and_validates(quant_data, monkeypatch):  # noqa: F811
    raw = store.read_raw('300001.XSHE')
    calls = []

    class FakeClient:
        def __init__(self, host, timeout=10):
            self.host, self.sock = host, None

        def connect(self):
            self.sock = object()
            return self

        def close(self):
            self.sock = None

        def minutes(self, code, day):
            calls.append(day)
            row = raw[raw['date'].dt.date == day].iloc[0]
            bad = day == DAYS[7] or (day == DAYS[8] and calls.count(day) == 1)
            close = row.close + (0.5 if bad else 0)  # DAYS[7] 各服务器都不符应丢弃；DAYS[8] 首次不符，换服务器取到
            return _path(row.open, close), np.full(240, 10)

    monkeypatch.setattr(tdxhq, 'Client', FakeClient)
    totals = minute.sync(['300001.XSHE'], DAYS[0].isoformat(), connections=2, end=DAYS[9])
    assert totals['days'] == 9 and totals['mismatch'] == 1
    saved = minute.load('300001.XSHE', 2022)
    assert len(saved['dates']) == 9 and saved['price'].shape == (9, 240)
    assert 20220113 in saved['dates'] and 20220112 not in saved['dates']  # DAYS[8] 保留、DAYS[7] 丢弃
    assert calls.count(DAYS[8]) == 2 and calls.count(DAYS[7]) == 2  # 不符时都问过另一台服务器
    calls.clear()
    totals = minute.sync(['300001.XSHE'], DAYS[0].isoformat(), connections=2, end=DAYS[11])
    assert sorted(set(calls)) == [DAYS[7], DAYS[10], DAYS[11]]  # 只补缺失的日期
    assert totals['days'] == 2


def test_minute_sync_skips_stocks_without_data(minute_data, monkeypatch):
    calls = []

    class EmptyClient:
        def __init__(self, host, timeout=10):
            self.host, self.sock = host, None

        def connect(self):
            self.sock = object()
            return self

        def close(self):
            self.sock = None

        def minutes(self, code, day):
            calls.append((self.host, day))
            return None  # 已退市股票：各服务器都没有分时

    monkeypatch.setattr(tdxhq, 'Client', EmptyClient)
    totals = minute.sync(['600000.XSHG'], DAYS[0].isoformat(), connections=1, end=DAYS[-1])
    # 只缺 NO_MINUTE_DAY 一天：抽查这一天，主、备两台服务器都问过后放弃，不再逐日请求
    assert totals['unavailable'] == 1 and totals['days'] == 0
    assert len(calls) == 2 and calls[0][0] != calls[1][0]
    assert '600000.XSHG' in store.load_state()['minute']['unavailable']
    calls.clear()
    minute.sync(['600000.XSHG'], DAYS[0].isoformat(), connections=1, end=DAYS[-1])
    assert calls == []  # 近期确认没有数据的股票直接跳过
