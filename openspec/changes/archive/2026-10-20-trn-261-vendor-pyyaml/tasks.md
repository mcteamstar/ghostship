# Tasks

## 1. Vendor PyYAML

- [x] 1.1 Copy the PyYAML pure-Python source into `bin/lib/vendor/yaml/` (17 files, PyYAML 6.0.3, no .so extensions). Verify: `PYTHONPATH=bin/lib/vendor python3 -c "import yaml; yaml.safe_load('a: 1')"` exits 0.

- [x] 1.2 Add `bin/lib/vendor/README.md` noting PyYAML 6.0.3, MIT license, and usage.

## 2. Move user-facing scripts and libs to bin/

- [x] 2.1 `git mv scripts/install.sh bin/install.sh`
- [x] 2.2 `git mv scripts/start.sh bin/start.sh`
- [x] 2.3 (no stop.sh — ghostship stop is CLI-only)
- [x] 2.4 `git mv scripts/uninstall.sh bin/uninstall.sh`
- [x] 2.5 `git mv scripts/lib/yaml_config.py bin/lib/yaml_config.py`
- [x] 2.6 `git mv scripts/lib/portal_host.sh bin/lib/portal_host.sh`
- [x] 2.7 `git mv scripts/lib/agent_backends.sh bin/lib/agent_backends.sh`

## 3. Update internal references in moved scripts

- [x] 3.1 `bin/install.sh`: updated `_YAML_CONFIG_HELPER`, removed venv bootstrap, added `PYTHONPATH` prefix, updated `source` paths for agent_backends.sh and portal_host.sh.
- [x] 3.2 `bin/start.sh`: same — removed venv bootstrap, updated paths, added `PYTHONPATH` prefix.
- [x] 3.3 `bin/uninstall.sh`: same — updated `_YAML_HELPER`, removed venv bootstrap, added `PYTHONPATH` prefix.
- [x] 3.4 `bin/lib/portal_host.sh`: self-relative path to yaml_config.py unchanged — still correct from bin/lib/.

## 4. Update the root shim and ghostship CLI

- [x] 4.1 `install.sh` (root shim): updated to `bin/install.sh`.
- [x] 4.2 `ghostship` CLI: all `_exec_script("scripts/...")` calls updated to `bin/`. Comments updated.

## 5. Update tests

- [x] 5.1 `tests/unit/test_yaml_config.py`: path updated to `bin/lib/yaml_config.py`.
- [x] 5.2 `tests/unit/test_config.py`: path updated to `bin/lib/yaml_config.py`.
- [x] 5.3 `tests/unit/test_portal_host.py`: `PORTAL_LIB`, `INSTALL_SH`, `START_SH` paths updated.
- [x] 5.4 `tests/integration/helpers/sandbox.sh`: paths updated.
- [x] 5.5 `tests/integration/test_install_migration.sh`: `stage_ghostship_tree` updated — mkdir, cp, vendor copy added.
- [x] 5.6 `tests/integration/test_install_config.sh`: `INSTALL` variable updated.
- [x] 5.7 `tests/integration/test_install_wizard.sh`: `INSTALL` variable and `bash -n` reference updated.
- [x] 5.8 `tests/integration/test_uninstall_auth_preservation.sh`: `UNINSTALL` variable updated.
- [x] Also fixed: `tests/unit/test_uninstall.py` and `tests/unit/test_install.py`.

## 6. Update specs and docs

- [x] 6.1 `openspec/specs/installation/spec.md`: all `scripts/` → `bin/` references updated.
- [x] 6.2 `openspec/specs/installation/client-only/spec.md`: updated.
- [x] 6.3 `openspec/specs/trn-cli/spec.md`: updated.
- [x] 6.4 `docs/configuration.md`: updated.
- [x] 6.5 `README.md`: updated.
- [x] 6.6 `transport/config.py`: comment references updated.

## 7. Update adjutant (separate repo)

- [ ] 7.1 Check adjutant `hyperv/starport/pre-deploy.sh` for any rsync/copy paths referencing `scripts/`. Update to `bin/` and commit.

## 8. Integration check

- [x] 8.1 `pytest tests/unit/` exits 0 — 858 passed.
- [x] 8.2 `./bin/install.sh --client-only` on clean shell (no venv) — completes with no bootstrap output.
- [x] 8.3 `./install.sh --client-only` (root shim) — delegates correctly to `bin/install.sh`.
