"""Web 服务：JSON API + 前端单页应用。数据库查询和计算都放到线程池，事件循环不被阻塞。"""
import datetime
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa
import tornado.ioloop
import tornado.web

from instock import __version__, config, db, history, net, schema
from instock.analysis import indicators, patterns
from instock.analysis.strategies import BY_KEY, STRATEGIES

log = logging.getLogger(__name__)

DIST_DIR = Path(__file__).resolve().parent / 'dist'
_pool = ThreadPoolExecutor(8, thread_name_prefix='api')
_KLINE_BARS = 500  # 返回的 K 线根数（展示 + 筹码分布回看）
_MA_PERIODS = (5, 10, 20, 60, 120, 250)


def _clean(value):
    """转成可 JSON 序列化的值：NaN/Inf 为 null，日期为 ISO 字符串。"""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bytes):  # 旧版建表用的 MySQL BIT 列
        return any(value)
    if isinstance(value, float):
        # 保留 4 位小数：MySQL FLOAT 读出的单精度噪声（如 12.3456001）会显著增大响应体
        return None if math.isnan(value) or math.isinf(value) else round(value, 4)
    if isinstance(value, datetime.datetime):
        return value.isoformat(' ')
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def _records(df):
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict('records')]


def _round_list(arr, digits=3):
    return [None if not np.isfinite(v) else round(float(v), digits) for v in arr]


class _TTLCache:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get_or_set(self, key, ttl, build):
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > now:
                return hit[1]
        value = build()
        with self._lock:
            self._data[key] = (now + ttl, value)
        return value

    def clear(self):
        with self._lock:
            self._data.clear()


_cache = _TTLCache()


class ApiHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json; charset=utf-8')
        self.set_header('Cache-Control', 'no-cache')

    async def call(self, fn, *args):
        return await tornado.ioloop.IOLoop.current().run_in_executor(_pool, fn, *args)

    def send(self, payload):
        self.finish(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), default=_clean))

    def write_error(self, status_code, **kwargs):
        message = self._reason
        if 'exc_info' in kwargs and isinstance(kwargs['exc_info'][1], tornado.web.HTTPError):
            message = kwargs['exc_info'][1].log_message or message
        self.finish(json.dumps({'error': message}, ensure_ascii=False))

    def day_arg(self):
        value = self.get_argument('date', None)
        if not value:
            return None
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            raise tornado.web.HTTPError(400, '日期格式应为 YYYY-MM-DD') from None


def _spec(name):
    spec = schema.TABLES.get(name)
    if spec is None or spec.group is None:
        raise tornado.web.HTTPError(404, f'没有数据表 {name}')
    return spec


def _dates(table, limit=250):
    return [d for (d,) in db.query(sa.select(table.c.date).distinct().order_by(table.c.date.desc()).limit(limit))[1]]


def _attention_codes():
    table = schema.SA_TABLES[schema.ATTENTION.name]
    return [code for (code,) in db.query(sa.select(table.c.code).order_by(table.c.created_at.desc()))[1]]


def _table_payload(name, day):
    spec = _spec(name)
    table = schema.SA_TABLES[name]
    dates = _dates(table)
    day = day or (dates[0] if dates else None)
    columns, rows = db.query(sa.select(table).where(table.c.date == day)) if day else (spec.names, [])
    return {
        'name': name, 'label': spec.label, 'date': day, 'dates': dates, 'sort': spec.sort,
        'columns': [{'name': c.name, 'label': c.label, 'fmt': c.fmt} for c in spec.cols],
        'rows': [[_clean(v) for v in row] for row in rows],
    }


class MetaHandler(ApiHandler):
    def get(self):
        groups = {}
        for spec in schema.TABLES.values():
            if spec.group:
                groups.setdefault(spec.group, []).append({'name': spec.name, 'label': spec.label})
        self.send({
            'version': __version__,
            'menu': [{'group': g, 'tables': items} for g, items in groups.items()],
            'strategies': [{'key': s.key, 'name': s.name, 'kind': s.kind, 'rule': s.rule, 'source': s.source,
                            'plain': s.plain, 'tips': s.tips, 'basis': 'fundamental' if s.screen else 'technical'}
                           for s in STRATEGIES],
            'horizons': schema.RETURN_HORIZONS,
            'patterns': [{'key': key, 'label': label} for key, label, _ in patterns.PATTERNS],
        })


