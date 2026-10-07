"""回测数据仓库（目录 config.QUANT_DIR）。

raw/<代码>.pkl     每只证券一份不复权日线（含停牌行、ST 标记、后复权因子），是唯一的数据来源；
panel/             由 raw 生成的按年宽表（行=交易日，列=证券），回测时以 np.memmap 只读映射、按需读取；
securities.pkl     证券列表（含已退市）；members.pkl 指数成分快照；trade_days.json 交易日历；state.json 同步状态。

宽表各年的列顺序相同（codes.json，新证券只追加在末尾），早年的表可能更窄，读取时补缺省值。
"""
import datetime
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from instock import config

PRICE_FIELDS = ('open', 'high', 'low', 'close', 'pre_close', 'high_limit', 'low_limit')
FLOAT_FIELDS = PRICE_FIELDS + ('volume', 'money', 'factor')
FLAG_FIELDS = ('paused', 'is_st')
FIELDS = FLOAT_FIELDS + FLAG_FIELDS
_PAD = {'paused': 1, 'is_st': 0}  # 未上市/已退市的日期：视为停牌、非 ST

# 涨跌停规则的关键日期
_FIRST_DAY_LIMIT = np.datetime64('2014-01-01')  # 此后主板/创业板新股首日涨跌幅 +44% / -36%
_CHINEXT_REFORM = np.datetime64('2020-08-24')  # 创业板注册制：涨跌幅 20%，新股前 5 日不设涨跌幅
_MAIN_REGISTRATION = np.datetime64('2023-04-10')  # 主板注册制：新股前 5 日不设涨跌幅
_MAIN_ST_10 = np.datetime64('2025-07-07')  # 主板风险警示股票涨跌幅由 5% 调整为 10%


def root():
    return config.QUANT_DIR


def _raw_path(code):
    return root() / 'raw' / f'{code}.pkl'


def _atomic(path, write):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    write(tmp)
    os.replace(tmp, path)


def read_raw(code):
    try:
        return pd.read_pickle(_raw_path(code))
    except FileNotFoundError:
        return None


def write_raw(code, df):
    _atomic(_raw_path(code), df.to_pickle)


def raw_codes():
    folder = root() / 'raw'
    return sorted(p.stem for p in folder.glob('*.pkl')) if folder.is_dir() else []


def load_securities():
    path = root() / 'securities.pkl'
    if not path.is_file():
        return pd.DataFrame(columns=['code', 'display_name', 'start_date', 'end_date', 'type'])
    return pd.read_pickle(path)


def save_securities(df):
    _atomic(root() / 'securities.pkl', df.to_pickle)


def load_members():
    path = root() / 'members.pkl'
    if not path.is_file():
        return pd.DataFrame(columns=['index', 'date', 'codes'])
    return pd.read_pickle(path)


def save_members(df):
    _atomic(root() / 'members.pkl', df.to_pickle)


def load_trade_days():
    path = root() / 'trade_days.json'
    if not path.is_file():
        return []
    return [datetime.date.fromisoformat(d) for d in json.loads(path.read_text())]


def save_trade_days(days):
    _atomic(root() / 'trade_days.json', lambda p: p.write_text(json.dumps([d.isoformat() for d in days])))


