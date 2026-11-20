"""Verify an offline Windows payload using fresh, isolated data and alternate ports."""
from __future__ import annotations
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fingerprint():
    result = {}
    for name in ("lostfound.db", "admin-credentials.txt"):
        path = ROOT / "data" / name
        if path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def request(url, body=None, headers=None, opener=None):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=raw, headers=headers or {})
    with (opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))).open(req, timeout=60) as response:
        content = response.read()
        if "json" in response.headers.get("Content-Type", ""):
            return json.loads(content)
        return content.decode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=ROOT / "target/windows-package/payload")
    parser.add_argument("--data-home", type=Path, default=ROOT / "target/windows-package-test/测试 数据")
    parser.add_argument("--port", type=int, default=18082)
    parser.add_argument("--ai-port", type=int, default=18767)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args()
    app = args.app.resolve()
    home = args.data_home.resolve()
    if not home.is_relative_to((ROOT / "target").resolve()):
        raise RuntimeError("Test data must remain inside the project's target directory")
    if (home / "data/lostfound.db").exists() and not args.allow_existing:
        raise RuntimeError("Use a new data directory for the fresh-install check")
    original = fingerprint()
    environment = os.environ.copy()
    # Poison the global Python paths. The embedded runtime must ignore them.
    environment["PYTHONHOME"] = str(ROOT / "target/nonexistent-python")
    environment["PYTHONPATH"] = str(ROOT / "target/nonexistent-packages")
    environment["PATH"] = os.pathsep.join([str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    checks = []
    def record(name):
        checks.append(name)
        print("PASS: " + name, flush=True)
    code = (
        "import sys,pathlib,json,torch,transformers,fastapi,uvicorn,numpy;"
        "from importlib import metadata as m;"
        "root=pathlib.Path(sys.executable).parent.resolve();"
        "assert sys.flags.isolated and sys.flags.no_user_site;"
        "assert all(pathlib.Path(m.distribution(n).locate_file('')).resolve().is_relative_to(root)"
        " for n in ['torch','transformers','fastapi','uvicorn','numpy']);"
        "assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in sys.path);"
        "print('isolated')"
    )
    subprocess.run([str(app / "python/python.exe"), "-I", "-B", "-c", code], check=True, env=environment)
    record("private Java/Python environment works without global PATH or Python packages")
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(app / "scripts/desktop.ps1"),
        "-DataHome", str(home), "-Port", str(args.port), "-AiPort", str(args.ai_port),
        "-NoUI", "-NoBrowser",
    ]
    # Use an explicit system executable because PATH is intentionally minimal.
    command[0] = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    services_started = False
    saved_pids = None
    try:
        subprocess.run(command, check=True, env=environment, timeout=240)
        services_started = True
        saved_pids = json.loads((home / "runtime/processes.json").read_text(encoding="utf-8-sig"))
        assert len(saved_pids) == 2
        base = "http://127.0.0.1:" + str(args.port)
        assert request(base + "/api/health") == {"ok": True, "ai": True}
        assert "<html" in request(base + "/").lower()
        assert ":root" in request(base + "/assets/style.css")
        record("website, static assets and bundled AI service become ready")
        connection = sqlite3.connect(home / "data/lostfound.db")
        try:
            assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
            assert connection.execute("SELECT username,role FROM users").fetchone() == ("admin", "ADMIN")
            for table in ("items", "claims", "notifications"):
                assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
        finally:
            connection.close()
        record("fresh database contains only a new administrator and no development records")
        credentials = (home / "data/admin-credentials.txt").read_text(encoding="utf-8")
        password = credentials.split("密码：", 1)[1].splitlines()[0].strip()
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        session = request(base + "/api/session", opener=opener)
        login = request(base + "/api/login", {"username": "admin", "password": password},
                        {"Content-Type": "application/json", "X-CSRF-Token": session["csrf"]}, opener)
        assert login["user"]["role"] == "ADMIN"
        record("new randomly generated administrator can sign in")
        headers = {"Content-Type": "application/json", "X-CSRF-Token": login["csrf"]}
        regular = request(base + "/api/register",
                          {"username": "package_test_user", "password": "PackageTest_2026!",
                           "display_name": "安装包验收用户"}, headers, opener)
        assert regular["username"] == "package_test_user"
        created = request(base + "/api/items", {
            "type": "FOUND", "title": "安装包验收用雨伞", "category": session["categories"][0],
            "description": "仅用于独立安装包验收的测试物品", "location": "测试教室",
            "event_date": "2026-11-01", "contact": "仅用于测试", "images": [],
        }, headers, opener)
        assert created["id"] > 0
        record("isolated test account and item can be created in the installed application")
        score = request("http://127.0.0.1:" + str(args.ai_port) + "/score",
                        {"query": "黑色雨伞", "documents": [
                            {"id": 1, "text": "黑色折叠雨伞，长柄防雨伞"},
                            {"id": 2, "text": "白色苹果手机，iPhone 15"}]},
                        {"Content-Type": "application/json"})
        assert score["scores"]["1"] > score["scores"]["2"]
        record("bundled BGE model performs a real semantic ranking")
        subprocess.run(command, check=True, env=environment, timeout=240)
        repeated = json.loads((home / "runtime/processes.json").read_text(encoding="utf-8-sig"))
        assert repeated == saved_pids
        record("repeated startup reuses the existing services")
    finally:
        if services_started or (home / "runtime/processes.json").exists():
            subprocess.run(command + ["-Action", "Stop"], check=True, env=environment, timeout=60)
        assert fingerprint() == original, "Development database or credentials changed"
    assert not (home / "runtime/processes.json").exists()
    record("services stop cleanly and the development database remains unchanged")
    import socket
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", args.port))
        occupied.listen(1)
        collision = subprocess.run(command, env=environment, capture_output=True, timeout=30)
        assert collision.returncode != 0
        assert "端口" in collision.stderr.decode("utf-8")
        assert not (home / "runtime/processes.json").exists()
        with socket.create_connection(("127.0.0.1", args.port), timeout=2):
            pass
    record("occupied port produces an error without stopping the unrelated listener")
    result = {
        "app": str(app), "data_home": str(home),
        "checks": checks, "count": len(checks),
        "website_port": args.port, "ai_port": args.ai_port,
        "development_data_unchanged": True,
        "services_stopped": True,
        "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    output = ROOT / "target/windows-package-verification.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERIFIED:", len(checks), "checks", flush=True)


if __name__ == "__main__":
    main()
