# Spec Delta

## MODIFIED Requirements

### Requirement: File-based transport auth persistence
The installation SHALL persist backend credentials only as plain files under `DATA_DIR`, mode `0600`, written by the transport's credential store. They SHALL NOT be stored as Podman secrets. No dedicated bind mount, migration step, or file-driver access is needed: `DATA_DIR` is already bind-mounted read/write into the transport container as `/data`, so the transport reads and writes the files directly.

#### Scenario: Install with no existing auth file
- **WHEN** installation runs before any backend credential exists
- **THEN** the transport starts with an empty credential store, and `ghostship auth login <backend>` remains available to populate it

#### Scenario: Install with an existing auth file
- **WHEN** installation runs and `DATA_DIR` already holds backend credentials from a previous install
- **THEN** the transport reads them directly via the existing `/data` mount, and the installer neither reads nor modifies them

#### Scenario: Ordinary uninstall preserves reusable auth
- **WHEN** uninstall runs without `--purge-auth`
- **THEN** transport state other than the backend credential files (kiro, claude and codex) is removed while those files are retained

#### Scenario: Ordinary uninstall on Linux preserves reusable auth even without --keep-machine
- **WHEN** `uninstall.sh` runs on Linux without `--purge-auth` and without `--keep-machine`
- **THEN** the backend credential files are retained; only the dedicated instance's `containers/` storage root is removed during machine teardown, not the entire `~/.local/share/${GA_MACHINE_NAME}` tree

#### Scenario: Purge uninstall removes reusable auth
- **WHEN** uninstall runs with `--purge-auth`
- **THEN** every backend credential file is also removed

#### Scenario: Uninstall removes obsolete credential secrets
- **WHEN** uninstall runs and obsolete backend credential Podman secrets (`ga-crew-anthropic-api-key`, `ga-claude-code-oauth-token`, `ga-crew-openai-api-key`, `ga-kiro-api-key`) exist
- **THEN** those secrets are removed

### Requirement: Model backend settings use their standard names

`install.sh` SHALL read the non-secret model backend settings under the names the Claude and Codex CLIs use: `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`. Each SHALL be reset to empty before `ghostship.conf` is sourced, so a value exported in the invoking shell is never used.

#### Scenario: Standard names configure the backends
- **WHEN** `ghostship.conf` sets `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`
- **THEN** `install.sh` passes them to the transport and prints no deprecation warning

#### Scenario: Shell values ignored
- **WHEN** `OPENAI_BASE_URL` is exported in the shell running `install.sh` and not set in `ghostship.conf`
- **THEN** the transport receives no `OPENAI_BASE_URL`

### Requirement: Pre-TRN-226 model backend names accepted as deprecated aliases

`install.sh` SHALL accept `GA_CREW_ANTHROPIC_BASE_URL` and `GA_CREW_OPENAI_BASE_URL` from `ghostship.conf` as aliases for the standard names. Each alias in use SHALL print a warning naming the old and new setting, never the value. When both names are set, the standard name SHALL win.

#### Scenario: Old name mapped with a warning
- **WHEN** `ghostship.conf` sets only `GA_CREW_OPENAI_BASE_URL`
- **THEN** `install.sh` uses its value as `OPENAI_BASE_URL` and warns that `GA_CREW_OPENAI_BASE_URL` is deprecated

#### Scenario: Standard name wins
- **WHEN** `ghostship.conf` sets both `OPENAI_BASE_URL` and `GA_CREW_OPENAI_BASE_URL`
- **THEN** `install.sh` uses `OPENAI_BASE_URL` and warns that the old name is ignored

### Requirement: Interactive setup collects backend and non-secret config
The interactive setup SHALL prompt the operator to choose a default agent backend (`kiro` default, `claude`, `codex`) and optional additional backends, then collect only the non-secret config for the selected backends (`KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` for kiro; nothing for claude; `OPENAI_BASE_URL` for codex). Collected values SHALL be written to a new `ghostship.conf` (mode `600`, non-empty vars only, no secrets) before the build proceeds. All credentials SHALL be left to `ghostship auth login <backend>`.

#### Scenario: Selecting kiro backend prompts for identity provider
- **WHEN** the operator selects `kiro` as the backend
- **THEN** the installer prompts for `KIRO_IDENTITY_PROVIDER` and (when a provider is given) `KIRO_REGION` and writes them to `ghostship.conf`

#### Scenario: Selecting claude backend collects no secret config
- **WHEN** the operator selects `claude` as a backend
- **THEN** the installer collects no config and does not print a `ghostship auth login anthropic` hint (the post-start login offer covers it)

#### Scenario: Multiple backends enabled simultaneously
- **WHEN** the operator selects `kiro` as default and adds `claude,codex`
- **THEN** `GA_CREW_AGENT=kiro,claude,codex` is written to `ghostship.conf` with `kiro` as the runtime default

### Requirement: Interactive setup runs login flow after transport starts
After the transport starts successfully, the interactive setup SHALL offer, for each enabled backend with no stored credential, to run `ghostship auth login <backend>`. Accepting SHALL run that command in the foreground against the just-installed transport (including its port and bearer key). Declining SHALL print the command to run later. The install SHALL succeed either way.

#### Scenario: Login flow triggered automatically after install
- **WHEN** interactive setup starts the transport with `GA_CREW_AGENT=kiro,claude` and neither backend holds a credential
- **THEN** the operator is offered `ghostship auth login kiro` and then `ghostship auth login claude`

#### Scenario: Login on a keyed install
- **WHEN** the transport was installed with a bearer key and the operator accepts the login offer
- **THEN** the login request carries that key and succeeds

#### Scenario: Backend already authenticated
- **WHEN** a backend already holds a stored credential
- **THEN** no login is offered for it

## ADDED Requirements

### Requirement: Installer never handles backend credentials
`install.sh` SHALL NOT read, create, remove or mount any backend credential: no `ga-crew-anthropic-api-key`, `ga-claude-code-oauth-token`, `ga-crew-openai-api-key` or `ga-kiro-api-key` secret operations, and no such secrets in the generated `compose.yml`. Re-running install, with or without `--wizard`, SHALL leave stored credentials unchanged.

#### Scenario: Re-install keeps credentials
- **WHEN** claude holds a stored setup-token and `install.sh --wizard` is run
- **THEN** claude's stored credential is unchanged after install

#### Scenario: Compose has no credential secrets
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** it references none of the backend credential secrets

### Requirement: Credential settings in ghostship.conf are ignored with a warning
When `ghostship.conf` sets `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`, `KIRO_API_KEY`, `GA_CREW_ANTHROPIC_API_KEY` or `GA_CREW_OPENAI_API_KEY`, `install.sh` SHALL warn naming the setting and the `ghostship auth login <backend>` command that replaces it, never the value, and SHALL otherwise ignore it.

#### Scenario: Leftover token in conf
- **WHEN** `ghostship.conf` sets `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** install warns that it is ignored and to use `ghostship auth login claude`, and creates no secret

## REMOVED Requirements

### Requirement: install.sh creates Podman secrets for crew API keys
**Reason**: Backend credentials are owned by the transport's credential store and supplied through `ghostship auth login <backend>`; the installer does configuration only.
**Migration**: None (breaking). After upgrading, re-enter credentials with `ghostship auth login <backend>`; old secrets are ignored.
