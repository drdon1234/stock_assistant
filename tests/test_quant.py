"""聚宽兼容回测：用合成数据验证宽表、撮合规则、分红送转、未来函数防护、定时任务、静态检查与任务运行。"""
import datetime
import json
import time

import numpy as np
import pandas as pd
import pytest

from instock import config
from instock.quant import check, child, engine, runner, store
from conftest import weekdays

DAYS = weekdays(datetime.date(2022, 1, 3), datetime.date(2022, 3, 31))[:60]
LIMIT_UP, PAUSED, DIVIDEND, SPLIT = 10, 20, 30, 40


def _raw(closes, events=None, paused=(), limit_up=()):
    """由收盘价构造日线：开盘为昨收，events 为 {行号: 当天的昨收}（除权）。"""
    rows, factor, prev = [], 1.0, None
    for i, (day, close) in enumerate(zip(DAYS, closes)):
        pre = (events or {}).get(i, prev if prev is not None else close)
        if prev is not None and pre != prev:
            factor *= prev / pre
        open_ = round(pre * 1.1, 2) if i in limit_up else pre
        if i in paused:
            rows.append([day, pre, pre, pre, pre, pre, 0, 0, 1, 0, factor])
            prev = pre
            continue
        rows.append([day, open_, max(open_, close) * 1.01, min(open_, close) * 0.99, close, pre, 1e6, close * 1e6,
                     0, 0, factor])
        prev = close
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'pre_close', 'volume', 'money',
                                     'paused', 'is_st', 'factor'])
    df['date'] = pd.to_datetime(df['date'])
    df[['paused', 'is_st']] = df[['paused', 'is_st']].astype('int8')
    return df


def _closes_a():
    closes = [10 + 0.1 * i for i in range(60)]
    closes[LIMIT_UP] = round(closes[LIMIT_UP - 1] * 1.1, 2)
    for i in range(LIMIT_UP + 1, 60):
        closes[i] = round(closes[i] + 1, 2)
    closes[PAUSED] = closes[PAUSED - 1]
    for i in range(DIVIDEND, 60):
        closes[i] = round(closes[i] - 0.5, 2)
    return closes


@pytest.fixture(scope='module')
def quant_data():
    """在测试数据目录中生成两只股票、一个指数的回测数据。"""
    a = _closes_a()
    store.write_raw('600000.XSHG', _raw(a, {DIVIDEND: round(a[DIVIDEND - 1] - 0.5, 2)}, paused=(PAUSED,),
                                        limit_up=(LIMIT_UP,)))
    b = [20 + 0.2 * i for i in range(60)]
    for i in range(SPLIT, 60):
        b[i] = round(b[i] / 2, 3)
    store.write_raw('300001.XSHE', _raw(b, {SPLIT: b[SPLIT - 1] / 2}))  # 10 送 10
    store.write_raw('000300.XSHG', _raw([4000 + 10 * i for i in range(60)]))
    store.save_securities(pd.DataFrame({
        'code': ['600000.XSHG', '300001.XSHE', '000300.XSHG'], 'display_name': ['浦发银行', '特锐德', '沪深300'],
        'start_date': pd.to_datetime(['2010-01-01'] * 3), 'end_date': pd.to_datetime([None] * 3),
        'type': ['stock', 'stock', 'index']}))
    store.save_members(pd.DataFrame([{'index': '000300.XSHG', 'date': DAYS[0], 'codes': ('600000.XSHG',)},
                                     {'index': '000300.XSHG', 'date': DAYS[25],
                                      'codes': ('300001.XSHE', '600000.XSHG')}]))
    store.save_trade_days(DAYS)
    config.QUANT_START = DAYS[0].isoformat()
    store.build_panel([2022], DAYS, DAYS[-1])
    store.save_state({'ready': True, 'start': DAYS[0].isoformat(), 'last_date': DAYS[-1].isoformat()})
    return a, b


def run(code, start=DAYS[0], end=DAYS[-1], capital=1_000_000):
    return child.run_strategy(code, start, end, capital)


