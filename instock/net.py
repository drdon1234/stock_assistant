"""带限流、熔断、重试和代理轮换的 HTTP 客户端。

每个数据源独立一套策略：
- 节流：请求间隔 = 1/rate 并加 ±随机抖动，避免固定频率特征；
- 并发：同一数据源同时在途请求数受限；
- 重试：网络错误、429、5xx 指数退避重试；
- 熔断：连续失败达到阈值后，冷却期内直接失败，交由调用方切换备用数据源，避免继续加重封禁。
速率可用环境变量覆盖，如 INSTOCK_RATE_EM_HIST=2。
"""
import itertools
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter

from instock import config

log = logging.getLogger(__name__)

USER_AGENTS = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
)


class FetchError(Exception):
    """数据源熔断中，或重试后仍失败。"""


@dataclass(frozen=True)
class Policy:
    rate: float  # 每秒请求数
    concurrency: int  # 同时在途请求数
    headers: dict = field(default_factory=dict)
    retries: int = 3
    timeout: float = 15
    fail_threshold: int = 5  # 连续失败多少次后熔断
    cooldown: float = 600  # 熔断冷却秒数


POLICIES = {
    # push2 列表接口（只用于资金流向）最易被封，失败 3 次即熔断 30 分钟，期间降级为新浪/选股器数据
    'em_quote': Policy(2, 2, {'Referer': 'https://quote.eastmoney.com/'}, fail_threshold=3, cooldown=1800),
    # 数据中心/选股器连续几十次请求（约每秒 2.5 次）也会封 IP，限速 1 次/秒
    'em_data': Policy(1, 1, {'Referer': 'https://data.eastmoney.com/'}, timeout=30),
    'tencent': Policy(5, 4, {'Referer': 'https://gu.qq.com/'}),
    'sina': Policy(2, 2, {'Referer': 'https://finance.sina.com.cn/'}),
    'ths': Policy(3, 3, {'Referer': 'http://zx.10jqka.com.cn/'}),
    'tdx': Policy(1, 1, {'User-Agent': USER_AGENTS[0] + ' TdxW'}),
}


class _Throttle:
    def __init__(self, rate):
        self._interval = 1.0 / rate
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            at = max(now, self._next_at)
            self._next_at = at + self._interval * random.uniform(0.8, 1.3)
        if at > now:
            time.sleep(at - now)


class _Breaker:
    def __init__(self, name, threshold, cooldown):
        self._name = name
        self._threshold = threshold
        self._cooldown = cooldown
        self._failures = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def check(self):
        if time.monotonic() < self._open_until:
            raise FetchError(f'{self._name} 熔断中')

    def success(self):
        with self._lock:
            self._failures = 0

    def failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._failures = 0
                self._open_until = time.monotonic() + self._cooldown
                log.warning('%s 连续失败，熔断 %d 秒', self._name, self._cooldown)


class _ProxyPool:
    def __init__(self, proxies):
        self._proxies = [p if '://' in p else f'http://{p}' for p in proxies]
        self._cycle = itertools.cycle(self._proxies)
        self._bad_until = {}
        self._lock = threading.Lock()

    def pick(self):
        """轮换取一个未被标记失效的代理；全部失效或未配置时直连。"""
        with self._lock:
            now = time.monotonic()
            for _ in range(len(self._proxies)):
                proxy = next(self._cycle)
                if self._bad_until.get(proxy, 0) <= now:
                    return proxy
        return None

    def mark_bad(self, proxy):
        with self._lock:
            self._bad_until[proxy] = time.monotonic() + 600


class _Retryable(Exception):
    pass


class _Source:
    def __init__(self, name, policy, proxy_pool):
        rate = float(os.environ.get(f'INSTOCK_RATE_{name.upper()}', policy.rate))
        self.name = name
        self.policy = policy
        self._throttle = _Throttle(rate)
        self._slots = threading.BoundedSemaphore(policy.concurrency)
        self._breaker = _Breaker(name, policy.fail_threshold, policy.cooldown)
        self._proxies = proxy_pool
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=policy.concurrency * 2)
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)
        self._session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            # 不声明 br/zstd：未安装解压库时 requests 无法解码
            'Accept-Encoding': 'gzip, deflate',
        })
        self._session.headers.update(policy.headers)
        if name.startswith('em_'):
            cookie = config.eastmoney_cookie()
            if cookie:
                self._session.headers['Cookie'] = cookie

    def request(self, method, url, **kwargs):
        self._breaker.check()
        error = None
        for attempt in range(self.policy.retries):
            if attempt:
                time.sleep(min(30.0, 2.0 ** attempt) * random.uniform(1.0, 1.5))
            proxy = self._proxies.pick()
            with self._slots:
                self._throttle.wait()
                try:
                    r = self._session.request(method, url, timeout=self.policy.timeout,
                                              proxies={'http': proxy, 'https': proxy} if proxy else None, **kwargs)
                    if r.status_code == 429 or r.status_code >= 500:
                        raise _Retryable(f'HTTP {r.status_code}')
                    r.raise_for_status()
                except requests.HTTPError as e:
                    # 其余 4xx 是请求本身的问题，重试无益
                    raise FetchError(f'{self.name} {url}: {e}') from e
                except (requests.RequestException, _Retryable) as e:
                    error = e
                    if proxy and isinstance(e, (requests.ConnectionError, requests.Timeout)):
                        self._proxies.mark_bad(proxy)
                    continue
            self._breaker.success()
            return r
        self.failed()
        raise FetchError(f'{self.name} {url}: {error}')

    def failed(self):
        self._breaker.failure()


_sources = {}
_sources_lock = threading.Lock()
_proxy_pool = None


def _source(name):
    global _proxy_pool
    with _sources_lock:
        if name not in _sources:
            if _proxy_pool is None:
                _proxy_pool = _ProxyPool(config.proxies())
            _sources[name] = _Source(name, POLICIES[name], _proxy_pool)
        return _sources[name]


def get(source, url, params=None, headers=None):
    return _source(source).request('GET', url, params=params, headers=headers)


def _json(source, response):
    try:
        return response.json()
    except ValueError as e:  # 被限流时常返回 200 的 HTML 页面
        _source(source).failed()
        raise FetchError(f'{source} 返回非 JSON：{response.text[:80]!r}') from e


def get_json(source, url, params=None, headers=None):
    return _json(source, get(source, url, params, headers))


def post_json(source, url, json=None, headers=None):
    return _json(source, _source(source).request('POST', url, json=json, headers=headers))
