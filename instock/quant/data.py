"""回测数据同步：从 BaoStock 回补 / 增量更新不复权日线、复权因子、证券列表、交易日历与指数成分，再生成宽表。

回补与增量是同一个过程：每只证券从本地已有数据的下一天抓起，没有数据则从 QUANT_START（或上市日）抓起，
因此中断后重新运行会从断点继续。首次全量约 7000 只证券，4 个进程约 7~8 小时。
"""
import datetime
import logging
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from instock import config, tradecal
from instock.quant import store
from instock.sources import baostock as bs

log = logging.getLogger(__name__)

_MEMBERS_START = datetime.date(2007, 1, 1)  # BaoStock 指数成分最早约从 2007 年开始


def _with_factor(code, df, is_index):
    """按除权除息日的后复权因子，给每一行填上当日的因子（除权日起生效，首个除权日之前为 1）。"""
    df = df.sort_values('date', ignore_index=True)
    if is_index:
        return df.assign(factor=1.0)
    factors = bs.adjust_factors(code).sort_values('date')
    if factors.empty:
        return df.assign(factor=1.0)
    merged = pd.merge_asof(df.drop(columns='factor', errors='ignore'), factors, on='date', direction='backward')
    merged['factor'] = merged['factor'].fillna(1.0)
    return merged


def _has_ex_event(old, new):
    """新数据中是否出现除权除息：某天的昨收与前一交易日收盘价不同。"""
    prev = np.concatenate([[old['close'].iloc[-1]], new['close'].to_numpy()[:-1]])
    return bool((np.abs(new['pre_close'].to_numpy() - prev) > 0.0051).any())


def sync_one(code, ipo, out, is_index, end):
    """同步一只证券，返回 (代码, 新增行数, 最早新增日期, 错误)。在子进程中运行。"""
    try:
        old = store.read_raw(code)
        start = datetime.date.fromisoformat(config.QUANT_START)
        if ipo is not None and not pd.isna(ipo):
            start = max(start, pd.Timestamp(ipo).date())
        if old is not None and not old.empty:
            start = old['date'].iloc[-1].date() + datetime.timedelta(days=1)
        stop = min(end, pd.Timestamp(out).date()) if out is not None and not pd.isna(out) else end
        if start > stop:
            return code, 0, None, None
        new = bs.daily(code, start, stop).dropna(subset=['close'])
        if new.empty:
            return code, 0, None, None
        if old is None or old.empty:
            df = _with_factor(code, new, is_index)
        elif is_index:
            df = pd.concat([old, new.assign(factor=1.0)], ignore_index=True)
        elif _has_ex_event(old, new):
            df = _with_factor(code, pd.concat([old, new], ignore_index=True), is_index)
        else:
            df = pd.concat([old, new.assign(factor=old['factor'].iloc[-1])], ignore_index=True)
        df = df.drop_duplicates('date', keep='last').sort_values('date', ignore_index=True)
        store.write_raw(code, df)
        return code, len(new), new['date'].iloc[0].date(), None
    except Exception as e:
        return code, 0, None, f'{type(e).__name__}: {e}'


def _init_worker():
    bs.login()


def _sample_days(days, since):
    """每周第一个交易日，用于抽样指数成分。"""
    out, week = [], None
    for d in days:
        if d < since:
            continue
        key = d.isocalendar()[:2]
        if key != week:
            out.append(d)
            week = key
    return out


def sync_members(days, today):
    """按周抽样指数成分，只在成分变化时保存一条快照。"""
    df = store.load_members()
    rows = df.to_dict('records')
    for index in bs.INDEX_MEMBERS:
        have = [r for r in rows if r['index'] == index]
        last = max(have, key=lambda r: r['date']) if have else None
        since = last['date'] + datetime.timedelta(days=1) if last else _MEMBERS_START
        current = tuple(last['codes']) if last else None
        sampled = _sample_days([d for d in days if d <= today], since)
        for i, day in enumerate(sampled):
            codes = tuple(bs.index_members(index, day))
            if codes and codes != current:
                rows.append({'index': index, 'date': day, 'codes': codes})
                current = codes
            if i and i % 100 == 0:
                log.info('指数成分 %s：%d / %d', index, i, len(sampled))
    store.save_members(pd.DataFrame(rows, columns=['index', 'date', 'codes']))


def sync(workers=None, codes=None):
    """同步回测数据并重建受影响年份的宽表。codes 只同步指定证券（调试用）。"""
    workers = workers or config.QUANT_WORKERS
    started = time.monotonic()
    state = store.load_state()
    bs.login()
    today = tradecal.now().date()
    secs = bs.securities()
    store.save_securities(secs)
    start = datetime.date.fromisoformat(config.QUANT_START)
    days = bs.trade_days(min(start, _MEMBERS_START), datetime.date(today.year, 12, 31))
    store.save_trade_days(days)
    end = max(d for d in days if d <= today)
    items = secs if codes is None else secs[secs['code'].isin(codes)]
    args = [(r.code, r.start_date, r.end_date, r.type == 'index', end) for r in items.itertuples()]
    log.info('回测数据同步开始：%d 只证券，截至 %s，%d 个进程', len(args), end, workers)

    changed, failed, added = None, [], 0
    with ProcessPoolExecutor(workers, initializer=_init_worker) as pool:
        futures = [pool.submit(sync_one, *a) for a in args]
        for n, fut in enumerate(futures, 1):
            code, rows, first, error = fut.result()
            if error:
                failed.append(code)
                log.warning('同步 %s 失败：%s', code, error)
            elif rows:
                added += rows
                changed = min(changed, first) if changed else first
            if n % 200 == 0:
                log.info('同步进度：%d / %d，新增 %d 行，失败 %d 只，已用 %.0f 分钟', n, len(args), added,
                         len(failed), (time.monotonic() - started) / 60)
    log.info('日线同步完成：新增 %d 行，失败 %d 只', added, len(failed))

    if codes is None:
        sync_members(days, end)
    benchmark = store.read_raw('000001.XSHG')  # 上证指数每个交易日都有数据，以它的最后日期为数据截止日
    last = benchmark['date'].iloc[-1].date() if benchmark is not None and not benchmark.empty else end
    rebuild = not (store.root() / 'panel' / 'codes.json').is_file()
    if changed or rebuild:
        first_year = start.year if rebuild else changed.year
        store.build_panel(range(first_year, last.year + 1), days, last, log)
    complete = codes is None and len(failed) <= max(10, len(args) // 100)
    state.update({
        'ready': bool(state.get('ready') or complete),
        'start': config.QUANT_START, 'last_date': last.isoformat(),
        'securities': int((secs['type'] == 'stock').sum()), 'failed': failed[:50],
        'synced_at': tradecal.now().isoformat(' ', 'seconds'),
    })
    store.save_state(state)
    log.info('回测数据同步结束：数据截至 %s，耗时 %.0f 分钟', last, (time.monotonic() - started) / 60)
    return state


def rebuild():
    """按现有 raw 重新生成全部宽表（调整规则或宽表损坏时使用）。"""
    days = store.load_trade_days()
    state = store.load_state()
    last = datetime.date.fromisoformat(state['last_date']) if state.get('last_date') else max(days)
    start = datetime.date.fromisoformat(config.QUANT_START)
    store.build_panel(range(start.year, last.year + 1), days, last, log)
