# agent-backends Specification

## Purpose
Defines the set of agent backends a Ghost Academy transport enables, the default backend, and the rules that keep configuration consistent. This is the single place that decides which backends exist on an instance, so that kiro, Claude and Codex are configured the same way.

## Requirements

### Requirement: GA_AGENT_BACKENDS selects the enabled agent backends
The transport SHALL derive the enabled backend set from the resolved backend
configuration sections. Valid backend names are `kiro`, `claude`, and `codex`.
Kiro SHALL always be included; Claude and Codex SHALL be included only when their
corresponding backend sections are configured. The set SHALL preserve no fallback
meaning from list ordering.

#### Scenario: Configured sections define enabled set
- **WHEN** the resolved configuration contains `backends.kiro` and `backends.claude` but no `backends.codex`
- **THEN** the enabled set SHALL be `{kiro, claude}`

#### Scenario: Backend section absent
- **WHEN** `backends.codex` is absent from the resolved configuration
- **THEN** Codex SHALL not be bundled, enabled, or accepted by backend-specific launch and login operations

#### Scenario: Unknown backend section rejected
- **WHEN** the configuration contains `backends.gemini`
- **THEN** install.sh SHALL reject or clearly warn about the unknown backend rather than bundling it

#### Scenario: Default set is kiro only
- **WHEN** neither optional backend section is configured
- **THEN** the enabled set SHALL be `{kiro}`, with no Claude or Codex backend enabled

#### Scenario: Multiple backends enabled
- **WHEN** `backends.claude` and `backends.codex` are configured
- **THEN** the enabled set SHALL be `{claude, codex}`

#### Scenario: Empty entries, duplicates and case are normalised
- **WHEN** backend configuration is normalized from repeated or case-varied entries
- **THEN** the enabled set SHALL contain each configured supported backend once

#### Scenario: Unknown backend name rejected at startup
- **WHEN** an unsupported backend section is present
- **THEN** configuration validation SHALL reject it naming the unknown value and valid names

### Requirement: Kiro is always enabled
The Kiro backend SHALL remain implicitly enabled as the built-in backend, regardless
of whether `backends.kiro` has an explicit configuration section.

#### Scenario: Omitting kiro does not disable it
- **WHEN** `backends.kiro` is absent and only `backends.claude` is configured
- **THEN** Kiro SHALL still be bundled and accepted as the built-in enabled backend

#### Scenario: Listing kiro changes nothing
- **WHEN** `backends.kiro` is present
- **THEN** Kiro SHALL be bundled and accepted as an enabled backend

### Requirement: The default backend must be an enabled backend
The scalar `backends.default` SHALL select the default backend for new crews and
SHALL name an enabled backend. If it names an absent optional or unknown backend,
install.sh or transport startup SHALL fail with an actionable error. If omitted, it
SHALL resolve to the built-in Kiro backend.

#### Scenario: Default backend is enabled
- **WHEN** `backends.default: claude` and `backends.claude` are configured
- **THEN** the transport SHALL start and use Claude for launches without an explicit backend

#### Scenario: Default backend is absent
- **WHEN** `backends.default: codex` is configured but `backends.codex` is absent
- **THEN** configuration validation SHALL fail and identify the missing backend section

#### Scenario: Default backend outside the set
- **WHEN** the scalar default names a backend whose section is absent
- **THEN** the transport SHALL raise a configuration error naming the default and enabled backend settings

#### Scenario: Default backend inside the set
- **WHEN** the scalar default names a configured optional backend section or Kiro
- **THEN** the transport SHALL start with that backend as the default

### Requirement: Settings for disabled backends are reported as inert

Once per transport start, the transport SHALL log one warning per inert setting: `ANTHROPIC_BASE_URL` while claude is disabled, `OPENAI_BASE_URL` while codex is disabled, and a stored credential for any disabled backend. Each warning SHALL name the setting or backend and method and SHALL NOT include any value. Inert settings SHALL NOT change behaviour.

#### Scenario: Credential for a disabled backend warns without its value
- **WHEN** claude holds a stored `api-key` credential and claude is not enabled
- **THEN** the transport logs a warning that the stored claude credential (api-key) has no effect, the log does not contain the key's value, and startup continues

#### Scenario: Each warning is logged once per start
- **WHEN** the transport starts with `OPENAI_BASE_URL` set and codex disabled
- **THEN** exactly one warning naming `OPENAI_BASE_URL` is logged for that start, regardless of how many modules load the configuration

#### Scenario: No warning for an enabled backend
- **WHEN** claude holds a stored credential and claude is enabled
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
