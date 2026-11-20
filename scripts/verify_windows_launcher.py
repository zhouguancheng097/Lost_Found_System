"""Exercise the compiled desktop GUI and demo accounts using isolated data."""
from pathlib import Path
import hashlib
import http.cookiejar
import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PS = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


def request(base, path, body=None, opener=None, csrf=None, expected=200):
    headers = {'Content-Type': 'application/json'}
    if csrf:
        headers['X-CSRF-Token'] = csrf
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with (opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))).open(req, timeout=30) as response:
            assert response.status == expected
            return json.load(response)
    except urllib.error.HTTPError as error:
        assert error.code == expected, (path, error.code, error.read())
        return json.load(error)


def verify_accounts(base, accounts):
    for account in accounts:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        session = request(base, '/api/session', opener=opener)
        login = request(base, '/api/login', {'username': account['username'], 'password': 'Demo123456!'},
                        opener, session['csrf'], 403 if account['status'] == 'BANNED' else 200)
        if account['status'] != 'BANNED':
            assert login['user']['username'] == account['username']


def main():
    app = ROOT / 'target/windows-package/payload'
    work = ROOT / 'target/windows-launcher-v111'
    home = work / 'profile'
    if home.exists():
        raise RuntimeError('Use a fresh regression directory')
    (work / 'scripts').mkdir(parents=True, exist_ok=True)
    shutil.copy2(app / 'Shiguang.exe', work / 'Shiguang.exe')
    # Test the actual compiled GUI, forwarding to isolated data and alternate ports.
    quote = lambda p: "'" + str(p).replace("'", "''") + "'"
    wrapper = "param([string]$Action='Start',[string]$ErrorFile='', [switch]$NoUI,[switch]$NoBrowser)\n"
    wrapper += '& ' + quote(app / 'scripts/desktop.ps1') + ' -Action $Action -ErrorFile $ErrorFile -DataHome ' + quote(home)
    wrapper += ' -Port 18086 -AiPort 18771 -NoUI -NoBrowser\nexit $LASTEXITCODE\n'
    (work / 'scripts/desktop.ps1').write_text(wrapper, encoding='utf-8-sig')
    command = [str(work / 'Shiguang.exe'), '--no-browser']
    stop = [str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(app / 'scripts/desktop.ps1'),
            '-Action', 'Stop', '-DataHome', str(home), '-NoUI', '-NoBrowser']
    checks = []

    def passed(message):
        checks.append(message)
        print('PASS:', message, flush=True)

    base = 'http://127.0.0.1:18086'
    launched = None
    try:
        started = time.monotonic()
        launched = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
        assert launched.wait(timeout=240) == 0
        assert request(base, '/api/health') == {'ok': True, 'ai': True}
        cold_seconds = round(time.monotonic() - started, 2)
        passed('native GUI closes after cold startup while website and AI remain healthy')
        records = (home / 'runtime/processes.json').read_bytes()
        subprocess.run(command, check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        assert records == (home / 'runtime/processes.json').read_bytes()
        passed('native GUI closes on repeated startup without duplicating services')
        credentials_hash = hashlib.sha256((home / 'data/admin-credentials.txt').read_bytes()).hexdigest()
        with sqlite3.connect(home / 'data/lostfound.db') as c:
            admin_hash = c.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        subprocess.run(command + ['--demo', '--quiet'], check=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        inventory = json.loads((home / 'data/demo-fixtures.json').read_text(encoding='utf-8'))
        assert [len(inventory[k]) for k in ('accounts', 'items', 'claims')] == [5, 16, 7]
        with sqlite3.connect(home / 'data/lostfound.db') as c:
            assert c.execute('PRAGMA foreign_key_check').fetchall() == []
            assert c.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0] == admin_hash
            assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 6
        assert credentials_hash == hashlib.sha256((home / 'data/admin-credentials.txt').read_bytes()).hexdigest()
        backups = list((home / 'data/backups').glob('before-demo-*.db'))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as c:
            assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        passed('demo creates 5 accounts, 16 items, 7 claims with backup and unchanged administrator')
        verify_accounts(base, inventory['accounts'])
        passed('four demo accounts sign in over HTTP and the initially banned account returns 403')
        first_id = inventory['items'][0]['id']
        with sqlite3.connect(home / 'data/lostfound.db') as c:
            c.execute("UPDATE items SET status='CLOSED' WHERE id=?", (first_id,))
            counts = [c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ('users', 'items', 'claims')]
        subprocess.run(command + ['--demo', '--quiet'], check=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        with sqlite3.connect(home / 'data/lostfound.db') as c:
            assert counts == [c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ('users','items','claims')]
            assert c.execute('SELECT status FROM items WHERE id=?', (first_id,)).fetchone()[0] == 'CLOSED'
        passed('repeated demo initialization preserves modified business states and creates no duplicates')
        error_file = work / 'expected-port-error.txt'
        failure = subprocess.run([str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(app / 'scripts/desktop.ps1'),
                   '-DataHome', str(work / 'collision-profile'), '-Port', '18086', '-AiPort', '18772', '-NoUI', '-NoBrowser', '-ErrorFile', str(error_file)],
                  timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        assert failure.returncode != 0 and '18086' in error_file.read_text(encoding='utf-8')
        assert request(base, '/api/health') == {'ok': True, 'ai': True}
        passed('script reports real failure through its UTF-8 error file without stopping occupied services')
    finally:
        subprocess.run(stop, check=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        if launched is not None and launched.poll() is None:
            launched.kill()
    assert not (home / 'runtime/processes.json').exists()
    passed('isolated regression services stop cleanly')
    result = {'version':'1.1.1','app':str(app),'count':len(checks),'checks':checks,
              'cold_start_seconds':cold_seconds,'native_gui_process_exited':True,
              'installer_finish_button_clicked':False,'other_computers_verified':False,
              'tested_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (ROOT / 'docs/Windows启动与账号修复验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('VERIFIED:',len(checks),'checks',flush=True)


if __name__ == '__main__':
    main()
