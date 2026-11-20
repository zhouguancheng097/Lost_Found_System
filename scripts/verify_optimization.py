"""Verify the updated HTTP flow using an isolated verification database only."""
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

import smoke_test
from smoke_test import Client

ROOT = Path(__file__).resolve().parents[1]
smoke_test.BASE = "http://127.0.0.1:18080"


def main():
    health = json.load(urllib.request.urlopen(smoke_test.BASE + "/api/health"))
    assert health["ok"] and health["ai"], health
    admin = Client()
    credentials = (ROOT / "target/optimization-data/admin-credentials.txt").read_text(encoding="utf-8").splitlines()
    admin.login("admin", credentials[1].split("：", 1)[1])
    # Only the dedicated verification account in the isolated test database may be reset.
    for account in admin.call("GET", "/api/admin/users"):
        if account["username"] == "optimization_owner" and account["status"] == "ACTIVE":
            for item in admin.call("GET", "/api/admin/items"):
                if item["owner_id"] == account["id"] and not item["deleted"]:
                    admin.call("DELETE", f"/api/items/{item['id']}")
            admin.call("POST", f"/api/admin/users/{account['id']}/delete", {"reason": "清理上一轮隔离验收数据"})
    owner = Client()
    owner.call("POST", "/api/register", {"username": "optimization_owner", "display_name": "优化验收", "password": "VerifyOnly123!"})
    old_csrf = owner.csrf
    owner.login("optimization_owner", "VerifyOnly123!")
    assert old_csrf != owner.csrf
    fixtures = [
        ("苹果 iPhone 15 手机", "白色苹果手机，粉色保护壳", "数码电子"),
        ("华为 Mate 60 手机", "黑色华为手机，透明保护壳", "数码电子"),
        ("黑色折叠雨伞", "黑色折叠伞，伞柄带挂绳", "雨伞"),
        ("蓝色卡套校园卡", "校园卡一张，蓝色卡套，姓名已隐藏", "证件卡片"),
        ("灰色笔记本电脑包", "装笔记本电脑的灰色包，内有电源适配器", "包袋"),
        ("蓝色保温杯", "深蓝色保温水杯，黑色杯盖", "水杯餐具"),
    ]
    ids = []
    for title, description, category in fixtures:
        item = owner.call("POST", "/api/items", {"type": "FOUND", "title": title, "description": description, "category": category, "location": "图书馆", "event_date": "2026-11-18", "contact": "仅验收使用", "hidden_features": "隐藏验收细节", "images": []})
        ids.append(item["id"])
        admin.call("POST", f"/api/admin/items/{item['id']}/review", {"approve": True, "reason": "隔离验收"})
    visitor = Client()
    checks = []
    for query, expected in [("苹果", [ids[0]]), ("Apple", [ids[0]]), ("iPhone15", [ids[0]]), ("华为", [ids[1]]), ("黑色雨伞", [ids[2]]), ("学生卡", [ids[3]]), ("吃饭用的卡丢了", [ids[3]]), ("装电脑的灰色包", [ids[4]]), ("蓝色保温杯", [ids[5]]), ("可以保温的蓝色水壶", [ids[5]]), ("昨天在图书馆丢的黑色雨伞", [ids[2]]), ("不存在的紫水晶吊坠", [])]:
        result = visitor.call("GET", "/api/items?" + urllib.parse.urlencode({"q": query}))
        actual = [item["id"] for item in result["items"]]
        assert actual == expected, (query, expected, result)
        assert result["total"] == len(expected) and result["mode"] == "hybrid"
        assert all(item["score"] >= 30 and "contact" not in item and "hidden_features" not in item for item in result["items"])
        checks.append({"query": query, "total": result["total"], "titles": [item["title"] for item in result["items"]], "scores": [item["score"] for item in result["items"]]})
    assert visitor.call("GET", "/api/items")["total"] == len(fixtures)
    assert visitor.call("GET", "/api/items?" + urllib.parse.urlencode({"q": "苹果", "category": "雨伞"}))["total"] == 0
    assert visitor.call("GET", "/api/items?" + urllib.parse.urlencode({"q": "苹果", "pageSize": 1, "page": 2}))["items"] == []
    owner.call("POST", "/api/logout")
    expired = owner.call("POST", "/api/items", {}, expected=401)
    assert "登录态过期" in expired["error"]
    owner.csrf = owner.call("GET", "/api/session")["csrf"]
    owner.login("optimization_owner", "VerifyOnly123!")
    assert owner.call("GET", "/api/mine/items")
    assert "auth-notice" in urllib.request.urlopen(smoke_test.BASE).read().decode("utf-8")
    report = {"ok": True, "date": "2026-11-19", "database": "target/optimization-data/lostfound.db", "model": "BAAI/bge-small-zh-v1.5", "queries": checks, "session_expiry_and_relogin": True, "strict_filters_paging_privacy": True}
    (ROOT / "docs/优化联调结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if not (ROOT / "target/optimization-data/test-processes.json").exists():
        sys.exit("Start the isolated verification services first; do not run against production data.")
    main()
