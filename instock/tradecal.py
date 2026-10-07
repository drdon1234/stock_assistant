"""交易日历与交易时段判断。所有时间按北京时间计算，与宿主机时区无关。"""
import bisect
import datetime
import json
import logging
import threading

from instock import config
from instock.sources import sina

log = logging.getLogger(__name__)

_CN_TZ = datetime.timezone(datetime.timedelta(hours=8))
OPEN_TIME = datetime.time(9, 30)
CLOSE_TIME = datetime.time(15, 0)


def now():
    """当前北京时间（naive）。"""
    return datetime.datetime.now(_CN_TZ).replace(tzinfo=None)


class TradeCalendar:
    def __init__(self, dates):
        self._dates = sorted(set(dates))
        self._set = set(self._dates)

    def is_trade_day(self, day):
        return day in self._set

    def prev(self, day, n=1):
        """day 之前（不含 day）的第 n 个交易日。"""
        idx = bisect.bisect_left(self._dates, day) - n
        return self._dates[max(idx, 0)]

    def between(self, start, end):
        lo, hi = bisect.bisect_left(self._dates, start), bisect.bisect_right(self._dates, end)
        return self._dates[lo:hi]

    def current_session(self, at=None):
        """已有行情的最近交易日：交易日开盘后为当天，否则为上一交易日。"""
        at = at or now()
        if self.is_trade_day(at.date()) and at.time() >= OPEN_TIME:
            return at.date()
        return self.prev(at.date())

    def closed_session(self, at=None):
        """最近一个已收盘的交易日。"""
        at = at or now()
        if self.is_trade_day(at.date()) and at.time() >= CLOSE_TIME:
            return at.date()
        return self.prev(at.date())


_lock = threading.Lock()
_calendar = None
_loaded_on = None


def get():
    """进程内缓存，每天重新加载一次。"""
    global _calendar, _loaded_on
    with _lock:
        today = now().date()
        if _calendar is None or _loaded_on != today:
            _calendar = TradeCalendar(_load(today))
            _loaded_on = today
        return _calendar


def _load(today):
    cache = config.CACHE_DIR / 'calendar.json'
    if cache.is_file() and datetime.date.fromtimestamp(cache.stat().st_mtime) == today:
        return [datetime.date.fromisoformat(d) for d in json.loads(cache.read_text())]
    try:
        dates = sina.trade_dates()
        config.ensure_dirs()
        cache.write_text(json.dumps([d.isoformat() for d in dates]))
        return dates
    except Exception as e:
        log.warning('获取交易日历失败：%s', e)
    if cache.is_file():
        return [datetime.date.fromisoformat(d) for d in json.loads(cache.read_text())]
    log.error('无可用交易日历，临时按工作日处理（不识别节假日）')
    start = datetime.date(2000, 1, 1)
    return [start + datetime.timedelta(days=i) for i in range((datetime.date(today.year + 1, 12, 31) - start).days)
            if (start + datetime.timedelta(days=i)).weekday() < 5]