class TableHandler(ApiHandler):
    async def get(self, name):
        day = self.day_arg()
        payload = await self.call(_cache.get_or_set, ('table', name, day), 60, lambda: _table_payload(name, day))
        self.send(payload)


def _signals_payload(day, strategy=None):
    table = schema.SA_TABLES[schema.SIGNAL.name]
    dates = _dates(table)
    day = day or (dates[0] if dates else None)
    query = sa.select(table).where(table.c.date == day)
    if strategy:
        query = query.where(table.c.strategy == strategy)
    columns, rows = db.query(query) if day else ([], [])
    return {'date': day, 'dates': dates,
            'columns': [{'name': c.name, 'label': c.label, 'fmt': c.fmt} for c in schema.SIGNAL.cols],
            'rows': [[_clean(v) for v in row] for row in rows]}


class SignalHandler(ApiHandler):
    async def get(self):
        day = self.day_arg()
        strategy = self.get_argument('strategy', None)
        if strategy and strategy not in BY_KEY:
            raise tornado.web.HTTPError(404, f'没有策略 {strategy}')
        self.send(await self.call(_cache.get_or_set, ('signals', day, strategy), 60,
                                  lambda: _signals_payload(day, strategy)))


def _round(value, digits):
    return None if value is None or pd.isna(value) else round(float(value), digits)


def _backtest_payload():
    """各策略在各持有期的样本数、平均/中位收益、胜率，以及相对全市场等权基准的平均超额收益。"""
    cols = [f'ret_{h}' for h in schema.RETURN_HORIZONS]
    df = db.read(f'SELECT date, strategy, {", ".join(cols)} FROM {schema.SIGNAL.name}')
    bench = db.read(f'SELECT date, {", ".join(cols)} FROM {schema.BENCHMARK.name}')
    for frame in (df, bench):
        frame['date'] = pd.to_datetime(frame['date']).dt.date
        frame[cols] = frame[cols].apply(pd.to_numeric, errors='coerce')
    df = df.merge(bench, on='date', how='left', suffixes=('', '_bench'))
    result = []
    for key, group in df.groupby('strategy'):
        stats = []
        for col, h in zip(cols, schema.RETURN_HORIZONS):
            r = group[col].dropna()
            excess = (group[col] - group[f'{col}_bench']).dropna()
            stats.append({'horizon': h, 'n': int(r.size), 'mean': _round(r.mean(), 3),
                          'median': _round(r.median(), 3), 'win': _round((r > 0).mean() * 100, 1) if r.size else None,
                          'excess': _round(excess.mean(), 3)})
        result.append({'strategy': key, 'name': BY_KEY[key].name if key in BY_KEY else key,
                       'signals': int(len(group)), 'days': int(group['date'].nunique()), 'stats': stats})
    days = bench[bench['date'].isin(set(df['date']))]
    benchmark = [{'horizon': h, 'mean': _round(days[col].mean(), 3), 'n': int(days[col].notna().sum())}
                 for col, h in zip(cols, schema.RETURN_HORIZONS)]
    return {'horizons': schema.RETURN_HORIZONS, 'strategies': result, 'benchmark': benchmark}


class BacktestHandler(ApiHandler):
    async def get(self):
        self.send(await self.call(_cache.get_or_set, ('backtest',), 300, _backtest_payload))


def _latest_spot():
    table = schema.SA_TABLES[schema.STOCK_SPOT.name]
    day = db.scalar(sa.select(sa.func.max(table.c.date)))
    if day is None:
        return None, pd.DataFrame(columns=schema.STOCK_SPOT.names)
    return day, db.read(f'SELECT * FROM {schema.STOCK_SPOT.name} WHERE date = :d', d=day)


def _limit_pct(code, name):
    if str(name).upper().startswith(('ST', '*ST')):
        return 5
    return 20 if str(code).startswith(('300', '301')) else 10


