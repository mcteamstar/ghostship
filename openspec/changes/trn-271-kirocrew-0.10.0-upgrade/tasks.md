# Tasks: TRN-271 — Upgrade Ghostship to KiroCrew 0.10.0

## Required

- [ ] Get the 0.10.0 multi-arch index digest from `ghcr.io/kirodotdev/kirocrew:0.10.0`
  **DONE:** `sha256:62ebe7a796e7653857d34b5daf08a93e123bf2af66559bc3bacb1c7af1eeaed2` (verified 2026-10-26 on starport; kiro-cli 2.34.0)
- [ ] Verify `seed_kiro_db.py` migration schema against the 0.10.0 image layer (follow procedure in `crews/_base/graduation/Containerfile:30–45`)
  **DONE:** Migration count still (6, 5) — schema unchanged. `seed_kiro_db.py` needs no edits; update header comment only (kiro-cli version 2.32.0 → 2.34.0).
- [ ] Update `ARG KC_BASE_IMAGE=` in `crews/_base/admission/Containerfile:23` to `ghcr.io/kirodotdev/kirocrew@sha256:62ebe7a796e7653857d34b5daf08a93e123bf2af66559bc3bacb1c7af1eeaed2`
- [ ] Update the inline comment block in `crews/_base/admission/Containerfile:18–22` (TRN-271, 2026-10-26)
- [ ] Update hardcoded SHA default in `transport/config.py:298` and `:486` to the 0.10.0 digest
- [ ] Update `seed_kiro_db.py` header comment: kiro-cli version 2.32.0 → 2.34.0, update verification date and SHA
- [ ] Update kiro-cli version reference in `crews/_base/graduation/Containerfile` comment (2.32.0 → 2.34.0)

## Optional

- [ ] Add `memory.embedding_idle_evict_secs: 600` to `_patch_crew_config()` in `transport/lifecycle.py`
- [ ] Add `memory.writes_enabled: false` and `memory.lesson_extraction_enabled: false` to `_patch_crew_config()` for ephemeral crew hygiene
- [ ] Add `KIROCREW_CREW_LOG=0` to `container_env` in `transport/tools.py:759–765` (crew log disk hygiene)
- [ ] Document `spawn_run backend=` per-task parameter in ghostship-spawn skill / SDD order templates
- [ ] Update stale version references in `docs/architecture.md` (two occurrences of `kirocrew:0.9.0-insider.4`) and `docs/configuration.md` (inline SHA)

## Deploy

- [ ] Update ghostship submodule pointer in `mcteamstar/adjutant` to new release branch
- [ ] `cd ~/development/mcteamstar/adjutant/hyperv && ./deploy.sh starport`
- [ ] Verify carrier crews are healthy after restart
