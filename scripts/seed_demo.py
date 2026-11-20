import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import base64
import json
from pathlib import Path
import secrets
import sqlite3
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Demo123456!"
SEED_ACTION = "DEMO_SEED_V1"
ACCOUNTS = [
    ("demo_finder", "测试·拾物发布者", "ACTIVE", "发布招领、编辑自己的信息"),
    ("demo_owner", "测试·失主甲", "ACTIVE", "发布寻物、申领和查看联系方式"),
    ("demo_claimant", "测试·失主乙", "ACTIVE", "竞争申领、撤回、权限隔离"),
    ("demo_banned", "测试·封禁账号", "BANNED", "封禁、解锁与会话失效"),
    ("demo_delete", "测试·注销练习", "ACTIVE", "没有进行中业务，可直接测试注销"),
]


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210000)
    return "210000:" + base64.b64encode(salt).decode() + ":" + base64.b64encode(digest).decode()


def sample_png():
    width, height = 160, 100
    rows = b"".join(b"\x00" + b"".join(bytes((41, 98, 82) if (column // 20 + row // 20) % 2 else (222, 234, 213)) for column in range(width)) for row in range(height))
    def chunk(kind, contents):
        return struct.pack(">I", len(contents)) + kind + contents + struct.pack(">I", zlib.crc32(kind + contents))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def write_inventory(directory, manifest):
    directory.mkdir(parents=True, exist_ok=True)
    files = directory / "demo-files"
    files.mkdir(exist_ok=True)
    (files / "demo-photo.png").write_bytes(sample_png())
    (files / "invalid-image.txt").write_text("This is not an image. Upload should be rejected.", encoding="utf-8")
    (directory / "demo-fixtures.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 本地测试账号与数据", "", f"初始化时间：{manifest['created_at']}。所有人物、联系方式与物品均为虚构测试数据。", "", f"五个普通测试账号的初始密码均为：`{PASSWORD}`。", "", "管理员沿用现有 admin，密码见同目录 admin-credentials.txt；本脚本不更改管理员密码。", "", "| 用户名 | 显示名称 | 初始状态 | 适合测试 |", "|---|---|---|---|"]
    for account in manifest["accounts"]:
        lines.append(f"| {account['username']} | {account['display_name']} | {account['status']} | {account['purpose']} |")
    lines.extend(["", "## 物品清单", "", "| 编号 | 标题 | 初始状态 | 发布者 |", "|---|---|---|---|"])
    for item in manifest["items"]:
        lines.append(f"| {item['id']} | {item['title']} | {item['status']} | {item['owner']} |")
    lines.extend(["", "## 预置申请", "", "| 申请编号 | 物品编号 | 申请人 | 初始状态 |", "|---|---|---|---|"])
    for claim in manifest["claims"]:
        lines.append(f"| {claim['id']} | {claim['item_id']} | {claim['applicant']} | {claim['status']} |")
    lines.extend(["", "状态和密码描述的是初始化时的情况。操作测试后，不会自动恢复状态或找回已注销账号。重复执行初始化只恢复这份清单，不重置现有业务，也不重复创建数据。", "", "手工用例见项目 docs/手工测试用例.md。图片上传样例：data/demo-files/demo-photo.png；非法样例：data/demo-files/invalid-image.txt。", ""])
    (directory / "测试账号与数据.md").write_text("\n".join(lines), encoding="utf-8")


def seed(directory):
    directory = Path(directory).resolve()
    database = directory / "lostfound.db"
    if not database.is_file():
        raise RuntimeError("数据库不存在，请先启动一次系统，再运行测试数据初始化。")
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        existing = connection.execute("SELECT reason FROM audit_logs WHERE action=? ORDER BY id LIMIT 1", (SEED_ACTION,)).fetchone()
        if existing:
            manifest = json.loads(existing["reason"])
            write_inventory(directory, manifest)
            return manifest, False
        administrator = connection.execute("SELECT id FROM users WHERE username='admin' AND role='ADMIN'").fetchone()
        if not administrator:
            raise RuntimeError("找不到管理员账号，请先完成系统初始化。")
        backup_path = directory / "backups" / ("before-demo-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".db")
        backup_path.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(backup_path)) as backup:
            connection.backup(backup)
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT reason FROM audit_logs WHERE action=? ORDER BY id LIMIT 1", (SEED_ACTION,)).fetchone()
        if existing:
            connection.rollback()
            manifest = json.loads(existing["reason"])
            write_inventory(directory, manifest)
            return manifest, False
        usernames = [account[0] for account in ACCOUNTS]
        placeholders = ",".join("?" for _ in usernames)
        if connection.execute(f"SELECT 1 FROM users WHERE username IN ({placeholders})", usernames).fetchone():
            raise RuntimeError("测试用户名已被已有账号使用。为保护原账号，未覆盖或重置任何账号，请先更换测试用户名。")
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        today = datetime.now(timezone(timedelta(hours=8))).date()
        manifest = {"version": 1, "created_at": timestamp, "backup": str(backup_path), "accounts": [], "items": [], "claims": []}
        account_ids = {}
        for username, display_name, status, purpose in ACCOUNTS:
            cursor = connection.execute("INSERT INTO users(username,display_name,password_hash,role,status,ban_reason,created_at) VALUES(?,?,?,'USER',?,?,?)", (username, display_name, password_hash(PASSWORD), status, "演示封禁状态，供管理员解锁测试" if status == "BANNED" else "", timestamp))
            account_ids[username] = cursor.lastrowid
            manifest["accounts"].append({"id": cursor.lastrowid, "username": username, "display_name": display_name, "status": status, "purpose": purpose})
            connection.execute("INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)", (cursor.lastrowid, "这是本地虚构测试账号，请参考手工测试用例进行操作。", timestamp))
        specifications = [
            ("umbrella", "demo_finder", "FOUND", "黑色折叠雨伞", "雨伞", "黑色折叠伞，伞柄带挂绳，在图书馆二楼拾到。", "图书馆二楼", 1, "OPEN", "伞柄内侧刻着 LF-2026"),
            ("lost_umbrella", "demo_owner", "LOST", "寻找图书馆丢失的黑色雨伞", "雨伞", "昨天在图书馆丢了一把黑色折叠伞，有一根挂绳。", "校图书馆", 1, "OPEN", ""),
            ("card", "demo_finder", "FOUND", "蓝色卡套校园卡", "证件卡片", "校园卡一张，蓝色卡套，卡面个人信息未公开。", "食堂门口", 2, "OPEN", "卡套背面有一颗星星贴纸"),
            ("lost_card", "demo_claimant", "LOST", "寻找学生卡和蓝色卡套", "证件卡片", "吃饭用的学生卡丢了，装在蓝色卡套中。", "食堂", 2, "OPEN", ""),
            ("laptop_bag", "demo_finder", "FOUND", "灰色笔记本电脑包", "包袋", "灰色笔记本电脑包，内有电源适配器，外侧有拉链袋。", "教学楼A座", 1, "OPEN", "内袋中有印着TEST的纸条"),
            ("lost_bag", "demo_owner", "LOST", "寻找装电脑的灰色包", "包袋", "装电脑和充电器的灰包丢了，可能落在教学楼。", "教学楼", 2, "OPEN", ""),
            ("huawei", "demo_finder", "FOUND", "黑色华为 Mate 60 手机", "数码电子", "黑色华为 Mate 60 手机，透明外壳，锁屏未解锁。", "体育馆", 1, "OPEN", "壳内有TEST字样的小纸片"),
            ("iphone", "demo_finder", "FOUND", "白色苹果 iPhone 15 手机", "数码电子", "白色苹果 iPhone 15，粉色外壳，供品牌颜色冲突检索测试。", "体育馆", 1, "OPEN", "壳底有小月亮贴纸"),
            ("cup", "demo_finder", "FOUND", "深蓝色保温杯", "水杯餐具", "深蓝色保温水杯，黑色杯盖，杯身没有公开姓名。", "操场", 3, "OPEN", "杯底贴着TEST-08"),
            ("earphones", "demo_finder", "FOUND", "白色无线蓝牙耳机", "数码电子", "白色无线耳机一副，带白色充电盒。", "图书馆一楼", 1, "OPEN", "盒盖内侧写着测试标记E1"),
            ("pending", "demo_owner", "LOST", "待审核的银色U盘", "数码电子", "银色金属U盘，带黑色短绳，用于内容审核和本人编辑测试。", "实验楼", 1, "PENDING", ""),
            ("rejected", "demo_finder", "FOUND", "已驳回的红色围巾", "衣物配饰", "红色羊毛围巾，等待发布者补充拾取位置后重新提交。", "教学楼", 4, "REJECTED", "围巾角落有TEST字样"),
            ("keys", "demo_finder", "FOUND", "交接中的小熊挂件钥匙", "钥匙", "一串钥匙，带小熊挂件，用于取消交接或确认领取测试。", "宿舍楼门口", 2, "HANDOVER", "共有三把钥匙，挂件背面是TEST"),
            ("claimed", "demo_finder", "FOUND", "已领取的绿色双肩书包", "包袋", "绿色双肩书包，已完成交接，供历史状态筛选测试。", "校门口", 5, "CLAIMED", ""),
            ("resolved", "demo_owner", "LOST", "已找回的红色钱包", "包袋", "红色钱包已由本人找回，用于寻物终态展示测试。", "食堂", 6, "RESOLVED", ""),
            ("closed", "demo_finder", "FOUND", "已关闭的高等数学课本", "书籍文具", "一本高等数学课本，信息已关闭，用于筛选和禁止申领测试。", "教学楼B座", 7, "CLOSED", ""),
        ]
        item_ids = {}
        for key, owner, kind, title, category, description, location, days, status, hidden in specifications:
            full_title = "【测试】" + title
            review_note = "请补充准确拾取位置" if status == "REJECTED" else ""
            cursor = connection.execute("INSERT INTO items(owner_id,type,title,category,description,location,event_date,contact,hidden_features,status,review_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (account_ids[owner], kind, full_title, category, description, location, str(today - timedelta(days=days)), "测试联系渠道：站内管理员转交（虚构）", hidden, status, review_note, timestamp, timestamp))
            item_ids[key] = cursor.lastrowid
            manifest["items"].append({"key": key, "id": cursor.lastrowid, "title": full_title, "status": status, "owner": owner})
        claim_specs = [
            ("umbrella", "demo_owner", "PENDING", "我丢的是黑色折叠伞，伞柄内侧刻着LF-2026，昨天遗失在二楼。"),
            ("umbrella", "demo_claimant", "PENDING", "我也丢了一把黑伞，但记得伞柄是木质的，没有刻字。"),
            ("keys", "demo_owner", "APPROVED", "三把钥匙，挂件背面写着TEST，已核验等待交接。"),
            ("keys", "demo_claimant", "PENDING", "我遗失了带小熊挂件的钥匙，需要进一步核验。"),
            ("claimed", "demo_claimant", "COMPLETED", "绿色书包，交接前已经核验完成，这是已完成样例。"),
            ("claimed", "demo_owner", "CANCELLED", "这是其他人已经领取后同步结束的申请样例。"),
            ("cup", "demo_claimant", "PENDING", "我的深蓝色保温杯底有TEST-08标签，供撤回申请测试。"),
        ]
        for key, applicant, status, proof in claim_specs:
            cursor = connection.execute("INSERT INTO claims(item_id,applicant_id,proof,status,review_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (item_ids[key], account_ids[applicant], proof, status, "物品已由其他申请人领取" if status == "CANCELLED" else "", timestamp, timestamp))
            manifest["claims"].append({"id": cursor.lastrowid, "item_id": item_ids[key], "item_key": key, "applicant": applicant, "status": status})
        connection.execute("INSERT INTO audit_logs(actor_id,action,target_type,target_id,reason,created_at) VALUES(?,?,'demo',0,?,?)", (administrator["id"], SEED_ACTION, json.dumps(manifest, ensure_ascii=False), timestamp))
        connection.commit()
        write_inventory(directory, manifest)
        return manifest, True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="追加虚构本地测试数据，保留现有账号和业务。")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    arguments = parser.parse_args()
    try:
        result, created = seed(arguments.data_dir)
        print("Created demo data." if created else "Demo data already exists; business states were preserved.")
        print(f"Accounts: {len(result['accounts'])}; items: {len(result['items'])}; claims: {len(result['claims'])}")
        print(f"Account inventory: {arguments.data_dir.resolve() / '测试账号与数据.md'}")
    except (RuntimeError, sqlite3.Error) as error:
        raise SystemExit(str(error)) from error
