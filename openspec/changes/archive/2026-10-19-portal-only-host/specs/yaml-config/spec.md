## MODIFIED Requirements

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

## ADDED Requirements

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
