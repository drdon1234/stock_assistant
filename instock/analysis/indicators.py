"""技术指标。

公式按通达信/同花顺的公式写法及默认参数实现（个别指标注明出处），便于与行情软件对照：
- EMA(X,N)、SMA(X,N,M) 均以首个有效值起算，与通达信一致；
- 所有指标只依赖当日及以前的数据，对整段历史算一次即可按日期取任意一天的值；
- 预热期不足的值为 NaN（入库为 NULL），不用 0 冒充。
"""
import numpy as np
import pandas as pd
import talib

# (列名, 显示名)
INDICATORS = (
    ('macd', 'MACD DIF'), ('macds', 'MACD DEA'), ('macdh', 'MACD柱'),
    ('kdjk', 'KDJ K'), ('kdjd', 'KDJ D'), ('kdjj', 'KDJ J'),
    ('boll_ub', 'BOLL上轨'), ('boll', 'BOLL中轨'), ('boll_lb', 'BOLL下轨'),
    ('trix', 'TRIX'), ('trma', 'TRMA'), ('tema', 'TEMA'),
    ('cr', 'CR'), ('cr_ma1', 'CR MA1'), ('cr_ma2', 'CR MA2'), ('cr_ma3', 'CR MA3'),
    ('rsi_6', 'RSI6'), ('rsi_12', 'RSI12'), ('rsi', 'RSI14'), ('rsi_24', 'RSI24'),
    ('vr', 'VR'), ('mavr', 'MAVR'),
    ('roc', 'ROC'), ('rocma', 'ROC MA'), ('rocema', 'ROC EMA'),
    ('pdi', 'PDI'), ('mdi', 'MDI'), ('dx', 'DX'), ('adx', 'ADX'), ('adxr', 'ADXR'),
    ('wr_6', 'WR6'), ('wr_10', 'WR10'), ('wr_14', 'WR14'),
    ('cci', 'CCI14'), ('cci_84', 'CCI84'),
    ('tr', 'TR'), ('atr', 'ATR'),
    ('dma', 'DMA DIF'), ('ama', 'DMA AMA'),
    ('obv', 'OBV'), ('sar', 'SAR'),
    ('psy', 'PSY'), ('psyma', 'PSYMA'),
    ('br', 'BR'), ('ar', 'AR'),
    ('emv', 'EMV'), ('emva', 'MAEMV'),
    ('bias', 'BIAS6'), ('bias_12', 'BIAS12'), ('bias_24', 'BIAS24'),
    ('mfi', 'MFI'), ('mfisma', 'MFI MA'),
    ('vwma', 'VWMA'), ('mvwma', 'VWMA MA'),
    ('ppo', 'PPO'), ('ppos', 'PPO信号'), ('ppoh', 'PPO柱'),
    ('wt1', 'WT1'), ('wt2', 'WT2'),
    ('supertrend_ub', 'SuperTrend上轨'), ('supertrend', 'SuperTrend'), ('supertrend_lb', 'SuperTrend下轨'),
    ('dpo', 'DPO'), ('madpo', 'MADPO'),
    ('vhf', 'VHF'),
    ('rvi', 'RVI'), ('rvis', 'RVI信号'),
    ('fi', 'FI'), ('force_2', 'FI EMA2'), ('force_13', 'FI EMA13'),
    ('ene_ue', 'ENE上轨'), ('ene', 'ENE'), ('ene_le', 'ENE下轨'),
    ('stochrsi_k', 'StochRSI K'), ('stochrsi_d', 'StochRSI D'),
)


def _s(x):
    return pd.Series(x, copy=False)


def ma(x, n):
    return _s(x).rolling(n).mean().to_numpy()


def _sum(x, n):
    return _s(x).rolling(n).sum().to_numpy()


def _hhv(x, n):
    return _s(x).rolling(n).max().to_numpy()


def _llv(x, n):
    return _s(x).rolling(n).min().to_numpy()


def _ema(x, n):
    return _s(x).ewm(span=n, adjust=False).mean().to_numpy()


def _sma(x, n, m=1):
    """通达信 SMA(X,N,M)：Y = (M*X + (N-M)*Y') / N。"""
    return _s(x).ewm(alpha=m / n, adjust=False).mean().to_numpy()


