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
The YAML config SHALL be organised into logical top-level sections: `network`, `crew`,
`model`, `backends`, `portal`, `machine`. Each section groups related keys into
sub-sections where semantically appropriate. Per-backend config lives under
`backends.<backend>`. The `images` section is merged into `machine.images`.

The canonical section structure is:

```
network:
  host, port, host_url, api_key
  tls:
    certfile, keyfile

crew:
  max_crews, max_active, idle_timeout_secs, subagent_timeout_secs
  batch_max_tasks, pickup_max_poll_secs, orders_dir
  git:
    author:
      name, email
  memory:
    min_free_mem_gb, spawn_min_memory_gb, resource_pressure_gb
    resource_critical_gb, spawn_pressure_escalate_cycles

model:
  default              # global fallback only — no global override

backends:
  default: [list]      # first entry is runtime default
  kiro:
    model:
      override: ""     # forces all kiro agents to this model
      default: ""      # kiro fallback when no per-agent model set
    identity_center:
      url, region
  claude:
    model:
      override: ""
      default: ""
    base_url
  codex:
    model:
      override: ""
      default: ""
    base_url

portal:
  tls_mode, domain, session_ttl_secs
  dashboard:
    default
    port_range:
      start, size
  rate_limit:
    enabled, login_get, login_post, mcp, files, crew_api, dashboard_auth

machine:
  dedicated, name
  resources:
    cpus, memory_mb, disk_gb
  images:              # was top-level images: section
    podman_socket, kc_image, kc_base_image
```

`backends.default` SHALL accept either a YAML list (canonical) or a comma-separated
string (deprecated, accepted for backwards compatibility). `yaml_config.py` normalises
either form to a comma-separated string for `GA_CREW_AGENT`.

#### Scenario: Full config structure accepted
- **WHEN** `config/ghostship.yaml` contains all sections with valid values
- **THEN** install.sh SHALL parse and apply all values without error

#### Scenario: Unknown keys warned
- **WHEN** `config/ghostship.yaml` contains an unrecognised key
- **THEN** install.sh SHALL warn the operator and continue (not abort)

#### Scenario: backends.default as list
- **WHEN** `config/ghostship.yaml` sets `backends.default: [kiro, claude]`
- **THEN** `GA_CREW_AGENT` SHALL be set to `kiro,claude`

#### Scenario: backends.default as string (backwards compat)
- **WHEN** `config/ghostship.yaml` sets `backends.default: "kiro,claude"`
- **THEN** `GA_CREW_AGENT` SHALL be set to `kiro,claude` and a deprecation warning is printed

### Requirement: Per-backend model control
Each backend SHALL support two model knobs under `backends.<b>.model`:

- `override` — forces all agents running on this backend to use the specified model,
  regardless of per-agent persona config. Use when a backend only supports certain
  models (e.g. kiro-cli's available model set).
- `default` — fallback model for agents on this backend that have no per-agent model
  set. More specific than the global `model.default`.

The global `model.override` key SHALL NOT exist. A global override is a footgun
because no single model is accessible across all backends (kiro, claude, and codex
use different model namespaces). Per-backend overrides provide the same capability
without the cross-backend breakage risk.

The full model precedence chain (highest to lowest) SHALL be:

```
dispatch(model=...)            # caller-supplied, highest precedence
backends.<b>.model.override    # per-backend lock
per-agent model                # persona file
backends.<b>.model.default     # per-backend fallback
model.default                  # global fallback
built-in default               # KiroCrew's own default
```

This chain SHALL be documented in `docs/configuration.md` with an explanation of
when to use each level.

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
configurable field with its default value shown as live YAML (not commented out).
It SHALL never be parsed programmatically — it is documentation only.

#### Scenario: Example file is complete
- **WHEN** a new field is added to the Config dataclass
- **THEN** a corresponding entry SHALL exist in `config/ghostship.yaml.example`

#### Scenario: CI sync check
- **WHEN** Config fields and `ghostship.yaml.example` entries are in sync
- **THEN** the existing CI sync test passes

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
