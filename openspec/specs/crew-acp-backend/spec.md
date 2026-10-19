# crew-acp-backend Specification

## Purpose

Defines how the ACP agent backend (kiro-cli vs Claude Code) is selected per crew at launch time, including configuration resolution, secret injection, and capability enforcement, so operators can run ghostship crews on different agent runtimes without code changes to the transport.

## Requirements

### Requirement: GA_CREW_ACP_BACKEND selects the agent runtime

The transport SHALL read `GA_CREW_ACP_BACKEND` at startup and use it as the default backend for new crews launched without a `backend` argument. Valid values are `"kiro"`, `"claude"` and `"codex"`; the value SHALL also be an enabled backend, as defined by the `agent-backends` capability. When unset, the default is `"kiro"`. When a crew's backend is `"claude"`, the crew SHALL have `acp_backend: "claude"` written into its crew config during `_patch_crew_config`. When a crew's backend is `"codex"`, the crew SHALL have `acp_backend: "codex"` written into its crew config during `_patch_crew_config`. When a crew's backend is `"kiro"`, existing behaviour is unchanged. The per-backend model override and default applied to a crew SHALL be those of the crew's backend.

#### Scenario: Default backend is kiro
- **WHEN** `GA_CREW_ACP_BACKEND` is unset or set to `"kiro"` and a crew is launched without a `backend` argument
- **THEN** `acp_backend` is not written to the crew config (KiroCrew defaults to kiro-cli)

#### Scenario: Claude backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, claude is enabled, and a crew is launched without a `backend` argument
- **THEN** `_patch_crew_config` writes `acp_backend: "claude"` into the crew's config before the gateway starts

#### Scenario: Codex backend selected
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, codex is enabled, and a crew is launched without a `backend` argument
- **THEN** `_patch_crew_config` writes `acp_backend: "codex"` into the crew's config before the gateway starts

#### Scenario: Per-backend model settings follow the crew
- **WHEN** `backends.kiro.model.override` and `backends.claude.model.override` are set to different models, the default is `claude`, and a crew is launched with `backend="kiro"`
- **THEN** the crew's agents are patched to the kiro override, not the claude one

#### Scenario: Invalid backend value is rejected at startup
- **WHEN** `GA_CREW_ACP_BACKEND` is set to an unrecognised value (e.g. `"opencode"`)
- **THEN** the transport logs an error at startup and exits rather than launching with an unknown backend

### Requirement: Backend selection is recorded in the crew registry

The crew's registry entry in `crews.json` SHALL include an `acp_backend` field set to the crew's backend at launch time (`"kiro"`, `"claude"`, or `"codex"`): the `backend` argument when given, otherwise the transport default. The recorded value is the crew's backend for the rest of its life.

#### Scenario: acp_backend stored in crews.json
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` and no `backend` argument
- **THEN** the crew's entry in `crews.json` includes `"acp_backend": "claude"`

#### Scenario: codex acp_backend stored in crews.json
- **WHEN** a crew is launched with `backend="codex"`
- **THEN** the crew's entry in `crews.json` includes `"acp_backend": "codex"`

#### Scenario: kiro backend crews omit or default the field
- **WHEN** a crew is launched on the kiro backend
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

### Requirement: Claude backend external network requirement

When `GA_CREW_ACP_BACKEND=claude`, crew containers require outbound HTTPS access to the Anthropic API endpoint. By default this is `api.anthropic.com`. When `ANTHROPIC_BASE_URL` is set, the transport SHALL inject it as `ANTHROPIC_BASE_URL` into Claude-backend crew containers, allowing traffic to be directed to an Anthropic-compatible endpoint (e.g. a local model router or proxy).

The WARNING log entry emitted at `launch` time when `GA_CREW_ACP_BACKEND=claude` SHALL name the effective endpoint: `api.anthropic.com` when `ANTHROPIC_BASE_URL` is unset, or the configured URL when it is set.

`ANTHROPIC_BASE_URL` has no effect when `GA_CREW_ACP_BACKEND != "claude"`.

#### Scenario: Base URL unset — default Anthropic endpoint used
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `ANTHROPIC_BASE_URL` is unset
- **THEN** the crew container is created without an `ANTHROPIC_BASE_URL` env var; Claude Code uses its default endpoint (`api.anthropic.com`)
- **THEN** the WARNING log at launch names `api.anthropic.com` as the required outbound destination

#### Scenario: Base URL set — custom endpoint injected
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `ANTHROPIC_BASE_URL` is set (e.g. `http://supply.penguin-piano.ts.net:11434`)
- **THEN** `ANTHROPIC_BASE_URL` is set to that value in the crew container's environment at creation time
- **THEN** Claude Code routes API calls to the configured endpoint instead of `api.anthropic.com`
- **THEN** the WARNING log at launch reflects the overridden endpoint

