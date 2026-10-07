"""策略信号的后验收益：信号日收盘后才能决策，以次日开盘价买入，持有 N 个交易日后按收盘价计算收益(%)。
同时按同样口径计算当日全部 A 股的等权平均收益作为基准，用于衡量策略的超额收益。"""
import logging
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat

import numpy as np
import pandas as pd

from instock import config, db, history, market
from instock.analysis.bars import Bars
from instock.schema import BENCHMARK, RETURN_HORIZONS, SIGNAL

log = logging.getLogger(__name__)
_RET_COLS = [f'ret_{h}' for h in RETURN_HORIZONS]


def forward_returns(b, i):
    n = len(b)
    if i + 1 >= n:
        return {col: None for col in _RET_COLS}
    entry = b.open[i + 1]
    return {f'ret_{h}': round((b.close[i + h] / entry - 1) * 100, 4) if i + h < n and entry > 0 else None
            for h in RETURN_HORIZONS}


def update_pending():
    """补算尚未完整的信号收益（最长周期仍为空的信号）。"""
    pending = db.read(f'SELECT date, strategy, code, {", ".join(_RET_COLS)} FROM {SIGNAL.name} '
                      f'WHERE ret_{RETURN_HORIZONS[-1]} IS NULL')
    if pending.empty:
        return 0
    pending['date'] = pd.to_datetime(pending['date']).dt.date
    rows = []
    for code, group in pending.groupby('code'):
        df = history.load(code)
        if df is None or df.empty:
            continue
        b = Bars(df)
        for rec in group.itertuples(index=False):
            i = b.index(rec.date)
            if i is None:
                continue
            rets = forward_returns(b, i)
            if any(rets[col] is not None and pd.isna(getattr(rec, col)) for col in _RET_COLS):
                rows.append({'date': rec.date, 'strategy': rec.strategy, 'code': code, **rets})
    db.update(SIGNAL, rows, keys=('date', 'strategy', 'code'))
    log.info('策略回测：待更新信号 %d 条，本次更新 %d 条', len(pending), len(rows))
    return len(rows)


def _benchmark_chunk(codes, days):
    sums = np.zeros((len(days), len(RETURN_HORIZONS)))
    counts = np.zeros_like(sums)
    for code in codes:
        df = history.load(code)
        if df is None or df.empty:
            continue
        b = Bars(df)
        for k, day in enumerate(days):
            i = b.index(day)
            if i is None:
                continue
            for j, value in enumerate(forward_returns(b, i).values()):
                if value is not None:
                    sums[k, j] += value
                    counts[k, j] += 1
    return sums, counts


def update_benchmark(workers=config.ANALYSIS_WORKERS):
    """为有信号但基准收益尚不完整的日期计算全市场等权基准收益。"""
    signal_days = set(pd.to_datetime(db.read(f'SELECT DISTINCT date FROM {SIGNAL.name}')['date']).dt.date)
    done = set(pd.to_datetime(db.read(f'SELECT date FROM {BENCHMARK.name} '
                                      f'WHERE ret_{RETURN_HORIZONS[-1]} IS NOT NULL')['date']).dt.date)
    days = sorted(signal_days - done)
    if not days:
        return
    codes = [p.stem for p in config.HIST_DIR.glob('*.pkl') if market.is_a_share(p.stem)]
    size = max(50, len(codes) // (workers * 4) + 1)
    sums = np.zeros((len(days), len(RETURN_HORIZONS)))
    counts = np.zeros_like(sums)
    with ProcessPoolExecutor(workers) as pool:
        for s, c in pool.map(_benchmark_chunk, [codes[i:i + size] for i in range(0, len(codes), size)], repeat(days)):
            sums += s
            counts += c
    with np.errstate(invalid='ignore', divide='ignore'):
        means = np.where(counts > 0, sums / counts, np.nan)
    for k, day in enumerate(days):
        row = {'date': day, 'stocks': int(counts[k, 0]), **dict(zip(_RET_COLS, means[k]))}
        db.replace(BENCHMARK, pd.DataFrame([row]), date=day)
    log.info('基准收益：更新 %d 个交易日', len(days))
