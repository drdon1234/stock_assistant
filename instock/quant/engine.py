"""日线回测引擎，撮合与账户语义尽量与聚宽一致。

- 时间：每个交易日依次为 09:00 盘前、09:30 开盘、各定时时刻、15:00 收盘、15:30 盘后。日线数据只有开盘价和收盘价，
  12:00 之前的时刻按开盘价撮合与显示最新价，12:00 之后按收盘价（例如常见的 14:50 尾盘交易）。
- 未来数据：history/attribute_history/get_bars 不含当天；get_price 在收盘（15:00）之后才能取到当天。
- 价格：按真实价格（不复权）撮合；行情接口默认按“回测当天”动态前复权，与聚宽 use_real_price 一致。
- 交易规则：T+1，买入按手（100 股，科创板至少 200 股），停牌不能交易，开盘/收盘价处于涨停不能买、跌停不能卖，
  单笔成交量不超过当日成交量 × order_volume_ratio；资金不足时按可用资金下单。
- 费用：默认佣金万三（最低 5 元），印花税按历年税率卖出单边收取（2008-09-19 前为双边），可用 set_order_cost 覆盖。
- 分红送转：除权日开盘前处理。复权因子变化 ≥10% 视为送转股（增加股数），否则视为现金分红（红利计入现金，不扣税）。
"""
import datetime
import math
import time

import numpy as np
import pandas as pd

BEFORE_OPEN, OPEN, NOON, CLOSE, AFTER_CLOSE = 540, 570, 720, 900, 930
_TIME_NAMES = {'before_open': BEFORE_OPEN, 'open': OPEN, 'every_bar': OPEN, 'close': CLOSE,
               'after_close': AFTER_CLOSE}
_RISK_FREE = 0.04  # 无风险利率，与聚宽相同
_DAYS_PER_YEAR = 250
_LOG_LIMIT = 5000
_TRADE_LIMIT = 50000


class NotSupported(Exception):
    """调用了兼容层尚未支持的聚宽功能。"""


class StrategyError(Exception):
    """策略代码有误（参数非法等），信息直接展示给用户。"""


def parse_time(value):
    """run_daily 的 time 参数转为当天的分钟数。"""
    text = str(value).strip().lower()
    if text in _TIME_NAMES:
        return _TIME_NAMES[text]
    try:
        hour, minute = text.split(':')[:2]
        return int(hour) * 60 + int(minute)
    except ValueError:
        raise StrategyError(f'无法识别的时间：{value!r}，应为 open/close/before_open/after_close 或 HH:MM') from None


def to_date(value):
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, np.datetime64):
        return pd.Timestamp(value).date()
    return pd.Timestamp(str(value)).date()


def normalize_code(code):
    """补全聚宽代码后缀：6/9 开头为上交所，其余为深交所。"""
    code = str(code).strip()
    if '.' in code:
        num, market = code.split('.', 1)
        market = market.upper()
        market = {'SH': 'XSHG', 'SS': 'XSHG', 'SZ': 'XSHE'}.get(market, market)
        if num.lower() in ('sh', 'sz'):  # sh.600000 写法
            num, market = market, 'XSHG' if num.lower() == 'sh' else 'XSHE'
        return f'{num}.{market}'
    if code[:2].lower() in ('sh', 'sz') and code[2:].isdigit():
        return f"{code[2:]}.{'XSHG' if code[:2].lower() == 'sh' else 'XSHE'}"
    return f"{code}.{'XSHG' if code.startswith(('6', '9', '5')) else 'XSHE'}"


class OrderCost:
    def __init__(self, open_tax=0.0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003,
                 close_today_commission=0.0, min_commission=5.0):
        self.open_tax, self.close_tax = float(open_tax), float(close_tax)
        self.open_commission, self.close_commission = float(open_commission), float(close_commission)
        self.close_today_commission, self.min_commission = float(close_today_commission), float(min_commission)


