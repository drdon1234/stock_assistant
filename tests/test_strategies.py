import numpy as np
import pandas as pd
import pytest

from instock.analysis.bars import Bars
from instock.analysis.strategies import BY_KEY, TECHNICAL

from conftest import make_bars


@pytest.mark.parametrize('seed', range(5))
def test_every_strategy_runs_on_every_bar(seed):
    """随机游走数据上逐根 K 线调用全部策略，确保不越界、不抛异常且返回布尔值。"""
    rng = np.random.default_rng(seed)
    b = Bars(make_bars(10 * np.exp(np.cumsum(rng.normal(0, 0.03, 320)))))
    for s in TECHNICAL:
        for i in range(s.min_bars - 1, len(b)):
            assert isinstance(bool(s.check(b, i)), bool)


def test_turtle_breakout():
    close = np.concatenate([np.full(60, 10.0), [11.0]])
    b = Bars(make_bars(close, spread=0.0))
    assert BY_KEY['turtle'].check(b, len(b) - 1)
    assert not BY_KEY['turtle'].check(b, len(b) - 2)


def test_id_nr4():
    df = make_bars(np.full(10, 10.0), spread=0.0)
    df['high'] = [11, 11, 11, 11, 11, 11, 12, 11.8, 11.6, 11.2]
    df['low'] = [9, 9, 9, 9, 9, 9, 8, 8.5, 8.7, 9.5]
    assert BY_KEY['id_nr4'].check(Bars(df), 9)


def test_rsi2_requires_uptrend_and_pullback():
    up = np.linspace(10, 20, 230)
    pullback = np.concatenate([up, [19.0, 18.0]])
    assert BY_KEY['rsi2'].check(Bars(make_bars(pullback)), len(pullback) - 1)
    assert not BY_KEY['rsi2'].check(Bars(make_bars(up)), len(up) - 1)


def test_high_tight_flag():
    base = np.full(40, 10.0)
    pole = np.linspace(10, 21, 25)  # 25 个交易日上涨 110%
    flag = np.linspace(20.5, 19.0, 8)  # 回撤约 10%
    close = np.concatenate([base, pole, flag, [21.6]])
    b = Bars(make_bars(close, spread=0.0))
    assert BY_KEY['high_tight_flag'].check(b, len(b) - 1)


def test_flat_base_breakout_needs_volume():
    close = np.concatenate([np.linspace(8, 10, 60), np.full(25, 10.0), [10.6]])
    df = make_bars(close, spread=0.01)
    b = Bars(df)
    assert not BY_KEY['flat_base_breakout'].check(b, len(b) - 1)  # 量能不足
    df.loc[len(df) - 1, 'volume'] = 3e6
    assert BY_KEY['flat_base_breakout'].check(Bars(df), len(df) - 1)


def test_graham_screen():
    df = pd.DataFrame({
        'code': ['000001', '000002', '000003'], 'name': ['a', 'b', 'c'], 'new_price': [10, 10, 10],
        'total_operate_income': [6e9, 6e9, 1e9], 'current_ratio': [2.5, 2.5, 3], 'pe9': [10, 18, 8],
        'pbnewmrq': [1.2, 1.0, 1.0], 'zxgxl': [3, 3, 3], 'parent_netprofit': [1e8, 1e8, 1e8],
        'netprofit_growthrate_3y': [5, 5, 5],
    })
    assert BY_KEY['graham'].screen(df)['code'].tolist() == ['000001']
