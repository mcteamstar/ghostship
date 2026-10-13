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

### Requirement: Interactive setup collects backend and non-secret config
The interactive setup SHALL prompt the operator to choose a default agent backend (`kiro` default, `claude`, `codex`) and optional additional backends, then collect only the non-secret config for the selected backends (`KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` for kiro; nothing for claude; `OPENAI_BASE_URL` for codex). Collected values SHALL be written to a new `ghostship.conf` (mode `600`, non-empty vars only, no secrets) before the build proceeds. Secret injection (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`) SHALL be deferred to `ghostship auth login <backend>`.

#### Scenario: Selecting kiro backend prompts for identity provider
- **WHEN** the operator selects `kiro` as the backend
- **THEN** the installer prompts for `KIRO_IDENTITY_PROVIDER` and (when a provider is given) `KIRO_REGION` and writes them to `ghostship.conf`

#### Scenario: Selecting claude backend collects no secret config
- **WHEN** the operator selects `claude` as a backend
- **THEN** the installer collects no config and instructs the operator to run `ghostship auth login anthropic` after install

#### Scenario: Multiple backends enabled simultaneously
- **WHEN** the operator selects `kiro` as default and adds `claude,codex`
- **THEN** `GA_CREW_AGENT=kiro,claude,codex` is written to `ghostship.conf` with `kiro` as the runtime default

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

## Interactive Setup Mode

### Trigger

Interactive guided setup runs when **either**:
- no `ghostship.conf` is found (neither `ghostship.conf` nor `config/ghostship.conf`) **and** stdin is a tty (`-t 0`); or
- the `--wizard` flag is passed (regardless of whether a config exists).

Otherwise the installer runs the existing non-interactive path unchanged.

### The seven steps

1. **Default backend** — prompt for `kiro`/`claude`/`codex` (default `kiro`); validate against the known set and re-prompt on an unknown value.
2. **Additional backends** — prompt for a comma-separated list (blank = none); validate each and append to `GA_CREW_AGENT` so all selected backends are enabled.
3. **Non-secret config per backend** — kiro: optional `KIRO_IDENTITY_PROVIDER` and, if set, `KIRO_REGION`; claude: none (printed note to run `ghostship auth login anthropic`); codex: optional `OPENAI_BASE_URL` (blank = OpenAI; may point at a local proxy such as litellm) plus a printed note to run `ghostship auth login openai`.
4. **Write `ghostship.conf`** — `${GHOSTSHIP_DIR}/config/ghostship.conf`, mode `600`, containing only the non-empty non-secret vars and a generation header. This file is sourced by the auto-detect loop on every subsequent `./install.sh`.
5. **Build & start** — the collected `GA_CREW_AGENT` feeds the existing `agent_backends_normalise` call and the normal build/transport-start path, unchanged.
6. **Authentication** — after `✓ Transport is ready`, kiro triggers `ghostship auth login` (device flow); claude and codex print the follow-up `ghostship auth login <backend>` command.
7. **Harness registration** — prompt (default `y`) to run `ghostship setup`, registering the MCP server with detected harnesses (kiro-cli, Claude Code, opencode). Declining skips it; the install still completes.

### Multi-backend topology

`GA_CREW_AGENT` is comma-separated and the transport holds config for all listed backends simultaneously (e.g. `GA_CREW_AGENT=kiro,claude,codex`). The **first** entry is the runtime default. The interactive installer surfaces this: a default backend plus any additional backends are enabled in one install.

### Invariants

- The non-interactive path (config present, no `--wizard`) is **unchanged** — no new prompts, no behavior change.
- No secrets are collected or written during interactive setup. Secret injection is deferred to `ghostship auth login <backend>`.
