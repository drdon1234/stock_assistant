"""数据库访问：建库建表与补列、按条件整批替换写入、批量更新、查询。支持 MySQL/MariaDB 与 SQLite。"""
import datetime
import logging
import threading

import pandas as pd
import sqlalchemy as sa

from instock import config
from instock.schema import SA_TABLES, metadata

log = logging.getLogger(__name__)

_engine = None
_engine_lock = threading.Lock()
_TRUE = {True, '1', 'true', 'True', '是'}  # True == 1，数值 1/1.0 也会命中
_FALSE = {False, '0', 'false', 'False', '否'}


def engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            url = sa.engine.make_url(config.DB_URL)
            if url.get_backend_name() == 'sqlite':
                config.ensure_dirs()
                _engine = sa.create_engine(url, connect_args={'check_same_thread': False, 'timeout': 60})
                sa.event.listen(_engine, 'connect', _sqlite_pragmas)
            else:
                _engine = sa.create_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=3600)
        return _engine


def _sqlite_pragmas(conn, _):
    # WAL 允许 Web 读与作业写并发
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.close()


def init():
    """创建数据库（MySQL）和缺失的表；已存在的表补齐新增列，并放宽长度不足的字符列、把整数列改为浮点列
    （库中可能有旧版本建的表）。"""
    url = sa.engine.make_url(config.DB_URL)
    mysql = url.get_backend_name() == 'mysql'
    if mysql:
        # URL.set 把 None 当作"不修改"，要用空串去掉库名，否则库不存在时连不上
        server = sa.create_engine(url.set(database=''))
        with server.begin() as conn:
            conn.execute(sa.text(f'CREATE DATABASE IF NOT EXISTS `{url.database}` '
                                 'CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci'))
        server.dispose()
    eng = engine()
    with eng.connect() as lock_conn:
        if mysql:
            # Web 与调度进程同时启动时串行建表，避免并发 CREATE TABLE 报"表已存在"
            lock_conn.execute(sa.text("SELECT GET_LOCK('instock_init', 300)"))
        try:
            _create_tables(eng, mysql)
        finally:
            if mysql:
                lock_conn.execute(sa.text("SELECT RELEASE_LOCK('instock_init')"))


def _create_tables(eng, mysql):
    metadata.create_all(eng)
    inspector = sa.inspect(eng)
    quote = eng.dialect.identifier_preparer.quote
    for name, table in SA_TABLES.items():
        # MySQL 列名不区分大小写
        existing = {c['name'].lower(): c['type'] for c in inspector.get_columns(name)}
        for column in table.columns:
            sql_type = column.type.compile(dialect=eng.dialect)
            current = existing.get(column.name.lower())
            if current is None:
                action = 'ADD'
            elif mysql and _needs_widen(current, column.type):
                action = 'MODIFY'
            else:
                continue
            with eng.begin() as conn:
                conn.execute(sa.text(f'ALTER TABLE {quote(name)} {action} COLUMN {quote(column.name)} {sql_type}'))
            log.info('表 %s %s 列 %s %s', name, action, column.name, sql_type)


def _needs_widen(current, wanted):
    if isinstance(wanted, sa.String):
        return isinstance(current, sa.String) and (current.length or 0) < wanted.length
    return isinstance(wanted, sa.Float) and isinstance(current, sa.Integer)


def _to_bool(value):
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None


def records(spec, df):
    """按表定义转换类型，返回可直接 executemany 的记录；缺失值统一为 None。"""
    keys = [k for k in spec.key if k in df.columns]
    if keys:
        df = df.dropna(subset=keys).drop_duplicates(keys, keep='last')
    out = {}
    for col in spec.cols:
        if col.name not in df.columns:
            continue
        s = df[col.name]
        if isinstance(col.type, sa.Date):
            s = pd.to_datetime(s.astype(str), errors='coerce', format='mixed').dt.date
        elif isinstance(col.type, sa.Boolean):
            s = s.map(_to_bool)
        elif isinstance(col.type, (sa.BigInteger, sa.SmallInteger)):
            s = pd.to_numeric(s, errors='coerce').round().astype('Int64')
        elif isinstance(col.type, sa.Float):
            s = pd.to_numeric(s, errors='coerce')
        elif isinstance(col.type, sa.String):
            s = s.map(lambda v, n=col.type.length: None if v is None or v != v else str(v)[:n])
        out[col.name] = s
    frame = pd.DataFrame(out).astype(object)
    return frame.where(frame.notna(), None).to_dict('records')


def replace(spec, df, **where):
    """在一个事务内删除 where 匹配的旧数据并写入 df，保证重跑幂等。返回写入行数。"""
    table = SA_TABLES[spec.name]
    rows = records(spec, df)
    with engine().begin() as conn:
        conn.execute(table.delete().where(sa.and_(*(table.c[k] == v for k, v in where.items()))))
        for chunk in _batched(rows, 1000):
            conn.execute(table.insert(), chunk)
    return len(rows)


def _batched(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def update(spec, rows, keys):
    """按主键批量更新部分列，rows 为 dict 列表（含 keys 与要更新的列）。"""
    if not rows:
        return
    table = SA_TABLES[spec.name]
    values = [k for k in rows[0] if k not in keys]
    stmt = (table.update()
            .where(sa.and_(*(table.c[k] == sa.bindparam(f'k_{k}') for k in keys)))
            .values({k: sa.bindparam(f'v_{k}') for k in values}))
    params = [{**{f'k_{k}': r[k] for k in keys}, **{f'v_{k}': r[k] for k in values}} for r in rows]
    with engine().begin() as conn:
        for chunk in _batched(params, 1000):
            conn.execute(stmt, chunk)


def _params(params):
    # 文本 SQL 的日期参数统一为 ISO 字符串：MySQL 可直接比较，SQLite 无需已弃用的默认日期适配器
    return {k: v.isoformat() if isinstance(v, datetime.date) else v for k, v in params.items()}


def _stmt(stmt):
    return sa.text(stmt) if isinstance(stmt, str) else stmt


def read(sql, **params):
    with engine().connect() as conn:
        return pd.read_sql(sa.text(sql), conn, params=_params(params))


def execute(stmt, **params):
    with engine().begin() as conn:
        return conn.execute(_stmt(stmt), _params(params))


def query(stmt, **params):
    """执行查询，返回 (列名列表, 行元组列表)。"""
    with engine().connect() as conn:
        result = conn.execute(_stmt(stmt), _params(params))
        return list(result.keys()), [tuple(row) for row in result]


def scalar(stmt, **params):
    with engine().connect() as conn:
        return conn.execute(_stmt(stmt), _params(params)).scalar()
