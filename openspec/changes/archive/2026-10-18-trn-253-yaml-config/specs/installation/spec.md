# Spec Delta

## MODIFIED Requirements

### Requirement: Config file resolution
The system SHALL resolve configuration by deep-merging three layers in order: built-in
defaults, then `config/ghostship.yaml` in the ghostship directory (if present), then
the XDG override file (if present). When `--config <path>` is passed, it replaces
layers 2 and 3 entirely. The system SHALL resolve `KIRO_IDENTITY_PROVIDER`,
`KIRO_REGION`, and `KIRO_LICENSE` from the merged config under `backends.kiro.*`
before falling back to individual CLI flags, then an interactive prompt if still
unset and running in a terminal.

#### Scenario: Repo config sets identity provider
- **WHEN** `config/ghostship.yaml` sets `backends.kiro.identity_provider` and `backends.kiro.region`
- **AND** no `--identity-provider` flag is passed
- **THEN** install.sh uses the config values

#### Scenario: XDG override sets identity provider
- **WHEN** the XDG override file sets `backends.kiro.identity_provider`
- **AND** `config/ghostship.yaml` does not set it
- **THEN** install.sh uses the XDG value

#### Scenario: --config flag replaces implicit resolution
- **WHEN** `--config /path/to/custom.yaml` is passed
- **THEN** only that file and built-in defaults are used; repo and XDG files are ignored

### Requirement: Auto-migration from ghostship.conf on install
When install.sh finds `config/ghostship.conf` with no `config/ghostship.yaml`, it
SHALL automatically convert the conf to YAML, write `config/ghostship.yaml`, rename
the old file to `config/ghostship.conf.bak`, and print a clear migration notice
before proceeding with the install.

#### Scenario: Auto-migration runs on upgrade
- **WHEN** `config/ghostship.conf` exists and `config/ghostship.yaml` does not
- **THEN** install.sh prints a migration notice, writes `config/ghostship.yaml`, and renames `config/ghostship.conf` to `config/ghostship.conf.bak`

#### Scenario: Install proceeds after migration
- **WHEN** auto-migration completes
- **THEN** install.sh continues with the migrated `config/ghostship.yaml` and completes normally

### Requirement: Wizard generates ghostship.yaml
The install wizard (run on first install or with `--wizard`) SHALL generate
`config/ghostship.yaml` with operator-supplied values and inline comments from an
internal template. It SHALL NOT generate `ghostship.conf`.

#### Scenario: Wizard writes YAML config
- **WHEN** the wizard completes
- **THEN** `config/ghostship.yaml` exists with the operator's choices and all other keys commented out at their defaults

#### Scenario: Wizard does not overwrite existing config
- **WHEN** `config/ghostship.yaml` already exists and `--wizard` is passed
- **THEN** the wizard prompts before overwriting (existing behaviour preserved)

## REMOVED Requirements

### Requirement: Config file sourcing (shell format)
**Reason**: install.sh no longer sources `ghostship.conf` as a shell file. The
`--config` flag now accepts a YAML file.
**Migration**: Auto-migration from `ghostship.conf` is provided. Operators running
`./install.sh` on an existing install will have their conf converted automatically.
