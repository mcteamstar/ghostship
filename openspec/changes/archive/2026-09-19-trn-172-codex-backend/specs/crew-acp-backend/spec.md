## MODIFIED Requirements

### Requirement: GA_CREW_ACP_BACKEND selects the agent runtime

The transport SHALL read `GA_CREW_ACP_BACKEND` at startup (valid values: `"kiro"`, `"claude"`, `"codex"`; default: `"kiro"`). When `"claude"` is set, every new crew launched SHALL have `acp_backend: "claude"` written into its crew config during `_patch_crew_config`. When `"codex"` is set, every new crew launched SHALL have `acp_backend: "codex"` written into its crew config during `_patch_crew_config`. When `"kiro"` is set or unset, existing behaviour is unchanged.

#### Scenario: Default backend is kiro
- **WHEN** `GA_CREW_ACP_BACKEND` is unset or set to `"kiro"` and a crew is launched
- **THEN** `acp_backend` is not written to the crew config (KiroCrew defaults to kiro-cli)

#### Scenario: Claude backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and a crew is launched
- **THEN** `_patch_crew_config` writes `acp_backend: "claude"` into the crew's config before the gateway starts

#### Scenario: Codex backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and a crew is launched
- **THEN** `_patch_crew_config` writes `acp_backend: "codex"` into the crew's config before the gateway starts

#### Scenario: Invalid backend value is rejected at startup
- **WHEN** `GA_CREW_ACP_BACKEND` is set to an unrecognised value (e.g. `"opencode"`)
- **THEN** the transport logs an error at startup and exits rather than launching with an unknown backend

## ADDED Requirements

### Requirement: Codex backend requires an OpenAI credential

When `GA_CREW_ACP_BACKEND=codex`, the transport SHALL accept either `GA_CREW_OPENAI_API_KEY` (API-key path) or a valid `ga-codex-auth` credential archive (OAuth path) as the Codex authentication source. At least one MUST be present by the time `launch` is called. The transport SHALL NOT enforce this constraint at startup — it is enforced lazily at `launch` time, allowing the operator to authenticate via `POST /login/codex` before launching any crews.

#### Scenario: API key present with Codex backend
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `GA_CREW_OPENAI_API_KEY` is set
- **THEN** `launch` proceeds normally; the key is injected as `OPENAI_API_KEY` into the crew container

#### Scenario: OAuth credential present, no API key — launch proceeds
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, `GA_CREW_OPENAI_API_KEY` is unset, and `ga-codex-auth` exists and is non-empty
- **THEN** `launch` proceeds normally; the OAuth credential is injected into the crew container's `~/.codex/`

#### Scenario: Neither credential present — launch returns not_authenticated
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, `GA_CREW_OPENAI_API_KEY` is unset, and `ga-codex-auth` does not exist or is empty
- **THEN** `launch` returns `not_authenticated` with a `login_url` for the Codex login flow; no crew container is created

#### Scenario: Missing credential does not fail at transport startup
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, `GA_CREW_OPENAI_API_KEY` is unset, and the transport starts
- **THEN** the transport starts successfully (no `ConfigError` at startup); the validation is deferred to `launch` time

### Requirement: Codex backend external network requirement

When `GA_CREW_ACP_BACKEND=codex`, crew containers require outbound HTTPS access to the OpenAI API endpoint. By default this is `api.openai.com`. When `GA_CREW_OPENAI_BASE_URL` is set, the transport SHALL inject it as `OPENAI_BASE_URL` into Codex-backend crew containers, allowing traffic to be directed to an OpenAI-compatible endpoint (e.g. a local model router or proxy).

The WARNING log entry emitted at `launch` time when `GA_CREW_ACP_BACKEND=codex` SHALL name the effective endpoint: `api.openai.com` when `GA_CREW_OPENAI_BASE_URL` is unset, or the configured URL when it is set.

`GA_CREW_OPENAI_BASE_URL` has no effect when `GA_CREW_ACP_BACKEND != "codex"`.

#### Scenario: Base URL unset — default OpenAI endpoint used
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `GA_CREW_OPENAI_BASE_URL` is unset
- **THEN** the crew container is created without an `OPENAI_BASE_URL` env var; Codex uses its default endpoint (`api.openai.com`)
- **THEN** the WARNING log at launch names `api.openai.com` as the required outbound destination

#### Scenario: Base URL set — custom endpoint injected
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `GA_CREW_OPENAI_BASE_URL` is set (e.g. `http://supply.penguin-piano.ts.net:11434/v1`)
- **THEN** `OPENAI_BASE_URL` is set to that value in the crew container's environment at creation time
- **THEN** Codex routes API calls to the configured endpoint instead of `api.openai.com`
- **THEN** the WARNING log at launch reflects the overridden endpoint

#### Scenario: Base URL has no effect on non-codex crews
- **WHEN** `GA_CREW_ACP_BACKEND != "codex"` and `GA_CREW_OPENAI_BASE_URL` is set
- **THEN** `OPENAI_BASE_URL` is NOT injected into the crew container; other backends' auth paths are unchanged

### Requirement: Codex backend requires the Codex-enabled image

The Codex adapter (`codex-acp`) is present in the spec-ops image only when it was built with `INCLUDE_CODEX_AGENT=true`, surfaced through `GA_INCLUDE_CODEX_AGENT`. Launching a Codex-backend crew from an image without the adapter SHALL fail with a clear, actionable error rather than starting a crew whose gateway cannot spawn the runtime.

#### Scenario: Codex backend on an image without the adapter
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and the spec-ops image was built without `INCLUDE_CODEX_AGENT=true`
- **THEN** `launch` (or the Codex login flow) returns an error naming `GA_INCLUDE_CODEX_AGENT=true` and image rebuild as the remedy; no crew is left in a broken state

## MODIFIED Requirements

### Requirement: Backend selection is recorded in the crew registry

The crew's registry entry in `crews.json` SHALL include an `acp_backend` field set to the value used at launch time (`"kiro"`, `"claude"`, or `"codex"`).

#### Scenario: acp_backend stored in crews.json
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude`
- **THEN** the crew's entry in `crews.json` includes `"acp_backend": "claude"`

#### Scenario: codex acp_backend stored in crews.json
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=codex`
- **THEN** the crew's entry in `crews.json` includes `"acp_backend": "codex"`

#### Scenario: kiro backend crews omit or default the field
- **WHEN** a crew is launched with the default kiro backend
- **THEN** the crew's entry in `crews.json` either omits `acp_backend` or records `"kiro"`; existing pre-TRN-167 entries without the field are treated as kiro

### Requirement: crews() response includes acp_backend

The `crews()` MCP tool response SHALL include the `acp_backend` value for each crew entry (`"kiro"`, `"claude"`, or `"codex"`), so the Admiral can see at a glance which backend each crew is using.

#### Scenario: Claude crew visible in crews()
- **WHEN** `crews()` is called and a Claude-backend crew is registered
- **THEN** the crew entry includes `"acp_backend": "claude"`

#### Scenario: Codex crew visible in crews()
- **WHEN** `crews()` is called and a Codex-backend crew is registered
- **THEN** the crew entry includes `"acp_backend": "codex"`

#### Scenario: Pre-existing crews without acp_backend field
- **WHEN** `crews()` is called and a crew entry predates TRN-167
- **THEN** the crew entry omits `acp_backend` or reports `"kiro"` as the default
