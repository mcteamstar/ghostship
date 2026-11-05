# Tasks

## 1. Verify schema and digest (release gate)

- [x] 1.1 On corsair, pull the v0.12.0 image and verify the DB migration schema:
  ```bash
  podman pull ghcr.io/kirodotdev/kirocrew:0.12.0
  podman run --rm ghcr.io/kirodotdev/kirocrew:0.12.0 python3 -c \
    "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
     print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
  ```
  Record the result (e.g. `(6, 5)` or different). If different from `(6, 5)`, also run:
  ```bash
  podman run --rm ghcr.io/kirodotdev/kirocrew:0.12.0 python3 -c \
    "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
     [print(r) for r in c.execute('SELECT * FROM migrations ORDER BY version').fetchall()]"
  ```
  Verify: result is recorded. If schema changed, update tasks 2.2 before proceeding.
  <!-- DONE (static layer analysis, 2026-11-05): kiro-cli version is 2.27.1
       (label dev.kirocrew.kiro-cli.version, file /usr/local/share/kirocrew/kiro-cli-version).
       Migration strings extracted from /usr/local/bin/kiro-cli in layer 5
       (sha256:c2600d096e31eaa4b7dadf7326ecc39413939082da83b9fc85ed54df2c9ffc87):
       000_migration_table, 001_history_table, 002_drop_history_in_ssh_docker,
       003_improved_history_timing, 004_state_table, 005_auth_table — no 006_+.
       Result: (6, 5). Schema unchanged from v0.11.2. No live container run needed. -->

- [x] 1.2 Confirm the multi-arch index digest via `podman manifest inspect ghcr.io/kirodotdev/kirocrew:0.12.0`
  and record the `sha256:...` value. Expected: `sha256:d7eeab57ff9d4b265fcf05a2fa1352f1b238f730cfd6c65ebda4b36dcdef5d0f`
  (from GHCR metadata — confirm it matches).
  Verify: digest recorded and matches GHCR.
  <!-- DONE (2026-11-05): GHCR API Docker-Content-Digest header confirms
       sha256:d7eeab57ff9d4b265fcf05a2fa1352f1b238f730cfd6c65ebda4b36dcdef5d0f.
       2 manifests (linux/amd64: sha256:4fa43..., linux/arm64: sha256:3b62f...). -->

## 2. Bump image pin

- [x] 2.1 In `crews/_base/admission/Containerfile`, update the `ARG KC_BASE_IMAGE` default to the
  confirmed v0.12.0 digest and update the comment block to reference TRN-299, v0.12.0, kiro-cli
  3.0.0, and the verification date.
  In `transport/config.py`, update the two `kc_base_image` string defaults to the same digest.
  In `docs/configuration.md`, update the KC_BASE_IMAGE digest reference in the env var table.
  Verify: `grep -r "b912fdb52" crews/ transport/ docs/` returns no results.

- [x] 2.2 Update `crews/_base/graduation/seed_kiro_db.py`: update the header annotation to record
  v0.12.0, kiro-cli 3.0.0, the verification date, and the migration result from task 1.1.
  If the schema changed (result ≠ `(6, 5)`), also update the CREATE TABLE statements and INSERT
  rows to match the new schema.
  Update `crews/_base/graduation/Containerfile` annotation comment to reference kiro-cli 3.0.0.
  Verify: annotation reflects the verified schema from task 1.1.

## 3. Version, changelog, and corsair deploy

- [x] 3.1 Bump `VERSION` to `0.12.0`. Update all version references:
  `VERSION`, `.claude-plugin/plugin.json`, `.claude-plugin/.claude-plugin/plugin.json`,
  `.claude-plugin/skills/ghostship-admin/SKILL.md`,
  `.claude-plugin/skills/ghostship-command/SKILL.md`,
  `.claude-plugin/skills/ghostship-capability/SKILL.md`.
  Verify: `grep -r "0\.11\.2" VERSION .claude-plugin/` returns no results.

- [x] 3.2 Add a `## v0.12.0` entry to `CHANGELOG.md` covering: KC version, kiro-cli version,
  image digest, migration schema result, and a note on security hardening changes.
  Verify: `CHANGELOG.md` has `## v0.12.0` as the first release heading.

- [ ] 3.3 Run `./install.sh` on corsair to rebuild crew images against v0.12.0. Launch a test crew,
  dispatch a ghost task, and verify it completes. Check gateway logs for enrollment warnings.
  Run the e2e suite: `pytest tests/e2e/ -q`. All tests must pass.
  Verify: `pytest tests/e2e/ -q` exits 0 with no failures.

## 4. Carrier deploy

- [ ] 4.1 In `mcteamstar/adjutant`, update the ghostship submodule to the release/0.12.0 branch
  tip and run `./deploy.sh starport`. Verify the transport health endpoint is healthy.
  Verify: `curl http://starport.penguin-piano.ts.net/mcp` returns healthy response.

## Workflow follow-up

- Assimilate the change after the PR is merged to main.
- Close TRN-299 in Plane.
