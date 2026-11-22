"""Pre-seed the kiro-cli SQLite DB with schema and migrations.

Verified 2026-11-22 against the KiroCrew v0.13.1 GHCR index
sha256:080c81417fd67d03ca28fdd983cb309efbcea8ee618adaeeb75a2ed96bcf58d1,
amd64 manifest sha256:a6b29dacc90f862c7f81cf1065d36f413f586609f479a1f42fad278de5754861,
and arm64 manifest sha256:2a6477e5acbbf1d411a2128264bbb9d47f9811c6d66840195a187fa954fb7d3d.
Both images label the bundled Kiro CLI as 2.27.1. Running
``kiro-cli-chat whoami`` in fresh, network-isolated containers initialized the
same ``data.sqlite3`` schema on both architectures: 11 chat migrations
(versions 0 through 10), eight tables, and the two explicit conversation
indexes. The rows, columns, and indexes match ``SCHEMA_SQL``; the seed is
unchanged for this pin.

If a later image changes the initialized migration sequence or schema, update
this seed and its focused test before advancing the base-image pin.
"""
from __future__ import annotations

import contextlib
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
    # sqlite3's context manager commits but does not close; closing() does.
    with contextlib.closing(sqlite3.connect(str(db))) as conn:
        with conn:
            conn.executescript(SCHEMA_SQL)
    os.chmod(str(db), 0o600)
    print(f"kiro-cli DB pre-seeded at {db}")


def main() -> None:
    db_dir = pathlib.Path("/home/kirocrew/.local/share/kiro-cli")
    seed_database(db_dir / "data.sqlite3")


if __name__ == "__main__":
    main()
