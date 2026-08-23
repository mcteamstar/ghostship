"""Pre-seed the kiro-cli SQLite DB with schema + migrations.

Baked into the crew image at build time so kiro-cli finds the DB already
initialised — transport only needs to INSERT auth_kv rows at launch,
with no migration wait and no restart cycle.

⚠️  Migration schema from kirocrew 0.2.0 (10 rows, versions 0-9).
    If kiro-cli adds migrations in a future release, update this file.
    See crews/spec-ops/Containerfile for the upgrade checklist.
"""
import os
import pathlib
import sqlite3

db_dir = pathlib.Path("/home/kirocrew/.local/share/kiro-cli")
db_dir.mkdir(parents=True, exist_ok=True)
db = db_dir / "data.sqlite3"

conn = sqlite3.connect(str(db))
conn.executescript("""
CREATE TABLE auth_kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE conversations (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE conversations_v2 (
    key TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (key, conversation_id)
);
CREATE INDEX idx_conversations_v2_key_updated ON conversations_v2(key, updated_at DESC);
CREATE INDEX idx_conversations_v2_updated_at ON conversations_v2(updated_at DESC);
CREATE TABLE extracted_kas_versions (
    version TEXT PRIMARY KEY,
    last_used_at INTEGER NOT NULL
);
CREATE TABLE history (
    id INTEGER PRIMARY KEY,
    command TEXT,
    shell TEXT,
    pid INTEGER,
    session_id TEXT,
    cwd TEXT,
    start_time INTEGER,
    hostname TEXT,
    exit_code INTEGER,
    end_time INTEGER,
    duration INTEGER
);
CREATE TABLE migrations (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    migration_time INTEGER NOT NULL
);
CREATE TABLE state (
    key TEXT PRIMARY KEY,
    value BLOB
);
INSERT INTO migrations (version, migration_time) VALUES
    (0, 1700000000),
    (1, 1700000000),
    (2, 1700000000),
    (3, 1700000000),
    (4, 1700000000),
    (5, 1700000000),
    (6, 1700000000),
    (7, 1700000000),
    (8, 1700000000),
    (9, 1700000000);
""")
conn.close()
os.chmod(str(db), 0o600)
print(f"kiro-cli DB pre-seeded at {db}")
