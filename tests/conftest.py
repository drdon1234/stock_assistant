import datetime
import os
import tempfile

# 必须在导入 instock 之前设置：测试使用临时目录和 SQLite，不触碰真实数据
_tmp = tempfile.mkdtemp(prefix='instock-test-')
os.environ['INSTOCK_DATA_DIR'] = _tmp
os.environ['INSTOCK_DB_URL'] = f"sqlite:///{os.path.join(_tmp, 'test.db').replace(os.sep, '/')}"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from instock import tradecal  # noqa: E402


def weekdays(start, end):
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += datetime.timedelta(days=1)
    return days


@pytest.fixture
def calendar(monkeypatch):
    """用工作日代替真实交易日历，避免测试访问网络。"""
    cal = tradecal.TradeCalendar(weekdays(datetime.date(2018, 1, 1), datetime.date(2030, 12, 31)))
    monkeypatch.setattr(tradecal, 'get', lambda: cal)
    return cal


def make_bars(close, start=datetime.date(2022, 1, 3), spread=0.01):
    """由收盘价序列构造日 K 线：开盘为昨收，高低价在开收盘外加一点波动。"""
    close = np.asarray(close, dtype=float)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    dates = pd.to_datetime(weekdays(start, start + datetime.timedelta(days=len(close) * 2))[:len(close)])
    return pd.DataFrame({'date': dates, 'open': open_, 'high': high, 'low': low, 'close': close,
                         'volume': np.full(len(close), 1e6), 'amount': close * 1e6, 'turnover': np.full(len(close), 1.0)})
