# crew-acp-backend Specification

## Purpose

Defines how the ACP agent backend (kiro-cli vs Claude Code) is selected per crew at launch time, including configuration resolution, secret injection, and capability enforcement, so operators can run ghostship crews on different agent runtimes without code changes to the transport.

## Requirements

### Requirement: GA_CREW_ACP_BACKEND selects the agent runtime

The transport SHALL read `GA_CREW_ACP_BACKEND` at startup (valid values: `"kiro"`, `"claude"`; default: `"kiro"`). When `"claude"` is set, every new crew launched SHALL have `acp_backend: "claude"` written into its crew config during `_patch_crew_config`. When `"kiro"` is set or unset, existing behaviour is unchanged.

#### Scenario: Default backend is kiro
- **WHEN** `GA_CREW_ACP_BACKEND` is unset or set to `"kiro"` and a crew is launched
- **THEN** `acp_backend` is not written to the crew config (KiroCrew defaults to kiro-cli)

#### Scenario: Claude backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and a crew is launched
- **THEN** `_patch_crew_config` writes `acp_backend: "claude"` into the crew's config before the gateway starts

#### Scenario: Invalid backend value is rejected at startup
- **WHEN** `GA_CREW_ACP_BACKEND` is set to an unrecognised value (e.g. `"opencode"`)
- **THEN** the transport logs an error at startup and exits rather than launching with an unknown backend

### Requirement: Claude backend requires ANTHROPIC_API_KEY

**Superseded by TRN-170.** The previous requirement stated that `GA_CREW_ANTHROPIC_API_KEY` MUST be set when `GA_CREW_ACP_BACKEND=claude`, and that `launch` would return an error if absent. This is replaced by the following:

When `GA_CREW_ACP_BACKEND=claude`, the transport SHALL accept either `GA_CREW_ANTHROPIC_API_KEY` (API key path) or a valid `ga-claude-auth` credential file (OAuth path) as the Claude authentication source. At least one MUST be present by the time `launch` is called. The transport SHALL NOT enforce this constraint at startup — it is enforced lazily at `launch` time, allowing the operator to authenticate via `POST /login/claude` before launching any crews.

#### Scenario: API key missing with Claude backend
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is unset and `ga-claude-auth` does not exist or is empty
- **THEN** any `launch` call returns `not_authenticated` with a `login_url` for the Claude device-code flow; no crew container is created

#### Scenario: API key present with Claude backend
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is set
- **THEN** `launch` proceeds normally; the key is injected as `ANTHROPIC_API_KEY` into the crew container

#### Scenario: OAuth credential present, no API key — launch proceeds
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `GA_CREW_ANTHROPIC_API_KEY` is unset, and `ga-claude-auth` exists and is non-empty
- **THEN** `launch` proceeds normally; the OAuth credential is injected into the crew container's `~/.claude/`

#### Scenario: Neither credential present — launch returns not_authenticated
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `GA_CREW_ANTHROPIC_API_KEY` is unset, and `ga-claude-auth` does not exist or is empty
- **THEN** `launch` returns `not_authenticated` with a `login_url` for the Claude device-code flow; no crew container is created

#### Scenario: Missing API key no longer fails at transport startup
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is unset and the transport starts
- **THEN** the transport starts successfully (no `ConfigError` at startup); the validation is deferred to `launch` time

### Requirement: Backend selection is recorded in the crew registry

The crew's registry entry in `crews.json` SHALL include an `acp_backend` field set to the value used at launch time.

#### Scenario: acp_backend stored in crews.json
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude`
- **THEN** the crew's entry in `crews.json` includes `"acp_backend": "claude"`

#### Scenario: kiro backend crews omit or default the field
- **WHEN** a crew is launched with the default kiro backend
- **THEN** the crew's entry in `crews.json` either omits `acp_backend` or records `"kiro"`; existing pre-TRN-167 entries without the field are treated as kiro

### Requirement: crews() response includes acp_backend

The `crews()` MCP tool response SHALL include the `acp_backend` value for each crew entry, so the Admiral can see at a glance which backend each crew is using.

#### Scenario: Claude crew visible in crews()
- **WHEN** `crews()` is called and a Claude-backend crew is registered
- **THEN** the crew entry includes `"acp_backend": "claude"`

#### Scenario: Pre-existing crews without acp_backend field
- **WHEN** `crews()` is called and a crew entry predates TRN-167
- **THEN** the crew entry omits `acp_backend` or reports `"kiro"` as the default

### Requirement: Claude backend warning at launch emits external network advisory

When a crew is launched with `GA_CREW_ACP_BACKEND=claude`, the transport SHALL emit a WARNING-level log entry stating that crew containers will make outbound HTTPS connections to `api.anthropic.com`, and that this will fail behind firewalls that block external HTTPS egress.

#### Scenario: Network advisory emitted for Claude backend
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude`
- **THEN** a WARNING-level log entry is emitted before the crew container is created, naming `api.anthropic.com` as a required outbound destination
