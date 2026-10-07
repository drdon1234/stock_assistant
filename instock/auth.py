"""账号与登录凭证。

密码用 scrypt 加盐哈希保存；登录成功后颁发随机的长效凭证（放在 HttpOnly Cookie 中），库中只保存凭证的 SHA-256。
凭证有效期为 SESSION_DAYS 天，每天首次使用时顺延，经常访问就无需重新登录。修改密码或删除账号时吊销该账号的全部凭证。
"""
import datetime
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time

import sqlalchemy as sa

from instock import config, db, schema

log = logging.getLogger(__name__)

COOKIE = 'instock_token'
MIN_PASSWORD = 8
_USERNAME = re.compile(r'[a-z0-9_.-]{2,32}')
_SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1}
_RENEW_AFTER = datetime.timedelta(days=1)


class AuthError(ValueError):
    """可直接展示给用户的错误。"""


def _users():
    return schema.SA_TABLES[schema.USER.name]


def _sessions():
    return schema.SA_TABLES[schema.SESSION.name]


def _attention():
    return schema.SA_TABLES[schema.ATTENTION.name]


def _now():
    return datetime.datetime.now().replace(microsecond=0)


def normalize(username):
    """账号统一小写，只允许字母、数字和 _ . -，避免 MySQL 与 SQLite 大小写比较规则不一致。"""
    name = (username or '').strip().lower()
    if not _USERNAME.fullmatch(name):
        raise AuthError('账号为 2~32 位字母、数字或 _ . -')
    return name


def _check_rule(password):
    if len(password or '') < MIN_PASSWORD:
        raise AuthError(f'密码至少 {MIN_PASSWORD} 位')


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        algo, n, r, p, salt, digest = stored.split('$')
        if algo != 'scrypt':
            return False
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (AttributeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


_dummy_hash = None


def _dummy():
    # 账号不存在时也算一次哈希，响应时间不暴露账号是否存在
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_hex(8))
    return _dummy_hash


def _user_dict(username, is_admin):
    return {'username': username, 'admin': bool(is_admin)}


# ---------- 账号 ----------

def has_users():
    return bool(db.scalar(sa.select(sa.func.count()).select_from(_users())))


def get_user(username):
    t = _users()
    _, rows = db.query(sa.select(t.c.username, t.c.is_admin).where(t.c.username == username))
    return _user_dict(*rows[0]) if rows else None


def list_users():
    t, s = _users(), _sessions()
    _, users = db.query(sa.select(t.c.username, t.c.is_admin, t.c.created_at).order_by(t.c.created_at))
    _, stats = db.query(sa.select(s.c.username, sa.func.count(), sa.func.max(s.c.last_used))
                        .where(s.c.expires_at > _now()).group_by(s.c.username))
    stats = {name: (n, last) for name, n, last in stats}
    return [{**_user_dict(name, admin), 'created_at': created, 'sessions': stats.get(name, (0, None))[0],
             'last_used': stats.get(name, (0, None))[1]} for name, admin, created in users]


def create_user(username, password, admin=False):
    """新建账号。系统中的第一个账号总是管理员，并接收旧版不分账号的关注列表。"""
    username = normalize(username)
    _check_rule(password)
    t = _users()
    first = not has_users()
    if get_user(username):
        raise AuthError(f'账号 {username} 已存在')
    db.execute(t.insert().values(username=username, password=hash_password(password), is_admin=bool(admin or first),
                                 created_at=_now()))
    if first:
        _adopt_legacy_attention(username)
    return get_user(username)


def _adopt_legacy_attention(username):
    if not sa.inspect(db.engine()).has_table(schema.LEGACY_ATTENTION):
        return
    count = db.execute(f'INSERT INTO {schema.ATTENTION.name} (username, code, created_at) '
                       f'SELECT :u, code, created_at FROM {schema.LEGACY_ATTENTION}', u=username).rowcount
    if count:
        log.info('旧版关注列表 %d 只股票已归入账号 %s', count, username)


def _require(username):
    user = get_user(username)
    if user is None:
        raise AuthError(f'账号 {username} 不存在')
    return user


def _admin_count():
    t = _users()
    return db.scalar(sa.select(sa.func.count()).select_from(t).where(t.c.is_admin == sa.true()))


def set_password(username, password):
    """修改密码并吊销该账号的全部登录凭证。"""
    _require(username)
    _check_rule(password)
    t = _users()
    db.execute(t.update().where(t.c.username == username).values(password=hash_password(password)))
    revoke_user(username)


def set_admin(username, admin):
    user = _require(username)
    if user['admin'] and not admin and _admin_count() <= 1:
        raise AuthError('至少需要保留一个管理员')
    t = _users()
    db.execute(t.update().where(t.c.username == username).values(is_admin=bool(admin)))