#### Scenario: Base URL has no effect on kiro-backend crews
- **WHEN** `GA_CREW_ACP_BACKEND=kiro` (or unset) and `ANTHROPIC_BASE_URL` is set
- **THEN** `ANTHROPIC_BASE_URL` is NOT injected into the crew container; kiro-cli auth paths are unchanged

### Requirement: Codex backend external network requirement

When `GA_CREW_ACP_BACKEND=codex`, crew containers require outbound HTTPS access to the OpenAI API endpoint. By default this is `api.openai.com`. When `OPENAI_BASE_URL` is set, the transport SHALL inject it as `OPENAI_BASE_URL` into Codex-backend crew containers, allowing traffic to be directed to an OpenAI-compatible endpoint (e.g. a local model router or proxy).

The WARNING log entry emitted at `launch` time when `GA_CREW_ACP_BACKEND=codex` SHALL name the effective endpoint: `api.openai.com` when `OPENAI_BASE_URL` is unset, or the configured URL when it is set.

`OPENAI_BASE_URL` has no effect when `GA_CREW_ACP_BACKEND != "codex"`.

#### Scenario: Base URL unset — default OpenAI endpoint used
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `OPENAI_BASE_URL` is unset
- **THEN** the crew container is created without an `OPENAI_BASE_URL` env var; Codex uses its default endpoint (`api.openai.com`)
- **THEN** the WARNING log at launch names `api.openai.com` as the required outbound destination

#### Scenario: Base URL set — custom endpoint injected
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `OPENAI_BASE_URL` is set (e.g. `http://supply.penguin-piano.ts.net:11434/v1`)
- **THEN** `OPENAI_BASE_URL` is set to that value in the crew container's environment at creation time
- **THEN** Codex routes API calls to the configured endpoint instead of `api.openai.com`
- **THEN** the WARNING log at launch reflects the overridden endpoint

#### Scenario: Base URL has no effect on non-codex crews
- **WHEN** `GA_CREW_ACP_BACKEND != "codex"` and `OPENAI_BASE_URL` is set
- **THEN** `OPENAI_BASE_URL` is NOT injected into the crew container; other backends' auth paths are unchanged

### Requirement: Codex backend requires the Codex-enabled image

The Codex adapter (`codex-acp`) is present in the spec-ops image only when `codex` is an enabled backend, so that `install.sh` passes it in `AGENT_TOOLCHAINS`. The transport SHALL NOT start with codex as the default backend unless codex is enabled, so a Codex-backend crew is never started from an image without the adapter.

#### Scenario: Codex backend on an image without the adapter
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and codex is not an enabled backend
- **THEN** the transport raises a `ConfigError` at startup naming `GA_CREW_ACP_BACKEND`, `GA_AGENT_BACKENDS` and the `ghostship install` re-run as the remedy; no crew is started

### Requirement: Claude backend requires a stored credential

A Claude-backend crew SHALL require claude to hold an active credential in the credential store, of any method (`oauth`, `api-key` or `setup-token`), by the time `launch` is called. Without one, launch SHALL start the Claude authorisation-code flow (backend-credentials). The transport SHALL NOT enforce this at startup. This applies whether claude is the crew's backend by default or by the `backend` argument.

#### Scenario: No Claude credential
- **WHEN** a claude crew is launched and claude holds no credential
- **THEN** `launch` starts the Claude authorisation-code flow, returns `not_authenticated` with its `login_url`, and creates no crew container

#### Scenario: Any Claude method satisfies launch
- **WHEN** a claude crew is launched and claude's active method is `api-key`, `setup-token` or `oauth`
- **THEN** `launch` proceeds and the crew receives that credential only

#### Scenario: Missing credential does not fail at transport startup
- **WHEN** claude is enabled, holds no credential, and the transport starts
- **THEN** the transport starts successfully; the check is deferred to `launch` time

### Requirement: Codex backend requires a stored credential

A Codex-backend crew SHALL require codex to hold an active credential (`api-key` or `chatgpt`) in the credential store by the time `launch` is called. Without one, launch SHALL start the Codex ChatGPT device-code flow (backend-credentials). The transport SHALL NOT enforce this at startup. This applies whether codex is the crew's backend by default or by the `backend` argument.

