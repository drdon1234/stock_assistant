import numpy as np
import pytest

from instock.analysis import indicators

from conftest import make_bars


@pytest.fixture
def bars():
    rng = np.random.default_rng(7)
    close = 10 * np.exp(np.cumsum(rng.normal(0, 0.02, 400)))
    return make_bars(close)


def _arrays(df):
    return tuple(df[k].to_numpy(dtype=float) for k in ('open', 'high', 'low', 'close', 'volume'))


def tdx_ema(x, n):
    """通达信 EMA：Y = (2X + (N-1)Y') / (N+1)，首值为 X。"""
    out = np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = (2 * x[i] + (n - 1) * out[i - 1]) / (n + 1)
    return out


def tdx_sma(x, n, m=1):
    out = np.full(len(x), np.nan)
    start = np.flatnonzero(~np.isnan(x))[0]
    out[start] = x[start]
    for i in range(start + 1, len(x)):
        out[i] = (m * x[i] + (n - m) * out[i - 1]) / n
    return out


def test_macd_matches_tdx_formula(bars):
    o, h, l, c, v = _arrays(bars)
    ind = indicators.compute(o, h, l, c, v)
    dif = tdx_ema(c, 12) - tdx_ema(c, 26)
    dea = tdx_ema(dif, 9)
    np.testing.assert_allclose(ind['macd'], dif, rtol=1e-9)
    np.testing.assert_allclose(ind['macdh'], 2 * (dif - dea), rtol=1e-9, atol=1e-12)


def test_rsi_matches_wilder_smoothing(bars):
    c = bars['close'].to_numpy()
    diff = np.concatenate([[np.nan], np.diff(c)])
    expected = tdx_sma(np.fmax(diff, 0), 6) / tdx_sma(np.abs(diff), 6) * 100
    np.testing.assert_allclose(indicators.rsi(c, 6)[1:], expected[1:], rtol=1e-9)


def test_kdj_and_wr_ranges(bars):
    ind = indicators.compute(*_arrays(bars))
    k = ind['kdjk'][20:]
    assert np.all((k >= 0) & (k <= 100))
    for key in ('wr_6', 'wr_10', 'wr_14'):
        wr = ind[key][20:]
        assert np.all((wr >= 0) & (wr <= 100))
    np.testing.assert_allclose(ind['kdjj'], 3 * ind['kdjk'] - 2 * ind['kdjd'])


def test_true_range_not_below_high_low(bars):
    o, h, l, c, v = _arrays(bars)
    tr = indicators.true_range(h, l, c)
    assert np.all(tr >= h - l - 1e-12)


def test_indicators_only_use_past_data(bars):
    """分析引擎对整段历史计算一次后按日期取值，要求每个指标都不使用未来数据。"""
    full = indicators.compute(*_arrays(bars))
    cut = 300
    part = indicators.compute(*(a[:cut] for a in _arrays(bars)))
    for key, values in part.items():
        np.testing.assert_allclose(values[-1], full[key][cut - 1], rtol=1e-9, atol=1e-9, equal_nan=True,
                                   err_msg=key)


def test_warmup_is_nan_not_zero(bars):
    ind = indicators.compute(*_arrays(bars))
    assert np.isnan(ind['bias_24'][0])
    assert np.isnan(ind['cci_84'][50])
