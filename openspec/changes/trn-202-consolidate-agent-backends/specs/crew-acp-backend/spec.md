# Spec Delta

## MODIFIED Requirements

### Requirement: GA_CREW_ACP_BACKEND selects the agent runtime

The transport SHALL read `GA_CREW_ACP_BACKEND` at startup and use it as the default backend for new crews. Valid values are `"kiro"`, `"claude"` and `"codex"`; the value SHALL also be an enabled backend, as defined by the `agent-backends` capability. When unset, the default is `"kiro"`. When `"claude"` is the default, every new crew launched SHALL have `acp_backend: "claude"` written into its crew config during `_patch_crew_config`. When `"codex"` is the default, every new crew launched SHALL have `acp_backend: "codex"` written into its crew config during `_patch_crew_config`. When `"kiro"` is the default, existing behaviour is unchanged.

#### Scenario: Default backend is kiro
- **WHEN** `GA_CREW_ACP_BACKEND` is unset or set to `"kiro"` and a crew is launched
- **THEN** `acp_backend` is not written to the crew config (KiroCrew defaults to kiro-cli)

#### Scenario: Claude backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, claude is enabled, and a crew is launched
- **THEN** `_patch_crew_config` writes `acp_backend: "claude"` into the crew's config before the gateway starts

#### Scenario: Codex backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, codex is enabled, and a crew is launched
- **THEN** `_patch_crew_config` writes `acp_backend: "codex"` into the crew's config before the gateway starts

#### Scenario: Invalid backend value is rejected at startup
- **WHEN** `GA_CREW_ACP_BACKEND` is set to an unrecognised value (e.g. `"opencode"`)
- **THEN** the transport logs an error at startup and exits rather than launching with an unknown backend

### Requirement: Codex backend requires the Codex-enabled image

The Codex adapter (`codex-acp`) is present in the spec-ops image only when `codex` is an enabled backend, so that `install.sh` passes it in `AGENT_TOOLCHAINS`. The transport SHALL NOT start with codex as the default backend unless codex is enabled, so a Codex-backend crew is never started from an image without the adapter.

#### Scenario: Codex backend on an image without the adapter
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and codex is not an enabled backend
- **THEN** the transport raises a `ConfigError` at startup naming `GA_CREW_ACP_BACKEND`, `GA_AGENT_BACKENDS` and the `ghostship install` re-run as the remedy; no crew is started
