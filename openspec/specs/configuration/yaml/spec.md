# YAML Config Specification

## Purpose

Defines the structured YAML configuration file format for ghostship, replacing the
flat shell-sourced `ghostship.conf` with a layered, deep-mergeable YAML config system.

## Requirements

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
The YAML config SHALL be organised into logical top-level sections. Configuration
under optional `backends.claude` or `backends.codex` SHALL also declare that backend
enabled for toolchain installation. Kiro SHALL remain a built-in enabled backend.
`backends.default` SHALL be a scalar backend name selecting the implicit runtime
backend, defaulting to Kiro when omitted; it SHALL not be a list of enabled backends.

#### Scenario: Full config structure accepted
- **WHEN** `config/ghostship.yaml` contains all sections with valid values
- **THEN** install.sh SHALL parse and apply all values without error

#### Scenario: Unknown keys warned
- **WHEN** `config/ghostship.yaml` contains an unrecognised key
- **THEN** install.sh SHALL warn the operator and continue without aborting

#### Scenario: backends.default as scalar
- **WHEN** `config/ghostship.yaml` sets `backends.default: claude` and contains `backends.claude: {}`
- **THEN** `GA_CREW_AGENT` SHALL be derived as `claude,kiro`

#### Scenario: Missing default uses Kiro
- **WHEN** `config/ghostship.yaml` omits `backends.default`
- **THEN** Kiro SHALL be the implicit runtime backend

#### Scenario: Legacy list is rejected
- **WHEN** `config/ghostship.yaml` sets `backends.default: [kiro, claude]`
- **THEN** install.sh SHALL fail with migration guidance

