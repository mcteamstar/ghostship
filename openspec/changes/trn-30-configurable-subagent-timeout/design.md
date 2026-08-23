## Context

`_patch_crew_config` in `transport/server.py` already writes 6 overrides to
`config.local.json` at crew launch. KiroCrew reads this file on startup and
applies its values over defaults. Adding `subagent_timeout_secs` and
`subagent_max_turns` here is a 2-line change to the existing dict.

The current default of 1800s (30 min) causes agents to time out mid-task on
long-running implementation work. 3600s (60 min) is the proposed new default —
generous enough for typical Ghost tasks while still bounding runaway sessions.

## Goals / Non-Goals

**Goals:**
- Expose `GA_SUBAGENT_TIMEOUT_SECS` and `GA_SUBAGENT_MAX_TURNS` as operator env vars
- Apply both to every new crew via `_patch_crew_config`
- Document in `docs/configuration.md`

**Non-Goals:**
- Per-crew or per-composition timeout (operator-level only for now)
- Changing the KiroCrew default upstream
- Any memory governor interaction (KiroCrew 0.3.0 handles that natively)

## Decisions

### 1. Defaults: 3600s and 200 turns

**Choice:** `GA_SUBAGENT_TIMEOUT_SECS=3600`, `GA_SUBAGENT_MAX_TURNS=200`.

**Rationale:** 3600s observed sufficient for all Wave 1/2 Ghost tasks. 200 turns
(up from 100) gives headroom for complex multi-file changes. Both can be lowered
by operators with faster hardware or tighter budgets.

### 2. Operator-level only (not per-crew)

**Choice:** Single env var applies to all crews on this transport instance.

**Rationale:** Per-crew config would require new `launch()` parameters and API
surface. The main pain point is a global floor being too low — operator-level
override fixes that without added complexity.

### 3. No install.sh flag

**Choice:** Document as config-file variables only (no `--subagent-timeout` flag
in `install.sh`).

**Rationale:** These are tuning knobs, not first-class install options. The
config file approach (setting vars in `ghostship.conf`) is consistent with
`GA_MAX_CREWS`, `GA_IDLE_TIMEOUT_SECS`, etc.

## Migration Plan

No migration needed. The new fields are additive — existing crews are unaffected
until relaunched. New crews pick up the defaults (3600s / 200 turns) on next
`launch()` call.
