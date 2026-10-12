# Banshee Review — trn-213-config-install-consistency

**Reviewer:** Banshee
**Branch:** `release/0.7.0`
**Implementation commit:** `8b0811d`
**Date:** 2026-10-12

## Scope reviewed

Independent review of the implementation against `proposal.md`, `design.md`,
`tasks.md`, and the two delta specs (`installation`, `config-file`). Covered
`transport/config.py`, `transport/lifecycle.py`, `transport/server.py`,
`scripts/install.sh`, `config/ghostship.conf.example`, `docs/configuration.md`,
and the updated test suite.

## Verification performed

- **Full unit suite:** `tests/unit` → **1324 passed, 3 skipped** (no regressions
  after my fixes).
- **Import smoke:** `import config, lifecycle, server` → OK (the `/data` permission
  warning is a sandbox artifact, not a code issue).
- **install.sh:** `bash -n` syntax OK; deprecation-alias mapping tested in isolation
  (`GA_AGENT_BACKENDS`/`GA_CREW_ACP_BACKEND` → `GA_CREW_AGENT`) — maps correctly.
- **Compose template rendering:** tested the `GA_ORDERS_DIR` / TLS `$(if …)`
  command-substitution blocks under both set and unset conditions. The heredoc
  delimiter is unquoted (`COMPOSE_EOF`), so substitution executes; output matches
  every spec scenario (`/mnt/orders`, `/mnt/tls`, rewritten container paths).
- **Task 7.3 grep check:** no `os.environ` reads of the 9 hardcoded vars remain in
  `from_env()`; no `cfg.*` access of removed fields outside the two compatibility
  properties; the only `GA_CREW_ACP_BACKEND` env read is the intentional deprecation
  fallback in `_read_ga_crew_agent()`.

## What was implemented correctly

- **D1 — Hardcode 9 vars:** `transport_data_dir`, `ga_enable_security_headers`,
  `ga_tls_min_version`, `ga_prewarm_enabled`, `ga_prewarm_ttl_secs`,
  `ga_subagent_max_turns` removed from `Config`/`from_env()`; replaced with module
  constants/literals. `GA_COMPOSE_RETRY_ATTEMPTS/DELAY_SECS` → `_COMPOSE_*`
  constants in install.sh. Compose template no longer carries the removed env keys.
- **D1 agent-name decoupling (the risky part):** the old `GA_CREW_AGENT` (KiroCrew
  internal agent name written to `config.local.json`) is correctly hardcoded to
  `_KC_AGENT_NAME = "kiro"` in both `lifecycle.py` and `server.py`, cleanly separated
  from the new backend meaning. `_patch_crew_config` still writes `"kiro"` regardless
  of backend — correct per design D1/D2.
- **D2 — GA_CREW_AGENT consolidation:** single `ga_crew_agent` field; `from_env()`
  reads `GA_CREW_AGENT`, falls back to `GA_CREW_ACP_BACKEND` with a deprecation log;
  `_parse_ga_crew_agent` validates and always includes kiro; back-compat
  `ga_crew_acp_backend` / `ga_agent_backends` **properties** keep all old call sites
  working. install.sh maps both deprecated aliases with printed warnings.
- **D3/D4 — volume mounts:** pre-compose validation for `GA_ORDERS_DIR` (absolute-path
  error, missing-dir warning) and TLS (both-or-neither error, same-parent-dir error);
  conditional `/mnt/orders:ro` and `/mnt/tls:ro` mounts; env vars rewritten to
  container paths. Matches every spec scenario.
- **D5 — TTL comment:** `lifecycle.py` comment corrected to state only the warm-marker
  TTL is floored; `_TASK_TIMESTAMP_TTL_SECS` has no floor. No behaviour change (D5 is
  comment-only). Spec's `_TASK_TIMESTAMP_TTL_SECS` requirement satisfied.
- **PORT decoupling** (installation spec): compose hardcodes transport `PORT: 64057`;
  docs clarify Caddy host port vs fixed internal port.
- **Prewarm gate removal:** `GA_PREWARM_ENABLED` gate removed from `_prewarm_crew` and
  `_finish_crew_setup`; `GA_PREWARM_ENABLED = True` retained as a patchable module name
  for test isolation. Correct and intentional per design risk note.

## Findings

### Finding 1 (MAJOR → FIXED by me): `GA_RATE_LIMIT_DASHBOARD_AUTH` missing from conf.example

