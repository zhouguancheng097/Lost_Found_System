"""Apply the verified fix to the user's explicitly identified test installation."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
import winreg

from verify_windows_launcher import request, verify_accounts

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ['LOCALAPPDATA']) / 'ShiguangLostFound'
INSTALLER = ROOT / 'dist/Shiguang-Setup-1.1.1-x64.exe'
WORK = ROOT / 'target/installed-v111-repair'
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8DB23807-A886-46CB-8940-BD011724C3E0}_is1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description='备份并升级已确认的拾光安装目录，再初始化虚构测试数据。')
    parser.add_argument('--app', required=True, type=Path)
    app = parser.parse_args().app.resolve()
    if WORK.exists():
        raise RuntimeError('Repair already attempted: inspect its backups before rerunning')
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        assert Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve() == app
    assert (app / 'Shiguang.exe').is_file() and INSTALLER.is_file()
    dev = {n:digest(ROOT / 'data' / n) for n in ('lostfound.db','admin-credentials.txt')}
    WORK.mkdir(parents=True)
    shutil.copy2(app / 'Shiguang.exe', WORK / 'Shiguang-1.1.0.exe')
    shutil.copy2(app / 'scripts/desktop.ps1', WORK / 'desktop-1.1.0.ps1')
    shutil.copy2(HOME / 'data/admin-credentials.txt', WORK / 'admin-credentials.backup.txt')
    credentials = digest(HOME / 'data/admin-credentials.txt')
    with sqlite3.connect(HOME / 'data/lostfound.db') as source:
        with sqlite3.connect(WORK / 'before-upgrade.db') as backup:
            source.backup(backup)
        counts = [source.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ('users','items','claims')]
    subprocess.run([str(INSTALLER), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                    '/DIR=' + str(app), '/LOG=' + str(WORK / 'upgrade.log')], check=True, timeout=900)
    assert digest(app / 'scripts/desktop.ps1') == digest(ROOT / 'scripts/windows/desktop.ps1')
    assert digest(app / 'Shiguang.exe') == digest(ROOT / 'target/windows-package/payload/Shiguang.exe')
    with sqlite3.connect(HOME / 'data/lostfound.db') as c:
        assert counts == [c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ('users','items','claims')]
    assert digest(HOME / 'data/admin-credentials.txt') == credentials
    print('PASS: existing installation upgraded, previous accounts and administrator preserved', flush=True)
    started = time.monotonic()
    subprocess.run([str(app / 'Shiguang.exe'), '--no-browser'], check=True, timeout=240,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    seconds = round(time.monotonic() - started,2)
    assert request('http://127.0.0.1:8080', '/api/health') == {'ok':True,'ai':True}
    print('PASS: installed GUI exits after startup, website and AI remain ready',flush=True)
    subprocess.run([str(app / 'Shiguang.exe'), '--demo', '--quiet'], check=True, timeout=60,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    inventory = json.loads((HOME / 'data/demo-fixtures.json').read_text(encoding='utf-8'))
    verify_accounts('http://127.0.0.1:8080',inventory['accounts'])
    assert digest(HOME / 'data/admin-credentials.txt') == credentials
    assert dev == {n:digest(ROOT / 'data' / n) for n in dev}
    assert (app / '初始化测试数据.cmd').is_file()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        assert winreg.QueryValueEx(key, 'DisplayVersion')[0] == '1.1.1'
    result = {
        'installed_app':str(app),'installer':str(INSTALLER),'bytes':INSTALLER.stat().st_size,
        'installer_sha256':digest(INSTALLER),'installed_version':'1.1.1',
        'installed_scripts_match_source':True,'upgrade_preserved_existing_data':True,
        'administrator_password_preserved':True,'development_database_unchanged':True,
        'native_gui_exited':True,'startup_seconds':seconds,'website_and_ai_healthy':True,
        'active_demo_logins_passed':4,'banned_demo_login_returns_403':True,
        'accounts_inventory':str(HOME / 'data/测试账号与数据.md'),
        'backup_directory':str(WORK),'services_left_running_for_user':True,
        'tested_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (ROOT / 'docs/Windows安装版现场修复.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPAIRED: user test installation and demo logins verified',flush=True)


if __name__ == '__main__':
    main()
