# Spec Delta

## ADDED Requirements

### Requirement: Interactive guided setup when no ghostship.conf exists
When `install.sh` is run and no `ghostship.conf` exists in the current directory (or `--setup` flag is passed), the installer SHALL enter an interactive guided setup mode. The existing non-interactive path SHALL be unchanged when a `ghostship.conf` is present.

#### Scenario: Interactive mode triggered on first install
- **WHEN** `install.sh` is run and no `ghostship.conf` is found
- **THEN** the installer enters interactive guided setup and prompts the operator for configuration before building

#### Scenario: Non-interactive path unchanged when conf exists
- **WHEN** `install.sh` is run and a `ghostship.conf` exists
- **THEN** the installer proceeds non-interactively as before, without any prompts

### Requirement: Interactive setup collects backend and credentials
The interactive setup SHALL prompt the operator to choose an agent backend (`kiro` default, `claude`, `codex`), then collect the required credentials for that backend (`KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` for kiro; `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` for claude; `OPENAI_API_KEY` for codex). Collected values SHALL be written to a new `ghostship.conf` before the build proceeds.

#### Scenario: Selecting kiro backend prompts for identity provider
- **WHEN** the operator selects `kiro` as the backend
- **THEN** the installer prompts for `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` and writes them to `ghostship.conf`

#### Scenario: Selecting claude backend prompts for token or API key
- **WHEN** the operator selects `claude` as the backend
- **THEN** the installer prompts for `CLAUDE_CODE_OAUTH_TOKEN` (preferred) or `ANTHROPIC_API_KEY` and writes the chosen credential to `ghostship.conf`

### Requirement: Interactive setup runs login flow after transport starts
After the transport is started successfully, the interactive setup SHALL automatically trigger the login flow for the selected backend and display the login URL or device code to the operator. The installer SHALL wait for login completion before exiting, so the operator finishes the install already authenticated.

#### Scenario: Login flow triggered automatically after install
- **WHEN** interactive setup completes the build and starts the transport
- **THEN** the appropriate login flow is started automatically and the operator is shown the login URL or device code without a separate manual step

### Requirement: Interactive setup offers harness registration
After login completes, the interactive setup SHALL offer to run `ghostship setup` to register the MCP server with detected harnesses (kiro-cli, Claude Code, opencode). The operator can accept or skip.

#### Scenario: Harness registration is optional
- **WHEN** the operator declines harness registration during interactive setup
- **THEN** the install completes normally without running `ghostship setup`
