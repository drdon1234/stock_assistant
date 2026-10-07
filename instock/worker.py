"""常驻调度进程（替代 cron + supervisor）：
- 交易日 9:30~15:00 每 30 分钟刷新股票和 ETF 行情，开盘首轮顺带抓早盘抢筹、刷新综合选股（基本面）；
- 交易日 17:30 运行完整作业（抓取、分析、回测）；
- 启动时若最近收盘日还没有分析结果则补跑；每天清理过期 K 线缓存。
"""
import datetime
import logging
import time

import sqlalchemy as sa

from instock import db, history, jobs, schema, tradecal

log = logging.getLogger(__name__)

_SESSION = (datetime.time(9, 30), datetime.time(15, 5))
_DAILY_AT = datetime.time(17, 30)


def _safe_run(**kwargs):
    try:
        jobs.run(**kwargs)
    except Exception:
        log.exception('作业失败')


def _catch_up():
    closed = tradecal.get().closed_session()
    table = schema.SA_TABLES[schema.INDICATOR.name]
    done = db.scalar(sa.select(sa.func.count()).select_from(table).where(table.c.date == closed))
    if not done:
        log.info('最近收盘日 %s 尚无分析结果，开始补跑', closed)
        _safe_run(days=[closed])
    return closed


def main():
    db.init()
    log.info('调度进程已启动')
    closed = _catch_up()
    last_slot = last_prune = None
    last_daily = closed  # 启动时已确保最近收盘日的作业完成，避免当天重复运行
    while True:
        now = tradecal.now()
        today, t = now.date(), now.time()
        if tradecal.get().is_trade_day(today):
            slot = (today, now.hour, now.minute // 30)
            if _SESSION[0] <= t <= _SESSION[1] and slot != last_slot:
                # 开盘首轮额外抓早盘抢筹，并刷新综合选股，使夜间披露的财报尽快进入行情的基本面列
                first = last_slot is None or last_slot[0] != today
                keys = jobs.REALTIME_KEYS + (('selection', 'chip_open') if first else ())
                last_slot = slot
                _safe_run(keys=keys)
            if t >= _DAILY_AT and last_daily != today:
                last_daily = today
                _safe_run()
        if last_prune != today:
            last_prune = today
            history.prune()
        time.sleep(20)