class PerTrade(OrderCost):
    """旧版 set_commission 的参数：sell_cost 已含印花税。"""

    def __init__(self, buy_cost=0.0003, sell_cost=0.0013, min_cost=5.0):
        super().__init__(0.0, 0.0, buy_cost, sell_cost, 0.0, min_cost)


class FixedSlippage:
    """固定滑点：买入价加 value/2，卖出价减 value/2。"""

    def __init__(self, value):
        self.value = float(value)

    def apply(self, price, is_buy):
        return price + self.value / 2 if is_buy else price - self.value / 2


class PriceRelatedSlippage:
    """百分比滑点：买入价乘以 1 + ratio/2，卖出价乘以 1 - ratio/2。"""

    def __init__(self, ratio=0.00246):
        self.ratio = float(ratio)

    def apply(self, price, is_buy):
        return price * (1 + self.ratio / 2) if is_buy else price * (1 - self.ratio / 2)


class MarketOrderStyle:
    def __init__(self, limit_price=None):
        self.limit_price = limit_price


class LimitOrderStyle:
    def __init__(self, limit_price):
        self.limit_price = float(limit_price)


class OrderStatus:
    open = 'open'
    filled = 'filled'
    canceled = 'canceled'
    rejected = 'rejected'
    held = 'held'


class Order:
    def __init__(self, order_id, security, amount, is_buy, add_time, style):
        self.order_id = order_id
        self.security = security
        self.amount = amount
        self.filled = 0
        self.price = 0.0
        self.avg_cost = 0.0
        self.is_buy = is_buy
        self.side = 'long'
        self.action = 'open' if is_buy else 'close'
        self.add_time = add_time
        self.status = OrderStatus.open
        self.commission = 0.0
        self.style = style

    def __repr__(self):
        return (f'Order(id={self.order_id}, {self.security}, {"买入" if self.is_buy else "卖出"} {self.filled}/'
                f'{self.amount}, price={self.price:.3f}, status={self.status})')


class Trade:
    def __init__(self, trade_id, order_id, security, amount, price, time_):
        self.trade_id, self.order_id, self.security = trade_id, order_id, security
        self.amount, self.price, self.time = amount, price, time_


class Position:
    def __init__(self, security, init_time):
        self.security = security
        self.price = 0.0
        self.avg_cost = 0.0
        self.acc_avg_cost = 0.0
        self.hold_cost = 0.0
        self.init_time = init_time
        self.transact_time = init_time
        self.total_amount = 0
        self.closeable_amount = 0
        self.today_amount = 0
        self.locked_amount = 0
        self.side = 'long'
        self.pindex = 0

    @property
    def amount(self):
        return self.total_amount

    @property
    def value(self):
        return self.total_amount * self.price

    def __repr__(self):
        return (f'Position({self.security}, total={self.total_amount}, closeable={self.closeable_amount}, '
                f'avg_cost={self.avg_cost:.3f}, price={self.price:.3f})')


class Positions(dict):
    """持仓字典；访问没有持仓的证券时返回一个空仓位（不加入字典），与聚宽一致。"""

    def __missing__(self, key):
        return Position(key, None)


class Portfolio:
    def __init__(self, cash):
        self.starting_cash = float(cash)
        self.available_cash = float(cash)
        self.positions = Positions()
        self.short_positions = {}
        self.locked_cash = 0.0
        self.margin = 0.0
        self.inout_cash = 0.0

    long_positions = property(lambda self: self.positions)
    cash = property(lambda self: self.available_cash)
    transferable_cash = property(lambda self: self.available_cash)
    subportfolios = property(lambda self: [self])

    @property
    def positions_value(self):
        return sum(p.value for p in self.positions.values())

    @property
    def total_value(self):
        return self.available_cash + self.positions_value

    @property
    def returns(self):
        return self.total_value / self.starting_cash - 1


class RunParams:
    def __init__(self, start, end):
        self.start_date, self.end_date = start, end
        self.type = 'simple_backtest'
        self.frequency = 'day'


