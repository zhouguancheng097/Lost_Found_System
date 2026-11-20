from pathlib import Path
from contextlib import closing, contextmanager
import json
import sqlite3
import tempfile
import unittest

from seed_demo import ACCOUNTS, ROOT, seed


class SeedDemoTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "target"
        temporary_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="demo-seed-test-", dir=temporary_root)
        self.directory = Path(self.temporary.name)
        with self.connect() as connection:
            connection.executescript((ROOT / "src/main/resources/schema.sql").read_text(encoding="utf-8"))
            connection.execute("INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES('admin','已有管理员','keep-admin-password','ADMIN','2026-11-13T00:00:00Z')")
            connection.execute("INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES('existing_user','已有用户','keep-user-password','USER','2026-11-13T00:00:00Z')")

    def tearDown(self):
        self.temporary.cleanup()

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.directory / "lostfound.db")) as connection:
            with connection:
                yield connection

    def test_creates_valid_scenarios_and_preserves_existing_accounts(self):
        manifest, created = seed(self.directory)
        self.assertTrue(created)
        self.assertEqual((5, 16, 7), (len(manifest["accounts"]), len(manifest["items"]), len(manifest["claims"])))
        with self.connect() as connection:
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())
            self.assertEqual("keep-admin-password", connection.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0])
            self.assertEqual("keep-user-password", connection.execute("SELECT password_hash FROM users WHERE username='existing_user'").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM users WHERE status='BANNED'").fetchone()[0])
        with closing(sqlite3.connect(manifest["backup"])) as backup:
            self.assertEqual(2, backup.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        self.assertEqual(b"\x89PNG\r\n\x1a\n", (self.directory / "demo-files/demo-photo.png").read_bytes()[:8])

    def test_rerun_preserves_business_changes_and_does_not_duplicate(self):
        manifest, _ = seed(self.directory)
        identifier = manifest["items"][0]["id"]
        with self.connect() as connection:
            connection.execute("UPDATE items SET status='CLOSED' WHERE id=?", (identifier,))
        repeated, created = seed(self.directory)
        self.assertFalse(created)
        self.assertEqual(manifest, repeated)
        with self.connect() as connection:
            self.assertEqual(7, connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            self.assertEqual(16, connection.execute("SELECT COUNT(*) FROM items").fetchone()[0])
            self.assertEqual("CLOSED", connection.execute("SELECT status FROM items WHERE id=?", (identifier,)).fetchone()[0])

    def test_username_collision_rolls_back_and_preserves_password(self):
        with self.connect() as connection:
            connection.execute("INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES(?, '原有同名用户','original-password','USER','2026-11-13T00:00:00Z')", (ACCOUNTS[1][0],))
        with self.assertRaisesRegex(RuntimeError, "未覆盖"):
            seed(self.directory)
        with self.connect() as connection:
            self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM items").fetchone()[0])
            self.assertEqual("original-password", connection.execute("SELECT password_hash FROM users WHERE username=?", (ACCOUNTS[1][0],)).fetchone()[0])

    def test_recovers_inventory_from_committed_database(self):
        manifest, _ = seed(self.directory)
        (self.directory / "demo-fixtures.json").unlink()
        repeated, created = seed(self.directory)
        self.assertFalse(created)
        self.assertEqual(manifest, repeated)
        self.assertEqual(manifest, json.loads((self.directory / "demo-fixtures.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
