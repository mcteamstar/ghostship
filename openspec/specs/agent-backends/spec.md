# agent-backends Specification

## Purpose
Defines the set of agent backends a Ghost Academy transport enables, the default backend, and the rules that keep configuration consistent. This is the single place that decides which backends exist on an instance, so that kiro, Claude and Codex are configured the same way.

## Requirements

### Requirement: GA_AGENT_BACKENDS selects the enabled agent backends

The transport SHALL read `GA_AGENT_BACKENDS` at startup as a comma-separated list of backend names. Valid names are `kiro`, `claude` and `codex`. Names SHALL be matched case-insensitively with surrounding whitespace ignored. Empty entries and duplicates SHALL be ignored. The enabled set SHALL always contain `kiro`, plus each valid name listed.

#### Scenario: Default set is kiro only
- **WHEN** `GA_AGENT_BACKENDS` is unset or empty
- **THEN** the enabled set is `{kiro}`, and no Claude or Codex login or default backend is accepted

#### Scenario: Multiple backends enabled
- **WHEN** `GA_AGENT_BACKENDS=claude, codex` is set
- **THEN** the enabled set is `{kiro, claude, codex}`

#### Scenario: Empty entries, duplicates and case are normalised
- **WHEN** `GA_AGENT_BACKENDS=" Claude,,claude , CODEX"` is set
- **THEN** the enabled set is `{kiro, claude, codex}`

#### Scenario: Unknown backend name rejected at startup
- **WHEN** `GA_AGENT_BACKENDS` contains a name outside `kiro`, `claude`, `codex`
- **THEN** the transport raises a `ConfigError` naming the unknown value and the valid names, and does not start

### Requirement: Kiro is always enabled

The kiro backend SHALL be enabled regardless of `GA_AGENT_BACKENDS`, because KiroCrew bundles kiro in every crew image. Listing `kiro` SHALL have no effect, and omitting it SHALL NOT disable kiro.

#### Scenario: Omitting kiro does not disable it
- **WHEN** `GA_AGENT_BACKENDS=claude` is set and `GA_CREW_ACP_BACKEND` is unset, and a crew is launched
- **THEN** the crew launches on kiro without error

#### Scenario: Listing kiro changes nothing
- **WHEN** the transport is started once with `GA_AGENT_BACKENDS=kiro,claude` and once with `GA_AGENT_BACKENDS=claude`
- **THEN** the enabled set is `{kiro, claude}` both times

### Requirement: The default backend must be an enabled backend

`GA_CREW_ACP_BACKEND` SHALL select the default backend for new crews, and SHALL default to `kiro` when unset. If it names a backend outside the enabled set, the transport SHALL raise a `ConfigError` at startup that names both settings and states that `ghostship install` must be re-run after changing them.

#### Scenario: Default backend outside the set
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_AGENT_BACKENDS` does not list `claude`
- **THEN** the transport raises a `ConfigError` naming `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS`, and does not start

#### Scenario: Default backend inside the set
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `GA_AGENT_BACKENDS=claude`
- **THEN** the transport starts with claude as the default backend

### Requirement: Settings for disabled backends are reported as inert

Once per transport start, the transport SHALL log one warning per inert setting: the `GA_CREW_ANTHROPIC_*` settings while claude is disabled, the `GA_CREW_OPENAI_*` settings while codex is disabled, and a stored `ga-claude-auth` or `ga-codex-auth` for a disabled backend. Each warning SHALL name the setting and SHALL NOT include its value. Inert settings SHALL NOT change behaviour.

#### Scenario: Credential for a disabled backend warns without its value
- **WHEN** `GA_CREW_ANTHROPIC_API_KEY` is set and claude is not enabled
- **THEN** the transport logs a warning naming `GA_CREW_ANTHROPIC_API_KEY` as having no effect, the log does not contain the key's value, and startup continues

#### Scenario: Each warning is logged once per start
- **WHEN** the transport starts with `GA_CREW_OPENAI_API_KEY` set and codex disabled
- **THEN** exactly one warning naming `GA_CREW_OPENAI_API_KEY` is logged for that start, regardless of how many modules load the configuration

#### Scenario: No warning for an enabled backend
- **WHEN** `GA_CREW_ANTHROPIC_API_KEY` is set and claude is enabled
- **THEN** no inert-setting warning is logged for it

### Requirement: Login is available only for enabled backends

`POST /login/claude` and `POST /login/claude/code` SHALL be available when claude is enabled, and `POST /login/codex` when codex is enabled, whether or not it is the default. Otherwise they SHALL return HTTP 400 naming `GA_AGENT_BACKENDS` and the install re-run, checked before the body or pending flow, and create no login container. Kiro's `POST /login` and every `POST /logout/<backend>` SHALL stay available.

#### Scenario: Login refused for a backend not in the set
- **WHEN** `GA_AGENT_BACKENDS` is unset and `POST /login/claude` is called
- **THEN** the transport returns HTTP 400 naming `GA_AGENT_BACKENDS`, and no login container is created

#### Scenario: Login allowed for an enabled backend that is not the default
- **WHEN** `GA_AGENT_BACKENDS=claude`, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/claude` is called
- **THEN** the Claude login flow starts and the response contains a `login_url`

#### Scenario: Disabled-backend check precedes body validation
- **WHEN** claude is not enabled and `POST /login/claude/code` is called with a malformed body
- **THEN** the transport returns HTTP 400 naming `GA_AGENT_BACKENDS`, not the malformed-body error

#### Scenario: Logout works for a disabled backend
- **WHEN** claude is not enabled, `ga-claude-auth` exists, and `POST /logout/claude` is called
- **THEN** `ga-claude-auth` is deleted

### Requirement: Retired include flags are rejected

`GA_INCLUDE_CLAUDE_AGENT` and `GA_INCLUDE_CODEX_AGENT` are retired. If either is present with a non-empty value, the transport SHALL raise a `ConfigError` at startup, and `install.sh` SHALL exit with an error. Both messages SHALL name the variable and its replacement, `GA_AGENT_BACKENDS`. Neither variable SHALL change the enabled set.

#### Scenario: Retired Claude flag stops startup
- **WHEN** `GA_INCLUDE_CLAUDE_AGENT=true` is set
- **THEN** the transport raises a `ConfigError` naming `GA_INCLUDE_CLAUDE_AGENT` and `GA_AGENT_BACKENDS`, and does not start

#### Scenario: Retired flag set to false still stops startup
- **WHEN** `GA_INCLUDE_CODEX_AGENT=false` is set
- **THEN** the transport raises a `ConfigError` naming `GA_INCLUDE_CODEX_AGENT` and `GA_AGENT_BACKENDS`, and does not start

#### Scenario: install.sh refuses a retired flag
- **WHEN** `ghostship.conf` sets `GA_INCLUDE_CLAUDE_AGENT=true` and `install.sh` runs
- **THEN** `install.sh` exits non-zero before building, with a message naming `GA_INCLUDE_CLAUDE_AGENT` and `GA_AGENT_BACKENDS`