def ref(x, n):
    out = np.full(len(x), np.nan)
    if n < len(x):
        out[n:] = x[:len(x) - n]
    return out


def _div(a, b):
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.asarray(a, dtype=float) / b
    r[~np.isfinite(r)] = np.nan
    return r


def true_range(h, l, c):
    pc = ref(c, 1)
    return np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(pc - l)))


def rsi(c, n):
    diff = c - ref(c, 1)
    return _div(_sma(np.fmax(diff, 0), n), _sma(np.abs(diff), n)) * 100


def _supertrend(h, l, c, tr, period=10, multiplier=3.0):
    """SuperTrend（Olivier Seban），ATR 用 Wilder 平滑。返回 (上轨, 当前趋势线, 下轨)。"""
    atr = _sma(tr, period)
    hl2 = (h + l) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    n = len(c)
    trend = np.ones(n)
    for i in range(1, n):
        if c[i - 1] <= upper[i - 1] and upper[i] > upper[i - 1]:
            upper[i] = upper[i - 1]
        if c[i - 1] >= lower[i - 1] and lower[i] < lower[i - 1]:
            lower[i] = lower[i - 1]
        if trend[i - 1] < 0 and c[i] > upper[i - 1]:
            trend[i] = 1
        elif trend[i - 1] > 0 and c[i] < lower[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
    return upper, np.where(trend > 0, lower, upper), lower


def compute(o, h, l, c, v):
    """输入 float64 的开高低收量（量单位：股），返回 {列名: 数组}。"""
    pc = ref(c, 1)
    out = {}

    dif = _ema(c, 12) - _ema(c, 26)
    dea = _ema(dif, 9)
    out.update(macd=dif, macds=dea, macdh=2 * (dif - dea))

    llv9, hhv9 = _llv(l, 9), _hhv(h, 9)
    k = _sma(_div(c - llv9, hhv9 - llv9) * 100, 3)
    d = _sma(k, 3)
    out.update(kdjk=k, kdjd=d, kdjj=3 * k - 2 * d)

    # 布林线：John Bollinger 原始定义，标准差为总体标准差
    out['boll_ub'], out['boll'], out['boll_lb'] = talib.BBANDS(c, 20, 2, 2, 0)

    mtr = _ema(_ema(_ema(c, 12), 12), 12)
    out['trix'] = _div(mtr - ref(mtr, 1), ref(mtr, 1)) * 100
    out['trma'] = ma(out['trix'], 9)
    out['tema'] = talib.TEMA(c, 14)

    mid = ref(h + l, 1) / 2
    cr = _div(_sum(np.fmax(h - mid, 0), 26), _sum(np.fmax(mid - l, 0), 26)) * 100
    out.update(cr=cr, cr_ma1=ref(ma(cr, 10), 5), cr_ma2=ref(ma(cr, 20), 9), cr_ma3=ref(ma(cr, 40), 17))

    for n, key in ((6, 'rsi_6'), (12, 'rsi_12'), (14, 'rsi'), (24, 'rsi_24')):
        out[key] = rsi(c, n)

    th = _sum(np.where(c > pc, v, 0.0), 26)
    tl = _sum(np.where(c < pc, v, 0.0), 26)
    tq = _sum(np.where(c == pc, v, 0.0), 26)
    out['vr'] = _div(2 * th + tq, 2 * tl + tq) * 100
    out['mavr'] = ma(out['vr'], 6)

    out['roc'] = _div(c - ref(c, 12), ref(c, 12)) * 100
    out['rocma'] = ma(out['roc'], 6)
    out['rocema'] = _ema(out['roc'], 9)

    tr = true_range(h, l, c)
    hd, ld = h - ref(h, 1), ref(l, 1) - l
    trs = _sum(tr, 14)
    pdi = _div(_sum(np.where((hd > 0) & (hd > ld), hd, 0.0), 14) * 100, trs)
    mdi = _div(_sum(np.where((ld > 0) & (ld > hd), ld, 0.0), 14) * 100, trs)
    dx = _div(np.abs(mdi - pdi), mdi + pdi) * 100
    adx = ma(dx, 6)
    out.update(pdi=pdi, mdi=mdi, dx=dx, adx=adx, adxr=(adx + ref(adx, 6)) / 2)

    # 威廉指标按通达信刻度 0~100：数值越大越超卖
    for n in (6, 10, 14):
        hh, ll = _hhv(h, n), _llv(l, n)
        out[f'wr_{n}'] = _div(hh - c, hh - ll) * 100

    out['cci'] = talib.CCI(h, l, c, 14)
    out['cci_84'] = talib.CCI(h, l, c, 84)
    out['tr'] = tr
    out['atr'] = ma(tr, 14)

    out['dma'] = ma(c, 10) - ma(c, 50)
    out['ama'] = ma(out['dma'], 10)
    out['obv'] = talib.OBV(c, v)
    out['sar'] = talib.SAR(h, l, 0.02, 0.2)

    out['psy'] = _sum((c > pc).astype(float), 12) / 12 * 100
    out['psyma'] = ma(out['psy'], 6)

    out['ar'] = _div(_sum(h - o, 26), _sum(o - l, 26)) * 100
    out['br'] = _div(_sum(np.fmax(h - pc, 0), 26), _sum(np.fmax(pc - l, 0), 26)) * 100

    hl = h + l
    emv_mid = _div(100 * (hl - ref(hl, 1)), hl)
    out['emv'] = ma(emv_mid * _div(ma(v, 14), v) * _div(h - l, ma(h - l, 14)), 14)
    out['emva'] = ma(out['emv'], 9)

    for n, key in ((6, 'bias'), (12, 'bias_12'), (24, 'bias_24')):
        m = ma(c, n)
        out[key] = _div(c - m, m) * 100

    out['mfi'] = talib.MFI(h, l, c, v, 14)
    out['mfisma'] = ma(out['mfi'], 6)
    out['vwma'] = _div(_sum(c * v, 14), _sum(v, 14))
    out['mvwma'] = ma(out['vwma'], 6)

    out['ppo'] = talib.PPO(c, 12, 26, 1)
    out['ppos'] = _ema(out['ppo'], 9)
    out['ppoh'] = out['ppo'] - out['ppos']

    # WaveTrend（LazyBear）：平均价用 HLC3
    ap = (h + l + c) / 3
    esa = _ema(ap, 10)
    ci = _div(ap - esa, 0.015 * _ema(np.abs(ap - esa), 10))
    out['wt1'] = _ema(ci, 21)
    out['wt2'] = ma(out['wt1'], 4)

    out['supertrend_ub'], out['supertrend'], out['supertrend_lb'] = _supertrend(h, l, c, tr)

    out['dpo'] = c - ref(ma(c, 20), 11)
    out['madpo'] = ma(out['dpo'], 6)
    out['vhf'] = _div(_hhv(c, 28) - _llv(c, 28), _sum(np.abs(c - pc), 28))

    # RVI（John Ehlers）
    co, hl_range = c - o, h - l
    num = (co + 2 * ref(co, 1) + 2 * ref(co, 2) + ref(co, 3)) / 6
    den = (hl_range + 2 * ref(hl_range, 1) + 2 * ref(hl_range, 2) + ref(hl_range, 3)) / 6
    rvi = _div(ma(num, 10), ma(den, 10))
    out['rvi'] = rvi
    out['rvis'] = (rvi + 2 * ref(rvi, 1) + 2 * ref(rvi, 2) + ref(rvi, 3)) / 6

    # 强力指数（Alexander Elder）
    out['fi'] = (c - pc) * v
    out['force_2'] = _ema(out['fi'], 2)
    out['force_13'] = _ema(out['fi'], 13)

    ma10 = ma(c, 10)
    out.update(ene_ue=1.11 * ma10, ene_le=0.91 * ma10, ene=(1.11 * ma10 + 0.91 * ma10) / 2)

    r = out['rsi']
    lo, hi = _llv(r, 14), _hhv(r, 14)
    out['stochrsi_k'] = _div(r - lo, hi - lo) * 100
    out['stochrsi_d'] = ma(out['stochrsi_k'], 3)

    for key, arr in out.items():
        # 必须复制：pandas 3（写时复制）的 to_numpy 返回只读视图，原地赋值会报错
        arr = np.array(arr, dtype=float)
        arr[~np.isfinite(arr)] = np.nan
        out[key] = arr
    return out
