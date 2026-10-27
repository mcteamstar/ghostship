# TRN-271: Upgrade Ghostship to KiroCrew 0.10.0

## Why

KiroCrew 0.10.0 was released 2026-10-25. Ghostship `release/0.9.0` is currently
pinned to `ghcr.io/kirodotdev/kirocrew@sha256:108e6b94...` (v0.9.0 stable).

Research was completed by Wraith on carrier crew `trn-271-kirocrew-upgrade`
(task `e4fe5e4c72e4b482`) against KiroCrew v0.10.0 source and the current
ghostship branch. Full report evacuated to `/tmp/trn-271-research-report.md`.

Notable 0.10.0 highlights relevant to ghostship: Crewmates (Preview), dashboards
out of preview, `kirocrew-team-lead` default agent, KAS without kiro-cli,
turn time limits, remote crews (Lambda MicroVM + EC2), Crew Mode, `kirocrew
tailnet up`, Linux arm64 desktop, persistent Browser Mode, push-to-talk voice,
sandbox default changed to `auto`, session-identity signing hardening,
and `spawn_run backend=` per-task parameter.

## What Changes

### Required

- **Bump `KC_BASE_IMAGE`** in `crews/_base/admission/Containerfile:23` to the
  0.10.0 multi-arch index digest from `ghcr.io/kirodotdev/kirocrew:0.10.0`.
  Update the inline comment (lines 18–22) with this TRN and date.

- **Update `transport/config.py`** — the v0.9.0 SHA is hardcoded as the default
  value in two places (lines 298 and 486). Both must be updated to the 0.10.0
  digest alongside the Containerfile bump.

- **Verify or update `seed_kiro_db.py`** — currently calibrated for kiro-cli
  2.32.0 (6 migrations, versions 0–5). Must verify against the actual 0.10.0
  image layer before release. Verification procedure is in
  `crews/_base/graduation/Containerfile` lines 30–45. ⚠️ Highest risk: if
  wrong, crew containers start with an incomplete DB and kiro-cli may fail
  to start.

### Optional (decide at implementation)

- **Memory controls in `_patch_crew_config()`** — 0.10.0 adds:
  - `memory.embedding_idle_evict_secs` (default 3600; consider 600 to reclaim
    ~1.2 GB after idle tasks)
  - `memory.writes_enabled: false` for ephemeral crews
  - `memory.lesson_extraction_enabled: false` for ephemeral crews
  File: `transport/lifecycle.py`, `_patch_crew_config()` ~line 1665.

- **Crew log disk hygiene** — 0.10.0 enables crew logs by default. Consider
  injecting `KIROCREW_CREW_LOG=0` into `container_env` in
  `transport/tools.py:759–765` if disk growth on spec-ops crews is a concern.

- **Document `spawn_run backend=`** in ghostship-spawn skill and SDD order
  templates (new per-task backend selection in 0.10.0).

- **Update docs** — `docs/architecture.md` references `kirocrew:0.9.0-insider.4`
  (two occurrences) and `docs/configuration.md` has the v0.9.0 digest inline.

## What does NOT change

- **`MC_` → `KIROCREW_` rename** — ghostship has zero `MC_*` references.
  Already on `KIROCREW_*` everywhere. No action needed.
- Transport-to-crew HTTP auth path — unchanged in 0.10.0.
- Worker and transport Containerfiles — independent of KC version.
- Sandbox config (`sandbox: "off"`, `sandbox_allow_unsandboxed_exec: true`) —
  unchanged; verify 0.10.0 has no new startup checks.

## Capabilities

### Modified Capabilities
- `crew-lifecycle` — `KC_BASE_IMAGE` version bump, `seed_kiro_db.py` verification

## Impact

- `crews/_base/admission/Containerfile:23` — `ARG KC_BASE_IMAGE=` default + comment
- `transport/config.py:298,486` — hardcoded SHA default (two occurrences)
- `crews/_base/graduation/seed_kiro_db.py` — migration count (verify/update)
- `crews/_base/graduation/Containerfile:30–45` — kiro-cli version comment
- `transport/lifecycle.py` `_patch_crew_config()` — optional memory config keys
- `transport/tools.py:759–765` — optional `KIROCREW_CREW_LOG=0`
- `docs/architecture.md` — stale version references (optional cleanup)
- `docs/configuration.md` — stale SHA inline (optional cleanup)
- Academy skills/SDD templates — optional `spawn_run backend=` docs
