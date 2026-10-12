# Spec Delta

## MODIFIED Requirements

### Requirement: Claude backend requires ANTHROPIC_API_KEY

**Superseded by TRN-170.** The previous requirement stated that `ANTHROPIC_API_KEY` MUST be set when `GA_CREW_ACP_BACKEND=claude`, and that `launch` would return an error if absent. This is replaced by the following:

When `GA_CREW_ACP_BACKEND=claude`, the transport SHALL accept either `ANTHROPIC_API_KEY` (API key path) or a valid `ga-claude-auth` credential file (OAuth path) as the Claude authentication source. At least one MUST be present by the time `launch` is called. The transport SHALL NOT enforce this constraint at startup — it is enforced lazily at `launch` time, allowing the operator to authenticate via `POST /login/claude` before launching any crews.

#### Scenario: API key missing with Claude backend
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `ANTHROPIC_API_KEY` is unset and `ga-claude-auth` does not exist or is empty
- **THEN** any `launch` call returns `not_authenticated` with a `login_url` for the Claude device-code flow; no crew container is created

#### Scenario: API key present with Claude backend
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `ANTHROPIC_API_KEY` is set
- **THEN** `launch` proceeds normally; the key is injected as `ANTHROPIC_API_KEY` into the crew container

#### Scenario: OAuth credential present, no API key — launch proceeds
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `ANTHROPIC_API_KEY` is unset, and `ga-claude-auth` exists and is non-empty
- **THEN** `launch` proceeds normally; the OAuth credential is injected into the crew container's `~/.claude/`

#### Scenario: Neither credential present — launch returns not_authenticated
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `ANTHROPIC_API_KEY` is unset, and `ga-claude-auth` does not exist or is empty
- **THEN** `launch` returns `not_authenticated` with a `login_url` for the Claude device-code flow; no crew container is created

#### Scenario: Missing API key no longer fails at transport startup
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `ANTHROPIC_API_KEY` is unset and the transport starts
- **THEN** the transport starts successfully (no `ConfigError` at startup); the validation is deferred to `launch` time

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

### Requirement: Codex backend requires an OpenAI credential

When `GA_CREW_ACP_BACKEND=codex`, the transport SHALL accept either `OPENAI_API_KEY` (API-key path) or a valid `ga-codex-auth` credential archive (OAuth path) as the Codex authentication source. At least one MUST be present by the time `launch` is called. The transport SHALL NOT enforce this constraint at startup — it is enforced lazily at `launch` time, allowing the operator to authenticate via `POST /login/codex` before launching any crews.

#### Scenario: API key present with Codex backend
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `OPENAI_API_KEY` is set
- **THEN** `launch` proceeds normally; the key is injected as `OPENAI_API_KEY` into the crew container

#### Scenario: OAuth credential present, no API key — launch proceeds
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, `OPENAI_API_KEY` is unset, and `ga-codex-auth` exists and is non-empty
- **THEN** `launch` proceeds normally; the OAuth credential is injected into the crew container's `~/.codex/`

#### Scenario: Neither credential present — launch returns not_authenticated
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, `OPENAI_API_KEY` is unset, and `ga-codex-auth` does not exist or is empty
- **THEN** `launch` returns `not_authenticated` with a `login_url` for the Codex login flow; no crew container is created

#### Scenario: Missing credential does not fail at transport startup
- **WHEN** `GA_CREW_ACP_BACKEND=codex`, `OPENAI_API_KEY` is unset, and the transport starts
- **THEN** the transport starts successfully (no `ConfigError` at startup); the validation is deferred to `launch` time

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
