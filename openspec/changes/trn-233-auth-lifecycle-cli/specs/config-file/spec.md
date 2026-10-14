# Spec Delta

## MODIFIED Requirements

### Requirement: Config file sourcing with correct precedence
The system SHALL accept a `--config <path>` flag pointing to a shell file that exports configuration variables. The config file SHALL be sourced BEFORE other flags are processed, so that command-line flags take precedence over values from the config file. Every supported variable SHALL be assigned a literal built-in default BEFORE the config file is sourced, so the config file's assignment (if any) unconditionally overrides that default rather than an ambient value inherited from the invoking shell's environment. Resolution order for every variable: built-in default → config file → command-line flag (where a corresponding flag exists). The system SHALL NOT treat an environment variable exported in the invoking shell as a configuration input at any point in this resolution — an ambient value with no corresponding config-file entry or flag SHALL be ignored, and the built-in default SHALL apply instead. A command-line flag is not required to mirror a single config-file variable one-to-one; a flag MAY represent a composite concept spanning what were previously multiple separate variables (for example, `--public-url` setting `GA_HOST_URL`, which replaced the separate `GA_FILE_PUBLIC_URL`/`GA_MCP_PUBLIC_URL` variables).

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
- **AND** backend credentials (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`, `KIRO_API_KEY`) SHALL be ignored with a warning pointing at `ghostship auth login <backend>`

#### Scenario: GA_PORTAL_PORT in config file is auto-migrated
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` contains `GA_PORTAL_PORT=9000`
- **THEN** `install.sh` SHALL print a deprecation warning stating `GA_PORTAL_PORT` is renamed to `PORT`
- **AND** the effective value of `PORT` SHALL be `9000` (the migration is applied automatically — no manual edit required)

#### Scenario: Config file sets git author identity
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` exports `GA_GIT_AUTHOR_NAME="Your Name"` and `GA_GIT_AUTHOR_EMAIL="you@example.com"`
- **THEN** crew containers SHALL have `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` set to the configured values

#### Scenario: Git identity vars absent — per-persona identity preserved
- **WHEN** `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are not set
- **THEN** crew containers SHALL use the per-persona git identity (e.g. `Ghost <ghost@localhost>`) as before — no breaking change

#### Scenario: Ambient environment variable ignored when unset elsewhere
- **WHEN** the invoking shell has `GA_MACHINE_NAME=from-env` exported, no `--config` file is passed, and no corresponding flag is passed
- **THEN** `install.sh` SHALL use the built-in default (`ghost-academy`), not the ambient value `from-env`

#### Scenario: Config file overrides an ambient environment variable
- **WHEN** the invoking shell has `GA_MACHINE_NAME=from-env` exported and `--config ./my.conf` is passed with `my.conf` exporting `GA_MACHINE_NAME=from-config`
- **THEN** `install.sh` SHALL use `from-config`

## ADDED Requirements

### Requirement: Auth docs describe the auth command
`docs/auth.md` SHALL state that backend credentials are not configured in `ghostship.conf`, SHALL keep the config-file snippet for `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` as the Identity Center default, and SHALL document `ghostship auth login <kiro|claude|codex>`, its methods, `ghostship auth logout <backend>` and `ghostship auth status`.

#### Scenario: Auth docs reference the auth command
- **WHEN** reading `docs/auth.md`
- **THEN** it describes each backend's login methods under `ghostship auth login`, including that Identity Center defaults to the configured start URL and region, and contains no credential snippet for `ghostship.conf`

## REMOVED Requirements

### Requirement: Auth docs config file reference
**Reason**: Credentials are no longer set in `ghostship.conf`; the auth docs centre on `ghostship auth`.
**Migration**: Replaced by "Auth docs describe the auth command".
