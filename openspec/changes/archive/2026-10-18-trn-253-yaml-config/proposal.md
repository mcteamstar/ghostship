# Proposal

## Why

`ghostship.conf` is a flat shell-sourced file that can only express structure through
comments. As the config surface grows — agent subconfigs, per-backend options, portal
settings, identity provider config — the flat format makes relationships opaque and
the file harder to navigate. Migrating to YAML gives the config real structure, enables
deep-merge layering, and removes the shell-sourcing requirement that prevents the file
from being used outside of bash contexts.

This is a breaking change deliberately targeted at 0.8.0 alongside the auth lifecycle
changes (TRN-233), to confine upgrade friction to a single release.

## What Changes

- **BREAKING** `ghostship.conf` is no longer read by `install.sh`. Operators must
  migrate to `ghostship.yaml`. Auto-migration is provided: install.sh detects an
  existing `ghostship.conf` with no `ghostship.yaml` and converts automatically,
  renaming the old file to `ghostship.conf.bak`.

- **New `config/ghostship.yaml`** (gitignored) — the operator's main config file,
  equivalent to today's `ghostship.conf`. Located at `config/ghostship.yaml` in the
  repo directory. Implicit: install.sh resolves it automatically without a flag.

- **New `config/ghostship.yaml.example`** — committed to the repo, replaces
  `config/ghostship.conf.example`. Fully commented-out, all configurable fields shown
  with their default values. Read-only from ghostship's perspective — documentation
  only, never parsed programmatically.

- **New XDG override layer** — `~/.config/ghost-academy/ghostship.yaml`. Optional
  personal override file for machine-specific or personal settings the operator
  doesn't want in the repo (e.g. identity provider URL, region).

- **Three-layer deep merge** — config is resolved in order, each layer deep-merging
  at the individual key level on top of the previous:
  1. Built-in defaults (Config dataclass field defaults)
  2. Repo-level: `config/ghostship.yaml` (if present)
  3. XDG override: `~/.config/ghost-academy/ghostship.yaml` (if present)

- **`--config <path>` flag** — replaces layers 2 and 3 entirely. The specified file
  deep-merges on top of built-in defaults only; no XDG override is applied. Every
  config file is an override file — operators only specify keys they want to change
  from the defaults.

- **Structured YAML schema** — flat env var keys become nested under logical sections:
  `network`, `crew`, `model`, `backends`, `portal`, `machine`. The `backends` section
  supports per-backend subconfig (e.g. `backends.kiro.identity_provider`).

- **`transport/config.py`** — `Config.from_env()` remains for container-side config
  (env vars are still baked into compose.yml by install.sh). A new `Config.from_yaml()`
  path deserialises the merged YAML dict into the same `Config` dataclass, used by
  install.sh when it shells out to Python for config loading.

- **`install.sh` wizard** — generates `config/ghostship.yaml` (not `ghostship.conf`)
  on first run. Comments are written from an internal template, not by parsing the
  example file.

- **`.gitignore`** — `ghostship.yaml` added (like `ghostship.conf` today).

## Capabilities

### New Capabilities

- `yaml-config`: Structured YAML configuration file with three-layer deep merge
  (defaults → repo → XDG), replacing the flat shell-sourced `ghostship.conf`.

### Modified Capabilities

- `config-file`: All existing requirements change — the file format changes from
  shell key=value to YAML, the sourcing mechanism changes from `source` to Python
  YAML parsing, the resolution order gains an XDG layer, and the sync invariant
  (Config fields ↔ config file entries) now applies to `ghostship.yaml.example`
  rather than `ghostship.conf.example`. The `--config` flag semantics change
  from "source this shell file" to "deep-merge this YAML file over defaults".

- `installation`: The install wizard and migration path change. The `--config` flag
  now accepts a YAML file. Auto-migration from `ghostship.conf` to `ghostship.yaml`
  is added.

## Impact

- `config/ghostship.conf.example` → `config/ghostship.yaml.example` (renamed + restructured)
- `config/ghostship.conf` → `config/ghostship.yaml` (operator file, gitignored)
- `scripts/install.sh` — config loading, wizard, migration
- `scripts/uninstall.sh` — references to `ghostship.conf` path
- `transport/config.py` — new `from_yaml()` class method
- `tests/unit/test_config.py` — sync invariant test updated to check `ghostship.yaml.example`
- `docs/configuration.md` — full rewrite for new format and resolution order
- `docs/auth.md` — references to `ghostship.conf` updated
- `README.md` — install instructions updated
