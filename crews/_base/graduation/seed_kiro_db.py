"""Pre-seed the kiro-cli SQLite DB with schema + migrations.

Baked into the crew image at build time so kiro-cli finds the DB already
initialised — transport only needs to INSERT auth_kv rows at launch,
with no migration wait and no restart cycle.

⚠️  Migration schema for KiroCrew 0.7.2 / kiro-cli 2.24.0 (6 rows, versions 0-5, max_version 5).
    Verified 2026-10-02 against ghcr.io/kirodotdev/kirocrew:0.7.2: result (6, 5).
    Tables: migrations, history, state (value TEXT), auth_kv.
    Removed vs 0.5.0 seed: conversations, conversations_v2 (+2 indexes), extracted_kas_versions.
    When updating the FROM pin to a newer kirocrew version, re-verify:
      podman run --rm ghcr.io/kirodotdev/kirocrew:<tag> python3 -c \
        "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
         print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
    If count or schema differ, update this file and Containerfile before release.
    See crews/_base/graduation/Containerfile for the checklist.
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
    value TEXT
);
INSERT INTO migrations (version, migration_time) VALUES
    (0, 1700000000),
    (1, 1700000000),
    (2, 1700000000),
    (3, 1700000000),
    (4, 1700000000),
    (5, 1700000000);
""")
conn.close()
os.chmod(str(db), 0o600)
print(f"kiro-cli DB pre-seeded at {db}")
