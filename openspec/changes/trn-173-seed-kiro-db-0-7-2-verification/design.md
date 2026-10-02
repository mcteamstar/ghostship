# Design: TRN-173 seed_kiro_db.py — 0.7.2 verification

## Verification approach

The kiro-cli SQLite DB lives at `/home/kirocrew/.local/share/kiro-cli/data.sqlite3`
inside the KiroCrew image. The image's own Python can query it at container start.

```bash
podman run --rm ghcr.io/kirodotdev/kirocrew:0.7.2 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
   print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
```

This must be run on a host where the image is pullable (academy, or any host
with Podman and access to ghcr.io).

## Expected outcome

The current seed hard-codes:
```python
INSERT INTO migrations (version, migration_time) VALUES
    (0, ...), (1, ...), ..., (9, ...);   # 10 rows, max_version 9
```

KiroCrew 0.7.0 added `crew_log`, `eventlog`, `work_ledger`, `decisions`, and
other new subsystems. Each new subsystem that needs persistent storage gets a
kiro-cli migration. The migration count for 0.7.2 is expected to be higher.

## If count differs — update seed_kiro_db.py

Extract the full schema from the 0.7.2 image:
```bash
podman run --rm ghcr.io/kirodotdev/kirocrew:0.7.2 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
   print(c.execute(\"SELECT sql FROM sqlite_master WHERE type='table'\").fetchall())"
```

Then update `seed_kiro_db.py`:
- Add any new `CREATE TABLE` / `CREATE INDEX` statements
- Add the new `INSERT INTO migrations` rows

Verify the updated script produces the correct count by running it in a
throwaway container:
```bash
podman run --rm ghcr.io/kirodotdev/kirocrew:0.7.2 bash -c \
  "python3 /tmp/seed_kiro_db.py && python3 -c \
  \"import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
  print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())\""
```

## CI regression guard (new test)

Add `tests/unit/test_seed_kiro_db.py` with a test that:
1. Pulls the base image tag from `crews/_base/admission/Containerfile` at
   test time (or reads a fixture constant)
2. Runs `seed_kiro_db.py` in a throwaway container via `podman run`
3. Queries the resulting DB and asserts `(count, max_version)` matches the
   hard-coded expected value in `seed_kiro_db.py`

This test will be slow (pulls image) so mark it `@pytest.mark.slow` and
exclude from the default unit run; add to a separate CI step.

## Files changed

| File | Change |
|------|--------|
| `crews/_base/graduation/seed_kiro_db.py` | Update DDL + migrations to match 0.7.2; update docstring |
| `crews/_base/graduation/Containerfile` | Update fragility warning comment to "0.7.2 (verified)" |
| `tests/unit/test_seed_kiro_db.py` | New — CI regression guard |