class Context:
    def __init__(self, portfolio, run_params):
        self.portfolio = portfolio
        self.subportfolios = [portfolio]
        self.run_params = run_params
        self.current_dt = None
        self.previous_date = None
        self.universe = []


def _default_cost(day):
    """历年 A 股股票交易费用：佣金万三最低 5 元；印花税 2008-04-24 前 3‰ 双边，此后 1‰，
    2008-09-19 起仅卖出收取，2023-08-28 起减半为 0.5‰。"""
    if day < datetime.date(2008, 4, 24):
        return OrderCost(0.003, 0.003)
    if day < datetime.date(2008, 9, 19):
        return OrderCost(0.001, 0.001)
    if day < datetime.date(2023, 8, 28):
        return OrderCost(0.0, 0.001)
    return OrderCost(0.0, 0.0005)


class Backtest:
    def __init__(self, panel, securities, members, trade_days, start, end, capital, benchmark='000300.XSHG',
                 progress=None):
        self.panel = panel
        self.securities = securities.set_index('code') if 'code' in securities.columns else securities
        self.members = members
        self.trade_days = trade_days
        start, end = to_date(start), to_date(end)
        dates = panel.dates
        r0 = int(np.searchsorted(dates, np.datetime64(start, 'D')))
        r1 = int(np.searchsorted(dates, np.datetime64(end, 'D'), side='right')) - 1
        if r0 >= len(dates) or r1 < r0:
            raise StrategyError(f'{start} ~ {end} 之间没有交易日数据（数据范围 {dates[0]} ~ {dates[-1]}）')
        self.r_start, self.r_end = r0, r1
        self.start, self.end = start, end
        self.capital = float(capital)
        self.benchmark = benchmark
        self.progress = progress
        self.portfolio = Portfolio(capital)
        self.context = Context(self.portfolio, RunParams(start, end))
        self.r = r0
        self.minute = None  # None：initialize 阶段
        self.order_cost = None  # None：按年份使用默认费用
        self.slippage = None
        self.volume_ratio = 1.0
        self.events = []  # (minute, seq, kind, func, arg, force)
        self.orders_today, self.trades_today = {}, {}
        self._order_seq = 0
        self.logs, self.logs_dropped = [], 0
        self.trades = []
        self.records = {}
        self.daily = []
        self._wins = self._closed = 0
        self._gain = self._loss = 0.0
        self._warned = set()
        self._calendar_marks()

    # ---------- 时间与日志 ----------

    @property
    def today(self):
        return pd.Timestamp(self.panel.dates[self.r]).date()

    def now(self):
        minute = BEFORE_OPEN if self.minute is None else self.minute
        return datetime.datetime.combine(self.today, datetime.time(minute // 60, minute % 60))

    def log(self, level, message):
        if len(self.logs) >= _LOG_LIMIT:
            self.logs_dropped += 1
            return
        self.logs.append(f'{self.now():%Y-%m-%d %H:%M:%S} - {level:<5} - {message}')

    def warn_once(self, key, message):
        if key not in self._warned:
            self._warned.add(key)
            self.log('WARN', message)

    def _calendar_marks(self):
        """每个交易日在所在周、月中的序号与当周/当月交易日数，用于 run_weekly / run_monthly。"""
        dates = pd.DatetimeIndex(self.panel.dates)
        iso = dates.isocalendar()
        for name, key in (('week', iso['year'].to_numpy() * 100 + iso['week'].to_numpy()),
                          ('month', dates.year.to_numpy() * 100 + dates.month.to_numpy())):
            pos = np.zeros(len(dates), dtype=int)
            size = np.zeros(len(dates), dtype=int)
            start = 0
            for i in range(1, len(dates) + 1):
                if i == len(dates) or key[i] != key[start]:
                    pos[start:i] = np.arange(i - start)
                    size[start:i] = i - start
                    start = i
            setattr(self, f'_{name}_pos', pos)
            setattr(self, f'_{name}_size', size)

    def _due(self, kind, n, force):
        """定时任务今天是否执行：n 为第几个交易日（从 1 开始，负数从末尾数）。"""
        if kind == 'daily':
            return True
        pos, size = getattr(self, f'_{kind}_pos')[self.r], getattr(self, f'_{kind}_size')[self.r]
        target = n - 1 if n > 0 else size + n
        if 0 <= target < size:
            return pos == target
        if not force:
            return False
        return pos == (size - 1 if target >= size else 0)

    # ---------- 行情 ----------

    def visible_row(self):
        """已收盘、可以无未来函数地读取的最后一行。"""
        return self.r if self.minute is not None and self.minute >= CLOSE else self.r - 1

    def bar(self, field, code, r=None):
        return self.panel.value(field, self.r if r is None else r, code)

    def current_price(self, code):
        """当前时刻的最新价：盘前为昨收，12:00 前为开盘价，之后为收盘价。"""
        if self.minute is None or self.minute < OPEN:
            return self.bar('pre_close', code)
        return self.bar('open' if self.minute < NOON else 'close', code)

    def security_name(self, code):
        if code in self.securities.index:
            return self.securities.at[code, 'display_name']
        return code

    # ---------- 交易 ----------

    def cost_for_today(self):
        return self.order_cost or _default_cost(self.today)

    def _reject(self, code, message):
        self.log('WARN', f'{code} 下单失败：{message}')
        return None

    def order(self, security, amount, style=None):
        """按股数下单，amount 为正买入、负卖出。成功返回 Order，失败返回 None（原因写入日志）。"""
        code = normalize_code(security)
        amount = int(amount)
        if amount == 0:
            return None
        if self.minute is None or self.minute >= AFTER_CLOSE:
            return self._reject(code, '只能在盘前至收盘之间下单')
        if code not in self.panel.col:
            return self._reject(code, '没有该证券的数据')
        if code in self.securities.index and self.securities.at[code, 'type'] == 'index':
            return self._reject(code, '指数不能交易')
        close = self.bar('close', code)
        if math.isnan(close):
            return self._reject(code, '当日未上市或已退市')
        if self.bar('paused', code):
            return self._reject(code, '停牌')
        price = self.bar('open' if self.minute < NOON else 'close', code)
        high, low = self.bar('high_limit', code), self.bar('low_limit', code)
        is_buy = amount > 0
        if is_buy and not math.isnan(high) and price >= high - 1e-6:
            return self._reject(code, f'涨停（{price:.2f}）无法买入')
        if not is_buy and not math.isnan(low) and price <= low + 1e-6:
            return self._reject(code, f'跌停（{price:.2f}）无法卖出')
        limit = getattr(style, 'limit_price', None)
        if isinstance(style, LimitOrderStyle) and limit is not None:
            if (is_buy and price > limit + 1e-9) or (not is_buy and price < limit - 1e-9):
                return self._reject(code, f'限价 {limit} 未成交（成交价 {price:.2f}）')
        if self.slippage is not None:
            price = self.slippage.apply(price, is_buy)
            if not math.isnan(high):
                price = min(price, high)
            if not math.isnan(low):
                price = max(price, low)
        volume_cap = int(self.bar('volume', code) * self.volume_ratio)
        star = code.startswith('688')
        cost = self.cost_for_today()
        order = Order(self._next_id(), code, abs(amount), is_buy, self.now(), style)
        if is_buy:
            filled = self._buy_amount(amount, price, volume_cap, star, cost)
            if filled <= 0:
                return self._reject(code, '可用资金不足或不足一手')
            value = filled * price
            commission = max(cost.min_commission, value * cost.open_commission)
            tax = value * cost.open_tax
            self.portfolio.available_cash -= value + commission + tax
            pos = self.portfolio.positions.get(code)
            if pos is None:
                pos = self.portfolio.positions[code] = Position(code, self.now())
            total = pos.total_amount + filled
            pos.avg_cost = (pos.avg_cost * pos.total_amount + value) / total
            pos.acc_avg_cost = (pos.acc_avg_cost * pos.total_amount + value + commission + tax) / total
            pos.hold_cost = (pos.hold_cost * pos.total_amount + value + commission + tax) / total
            pos.total_amount = total
            pos.today_amount += filled
            pos.price = price
            pos.transact_time = self.now()
            pnl = None
        else:
            pos = self.portfolio.positions.get(code)
            if pos is None or pos.total_amount <= 0:
                return self._reject(code, '没有持仓')
            filled = min(-amount, pos.closeable_amount, max(volume_cap, 0))
            if filled < pos.total_amount and not code.startswith('688'):
                filled = filled // 100 * 100  # 部分卖出须为整手，清仓时零股可一并卖出
            if filled <= 0:
                reason = '今日买入的股票次日才能卖出（T+1）' if pos.closeable_amount < 100 else '超过当日成交量限制'
                return self._reject(code, reason)
            value = filled * price
            commission = max(cost.min_commission, value * cost.close_commission)
            tax = value * cost.close_tax
            self.portfolio.available_cash += value - commission - tax
            pnl = (price - pos.avg_cost) * filled - commission - tax
            self._closed += 1
            if pnl > 0:
                self._wins += 1
                self._gain += pnl
            else:
                self._loss -= pnl
            pos.total_amount -= filled
            pos.closeable_amount -= filled
            pos.price = price
            pos.transact_time = self.now()
            if pos.total_amount <= 0:
                del self.portfolio.positions[code]
        order.filled, order.price, order.avg_cost = filled, price, price
        order.commission = commission + tax
        order.status = OrderStatus.filled
        self.orders_today[order.order_id] = order
        self.trades_today[order.order_id] = Trade(order.order_id, order.order_id, code, filled, price, self.now())
        if len(self.trades) < _TRADE_LIMIT:
            self.trades.append([f'{self.now():%Y-%m-%d %H:%M}', code, self.security_name(code),
                                '买' if is_buy else '卖', filled, round(price, 4), round(value, 2),
                                round(commission, 2), round(tax, 2), None if pnl is None else round(pnl, 2)])
        return order

    def _buy_amount(self, amount, price, volume_cap, star, cost):
        """实际可买股数：不超过成交量限制与可用资金（含费用），主板/创业板为整百股，科创板至少 200 股。"""
        cash = self.portfolio.available_cash
        if price <= 0:
            return 0

        def affordable(n):
            value = n * price
            return value + max(cost.min_commission, value * cost.open_commission) + value * cost.open_tax <= cash + 1e-6

        step = 1 if star else 100
        n = min(amount, volume_cap, int(cash / (price * (1 + cost.open_commission + cost.open_tax))))
        n = n // step * step
        while n > 0 and not affordable(n):
            n -= step
        return 0 if star and n < 200 else max(n, 0)

    def _next_id(self):
        self._order_seq += 1
        return self._order_seq

    def order_target(self, security, amount, style=None):
        code = normalize_code(security)
        current = self.portfolio.positions.get(code)
        return self.order(code, int(amount) - (current.total_amount if current else 0), style)

    def order_value(self, security, value, style=None):
        code = normalize_code(security)
        price = self._order_price(code)
        if price is None:
            return None
        return self.order(code, int(value / price), style)

    def order_target_value(self, security, value, style=None):
        code = normalize_code(security)
        price = self._order_price(code)
        if price is None:
            return None
        current = self.portfolio.positions.get(code)
        held = current.total_amount if current else 0
        target = int(value / price)
        if value <= 0:
            target = 0
        return self.order(code, target - held, style)

    def _order_price(self, code):
        if self.minute is None or self.minute >= AFTER_CLOSE:
            return self._reject(code, '只能在盘前至收盘之间下单')
        if code not in self.panel.col:
            return self._reject(code, '没有该证券的数据')
        price = self.bar('open' if self.minute < NOON else 'close', code)
        if math.isnan(price) or price <= 0:
            return self._reject(code, '当日没有行情')
        return price

    # ---------- 每日流程 ----------

    def _corporate_actions(self):
        """除权除息与退市：在开盘前调整持仓。"""
        r = self.r
        for code, pos in list(self.portfolio.positions.items()):
            close = self.bar('close', code)
            if math.isnan(close):
                value = pos.total_amount * pos.price
                self.portfolio.available_cash += value
                del self.portfolio.positions[code]
                self.log('WARN', f'{code} 已退市，按最后价格 {pos.price:.2f} 清算 {pos.total_amount} 股，得 {value:.2f} 元')
                continue
            f_prev, f_now = self.bar('factor', code, r - 1), self.bar('factor', code, r)
            if math.isnan(f_prev) or math.isnan(f_now) or abs(f_now / f_prev - 1) < 1e-6:
                continue
            ratio = f_now / f_prev
            pre_close = self.bar('pre_close', code)
            if ratio >= 1.1:
                shares = pos.total_amount * ratio
                whole = int(shares + 1e-6)  # 因子由价格算出，10 送 10 的比例可能是 1.9999999
                self.portfolio.available_cash += (shares - whole) * pre_close
                pos.closeable_amount = int(pos.closeable_amount * ratio + 1e-6)
                pos.total_amount = whole
                for attr in ('avg_cost', 'acc_avg_cost', 'hold_cost', 'price'):
                    setattr(pos, attr, getattr(pos, attr) / ratio)
                self.log('INFO', f'{code} 送转股：每股变为 {ratio:.4f} 股，持仓 {whole} 股')
            else:
                per_share = self.bar('close', code, r - 1) - pre_close
                cash = per_share * pos.total_amount
                self.portfolio.available_cash += cash
                self.log('INFO', f'{code} 分红：每股 {per_share:.4f} 元，共 {cash:.2f} 元')

    def _run_events(self, until, handle_data, data):
        """执行时间不晚于 until 的、尚未执行的事件。"""
        while self._pending and self._pending[0][0] <= until:
            minute, _, kind, func, arg, force = self._pending.pop(0)
            self.minute = minute
            if func == '__handle_data__':
                handle_data(self.context, data)
            elif kind in ('callback',):
                func(self.context)
            elif self._due(kind, arg, force):
                func(self.context)

    def run(self, ns):
        """执行策略。ns 为策略代码执行后的命名空间（含 initialize 等函数）。"""
        started = time.monotonic()
        initialize = ns.get('initialize')
        if not callable(initialize):
            raise StrategyError('策略中没有 initialize(context) 函数')
        self._set_day(self.r_start)
        self.minute = None
        initialize(self.context)
        if callable(ns.get('process_initialize')):
            ns['process_initialize'](self.context)
        handle_data = ns.get('handle_data')
        before, after = ns.get('before_trading_start'), ns.get('after_trading_end')
        total = self.r_end - self.r_start + 1
        for n, r in enumerate(range(self.r_start, self.r_end + 1)):
            self._set_day(r)
            self.minute = BEFORE_OPEN
            if r > self.r_start:
                self._corporate_actions()
            for pos in self.portfolio.positions.values():
                pos.closeable_amount = pos.total_amount
                pos.today_amount = 0
            self.orders_today, self.trades_today = {}, {}
            pending = []
            if callable(before):
                pending.append((BEFORE_OPEN, -1, 'callback', before, None, False))
            pending += [e for e in self.events]
            if callable(handle_data):
                pending.append((OPEN, 1 << 30, 'daily', '__handle_data__', None, False))
            if callable(after):
                pending.append((AFTER_CLOSE, 1 << 30, 'callback', after, None, False))
            self._pending = sorted(pending, key=lambda e: (e[0], e[1]))
            data = _BarData(self)
            self._run_events(AFTER_CLOSE, handle_data, data)
            self.minute = AFTER_CLOSE
            self._settle()
            if self.progress and (n % 20 == 0 or r == self.r_end):
                self.progress((n + 1) / total, self.today)
        if callable(ns.get('on_strategy_end')):
            ns['on_strategy_end'](self.context)
        return self.result(time.monotonic() - started)

    def _set_day(self, r):
        self.r = r
        self.context.current_dt = self.now()
        self.context.previous_date = pd.Timestamp(self.panel.dates[r - 1]).date() if r > 0 else None

    def _settle(self):
        positions = self.portfolio.positions
        if positions:
            codes = list(positions)
            closes = self.panel.block('close', self.r, self.r + 1, self.panel.cols(codes))[0]
            for code, close in zip(codes, closes):
                if not math.isnan(close):
                    positions[code].price = close
        bench = self.bar('close', self.benchmark) if self.benchmark in self.panel.col else np.nan
        self.daily.append((self.today, self.portfolio.total_value, self.portfolio.available_cash, bench))

    def record(self, **kwargs):
        day = self.today.isoformat()
        for key, value in kwargs.items():
            try:
                self.records.setdefault(str(key), {})[day] = None if value is None else float(value)
            except (TypeError, ValueError):
                raise StrategyError(f'record 的值必须是数字：{key}={value!r}') from None

    # ---------- 结果 ----------

    def result(self, elapsed):
        dates = [d.isoformat() for d, *_ in self.daily]
        values = np.array([v for _, v, _, _ in self.daily])
        cash = np.array([c for _, _, c, _ in self.daily])
        bench = np.array([b for *_, b in self.daily], dtype=float)
        bench_base = self.bar('pre_close', self.benchmark, self.r_start) if self.benchmark in self.panel.col else np.nan
        if math.isnan(bench_base) and len(bench):
            bench_base = bench[0]
        bench_curve = bench / bench_base - 1 if bench_base and not math.isnan(bench_base) else np.full(len(bench), np.nan)
        curve = values / self.capital - 1
        peak = np.maximum.accumulate(np.concatenate([[self.capital], values]))[1:]
        drawdown = values / peak - 1
        summary = metrics(values, self.capital, bench, bench_base, dates)
        summary.update({
            'trades': len(self.trades), 'closed_trades': self._closed,
            'win_ratio': self._wins / self._closed if self._closed else None,
            'profit_loss_ratio': self._gain / self._loss if self._loss > 0 else None,
            'final_value': float(values[-1]) if len(values) else self.capital,
        })
        series = {k: [v.get(d) for d in dates] for k, v in self.records.items()}
        positions = [{'code': c, 'name': self.security_name(c), 'amount': p.total_amount,
                      'avg_cost': round(p.avg_cost, 4), 'price': round(p.price, 4), 'value': round(p.value, 2)}
                     for c, p in self.portfolio.positions.items()]
        rounded = lambda arr, d=6: [None if not np.isfinite(x) else round(float(x), d) for x in arr]  # noqa: E731
        return {
            'summary': summary,
            'daily': {'dates': dates, 'value': rounded(values, 2), 'cash': rounded(cash, 2),
                      'returns': rounded(curve), 'benchmark': rounded(bench_curve), 'drawdown': rounded(drawdown)},
            'records': series,
            'trades': self.trades,
            'trades_truncated': len(self.trades) >= _TRADE_LIMIT,
            'positions': positions,
            'logs': self.logs,
            'logs_dropped': self.logs_dropped,
            'elapsed': round(elapsed, 2),
        }


def metrics(values, capital, bench, bench_base, dates):
    """收益风险指标（口径参考聚宽：年化按 250 个交易日，无风险利率 4%）。"""
    n = len(values)
    out = {'days': n, 'start': dates[0] if dates else None, 'end': dates[-1] if dates else None}
    if not n:
        return out
    prev = np.concatenate([[capital], values[:-1]])
    r = values / prev - 1
    total = values[-1] / capital - 1
    annual = (1 + total) ** (_DAYS_PER_YEAR / n) - 1 if total > -1 else -1.0
    vol = float(np.std(r, ddof=1) * math.sqrt(_DAYS_PER_YEAR)) if n > 1 else 0.0
    downside = r[r < 0]
    down_vol = float(np.sqrt(np.mean(downside ** 2)) * math.sqrt(_DAYS_PER_YEAR)) if downside.size else 0.0
    peak = np.maximum.accumulate(np.concatenate([[capital], values]))
    dd = np.concatenate([[capital], values]) / peak - 1
    end_i = int(np.argmin(dd))
    start_i = int(np.argmax(np.concatenate([[capital], values])[:end_i + 1])) if end_i else 0
    out.update({
        'total_return': float(total), 'annual_return': float(annual), 'volatility': vol,
        'sharpe': float((annual - _RISK_FREE) / vol) if vol > 0 else None,
        'sortino': (annual - _RISK_FREE) / down_vol if down_vol > 0 else None,
        'max_drawdown': max(0.0, float(-dd[end_i])),
        'max_drawdown_start': dates[max(start_i - 1, 0)] if end_i else None,
        'max_drawdown_end': dates[end_i - 1] if end_i else None,
    })
    if bench_base and not math.isnan(bench_base) and np.isfinite(bench).all():
        b_prev = np.concatenate([[bench_base], bench[:-1]])
        rb = bench / b_prev - 1
        b_total = bench[-1] / bench_base - 1
        b_annual = (1 + b_total) ** (_DAYS_PER_YEAR / n) - 1 if b_total > -1 else -1.0
        var_b = float(np.var(rb, ddof=1)) if n > 1 else 0.0
        beta = float(np.cov(r, rb, ddof=1)[0, 1] / var_b) if var_b > 0 else None
        excess = r - rb
        te = float(np.std(excess, ddof=1) * math.sqrt(_DAYS_PER_YEAR)) if n > 1 else 0.0
        out.update({
            'benchmark_return': float(b_total), 'benchmark_annual_return': float(b_annual), 'beta': beta,
            'alpha': float(annual - (_RISK_FREE + beta * (b_annual - _RISK_FREE))) if beta is not None else None,
            'information_ratio': float(np.mean(excess) * _DAYS_PER_YEAR / te) if te > 0 else None,
            'excess_return': float((1 + total) / (1 + b_total) - 1),
            'daily_win_ratio': float(np.mean(r > rb)),
        })
    return out


class _Bar:
    """handle_data 的 data[security]：前一交易日的日线（避免未来函数）。"""

    def __init__(self, bt, code):
        r = bt.r - 1
        self._bt, self.security = bt, code
        for f in ('open', 'close', 'high', 'low', 'volume', 'money', 'factor', 'high_limit', 'low_limit',
                  'pre_close'):
            setattr(self, f, bt.bar(f, code, r) if r >= 0 else np.nan)
        self.paused = bool(bt.bar('paused', code, r)) if r >= 0 else True
        self.avg = self.money / self.volume if self.volume else np.nan
        self.price = self.avg

    def _hist(self, days, field):
        from instock.quant import jqapi
        return jqapi.Api(self._bt).attribute_history(self.security, days, '1d', [field], df=False)[field]

    def mavg(self, days, field='close'):
        return float(np.nanmean(self._hist(days, field)))

    def vwap(self, days):
        money, volume = self._hist(days, 'money'), self._hist(days, 'volume')
        return float(np.nansum(money) / np.nansum(volume)) if np.nansum(volume) else np.nan

    def stddev(self, days):
        return float(np.nanstd(self._hist(days, 'close'), ddof=1))

    def returns(self):
        return self.close / self.pre_close - 1 if self.pre_close else np.nan


class _BarData(dict):
    def __init__(self, bt):
        super().__init__()
        self._bt = bt

    def __missing__(self, key):
        code = normalize_code(key)
        value = self[key] = _Bar(self._bt, code)
        return value
