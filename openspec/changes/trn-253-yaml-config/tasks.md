# Tasks

## Group 1: Python config helper

- [x] 1.1 Write `scripts/lib/yaml_config.py` — standalone Python module with:
  - Built-in defaults dict (mirrors `Config` field defaults and existing `install.sh` built-in defaults)
  - `load_yaml(path)` — loads a YAML file, returns dict (empty dict if file missing)
  - `deep_merge(base, override)` — recursive merge, lists replaced entirely
  - `resolve_config(repo_path, xdg_path, explicit_path)` — applies three-layer merge: built-in defaults → repo → XDG, or built-in defaults → explicit (skips repo+XDG)
  - `flatten_to_env(merged)` — maps YAML nested keys to env var names (e.g. `network.port` → `PORT`)
  - `migrate_conf(conf_path, yaml_path)` — reads `ghostship.conf`, maps keys to YAML paths, writes `ghostship.yaml` with non-default values only; returns list of unknown keys
  - Verify: unit tests in `tests/unit/test_yaml_config.py` covering deep merge, flatten, migration, and missing-file handling

- [x] 1.2 Write `tests/unit/test_yaml_config.py` covering:
  - Deep merge: scalar override, nested partial override, list replacement
  - XDG layer missing → falls through to repo layer
  - `--config` flag skips repo and XDG
  - `flatten_to_env` maps all supported keys
  - `migrate_conf` maps known conf keys, emits `# UNKNOWN:` comments for unknowns

## Group 2: install.sh config loading

- [x] 2.1 Replace `source "$CONFIG_FILE"` config loading in `install.sh` with a call to `scripts/lib/yaml_config.py`:
  - Detect `--config <path>` flag → pass as explicit path
  - Otherwise resolve `$GHOSTSHIP_DIR/config/ghostship.yaml` (repo) and XDG path
  - Shell out: `python3 scripts/lib/yaml_config.py resolve ...` → outputs `KEY=value` lines → eval into install.sh environment
  - Preserve existing flag-override behaviour (CLI flags still take precedence over all config layers)
  - Verify: existing install tests pass; `--port` flag overrides `network.port` in config

- [x] 2.2 Add auto-migration in `install.sh`:
  - Before config loading: detect `config/ghostship.conf` with no `config/ghostship.yaml`
  - Shell out to migration helper, print notice, rename old file to `config/ghostship.conf.bak`
  - Warn on unknown keys found during migration
  - Verify: `tests/integration/test_install_migration.sh` — migration runs, YAML written, conf renamed, install proceeds

- [x] 2.3 Update `uninstall.sh` — replace references to `ghostship.conf` path with `ghostship.yaml`

## Group 3: Config example and .gitignore

- [x] 3.1 Write `config/ghostship.yaml.example` — fully commented-out YAML with all sections (`network`, `crew`, `model`, `backends`, `portal`, `machine`) and every configurable field at its default value, with description comments matching the current `ghostship.conf.example` style

- [x] 3.2 Update `config/ghostship.conf.example` — add a deprecation header pointing to `ghostship.yaml.example`; keep the file for one release (removed in 0.9.0)

- [x] 3.3 Update `.gitignore` — add `config/ghostship.yaml`, keep `config/ghostship.conf` entry

## Group 4: CI sync test

- [x] 4.1 Update `tests/unit/test_config.py` sync invariant — change the test that checks `Config` fields ↔ `ghostship.conf.example` to check against `ghostship.yaml.example` instead. Verify all existing `Config` fields appear in the YAML example.

## Group 5: Wizard

- [x] 5.1 Update the install.sh wizard to generate `config/ghostship.yaml` instead of `ghostship.conf`. Use a bash heredoc template with all keys commented out and operator-supplied values uncommented. Preserve `--wizard` flag behaviour (prompts before overwriting existing file).

## Group 6: docs

- [x] 6.1 Rewrite the "Config file" section of `docs/configuration.md`:
  - YAML format, three-layer merge, resolution order
  - All supported YAML keys by section with descriptions
  - XDG override file location (macOS and Linux)
  - `--config` flag semantics
  - Migration from `ghostship.conf`
  - Note that `ghostship.conf` is no longer read

- [x] 6.2 Update `docs/auth.md` — replace `ghostship.conf` references with `ghostship.yaml` where applicable (e.g. IDC config snippet)

- [x] 6.3 Update `README.md` — install instructions referencing config file format

## Group 7: Integration test updates

- [x] 7.1 Update `tests/integration/test_uninstall_auth_preservation.sh` — replace `ga-kiro-auth` preservation checks with `credentials/` preservation checks (legacy file removed in TRN-233); update any `ghostship.conf` references to `ghostship.yaml`

- [x] 7.2 Write `tests/integration/test_install_migration.sh` — verifies auto-migration: creates a sandbox with `ghostship.conf`, runs install, asserts `ghostship.yaml` created, `ghostship.conf.bak` exists, install completes successfully

## Deferred

- Transport reading `ghostship.yaml` directly (mounted via volume) — deferred to a future change. For 0.8.0, env var injection via compose.yml is preserved.
