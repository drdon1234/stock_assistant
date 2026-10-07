"""聚宽 API 兼容层：把聚宽策略代码里直接使用的全局函数、类与对象映射到回测引擎。

只支持日线（frequency='daily' / unit='1d'）。没有数据支撑的函数（财务数据、行业概念、分钟线等）调用时抛出
NotSupported 并说明原因；check.py 会在运行前静态扫描出这些调用。
"""
import builtins
import datetime
import math
import sys
import types

import numpy as np
import pandas as pd

from instock.quant import engine
from instock.quant import minute
from instock.quant.engine import NotSupported, StrategyError, normalize_code, to_date

_DEFAULT_FIELDS = ['open', 'close', 'high', 'low', 'volume', 'money']
_PRICE_LIKE = {'open', 'close', 'high', 'low', 'high_limit', 'low_limit', 'pre_close', 'avg', 'price'}
_ALL_FIELDS = _PRICE_LIKE | {'volume', 'money', 'factor', 'paused'}
_INDEX_NAMES = {'000300.XSHG': '沪深300', '000016.XSHG': '上证50', '000905.XSHG': '中证500'}

# 已知但不支持的聚宽函数 -> 原因
UNSUPPORTED = {
    'get_fundamentals': '没有历史财务与估值数据', 'get_fundamentals_continuously': '没有历史财务与估值数据',
    'get_history_fundamentals': '没有历史财务数据', 'get_valuation': '没有历史估值数据',
    'query': '没有财务数据库（query 用于 get_fundamentals）', 'run_query': '没有聚宽数据库表',
    'get_industry': '没有行业分类历史', 'get_industry_stocks': '没有行业分类历史', 'get_industries': '没有行业分类历史',
    'get_concept_stocks': '没有概念板块数据', 'get_concept': '没有概念板块数据', 'get_concepts': '没有概念板块数据',
    'get_index_weights': '没有指数权重数据', 'get_money_flow': '没有历史资金流向', 'get_billboard_list': '没有历史龙虎榜',
    'get_locked_shares': '没有限售解禁数据', 'get_mtss': '没有融资融券数据', 'get_ticks': '没有 tick 数据',
    'get_call_auction': '没有集合竞价数据', 'get_factor_values': '没有因子库', 'get_all_factors': '没有因子库',
    'get_margincash_stocks': '不支持融资融券', 'get_marginsec_stocks': '不支持融资融券',
    'get_dominant_future': '不支持期货', 'get_future_contracts': '不支持期货', 'get_futures_info': '不支持期货',
    'write_file': '回测沙箱不能写文件', 'read_file': '回测沙箱不能读文件', 'send_order': '不支持',
    'inout_cash': '暂不支持出入金', 'transfer_cash': '只有一个账户', 'set_subportfolios': '只支持单个股票账户',
    'margincash_open': '不支持融资融券', 'margincash_close': '不支持融资融券', 'marginsec_open': '不支持融资融券',
    'marginsec_close': '不支持融资融券',
}
# 财务表对象：query(valuation.code, ...) 会先访问其属性
UNSUPPORTED_OBJECTS = ('valuation', 'income', 'balance', 'cash_flow', 'indicator', 'finance', 'macro', 'opt',
                       'bond', 'jy', 'sup', 'alpha101', 'alpha191', 'technical_analysis')


def _unsupported(name, reason):
    def fn(*args, **kwargs):
        raise NotSupported(f'暂不支持聚宽函数 {name}：{reason}')
    fn.__name__ = name
    return fn


class _UnsupportedObject:
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        raise NotSupported(f'暂不支持 {self._name}.{attr}：没有聚宽财务/扩展数据库')


class _Log:
    def __init__(self, bt):
        self._bt = bt

    def _write(self, level, args):
        self._bt.log(level, ' '.join(str(a) for a in args))

    def debug(self, *args):
        self._write('DEBUG', args)

    def info(self, *args):
        self._write('INFO', args)

    def warn(self, *args):
        self._write('WARN', args)

    warning = warn

    def error(self, *args):
        self._write('ERROR', args)

    critical = error

    def set_level(self, *args, **kwargs):
        pass


class _Info:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f'{type(self).__name__}({self.__dict__})'


