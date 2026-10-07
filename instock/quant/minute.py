"""分钟数据：通达信历史分时（每分钟收盘价与成交量）的本地仓库、同步与分钟 K 线构造。

minute/<代码>/<年>.npz：dates int32[n]（yyyymmdd）、price float32[n,240]（不复权收盘价）、volume int32[n,240]（手）。
分时没有分钟内的开高低：分钟 K 线的开盘价取上一分钟收盘价（每天第一根取当日开盘价），最高/最低取开收中的较大/较小值，
成交额按收盘价 × 成交量估算。

同步只抓本地日线显示“当天有成交”的交易日；每天的最后一分钟价格须等于日线收盘价，否则视为异常数据丢弃。
回补与增量是同一个过程，按股票、按年保存，中断后重跑从断点继续。
"""
import datetime
import logging
import os
import queue
import threading
import time
from collections import OrderedDict

import numpy as np
import pandas as pd

from instock import config, tradecal
from instock.quant import store
from instock.sources import tdxhq

log = logging.getLogger(__name__)

MINUTES = tdxhq.MINUTES
# 第 k 个分时点（k=0..239）的时刻（分钟数）：09:31~11:30、13:01~15:00
POINT_MINUTE = np.concatenate([np.arange(571, 691), np.arange(781, 901)])


def point_index(minute):
    """当天 minute 时刻（含）之前最后一个已走完的分时点序号；09:31 之前返回 -1。"""
    return int(np.searchsorted(POINT_MINUTE, minute, side='right')) - 1


def _dir(code):
    return store.root() / 'minute' / code


def _path(code, year):
    return _dir(code) / f'{year}.npz'


def load(code, year):
    try:
        with np.load(_path(code, year)) as f:
            return {'dates': f['dates'], 'price': f['price'], 'volume': f['volume']}
    except FileNotFoundError:
        return None


def save(code, year, dates, price, volume):
    order = np.argsort(dates)
    path = _path(code, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, dates=np.asarray(dates, dtype=np.int32)[order],
                            price=np.asarray(price, dtype=np.float32)[order],
                            volume=np.asarray(volume, dtype=np.int32)[order])
    os.replace(tmp, path)


def coverage():
    """已有分钟数据的股票数与最早、最晚日期（读取状态文件，不扫描目录）。"""
    return store.load_state().get('minute') or {}


class Cache:
    """回测进程内的分钟数据缓存：按（股票, 年）加载，最多保留 limit 份。"""

    def __init__(self, limit=400):
        self.limit = limit
        self._data = OrderedDict()

    def day(self, code, day):
        """某股票某天的 (收盘价[240], 成交量手[240])；没有数据返回 None。"""
        key = (code, day.year)
        entry = self._data.get(key)
        if entry is None:
            raw = load(code, day.year)
            entry = (raw, {int(d): i for i, d in enumerate(raw['dates'])}) if raw is not None else (None, {})
            self._data[key] = entry
            if len(self._data) > self.limit:
                self._data.popitem(last=False)
        else:
            self._data.move_to_end(key)
        raw, index = entry
        i = index.get(day.year * 10000 + day.month * 100 + day.day)
        if i is None:
            return None
        return raw['price'][i].astype(float), raw['volume'][i].astype(np.int64)


def bars_for_day(price, volume, day_open):
    """一天的分时点 -> 1 分钟 K 线字段（数组长度 240）。"""
    open_ = np.concatenate([[day_open], price[:-1]])
    vol = volume * 100.0
    return {'open': open_, 'close': price, 'high': np.maximum(open_, price), 'low': np.minimum(open_, price),
            'volume': vol, 'money': vol * price}


# ---------- 同步 ----------

def universe(scope):
    """index：2015 年以来沪深300、中证500 的全部历史成分；all：全部 A 股；也可直接传代码列表。"""
    if not isinstance(scope, str):
        return sorted(scope)
    secs = store.load_securities()
    if scope == 'all':
        return sorted(secs.loc[secs['type'] == 'stock', 'code'])
    members = store.load_members()
    codes = set()
    for codes_ in members[members['index'].isin(['000300.XSHG', '000905.XSHG'])]['codes']:
        codes.update(codes_)
    return sorted(codes)


def _plan(code, start, end):
    """需要抓取的 {年: [日期...]}：日线中有成交、且本地还没有分钟数据的交易日；同时返回这些日期的日线收盘价。"""
    raw = store.read_raw(code)
    if raw is None or raw.empty:
        return {}, {}
    raw = raw[(raw['paused'] == 0) & (raw['volume'] > 0)]
    dates = raw['date'].dt.date
    raw = raw[(dates >= start) & (dates <= end)]
    closes = dict(zip(raw['date'].dt.date, raw['close']))
    plan = {}
    for day in closes:
        plan.setdefault(day.year, []).append(day)
    for year in list(plan):
        have = load(code, year)
        if have is not None:
            done = set(have['dates'].tolist())
            plan[year] = [d for d in plan[year] if d.year * 10000 + d.month * 100 + d.day not in done]
        if not plan[year]:
            del plan[year]
    return plan, closes


