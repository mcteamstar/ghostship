# Spec Delta

## ADDED Requirements

### Requirement: Podman provisioning uses resolved installation configuration
Before provisioning or selecting the dedicated Podman instance, installation SHALL resolve and use the effective YAML values for dedicated-machine selection, machine name, and resource limits.

#### Scenario: Repository YAML controls first-time machine provisioning
- **WHEN** the repository YAML configures a dedicated machine name and resource limits that differ from defaults
- **THEN** first-time provisioning uses those configured values before the transport starts

#### Scenario: Explicit config controls Podman provisioning
- **WHEN** install is invoked with `--config` and that file sets dedicated-machine values
- **THEN** Podman provisioning uses those values and ignores repository and XDG config layers for those settings

#### Scenario: XDG config controls Podman provisioning
- **WHEN** repository YAML does not set a dedicated-machine value and the XDG override does
- **THEN** Podman provisioning uses the XDG value

#### Scenario: Ambient machine variables do not override YAML
- **WHEN** machine-related shell variables differ from the resolved YAML values
- **THEN** provisioning uses the resolved YAML values

#### Scenario: Provisioned paths match the selected machine
- **WHEN** installation resolves a dedicated-machine name from YAML
- **THEN** the selected Podman service, socket, data directory, and generated Compose configuration refer to that same machine
