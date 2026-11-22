# Spec Delta

## ADDED Requirements

### Requirement: Podman provisioning configuration has regression coverage
The installation test suite SHALL verify that Podman setup receives the effective dedicated-machine settings resolved from the selected YAML configuration.

#### Scenario: Repository configuration is used for provisioning
- **WHEN** installation tests provide repository YAML with non-default machine settings
- **THEN** the setup invocation uses the configured machine name and resource limits

#### Scenario: Explicit config precedence is preserved during provisioning
- **WHEN** repository, XDG, and explicit config files contain different machine settings
- **THEN** tests verify that provisioning uses only the explicit config layer over built-in defaults

#### Scenario: XDG config is used when repository config omits a machine setting
- **WHEN** repository YAML omits a machine setting and XDG YAML provides it
- **THEN** tests verify that the XDG value is used for Podman provisioning

#### Scenario: Ambient variables do not affect provisioning
- **WHEN** machine-related environment variables conflict with the selected YAML config
- **THEN** tests verify that the YAML values determine the Podman setup inputs

#### Scenario: Setup outputs match generated service configuration
- **WHEN** installation provisions a machine from resolved YAML values
- **THEN** tests verify the selected machine, socket, data directory, and generated Compose settings refer to the same instance
