## MODIFIED Requirements

### Requirement: Config file sourcing with correct precedence

The system SHALL accept a `--config <path>` flag pointing to a shell file that exports configuration variables. The config file SHALL be sourced BEFORE other flags are processed, so that command-line flags take precedence over config-file values. Every supported variable SHALL be assigned a literal built-in default BEFORE the config file is sourced.

Before sourcing the config file, `install.sh` SHALL check whether it contains `GA_PORTAL_PORT`. If found, it SHALL print a deprecation warning and automatically substitute `GA_PORTAL_PORT` with `PORT` in the effective config, so that existing config files continue to work without requiring manual edits.

#### Scenario: Config file sets defaults, no flags override
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` exports `PORT=9000`
- **AND** no `--port` flag is passed
- **THEN** the transport SHALL use port `9000`

#### Scenario: Command-line flag overrides config file
- **WHEN** `install.sh` runs with `--config ./my.conf --port 8000` and `my.conf` exports `PORT=9000`
- **THEN** the transport SHALL use port `8000` (flag wins)

#### Scenario: Config file sets identity provider
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` exports `KIRO_IDENTITY_PROVIDER=https://idp.example.com` and `KIRO_REGION=us-west-2`
- **AND** no `--identity-provider` or `--region` flags are passed
- **THEN** the transport SHALL use the config file values for identity provider and region

#### Scenario: Missing config file
- **WHEN** `install.sh` runs with `--config /nonexistent/path`
- **THEN** the script SHALL exit with a non-zero status and print an error indicating the file does not exist or is not readable

#### Scenario: Config file with all supported variables
- **WHEN** a config file exports any combination of: `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`, `PORT`, `KC_MODEL_OVERRIDE`, `KC_MODEL_DEFAULT`, `GA_API_KEY`, `GA_HOST_URL`, `GA_DEDICATED_MACHINE`, `GA_MACHINE_NAME`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`
- **THEN** each exported variable SHALL act as a default, overridable by its corresponding flag where one exists
- **AND** the following variables SHALL no longer be supported as operator-configurable inputs and SHALL be ignored if present: `GA_PORTAL_PORT` (superseded by `PORT`), `HOST`, `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`

#### Scenario: GA_PORTAL_PORT in config file is auto-migrated
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` contains `GA_PORTAL_PORT=9000`
- **THEN** `install.sh` SHALL print a deprecation warning stating `GA_PORTAL_PORT` is renamed to `PORT`
- **AND** the effective value of `PORT` SHALL be `9000` (the migration is applied automatically — no manual edit required)

#### Scenario: Config file sets git author identity
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` exports `GA_GIT_AUTHOR_NAME="Your Name"` and `GA_GIT_AUTHOR_EMAIL="you@example.com"`
- **THEN** crew containers SHALL have `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` set to the configured values

#### Scenario: Git identity vars absent — per-persona identity preserved
- **WHEN** `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are not set
- **THEN** crew containers SHALL use the per-persona git identity (e.g. `Ghost <ghost@localhost>`) as before

#### Scenario: Ambient environment variable ignored when unset elsewhere
- **WHEN** the invoking shell has `GA_MACHINE_NAME=from-env` exported, no `--config` file is passed, and no corresponding flag is passed
- **THEN** `install.sh` SHALL use the built-in default (`ghost-academy`), not the ambient value `from-env`

#### Scenario: Config file overrides an ambient environment variable
- **WHEN** the invoking shell has `GA_MACHINE_NAME=from-env` exported and `--config ./my.conf` is passed with `my.conf` exporting `GA_MACHINE_NAME=from-config`
- **THEN** `install.sh` SHALL use `from-config`

### Requirement: Config file format documentation

`docs/configuration.md` SHALL document the config file format, list all supported variables, state the resolution order, and document the full model precedence chain.

The model precedence chain SHALL be documented as:
`dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model field > `KC_MODEL_DEFAULT` > KiroCrew built-in default

Variables removed from the operator-configurable surface (`HOST`, `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`) SHALL NOT appear in the supported variable list. `GA_PORTAL_PORT` SHALL appear only as a deprecated alias with a note pointing to `PORT`.

#### Scenario: Config file section present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL contain a "Config file" section listing supported variables and the resolution order: built-in default → config file → command-line flag

#### Scenario: Model precedence table present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL include a model precedence table or section documenting: `dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model > `KC_MODEL_DEFAULT` > KiroCrew built-in

#### Scenario: Removed vars absent from docs
- **WHEN** reading `docs/configuration.md`
- **THEN** the removed variables SHALL NOT appear as supported operator-configurable inputs
