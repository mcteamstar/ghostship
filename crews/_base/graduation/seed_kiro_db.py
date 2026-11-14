"""Pre-seed the kiro-cli SQLite DB with schema and migrations.

The KiroCrew v0.12.2 image includes kiro-cli 2.27.1. Static inspection of the
published amd64 image layer found the main kiro-cli settings migrations
000_migration_table through 005_auth_table, plus the kiro-cli-chat and
kiro-cli-chat-v2 migration sequence through 010_pinned_bin_versions. The chat
sequence is the active task runtime and extends the shared data.sqlite3 schema:
11 migration rows, versions 0 through 10, maximum version 10.

Verified 2026-11-14 against KiroCrew v0.12.2 index
sha256:e5c09209758348ec658c45a06853d4faa3b19fb93c0699ab8eca9c39e32d569e,
amd64 manifest sha256:6f177f87c3850b7dd1f4a81f55f835ca516be55564910ff0a769f6dc9013bc72,
and CLI layer
sha256:0e379673fd4478ede08d7b098838c62f39a4da711d9497dcd726f1fc05176cdc.
The image label dev.kirocrew.kiro-cli.version and the
/usr/local/share/kirocrew/kiro-cli-version marker both identify 2.27.1.
Migration 006 changes state.value to BLOB; 007 and 008 add the conversation
tables and indexes; 009 and 010 add extracted_kas_versions and
pinned_bin_versions. The auth_kv definition is unchanged.

The v0.12.0 baseline used the same CLI version and had migrations 000 through
005 in /usr/local/bin/kiro-cli; its image did not include the chat executable
migration sequence. The former seed therefore matched the main executable but
did not pre-seed the active chat runtime schema. The complete comparison and
release-note review are in docs/dependency-review-2026-11-14.md.

Inspection used the public GHCR manifest and image layer because Podman is not
installed in this environment. The image database was not executed here. On a
Podman host, verify the live result after starting the Kiro CLI runtime with:

  podman run --rm ghcr.io/kirodotdev/kirocrew:0.12.2 python3 -c \
    "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
     print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"

If the image migration sequence changes, update this schema and the focused
test before advancing the base-image pin.
"""
from __future__ import annotations

import os
import pathlib
import sqlite3


SCHEMA_SQL = """
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
    value BLOB
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
CREATE INDEX idx_conversations_v2_key_updated
    ON conversations_v2(key, updated_at DESC);
CREATE INDEX idx_conversations_v2_updated_at
    ON conversations_v2(updated_at DESC);
CREATE TABLE extracted_kas_versions (
    version TEXT PRIMARY KEY,
    last_used_at INTEGER NOT NULL
);
CREATE TABLE pinned_bin_versions (
    version TEXT PRIMARY KEY,
    last_used_at INTEGER NOT NULL
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
    (9, 1700000000),
    (10, 1700000000);
"""


def seed_database(db: pathlib.Path | str) -> None:
    """Create the pre-migrated CLI database at db."""
    db = pathlib.Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        conn.executescript(SCHEMA_SQL)
    os.chmod(str(db), 0o600)
    print(f"kiro-cli DB pre-seeded at {db}")


def main() -> None:
    db_dir = pathlib.Path("/home/kirocrew/.local/share/kiro-cli")
    seed_database(db_dir / "data.sqlite3")


if __name__ == "__main__":
    main()
