# Tasks: TRN-173 seed_kiro_db.py — update for KiroCrew 0.7.2 / kiro-cli 2.24.0

> Verification completed 2026-10-02 on academy. Result: `(6, 5)`.
> Schema: `migrations`, `history`, `state` (value TEXT not BLOB), `auth_kv`.
> Removed: `conversations`, `conversations_v2` (+2 indexes), `extracted_kas_versions`.

## 1. Update seed_kiro_db.py

- [ ] 1.1 Remove `CREATE TABLE conversations` from `executescript`
- [ ] 1.2 Remove `CREATE TABLE conversations_v2` and both its `CREATE INDEX` statements
- [ ] 1.3 Remove `CREATE TABLE extracted_kas_versions`
- [ ] 1.4 Change `state.value` column type from `BLOB` to `TEXT`
- [ ] 1.5 Replace the 10 `INSERT INTO migrations` rows with 6 rows (versions 0–5)
- [ ] 1.6 Update docstring to: "Migration schema for KiroCrew 0.7.2 / kiro-cli 2.24.0 (6 rows, versions 0–5, max_version 5)"

## 2. Update graduation/Containerfile

- [ ] 2.1 Update the `⚠️ FRAGILITY WARNING` comment to reference KiroCrew 0.7.2 (verified 2026-10-02)
- [ ] 2.2 Update the line referencing `kirocrew 0.5.0` to `kirocrew 0.7.2`

## 3. Verify in throwaway container

- [ ] 3.1 Run updated script in a 0.7.2 container and confirm `(count, max_version) == (6, 5)`: `podman run --rm --entrypoint /bin/bash -v ./crews/_base/graduation/seed_kiro_db.py:/tmp/seed_kiro_db.py ghcr.io/kirodotdev/kirocrew:0.7.2 -c "python3 /tmp/seed_kiro_db.py && python3 -c \"import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())\""`

## 4. Add CI regression test

- [ ] 4.1 Create `tests/unit/test_seed_kiro_db.py` that parses the base image tag from `admission/Containerfile`, runs `seed_kiro_db.py` in a throwaway container, and asserts `(count, max_version) == (6, 5)`
- [ ] 4.2 Mark `@pytest.mark.slow` and exclude from the default fast unit run
- [ ] 4.3 Run `python -m pytest tests/unit/ -x -q` (non-slow) and confirm all tests pass

## 5. Commit

- [ ] 5.1 Commit: `trn-173: update seed_kiro_db.py for KiroCrew 0.7.2 / kiro-cli 2.24.0`
- [ ] 5.2 Confirm `openspec validate --change trn-173-seed-kiro-db-0-7-2-verification` passes
