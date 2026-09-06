# Config File Specification

## Purpose

Allow operators to set install.sh defaults in a shell config file rather than passing long flag lists on every invocation. The config file is sourced before flag parsing so command-line flags always override config-file values.

## Requirements

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

### Requirement: Config file format documentation
`docs/configuration.md` SHALL document the config file format (shell file exporting variables), list all supported variables, and state the resolution order explicitly: built-in default → config file → command-line flag, with no ambient-environment-variable tier. It SHALL also state, for variables that are passed through into the transport container's own runtime environment, that this is a distinct later step (`install.sh` baking its own already-resolved values into `podman run -e` flags) and not something an operator sets by exporting a variable in any shell.

The documentation SHALL also document the full model precedence chain:
`dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model field > `KC_MODEL_DEFAULT` > KiroCrew built-in default

Variables removed from the operator-configurable surface (`HOST`, `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`) SHALL NOT appear in the supported variable list. `GA_PORTAL_PORT` SHALL appear only as a deprecated alias with a note pointing to `PORT`.

#### Scenario: Config file section present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL contain a "Config file" section explaining that the file is a shell script exporting variables, listing all supported variable names, and stating the resolution order: built-in default → config file → command-line flag

#### Scenario: No ambient environment variable tier documented
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL NOT describe exporting a variable in the invoking shell as a supported way to configure `install.sh` or `uninstall.sh`

#### Scenario: Model precedence table present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL include a model precedence table or section documenting: `dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model > `KC_MODEL_DEFAULT` > KiroCrew built-in

#### Scenario: Removed vars absent from docs
- **WHEN** reading `docs/configuration.md`
- **THEN** the removed variables SHALL NOT appear as supported operator-configurable inputs

### Requirement: Auth docs config file reference
`docs/auth.md` SHALL document the config file as the first item in identity provider resolution order (config file → flags → interactive prompt) and include an example config file snippet for identity provider settings.

#### Scenario: Auth docs reference config file
- **WHEN** reading `docs/auth.md` "Identity provider config" section
- **THEN** it SHALL list config file as item 1 in the resolution order and include an example snippet showing `KIRO_IDENTITY_PROVIDER=...` and `KIRO_REGION=...`

### Requirement: Transport runtime config centralised in Config dataclass
The transport SHALL load all runtime configuration from environment variables exactly once at startup into a `Config` dataclass defined in `transport/config.py`. All transport subsystems SHALL read configuration from this loaded instance rather than calling `os.environ.get()` directly at use sites.

#### Scenario: Config loaded at startup
- **WHEN** the transport process starts
- **THEN** a single `Config` instance is constructed from the current environment variables before any request is handled

#### Scenario: Default values applied consistently
- **WHEN** an environment variable is absent
- **THEN** the `Config` dataclass applies the same default that was previously scattered at each call site

### Requirement: Config fields match ghostship.conf.example
Every field in the `Config` dataclass SHALL have a corresponding commented-out entry in `config/ghostship.conf.example`, and vice versa. A CI test SHALL assert this invariant so the two cannot silently diverge.

#### Scenario: CI sync check passes
- **WHEN** `Config` fields and `ghostship.conf.example` entries are in sync
- **THEN** the CI test passes

#### Scenario: CI sync check fails on drift
- **WHEN** a field is added to `Config` without a matching entry in `ghostship.conf.example`
- **THEN** the CI test fails and identifies the missing entry

### Requirement: Operator-configurable git author identity for crew commits
The system SHALL optionally inject `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` environment variables into crew containers at creation time when `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set. When set, all commits made by agents inside the crew SHALL carry the operator's configured identity as both author and committer.

#### Scenario: Git identity injected when configured
- **WHEN** `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set and a crew is launched
- **THEN** the crew container has all four git identity env vars set to the configured values

#### Scenario: Identity not injected when unconfigured
- **WHEN** `GA_GIT_AUTHOR_NAME` is unset
- **THEN** the crew container does not have `GIT_AUTHOR_NAME` or `GIT_COMMITTER_NAME` in its environment — kiro-cli uses its own per-session identity