def _overview_payload():
    day, spot = _latest_spot()
    payload = {'date': day, 'market': None, 'gainers': [], 'losers': [], 'active': [], 'industry': [],
               'signals': [], 'attention': []}
    if day is not None and not spot.empty:
        chg = pd.to_numeric(spot['change_rate'], errors='coerce')
        limit = np.array([_limit_pct(c, n) for c, n in zip(spot['code'], spot['name'])])
        bins = [-np.inf, -7, -5, -3, -1, -1e-9, 1e-9, 1, 3, 5, 7, np.inf]
        labels = ['<-7', '-7~-5', '-5~-3', '-3~-1', '-1~0', '0', '0~1', '1~3', '3~5', '5~7', '>7']
        hist = pd.cut(chg, bins=bins, labels=labels).value_counts().reindex(labels).fillna(0).astype(int)
        payload['market'] = {
            'total': int(chg.notna().sum()), 'up': int((chg > 0).sum()), 'down': int((chg < 0).sum()),
            'flat': int((chg == 0).sum()), 'limit_up': int((chg >= limit - 0.1).sum()),
            'limit_down': int((chg <= -limit + 0.1).sum()),
            'amount': float(pd.to_numeric(spot['deal_amount'], errors='coerce').sum()),
            'median_change': _clean(float(chg.median())),
            'distribution': [{'label': k, 'count': int(v)} for k, v in hist.items()],
        }
        cols = ['code', 'name', 'new_price', 'change_rate', 'deal_amount', 'turnoverrate']
        brief = spot[cols].assign(change_rate=chg)
        brief = brief.assign(deal_amount=pd.to_numeric(brief['deal_amount'], errors='coerce'))
        payload['gainers'] = _records(brief.nlargest(10, 'change_rate'))
        payload['losers'] = _records(brief.nsmallest(10, 'change_rate'))
        payload['active'] = _records(brief.nlargest(10, 'deal_amount'))
        codes = _attention_codes()
        if codes:
            payload['attention'] = _records(brief[brief['code'].isin(codes)])
    industry = schema.SA_TABLES[schema.FUND_FLOW_INDUSTRY.name]
    flow_day = db.scalar(sa.select(sa.func.max(industry.c.date)))
    if flow_day:
        flow = db.read(f'SELECT name, change_rate, fund_amount FROM {industry.name} WHERE date = :d', d=flow_day)
        flow = flow.dropna(subset=['fund_amount']).sort_values('fund_amount')
        payload['industry'] = {'date': flow_day, 'inflow': _records(flow.tail(10)[::-1]),
                               'outflow': _records(flow.head(10))}
    signal = schema.SA_TABLES[schema.SIGNAL.name]
    signal_day = db.scalar(sa.select(sa.func.max(signal.c.date)))
    if signal_day:
        _, rows = db.query(sa.select(signal.c.strategy, sa.func.count()).where(signal.c.date == signal_day)
                           .group_by(signal.c.strategy))
        counts = dict(rows)
        payload['signals'] = {'date': signal_day, 'items': [
            {'key': s.key, 'name': s.name, 'kind': s.kind, 'count': counts.get(s.key, 0)} for s in STRATEGIES]}
    return payload


class OverviewHandler(ApiHandler):
    async def get(self):
        self.send(await self.call(_cache.get_or_set, ('overview',), 60, _overview_payload))


def _lookup_name(code):
    for spec in (schema.STOCK_SPOT, schema.ETF_SPOT):
        name = db.scalar(f'SELECT name FROM {spec.name} WHERE code = :c ORDER BY date DESC LIMIT 1', c=code)
        if name:
            return name
    return None


def _kline_payload(code):
    df = history.get(code)
    if df is None or df.empty:
        raise tornado.web.HTTPError(404, f'没有 {code} 的行情数据')
    o, h, l, c, v = (df[k].to_numpy(dtype=float) for k in ('open', 'high', 'low', 'close', 'volume'))
    ind = indicators.compute(o, h, l, c, v)
    pats = patterns.detect(o, h, l, c)
    start = max(0, len(df) - _KLINE_BARS)
    tail = df.iloc[start:]
    labels = {key: label for key, label, _ in patterns.PATTERNS}
    marks = [{'i': int(i - start), 'key': key, 'label': labels[key], 'value': int(arr[i])}
             for key, arr in pats.items() for i in np.flatnonzero(arr[start:]) + start]
    return {
        'code': code,
        'name': _lookup_name(code),
        'dates': tail['date'].dt.strftime('%Y-%m-%d').tolist(),
        'open': _round_list(o[start:]), 'high': _round_list(h[start:]), 'low': _round_list(l[start:]),
        'close': _round_list(c[start:]), 'volume': _round_list(v[start:] / 100, 0),  # 股 -> 手
        'amount': _round_list(tail['amount'].to_numpy(dtype=float), 0),
        'turnover': _round_list(tail['turnover'].to_numpy(dtype=float)),
        'ma': {f'ma{n}': _round_list(indicators.ma(c, n)[start:]) for n in _MA_PERIODS},
        'vol_ma': {f'ma{n}': _round_list(indicators.ma(v / 100, n)[start:], 0) for n in (5, 10)},
        'indicators': {k: _round_list(arr[start:], 4) for k, arr in ind.items()},
        'patterns': marks,
        'attention': code in _attention_codes(),
    }


