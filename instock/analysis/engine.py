"""批量分析：多进程逐只股票读取 K 线缓存，一次计算整段指标/形态，再按日期取值并判断策略。

一只股票无论分析多少个日期都只计算一次指标，区间回补时比逐日计算快一个数量级。
"""
import logging
import traceback
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat

import pandas as pd

from instock import history
from instock.analysis import patterns
from instock.analysis.bars import Bars
from instock.analysis.strategies import BY_KEY, TECHNICAL

log = logging.getLogger(__name__)


def _analyze(code, days):
    df = history.load(code)
    if df is None or df.empty:
        return None
    b = Bars(df)
    found = [(day, i) for day in days if (i := b.index(day)) is not None]
    if not found:
        return None
    ind = b.indicators()
    pats = patterns.detect(b.open, b.high, b.low, b.close)
    indicators, pattern_rows, hits, rs = [], [], [], []
    for day, i in found:
        indicators.append({'date': day, 'code': code, 'close': b.close[i], **{k: v[i] for k, v in ind.items()}})
        row = {k: int(v[i]) for k, v in pats.items() if v[i]}
        if row:
            pattern_rows.append({'date': day, 'code': code, **row})
        for s in TECHNICAL:
            if i + 1 >= s.min_bars and s.check(b, i):
                hits.append({'date': day, 'strategy': s.key, 'code': code, 'close': b.close[i]})
        rs.append({'date': day, 'code': code, 'rs': b.rs_score(i)})
    return indicators, pattern_rows, hits, rs


def _analyze_chunk(codes, days):
    results, errors = [], []
    for code in codes:
        try:
            result = _analyze(code, days)
            if result:
                results.append(result)
        except Exception:
            errors.append(f'{code}: {traceback.format_exc(limit=3)}')
    return results, errors


def run(codes, days, workers):
    """返回 (指标, 形态, 策略信号) 三个 DataFrame，名称列未填充。"""
    codes = list(codes)
    size = max(20, len(codes) // (workers * 8) + 1)
    chunks = [codes[i:i + size] for i in range(0, len(codes), size)]
    parts = ([], [], [], [])
    with ProcessPoolExecutor(workers) as pool:
        for results, errors in pool.map(_analyze_chunk, chunks, repeat(days)):
            for error in errors:
                log.error('分析失败 %s', error)
            for result in results:
                for part, rows in zip(parts, result):
                    part.extend(rows)
    indicators, pattern_rows, hits, rs = (pd.DataFrame(p) for p in parts)
    return indicators, pattern_rows, _filter_rs(hits, rs)


def _filter_rs(hits, rs):
    """需要相对强度排名的策略：按当日全部股票的 RS 原始分算百分位后过滤。"""
    if hits.empty or rs.empty:
        return hits
    rs['rs_pct'] = rs.groupby('date')['rs'].rank(pct=True) * 100
    hits = hits.merge(rs[['date', 'code', 'rs_pct']], on=['date', 'code'], how='left')
    min_rs = hits['strategy'].map(lambda k: BY_KEY[k].min_rs)
    keep = (min_rs == 0) | (hits['rs_pct'] >= min_rs)
    return hits[keep].drop(columns='rs_pct')
