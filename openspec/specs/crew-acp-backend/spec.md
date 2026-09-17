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

When `GA_CREW_ACP_BACKEND=claude`, the transport SHALL require `GA_CREW_ANTHROPIC_API_KEY` to be set. If it is absent, `launch` SHALL return an error rather than creating a crew without a usable API key.

#### Scenario: API key missing with Claude backend
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is unset
- **THEN** any `launch` call returns an error indicating the Anthropic API key is required for the Claude backend; no crew container is created

#### Scenario: API key present with Claude backend
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is set
- **THEN** `launch` proceeds normally; the key is injected into the crew container

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
