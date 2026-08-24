# Spec: Configuration and Documentation

## Purpose

Extend the configuration surface to support dedicated Podman machine settings and document the feature for operators.

## Requirements

### Requirement: New configuration variables in ghostship.conf

The config file format SHALL support dedicated-machine variables, sourced before flag parsing.

#### Scenario: All dedicated-machine variables in config
- **GIVEN** a config file containing `GA_DEDICATED_MACHINE=true`, `GA_MACHINE_CPUS=6`, `GA_MACHINE_MEMORY=12288`, `GA_MACHINE_DISK=100`, `GA_MACHINE_NAME=ghostship`
- **WHEN** `install.sh --config <path>` is run
- **THEN** all variables are available to the provisioning logic

#### Scenario: CLI flag overrides config variable
- **GIVEN** config sets `GA_MACHINE_NAME=ghostship`
- **AND** a future `--machine-name academy` CLI flag is passed
- **THEN** the effective machine name is `academy`

### Requirement: ghostship.conf.example updated

The example config file SHALL include commented-out dedicated-machine variables with documentation.

#### Scenario: Example file includes new section
- **WHEN** an operator reads `config/ghostship.conf.example`
- **THEN** they see a `── Dedicated Podman Machine ──` section with `GA_DEDICATED_MACHINE`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_MACHINE_NAME`

### Requirement: docs/configuration.md updated

The configuration reference SHALL document all new variables.

#### Scenario: Variable table extended
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_DEDICATED_MACHINE`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_MACHINE_NAME` in the variable table with descriptions and defaults

### Requirement: docs/architecture.md updated

The architecture doc SHALL mention the dedicated-machine option in the Components section.

#### Scenario: Architecture mentions isolation modes
- **WHEN** a developer reads `docs/architecture.md`
- **THEN** the "ga-transport" component description mentions that it can optionally use a dedicated Podman machine for isolation

### Requirement: docs/troubleshooting.md updated

Troubleshooting SHALL include common dedicated-machine issues.

#### Scenario: Troubleshooting covers dedicated machine
- **WHEN** an operator has issues with the dedicated machine
- **THEN** troubleshooting.md includes sections for: machine not starting, socket not found, storage space on dedicated root, and how to check which containers are on which instance
