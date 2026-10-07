import logging
import sys
from logging.handlers import RotatingFileHandler

from instock import config


def setup(name, level=logging.INFO):
    """日志同时写 data/log/<name>.log（滚动）和标准错误，便于 docker logs 查看。"""
    config.ensure_dirs()
    fmt = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
    file_handler = RotatingFileHandler(config.LOG_DIR / f'{name}.log', maxBytes=10 * 1024 * 1024,
                                       backupCount=5, encoding='utf-8')
    stream_handler = logging.StreamHandler(sys.stderr)
    root = logging.getLogger()
    root.handlers.clear()
    for handler in (file_handler, stream_handler):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    root.setLevel(level)
    for noisy in ('urllib3', 'tornado.access'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
