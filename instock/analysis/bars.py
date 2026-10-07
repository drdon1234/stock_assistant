import numpy as np

from instock.analysis import indicators


class Bars:
    """单只股票的日 K 线（前复权，量单位：股），并缓存策略常用的派生序列。"""

    def __init__(self, df):
        self.dates = df['date'].to_numpy(dtype='datetime64[D]')
        self.open = df['open'].to_numpy(dtype=float)
        self.high = df['high'].to_numpy(dtype=float)
        self.low = df['low'].to_numpy(dtype=float)
        self.close = df['close'].to_numpy(dtype=float)
        self.volume = df['volume'].to_numpy(dtype=float)
        self._cache = {}

    def __len__(self):
        return len(self.close)

    def index(self, day):
        """day 当天 K 线的下标；当天无交易（停牌/未上市）返回 None。"""
        day = np.datetime64(day, 'D')
        i = int(np.searchsorted(self.dates, day))
        return i if i < len(self.dates) and self.dates[i] == day else None

    def _cached(self, key, build):
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    def ma(self, n):
        return self._cached(('ma', n), lambda: indicators.ma(self.close, n))

    def vol_ma(self, n):
        return self._cached(('vol_ma', n), lambda: indicators.ma(self.volume, n))

    def rsi(self, n):
        return self._cached(('rsi', n), lambda: indicators.rsi(self.close, n))

    def indicators(self):
        return self._cached('indicators', lambda: indicators.compute(
            self.open, self.high, self.low, self.close, self.volume))

    def rs_score(self, i):
        """IBD 风格相对强度原始分：近 3/6/9/12 个月涨幅加权（最近一季权重 40%）。数据不足一年返回 NaN。"""
        if i < 252:
            return np.nan
        c = self.close
        return 0.4 * (c[i] / c[i - 63] - 1) + 0.2 * (c[i] / c[i - 126] - 1) + \
            0.2 * (c[i] / c[i - 189] - 1) + 0.2 * (c[i] / c[i - 252] - 1)
