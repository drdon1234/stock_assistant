import datetime
import json
from http.cookies import SimpleCookie

import pytest
import sqlalchemy as sa
from tornado.testing import AsyncHTTPTestCase

from instock import auth, db, schema
from instock.web import app


def _clear():
    db.init()
    for spec in (schema.SESSION, schema.ATTENTION, schema.USER):
        db.execute(schema.SA_TABLES[spec.name].delete())
    with db.engine().begin() as conn:
        conn.execute(sa.text(f'DROP TABLE IF EXISTS {schema.LEGACY_ATTENTION}'))


@pytest.fixture
def fresh():
    _clear()


def test_password_hash_roundtrip():
    stored = auth.hash_password('correct horse')
    assert stored.startswith('scrypt$') and 'correct horse' not in stored
    assert auth.check_password('correct horse', stored)
    assert not auth.check_password('wrong', stored)
    assert not auth.check_password('x', 'garbage')


def test_first_user_is_admin_and_adopts_legacy_attention(fresh):
    with db.engine().begin() as conn:
        conn.execute(sa.text(f'CREATE TABLE {schema.LEGACY_ATTENTION} (code VARCHAR(6) PRIMARY KEY, created_at DATE)'))
        conn.execute(sa.text(f"INSERT INTO {schema.LEGACY_ATTENTION} VALUES ('600519', '2026-09-01')"))
    first = auth.create_user('Alice', 'password1')
    second = auth.create_user('bob', 'password2')
    assert first == {'username': 'alice', 'admin': True}
    assert second == {'username': 'bob', 'admin': False}
    table = schema.SA_TABLES[schema.ATTENTION.name]
    assert db.query(sa.select(table.c.username, table.c.code))[1] == [('alice', '600519')]


def test_user_rules(fresh):
    with pytest.raises(auth.AuthError):
        auth.create_user('a', 'password1')
    with pytest.raises(auth.AuthError):
        auth.create_user('alice', 'short')
    auth.create_user('alice', 'password1')
    with pytest.raises(auth.AuthError):
        auth.create_user('ALICE', 'password1')
    with pytest.raises(auth.AuthError):
        auth.delete_user('alice')  # 最后一个管理员
    with pytest.raises(auth.AuthError):
        auth.set_admin('alice', False)
    assert auth.authenticate('Alice ', 'password1')['username'] == 'alice'
    assert auth.authenticate('alice', 'password2') is None
    assert auth.authenticate('nobody', 'password1') is None


def test_session_lifecycle(fresh):
    auth.create_user('alice', 'password1')
    token = auth.issue('alice')
    assert auth.resolve(token) == ({'username': 'alice', 'admin': True}, False)
    assert auth.resolve(token + 'x') == (None, False)
    s = schema.SA_TABLES[schema.SESSION.name]
    # 超过一天未使用：续期
    db.execute(s.update().values(last_used=datetime.datetime(2000, 1, 1)))
    assert auth.resolve(token)[1] is True
    # 已过期：失效并删除
    db.execute(s.update().values(expires_at=datetime.datetime(2000, 1, 1)))
    assert auth.resolve(token) == (None, False)
    assert db.scalar(sa.select(sa.func.count()).select_from(s)) == 0
    # 改密码吊销全部凭证
    token = auth.issue('alice')
    auth.set_password('alice', 'password9')
    assert auth.resolve(token) == (None, False)


def test_throttle():
    t = auth.Throttle(per_user=2, per_ip=3, window=60)
    assert t.wait('1.1.1.1', 'alice') == 0
    t.fail('1.1.1.1', 'alice')
    t.fail('1.1.1.1', 'Alice')
    assert t.wait('2.2.2.2', 'alice') > 0  # 同一账号
    t.reset('alice')
    assert t.wait('2.2.2.2', 'alice') == 0
    t.fail('1.1.1.1', 'carol')
    assert t.wait('1.1.1.1', 'dave') > 0  # 同一 IP


