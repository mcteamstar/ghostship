# TRN-218 — KAS ACP backend

Plane ticket: **TRN-218**
Context: KiroCrew 0.9.0 upgrade (`0.9.0-insider.4`)

## Priority verdict

**Hard break — but only on explicit opt-in.** Ghostship validates
`GA_CREW_ACP_BACKEND` against `_ACP_BACKEND_VALUES = {"kiro", "claude", "codex"}`
in `transport/config.py`. KAS is not in that set, so setting
`GA_CREW_ACP_BACKEND=kas` (or `GA_AGENT_BACKENDS=kas`) raises `ConfigError` and
the crew crashes at startup. The current default (`kiro`) is unaffected, so this
is **not a regression for existing installs** — it is a feature gap. KAS exists
in the 0.9.0 gateway but ghostship has no path to select it.

Urgency is therefore **low for the 0.9.0 bump itself** (KAS is still a
preview/insider feature upstream and not yet the default), and becomes
**required when KAS reaches GA** or when an operator wants to run crews on it.

## Why

KiroCrew 0.9.0 adds KAS (Kiro Agent Service) as a selectable ACP backend
(PRs #3340 → #3435 → #3621/#3666/#3744/#3823/#3917). It is the most significant
architectural addition in the 0.9.0 cycle. To let ghostship spec-ops crews run
on KAS alongside kiro-cli, Claude, and Codex, the transport's backend
validation and config-write path must learn the `kas` name.

Unlike Claude and Codex (TRN-202) and OpenCode (TRN-168), **KAS is bundled in
the gateway image** — it needs no toolchain install script and no stored
credential file. In that respect it is structurally like `kiro`
(`_ALWAYS_ENABLED_BACKEND`): the only work is validation plus a config-write
branch so the gateway routes agent spawns through the KAS ACP runtime.

## What changes

- `transport/config.py`: add `"kas"` to `_ACP_BACKEND_VALUES`. This single
  change makes `GA_CREW_ACP_BACKEND=kas` and `GA_AGENT_BACKENDS=kas` pass both
  `_validate_acp_backend()` and `parse_agent_backends()`.
- `transport/lifecycle.py`: add an `elif GA_CREW_ACP_BACKEND == "kas":` branch
  in `_patch_crew_config` that writes `agent_overrides["acp_backend"] = "kas"`,
  so the gateway routes spawns through the KAS runtime instead of falling
  through to the default (`kiro`).
- `scripts/lib/agent_backends.sh`: recognise `kas` on the install side (parity
  with `parse_agent_backends()`), gated by the agent-backends parity test.
- Tests: extend `tests/unit/test_agent_backends.py` (and the parity test) with
  KAS validation coverage.
- `docs/configuration.md`: document `kas` as a valid `GA_AGENT_BACKENDS` /
  `GA_CREW_ACP_BACKEND` value, noting Preview/insider status and that it is
  bundled (no toolchain, no login flow).

## Capabilities

### New capabilities

- `kas-backend`: KAS as a selectable ghostship agent backend — validation and
  the `acp_backend=kas` config-write branch. No toolchain, no credential file
  (bundled in the gateway image).

### Modified capabilities

- `agent-backends`: extend the valid `GA_AGENT_BACKENDS` name set to include
  `kas`; keep transport (`config.py`) and shell (`agent_backends.sh`)
  validation in step.

## Affected ghostship files / functions

| File | Symbol | Line(s) | Change |
|---|---|---|---|
| `transport/config.py` | `_ACP_BACKEND_VALUES` | 74 | add `"kas"` to the frozenset |
| `transport/config.py` | `_validate_acp_backend()` | 77–87 | error message string lists `kas` |
| `transport/config.py` | `parse_agent_backends()` | 90–119 | no code change — reads `_ACP_BACKEND_VALUES` |
| `transport/lifecycle.py` | `_patch_crew_config` | ~1835–1843 | add `elif GA_CREW_ACP_BACKEND == "kas":` branch |
| `scripts/lib/agent_backends.sh` | backend validation | — | add `kas` to the valid set |
| `academy/agents/*.json` | `"model": "gpt-5.6-luna"` | — | review model routing under KAS (see design.md) |

## Impact

- `transport/config.py`, `transport/lifecycle.py` — validation + config write.
- `scripts/lib/agent_backends.sh` — install-side parity.
- `tests/unit/test_agent_backends.py`, `tests/unit/test_agent_backends_parity.py`
  — KAS coverage.
- `docs/configuration.md` — documentation.
- No toolchain script, no login/logout routes, no credential mount — KAS is
  bundled in the gateway image.