### Requirement: Per-backend model control
Each `backends.<b>.model` SHALL support `override` (force that backend's model) and `default` (fallback when persona model is unset); global `model.override` SHALL NOT exist. Precedence SHALL be dispatch override, backend override, persona model, backend default, global default, then built-in. `docs/configuration.md` SHALL explain each level's use.

#### Scenario: Per-backend override beats per-agent model
- **WHEN** `backends.kiro.model.override: "claude-sonnet-4-5"` is set and a kiro agent persona specifies a different model
- **THEN** the kiro crew uses `claude-sonnet-4-5` regardless of the agent's persona config

#### Scenario: Per-backend default loses to per-agent model
- **WHEN** `backends.kiro.model.default: "qwen-dense"` is set and a kiro agent persona specifies `gpt-5.6-luna`
- **THEN** the agent uses `gpt-5.6-luna` (per-agent wins over backend default)

#### Scenario: Per-backend default beats global default
- **WHEN** `backends.kiro.model.default: "qwen-dense"` is set and `model.default: "gemma"` is set
- **THEN** kiro agents with no per-agent model use `qwen-dense`, not `gemma`

#### Scenario: Global default is the final fallback
- **WHEN** `model.default: "gemma"` is set and no per-backend or per-agent model is configured
- **THEN** all agents on all backends use `gemma`

#### Scenario: Backends without a model override are unaffected
- **WHEN** `backends.kiro.model.override: "claude-sonnet-4-5"` is set
- **THEN** claude and codex crews are unaffected and use their own model resolution

### Requirement: Deprecated YAML paths mapped with a warning
When install.sh reads a `config/ghostship.yaml` that uses any of the old key paths
from before TRN-257, it SHALL warn the operator naming the old and new path and
continue using the value. It SHALL NOT silently ignore the old path.

#### Scenario: Migrate a supported deprecated path
- **WHEN** the installer reads a deprecated key from the table below
- **THEN** it applies the indicated mapping or removal.

The deprecated path mappings are:

| Old path | New path |
|:---------|:---------|
| `network.tls_certfile` | `network.tls.certfile` |
| `network.tls_keyfile` | `network.tls.keyfile` |
| `crew.git_author_name` | `crew.git.author.name` |
| `crew.git_author_email` | `crew.git.author.email` |
| `backends.agent` | `backends.default` |
| `backends.kiro.identity_provider` | `backends.kiro.identity_center.url` |
| `backends.kiro.region` | `backends.kiro.identity_center.region` |
| `portal.dashboard_port_range_start` | `portal.dashboard.port_range.start` |
| `portal.dashboard_port_range_size` | `portal.dashboard.port_range.size` |
| `portal.dashboard_default` | `portal.dashboard.default` |
| `machine.cpus` | `machine.resources.cpus` |
| `machine.memory` | `machine.resources.memory_mb` |
| `machine.disk` | `machine.resources.disk_gb` |
| `images.podman_socket` | `machine.images.podman_socket` |
| `images.kc_image` | `machine.images.kc_image` |
| `images.kc_base_image` | `machine.images.kc_base_image` |
| `model.override` | _(removed — warn and ignore)_ |

#### Scenario: Old YAML path warns and applies
- **WHEN** `config/ghostship.yaml` uses `crew.git_author_name: "Bot"`
- **THEN** install.sh warns that `crew.git_author_name` is deprecated in favour of `crew.git.author.name`, and applies the value

#### Scenario: Removed model.override warns and is ignored
- **WHEN** `config/ghostship.yaml` sets `model.override: "some-model"`
- **THEN** install.sh warns that `model.override` has been removed and the value is ignored, directing the operator to use `backends.<b>.model.override` instead

#### Scenario: New path takes precedence when both present
- **WHEN** `config/ghostship.yaml` sets both `backends.agent: "kiro"` and `backends.default: [kiro, claude]`
- **THEN** `backends.default` wins and no deprecation warning is printed for `backends.agent`

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

### Requirement: ghostship.yaml.example documents all configurable fields
`config/ghostship.yaml.example` SHALL be committed to the repo and contain every
configurable field with its default value shown as live YAML (not commented out).
It SHALL never be parsed programmatically — it is documentation only.

#### Scenario: Example file is complete
- **WHEN** a new field is added to the Config dataclass
- **THEN** a corresponding entry SHALL exist in `config/ghostship.yaml.example`

#### Scenario: CI sync check
- **WHEN** Config fields and `ghostship.yaml.example` entries are in sync
- **THEN** the existing CI sync test passes

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

### Requirement: network.api_key accepts a key or an explicit opt-out

`network.api_key` SHALL accept a non-empty string (enables bearer authentication with that key), or the YAML boolean `false` (explicit opt-out: no authentication, permitted on non-loopback installs). An absent key, `null` or empty string SHALL mean unset, never opt-out. Any other value, including `true` and the strings `"true"`/`"false"`, SHALL make `install.sh` exit non-zero naming `network.api_key`.

#### Scenario: String enables authentication
- **WHEN** `network.api_key: "s3cret"` is set
- **THEN** the transport requires `Authorization: Bearer s3cret`

#### Scenario: false is an explicit opt-out
- **WHEN** `network.api_key: false` is set and `network.host: 0.0.0.0`
- **THEN** the install proceeds unauthenticated with a WARNING rather than aborting

#### Scenario: Empty or null is unset, not opt-out
- **WHEN** `network.api_key:` (null) or `network.api_key: ""` is set and `network.host: 0.0.0.0`
- **THEN** the install aborts as for an unset key

#### Scenario: true is rejected
- **WHEN** `network.api_key: true` is set
- **THEN** `install.sh` exits non-zero with an error naming `network.api_key` and its accepted values

#### Scenario: Quoted "false" is rejected, not used as a key
- **WHEN** `network.api_key: "false"` (a string) is set
- **THEN** `install.sh` exits non-zero with an error naming `network.api_key`, rather than enabling authentication with the literal key `false`

### Requirement: network.require_api_key is deprecated and mapped

`network.require_api_key` (and `GA_REQUIRE_API_KEY` in a migrated `ghostship.conf`) SHALL be accepted with a deprecation warning naming `network.api_key`. The value `off` SHALL act as `network.api_key: false` only when no key is resolved from any source (flag, YAML, or persisted); otherwise the key SHALL win. The values `error` and `warn` SHALL be ignored, so an unset key on a non-loopback install aborts.

#### Scenario: off maps to the opt-out
- **WHEN** `network.require_api_key: off` is set and `network.api_key` is unset
- **THEN** `install.sh` warns that `require_api_key` is deprecated and behaves as `network.api_key: false`

#### Scenario: A key set alongside off wins
- **WHEN** `network.require_api_key: off` and `network.api_key: "s3cret"` are both set
- **THEN** `install.sh` warns that `require_api_key` is deprecated and ignored, and authentication is enabled with `s3cret`

#### Scenario: A persisted key set alongside off wins
- **WHEN** `network.require_api_key: off` is set, `network.api_key` is unset, `install.sh` runs without `--api-key`, and `DATA_DIR` holds a key persisted by an earlier `--api-key`
- **THEN** authentication stays enabled with the persisted key, and the deprecation warning is printed

#### Scenario: warn no longer lets an unset key through
- **WHEN** `network.require_api_key: warn` is set, `network.api_key` is unset, and `network.host: 0.0.0.0`
- **THEN** `install.sh` warns that `require_api_key` is deprecated and aborts as for an unset key

#### Scenario: Legacy conf value migrated
- **WHEN** a `ghostship.conf` containing `GA_REQUIRE_API_KEY=off` and no `GA_API_KEY` is auto-migrated
- **THEN** the generated YAML sets `network.api_key: false` and omits `require_api_key`

### Requirement: Configured model fallbacks reach the agent runtime
A nonempty backend model default SHALL be consumed by the crew runtime when no higher-precedence model applies. A global model default SHALL supply that fallback only when the crew backend has no model default. Resolution SHALL use the crew’s own backend and SHALL preserve dispatch, backend override and applicable persona precedence.

#### Scenario: Backend fallback reaches execution
- **WHEN** a backend has a supported model default and the selected persona has no explicit model
- **THEN** the crew runtime resolves that configured model rather than its harness-selected default

#### Scenario: Backend fallback beats global fallback at runtime
- **WHEN** distinct supported backend and global defaults are configured and no higher-precedence model applies
- **THEN** the crew runtime resolves the backend default

#### Scenario: Global fallback reaches execution
- **WHEN** a supported global default is configured and backend default and higher-precedence models are unset
- **THEN** the crew runtime resolves the global default

#### Scenario: Persona and dispatch retain precedence
- **WHEN** a supported persona pin or dispatch selection applies alongside a different configured fallback
- **THEN** the higher-precedence selection wins in the crew runtime

#### Scenario: Backend override retains precedence
- **WHEN** an explicit persona model is subject to a backend override and no dispatch model is supplied
- **THEN** runtime selection uses the backend override rather than a configured fallback

#### Scenario: Per-crew backend controls fallback
- **WHEN** a crew is launched on a backend different from the transport’s default backend
- **THEN** the model fallback comes from that crew’s backend settings

### Requirement: Backend model defaults avoid automatic routing
Shipped backend profiles SHALL provide concrete model defaults while leaving shipped
persona definitions unpinned. The harness `auto` fallback SHALL remain available when
an operator explicitly clears the relevant backend model default.

#### Scenario: Kiro backend default
- **WHEN** a Kiro crew has no higher-precedence model selection
- **THEN** Ghostship uses `claude-haiku-5.5` rather than automatic routing

#### Scenario: Claude backend default
- **WHEN** a Claude crew has no higher-precedence model selection
- **THEN** Ghostship uses `claude-haiku-5-5` rather than automatic routing

#### Scenario: Codex backend default
- **WHEN** a Codex crew has no higher-precedence model selection
- **THEN** Ghostship uses `gpt-6-luna` rather than automatic routing

#### Scenario: Explicitly cleared default delegates to harness
- **WHEN** an operator explicitly clears the selected backend's model default and no higher-precedence model applies
- **THEN** Ghostship SHALL supply `auto` rather than silently inserting a concrete model

#### Scenario: Explicit selection retains precedence
- **WHEN** a dispatch model or backend override is supplied
- **THEN** that explicit selection SHALL take precedence over the backend default

#### Scenario: Rejected pin is distinct from unset selection
- **WHEN** the runtime rejects a configured backend model
- **THEN** the resulting harness-selected model SHALL be reported as a rejected configured pin, not as the normal configured fallback

### Requirement: Reapplying generated model settings clears obsolete fallback state
Reapplying crew configuration SHALL remove obsolete generated model-fallback state and reflect the current resolved fallback. Clearing a previously configured fallback SHALL restore inheritance without retaining that earlier generated model. Operator YAML and stored credentials SHALL remain unchanged.

#### Scenario: Reapply corrects obsolete generated fallback
- **WHEN** an existing crew has obsolete generated fallback state and configuration is reapplied
- **THEN** the runtime consumes the currently configured fallback and the obsolete state is removed

#### Scenario: Clear configured fallback
- **WHEN** backend and global defaults are cleared after a generated fallback had been applied
- **THEN** the runtime no longer inherits the old generated model and returns to higher-precedence selections or harness selection

### Requirement: Shipped personas inherit backend model configuration
The six shipped persona files SHALL omit explicit model pins. Operator backend overrides SHALL apply to personas with no model or auto, while explicit dispatch selection retains higher priority. Persona prompts and tools SHALL remain unchanged.

#### Scenario: Unpinned shipped persona uses configured fallback
- **WHEN** a supported backend model default is configured and a shipped persona is dispatched without a model argument
- **THEN** the runtime resolves that configured fallback without a foreign persona pin

#### Scenario: Backend override applies to an unpinned persona
- **WHEN** an operator configures a backend model override and a persona has no model or uses auto
- **THEN** that persona uses the backend override unless dispatch explicitly selects a model

### Requirement: Backend default has scalar compatibility semantics
`backends.default` SHALL accept a scalar backend name. The legacy list form SHALL
not silently select multiple enabled backends; install.sh SHALL reject it with a
migration error or provide an explicit, documented migration to a scalar default
and backend sections.

#### Scenario: Scalar default accepted
- **WHEN** `backends.default: claude` is configured
- **THEN** the generated runtime configuration SHALL identify Claude as the implicit backend

#### Scenario: Legacy list rejected or migrated
- **WHEN** `backends.default: [claude, kiro]` is configured
- **THEN** install.sh SHALL either fail with an actionable migration message or convert it to `default: claude` while enabling the corresponding backend sections

### Requirement: Configuration resolution follows explicit precedence

Configuration SHALL deep-merge built-in defaults, repository YAML, and the platform override in that order. Explicit `--config` replaces the repository and platform override layers. CLI flags override merged values. Ambient shell variables SHALL NOT serve as configuration inputs. Installer prompts may supply missing values where interactive prompting is supported.

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

#### Scenario: Repo config sets identity provider
- **WHEN** `config/ghostship.yaml` sets `backends.kiro.identity_provider` and `backends.kiro.region`
- **AND** no `--identity-provider` flag is passed
- **THEN** install.sh uses the config values

#### Scenario: XDG override sets identity provider
- **WHEN** the XDG override file sets `backends.kiro.identity_provider`
- **AND** `config/ghostship.yaml` does not set it
- **THEN** install.sh uses the XDG value

#### Scenario: XDG overrides repo key
- **WHEN** `config/ghostship.yaml` sets `crew.max_active: 3` and `~/.config/ghost-academy/ghostship.yaml` sets `crew.max_active: 6`
- **THEN** the effective `max_active` SHALL be `6`

#### Scenario: XDG partial override preserves other repo keys
- **WHEN** `config/ghostship.yaml` sets `crew.max_active: 3` and `crew.idle_timeout_secs: 600` and `~/.config/ghost-academy/ghostship.yaml` sets only `crew.max_active: 6`
- **THEN** `idle_timeout_secs` SHALL remain `600` (from repo layer)

#### Scenario: No XDG file — repo layer applies
- **WHEN** `~/.config/ghost-academy/ghostship.yaml` does not exist
- **THEN** only the repo-level config and built-in defaults are used

#### Scenario: --config skips repo and XDG layers
- **WHEN** `--config /path/to/custom.yaml` is passed and both `config/ghostship.yaml` and the XDG file exist
- **THEN** only `/path/to/custom.yaml` is merged on top of built-in defaults; repo and XDG files are ignored

#### Scenario: --config partial file inherits defaults
- **WHEN** `--config custom.yaml` sets only `network.port: 9000`
- **THEN** all other settings use built-in defaults, not the repo or XDG config

### Requirement: Install migrates legacy config when YAML is absent

Before reading the repository configuration, install SHALL convert legacy `config/ghostship.conf` when its YAML counterpart is absent, write `config/ghostship.yaml`, save the original as `config/ghostship.conf.bak`, and print a migration notice. Existing YAML SHALL take precedence without modifying either file.

#### Scenario: Auto-migration on upgrade
- **WHEN** `config/ghostship.conf` exists and `config/ghostship.yaml` does not
- **THEN** install.sh converts and writes `config/ghostship.yaml`, renames old file to `config/ghostship.conf.bak`, and prints a migration notice

#### Scenario: No migration when YAML already exists
- **WHEN** both `config/ghostship.conf` and `config/ghostship.yaml` exist
- **THEN** install.sh uses `config/ghostship.yaml` and does not modify `config/ghostship.conf`

#### Scenario: Install proceeds after migration
- **WHEN** auto-migration completes
- **THEN** install.sh continues with the migrated `config/ghostship.yaml` and completes normally