def delete_user(username):
    user = _require(username)
    if user['admin'] and _admin_count() <= 1:
        raise AuthError('不能删除最后一个管理员')
    with db.engine().begin() as conn:
        for table in (_sessions(), _attention(), _users()):
            conn.execute(table.delete().where(table.c.username == username))


def authenticate(username, password):
    """账号密码正确时返回用户，否则返回 None。"""
    try:
        username = normalize(username)
    except AuthError:
        username = None
    t = _users()
    rows = []
    if username:
        _, rows = db.query(sa.select(t.c.username, t.c.is_admin, t.c.password).where(t.c.username == username))
    stored = rows[0][2] if rows else _dummy()
    if not check_password(password or '', stored) or not rows:
        return None
    return _user_dict(rows[0][0], rows[0][1])


def bootstrap():
    """Web 服务启动时调用：按环境变量创建初始管理员；还没有任何账号时提示如何创建。"""
    if config.ADMIN_USER and config.ADMIN_PASSWORD:
        try:
            if get_user(normalize(config.ADMIN_USER)) is None:
                create_user(config.ADMIN_USER, config.ADMIN_PASSWORD, admin=True)
                log.info('已按 INSTOCK_ADMIN_USER 创建管理员账号 %s', normalize(config.ADMIN_USER))
        except AuthError as e:
            log.error('INSTOCK_ADMIN_USER/INSTOCK_ADMIN_PASSWORD 无效：%s', e)
    if not has_users():
        log.warning('尚未创建任何账号，网页无法登录。请运行 python -m instock user add <账号> 创建管理员'
                    '（Docker：docker exec -it instock-web python -m instock user add <账号>）')


# ---------- 登录凭证 ----------

def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue(username, user_agent='', ip=''):
    """颁发新凭证并返回凭证原文（只此一次）。顺带清理已过期的凭证。"""
    token = secrets.token_urlsafe(32)
    now = _now()
    s = _sessions()
    with db.engine().begin() as conn:
        conn.execute(s.delete().where(s.c.expires_at <= now))
        conn.execute(s.insert().values(token=_digest(token), username=username, created_at=now, last_used=now,
                                       expires_at=now + datetime.timedelta(days=config.SESSION_DAYS),
                                       user_agent=(user_agent or '')[:200], ip=(ip or '')[:64]))
    return token


def resolve(token):
    """凭证有效时返回 (用户, 是否已续期)，否则返回 (None, False)。"""
    if not token or len(token) > 128:
        return None, False
    s, t = _sessions(), _users()
    digest = _digest(token)
    _, rows = db.query(sa.select(t.c.username, t.c.is_admin, s.c.expires_at, s.c.last_used)
                       .join(t, t.c.username == s.c.username).where(s.c.token == digest))
    if not rows:
        return None, False
    username, is_admin, expires_at, last_used = rows[0]
    now = _now()
    if expires_at <= now:
        db.execute(s.delete().where(s.c.token == digest))
        return None, False
    renewed = now - last_used >= _RENEW_AFTER
    if renewed:
        db.execute(s.update().where(s.c.token == digest)
                   .values(last_used=now, expires_at=now + datetime.timedelta(days=config.SESSION_DAYS)))
    return _user_dict(username, is_admin), renewed


def revoke(token):
    if token:
        s = _sessions()
        db.execute(s.delete().where(s.c.token == _digest(token)))


def revoke_user(username):
    s = _sessions()
    db.execute(s.delete().where(s.c.username == username))


class Throttle:
    """登录失败限流：同一账号或同一 IP 在时间窗内失败次数过多时暂时拒绝登录。仅保存在进程内存中。"""

    def __init__(self, per_user=5, per_ip=20, window=900):
        self.limits = {'u': per_user, 'i': per_ip}
        self.window = window
        self._fails = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        times = [t for t in self._fails.get(key, ()) if t > now - self.window]
        if times:
            self._fails[key] = times
        else:
            self._fails.pop(key, None)
        return times

    def wait(self, ip, username):
        """需要等待的秒数，0 表示可以尝试。"""
        now = time.monotonic()
        with self._lock:
            waits = [times[-self.limits[kind]] + self.window - now
                     for kind, key in (('u', f'u:{(username or "").strip().lower()}'), ('i', f'i:{ip}'))
                     if len(times := self._recent(key, now)) >= self.limits[kind]]
        return max(waits, default=0)

    def fail(self, ip, username):
        now = time.monotonic()
        with self._lock:
            for key in (f'u:{(username or "").strip().lower()}', f'i:{ip}'):
                self._fails.setdefault(key, []).append(now)

    def reset(self, username):
        with self._lock:
            self._fails.pop(f'u:{(username or "").strip().lower()}', None)
