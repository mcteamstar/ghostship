# Design

## Context

See proposal.md — Why for motivation. Research report: `research-kc012.md` (produced by Wraith
on 2026-11-05 from the `trn-299-kc012-research` carrier crew).

KiroCrew v0.12.0 ships kiro-cli 3.0.0 — a major version jump from 2.36.0 (bundled in v0.11.2).
The ghostship upgrade process for prior KC versions (TRN-293, TRN-307) established the pattern:
bump digest → verify migration schema → update seed → deploy to dev → e2e → deploy to carrier.

## Goals / Non-Goals

**Goals:**
- Advance the `KC_BASE_IMAGE` pin to v0.12.0 across all ghostship pin sites.
- Verify the kiro-cli 3.0.0 DB migration schema against the live image and update `seed_kiro_db.py` accordingly.
- Deploy to corsair (dev instance), run e2e, then deploy to carrier.

**Non-Goals:**
- Adopting any new KC 0.12.0 features (Bots, worktrees, Strands harness, Remote dispatch) — this
  is a mechanical bump, not a feature pylon.
- Changing the `GA_CREW_AGENT=kiro-cli` or `kas_bundle=false` default — both are confirmed safe.
- Any changes related to the "Mates → Bots" rename — UI-only, no ghostship code paths affected.

## Decisions

**Same upgrade pattern as TRN-307.**
The change is mechanical: bump four files, verify schema, update seed annotation. No architectural
decisions required.

**Migration schema verification is a release gate — not optional.**
kiro-cli 3.0.0 is a major release. The research crew confirmed it cannot verify schema without a
container runtime. The verification must be done on corsair (the dev Podman machine) as task 1.1,
before any code changes are committed. If the schema changed, the seed INSERT rows and CREATE TABLE
statements in `seed_kiro_db.py` must be updated to match.

**Digest source: podman manifest inspect on corsair.**
The research crew found `sha256:d7eeab57ff9d4b265fcf05a2fa1352f1b238f730cfd6c65ebda4b36dcdef5d0f`
from GHCR metadata. This must be confirmed with `podman manifest inspect` on the dev machine
before pinning, as the research crew had no container runtime.

## Risks / Trade-offs

**[BLOCKER] DB migration schema unknown for kiro-cli 3.0.0.**
V3 introduced cloud sessions, memory, and workspace trust — all features that typically add
migrations. If `seed_kiro_db.py` is not updated and the schema changed, crews start but agents
silently fail to authenticate on first launch.
→ Mitigation: task 1.1 verifies schema before any code changes land.

**[MEDIUM] Security policy compatibility.**
KC 0.12.0 hardened governance for cron and deny rules. Ghostship's `inject_policy.py` writes
`security_policy.json` at launch. A policy format edge case that was silently tolerated before
may now surface as an explicit refusal.
→ Mitigation: full crew startup smoke test (task 3.3) catches this on corsair.

**[LOW] Enrollment endpoint rename.**
"Mates" → "Bots" is UI-only per research, but if the REST endpoint `/api/members/{slug}/thread`
was also renamed to `/api/bots/...`, enrollment fails silently.
→ Mitigation: check gateway logs after first corsair crew launch (task 3.3).