def test_panel_layout(quant_data):
    panel = store.Panel()
    assert len(panel) == 60 and panel.codes == sorted(panel.codes)
    a = panel.column('close', 0, 60, '600000.XSHG')
    assert a[PAUSED] == a[PAUSED - 1]
    assert panel.value('paused', PAUSED, '600000.XSHG') == 1
    assert panel.value('high_limit', LIMIT_UP, '600000.XSHG') == pytest.approx(round(a[LIMIT_UP - 1] * 1.1, 2))
    assert np.isnan(panel.value('high_limit', 5, '000300.XSHG'))  # 指数不设涨跌停
    missing = panel.block('close', 0, 2, [-1])
    assert np.isnan(missing).all() and panel.block('paused', 0, 2, [-1]).tolist() == [[1], [1]]


def test_limit_price_rules():
    d = lambda s: np.datetime64(s)  # noqa: E731
    days = np.array([d('2020-08-21'), d('2020-08-24')])
    high, low = store.limit_prices('300001', days, [10.0, 10.0], [0, 0], '2010-01-01')
    assert high.tolist() == [11.0, 12.0] and low.tolist() == [9.0, 8.0]
    high, _ = store.limit_prices('600001', days, [10.0, 10.0], [1, 1], '2010-01-01')
    assert high.tolist() == [10.5, 10.5]
    high, _ = store.limit_prices('600001', np.array([d('2025-07-07')]), [10.0], [1], '2010-01-01')
    assert high.tolist() == [11.0]
    ipo = np.array([d('2021-07-01') + np.timedelta64(i, 'D') for i in range(7)])
    high, _ = store.limit_prices('688001', ipo, [10.0] * 7, [0] * 7, '2021-07-01')
    assert np.isnan(high[:5]).all() and high[5] == 12.0
    high, low = store.limit_prices('600002', np.array([d('2015-06-01'), d('2015-06-02')]), [10.0, 14.4], [0, 0],
                                   '2015-06-01')
    assert (high[0], low[0], high[1]) == (14.4, 6.4, 15.84)
    # 四舍五入：10.05 * 1.1 = 11.055 -> 11.06
    assert store.limit_prices('600003', np.array([d('2022-01-04')]), [10.05], [0], None)[0][0] == 11.06


BUY_HOLD = '''
def initialize(context):
    set_benchmark('000300.XSHG')
    run_daily(trade, 'open')

def trade(context):
    if not context.portfolio.positions:
        order('600000.XSHG', 1000)
'''


def test_buy_fills_at_open_with_commission(quant_data):
    a, _ = quant_data
    result = run(BUY_HOLD, end=DAYS[5])
    trade = result['trades'][0]
    assert trade[3] == '买' and trade[4] == 1000 and trade[5] == pytest.approx(a[0])  # 首日开盘价为昨收
    assert trade[7] == 5.0  # 佣金不足 5 元按 5 元
    final = 1_000_000 - 1000 * a[0] - 5 + 1000 * a[5]
    assert result['summary']['final_value'] == pytest.approx(final)
    assert result['summary']['total_return'] == pytest.approx(final / 1e6 - 1)
    assert result['daily']['benchmark'][-1] == pytest.approx(4050 / 4000 - 1)


def test_t_plus_one_limit_and_paused(quant_data):
    code = '''
def initialize(context):
    run_daily(trade, 'open')

def trade(context):
    i = context.run_params.start_date
    d = context.current_dt.date()
    if d == get_trade_days(i, count=None)[0]:
        order('600000.XSHG', 500)
        log.info('sell same day', order('600000.XSHG', -500))
    elif len(get_trade_days(i, d)) == 2:
        log.info('sell next day', order('600000.XSHG', -500) is not None)
    elif len(get_trade_days(i, d)) == %d:
        log.info('limit up', order('600000.XSHG', 100))
    elif len(get_trade_days(i, d)) == %d:
        log.info('paused', order('600000.XSHG', 100))
''' % (LIMIT_UP + 1, PAUSED + 1)
    logs = '\n'.join(run(code)['logs'])
    assert 'sell same day None' in logs and 'T+1' in logs
    assert 'sell next day True' in logs
    assert '涨停' in logs and 'limit up None' in logs
    assert '停牌' in logs and 'paused None' in logs


