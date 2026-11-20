PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('USER','ADMIN')),
 status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','BANNED','DELETED')),
 ban_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
 phone TEXT NOT NULL DEFAULT '', default_address TEXT NOT NULL DEFAULT '', session_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL REFERENCES users(id),
 type TEXT NOT NULL CHECK(type IN ('LOST','FOUND')), title TEXT NOT NULL, category TEXT NOT NULL,
 description TEXT NOT NULL, location TEXT NOT NULL, event_date TEXT NOT NULL, contact TEXT NOT NULL,
 hidden_features TEXT NOT NULL DEFAULT '', status TEXT NOT NULL CHECK(status IN ('PENDING','REJECTED','OPEN','HANDOVER','CLAIMED','RESOLVED','CLOSED')),
 review_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attachments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL REFERENCES users(id), stored_name TEXT NOT NULL UNIQUE,
 mime TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('PUBLIC','PROOF')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS item_images (
 item_id INTEGER NOT NULL REFERENCES items(id), attachment_id INTEGER NOT NULL UNIQUE REFERENCES attachments(id), PRIMARY KEY(item_id,attachment_id)
);
CREATE TABLE IF NOT EXISTS claims (
 id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL REFERENCES items(id), applicant_id INTEGER NOT NULL REFERENCES users(id),
 proof TEXT NOT NULL, proof_attachment_id INTEGER REFERENCES attachments(id),
 status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','WITHDRAWN','COMPLETED','CANCELLED')),
 review_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS claims_active_user ON claims(item_id,applicant_id) WHERE status IN ('PENDING','APPROVED');
CREATE UNIQUE INDEX IF NOT EXISTS claims_one_winner ON claims(item_id) WHERE status IN ('APPROVED','COMPLETED');
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), message TEXT NOT NULL,
 is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL,
 target_type TEXT NOT NULL, target_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS items_public ON items(status,type,deleted);
CREATE INDEX IF NOT EXISTS claims_item ON claims(item_id,status);
CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id,is_read);
