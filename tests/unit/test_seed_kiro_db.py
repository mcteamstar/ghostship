"""Focused tests for the pre-seeded Kiro CLI database schema."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "crews" / "_base" / "graduation" / "seed_kiro_db.py"
SPEC = importlib.util.spec_from_file_location("seed_kiro_db", SEED_PATH)
assert SPEC is not None and SPEC.loader is not None
seed_kiro_db = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_kiro_db)


def test_seed_matches_v0122_chat_database_schema(tmp_path):
    db = tmp_path / "kiro-cli" / "data.sqlite3"
    seed_kiro_db.seed_database(db)

    with sqlite3.connect(str(db)) as conn:
        versions = conn.execute(
            "SELECT version FROM migrations ORDER BY version"
        ).fetchall()
        assert versions == [(version,) for version in range(11)]
        assert conn.execute(
            "SELECT COUNT(*), MAX(version) FROM migrations"
        ).fetchone() == (11, 10)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables == {
            "auth_kv",
            "history",
            "migrations",
            "state",
            "conversations",
            "conversations_v2",
            "extracted_kas_versions",
            "pinned_bin_versions",
        }

        state_columns = conn.execute("PRAGMA table_info(state)").fetchall()
        assert [(row[1], row[2], row[5]) for row in state_columns] == [
            ("key", "TEXT", 1),
            ("value", "BLOB", 0),
        ]

        auth_columns = conn.execute("PRAGMA table_info(auth_kv)").fetchall()
        assert [(row[1], row[2], row[5]) for row in auth_columns] == [
            ("key", "TEXT", 1),
            ("value", "TEXT", 0),
        ]

        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "idx_conversations_v2_key_updated",
            "idx_conversations_v2_updated_at",
        } <= indexes
