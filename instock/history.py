"""日 K 线本地缓存（前复权，数据源为腾讯）。

首次全量抓取近几年数据；之后每个交易日用收盘行情直接追加一根 K 线，不再请求历史接口。
当缓存最后收盘价与当日“昨收”不一致（除权除息导致前复权价变化）或缓存断档时，自动重新全量抓取。
只缓存已收盘的 K 线，盘中抓到的当日 K 线只用于展示。
"""
import datetime
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from instock import config, net, tradecal
from instock.sources import tencent

log = logging.getLogger(__name__)

COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'turnover']  # 量：股，额：元，换手：%
_MIN_HISTORY_DAYS = 400  # 策略最长需要约 260 根 K 线


def _path(code):
    return config.HIST_DIR / f'{code}.pkl'


def load(code):
    try:
        return pd.read_pickle(_path(code))
    except FileNotFoundError:
        return None
    except Exception as e:
        log.warning('K 线缓存 %s 损坏，将重新抓取：%s', code, e)
        return None


def _save(code, df):
    config.HIST_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(code).with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
    df.to_pickle(tmp)
    os.replace(tmp, _path(code))  # 原子替换，Web 与作业进程可同时读写


def _normalize(df):
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    for col in COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors='coerce') if col in df.columns else np.nan
    df['volume'] = df['volume'] * 100  # 手 -> 股
    return df[COLUMNS].dropna(subset=['open', 'close']).drop_duplicates('date').sort_values('date', ignore_index=True)


def fetch(code, start, end=None):
    """抓取前复权日 K 线（腾讯）。attrs['start'] 记录数据完整覆盖的起点：
    上市晚于 start 的股票也视为从 start 起完整，避免反复重抓。"""
    df = _normalize(tencent.kline(code, start, end))
    df.attrs['start'] = start
    return df


def refresh(code, as_of=None):
    """重新抓取并写缓存，返回含盘中 K 线的完整数据。"""
    cal = tradecal.get()
    as_of = as_of or cal.current_session()
    df = fetch(code, as_of - datetime.timedelta(days=365 * config.HIST_YEARS))
    closed = pd.Timestamp(cal.closed_session())
    if not df.empty:
        done = df[df['date'] <= closed]
        done.attrs = dict(df.attrs)
        _save(code, done)
    return df


def get(code):
    """供页面展示：缓存已覆盖最近交易日则直接返回，否则重新抓取。"""
    df = load(code)
    current = tradecal.get().current_session()
    if df is not None and not df.empty and df['date'].iloc[-1].date() >= current:
        return df
    return refresh(code, current)


def _covered(df, as_of, earliest):
    start = min(df['date'].iloc[0].date(), df.attrs.get('start', datetime.date.max))
    return df['date'].iloc[-1].date() >= as_of and start <= earliest - datetime.timedelta(days=_MIN_HISTORY_DAYS)


def _spot_bar(row, day):
    return {'date': pd.Timestamp(day), 'open': row.open_price, 'high': row.high_price, 'low': row.low_price,
            'close': row.new_price, 'volume': row.volume * 100, 'amount': row.deal_amount,
            'turnover': row.turnoverrate}


def ensure(codes, as_of, spot=None, earliest=None):
    """确保 codes 的缓存覆盖 [earliest, as_of]（含足够的预热数据）。
    spot 为 as_of 收盘后抓取的行情时，能接上的直接追加，其余重新抓取。"""
    earliest = earliest or as_of
    cal = tradecal.get()
    prev_day = cal.prev(as_of)
    fetched_at = spot.attrs.get('fetched_at') if spot is not None else None
    usable = (fetched_at is not None and fetched_at.date() == as_of and fetched_at.time() >= tradecal.CLOSE_TIME)
    bars = spot.drop_duplicates('code').set_index('code') if usable else None

    appended, stale = 0, []
    for code in codes:
        df = load(code)
        if df is not None and not df.empty:
            if _covered(df, as_of, earliest):
                continue
            if bars is not None and code in bars.index and df['date'].iloc[-1].date() == prev_day:
                row = bars.loc[code]
                if row.volume > 0 and abs(row.pre_close_price - df['close'].iloc[-1]) <= 0.006:
                    new = pd.concat([df, pd.DataFrame([_spot_bar(row, as_of)])], ignore_index=True)
                    new.attrs = dict(df.attrs)
                    _save(code, new)
                    appended += 1
                    continue
        stale.append(code)

    started = time.monotonic()
    failed = 0
    if stale:
        log.info('K 线缓存：%d 只追加当日数据，%d 只需重新抓取', appended, len(stale))

        def work(code):
            try:
                refresh(code, as_of)
                return True
            except net.FetchError as e:
                log.warning('抓取 %s 历史 K 线失败：%s', code, e)
                return False

        # 线程数只是上限，实际速率由数据源限流控制
        with ThreadPoolExecutor(8) as pool:
            for done, ok in enumerate(pool.map(work, stale), 1):
                failed += not ok
                if done % 500 == 0:  # 首次部署要抓全部股票，耗时十几分钟，定期报告进度
                    log.info('K 线抓取进度：%d/%d', done, len(stale))
    log.info('K 线缓存就绪：追加 %d，重新抓取 %d（失败 %d），耗时 %.0f 秒',
             appended, len(stale), failed, time.monotonic() - started)


def prune(days=30):
    """删除 days 天未更新的缓存（退市股、偶尔查看的 ETF 等）。"""
    deadline = time.time() - days * 86400
    removed = 0
    for path in config.HIST_DIR.glob('*'):
        if path.stat().st_mtime < deadline:
            path.unlink(missing_ok=True)
            removed += 1
    if removed:
        log.info('清理过期 K 线缓存 %d 个', removed)
