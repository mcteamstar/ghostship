# Proposal

## Why

The initial YAML config structure (TRN-253) mapped env var names nearly 1:1 into flat YAML keys, missing the opportunity for semantic grouping. Flat sibling keys like `tls_certfile`/`tls_keyfile`, `git_author_name`/`git_author_email`, and `dashboard_port_range_start`/`dashboard_port_range_size`/`dashboard_default` belong under sub-sections that express their relationships and leave room for future additions without restructuring. 0.8.0 is a breaking-change release — this is the right moment.

## What Changes

- **BREAKING** `network.tls_certfile` / `network.tls_keyfile` → `network.tls.certfile` / `network.tls.keyfile`
- **BREAKING** `crew.git_author_name` / `crew.git_author_email` → `crew.git.author.name` / `crew.git.author.email`
- **BREAKING** `backends.agent` (string) → `backends.default` (YAML list); `yaml_config.py` joins the list to a comma-string for `GA_CREW_AGENT`
- **BREAKING** `backends.kiro.identity_provider` / `backends.kiro.region` → `backends.kiro.identity_center.url` / `backends.kiro.identity_center.region`
- **BREAKING** `portal.dashboard_port_range_start` / `portal.dashboard_port_range_size` / `portal.dashboard_default` → `portal.dashboard.port_range.start` / `portal.dashboard.port_range.size` / `portal.dashboard.default`
- **BREAKING** `machine.cpus` / `machine.memory` / `machine.disk` → `machine.resources.cpus` / `machine.resources.memory_mb` / `machine.resources.disk_gb`
- All env var names (`GA_MACHINE_MEMORY`, `GA_DASHBOARD_DEFAULT`, `KIRO_IDENTITY_PROVIDER`, etc.) are **unchanged** — only YAML paths move
- Old YAML paths added to `_DEPRECATED_YAML_ALIASES` in `yaml_config.py` — warn and map on load so existing configs don't silently break
- `config/ghostship.yaml.example` rewritten with new structure

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `yaml-config`: YAML key paths for the affected sections change; list type for `backends.default`; deprecated-path warning on load

## Impact

- `scripts/lib/yaml_config.py` — `_KEY_MAP`, `DEFAULTS`, `flatten_to_env` (list join), new deprecated-path alias map
- `config/ghostship.yaml.example`
- `tests/unit/test_yaml_config.py` — path references
- `tests/unit/test_config.py` — sync invariant
- `docs/configuration.md` — key path references
