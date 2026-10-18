# Spec Delta

## MODIFIED Requirements

### Requirement: YAML config schema with logical sections
The YAML config SHALL be organised into logical sections: `network`, `crew`, `model`,
`backends`, `portal`, `machine`. Each section groups related keys into sub-sections
where semantically appropriate. Per-backend config lives under `backends.<backend>`.

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
  override, default

backends:
  default: [list of backends]   # first entry is runtime default
  kiro:
    identity_center:
      url, region
    license
  claude:
    base_url
  codex:
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

images:
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

#### Scenario: Old YAML path warns and applies
- **WHEN** `config/ghostship.yaml` uses `crew.git_author_name: "Bot"`
- **THEN** install.sh warns that `crew.git_author_name` is deprecated in favour of `crew.git.author.name`, and applies the value to `GA_GIT_AUTHOR_NAME`

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
