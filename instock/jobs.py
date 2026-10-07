"""作业编排：数据抓取任务与分析流水线。支持当前、单日、多日和区间运行。

- 实时类数据（行情、资金流向等）接口只提供当前数据，只在“当前交易日”运行，回补历史日期时自动跳过；
- 收盘后数据（大宗交易、尾盘抢筹、龙虎榜、分析）只对已收盘的交易日运行；
- 多个日期的分析合并为一次计算：每只股票只算一遍指标，再按各日期取值。
"""
import datetime
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pandas as pd

from instock import config, db, history, market, schema, tradecal
from instock.analysis import backtest, engine
from instock.analysis.strategies import FUNDAMENTAL

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Task:
    key: str
    name: str
    realtime: bool = False  # 只能抓当前数据
    after_close: bool = False  # 收盘后才有数据


TASKS = (
    Task('spot', '每日股票数据', realtime=True),
    Task('etf', '每日ETF数据', realtime=True),
    Task('selection', '综合选股', realtime=True),
    Task('fund_flow', '个股资金流向', realtime=True),
    Task('sector_flow', '板块资金流向', realtime=True),
    Task('bonus', '分红配送', realtime=True),
    Task('chip_open', '早盘抢筹'),
    Task('limitup', '涨停原因'),
    Task('lhb', '龙虎榜', after_close=True),
    Task('blocktrade', '大宗交易', after_close=True),
    Task('chip_end', '尾盘抢筹', after_close=True),
    Task('analysis', '指标/形态/策略分析', after_close=True),
    Task('backtest', '策略回测', after_close=True),
    Task('quant', '回测数据', after_close=True),  # 首次回补完成（quant sync）后才每日增量更新
)
TASK_KEYS = tuple(t.key for t in TASKS)
REALTIME_KEYS = ('spot', 'etf')  # 盘中定时刷新的任务


class _Day:
    """单个交易日的抓取任务。"""

    def __init__(self, day):
        self.day = day
        self.spot = None

    def _save(self, spec, df, day=None):
        day = day or self.day
        rows = db.replace(spec, df, date=day) if df is not None else 0
        log.info('%s %s：%d 行', spec.label, day, rows)

    def spot_task(self):
        self.spot = market.stock_spot(self.day)
        self._save(schema.STOCK_SPOT, self.spot)

    def etf_task(self):
        self._save(schema.ETF_SPOT, market.etf_spot(self.day))

    def selection_task(self):
        df = market.selection()
        days = pd.to_datetime(df['date'], errors='coerce').dropna().dt.date
        self._save(schema.SELECTION, df, days.max() if not days.empty else self.day)

    def fund_flow_task(self):
        self._save(schema.FUND_FLOW, market.stock_fund_flow(self.day))

    def sector_flow_task(self):
        self._save(schema.FUND_FLOW_INDUSTRY, market.sector_fund_flow(self.day, concept=False))
        self._save(schema.FUND_FLOW_CONCEPT, market.sector_fund_flow(self.day, concept=True))

    def bonus_task(self):
        self._save(schema.BONUS, market.bonus(self.day))

    def chip_open_task(self):
        self._save(schema.CHIP_RACE_OPEN, market.chip_race(self.day, closing=False))

    def limitup_task(self):
        self._save(schema.LIMITUP_REASON, market.limitup_reasons(self.day))

    def lhb_task(self):
        self._save(schema.LHB, market.lhb(self.day))

    def blocktrade_task(self):
        self._save(schema.BLOCKTRADE, market.blocktrade(self.day))

    def chip_end_task(self):
        self._save(schema.CHIP_RACE_END, market.chip_race(self.day, closing=True))

    def run(self, keys):
        """先依次抓综合选股（行情的基本面列取自它）和行情，再并发执行其余任务（各数据源自带限流）。"""
        def safe(key):
            started = time.monotonic()
            try:
                getattr(self, f'{key}_task')()
            except Exception as e:
                log.exception('%s %s 失败：%s', key, self.day, e)
            else:
                log.debug('%s 用时 %.1f 秒', key, time.monotonic() - started)

        first = [k for k in ('selection', 'spot') if k in keys]
        for key in first:
            safe(key)
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(safe, [k for k in keys if k not in first]))