def test_dividend_and_split(quant_data):
    a, b = quant_data
    code = '''
def initialize(context):
    run_daily(trade, 'open')

def trade(context):
    if not context.portfolio.positions:
        order('600000.XSHG', 1000)
        order('300001.XSHE', 1000)
'''
    result = run(code, start=DAYS[DIVIDEND - 2], end=DAYS[SPLIT + 1])
    logs = '\n'.join(result['logs'])
    assert '600000.XSHG 分红：每股 0.5000 元' in logs
    assert '300001.XSHE 送转股' in logs
    positions = {p['code']: p for p in result['positions']}
    assert positions['300001.XSHE']['amount'] == 2000
    # 分红、送转都不改变当天开盘前的账户价值
    # 首日开盘价为前一日收盘价
    cash = 1_000_000 - 1000 * a[DIVIDEND - 3] - 5 - 1000 * b[DIVIDEND - 3] - 1000 * b[DIVIDEND - 3] * 0.0003 + 500
    expected = cash + 1000 * a[SPLIT + 1] + 2000 * b[SPLIT + 1]
    assert result['summary']['final_value'] == pytest.approx(expected, abs=0.02)


def test_no_future_data_and_dynamic_pre_adjust(quant_data):
    a, _ = quant_data
    code = '''
def initialize(context):
    run_daily(at_open, 'open')
    run_daily(at_close, 'close')

def at_open(context):
    h = attribute_history('600000.XSHG', 2, '1d', ['close'], skip_paused=False)
    p = get_price('600000.XSHG', end_date=context.current_dt, count=1, fields=['close'])
    record(open_hist=h['close'].iloc[-1], open_price=p['close'].iloc[-1], last=get_current_data()['600000.XSHG'].last_price)

def at_close(context):
    p = get_price('600000.XSHG', end_date=context.current_dt, count=1, fields=['close'])
    raw = get_price('600000.XSHG', end_date=context.current_dt, count=3, fields=['close'], fq=None)
    record(close_price=p['close'].iloc[-1], raw_first=raw['close'].iloc[0])
'''
    i = DIVIDEND + 1
    result = run(code, start=DAYS[i], end=DAYS[i])
    rec = {k: v[0] for k, v in result['records'].items()}
    assert rec['open_hist'] == pytest.approx(a[i - 1])
    assert rec['open_price'] == pytest.approx(a[i - 1])  # 开盘时 get_price 取不到当天
    assert rec['last'] == pytest.approx(a[i - 1])  # 开盘价为昨收
    assert rec['close_price'] == pytest.approx(a[i])  # 收盘后可以取到当天
    assert rec['raw_first'] == pytest.approx(a[i - 2])  # 不复权：除权前的原始价格
    pre = run(code.replace("fq=None", "fq='pre'"), start=DAYS[i], end=DAYS[i])['records']['raw_first'][0]
    assert pre == pytest.approx(a[i - 2] - 0.5, abs=0.01)  # 前复权：以当天为基准扣除分红


def test_schedules_and_index_members(quant_data):
    code = '''
def initialize(context):
    g.weekly, g.monthly, g.last = 0, 0, 0
    run_weekly(lambda c: setattr(g, 'weekly', g.weekly + 1), 1, 'open')
    run_monthly(lambda c: setattr(g, 'monthly', g.monthly + 1), -1, 'close')
    run_daily(members, 'before_open')

def members(context):
    record(n=len(get_index_stocks('000300.XSHG')))

def on_strategy_end(context):
    log.info('counts', g.weekly, g.monthly)
'''
    result = run(code)
    assert 'counts 12 3' in '\n'.join(result['logs'])
    n = result['records']['n']
    assert n[24] == 1 and n[25] == 2