class _Hosts:
    """服务器轮换：连接失败或出错的服务器冷却 10 分钟。"""

    def __init__(self, hosts):
        self._hosts = list(hosts)
        self._bad = {}
        self._next = 0
        self._lock = threading.Lock()

    def pick(self):
        with self._lock:
            now = time.monotonic()
            for _ in range(len(self._hosts)):
                host = self._hosts[self._next % len(self._hosts)]
                self._next += 1
                if self._bad.get(host, 0) <= now:
                    return host
        time.sleep(5)
        return self.pick()

    def bad(self, host):
        with self._lock:
            self._bad[host] = time.monotonic() + 600


def _fetch_day(client, hosts, code, day):
    """抓一天，出错时换服务器重试，最多 3 次。返回 (client, 结果)：结果为 False 表示出错，None 表示各服务器都没有数据。
    只会请求日线显示有成交的日期，所以空结果也换服务器再试（个别服务器会缺某些日期）。"""
    empty = False
    for attempt in range(3):
        try:
            if client.sock is None:
                client = tdxhq.Client(hosts.pick()).connect()
            got = client.minutes(code, day)
            if got is not None:
                return client, got
            empty = True
            log.debug('%s %s 在 %s 上没有数据，换服务器重试', code, day, client.host[0])
        except (OSError, tdxhq.TdxError, ValueError) as e:
            log.debug('%s %s 第 %d 次失败（%s）：%s', code, day, attempt + 1, client.host[0], e)
            hosts.bad(client.host)
        client.close()
        client = tdxhq.Client(hosts.pick())
    return client, None if empty else False


def sync(scope='index', start=None, connections=8, end=None):
    """同步分钟数据。scope 见 universe()；start 默认 config.QUANT_MINUTE_START。"""
    started = time.monotonic()
    start = datetime.date.fromisoformat(start or config.QUANT_MINUTE_START)
    state = store.load_state()
    if not state.get('last_date'):
        raise RuntimeError('请先运行 python -m instock quant sync 同步日线数据')
    end = end or datetime.date.fromisoformat(state['last_date'])
    codes = universe(scope)
    log.info('分钟数据同步开始：%d 只股票，%s ~ %s，%d 个连接', len(codes), start, end, connections)
    hosts = _Hosts(tdxhq.HOSTS)
    tasks = queue.Queue()
    for code in codes:
        tasks.put(code)
    totals = {'stocks': 0, 'days': 0, 'calls': 0, 'mismatch': 0, 'failed': 0, 'empty': 0}
    lock = threading.Lock()

    def worker():
        client = tdxhq.Client(hosts.pick())
        while True:
            try:
                code = tasks.get_nowait()
            except queue.Empty:
                break
            plan, closes = _plan(code, start, end)
            for year, days in plan.items():
                existing = load(code, year)
                dates, prices, volumes = [], [], []
                for day in days:
                    client, got = _fetch_day(client, hosts, code, day)
                    with lock:
                        totals['calls'] += 1
                        if got is False:
                            totals['failed'] += 1
                        elif got is None:
                            totals['empty'] += 1
                    if not got:
                        continue
                    price, volume = got
                    if abs(price[-1] - closes[day]) > 0.006:
                        with lock:
                            totals['mismatch'] += 1
                        continue
                    dates.append(day.year * 10000 + day.month * 100 + day.day)
                    prices.append(price)
                    volumes.append(volume)
                if dates:
                    if existing is not None:
                        dates = np.concatenate([existing['dates'], dates])
                        prices = np.concatenate([existing['price'], np.array(prices, dtype=np.float32)])
                        volumes = np.concatenate([existing['volume'], np.array(volumes, dtype=np.int32)])
                    save(code, year, dates, prices, volumes)
                    with lock:
                        totals['days'] += len(dates) - (len(existing['dates']) if existing is not None else 0)
            with lock:
                totals['stocks'] += 1
                n = totals['stocks']
            if n % 20 == 0:
                elapsed = time.monotonic() - started
                log.info('分钟数据：%d / %d 只，新增 %d 天，%.0f 次/秒，异常 %d，失败 %d，预计还需 %.0f 分钟',
                         n, len(codes), totals['days'], totals['calls'] / elapsed, totals['mismatch'], totals['failed'],
                         elapsed / n * (len(codes) - n) / 60)
        client.close()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(connections)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    state = store.load_state()
    previous = state.get('minute') or {}
    state['minute'] = {
        'scope': scope if isinstance(scope, str) else 'custom',
        'start': min(start.isoformat(), previous.get('start') or start.isoformat()),
        'end': end.isoformat(), 'stocks': max(len(codes), previous.get('stocks') or 0),
        'synced_at': tradecal.now().isoformat(' ', 'seconds'),
    }
    store.save_state(state)
    log.info('分钟数据同步结束：%d 只股票，新增 %d 天，与日线不符 %d，无数据 %d，失败 %d，耗时 %.0f 分钟', len(codes),
             totals['days'], totals['mismatch'], totals['empty'], totals['failed'], (time.monotonic() - started) / 60)
    return totals


def frame_for_day(cache, code, day, day_open):
    """一天的 1 分钟 K 线 DataFrame（索引为每分钟结束时刻）；没有数据返回 None。"""
    got = cache.day(code, day)
    if got is None:
        return None
    bars = bars_for_day(*got, day_open)
    base = pd.Timestamp(day)
    index = pd.DatetimeIndex([base + pd.Timedelta(minutes=int(m)) for m in POINT_MINUTE])
    return pd.DataFrame(bars, index=index)
