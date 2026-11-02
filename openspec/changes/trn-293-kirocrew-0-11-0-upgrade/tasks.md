# TRN-293 — Tasks

## T1 — Get v0.11.1 digest

- [x] 1.1 On corsair or starport, run `podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.11.1`
  **DONE:** Obtained via GHCR registry API (tag `0.11.1` without `v` prefix; podman not available in subagent env). Multi-arch index digest fetched via Content-Digest header.
- [x] 1.2 Extract the multi-arch index digest (top-level `digest` field, `sha256:...`)
  **DONE:** `sha256:828ad5140a050414ef5bc9dd5c27e71bb92947ec31c8d2365eee7fa5eecbc587`
- [x] 1.3 Record it — this is the value for `KC_BASE_IMAGE`

## T2 — Verify migration schema

- [x] 2.1 Run the verification command against the v0.11.1 image (see design D2)
  **DONE:** Static layer inspection — extracted migration SQL from `/usr/local/bin/kiro-cli` (2.37.0) in the v0.11.1 image layer (amd64 layer 5, digest `sha256:8c26c2f...`). Migrations 000–005 identical to v0.10.0 (kiro-cli 2.34.0).
- [x] 2.2 Compare result to v0.10.0 baseline `(6, 5)`
  **DONE:** Result `(6, 5)` — unchanged. 6 migrations (versions 0–5). Final history table columns identical.
- [x] 2.3 If identical: update only the verification annotation in `crews/_base/graduation/seed_kiro_db.py` (version → v0.11.1, date → today)
  **DONE:** Updated annotation to v0.11.1 / kiro-cli 2.37.0 / 2026-11-02.
- [ ] 2.4 If different: update migration rows and table-creation statements in `seed_kiro_db.py` to match; record new count and max_version in the annotation

## T3 — Bump Containerfile

- [x] 3.1 Update `KC_BASE_IMAGE` in `crews/_base/admission/Containerfile` to the v0.11.1 digest from T1.2
- [x] 3.2 Update the comment block above the ARG (version, digest, verified date)
- [x] 3.3 Verify `bash -n crews/_base/admission/Containerfile` passes (or equivalent syntax check)
  **DONE:** Python syntax check confirmed ARG before FROM, correct structure.

## T4 — Build and smoke test

- [ ] 4.1 Run `ghostship upgrade` on corsair — confirm spec-ops image rebuilds without error
- [ ] 4.2 Launch a test crew on corsair, dispatch a trivial Ghost task, confirm completion
- [ ] 4.3 Run `ghostship upgrade` on carrier — confirm spec-ops image rebuilds
- [ ] 4.4 Launch a test crew on carrier, dispatch a trivial Ghost task, confirm completion
- [ ] 4.5 Nuke both test crews

## T5 — e2e

- [ ] 5.1 Run `scripts/run.sh --e2e` against corsair — 23 passed
- [ ] 5.2 Run `scripts/run.sh --e2e` against carrier — 23 passed

## T6 — Release

- [x] 6.1 Commit all changes on `release/0.11.0` with message `feat: bump KC_BASE_IMAGE to KiroCrew v0.11.1`
  **DONE:** Committed. See git log.
- [x] 6.2 Bump VERSION and plugin.json files to `0.11.0`
  **DONE:** VERSION, .claude-plugin/plugin.json (×2), three SKILL.md files bumped to 0.11.0.
- [x] 6.3 Write CHANGELOG entry for v0.11.0
  **DONE:** Added v0.11.0 entry with WAL fix, shell reader security fix, CVE list, migration note.
- [ ] 6.4 Push `release/0.11.0`, open PR to main, merge squash
- [ ] 6.5 Tag `v0.11.0` on main
- [ ] 6.6 Bump adjutant submodule to v0.11.0, deploy starport
- [ ] 6.7 Create GitHub release for v0.11.0