def test_strategy_error_reports_line(quant_data):
    code = 'def initialize(context):\n    run_daily(f)\n\ndef f(context):\n    x = 1 / 0\n'
    with pytest.raises(child.StrategyFailure) as info:
        run(code, end=DAYS[2])
    assert 'ZeroDivisionError' in info.value.message
    assert info.value.trace[-1]['line'] == 5
    with pytest.raises(child.StrategyFailure, match='暂不支持聚宽函数 query'):
        run('def initialize(context):\n    get_fundamentals(query(valuation))\n', end=DAYS[2])


def test_jqdata_import_and_helpers(quant_data):
    code = '''
from jqdata import *
import jqdata

def initialize(context):
    log.info(normalize_code('600000'), normalize_code('000001'), jqdata.get_trade_days(count=2)[-1])
    s = get_all_securities(['stock'])
    log.info('securities', len(s), s.loc['600000.XSHG', 'display_name'])
    bars = get_bars('600000.XSHG', 3, '1d', ['date', 'close'])
    log.info('bars', len(bars))
    panel = get_price(['600000.XSHG', '300001.XSHE'], end_date=context.previous_date, count=2, fields=['close'])
    log.info('panel', panel['close'].shape)
'''
    logs = '\n'.join(run(code, start=DAYS[10], end=DAYS[11])['logs'])
    assert '600000.XSHG 000001.XSHE' in logs
    assert 'securities 2 浦发银行' in logs and 'bars 3' in logs and 'panel (2, 2)' in logs


def test_static_check():
    report = check.check('import jqlib\ndef initialize(context):\n    q = query(valuation.code)\n'
                         '    run_daily(f, "14:50")\n    get_price("600000.XSHG", frequency="1m")\n')
    messages = ' '.join(i['message'] for i in report['warnings'])
    assert not report['errors']
    assert 'jqlib' in messages and 'query' in messages and 'valuation.code' in messages and '1m' in messages
    assert '收盘价' in report['notes'][0]['message']
    assert check.check('def f(:\n')['errors'][0]['line'] == 1
    assert check.check('x = 1')['errors'][0]['message'].startswith('缺少 initialize')


def test_normalize_code():
    assert engine.normalize_code('600000') == '600000.XSHG'
    assert engine.normalize_code('000001.XSHE') == '000001.XSHE'
    assert engine.normalize_code('sz000001') == '000001.XSHE'
    assert engine.normalize_code('600000.SH') == '600000.XSHG'


def test_job_lifecycle(quant_data, monkeypatch):
    monkeypatch.setattr(runner, 'runner_status', lambda: {'alive': True, 'sandboxed': False})
    admin, user = {'username': 'admin', 'admin': True}, {'username': 'bob', 'admin': False}
    with pytest.raises(runner.JobError, match='只有管理员'):
        runner.create_job(user, {'code': BUY_HOLD})
    job, report = runner.create_job(admin, {'code': 'x = 1'})
    assert job is None and report['errors']
    job, _ = runner.create_job(admin, {'code': BUY_HOLD, 'start': '2021-01-01', 'end': '2022-12-31', 'name': '买入'})
    assert job['start'] == DAYS[0].isoformat() and job['status']['state'] == 'queued'
    with pytest.raises(runner.JobError, match='不存在'):
        runner.get_job(job['id'], user)

    folder = runner.jobs_dir() / job['id']
    running = runner._Running(folder)  # 真实子进程：与运行器执行的方式相同
    deadline = time.time() + 120
    while running.proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    running.finish()
    detail = runner.get_job(job['id'], admin)
    assert detail['status']['state'] == 'done', detail['status']
    assert detail['result']['summary']['trades'] == 1
    assert json.loads((folder / 'status.json').read_text(encoding='utf-8'))['summary']['days'] == 60
    assert runner.remove_job(job['id'], admin) == 'deleted' and not folder.exists()