def load_state():
    path = root() / 'state.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def save_state(state):
    _atomic(root() / 'state.json',
            lambda p: p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8'))


def _round2(x):
    """四舍五入到分（交易所规则），避免二进制浮点导致 x.xx5 向下舍入。"""
    return np.floor(x * 100 + 0.5 + 1e-7) / 100


def limit_prices(code, dates, pre_close, is_st, ipo):
    """按交易所规则计算每日涨停价、跌停价；不设涨跌幅的日期为 NaN。
    dates 为该证券从上市（或数据起点）起的全部交易日，ipo 为上市日期（未知时为 None）。"""
    dates = np.asarray(dates, dtype='datetime64[D]')
    pre_close = np.asarray(pre_close, dtype=float)
    st = np.asarray(is_st, dtype=bool)
    board = code[:3]
    ipo = np.datetime64(ipo, 'D') if ipo is not None and not pd.isna(ipo) else None
    if board == '688':
        pct = np.full(len(dates), 0.20)
        free_days, first_day = 5, False
    elif board in ('300', '301'):
        pct = np.where(dates >= _CHINEXT_REFORM, 0.20, np.where(st, 0.05, 0.10))
        late = ipo is not None and ipo >= _CHINEXT_REFORM
        free_days, first_day = (5, False) if late else (0, True)
    else:
        pct = np.where(st, np.where(dates >= _MAIN_ST_10, 0.10, 0.05), 0.10)
        late = ipo is not None and ipo >= _MAIN_REGISTRATION
        free_days, first_day = (5, False) if late else (0, True)
    high, low = _round2(pre_close * (1 + pct)), _round2(pre_close * (1 - pct))
    if ipo is not None and len(dates) and dates[0] <= ipo + np.timedelta64(7, 'D'):
        # 数据从上市首日开始：处理上市初期的特殊规则
        k = np.arange(len(dates)) - int(np.searchsorted(dates, ipo))
        if free_days:
            free = (k >= 0) & (k < free_days)
            high[free] = low[free] = np.nan
        elif first_day and (k == 0).any():
            i = int(np.flatnonzero(k == 0)[0])
            if ipo >= _FIRST_DAY_LIMIT:
                high[i], low[i] = _round2(pre_close[i] * 1.44), _round2(pre_close[i] * 0.64)
            else:
                high[i] = low[i] = np.nan
    return high, low


def _save_npy(path, arr):
    with open(path, 'wb') as fh:  # 传文件对象，np.save 不会给临时文件名追加 .npy
        np.save(fh, arr, allow_pickle=False)


def _year_dir(year):
    return root() / 'panel' / str(year)


def build_panel(years, trade_days=None, last_date=None, log=None):
    """重建指定年份的宽表。每只证券的 raw 只读一次，直接写入各年的内存映射文件，内存占用小。"""
    years = sorted(set(years))
    if not years:
        return
    trade_days = trade_days or load_trade_days()
    last_date = last_date or datetime.date.today()
    secs = load_securities().set_index('code')
    panel_dir = root() / 'panel'
    panel_dir.mkdir(parents=True, exist_ok=True)
    codes_path = panel_dir / 'codes.json'
    codes = json.loads(codes_path.read_text()) if codes_path.is_file() else []
    known = set(codes)
    codes += sorted(c for c in raw_codes() if c not in known)
    col = {c: i for i, c in enumerate(codes)}
    # 先写列表：列只追加，旧宽表仍按原列号读取
    _atomic(codes_path, lambda p: p.write_text(json.dumps(codes)))

    start = datetime.date.fromisoformat(config.QUANT_START)
    year_days = {y: np.array([d for d in trade_days if d.year == y and start <= d <= last_date],
                             dtype='datetime64[D]') for y in years}
    year_days = {y: d for y, d in year_days.items() if len(d)}
    arrays = {}
    for y, days in year_days.items():
        _year_dir(y).mkdir(parents=True, exist_ok=True)
        for f in FIELDS:
            path = _year_dir(y) / f'{f}.npy.{os.getpid()}.tmp'
            dtype = np.int8 if f in FLAG_FIELDS else np.float64
            arr = np.lib.format.open_memmap(path, mode='w+', dtype=dtype, shape=(len(days), len(codes)))
            arr[:] = _PAD.get(f, np.nan)
            arrays[y, f] = (path, arr)
    lo = min(d[0] for d in year_days.values()) if year_days else None
    hi = max(d[-1] for d in year_days.values()) if year_days else None
    for n, code in enumerate(codes):
        if log and n and n % 1000 == 0:
            log.info('生成宽表：%d / %d', n, len(codes))
        df = read_raw(code)
        if df is None or df.empty:
            continue
        dates = df['date'].to_numpy(dtype='datetime64[D]')
        ipo = secs['start_date'].get(code) if code in secs.index else None
        is_index = code in secs.index and secs.at[code, 'type'] == 'index'
        if is_index:
            high = low = np.full(len(df), np.nan)
        else:
            high, low = limit_prices(code, dates, df['pre_close'], df['is_st'], ipo)
        values = {f: df[f].to_numpy() for f in ('open', 'high', 'low', 'close', 'pre_close', 'volume', 'money',
                                                'factor', 'paused', 'is_st')}
        values['high_limit'], values['low_limit'] = high, low
        sel = (dates >= lo) & (dates <= hi)
        if not sel.any():
            continue
        for y, days in year_days.items():
            idx = np.searchsorted(days, dates[sel])
            ok = (idx < len(days)) & (days[np.minimum(idx, len(days) - 1)] == dates[sel])
            if not ok.any():
                continue
            rows = idx[ok]
            for f in FIELDS:
                arrays[y, f][1][rows, col[code]] = values[f][sel][ok]
    for y, days in year_days.items():
        _atomic(_year_dir(y) / 'dates.npy', lambda p, d=days: _save_npy(p, d))
        for f in FIELDS:
            path, arr = arrays[y, f]
            arr.flush()
            del arr
            arrays[y, f] = (path, None)
            os.replace(path, _year_dir(y) / f'{f}.npy')


class Panel:
    """宽表的只读视图。行号为全局交易日序号（跨年连续），列号为 codes.json 中的序号。"""

    def __init__(self, path=None):
        self.root = Path(path or root() / 'panel')
        self.codes = json.loads((self.root / 'codes.json').read_text())
        self.col = {c: i for i, c in enumerate(self.codes)}
        years = sorted(int(p.name) for p in self.root.iterdir()
                       if p.is_dir() and p.name.isdigit() and (p / 'dates.npy').is_file())
        self._years, chunks, offset = [], [], 0
        for y in years:
            d = np.load(self.root / str(y) / 'dates.npy')
            self._years.append((y, offset, len(d)))
            chunks.append(d)
            offset += len(d)
        self.dates = np.concatenate(chunks) if chunks else np.array([], dtype='datetime64[D]')
        self._maps = {}

    def __len__(self):
        return len(self.dates)

    def row(self, day):
        """day 当天或之前最近一个交易日的行号；早于第一天返回 -1。"""
        return int(np.searchsorted(self.dates, np.datetime64(day, 'D'), side='right')) - 1

    def _map(self, year, field):
        key = (year, field)
        if key not in self._maps:
            self._maps[key] = np.load(self.root / str(year) / f'{field}.npy', mmap_mode='r')
        return self._maps[key]

    def cols(self, codes):
        return np.array([self.col.get(c, -1) for c in codes], dtype=np.int64)

    def block(self, field, r0, r1, cols):
        """field 在行 [r0, r1) 与 cols 列的取值；不存在的证券（列号 -1）返回缺省值。"""
        cols = np.asarray(cols, dtype=np.int64)
        flag = field in FLAG_FIELDS
        out = np.full((max(r1 - r0, 0), len(cols)), _PAD.get(field, np.nan), dtype=np.int8 if flag else np.float64)
        for y, start, n in self._years:
            a, b = max(r0, start), min(r1, start + n)
            if a >= b:
                continue
            arr = self._map(y, field)
            ok = (cols >= 0) & (cols < arr.shape[1])
            if ok.all():
                out[a - r0:b - r0] = arr[a - start:b - start][:, cols]
            elif ok.any():
                out[a - r0:b - r0, ok] = arr[a - start:b - start][:, cols[ok]]
        return out

    def column(self, field, r0, r1, code):
        return self.block(field, r0, r1, [self.col.get(code, -1)])[:, 0]

    def value(self, field, r, code):
        return self.block(field, r, r + 1, [self.col.get(code, -1)])[0, 0]
