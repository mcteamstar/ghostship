# Spec Delta

## MODIFIED Requirements

### Requirement: Config file sourcing with correct precedence
The system SHALL accept a `--config <path>` flag pointing to a YAML file that
provides configuration overrides. The `--config` file SHALL be merged on top of
built-in defaults only, replacing the implicit repo-level and XDG override layers
entirely. Resolution order for every setting: built-in default → `--config` file
(when passed), OR built-in default → `config/ghostship.yaml` → XDG override
(when `--config` is not passed). Command-line flags (e.g. `--port`, `--public-url`)
take precedence over all config file layers. The system SHALL NOT treat an environment
variable exported in the invoking shell as a configuration input — the built-in
default applies when no config file or flag provides a value.

Before reading the config, install.sh SHALL check whether `config/ghostship.conf`
exists with no `config/ghostship.yaml`. If found, it SHALL auto-migrate the conf
file to YAML (see `yaml-config` capability) and print a migration notice.

#### Scenario: Config file sets defaults, no flags override
- **WHEN** `install.sh` runs with `--config ./my.yaml` and `my.yaml` sets `network.port: 9000`
- **AND** no `--port` flag is passed
- **THEN** the transport SHALL use port `9000`

#### Scenario: Command-line flag overrides config file
- **WHEN** `install.sh` runs with `--config ./my.yaml --port 8000` and `my.yaml` sets `network.port: 9000`
- **THEN** the transport SHALL use port `8000` (flag wins)

#### Scenario: Config file sets identity provider
- **WHEN** install.sh runs with `--config ./my.yaml` and `my.yaml` sets `backends.kiro.identity_provider` and `backends.kiro.region`
- **AND** no `--identity-provider` or `--region` flags are passed
- **THEN** the transport SHALL use the config file values for identity provider and region

#### Scenario: Missing config file
- **WHEN** `install.sh` runs with `--config /nonexistent/path`
- **THEN** the script SHALL exit with a non-zero status and print an error indicating the file does not exist or is not readable

#### Scenario: Ambient environment variable ignored when unset elsewhere
- **WHEN** the invoking shell has `GA_MACHINE_NAME=from-env` exported, no `--config` file is passed, and no corresponding flag is passed
- **THEN** `install.sh` SHALL use the built-in default (`ghost-academy`), not the ambient value `from-env`

### Requirement: Config file format documentation
`docs/configuration.md` SHALL document the YAML config file format, the three-layer
merge resolution order (built-in defaults → repo config → XDG override, or built-in
defaults → `--config`), all supported YAML keys organised by section, and the
location of both the repo-level and XDG override files. It SHALL document that config
files are override files — operators only specify keys they want to change. It SHALL
state the migration path from `ghostship.conf` and that `ghostship.conf` is no longer
read. The model precedence chain SHALL be documented:
`dispatch(model=...)` > `model.override` > per-agent model field > `model.default` > KiroCrew built-in.

#### Scenario: Config file section present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it contains a section explaining the YAML format, all supported keys, and the three-layer resolution order

#### Scenario: Migration path documented
- **WHEN** reading `docs/configuration.md`
- **THEN** it describes the auto-migration from `ghostship.conf` to `ghostship.yaml` and states that `ghostship.conf` is no longer read

#### Scenario: No ambient environment variable tier documented
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL NOT describe exporting a shell variable as a supported configuration method

### Requirement: Config fields match ghostship.yaml.example
Every field in the `Config` dataclass SHALL have a corresponding commented-out entry
in `config/ghostship.yaml.example`, and vice versa. A CI test SHALL assert this
invariant. `config/ghostship.conf.example` is retired.

#### Scenario: CI sync check passes
- **WHEN** `Config` fields and `ghostship.yaml.example` entries are in sync
- **THEN** the CI test passes

#### Scenario: CI sync check fails on drift
- **WHEN** a field is added to `Config` without a matching entry in `ghostship.yaml.example`
- **THEN** the CI test fails and identifies the missing entry

## REMOVED Requirements

### Requirement: Config file format documentation (shell format)
**Reason**: Replaced by YAML format. The shell-sourced `ghostship.conf` format and
its documentation are superseded by the YAML config system.
**Migration**: Operators run `./install.sh` which auto-migrates `ghostship.conf` to
`ghostship.yaml`. The `docs/configuration.md` config file section is rewritten for
the YAML format.

### Requirement: Config fields match ghostship.conf.example
**Reason**: `ghostship.conf.example` is retired and replaced by `ghostship.yaml.example`.
**Migration**: The CI sync test is updated to check `ghostship.yaml.example` instead.