class KlineHandler(ApiHandler):
    async def get(self, code):
        try:
            payload = await self.call(_cache.get_or_set, ('kline', code), 60, lambda: _kline_payload(code))
        except net.FetchError as e:
            raise tornado.web.HTTPError(502, f'行情获取失败：{e}') from e
        self.send(payload)


def _attention_payload():
    codes = _attention_codes()
    quotes = {}
    for spec in (schema.ETF_SPOT, schema.STOCK_SPOT):
        table = schema.SA_TABLES[spec.name]
        day = db.scalar(sa.select(sa.func.max(table.c.date)))
        if day is None or not codes:
            continue
        _, rows = db.query(sa.select(table.c.code, table.c.name, table.c.new_price, table.c.change_rate,
                                     table.c.turnoverrate, table.c.deal_amount)
                           .where(table.c.date == day, table.c.code.in_(codes)))
        for r in rows:
            quotes[r[0]] = {'code': r[0], 'name': r[1], 'new_price': r[2], 'change_rate': r[3],
                            'turnoverrate': r[4], 'deal_amount': r[5], 'date': day}
    return {'codes': codes, 'items': [quotes.get(c, {'code': c}) for c in codes]}


class AttentionHandler(ApiHandler):
    async def get(self):
        self.send(await self.call(_attention_payload))

    async def put(self, code):
        table = schema.SA_TABLES[schema.ATTENTION.name]

        def add():
            db.execute(table.delete().where(table.c.code == code))
            db.execute(table.insert().values(code=code, created_at=datetime.date.today()))
        await self.call(add)
        _cache.clear()
        self.send({'ok': True})

    async def delete(self, code):
        table = schema.SA_TABLES[schema.ATTENTION.name]
        await self.call(lambda: db.execute(table.delete().where(table.c.code == code)))
        _cache.clear()
        self.send({'ok': True})


def _search(q):
    q = q.strip()
    if not q:
        return []
    results = []
    for spec, kind in ((schema.STOCK_SPOT, '股票'), (schema.ETF_SPOT, 'ETF')):
        table = schema.SA_TABLES[spec.name]
        day = db.scalar(sa.select(sa.func.max(table.c.date)))
        if day is None:
            continue
        cond = table.c.code.startswith(q) if q.isdigit() else table.c.name.contains(q)
        _, rows = db.query(sa.select(table.c.code, table.c.name, table.c.new_price, table.c.change_rate)
                           .where(table.c.date == day, cond).limit(20))
        results += [{'code': r[0], 'name': r[1], 'price': r[2], 'change': r[3], 'kind': kind} for r in rows]
    return results[:20]


class SearchHandler(ApiHandler):
    async def get(self):
        self.send({'items': await self.call(_search, self.get_argument('q', ''))})


class SpaHandler(tornado.web.RequestHandler):
    """前端路由由浏览器端处理，未匹配的路径都返回 index.html。"""

    def get(self, *_):
        index = DIST_DIR / 'index.html'
        if not index.is_file():
            self.set_status(503)
            self.finish('前端尚未构建：cd frontend && npm install && npm run build')
            return
        self.set_header('Cache-Control', 'no-cache')
        self.finish(index.read_bytes())

    head = get  # 探活常用 HEAD；Tornado 会自动丢弃 HEAD 的响应体


def make_app():
    return tornado.web.Application([
        (r'/api/meta', MetaHandler),
        (r'/api/overview', OverviewHandler),
        (r'/api/tables/(\w+)', TableHandler),
        (r'/api/signals', SignalHandler),
        (r'/api/backtest', BacktestHandler),
        (r'/api/kline/(\d{6})', KlineHandler),
        (r'/api/attention', AttentionHandler),
        (r'/api/attention/(\d{6})', AttentionHandler),
        (r'/api/search', SearchHandler),
        (r'/assets/(.*)', tornado.web.StaticFileHandler, {'path': DIST_DIR / 'assets'}),
        (r'/(favicon\.svg)', tornado.web.StaticFileHandler, {'path': DIST_DIR}),
        (r'/.*', SpaHandler),
    ], compress_response=True)


def main():
    db.init()
    make_app().listen(config.WEB_PORT, config.WEB_HOST)
    log.info('Web 服务已启动：http://localhost:%d/', config.WEB_PORT)
    tornado.ioloop.IOLoop.current().start()
