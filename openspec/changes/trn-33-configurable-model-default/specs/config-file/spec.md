## MODIFIED Requirements

### Requirement: Config file sourcing with correct precedence
The system SHALL accept a `--config <path>` flag pointing to a shell file that exports configuration variables. The config file SHALL be sourced BEFORE other flags are processed, so that command-line flags take precedence over values from the config file. Resolution order: config file → command-line flags → defaults.

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
- **WHEN** a config file exports any combination of: `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`, `PORT`, `KC_MODEL_OVERRIDE`, `KC_MODEL_DEFAULT`, `GA_API_KEY`, `GA_FILE_PUBLIC_URL`, `GA_MCP_PUBLIC_URL`
- **THEN** each exported variable SHALL act as a default, overridable by its corresponding flag
