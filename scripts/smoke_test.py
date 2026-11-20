import http.cookiejar
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ""
        self.csrf = self.call("GET", "/api/session")["csrf"]

    def call(self, method, path, body=None, expected=200):
        headers = {"X-CSRF-Token": self.csrf}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            assert response.status == expected, (path, response.status, result)
            return result

    def login(self, username, password):
        result = self.call("POST", "/api/login", {"username": username, "password": password})
        self.csrf = result["csrf"]
        return result["user"]


def main():
    admin = Client()
    credentials = (ROOT / "data" / "admin-credentials.txt").read_text(encoding="utf-8").splitlines()
    admin.login("admin", credentials[1].split("：", 1)[1])
    clients = []
    accounts = []
    for index in range(3):
        client = Client()
        username = "smoke_" + uuid.uuid4().hex[:12]
        account = client.call("POST", "/api/register", {"username": username, "display_name": f"验收测试{index}", "password": "SmokeTestPassword123"})
        client.login(username, "SmokeTestPassword123")
        clients.append(client)
        accounts.append(account)
    owner, first, second = clients
    item = owner.call("POST", "/api/items", {"type": "FOUND", "title": "验收测试：黑色折叠雨伞", "category": "雨伞", "description": "图书馆二楼拾到黑色折叠雨伞，带挂绳", "location": "图书馆", "event_date": time.strftime("%Y-%m-%d"), "contact": "测试私密联系方式", "hidden_features": "测试隐藏特征", "images": []})
    identifier = item["id"]
    Client().call("GET", f"/api/items/{identifier}", expected=404)
    admin.call("POST", f"/api/admin/items/{identifier}/review", {"approve": True, "reason": "本机验收"})
    public = Client().call("GET", f"/api/items/{identifier}")
    assert "contact" not in public and "hidden_features" not in public
    first.call("DELETE", f"/api/items/{identifier}", expected=403)
    applications = [client.call("POST", f"/api/items/{identifier}/claims", {"proof": "验收证明：遗失在图书馆二楼，挂绳上有标记"}) for client in (first, second)]
    search = Client().call("GET", "/api/items?q=" + urllib.parse.quote("图书馆黑色雨伞"))
    assert search["mode"] == "hybrid" and identifier in [entry["id"] for entry in search["items"]]
    admin.call("POST", f"/api/admin/claims/{applications[0]['id']}/approve", {"reason": "验证完成"})
    admin.call("POST", f"/api/admin/claims/{applications[1]['id']}/approve", {"reason": "重复交接"}, expected=409)
    assert first.call("GET", f"/api/items/{identifier}")["contact"] == "测试私密联系方式"
    assert "contact" not in second.call("GET", f"/api/items/{identifier}")
    admin.call("POST", f"/api/admin/claims/{applications[0]['id']}/complete", {"reason": "已完成测试交接"})
    assert first.call("GET", "/api/mine/claims")[0]["status"] == "COMPLETED"
    assert second.call("GET", "/api/mine/claims")[0]["status"] == "CANCELLED"
    assert admin.call("GET", f"/api/items/{identifier}")["status"] == "CLAIMED"
    admin.call("DELETE", f"/api/items/{identifier}")
    for account in accounts:
        admin.call("POST", f"/api/admin/users/{account['id']}/delete", {"reason": "结束本机验收，匿名化测试账号"})
    report = {"ok": True, "search_mode": search["mode"], "scenarios": ["真实HTTP注册登录与会话", "审核前信息保密", "非本人删除被拒绝", "私密字段保护", "多人申领", "混合检索", "唯一交接人", "批准后联系信息授权", "完成后其他申请取消", "测试数据逻辑删除和账号匿名化"]}
    (ROOT / "docs" / "联调结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
