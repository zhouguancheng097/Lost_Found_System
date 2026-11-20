"""Exercise the real EXE installer, upgrade and uninstall inside target/."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request
import winreg

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "target/windows-installer-test"
APP = WORK / "安装 目录"
PROFILE = WORK / "profile"
HOME = PROFILE / "ShiguangLostFound"
INSTALLER = ROOT / "dist/Shiguang-Setup-1.1.1-x64.exe"
KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{8DB23807-A886-46CB-8940-BD011724C3E0}_is1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not APP.resolve().is_relative_to((ROOT / "target").resolve()):
        raise RuntimeError("Unsafe test installation directory")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            location = winreg.QueryValueEx(key, "InstallLocation")[0]
            if Path(location).resolve() != APP.resolve():
                raise RuntimeError("An existing installation belongs to the user; refusing to replace it")
    except FileNotFoundError:
        pass
    if HOME.exists():
        raise RuntimeError("Use a fresh installer test profile")
    WORK.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(PROFILE)
    results = []
    def passed(name):
        results.append(name)
        print("PASS:", name, flush=True)
    def install(label):
        print("Running installer:", label, flush=True)
        subprocess.run([str(INSTALLER), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        "/NOICONS", "/TASKS=", "/DIR=" + str(APP),
                        "/LOG=" + str(WORK / (label + ".log"))],
                       check=True, env=environment, timeout=900)
        assert (APP / "Shiguang.exe").exists()
        assert digest(APP / "scripts/desktop.ps1") == digest(ROOT / "scripts/windows/desktop.ps1")
    def uninstall(label):
        uninstaller = APP / "unins000.exe"
        subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        "/LOG=" + str(WORK / (label + ".log"))],
                       check=True, env=environment, timeout=300)
        for _ in range(30):
            if not (APP / "app.jar").exists() and not uninstaller.exists():
                break
            time.sleep(0.5)
        assert not (APP / "app.jar").exists()
    def user_hashes():
        return {name: digest(HOME / "data" / name) for name in
                ("lostfound.db", "admin-credentials.txt", "uploads/upgrade-sentinel.txt")}
    installed = False
    try:
        install("initial-install")
        installed = True
        passed("EXE installs successfully into a path containing Chinese characters and spaces")
        subprocess.run([sys.executable, str(ROOT / "scripts/verify_windows_package.py"),
                        "--app", str(APP), "--data-home", str(HOME)],
                       check=True, env=environment, timeout=480)
        verification = json.loads((ROOT / "target/windows-package-verification.json").read_text(encoding="utf-8"))
        assert verification["count"] == 9
        passed("installed program passes all nine isolated startup, AI and safety checks")
        uploads = HOME / "data/uploads"
        uploads.mkdir(exist_ok=True)
        (uploads / "upgrade-sentinel.txt").write_text("Upgrade/uninstall preservation check", encoding="utf-8")
        before = user_hashes()
        install("upgrade-install")
        assert user_hashes() == before
        connection = sqlite3.connect(HOME / "data/lostfound.db")
        try:
            assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
            assert connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()
        passed("upgrade preserves accounts, items, administrator password and uploaded files")
        # Reading/checkpointing SQLite can change its main file. Snapshot after closing it.
        before = user_hashes()
        uninstall("uninstall")
        installed = False
        assert user_hashes() == before
        passed("uninstall removes program files while preserving all user data")
        install("reinstall")
        installed = True
        assert user_hashes() == before
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(APP / "scripts/desktop.ps1"), "-DataHome", str(HOME),
                   "-Port", "18082", "-AiPort", "18767", "-NoUI", "-NoBrowser"]
        try:
            subprocess.run(command, check=True, env=environment, timeout=240)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:18082/api/health", timeout=10) as response:
                assert json.load(response) == {"ok": True, "ai": True}
            connection = sqlite3.connect(HOME / "data/lostfound.db")
            try:
                assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
                assert connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
            finally:
                connection.close()
        finally:
            subprocess.run(command + ["-Action", "Stop"], check=True, env=environment, timeout=60)
        assert digest(HOME / "data/admin-credentials.txt") == before["admin-credentials.txt"]
        passed("reinstall starts successfully with the original accounts and administrator password")
    finally:
        if installed and (APP / "unins000.exe").exists():
            uninstall("test-cleanup")
    result = {
        "installer": str(INSTALLER),
        "bytes": INSTALLER.stat().st_size,
        "sha256": digest(INSTALLER),
        "checks": results,
        "count": len(results),
        "runtime_verification": verification,
        "test_installation_removed": True,
        "test_data_retained_under_target": True,
        "ui_clicks_verified": False,
        "other_computers_verified": False,
        "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    output = ROOT / "docs/Windows安装包验收.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("INSTALLER VERIFIED:", len(results), "checks", flush=True)


if __name__ == "__main__":
    main()