class WebAuthTest(AsyncHTTPTestCase):
    def get_app(self):
        return app.make_app()

    def setUp(self):
        super().setUp()
        _clear()
        app._throttle = auth.Throttle()
        auth.create_user('alice', 'password1')
        auth.create_user('bob', 'password2')

    def api(self, method, path, body=None, token=None, csrf=True):
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-Requested-With'] = 'instock'
        if token:
            headers['Cookie'] = f'{auth.COOKIE}={token}'
        payload = None if body is None and method in ('GET', 'DELETE') else json.dumps(body or {})
        response = self.fetch(path, method=method, headers=headers, body=payload, raise_error=False)
        return response, json.loads(response.body or b'{}')

    def login(self, username, password):
        response, body = self.api('POST', '/api/auth/session', {'username': username, 'password': password})
        assert response.code == 200, body
        cookie = SimpleCookie(response.headers['Set-Cookie'])[auth.COOKIE]
        assert cookie['httponly'] and cookie['samesite'] == 'Lax' and cookie['expires']
        return cookie.value

    def test_requires_login(self):
        for path in ('/api/meta', '/api/overview', '/api/attention', '/api/kline/600519', '/api/backtest',
                     '/api/users'):
            assert self.api('GET', path)[0].code == 401
        assert self.api('PUT', '/api/attention/600519')[0].code == 401
        response, body = self.api('GET', '/api/auth/session')
        assert response.code == 200 and body['user'] is None and body['setup'] is False
        assert self.fetch('/').code in (200, 503)  # 前端页面本身无需登录

    def test_login_and_logout(self):
        assert self.api('POST', '/api/auth/session', {'username': 'alice', 'password': 'bad'})[0].code == 400
        token = self.login('alice', 'password1')
        assert self.api('GET', '/api/auth/session', token=token)[1]['user'] == {'username': 'alice', 'admin': True}
        assert self.api('GET', '/api/meta', token=token)[0].code == 200
        assert self.api('DELETE', '/api/auth/session', token=token)[0].code == 200
        assert self.api('GET', '/api/meta', token=token)[0].code == 401

    def test_login_throttled(self):
        for _ in range(5):
            self.api('POST', '/api/auth/session', {'username': 'bob', 'password': 'wrong'})
        response, body = self.api('POST', '/api/auth/session', {'username': 'bob', 'password': 'password2'})
        assert response.code == 429

    def test_csrf_header_required(self):
        token = self.login('alice', 'password1')
        assert self.api('PUT', '/api/attention/600519', token=token, csrf=False)[0].code == 403
        assert self.api('POST', '/api/auth/session', {'username': 'alice', 'password': 'password1'},
                        csrf=False)[0].code == 403

    def test_attention_is_per_user(self):
        alice, bob = self.login('alice', 'password1'), self.login('bob', 'password2')
        assert self.api('PUT', '/api/attention/600519', token=alice)[0].code == 200
        assert self.api('PUT', '/api/attention/000001', token=bob)[0].code == 200
        assert self.api('GET', '/api/attention', token=alice)[1]['codes'] == ['600519']
        assert self.api('GET', '/api/attention', token=bob)[1]['codes'] == ['000001']
        self.api('DELETE', '/api/attention/000001', token=alice)
        assert self.api('GET', '/api/attention', token=bob)[1]['codes'] == ['000001']

    def test_admin_manages_users(self):
        alice, bob = self.login('alice', 'password1'), self.login('bob', 'password2')
        assert self.api('GET', '/api/users', token=bob)[0].code == 403
        names = [u['username'] for u in self.api('GET', '/api/users', token=alice)[1]['items']]
        assert names == ['alice', 'bob']
        response, body = self.api('POST', '/api/users', {'username': 'carol', 'password': 'short'}, token=alice)
        assert response.code == 400 and '密码' in body['error']
        assert self.api('POST', '/api/users', {'username': 'carol', 'password': 'password3'}, token=alice)[0].code == 200
        # 重置密码后 bob 的旧凭证失效
        assert self.api('PUT', '/api/users/bob', {'password': 'password4'}, token=alice)[0].code == 200
        assert self.api('GET', '/api/meta', token=bob)[0].code == 401
        assert self.api('DELETE', '/api/users/alice', token=alice)[0].code == 400
        assert self.api('DELETE', '/api/users/carol', token=alice)[0].code == 200

    def test_change_own_password(self):
        token = self.login('bob', 'password2')
        other = self.login('bob', 'password2')
        assert self.api('POST', '/api/auth/password', {'old': 'nope', 'new': 'password5'}, token=token)[0].code == 400
        response, _ = self.api('POST', '/api/auth/password', {'old': 'password2', 'new': 'password5'}, token=token)
        assert response.code == 200
        fresh_token = SimpleCookie(response.headers['Set-Cookie'])[auth.COOKIE].value
        assert self.api('GET', '/api/meta', token=other)[0].code == 401
        assert self.api('GET', '/api/meta', token=fresh_token)[0].code == 200
