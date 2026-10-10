## ADDED Requirements

### Requirement: Unauthenticated non-loopback bind warning
`install.sh` SHALL emit a prominent `WARNING` to stderr when `GA_API_KEY` is not
set (or empty) **and** the published host port maps to a non-loopback address
(i.e. anything other than `127.0.0.1` or `::1`). The default published address
is `0.0.0.0`, which triggers the warning. The warning SHALL name the port, state
that MCP endpoints are accessible to any host that can reach the machine, and
direct the operator to pass `--api-key` or set `GA_REQUIRE_API_KEY=off` to
silence it.

`GA_REQUIRE_API_KEY` controls the severity of the check:
- `warn` (default) — print warning and continue.
- `error` — print warning and exit non-zero.
- `off` — skip the check entirely.

The transport process SHALL also log a `WARNING`-level message at startup when
`GA_API_KEY` is absent and the `HOST` environment variable is not a loopback
address (`127.0.0.1` or `::1`).

#### Scenario: Default install without API key on non-loopback address emits warning
- **WHEN** `install.sh` runs without `--api-key`, `GA_REQUIRE_API_KEY` is unset
  or `warn`, and the published port maps to `0.0.0.0`
- **THEN** `install.sh` prints a WARNING to stderr naming the port and stating
  that unauthenticated access is enabled, and installation continues

#### Scenario: GA_REQUIRE_API_KEY=error without API key exits
- **WHEN** `install.sh` runs without `--api-key`, `GA_REQUIRE_API_KEY=error`,
  and the published port maps to a non-loopback address
- **THEN** `install.sh` prints the same WARNING to stderr and exits non-zero
  before writing compose.yml

#### Scenario: GA_REQUIRE_API_KEY=off suppresses the check
- **WHEN** `install.sh` runs without `--api-key` and `GA_REQUIRE_API_KEY=off`
- **THEN** no warning is printed, installation continues normally

#### Scenario: API key set on non-loopback address does not warn
- **WHEN** `install.sh` runs with `--api-key <value>` and the published port
  maps to `0.0.0.0`
- **THEN** no unauthenticated-access warning is printed

#### Scenario: Transport logs startup warning when unauthenticated on non-loopback
- **WHEN** the transport process starts with `GA_API_KEY` absent and `HOST` set
  to a non-loopback address
- **THEN** the transport logs a `WARNING`-level message stating that no API key
  is configured and MCP endpoints are accessible without authentication

### Requirement: GA_REQUIRE_API_KEY and GA_TRUSTED_PROXY documented in configuration docs
`docs/configuration.md` SHALL include entries for `GA_REQUIRE_API_KEY` (its three
values, the default, and when to use `error` or `off`) and `GA_TRUSTED_PROXY`
(what it does, the default, and how to set it for Caddy-fronted installs).

`config/ghostship.conf.example` SHALL include commented-out entries for both
variables.

#### Scenario: Operator reads docs to understand authentication posture options
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_REQUIRE_API_KEY` documented with its three values and
  the warning behaviour, and `GA_TRUSTED_PROXY` documented with its effect on
  rate-limit source-IP extraction

#### Scenario: Example config includes both variables
- **WHEN** an operator opens `config/ghostship.conf.example`
- **THEN** `GA_REQUIRE_API_KEY` and `GA_TRUSTED_PROXY` are present as commented-out
  entries with their defaults