The config-file spec (both this change's MODIFIED delta **and** the synced baseline
`openspec/specs/config-file/spec.md:125`) states: *"`config/ghostship.conf.example`
SHALL include a `GA_RATE_LIMIT_DASHBOARD_AUTH` entry (default `600:60`)"* with a
passing scenario. The entry was **absent** (never present in git history), so the
synced baseline spec asserted something false about the shipped file. Code default is
`("GA_RATE_LIMIT_DASHBOARD_AUTH", 600, 60)` in `transport/auth.py:74`.

**Fix applied:** added the commented `# GA_RATE_LIMIT_DASHBOARD_AUTH=600:60` entry with
a `/dashboard/auth` forward_auth description to the HTTP rate-limiting section of
`config/ghostship.conf.example`.

### Finding 2 (MINOR → FIXED by me): `TRANSPORT_DATA_DIR` docs row missing

The config-file spec's ADDED requirement *"Configuration docs accurately describe …
TRANSPORT_DATA_DIR behaviour"* requires a `docs/configuration.md` table row explaining
the effective value is `/data` and cannot change without a custom compose override. No
such row existed (the var was hardcoded away but the doc row was never added).

**Fix applied:** added a `TRANSPORT_DATA_DIR` row to the reference table in
`docs/configuration.md` documenting the pinning (hardcoded, `DATA_DIR` always mounted
as `/data`).

### Finding 3 (OBSERVATION — not fixed, by design tension): conf.example pruned to 48, not "~30"

tasks.md §6.1 / design D6 call for pruning `ghostship.conf.example` to ~30 operator
vars by **removing** advanced tuning knobs (`PODMAN_SOCKET`, `KC_IMAGE`, `KC_BASE_IMAGE`,
`GA_MIN_FREE_MEM_GB`, `GA_SUBAGENT_TIMEOUT_SECS`, the memory-pressure vars,
`GA_DASHBOARD_PORT_RANGE_*`) while keeping them in `config.py`. This is **structurally
impossible** given the pre-existing `tests/unit/test_config_sync.py` invariant, which
requires *every* `Config` field to have a commented entry in conf.example. Those vars
are still `Config` fields, so they remain in conf.example (now 48 vars). Only the vars
actually removed from `Config` (the 9 hardcoded) and the renamed/removed backend vars
and the non-`Config` per-endpoint `GA_RATE_LIMIT_*` vars left the file.

The implementer made the **correct** call to keep CI green rather than delete entries
and break the sync test. The design's "~30" target was not reachable without also
changing the sync-test invariant, which the change deliberately did **not** touch
(out of scope; config fields are retained). Documented here as an acknowledged
design/test tension, not a defect in the implementation. No action required for this
change; a follow-up could reconcile the sync-test contract with the pruning goal if the
"~30 vars" outcome is still desired.

### Finding 4 (NIT — not fixed): stale inline comments reference removed env vars

- `transport/lifecycle.py:1826` comment says `GA_CREW_AGENT (default "kiro")` — now a
  hardcoded internal name, no longer env-configurable.
- `scripts/install.sh` compose-retry warning (line ~1119) still prints
  `GA_COMPOSE_RETRY_ATTEMPTS='…'` though the value is now the hardcoded
  `_COMPOSE_RETRY_ATTEMPTS` (unreachable branch — the constant is always `3`).
- `docs/configuration.md` `GA_CREW_AGENT` row lists `kiro/claude/codex` but the proposal
  also mentions `opencode`; code `_ACP_BACKEND_VALUES` is `{kiro,claude,codex}`, so the
  docs match the code (proposal's `opencode` mention is aspirational/build-only). No
  code change needed; left as-is since docs track code.

These are cosmetic and non-behavioural; left for a cleanup pass to avoid churn on an
archived change.

## Fixes committed in this review

- `config/ghostship.conf.example`: add `GA_RATE_LIMIT_DASHBOARD_AUTH=600:60` entry.
- `docs/configuration.md`: add `TRANSPORT_DATA_DIR` reference-table row.

Both verified: `test_config_sync.py` passes; full unit suite re-run → 1324 passed.

## Verdict

**APPROVED WITH FIXES — no unresolved blocking findings.**

The core implementation (hardcoding, GA_CREW_AGENT consolidation, volume-mount fixes,
comment fix, PORT decoupling) is correct, well-tested, and faithful to the design.
Two spec-compliance gaps (Findings 1 & 2) were found and **fixed in this review**;
both were spec requirements the implementation left unsatisfied. Finding 3 is an
acknowledged design-vs-test-invariant tension that the implementer handled correctly.
Finding 4 lists cosmetic nits only.

**Unresolved findings: NONE** (both actionable findings fixed; remaining items are
non-blocking observations/nits).
