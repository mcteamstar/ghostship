# Spec Delta

## Purpose

Defines the structured YAML configuration file format for ghostship, replacing the
flat shell-sourced `ghostship.conf` with a layered, deep-mergeable YAML config system.

## ADDED Requirements

### Requirement: YAML config file format
The system SHALL accept `config/ghostship.yaml` in the ghostship repo directory as the
operator's primary configuration file. The file SHALL be YAML. All keys are optional —
operators only specify keys they want to change from built-in defaults.

#### Scenario: Minimal config file
- **WHEN** `config/ghostship.yaml` contains only `crew:\n  max_active: 6`
- **THEN** install.sh SHALL use `max_active: 6` and all other settings SHALL use built-in defaults

#### Scenario: Missing config file
- **WHEN** no `config/ghostship.yaml` exists and no `--config` flag is passed
- **THEN** install.sh SHALL proceed using built-in defaults only

### Requirement: YAML config schema with logical sections
The YAML config SHALL be organised into logical sections: `network`, `crew`, `model`,
`backends`, `portal`, `machine`. Each section contains related keys. Per-backend config
lives under `backends.<backend>` (e.g. `backends.kiro.identity_provider`).

#### Scenario: Full config structure accepted
- **WHEN** `config/ghostship.yaml` contains all sections with valid values
- **THEN** install.sh SHALL parse and apply all values without error

#### Scenario: Unknown keys warned
- **WHEN** `config/ghostship.yaml` contains an unrecognised key
- **THEN** install.sh SHALL warn the operator and continue (not abort)

### Requirement: Three-layer deep merge
Config is resolved by deep-merging three layers in order: (1) built-in defaults,
(2) repo-level `config/ghostship.yaml`, (3) XDG override
`~/.config/ghost-academy/ghostship.yaml`. Later layers override earlier ones at the
individual key level. Unspecified keys fall through to the layer below.

#### Scenario: XDG overrides repo key
- **WHEN** `config/ghostship.yaml` sets `crew.max_active: 3` and `~/.config/ghost-academy/ghostship.yaml` sets `crew.max_active: 6`
- **THEN** the effective `max_active` SHALL be `6`

#### Scenario: XDG partial override preserves other repo keys
- **WHEN** `config/ghostship.yaml` sets `crew.max_active: 3` and `crew.idle_timeout_secs: 600` and `~/.config/ghost-academy/ghostship.yaml` sets only `crew.max_active: 6`
- **THEN** `idle_timeout_secs` SHALL remain `600` (from repo layer)

#### Scenario: No XDG file — repo layer applies
- **WHEN** `~/.config/ghost-academy/ghostship.yaml` does not exist
- **THEN** only the repo-level config and built-in defaults are used

### Requirement: XDG override file location
The XDG override config file SHALL be resolved from
`$XDG_CONFIG_HOME/ghost-academy/ghostship.yaml` on Linux (defaulting to
`~/.config/ghost-academy/ghostship.yaml` when `XDG_CONFIG_HOME` is unset) and
`~/Library/Application Support/ghost-academy/ghostship.yaml` on macOS.

#### Scenario: Linux XDG_CONFIG_HOME set
- **WHEN** `XDG_CONFIG_HOME=/custom/config` is set on Linux
- **THEN** the XDG override is read from `/custom/config/ghost-academy/ghostship.yaml`

#### Scenario: Linux XDG_CONFIG_HOME unset
- **WHEN** `XDG_CONFIG_HOME` is not set on Linux
- **THEN** the XDG override is read from `~/.config/ghost-academy/ghostship.yaml`

### Requirement: --config flag replaces implicit file resolution
When `--config <path>` is passed to install.sh, it replaces layers 2 and 3 of the
merge entirely. The specified file deep-merges on top of built-in defaults only.
No XDG override is applied when `--config` is used.

#### Scenario: --config skips repo and XDG layers
- **WHEN** `--config /path/to/custom.yaml` is passed and both `config/ghostship.yaml` and the XDG file exist
- **THEN** only `/path/to/custom.yaml` is merged on top of built-in defaults; repo and XDG files are ignored

#### Scenario: --config partial file inherits defaults
- **WHEN** `--config custom.yaml` sets only `network.port: 9000`
- **THEN** all other settings use built-in defaults, not the repo or XDG config

### Requirement: ghostship.yaml.example documents all configurable fields
`config/ghostship.yaml.example` SHALL be committed to the repo and contain every
configurable field, commented out, with its default value shown. It SHALL never be
parsed programmatically — it is documentation only.

#### Scenario: Example file is complete
- **WHEN** a new field is added to the Config dataclass
- **THEN** a corresponding commented-out entry SHALL exist in `config/ghostship.yaml.example`

#### Scenario: CI sync check
- **WHEN** Config fields and `ghostship.yaml.example` entries are in sync
- **THEN** the existing CI sync test passes (updated to check YAML example)

### Requirement: Auto-migration from ghostship.conf
When install.sh detects `config/ghostship.conf` with no `config/ghostship.yaml`, it
SHALL automatically convert the conf file to YAML, write `config/ghostship.yaml`, and
rename the old file to `config/ghostship.conf.bak`.

#### Scenario: Auto-migration on upgrade
- **WHEN** `config/ghostship.conf` exists and `config/ghostship.yaml` does not
- **THEN** install.sh converts and writes `config/ghostship.yaml`, renames old file to `config/ghostship.conf.bak`, and prints a migration notice

#### Scenario: No migration when YAML already exists
- **WHEN** both `config/ghostship.conf` and `config/ghostship.yaml` exist
- **THEN** install.sh uses `config/ghostship.yaml` and does not modify `config/ghostship.conf`

### Requirement: Config files are operator-owned and never written back
ghostship SHALL treat all config files (repo, XDG, --config) as read-only. Runtime
state (credentials, registry, compose.yml) is stored separately on the data volume.
install.sh MAY generate a new `config/ghostship.yaml` via the wizard (writing from an
internal template), but SHALL NOT modify an existing config file after initial creation.

#### Scenario: Repeated installs do not overwrite operator config
- **WHEN** install.sh is run multiple times with an existing `config/ghostship.yaml`
- **THEN** `config/ghostship.yaml` is not modified

#### Scenario: Runtime state stays on data volume
- **WHEN** a kiro device flow completes and a credential is stored
- **THEN** the credential is written to `DATA_DIR/credentials/`, not to any config file
