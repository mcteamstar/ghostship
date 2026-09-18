## MODIFIED Requirements

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