def _universe(day, spot):
    """当日需要分析的股票：当日有成交的沪深 A 股及名称。"""
    if spot is not None and spot['date'].iloc[0] == day:
        frame = spot
    else:
        frame = db.read(f'SELECT code, name, volume FROM {schema.STOCK_SPOT.name} WHERE date = :d', d=day)
        if frame.empty:
            latest = db.scalar(f'SELECT MAX(date) FROM {schema.STOCK_SPOT.name}')
            frame = db.read(f'SELECT code, name, volume FROM {schema.STOCK_SPOT.name} WHERE date = :d', d=latest)
    frame = frame[pd.to_numeric(frame['volume'], errors='coerce').fillna(1) > 0]
    return dict(zip(frame['code'], frame['name']))


def analyze(days, spots, batch=20):
    """对多个已收盘交易日做技术分析与基本面筛选，结果按日期整批替换入库。日期多时分批以控制内存。"""
    for i in range(0, len(days), batch):
        _analyze_batch(days[i:i + batch], spots)


def _analyze_batch(days, spots):
    names = {}
    for day in days:
        names.update(_universe(day, spots.get(day)))
    history.ensure(names, days[-1], spots.get(days[-1]), earliest=days[0])
    started = time.monotonic()
    indicators, pattern_rows, hits = engine.run(names, days, config.ANALYSIS_WORKERS)
    log.info('技术分析完成：%d 只股票 × %d 天，耗时 %.0f 秒', len(names), len(days), time.monotonic() - started)

    hits = pd.concat([hits, _fundamental(days)], ignore_index=True)
    for frame in (indicators, pattern_rows, hits):
        if not frame.empty:
            mapped = frame['code'].map(names)
            frame['name'] = mapped.fillna(frame['name']) if 'name' in frame else mapped
    for day in days:
        for spec, frame in ((schema.INDICATOR, indicators), (schema.PATTERN, pattern_rows), (schema.SIGNAL, hits)):
            part = frame[frame['date'] == day] if not frame.empty else frame
            rows = db.replace(spec, part, date=day)
            log.info('%s %s：%d 行', spec.label, day, rows)


def _fundamental(days):
    frames = []
    for day in days:
        sel = db.read(f'SELECT * FROM {schema.SELECTION.name} WHERE date = :d', d=day)
        if sel.empty:
            continue
        for s in FUNDAMENTAL:
            hit = s.screen(sel)
            frames.append(pd.DataFrame({'date': day, 'strategy': s.key, 'code': hit['code'],
                                        'name': hit['name'], 'close': hit['new_price']}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run(days=None, keys=TASK_KEYS):
    """运行作业。days 为空表示当前；keys 为要运行的任务。"""
    db.init()
    cal = tradecal.get()
    current, closed = cal.current_session(), cal.closed_session()
    days = sorted(set(days or [current]))
    started = time.monotonic()
    spots, analysis_days = {}, []
    for day in days:
        if not cal.is_trade_day(day):
            log.info('%s 不是交易日，跳过', day)
            continue
        todo = []
        for task in TASKS:
            if task.key not in keys or task.key in ('analysis', 'backtest', 'quant'):
                continue
            if task.realtime and day != current:
                log.info('%s 只能获取当前数据，跳过 %s', task.name, day)
            elif task.after_close and day > closed:
                log.info('%s 尚未收盘，跳过 %s', day, task.name)
            else:
                todo.append(task.key)
        if 'analysis' in keys and day <= closed and 'spot' not in todo and day == current:
            todo.insert(0, 'spot')  # 分析依赖当日收盘行情
        job = _Day(day)
        if todo:
            job.run(todo)
        spots[day] = job.spot
        if 'analysis' in keys and day <= closed:
            analysis_days.append(day)
    if analysis_days:
        analyze(analysis_days, spots)
    if 'backtest' in keys:
        backtest.update_pending()
        backtest.update_benchmark()
    if 'quant' in keys and days[-1] <= closed:
        _sync_quant()
    log.info('作业完成：%s，耗时 %.0f 秒', ', '.join(map(str, days)), time.monotonic() - started)


def _sync_quant():
    from instock.quant import data, store
    if not store.load_state().get('ready'):
        return  # 首次回补耗时数小时，需手动运行 python -m instock quant sync
    try:
        data.sync()
    except Exception:
        log.exception('回测数据同步失败')


def parse_days(args):
    """命令行日期：空=当前；单日 2024-03-01；多日 2024-03-01,2024-03-05；区间 2024-03-01 2024-03-31。"""
    if not args:
        return None
    if len(args) == 2:
        start, end = (datetime.date.fromisoformat(a) for a in args)
        return tradecal.get().between(start, end)
    return [datetime.date.fromisoformat(a) for a in args[0].split(',')]
