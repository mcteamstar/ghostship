# Tasks: TRN-271 — Upgrade Ghostship to KiroCrew 0.10.0

## Required

- [x] Get the 0.10.0 multi-arch index digest from `ghcr.io/kirodotdev/kirocrew:0.10.0`
  **DONE:** `sha256:b6d0b9a3a666df30d99fcadc6a71ab83cbf4ed1c6521e1b81f0333c5553f3e90` (OCI index digest; resolves arm64 on corsair, amd64 on starport. Initial attempt used the amd64-specific digest from `podman inspect` on starport — corrected by fetching from registry Content-Digest header.)
- [x] Verify `seed_kiro_db.py` migration schema against the 0.10.0 image layer (follow procedure in `crews/_base/graduation/Containerfile:30–45`)
  **DONE:** Migration count still (6, 5) — schema unchanged. kiro-cli 2.34.0 (was 2.32.0). `seed_kiro_db.py` logic unchanged; header comment updated.
- [x] Update `ARG KC_BASE_IMAGE=` in `crews/_base/admission/Containerfile` to 0.10.0 index digest
- [x] Update the inline comment block in `crews/_base/admission/Containerfile` (TRN-271, 2026-10-26, notes arm64/amd64 resolution)
- [x] Update hardcoded SHA default in `transport/config.py:298` and `:486` to the 0.10.0 digest
- [x] Update `seed_kiro_db.py` header comment: kiro-cli version 2.32.0 → 2.34.0, update verification date and SHA
- [x] Update kiro-cli version reference in `crews/_base/graduation/Containerfile` comment (2.32.0 → 2.34.0)
- [x] Bump ghostship version 0.8.1 → 0.9.0 in `VERSION`, `plugin.json` (×2), and all three `SKILL.md` files
- [x] Bump gateway readiness timeout 60s → 120s in `transport/tools.py` — KC 0.10.0 takes ~92s cold start under emulation; native arm64 takes ~9s

## Discovered during implementation

- **Wrong digest class** — `podman inspect` on starport returned the amd64-specific digest, not the OCI index. Using the index digest (fetched via registry Content-Digest header) is the correct approach, matching how 0.9.0 was pinned.
- **Version label timing** — `VERSION` must be bumped before running `./install.sh` so the image label bakes in correctly.
- **Gateway timeout** — even with the native arm64 fix, 120s is the right default for cold starts under emulation and is safer headroom on any slow host.

## Verified on corsair

- `crew_image_version: 0.9.0-spec-ops` ✓
- `kirocrew 0.10.0` / `kiro-cli 2.34.0` inside crews ✓
- Native arm64 image (no Rosetta emulation) ✓
- Cold start: ~9s (was ~92s) ✓
- e2e: 23 passed, 6 skipped (opt-in auth tests) ✓

## Optional

- [ ] Add `memory.embedding_idle_evict_secs: 600` to `_patch_crew_config()` in `transport/lifecycle.py`
- [ ] Add `memory.writes_enabled: false` and `memory.lesson_extraction_enabled: false` to `_patch_crew_config()` for ephemeral crew hygiene
- [ ] Add `KIROCREW_CREW_LOG=0` to `container_env` in `transport/tools.py` (crew log disk hygiene)
- [ ] Document `spawn_run backend=` per-task parameter in ghostship-spawn skill / SDD order templates
- [ ] Update stale version references in `docs/architecture.md` and `docs/configuration.md`

## Deploy

- [x] Update ghostship submodule pointer in `mcteamstar/adjutant` to new release branch
  **DONE:** `adjutant` commit `7dcddd5` bumped submodule to `release/0.9.0` tip (`15454c6`)
- [x] `cd ~/development/mcteamstar/adjutant/hyperv && ./deploy.sh starport`
  **DONE:** Deployed 2026-10-27; transport and crew images rebuilt as `0.9.0` / `0.9.0-spec-ops`
- [x] Verify carrier crews are healthy after restart
  **DONE:** e2e against carrier — 25 passed, 2 skipped (expected), 2 errors (Podman socket locality — pass when run from starport)
