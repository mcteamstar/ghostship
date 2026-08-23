## MODIFIED Requirements

### Requirement: Crew configuration supports operator-tunable task timeout

The transport SHALL apply operator-configured task timeout and turn limit
overrides to each crew's local configuration at launch time. Both values SHALL
be driven by environment variables with sensible defaults that allow long-running
implementation tasks to complete without hitting the KiroCrew default ceiling.

The following operator-level environment variables SHALL be supported:

| Variable | Default | Description |
|---|---|---|
| `GA_SUBAGENT_TIMEOUT_SECS` | 3600 | Maximum wall-clock seconds per task (subagent_timeout_secs) |
| `GA_SUBAGENT_MAX_TURNS` | 200 | Maximum turns per task (subagent_max_turns) |

Both variables SHALL be documented in `docs/configuration.md`.

#### Scenario: Operator sets custom timeout

- **WHEN** the transport is started with `GA_SUBAGENT_TIMEOUT_SECS=7200`
- **THEN** every new crew's `config.local.json` contains `subagent_timeout_secs: 7200`

#### Scenario: Default timeout applied when env var absent

- **WHEN** the transport is started without `GA_SUBAGENT_TIMEOUT_SECS` set
- **THEN** every new crew's `config.local.json` contains `subagent_timeout_secs: 3600`

#### Scenario: Operator sets custom turn limit

- **WHEN** the transport is started with `GA_SUBAGENT_MAX_TURNS=300`
- **THEN** every new crew's `config.local.json` contains `subagent_max_turns: 300`
