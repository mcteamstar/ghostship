#!/usr/bin/env python3
"""Inject kiro-cli auth rows into a crew container's SQLite DB.

Runs inside a crew container via
``python3 /scripts/inject_auth.py <db_path>``, where the payload
(a base64-encoded JSON list of ``[key, value]`` pairs, or a versioned dict)
is written to the process's stdin by the caller.

Reading the payload via stdin rather than argv ensures the auth credential
never appears in ``/proc/<pid>/cmdline`` (secret-delivery-hardening spec,
TRN-269).

The DB schema and migrations are pre-seeded in the crew image, so kiro-cli
finds them already applied — direct INSERT, no migration wait needed.

Payload formats (both base64-encoded JSON):
  Legacy (v1): list of [key, value] pairs — written to auth_kv only
  Versioned (v2): {"v": 2, "auth_kv": [[key, value], ...],
                             "state": [[key, value], ...]}

Args (argv):
    1. db_path — path to the kiro-cli SQLite DB

Stdin:
    base64-encoded JSON payload (legacy list or v2 dict)

Prints ``injected <N> auth_kv rows, <M> state rows`` on success.
"""
from __future__ import annotations

import base64
import json
import sqlite3
import sys


def inject_auth(db_path: str, b64_payload: str) -> tuple[int, int]:
    """Insert auth rows into auth_kv and state tables. Returns (auth_kv_count, state_count)."""
    raw = json.loads(base64.b64decode(b64_payload).decode())

    if isinstance(raw, dict) and raw.get("v") == 2:
        # v2 format: separate auth_kv and state rows
        auth_kv_rows = raw.get("auth_kv", [])
        state_rows = raw.get("state", [])
    else:
        # Legacy format: list of [key, value] pairs for auth_kv only
        auth_kv_rows = raw
        state_rows = []

    conn = sqlite3.connect(db_path)
    try:
        if auth_kv_rows:
            conn.executemany(
                "INSERT OR REPLACE INTO auth_kv (key, value) VALUES (?, ?)",
                auth_kv_rows,
            )
        if state_rows:
            conn.executemany(
                "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                state_rows,
            )
        conn.commit()
    finally:
        conn.close()
    return len(auth_kv_rows), len(state_rows)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: inject_auth.py <db_path>  (payload on stdin)", file=sys.stderr)
        return 2
    b64_payload = sys.stdin.read().strip()
    auth_count, state_count = inject_auth(argv[1], b64_payload)
    print(f"injected {auth_count} auth_kv rows, {state_count} state rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
