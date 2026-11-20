"""Explicit local administrator password reset; never invoked during startup."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import secrets
import shutil
import sqlite3


def reset_admin(data: Path) -> Path:
    data = data.resolve(strict=True)
    database = data / "lostfound.db"
    if not database.is_file():
        raise RuntimeError("Database does not exist; start the system first.")
    with sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=10) as connection:
        user = connection.execute("SELECT id,role,status FROM users WHERE username='admin'").fetchone()
        if not user or user[1:] != ("ADMIN", "ACTIVE"):
            raise RuntimeError("Active administrator was not found; no account was changed.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        backup = data / "backups" / ("before-admin-reset-" + stamp)
        backup.mkdir(parents=True, exist_ok=False)
        with sqlite3.connect(backup / "lostfound.db") as destination:
            connection.backup(destination)
        credentials = data / "admin-credentials.txt"
        if credentials.is_file():
            shutil.copy2(credentials, backup / credentials.name)
        salt = secrets.token_bytes(16)
        password_hash = "210000:" + base64.b64encode(salt).decode() + ":" + base64.b64encode(
            hashlib.pbkdf2_hmac("sha256", b"123456", salt, 210000)).decode()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        revoke = ",session_version=session_version+1" if "session_version" in columns else ""
        connection.execute("UPDATE users SET password_hash=?" + revoke + " WHERE id=?", (password_hash, user[0]))
        connection.execute("INSERT INTO audit_logs(actor_id,action,target_type,target_id,reason,created_at) VALUES(?,?,?,?,?,?)",
                           (user[0], "本机重设管理员密码", "user", user[0], "按本机维护要求恢复默认管理员密码", datetime.now(timezone.utc).isoformat()))
    credentials.write_text("用户名：admin\n密码：123456\n本机维护已重设。修改密码后使用新密码；升级和重启不会再次重设。\n", encoding="utf-8")
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Back up local data and reset admin to the requested default password.")
    parser.add_argument("--data", required=True, type=Path, help="Explicit local data directory")
    args = parser.parse_args()
    print("Administrator reset; backup:", reset_admin(args.data))
