# Spec Delta

## MODIFIED Requirements

### Requirement: Claude credential injected into crew containers at launch

When `GA_CREW_ACP_BACKEND=claude`, `ga-claude-auth` exists, and neither `ANTHROPIC_API_KEY` nor `CLAUDE_CODE_OAUTH_TOKEN` is set, the transport SHALL inject the Claude credential into each new crew container's `~/.claude/` directory during setup, so `claude-agent-acp` can authenticate without an API key.

#### Scenario: OAuth credential injected at crew setup
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude`, `ga-claude-auth` is present, and neither `ANTHROPIC_API_KEY` nor `CLAUDE_CODE_OAUTH_TOKEN` is set
- **THEN** the Claude credential is written into the crew container's `~/.claude/` before the gateway starts; no `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` env var is injected

#### Scenario: API key path unaffected when GA_CREW_ANTHROPIC_API_KEY is set
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` and `ANTHROPIC_API_KEY` is set (regardless of `ga-claude-auth` presence)
- **THEN** the API key env var path takes precedence; OAuth credential injection is skipped

#### Scenario: OAuth credential injection skipped when the OAuth token is set
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude`, `CLAUDE_CODE_OAUTH_TOKEN` is set, and `ga-claude-auth` is present
- **THEN** `CLAUDE_CODE_OAUTH_TOKEN` is injected and the `ga-claude-auth` credential is not written into the crew container's `~/.claude/`

### Requirement: Claude backend is opt-in

The Claude backend SHALL be available only when `claude` is an enabled backend, as defined by the `agent-backends` capability (`GA_AGENT_BACKENDS`). Kiro remains the default. Claude login SHALL be available whenever claude is enabled, including when it is not the default backend. When claude is not enabled, `POST /login/claude` SHALL return HTTP 400 naming `GA_AGENT_BACKENDS`, and the transport SHALL refuse to start with claude as the default backend.

The operator documentation (`docs/auth.md`) SHALL document `CLAUDE_CODE_OAUTH_TOKEN` (generated with `claude setup-token`) as the recommended Claude auth path for headless and server deployments, and SHALL document the OAuth device-code flow (`POST /login/claude` + `POST /login/claude/code`) as the alternative for interactive use. The known-limitation note about OAuth token expiry causing cross-crew invalidation SHALL be scoped to the OAuth path only and SHALL NOT apply to the token path.

#### Scenario: Login refused when the image lacks the Claude CLI
- **WHEN** claude is not an enabled backend and `POST /login/claude` is called
- **THEN** the transport returns HTTP 400 with a message naming `GA_AGENT_BACKENDS`, and no login container is created

#### Scenario: Setup-token login refused when the image lacks the Claude CLI
- **WHEN** claude is not an enabled backend and `POST /login/claude/setup-token` is called
- **THEN** the transport returns HTTP 404 because the route no longer exists, and no login container is created

#### Scenario: Launch refused when the image lacks the Claude CLI
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and claude is not an enabled backend
- **THEN** the transport raises a `ConfigError` at startup naming both settings, so no launch or Claude login flow can start

#### Scenario: Kiro is the default backend
- **WHEN** `GA_CREW_ACP_BACKEND` is unset
- **THEN** crews launch on kiro and no Claude login or opt-in check applies to them

#### Scenario: Claude login available while kiro is the default
- **WHEN** claude is an enabled backend, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/claude` is called
- **THEN** the Claude login flow starts

#### Scenario: Setup-token login available while kiro is the default
- **WHEN** claude is an enabled backend, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/claude/setup-token` is called
- **THEN** the transport returns HTTP 404 because the route no longer exists; headless Claude auth is configured through `CLAUDE_CODE_OAUTH_TOKEN` instead
