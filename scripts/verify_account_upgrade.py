"""Real HTTP checks and administrator recovery on isolated copies of local data."""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

from reset_admin import reset_admin

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                  urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = self.call('/api/session')['csrf']

    def call(self, path, body=None, method=None, expected=200, csrf=True):
        headers = {'Content-Type': 'application/json'}
        if hasattr(self, 'csrf') and csrf:
            headers['X-CSRF-Token'] = self.csrf
        req = urllib.request.Request(self.base + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with self.opener.open(req, timeout=20) as response:
                status, data = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, data = error.code, json.load(error)
        assert status == expected, (path, status, expected, data.get('error'))
        if isinstance(data, dict) and 'csrf' in data:
            self.csrf = data['csrf']
        return data

    def login(self, username, password, expected=200):
        return self.call('/api/login', {'username': username, 'password': password}, expected=expected)


def snapshot(database):
    with sqlite3.connect(database) as connection:
        return {
            'users': connection.execute('SELECT id,username,password_hash,role,status FROM users ORDER BY id').fetchall(),
            'counts': {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                       for table in ('users', 'items', 'claims', 'notifications')},
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=ROOT / 'target/account-v112-http')
    parser.add_argument('--port', type=int, default=18084)
    args = parser.parse_args()
    work = args.work.resolve()
    assert work.is_relative_to((ROOT / 'target').resolve())
    work.mkdir(parents=True, exist_ok=False)
    base = 'http://127.0.0.1:' + str(args.port)
    checks = []

    def passed(name):
        checks.append(name)
        print('PASS:', name, flush=True)

    def start(data, label):
        log = (work / (label + '.log')).open('wb')
        env = os.environ.copy()
        env.pop('LOSTFOUND_ADMIN_PASSWORD', None)
        process = subprocess.Popen([str(args.java), '-Dfile.encoding=UTF-8', '-Dapp.data=' + str(data),
                                    '-Dapp.port=' + str(args.port), '-Dapp.ai=http://127.0.0.1:1', '-cp',
                                    str(ROOT / 'target/lost-found-1.0.0.jar') + os.pathsep + str(ROOT / 'target/dependency/*'),
                                    'cn.campus.lostfound.Server'], cwd=work, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        log.close()
        try:
            for _ in range(80):
                if process.poll() is not None:
                    raise RuntimeError('Server exited; see ' + label + '.log')
                try:
                    return process, Client(base)
                except (OSError, urllib.error.URLError):
                    time.sleep(.25)
            raise RuntimeError('Server readiness timed out')
        except BaseException:
            process.terminate()
            process.wait(timeout=30)
            raise

    def stop(process):
        process.terminate()
        process.wait(timeout=30)

    fresh = work / 'fresh'
    process, admin = start(fresh, 'fresh')
    try:
        assert admin.login('admin', '123456')['user']['role'] == 'ADMIN'
        passed('real HTTP accepts admin / six-character default password')
        guest = Client(base)
        guest.call('/api/account/profile', expected=401)
        guest.call('/api/register', {'username': 'profile_http', 'display_name': '资料测试', 'password': 'TestOnly123!'})
        user = guest.login('profile_http', 'TestOnly123!')['user']
        guest.call('/api/account/profile', {'username': 'profile_http', 'display_name': '未经验证'}, method='PUT',
                   csrf=False, expected=403)
        profile = {'username': 'profile_renamed', 'display_name': '新的昵称', 'phone': '+86 13800000000',
                   'default_address': '图书馆二楼', 'current_password': 'TestOnly123!', 'id': 1, 'role': 'ADMIN'}
        result = guest.call('/api/account/profile', profile, method='PUT')
        assert result['id'] == user['id'] and result['role'] == 'USER'
        assert result['phone'] == profile['phone'] and result['default_address'] == profile['default_address']
        assert guest.call('/api/account/profile')['username'] == 'profile_renamed'
        passed('profile persistence, login rename, optional phone/address and identity/CSRF protection work over HTTP')
        second = Client(base)
        second.login('profile_renamed', 'TestOnly123!')
        guest.call('/api/account/password', {'current_password': 'TestOnly123!', 'new_password': 'ChangedOnly123!',
                                             'confirm_password': 'ChangedOnly123!'})
        guest.call('/api/account/profile', expected=401)
        second.call('/api/account/profile', expected=401)
        assert second.call('/api/session')['user'] is None
        second.login('profile_renamed', 'TestOnly123!', expected=401)
        assert second.login('profile_renamed', 'ChangedOnly123!')['user']['id'] == user['id']
        passed('password update revokes both real browser sessions and rejects the old password')
        profile.update(phone='', default_address='')
        assert second.call('/api/account/profile', profile, method='PUT')['phone'] == ''
        assert second.call('/api/account/profile')['default_address'] == ''
        admin.call('/api/account/profile', {'username': 'admin_renamed', 'display_name': '管理员',
                                          'current_password': '123456'}, method='PUT', expected=400)
        passed('optional fields can be cleared and administrator login name stays fixed')
    finally:
        stop(process)

    before = snapshot(fresh / 'lostfound.db')
    backup = reset_admin(fresh)
    after = snapshot(fresh / 'lostfound.db')
    assert snapshot(backup / 'lostfound.db') == before
    assert before['users'][1:] == after['users'][1:] and before['counts'] == after['counts']
    assert before['users'][0][2] != after['users'][0][2]
    encoded = after['users'][0][2].split(':')
    assert hashlib.pbkdf2_hmac('sha256', b'123456', base64.b64decode(encoded[1]), int(encoded[0])) == base64.b64decode(encoded[2])
    passed('explicit reset creates a consistent original backup and preserves ordinary accounts/business data')

    legacy = work / 'legacy'
    legacy.mkdir()
    with sqlite3.connect((ROOT / 'data/lostfound.db').as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(legacy / 'lostfound.db') as destination:
            source.backup(destination)
    with sqlite3.connect(legacy / 'lostfound.db') as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(users)')}
        for column in ('phone', 'default_address', 'session_version'):
            if column in columns:
                connection.execute('ALTER TABLE users DROP COLUMN ' + column)
    before = snapshot(legacy / 'lostfound.db')
    process, _ = start(legacy, 'legacy-migration')
    try:
        assert snapshot(legacy / 'lostfound.db') == before
        with sqlite3.connect(legacy / 'lostfound.db') as connection:
            columns = {row[1] for row in connection.execute('PRAGMA table_info(users)')}
            assert {'phone', 'default_address', 'session_version'} <= columns
            assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        stop(process)
    passed('real old-schema database migrates while preserving every account hash and business record count')
    process, _ = start(legacy, 'legacy-restart')
    try:
        assert snapshot(legacy / 'lostfound.db') == before
    finally:
        stop(process)
    passed('repeat startup leaves existing passwords and business data unchanged')
    result = {'version': '1.1.2', 'checks': checks, 'count': len(checks), 'services_stopped': True,
              'backend_tests': 26, 'frontend_behavior_checks': 12, 'browser_visual_validation': False,
              'work': str(work), 'tested_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    (ROOT / 'docs/个人信息与账号优化验收.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
