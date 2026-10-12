# claude-setup-token-auth Specification

## Purpose

Provides headless Claude auth for unattended deployments: the operator generates a long-lived token with `claude setup-token` on their own machine and sets it as `CLAUDE_CODE_OAUTH_TOKEN` in `ghostship.conf`; the transport delivers it to Claude-backend crews, with a defined precedence against the API key and the stored OAuth credential (TRN-226).

## Requirements

### Requirement: Claude OAuth token configured by the operator

The operator SHALL be able to supply a long-lived Claude token, generated with `claude setup-token` on their own machine, through the `CLAUDE_CODE_OAUTH_TOKEN` setting in `ghostship.conf`. The transport SHALL NOT run `claude setup-token` itself and SHALL NOT expose an HTTP route that obtains this token.

#### Scenario: Token supplied through config
- **WHEN** `CLAUDE_CODE_OAUTH_TOKEN` is set in `ghostship.conf` and `ghostship install` runs
- **THEN** the transport starts with the token available for Claude-backend crews, and no login container is created

#### Scenario: Token never logged
- **WHEN** the transport starts with `CLAUDE_CODE_OAUTH_TOKEN` configured and emits logs or audit events
- **THEN** the token value does not appear in any log line, audit event or HTTP response

### Requirement: Claude OAuth token injected into crew containers

When `CLAUDE_CODE_OAUTH_TOKEN` is configured, `ANTHROPIC_API_KEY` is not configured, and a crew is launched on the Claude backend, the transport SHALL set `CLAUDE_CODE_OAUTH_TOKEN` in the crew container's environment to the configured token, and SHALL NOT inject the `ga-claude-auth` credential into the crew's `~/.claude/` directory.

#### Scenario: Token injected at launch
- **WHEN** a crew is launched with claude as its backend, `CLAUDE_CODE_OAUTH_TOKEN` is set and `ANTHROPIC_API_KEY` is not
- **THEN** the crew container's environment contains `CLAUDE_CODE_OAUTH_TOKEN` with the configured value, and `ANTHROPIC_API_KEY` is absent

#### Scenario: Stored OAuth credential not injected alongside the token
- **WHEN** a crew is launched with claude as its backend, `CLAUDE_CODE_OAUTH_TOKEN` is set, and `ga-claude-auth` also exists
- **THEN** `CLAUDE_CODE_OAUTH_TOKEN` is injected and the crew's `~/.claude/` does not receive the `ga-claude-auth` credential

#### Scenario: Token not injected into non-Claude crews
- **WHEN** a crew is launched on the kiro or codex backend while `CLAUDE_CODE_OAUTH_TOKEN` is set
- **THEN** the crew container's environment does not contain `CLAUDE_CODE_OAUTH_TOKEN`

### Requirement: Claude credential precedence

For a Claude-backend crew the transport SHALL select exactly one credential, in this order: `ANTHROPIC_API_KEY`, then `CLAUDE_CODE_OAUTH_TOKEN`, then `ga-claude-auth`. Only the selected credential SHALL be delivered to the crew.

#### Scenario: API key outranks the token
- **WHEN** both `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` are set and a Claude-backend crew is launched
- **THEN** the crew receives `ANTHROPIC_API_KEY`, does not receive `CLAUDE_CODE_OAUTH_TOKEN`, and does not receive the `ga-claude-auth` credential

#### Scenario: Stored OAuth credential used only as a fallback
- **WHEN** neither `ANTHROPIC_API_KEY` nor `CLAUDE_CODE_OAUTH_TOKEN` is set and `ga-claude-auth` exists
- **THEN** the crew's `~/.claude/` receives the `ga-claude-auth` credential and neither environment variable is set

### Requirement: Claude OAuth token satisfies the launch auth check

When the default backend is claude, `launch` SHALL treat a configured `CLAUDE_CODE_OAUTH_TOKEN` as a valid Claude credential and SHALL NOT start the interactive Claude login flow or return `not_authenticated`.

#### Scenario: Launch proceeds with only the token
- **WHEN** `launch` is called with claude as the default backend, `CLAUDE_CODE_OAUTH_TOKEN` set, no `ANTHROPIC_API_KEY` and no `ga-claude-auth`
- **THEN** the crew is created and no Claude login container is started

#### Scenario: Launch still prompts with no Claude credential
- **WHEN** `launch` is called with claude as the default backend and none of `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` or `ga-claude-auth` is present
- **THEN** `launch` returns `not_authenticated` with a login URL, unchanged from the existing behaviour

### Requirement: Claude OAuth token reported as inert when claude is disabled

When `CLAUDE_CODE_OAUTH_TOKEN` is set but claude is not an enabled backend, the transport SHALL include it in the inert backend-setting warnings, as it does for `ANTHROPIC_API_KEY`.

#### Scenario: Inert token warning
- **WHEN** the transport starts with `CLAUDE_CODE_OAUTH_TOKEN` set and claude absent from the enabled backends
- **THEN** a warning names `CLAUDE_CODE_OAUTH_TOKEN` as a setting with no effect, without printing its value