#### Scenario: API key stored
- **WHEN** a codex crew is launched and codex holds an `api-key` credential
- **THEN** `launch` proceeds and the key is injected as `OPENAI_API_KEY` into the crew container

#### Scenario: ChatGPT credential stored
- **WHEN** a codex crew is launched and codex holds a `chatgpt` credential
- **THEN** `launch` proceeds and the stored `auth.json` is installed in the crew's `~/.codex/`

#### Scenario: No Codex credential
- **WHEN** a codex crew is launched and codex holds no credential
- **THEN** `launch` starts the ChatGPT device-code flow, returns `not_authenticated` with its `login_url` and `code`, and creates no crew container

#### Scenario: Missing credential does not fail at transport startup
- **WHEN** codex is enabled, holds no credential, and the transport starts
- **THEN** the transport starts successfully; the check is deferred to `launch` time

### Requirement: launch accepts a per-crew backend

`launch` SHALL accept an optional `backend` argument naming the agent runtime for the new crew, using the same backend names as configuration (today `"kiro"`, `"claude"` or `"codex"`). When it is omitted or null, the crew SHALL use the transport default backend. The value is case-insensitive.

#### Scenario: Backend omitted uses the default
- **WHEN** the default backend is `claude` and `launch(crew_id="a")` is called with no `backend`
- **THEN** the crew launches on claude, exactly as before this change

#### Scenario: Explicit backend overrides the default
- **WHEN** the default backend is `claude`, kiro holds a credential, and `launch(crew_id="a", backend="kiro")` is called
- **THEN** the crew launches on kiro and its registry entry records `"acp_backend": "kiro"`

#### Scenario: Backends coexist
- **WHEN** one crew is launched with `backend="kiro"` and another with `backend="claude"` on the same transport
- **THEN** both crews run concurrently, each on its own backend, and `crews()` reports each crew's `acp_backend`

### Requirement: Requested backend must be enabled

The backend requested from `launch` SHALL be an enabled backend, as defined by the `agent-backends` capability. Otherwise `launch` SHALL return an error that names the requested backend and lists the enabled backends, and SHALL create no container, volume or registry entry.

#### Scenario: Disabled backend requested
- **WHEN** only kiro and claude are enabled and `launch(crew_id="a", backend="codex")` is called
- **THEN** `launch` returns an error naming `codex` and listing `kiro, claude`, and no crew is created

#### Scenario: Unknown backend requested
- **WHEN** `launch(crew_id="a", backend="gemini")` is called
- **THEN** `launch` returns an error listing the enabled backends, and no crew is created

#### Scenario: Kiro is always launchable
- **WHEN** the backend list in configuration is `claude` only and `launch(crew_id="a", backend="kiro")` is called with a stored kiro credential
- **THEN** the crew launches on kiro

### Requirement: Launch authentication follows the crew's backend

Credential lookup, the not-authenticated login flow, and credential delivery to the new crew SHALL use the crew's backend, not the transport default. A crew SHALL receive only its own backend's credential.

#### Scenario: Missing credential for the requested backend
- **WHEN** the default backend is `claude` (with a claude credential stored), kiro holds no credential, and `launch(crew_id="a", backend="kiro")` is called
- **THEN** `launch` starts the kiro device flow and returns `not_authenticated` with its `login_url`, and creates no crew container

#### Scenario: Only the crew's credential is delivered
- **WHEN** both kiro and claude hold credentials and a crew is launched with `backend="kiro"`
- **THEN** the crew receives kiro's credential and none of claude's credential environment variables

### Requirement: Restarts preserve the crew's backend

Whenever the transport restarts a crew and re-applies its crew config (reconcile or recovery restart), it SHALL use the backend recorded in the crew's registry entry, treating a missing value as `kiro`. A change to the transport default SHALL NOT change the runtime of an existing crew.

#### Scenario: Default changes between launch and restart
- **WHEN** a crew was launched on kiro, the transport default is later changed to `claude`, and the crew is restarted by reconcile
- **THEN** the crew's config keeps the kiro runtime and its registry entry still records `"acp_backend": "kiro"`

#### Scenario: Claude crew restarted under a kiro default
- **WHEN** a crew was launched with `backend="claude"` while the default is `kiro`, and the crew is restarted
- **THEN** the crew's config still selects the claude runtime
