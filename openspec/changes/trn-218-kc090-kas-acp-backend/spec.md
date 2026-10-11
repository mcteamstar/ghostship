# Delta spec — KAS ACP backend (TRN-218)

## Purpose

Defines how the KAS (Kiro Agent Service) agent backend is validated and
selected in ghostship spec-ops crews. KAS is bundled in the KiroCrew 0.9.0
gateway image, so — unlike Claude, Codex, and OpenCode — it requires no
toolchain install script and no stored credential file. The only ghostship
work is backend-name validation and a `config.local.json` write that routes
agent spawns through the KAS ACP runtime.

## Behaviour change

### Before (0.8.0 baseline)

- `_ACP_BACKEND_VALUES = frozenset({"kiro", "claude", "codex"})`.
- `GA_CREW_ACP_BACKEND=kas` raises `ConfigError` at startup via
  `_validate_acp_backend()`; the crew never launches.
- `GA_AGENT_BACKENDS=kas` raises `ConfigError` via `parse_agent_backends()`
  ("unknown backend 'kas'").
- `_patch_crew_config` writes `acp_backend` only for `claude` and `codex`; any
  other selected value falls through to the gateway default (`kiro`).

### After (this change)

- `_ACP_BACKEND_VALUES = frozenset({"kiro", "claude", "codex", "kas"})`.
- `GA_CREW_ACP_BACKEND=kas` and `GA_AGENT_BACKENDS=kas` validate successfully.
- `_patch_crew_config` writes `acp_backend = "kas"` into `config.local.json`
  when `GA_CREW_ACP_BACKEND == "kas"`, so the gateway routes agent spawns
  through the KAS runtime.
- The default backend remains `kiro`; KAS is opt-in only.

## Configuration after the change

KAS is enabled the same way as the other optional backends:

```
# Enable KAS as an available backend (bundled; no toolchain, no login)
GA_AGENT_BACKENDS=kas

# Select KAS as the crew's ACP backend
GA_CREW_ACP_BACKEND=kas
```

No new config keys are introduced in ghostship's own config surface. The only
derived output is the gateway config key written by `_patch_crew_config`:

| Written key | Path | Value when `GA_CREW_ACP_BACKEND=kas` |
|---|---|---|
| `acp_backend` | `config.local.json` → `agent.acp_backend` | `"kas"` |

KAS, like `kiro` (`_ALWAYS_ENABLED_BACKEND`), has **no** backend-specific
credential or endpoint settings — so there are no new entries in
`_BACKEND_SETTINGS` or `_BACKEND_CREDENTIAL_FILES`, and nothing new in the
inert-setting warnings.

## ADDED Requirements

### Requirement: KAS is a valid backend name

`GA_AGENT_BACKENDS` and `GA_CREW_ACP_BACKEND` SHALL accept `kas` as a valid
backend name, validated against `_ACP_BACKEND_VALUES` by both
`_validate_acp_backend()` and `parse_agent_backends()` in `transport/config.py`.
`scripts/lib/agent_backends.sh` SHALL recognise the same name so install-side
and transport-side validation stay in step.

#### Scenario: KAS accepted as the crew backend
- **WHEN** `GA_CREW_ACP_BACKEND=kas` and `GA_AGENT_BACKENDS=kas`
- **THEN** config parsing succeeds and the crew launches without `ConfigError`

#### Scenario: Unknown backend still rejected
- **WHEN** `GA_CREW_ACP_BACKEND=bogus`
- **THEN** `_validate_acp_backend()` raises `ConfigError` listing `kas` among
  the valid names

#### Scenario: Install-side validation parity
- **WHEN** `scripts/lib/agent_backends.sh` validates `GA_AGENT_BACKENDS=kas`
- **THEN** it accepts the name, matching `parse_agent_backends()`

### Requirement: KAS routes agent spawns through the KAS runtime

When `GA_CREW_ACP_BACKEND=kas`, `_patch_crew_config` SHALL write
`agent.acp_backend = "kas"` into `config.local.json`, so the gateway routes
agent spawns through the KAS ACP runtime rather than falling through to the
default `kiro` runtime.

#### Scenario: acp_backend written for KAS
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=kas`
- **THEN** `config.local.json` contains `agent.acp_backend = "kas"`

#### Scenario: Default unchanged when KAS not selected
- **WHEN** `GA_CREW_ACP_BACKEND` is unset (default `kiro`)
- **THEN** no `acp_backend` key is written and the gateway uses the `kiro`
  runtime

### Requirement: KAS is bundled — no toolchain, no credential

KAS SHALL be treated like `kiro` (`_ALWAYS_ENABLED_BACKEND`) with respect to
provisioning: no toolchain install script under `crews/spec-ops/toolchains/`,
no stored credential file, no `/login/kas` or `/logout/kas` route, and no
crew-launch credential mount. KAS is bundled in the KiroCrew gateway image.

#### Scenario: No credential required to launch on KAS
- **WHEN** `GA_CREW_ACP_BACKEND=kas` and no backend credential file exists
- **THEN** the crew launches successfully (KAS authenticates through the
  gateway's bundled runtime)

### Requirement: KAS is a Preview feature requiring explicit opt-in

The KAS backend SHALL NOT be the default. It is selected only via
`GA_CREW_ACP_BACKEND=kas`. Documentation SHALL note KAS is upstream
preview/insider status in KiroCrew 0.9.0 and may have capability gaps compared
to the kiro-cli backend.

#### Scenario: Default remains kiro when KAS is available but not selected
- **WHEN** `GA_AGENT_BACKENDS=kas` and `GA_CREW_ACP_BACKEND` is unset
- **THEN** new crews default to the `kiro` backend
