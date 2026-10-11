# Spec Delta

## ADDED Requirements

### Requirement: install.sh retries compose up on transient port conflict
`install.sh` SHALL retry the `podman compose up` invocation up to `GA_COMPOSE_RETRY_ATTEMPTS` times (default 3, minimum 1) with a `GA_COMPOSE_RETRY_DELAY_SECS`-second sleep (default 2) between attempts before giving up. On final failure, `install.sh` SHALL print the compose error output and exit non-zero.

#### Scenario: Compose up succeeds on first attempt
- **WHEN** `podman compose up` succeeds immediately
- **THEN** `install.sh` proceeds normally without sleeping

#### Scenario: Compose up fails transiently then succeeds
- **WHEN** `podman compose up` fails on the first attempt (e.g. transient port conflict) then succeeds on the second
- **THEN** `install.sh` sleeps `GA_COMPOSE_RETRY_DELAY_SECS` seconds and retries, and installation succeeds

#### Scenario: Compose up exhausts all retries
- **WHEN** `podman compose up` fails on every attempt up to `GA_COMPOSE_RETRY_ATTEMPTS`
- **THEN** `install.sh` prints the compose error to stderr and exits non-zero

#### Scenario: GA_COMPOSE_RETRY_ATTEMPTS=1 disables retry
- **WHEN** `GA_COMPOSE_RETRY_ATTEMPTS=1` is set and `podman compose up` fails
- **THEN** `install.sh` makes exactly one attempt, prints the error, and exits non-zero without sleeping

### Requirement: GA_COMPOSE_RETRY_ATTEMPTS and GA_COMPOSE_RETRY_DELAY_SECS documented
`docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` with their defaults, valid ranges, and purpose.

#### Scenario: Operator reads docs to disable retries
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_COMPOSE_RETRY_ATTEMPTS` documented with its default (3) and that setting it to 1 disables retry

#### Scenario: Example config includes retry variables
- **WHEN** an operator opens `config/ghostship.conf.example`
- **THEN** `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` are present as commented-out entries with their default values
