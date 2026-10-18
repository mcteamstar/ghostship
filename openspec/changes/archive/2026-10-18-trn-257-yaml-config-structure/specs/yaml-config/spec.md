# Spec Delta

## MODIFIED Requirements

### Requirement: YAML config schema with logical sections
The YAML config SHALL be organised into logical top-level sections: `network`, `crew`,
`model`, `backends`, `portal`, `machine`. Each section groups related keys into
sub-sections where semantically appropriate. Per-backend config lives under
`backends.<backend>`. The `images` section is merged into `machine.images`.

The canonical section structure is:

```
network:
  host, port, host_url, api_key, require_api_key
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
    license
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

## REMOVED Requirements

### Requirement: (none removed — model.override is a config key, not a spec requirement)
