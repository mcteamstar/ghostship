# TRN-293 — Tasks

## T1 — Get v0.11.1 digest

- [ ] 1.1 On corsair or starport, run `podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.11.1`
- [ ] 1.2 Extract the multi-arch index digest (top-level `digest` field, `sha256:...`)
- [ ] 1.3 Record it — this is the value for `KC_BASE_IMAGE`

## T2 — Verify migration schema

- [ ] 2.1 Run the verification command against the v0.11.1 image (see design D2)
- [ ] 2.2 Compare result to v0.10.0 baseline `(6, 5)`
- [ ] 2.3 If identical: update only the verification annotation in `crews/_base/graduation/seed_kiro_db.py` (version → v0.11.1, date → today)
- [ ] 2.4 If different: update migration rows and table-creation statements in `seed_kiro_db.py` to match; record new count and max_version in the annotation

## T3 — Bump Containerfile

- [ ] 3.1 Update `KC_BASE_IMAGE` in `crews/_base/admission/Containerfile` to the v0.11.1 digest from T1.2
- [ ] 3.2 Update the comment block above the ARG (version, digest, verified date)
- [ ] 3.3 Verify `bash -n crews/_base/admission/Containerfile` passes (or equivalent syntax check)

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

- [ ] 6.1 Commit all changes on `release/0.11.0` with message `feat: bump KC_BASE_IMAGE to KiroCrew v0.11.1`
- [ ] 6.2 Bump VERSION and plugin.json files to `0.11.0`
- [ ] 6.3 Write CHANGELOG entry for v0.11.0
- [ ] 6.4 Push `release/0.11.0`, open PR to main, merge squash
- [ ] 6.5 Tag `v0.11.0` on main
- [ ] 6.6 Bump adjutant submodule to v0.11.0, deploy starport
- [ ] 6.7 Create GitHub release for v0.11.0
