# Spec Delta

## MODIFIED Requirements

### Requirement: GA_REQUIRE_API_KEY defaults to error on non-loopback installs
The `GA_REQUIRE_API_KEY` setting SHALL default to `error` (changed from `warn`). When `HOST` is unset or `127.0.0.1`, the check SHALL be skipped entirely — no API key is required for loopback installs. When `HOST` is any non-loopback value and `GA_API_KEY` is not set, the install SHALL abort with an error message directing the operator to set `GA_API_KEY` or use `GA_REQUIRE_API_KEY=off`. Setting `GA_REQUIRE_API_KEY=off` SHALL allow unauthenticated remote access (for deployments that place their own auth layer in front). The `warn` mode MAY be removed in a future release.

#### Scenario: Remote install without API key aborts
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and `GA_API_KEY` is not set and `GA_REQUIRE_API_KEY` is not `off`
- **THEN** the install aborts with a non-zero exit code before starting any containers, and the error message names `GA_API_KEY` and `GA_REQUIRE_API_KEY=off` as the resolution paths

#### Scenario: Local install without API key succeeds
- **WHEN** `install.sh` is run with `HOST=127.0.0.1` (or `HOST` unset) and `GA_API_KEY` is not set
- **THEN** the install completes normally and the transport starts without authentication

#### Scenario: Remote install with GA_REQUIRE_API_KEY=off succeeds
- **WHEN** `install.sh` is run with `HOST=0.0.0.0`, `GA_API_KEY` not set, and `GA_REQUIRE_API_KEY=off`
- **THEN** the install completes normally with a warning logged that the transport is unauthenticated

### Requirement: Transport startup enforces GA_REQUIRE_API_KEY=error
The transport SHALL re-check the `GA_REQUIRE_API_KEY` constraint at startup. If `GA_REQUIRE_API_KEY` is `error` (or unset, i.e. default) and the bind address is non-loopback and no API key secret is present, the transport SHALL refuse to start and exit with a non-zero code.

#### Scenario: Transport refuses to start unauthenticated on non-loopback
- **WHEN** the transport starts with a non-loopback bind address and no `ga-api-key` secret and `GA_REQUIRE_API_KEY` is not `off`
- **THEN** the transport exits immediately with a logged error naming the missing API key