class _CurrentData(dict):
    def __init__(self, api):
        super().__init__()
        self._api = api

    def __missing__(self, key):
        bt = self._api.bt
        code = normalize_code(key)
        close = bt.bar('close', code)
        listed = not math.isnan(close)
        value = self[key] = _Info(
            last_price=bt.current_price(code), high_limit=bt.bar('high_limit', code),
            low_limit=bt.bar('low_limit', code), paused=bool(bt.bar('paused', code)) or not listed,
            is_st=bool(bt.bar('is_st', code)), name=bt.security_name(code), industry_code=None,
            day_open=bt.bar('open', code) if bt.minute is not None and bt.minute >= engine.OPEN else np.nan,
            security=code)
        return value


class FieldPanel(dict):
    """多证券 get_price（panel=True）的结果：panel['close'] 为日期×证券的 DataFrame。"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def items(self):  # 兼容旧 Panel 的 .items
        return list(self.keys())


def _as_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return list(value)


_MINUTE_UNITS = {'1m': 1, 'minute': 1, '5m': 5, '15m': 15, '30m': 30, '60m': 60, '120m': 120}
_MINUTE_FIELDS = {'open', 'close', 'high', 'low', 'volume', 'money', 'avg', 'price', 'factor', 'high_limit',
                  'low_limit', 'paused'}


def _bar_minutes(unit):
    """日线返回 None，分钟线返回每根 K 线包含的分钟数。"""
    text = str(unit).lower()
    if text in ('daily', '1d', 'day', 'd'):
        return None
    if text in _MINUTE_UNITS:
        return _MINUTE_UNITS[text]
    raise NotSupported(f'暂不支持 {unit} 周期：可用 daily/1d 与 1m/5m/15m/30m/60m/120m')


class Api:
    """绑定到一次回测的聚宽 API。"""

    def __init__(self, bt):
        self.bt = bt
        self.panel = bt.panel

    # ---------- 行情：内部工具 ----------

    def _fields(self, fields, default):
        fields = default if fields is None else _as_list(fields)
        unknown = [f for f in fields if f not in _ALL_FIELDS]
        if unknown:
            raise StrategyError(f'不支持的字段：{", ".join(unknown)}；可用字段：{", ".join(sorted(_ALL_FIELDS))}')
        return fields

    def _values(self, field, r0, r1, cols, fq, ref_row):
        """取 field 在 [r0, r1) 的值并按 fq 复权（pre：以 ref_row 当天为基准前复权；post：后复权）。"""
        p = self.panel
        if field in ('avg', 'price'):
            money, volume = p.block('money', r0, r1, cols), p.block('volume', r0, r1, cols)
            with np.errstate(invalid='ignore', divide='ignore'):
                v = np.where(volume > 0, money / volume, p.block('close', r0, r1, cols))
        elif field == 'paused':
            v = p.block('paused', r0, r1, cols).astype(float)
        else:
            v = p.block(field, r0, r1, cols)
        if fq not in ('pre', 'post') or field == 'paused':
            return v if field != 'factor' else np.where(np.isnan(v), np.nan, 1.0)
        factor = p.block('factor', r0, r1, cols)
        scale = factor / p.block('factor', ref_row, ref_row + 1, cols)[0] if fq == 'pre' else factor
        if field == 'factor':
            return scale
        if field == 'volume':
            return v / scale
        if field in _PRICE_LIKE:
            return v * scale
        return v

    def _range(self, start_date, end_date, count, limit_row):
        end_row = limit_row if end_date is None else min(self.panel.row(to_date(end_date)), limit_row)
        if count is not None:
            if start_date is not None:
                raise StrategyError('start_date 与 count 只能指定一个')
            return max(end_row + 1 - int(count), 0), end_row + 1
        if start_date is None:
            raise StrategyError('需要指定 start_date 或 count')
        start_row = int(np.searchsorted(self.panel.dates, np.datetime64(to_date(start_date), 'D')))
        return start_row, end_row + 1

    def _skip_paused_rows(self, code, r_end, count):
        """r_end 之前（不含）最近 count 个未停牌交易日的行号。"""
        rows, r1, step = [], r_end, max(count * 2, 30)
        col = [self.panel.col.get(code, -1)]
        while r1 > 0 and len(rows) < count:
            r0 = max(r1 - step, 0)
            paused = self.panel.block('paused', r0, r1, col)[:, 0]
            rows = list(np.arange(r0, r1)[paused == 0]) + rows
            r1 = r0
        return np.array(rows[-count:], dtype=int)

    def _index(self, r0, r1):
        return pd.DatetimeIndex(self.panel.dates[r0:r1], name=None)

    def _ref_row(self):
        return self.bt.r

    # ---------- 分钟线 ----------

    def _minute_cursor(self, end_dt=None):
        """(行号, 当天最后一个可见的分时点序号)，序号为 None 表示当天全部可见。只能看到当前时刻之前走完的 K 线。"""
        bt = self.bt
        m = bt.minute
        if m is None or m < engine.OPEN:
            cursor = (bt.r - 1, None)
        elif m >= engine.CLOSE:
            cursor = (bt.r, None)
        else:
            k = minute.point_index(m)
            cursor = (bt.r, k) if k >= 0 else (bt.r - 1, None)
        if end_dt is not None:
            ts = pd.Timestamp(end_dt)
            row = self.panel.row(ts.date())
            if row >= 0 and pd.Timestamp(self.panel.dates[row]).date() == ts.date():
                # 只有日期时为当天 00:00，不含当天（与聚宽一致）
                k = minute.point_index(ts.hour * 60 + ts.minute)
                end = (row, None if k >= minute.MINUTES - 1 else k) if k >= 0 else (row - 1, None)
            else:
                end = (row, None)
            key = lambda c: (c[0], minute.MINUTES if c[1] is None else c[1])  # noqa: E731
            cursor = min(cursor, end, key=key)
        return cursor

    def _minute_frame(self, code, count, fields, fq, k, cursor, start=None):
        """截至 cursor 往前 count 根（或从 start 起）的 k 分钟 K 线，索引为每根 K 线的结束时刻。"""
        bt, p = self.bt, self.panel
        unknown = [f for f in fields if f not in _MINUTE_FIELDS]
        if unknown:
            raise StrategyError(f'分钟线不支持字段：{", ".join(unknown)}')
        row, last = cursor
        col = [p.col.get(code, -1)]
        ref_factor = p.value('factor', self._ref_row(), code)
        parts, total = [], 0
        while row >= 0 and (count is None or total < count):
            day = pd.Timestamp(p.dates[row]).date()
            if start is not None and day < start.date():
                break
            daily = {f: p.block(f, row, row + 1, col)[0, 0] for f in ('paused', 'open', 'factor', 'high_limit',
                                                                         'low_limit')}
            bars = bt.minutes.bars(code, day, daily['open']) if daily['paused'] == 0 else None
            if bars is None and daily['paused'] == 0:
                bt.warn_once('no-minute-bars', f'{code} 等股票在 {day} 等日期没有分钟数据，分钟线中缺少这些日期')
            if bars is not None:
                if last is not None:
                    bars = {f: v[:last + 1] for f, v in bars.items()}
                if k > 1:
                    bars = minute.aggregate(bars, k)
                scale = {'pre': daily['factor'] / ref_factor, 'post': daily['factor']}.get(fq, 1.0)
                parts.append((bars, scale, daily))
                total += len(bars['close'])
            row, last = row - 1, None
        parts.reverse()

        def column(f):
            if not parts:
                return np.array([], dtype=float)
            if f in ('open', 'close', 'high', 'low'):
                return np.concatenate([b[f] * s for b, s, _ in parts])
            if f == 'volume':
                return np.concatenate([b['volume'] / s for b, s, _ in parts])
            if f in ('money', 'time'):
                return np.concatenate([b[f] for b, _, _ in parts])
            if f in ('avg', 'price'):
                money, volume, close = column('money'), column('volume'), column('close')
                with np.errstate(invalid='ignore', divide='ignore'):
                    return np.where(volume > 0, money / volume, close)
            if f == 'factor':
                return np.concatenate([np.full(len(b['close']), s if fq in ('pre', 'post') else 1.0)
                                       for b, s, _ in parts])
            if f in ('high_limit', 'low_limit'):
                return np.concatenate([np.full(len(b['close']), d[f] * s) for b, s, d in parts])
            return np.zeros(sum(len(b['close']) for b, _, _ in parts))  # paused

        times = column('time')
        keep = np.ones(len(times), dtype=bool)
        if start is not None:
            keep &= times >= np.datetime64(start, 'm')
        index = np.flatnonzero(keep)
        if count is not None:
            index = index[-int(count):]
        return pd.DataFrame({f: column(f)[index] for f in fields},
                            index=pd.DatetimeIndex(times[index], name=None))

    # ---------- 行情：聚宽函数 ----------

    def get_price(self, security, start_date=None, end_date=None, frequency='daily', fields=None, skip_paused=False,
                  fq='pre', count=None, panel=True, fill_paused=True, df=True, round=True):
        k = _bar_minutes(frequency)
        single = isinstance(security, str)
        codes = [normalize_code(c) for c in _as_list(security)]
        one_field = isinstance(fields, str)
        if k:
            if (start_date is None) == (count is None):
                raise StrategyError('需要指定 start_date 或 count 之一')
            fields = _as_list(fields) or _DEFAULT_FIELDS
            start = pd.Timestamp(start_date) if start_date is not None else None
            cursor = self._minute_cursor(end_date)
            frames = {c: self._minute_frame(c, count, fields, fq, k, cursor, start) for c in codes}
            if single:
                return frames[codes[0]]
            if not panel:
                parts = [f.assign(code=c).rename_axis('time').reset_index() for c, f in frames.items()]
                return pd.concat(parts, ignore_index=True)[['time', 'code', *fields]]
            out = {f: pd.DataFrame({c: frames[c][f] for c in codes}) for f in fields}
            return out[fields[0]] if one_field else FieldPanel(out)
        fields = self._fields(fields, _DEFAULT_FIELDS)
        r0, r1 = self._range(start_date, end_date, count, self.bt.visible_row())
        cols = self.panel.cols(codes)
        values = {f: self._values(f, r0, r1, cols, fq, self._ref_row()) for f in fields}
        paused = self.panel.block('paused', r0, r1, cols).astype(bool)
        if not fill_paused:
            for f in fields:
                if f != 'paused':
                    values[f] = np.where(paused, np.nan, values[f])
        index = self._index(r0, r1)
        if single:
            frame = pd.DataFrame({f: values[f][:, 0] for f in fields}, index=index)
            if skip_paused:
                frame = frame[~paused[:, 0]]
                if count is not None and len(frame) < int(count):
                    rows = self._skip_paused_rows(codes[0], r1, int(count))
                    return self._rows_frame(codes[0], rows, fields, fq)
            return frame
        if not panel:
            parts = []
            for j, code in enumerate(codes):
                part = pd.DataFrame({'time': index, 'code': code, **{f: values[f][:, j] for f in fields}})
                parts.append(part[~paused[:, j]] if skip_paused else part)
            return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=['time', 'code', *fields])
        frames = {f: pd.DataFrame(values[f], index=index, columns=codes) for f in fields}
        return frames[fields[0]] if one_field else FieldPanel(frames)

    def _rows_frame(self, code, rows, fields, fq):
        col = [self.panel.col.get(code, -1)]
        data = {}
        for f in fields:
            if len(rows):
                block = self._values(f, int(rows[0]), int(rows[-1]) + 1, col, fq, self._ref_row())[:, 0]
                data[f] = block[rows - rows[0]]
            else:
                data[f] = np.array([])
        return pd.DataFrame(data, index=pd.DatetimeIndex(self.panel.dates[rows]))

    def history(self, count, unit='1d', field='avg', security_list=None, df=True, skip_paused=False, fq='pre'):
        k = _bar_minutes(unit)
        codes = security_list if security_list is not None else self.bt.context.universe
        codes = [normalize_code(c) for c in _as_list(codes)]
        if k:
            cursor = self._minute_cursor()
            series = {c: self._minute_frame(c, int(count), [field], fq, k, cursor)[field] for c in codes}
            return pd.DataFrame(series) if df else {c: v.to_numpy() for c, v in series.items()}
        field = self._fields(field, None)[0]
        r1 = self.bt.r  # 不含当天
        r0 = max(r1 - int(count), 0)
        if skip_paused:
            data = {c: self._rows_frame(c, self._skip_paused_rows(c, r1, int(count)), [field], fq)[field].to_numpy()
                    for c in codes}
            if not df:
                return data
            return pd.DataFrame({c: pd.Series(v) for c, v in data.items()})
        values = self._values(field, r0, r1, self.panel.cols(codes), fq, self._ref_row())
        if not df:
            return {c: values[:, j] for j, c in enumerate(codes)}
        return pd.DataFrame(values, index=self._index(r0, r1), columns=codes)

    def attribute_history(self, security, count, unit='1d', fields=('open', 'close', 'high', 'low', 'volume', 'money'),
                          skip_paused=True, df=True, fq='pre'):
        k = _bar_minutes(unit)
        code = normalize_code(security)
        if k:
            fields = _as_list(fields)
            frame = self._minute_frame(code, int(count), fields, fq, k, self._minute_cursor())
            return frame if df else {f: frame[f].to_numpy() for f in fields}
        fields = self._fields(list(fields) if not isinstance(fields, str) else fields, None)
        r1 = self.bt.r
        if skip_paused:
            frame = self._rows_frame(code, self._skip_paused_rows(code, r1, int(count)), fields, fq)
        else:
            r0 = max(r1 - int(count), 0)
            frame = self._rows_frame(code, np.arange(r0, r1), fields, fq)
        return frame if df else {f: frame[f].to_numpy() for f in fields}

    def get_bars(self, security, count, unit='1d', fields=('date', 'open', 'high', 'low', 'close'), include_now=False,
                 end_dt=None, fq_ref_date=None, df=False):
        k = _bar_minutes(unit)
        if not isinstance(security, str):
            bars = {normalize_code(s): self.get_bars(s, count, unit, fields, include_now, end_dt, fq_ref_date, df)
                    for s in security}
            return pd.concat(bars, names=['code', None]) if df else bars
        code = normalize_code(security)
        fields = [fields] if isinstance(fields, str) else list(fields)
        if k:
            values = [f for f in fields if f != 'date']
            frame = self._minute_frame(code, int(count), values, 'pre' if fq_ref_date is not None else None, k,
                                       self._minute_cursor(end_dt))
            stamps = np.array([ts.to_pydatetime() for ts in frame.index], dtype=object)
            if df:
                return frame.assign(date=stamps)[fields].reset_index(drop=True)
            arr = np.empty(len(frame), dtype=[(f, 'O' if f == 'date' else 'f8') for f in fields])
            for f in fields:
                arr[f] = stamps if f == 'date' else frame[f].to_numpy()
            return arr
        end_row = self.bt.visible_row() if include_now else self.bt.r - 1
        if end_dt is not None:
            end_row = min(end_row, self.panel.row(to_date(end_dt)))
        rows = self._skip_paused_rows(code, end_row + 1, int(count))
        if fq_ref_date is None:
            fq, ref = None, self._ref_row()
        else:
            fq, ref = 'pre', min(self.panel.row(to_date(fq_ref_date)), self.bt.r)
        col = [self.panel.col.get(code, -1)]
        out = {}
        for f in fields:
            if f == 'date':
                out[f] = np.array([pd.Timestamp(d).date() for d in self.panel.dates[rows]], dtype=object)
                continue
            self._fields(f, None)
            if len(rows):
                block = self._values(f, int(rows[0]), int(rows[-1]) + 1, col, fq, ref)[:, 0]
                out[f] = block[rows - rows[0]]
            else:
                out[f] = np.array([], dtype=float)
        if df:
            return pd.DataFrame(out)
        dtype = [(f, 'O' if f == 'date' else 'f8') for f in fields]
        arr = np.empty(len(rows), dtype=dtype)
        for f in fields:
            arr[f] = out[f]
        return arr

    def get_current_data(self, security_list=None):
        return _CurrentData(self)

    def get_extras(self, info, security_list, start_date=None, end_date=None, df=True, count=None):
        if info != 'is_st':
            raise NotSupported(f'get_extras 暂只支持 is_st，不支持 {info}')
        codes = [normalize_code(c) for c in _as_list(security_list)]
        r0, r1 = self._range(start_date, end_date, count, self.bt.visible_row())
        values = self.panel.block('is_st', r0, r1, self.panel.cols(codes)).astype(bool)
        if not df:
            return {c: values[:, j] for j, c in enumerate(codes)}
        return pd.DataFrame(values, index=self._index(r0, r1), columns=codes)

    # ---------- 证券与日历 ----------

    def get_all_securities(self, types=('stock',), date=None):
        types = _as_list(types) or ['stock']
        secs = self.bt.securities
        known = [t for t in types if t in ('stock', 'index')]
        for t in set(types) - set(known):
            self.bt.warn_once(f'type:{t}', f'get_all_securities 暂不支持 {t} 类型（只有股票与指数），已忽略')
        frame = secs[secs['type'].isin(known)]
        start = frame['start_date'].dt.date
        end = frame['end_date'].fillna(pd.Timestamp('2200-01-01')).dt.date
        if date is not None:
            day = to_date(date)
            keep = (start <= day) & (end > day)
            frame, start, end = frame[keep], start[keep], end[keep]
        return pd.DataFrame({'display_name': frame['display_name'], 'name': '', 'start_date': start,
                             'end_date': end, 'type': frame['type']}, index=frame.index.rename(None))

    def get_security_info(self, code, date=None):
        code = normalize_code(code)
        secs = self.bt.securities
        if code not in secs.index:
            return None
        row = secs.loc[code]
        end = row['end_date'].date() if not pd.isna(row['end_date']) else datetime.date(2200, 1, 1)
        return _Info(code=code, display_name=row['display_name'], name='', start_date=row['start_date'].date(),
                     end_date=end, type=row['type'], parent=None)

    def get_trade_days(self, start_date=None, end_date=None, count=None):
        days = self.bt.trade_days
        end = to_date(end_date) if end_date is not None else days[-1]
        upto = [d for d in days if d <= end]
        if count is not None:
            return np.array(upto[-int(count):], dtype=object)
        if start_date is None:
            raise StrategyError('get_trade_days 需要 start_date 或 count')
        start = to_date(start_date)
        return np.array([d for d in upto if d >= start], dtype=object)

    def get_all_trade_days(self):
        return np.array(self.bt.trade_days, dtype=object)

    def get_index_stocks(self, index_symbol, date=None):
        code = normalize_code(index_symbol)
        if code not in _INDEX_NAMES:
            raise NotSupported(f'get_index_stocks 暂只支持 {"、".join(f"{k}（{v}）" for k, v in _INDEX_NAMES.items())}')
        day = to_date(date) if date is not None else self.bt.today
        m = self.bt.members
        snaps = m[(m['index'] == code) & (m['date'] <= day)]
        if snaps.empty:
            self.bt.warn_once(f'members:{code}', f'{code} 在 {day} 之前没有成分股数据，返回空列表')
            return []
        return list(snaps.sort_values('date')['codes'].iloc[-1])

    # ---------- 设置 ----------

    def set_benchmark(self, security):
        code = normalize_code(security)
        if code not in self.panel.col:
            raise StrategyError(f'没有基准 {security} 的数据')
        self.bt.benchmark = code

    def set_universe(self, security_list):
        self.bt.context.universe = [normalize_code(c) for c in _as_list(security_list)]

    def set_option(self, key, value):
        if key == 'order_volume_ratio':
            self.bt.volume_ratio = float(value)
        elif key == 'use_real_price' and not value:
            self.bt.warn_once('real_price', 'use_real_price=False 不受支持，仍按真实价格撮合')
        elif key not in ('use_real_price', 'avoid_future_data', 'match_by_signal', 'match_with_order_book'):
            self.bt.warn_once(f'option:{key}', f'set_option({key!r}) 不受支持，已忽略')

    def set_order_cost(self, cost, type='stock', ref=None):
        if type in ('stock', None):
            self.bt.order_cost = cost

    def set_commission(self, commission):
        self.bt.order_cost = commission

    def set_slippage(self, slippage, type=None, ref=None):
        if type in (None, 'stock'):
            self.bt.slippage = slippage

    # ---------- 定时运行 ----------

    def _schedule(self, kind, func, n, time_, force):
        if not callable(func):
            raise StrategyError('定时任务的第一个参数必须是函数')
        at = engine.EVERY_BAR if str(time_).strip().lower() == 'every_bar' else engine.parse_time(time_)
        self.bt.events.append((at, len(self.bt.events), kind, func, n, force))

    def run_daily(self, func, time='9:30', reference_security='000300.XSHG'):
        self._schedule('daily', func, None, time, False)

    def run_weekly(self, func, weekday, time='9:30', reference_security='000300.XSHG', force=True):
        self._schedule('week', func, int(weekday), time, force)

    def run_monthly(self, func, monthday, time='9:30', reference_security='000300.XSHG', force=True):
        self._schedule('month', func, int(monthday), time, force)

    def unschedule_all(self):
        self.bt.events.clear()

    # ---------- 交易 ----------

    def order(self, security, amount, style=None, side='long', pindex=0, close_today=False):
        return self.bt.order(security, amount, style)

    def order_target(self, security, amount, style=None, side='long', pindex=0, close_today=False):
        return self.bt.order_target(security, amount, style)

    def order_value(self, security, value, style=None, side='long', pindex=0, close_today=False):
        return self.bt.order_value(security, value, style)

    def order_target_value(self, security, value, style=None, side='long', pindex=0, close_today=False):
        return self.bt.order_target_value(security, value, style)

    def cancel_order(self, order):
        return None

    def get_open_orders(self):
        return {}

    def get_orders(self, order_id=None, security=None, status=None):
        orders = self.bt.orders_today
        return {k: o for k, o in orders.items() if (order_id is None or k == order_id)
                and (security is None or o.security == normalize_code(security))
                and (status is None or o.status == status)}

    def get_trades(self, order_id=None, security=None):
        return {k: t for k, t in self.bt.trades_today.items() if (order_id is None or t.order_id == order_id)
                and (security is None or t.security == normalize_code(security))}

    # ---------- 其它 ----------

    def record(self, **kwargs):
        self.bt.record(**kwargs)

    def send_message(self, message, channel='weixin'):
        self.bt.log('INFO', f'[消息] {message}')
        return True

    def namespace(self):
        """策略代码的全局命名空间。"""
        log = _Log(self.bt)

        def print_(*args, sep=' ', end='\n', file=None, flush=False):
            if file not in (None, sys.stdout):
                return builtins.print(*args, sep=sep, end=end, file=file, flush=flush)
            self.bt.log('INFO', sep.join(str(a) for a in args))

        ns = {name: _unsupported(name, reason) for name, reason in UNSUPPORTED.items()}
        ns.update({name: _UnsupportedObject(name) for name in UNSUPPORTED_OBJECTS})
        for name in ('get_price', 'history', 'attribute_history', 'get_bars', 'get_current_data', 'get_extras',
                     'get_all_securities', 'get_security_info', 'get_trade_days', 'get_all_trade_days',
                     'get_index_stocks', 'set_benchmark', 'set_universe', 'set_option', 'set_order_cost',
                     'set_commission', 'set_slippage', 'run_daily', 'run_weekly', 'run_monthly', 'unschedule_all',
                     'order', 'order_target', 'order_value', 'order_target_value', 'cancel_order', 'get_open_orders',
                     'get_orders', 'get_trades', 'record', 'send_message'):
            ns[name] = getattr(self, name)
        noop = lambda *a, **k: None  # noqa: E731
        ns.update({
            'log': log, 'print': print_, 'g': types.SimpleNamespace(), 'normalize_code': _normalize_any,
            'OrderCost': engine.OrderCost, 'PerTrade': engine.PerTrade, 'FixedSlippage': engine.FixedSlippage,
            'PriceRelatedSlippage': engine.PriceRelatedSlippage, 'MarketOrderStyle': engine.MarketOrderStyle,
            'LimitOrderStyle': engine.LimitOrderStyle, 'OrderStatus': engine.OrderStatus,
            'enable_profile': noop, 'disable_cache': noop, 'set_params': noop, 'set_universe_list': noop,
            'np': np, 'pd': pd,
        })
        return ns


def _normalize_any(code):
    if isinstance(code, str):
        return normalize_code(code)
    return [normalize_code(c) for c in code]


def install_modules(ns):
    """让 from jqdata import * / import jqdata / from kuanke.user_space_api import * 可用。"""
    public = {k: v for k, v in ns.items() if not k.startswith('_') and k not in ('np', 'pd', 'print')}
    for name in ('jqdata', 'kuanke', 'kuanke.user_space_api'):
        module = types.ModuleType(name)
        module.__dict__.update(public)
        module.__all__ = list(public)
        sys.modules[name] = module
    sys.modules['kuanke'].user_space_api = sys.modules['kuanke.user_space_api']
