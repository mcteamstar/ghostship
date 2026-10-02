# TRN-166: Upgrade crew base image to KiroCrew 0.7.2

## Context

Ghostship 0.6.0 branch. The base image pin in `crews/_base/admission/Containerfile`
is currently `ghcr.io/kirodotdev/kirocrew:0.6.0`. KiroCrew 0.7.2 is the current
stable release (released 2026-09-28), shipping kiro-cli 2.24.0.

## Blockers (reassessed 2026-10-02)

**TRN-173 must complete first.** The `seed_kiro_db.py` pre-seeded migration DB
is hard-coded to 0.5.0 values and must be verified / updated against 0.7.2
before the base image is bumped. Bumping without this risks silent DB
inconsistency on first agent boot.

## Proposed Change

1. **Bump base image**: Update `FROM ghcr.io/kirodotdev/kirocrew:0.6.0` to
   `FROM ghcr.io/kirodotdev/kirocrew:0.7.2` in `crews/_base/admission/Containerfile`.
   Update the comment from "Pinned to 0.5.0 semver tag" to "Pinned to 0.7.2 semver tag".

2. **Sandbox config**: Replace `"sandbox": "off"` (or equivalent) in the
   `scripts/install.sh` config patch with `"sandbox_allow_unsandboxed_exec": true`.
   Podman rootless cannot perform user-namespace bind mounts (EPERM). In 0.7.0
   the text credential gate is removed — bind masks are now the only fence —
   so `sandbox: off` leaves no protection. The `sandbox_allow_unsandboxed_exec`
   flag is the correct rootless escape hatch. Verify the agent starts without
   EPERM on academy after the change.

3. **Cron audit**: Review all crew cron definitions (Captain check-in, Raven
   patrol, heartbeat) and confirm they pass the new fire-time policy vetting
   introduced in 0.7.0. Add `minimal_context: true` to Raven patrol and any
   other low-cost polling crons.

4. **Config updates**: In `scripts/install.sh` config patch:
   - Set `orchestrator.max_plan_duration_seconds` to a value above 7200 (e.g.
     14400) so long SDD runs are not cut off by the new 2h default.
   - Remove any `KIRO_API_KEY` references from agent environment (scrubbed in 0.7.0).

5. **Validate on academy**: After rebuilding images with `./install.sh`:
   - Launch a crew, run a Ghost task, confirm agent boots cleanly.
   - Run a Captain check-in (Raven patrol), confirm cron fires correctly.
   - Run a multi-turn Ghost SDD session, confirm resume behaviour with new
     memory injection semantics.

6. **Update version strings**: The `VERSION` file and skill version strings are
   set at release time, not here.

## Scope

- `crews/_base/admission/Containerfile` — bump FROM pin
- `scripts/install.sh` — sandbox config, orchestrator timeout, cron minimal_context
- `openspec/specs/installation/spec.md` — update with new config options
- `docs/architecture.md` — note 0.7.2 base image
