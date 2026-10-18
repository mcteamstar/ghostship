# Proposal

## Why

The initial YAML config structure (TRN-253) mapped env var names nearly 1:1 into flat YAML keys, missing the opportunity for semantic grouping. Related keys like `tls_certfile`/`tls_keyfile`, `git_author_name`/`git_author_email`, and the dashboard knobs belong under sub-sections. The model precedence design also needs revisiting: a global `model.override` is a footgun because no single model is accessible across all backends (kiro, claude, codex use different namespaces). The right design is per-backend model control with a single global fallback default. 0.8.0 is a breaking-change release — this is the right moment.

## What Changes

**Path restructuring (env var names unchanged throughout):**

- **BREAKING** `network.tls_certfile` / `network.tls_keyfile` → `network.tls.certfile` / `network.tls.keyfile`
- **BREAKING** `crew.git_author_name` / `crew.git_author_email` → `crew.git.author.name` / `crew.git.author.email`
- **BREAKING** `backends.agent` (string) → `backends.default` (YAML list); `yaml_config.py` joins list to comma-string for `GA_CREW_AGENT`
- **BREAKING** `backends.kiro.identity_provider` / `backends.kiro.region` → `backends.kiro.identity_center.url` / `backends.kiro.identity_center.region`
- **BREAKING** `portal.dashboard_port_range_start` / `portal.dashboard_port_range_size` / `portal.dashboard_default` → `portal.dashboard.port_range.start` / `portal.dashboard.port_range.size` / `portal.dashboard.default`
- **BREAKING** `machine.cpus` / `machine.memory` / `machine.disk` → `machine.resources.cpus` / `machine.resources.memory_mb` / `machine.resources.disk_gb`
- **BREAKING** top-level `images:` section merged into `machine.images:` (socket path and image names are machine-specific)

**Model precedence redesign:**

- **BREAKING** `model.override` removed — a global model override is a footgun across backends with different model namespaces
- **BREAKING** `model.default` kept as the sole global model knob
- **NEW** `backends.<b>.model.override` — per-backend model lock (e.g. force all kiro crews to `claude-sonnet-4-5` regardless of per-agent config)
- **NEW** `backends.<b>.model.default` — per-backend fallback when no per-agent model is set

Precedence chain (highest to lowest):
```
dispatch(model=...)  >  backends.<b>.model.override  >  per-agent  >  backends.<b>.model.default  >  model.default  >  built-in
```

**Backwards compatibility:**
- Old YAML paths added to `_DEPRECATED_YAML_PATHS` in `yaml_config.py` — warn and remap on load
- `config/ghostship.yaml.example` rewritten with new structure

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `yaml-config`: path restructuring, `images` merged into `machine`, model precedence redesign, list type for `backends.default`, deprecated-path warning on load

## Impact

- `scripts/lib/yaml_config.py` — `_KEY_MAP`, `DEFAULTS`, `flatten_to_env` (list join, new model env vars), deprecated-path rewrite pass
- `transport/config.py` — new per-backend model env vars; precedence logic updated
- `config/ghostship.yaml.example` — rewritten with new structure and per-backend model knobs
- `docs/configuration.md` — all YAML key path references updated; model precedence chain documented explicitly with the full chain and an explanation of when to use each level
- `tests/unit/test_yaml_config.py` — path references, new model tests
- `tests/unit/test_config.py` — sync invariant
