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

### Requirement: Claude backend external network requirement

When `GA_CREW_ACP_BACKEND=claude`, crew containers require outbound HTTPS access to the Anthropic API endpoint. By default this is `api.anthropic.com`. When `GA_CREW_ANTHROPIC_BASE_URL` is set, the transport SHALL inject it as `ANTHROPIC_BASE_URL` into Claude-backend crew containers, allowing traffic to be directed to an Anthropic-compatible endpoint (e.g. a local model router or proxy).

The WARNING log entry emitted at `launch` time when `GA_CREW_ACP_BACKEND=claude` SHALL name the effective endpoint: `api.anthropic.com` when `GA_CREW_ANTHROPIC_BASE_URL` is unset, or the configured URL when it is set.

`GA_CREW_ANTHROPIC_BASE_URL` has no effect when `GA_CREW_ACP_BACKEND != "claude"`.

#### Scenario: Base URL unset — default Anthropic endpoint used
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_BASE_URL` is unset
- **THEN** the crew container is created without an `ANTHROPIC_BASE_URL` env var; Claude Code uses its default endpoint (`api.anthropic.com`)
- **THEN** the WARNING log at launch names `api.anthropic.com` as the required outbound destination

#### Scenario: Base URL set — custom endpoint injected
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_BASE_URL` is set (e.g. `http://supply.penguin-piano.ts.net:11434`)
- **THEN** `ANTHROPIC_BASE_URL` is set to that value in the crew container's environment at creation time
- **THEN** Claude Code routes API calls to the configured endpoint instead of `api.anthropic.com`
- **THEN** the WARNING log at launch reflects the overridden endpoint

#### Scenario: Base URL has no effect on kiro-backend crews
- **WHEN** `GA_CREW_ACP_BACKEND=kiro` (or unset) and `GA_CREW_ANTHROPIC_BASE_URL` is set
- **THEN** `ANTHROPIC_BASE_URL` is NOT injected into the crew container; kiro-cli auth paths are unchanged
