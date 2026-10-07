"""运行配置。全部来自环境变量，未设置时使用开箱即用的默认值。"""
import os
from pathlib import Path

from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('INSTOCK_DATA_DIR', ROOT_DIR / 'data')).resolve()
CACHE_DIR = DATA_DIR / 'cache'
HIST_DIR = CACHE_DIR / 'hist'
LOG_DIR = DATA_DIR / 'log'
PROXY_FILE = DATA_DIR / 'proxy.txt'
COOKIE_FILE = DATA_DIR / 'eastmoney_cookie.txt'


def _env_int(name, default):
    value = os.environ.get(name)
    return int(value) if value else default


def _db_url():
    """INSTOCK_DB_URL 优先；其次 MYSQL_* 拼 MySQL/MariaDB 连接；都没有则用本地 SQLite。"""
    url = os.environ.get('INSTOCK_DB_URL')
    if url:
        return url
    host = os.environ.get('MYSQL_HOST')
    if host:
        # 用 URL.create 转义用户名和密码，密码含 @ / # 等字符时也能连接
        return URL.create('mysql+pymysql', username=os.environ.get('MYSQL_USER', 'root'),
                          password=os.environ.get('MYSQL_PASSWORD', ''), host=host,
                          port=int(os.environ.get('MYSQL_PORT', '3306')),
                          database=os.environ.get('MYSQL_DATABASE', 'instockdb'),
                          query={'charset': 'utf8mb4'}).render_as_string(hide_password=False)
    return f"sqlite:///{(DATA_DIR / 'instock.db').as_posix()}"


DB_URL = _db_url()

WEB_HOST = os.environ.get('INSTOCK_WEB_HOST', '0.0.0.0')
WEB_PORT = _env_int('INSTOCK_WEB_PORT', 9988)
# 部署在反向代理（Nginx 等）之后时设为 1：按 X-Forwarded-For/-Proto 识别客户端 IP 与 HTTPS
TRUST_PROXY = os.environ.get('INSTOCK_TRUST_PROXY', '').lower() in ('1', 'true', 'yes')
# 登录凭证有效天数；每天首次使用时自动续期，期间内访问过就不必重新登录
SESSION_DAYS = _env_int('INSTOCK_SESSION_DAYS', 90)
# 启动时若该账号不存在则创建为管理员（可选，也可用 python -m instock user add 创建）
ADMIN_USER = os.environ.get('INSTOCK_ADMIN_USER', '').strip()
ADMIN_PASSWORD = os.environ.get('INSTOCK_ADMIN_PASSWORD', '')

# 分析计算的进程数，CPU 核数少的机器可调小
ANALYSIS_WORKERS = _env_int('INSTOCK_WORKERS', max(1, (os.cpu_count() or 2) - 1))
# 首次抓取历史 K 线的年数；之后按日增量追加
HIST_YEARS = _env_int('INSTOCK_HIST_YEARS', 3)

# 聚宽兼容回测：历史数据（不复权日线、复权因子、停牌、ST、指数成分）与回测任务都放在 QUANT_DIR
QUANT_DIR = DATA_DIR / 'quant'
QUANT_START = os.environ.get('INSTOCK_QUANT_START', '2005-01-01')  # 回补历史数据的起始日期
QUANT_WORKERS = _env_int('INSTOCK_QUANT_WORKERS', 4)  # 回补时同时连接 BaoStock 的进程数
QUANT_TIMEOUT = _env_int('INSTOCK_QUANT_TIMEOUT', 1800)  # 单个回测最长运行秒数
QUANT_MEMORY_MB = _env_int('INSTOCK_QUANT_MEMORY_MB', 3072)  # 沙箱中单个回测进程的内存上限
# 回测运行器是否以沙箱方式执行策略代码（docker-compose 的 instock-backtest 容器中为 1）。
# 只有沙箱模式下普通账号才能提交回测；否则策略代码与服务同权限运行，仅管理员可用
QUANT_SANDBOX = os.environ.get('INSTOCK_QUANT_SANDBOX', '').lower() in ('1', 'true', 'yes')


def eastmoney_cookie():
    cookie = os.environ.get('EAST_MONEY_COOKIE', '').strip()
    if not cookie and COOKIE_FILE.is_file():
        cookie = COOKIE_FILE.read_text(encoding='utf-8').strip()
    return cookie


def proxies():
    """代理列表，每行一个：ip:port 或 user:pass@ip:port。"""
    if not PROXY_FILE.is_file():
        return []
    lines = (line.strip() for line in PROXY_FILE.read_text(encoding='utf-8').splitlines())
    return sorted({line for line in lines if line and not line.startswith('#')})


def ensure_dirs():
    for path in (DATA_DIR, HIST_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
