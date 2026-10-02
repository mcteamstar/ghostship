# TRN-173: seed_kiro_db.py — verify migration count against KiroCrew 0.7.2

## Problem

The graduation image pre-seeds the kiro-cli SQLite migration DB at build time
(`crews/_base/graduation/seed_kiro_db.py`). The seed is hard-coded to KiroCrew
0.5.0: 10 migration rows, versions 0–9, max_version 9.

The base image has since been bumped from 0.5.0 to 0.6.0, and the 0.6.0
verification was deferred and never completed (TRN-113 / TRN-149). Now the
target is 0.7.2, which ships kiro-cli 2.24.0. The 0.7.0 release introduced
significant new subsystems (crew_log, eventlog, work_ledger, decisions) that
almost certainly added new kiro-cli migrations.

If the seeded DB is missing migrations, kiro-cli will attempt to run them
against an existing DB on first boot — potentially producing incorrect state or
a crash, silently failing, or taking the migration latency we were trying to
avoid.

## Verification result (2026-10-02, academy)

Query run against `ghcr.io/kirodotdev/kirocrew:0.7.2` (kiro-cli 2.24.0):

```
(6, 5)  — 6 rows, versions 0–5, max_version 5
```

Current seed hard-codes `(10, 9)` — **the seed is wrong**. kiro-cli 2.24.0
dropped three tables entirely and reduced the migration count from 10 to 6.

### Schema diff vs current seed

**Removed tables** (no longer exist in kiro-cli 2.24.0):
- `conversations`
- `conversations_v2` (+ 2 indexes)
- `extracted_kas_versions`

**Changed**: `state.value` column type `BLOB` → `TEXT`

**Remaining**: `migrations`, `history`, `state`, `auth_kv`

## Proposed Change

1. Update `seed_kiro_db.py`:
   - Remove the three dropped `CREATE TABLE` / `CREATE INDEX` statements
   - Change `state.value` from `BLOB` to `TEXT`
   - Replace 10 `INSERT INTO migrations` rows with 6 rows (versions 0–5)
   - Update docstring to "KiroCrew 0.7.2 / kiro-cli 2.24.0 (6 rows, versions 0–5, max_version 5)"
2. Update the fragility warning comment in `graduation/Containerfile`.
3. Add a CI regression test (`tests/unit/test_seed_kiro_db.py`) asserting
   `(count, max_version) == (6, 5)` against the pinned base image.

## Scope

- `crews/_base/graduation/seed_kiro_db.py`
- `crews/_base/graduation/Containerfile` (comment update only)
- `tests/unit/test_seed_kiro_db.py` (new — CI regression guard)

## Gate for TRN-166

This change must be completed and merged before `admission/Containerfile` is
bumped to `ghcr.io/kirodotdev/kirocrew:0.7.2`.
