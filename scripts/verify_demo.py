import json
from pathlib import Path
import urllib.parse

from smoke_test import Client

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "data/demo-fixtures.json").read_text(encoding="utf-8"))
    password = "Demo123456!"
    sessions = {}
    for account in manifest["accounts"]:
        client = Client()
        if account["status"] == "BANNED":
            client.call("POST", "/api/login", {"username": account["username"], "password": password}, expected=403)
        else:
            profile = client.login(account["username"], password)
            assert profile["id"] == account["id"] and profile["role"] == "USER"
            sessions[account["username"]] = client
    administrator = Client()
    credentials = (ROOT / "data/admin-credentials.txt").read_text(encoding="utf-8").splitlines()
    administrator.login("admin", credentials[1].split("：", 1)[1])
    visitor = Client()
    identifiers = {item["key"]: item["id"] for item in manifest["items"]}
    for key in ("pending", "rejected"):
        visitor.call("GET", f"/api/items/{identifiers[key]}", expected=404)
    public = visitor.call("GET", f"/api/items/{identifiers['umbrella']}")
    assert "contact" not in public and "hidden_features" not in public
    assert public["claim_count"] == 2
    approved = sessions["demo_owner"].call("GET", f"/api/items/{identifiers['keys']}")
    assert "contact" in approved and "hidden_features" not in approved
    unapproved = sessions["demo_claimant"].call("GET", f"/api/items/{identifiers['keys']}")
    assert "contact" not in unapproved
    checks = {}
    for query, key in (("学生卡", "card"), ("装电脑的灰色包", "laptop_bag"), ("黑色华为mate60", "huawei")):
        result = visitor.call("GET", "/api/items?" + urllib.parse.urlencode({"q": query, "type": "FOUND"}))
        assert identifiers[key] in [item["id"] for item in result["items"][:5]], (query, key)
        checks[query] = {"mode": result["mode"], "expected_in_top5": True}
    actual_claims = administrator.call("GET", "/api/admin/claims")
    indexed_claims = {claim["id"]: claim for claim in actual_claims}
    for claim in manifest["claims"]:
        assert indexed_claims[claim["id"]]["status"] == claim["status"]
    print(json.dumps({"ok": True, "accounts_verified": 5, "fixture_items": 16, "fixture_claims": 7, "queries": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
