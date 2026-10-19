# Tasks

## 1. Vendor PyYAML

- [ ] 1.1 Copy the PyYAML pure-Python source into `bin/lib/vendor/yaml/`:
  extract the `yaml/` directory from PyYAML 6.x (e.g. from the installed
  venv at `${TMPDIR}/ghostship-yaml-venv`, or `pip download pyyaml --no-deps
  --no-binary :all:` and extract). Commit all `.py` files. Do NOT include any
  `_yaml.cpython-*.so` compiled extensions — pure Python only. Verify:
  `PYTHONPATH=bin/lib/vendor python3 -c "import yaml; yaml.safe_load('a: 1')"` exits 0.

- [ ] 1.2 Add `bin/lib/vendor/README.md` recording the vendored package name,
  version, and license (MIT). Verify: file exists with PyYAML version recorded.

## 2. Move user-facing scripts and libs to bin/

- [ ] 2.1 `git mv scripts/install.sh bin/install.sh`
- [ ] 2.2 `git mv scripts/start.sh bin/start.sh`
- [ ] 2.3 `git mv scripts/stop.sh bin/stop.sh` (if it exists separately)
- [ ] 2.4 `git mv scripts/uninstall.sh bin/uninstall.sh`
- [ ] 2.5 `git mv scripts/lib/yaml_config.py bin/lib/yaml_config.py`
- [ ] 2.6 `git mv scripts/lib/portal_host.sh bin/lib/portal_host.sh`
- [ ] 2.7 `git mv scripts/lib/agent_backends.sh bin/lib/agent_backends.sh`

  After each move verify `bash -n` passes on each moved `.sh` file.

## 3. Update internal references in moved scripts

- [ ] 3.1 In `bin/install.sh`: update `_YAML_CONFIG_HELPER` from
  `${GHOSTSHIP_DIR}/scripts/lib/yaml_config.py` → `${GHOSTSHIP_DIR}/bin/lib/yaml_config.py`.
  Update `source` paths for `agent_backends.sh` and `portal_host.sh`.
  Remove the entire venv bootstrap block (`_YAML_VENV`, `_YAML_PYTHON`,
  uv/ensurepip/get-pip.py chain). Replace all `"$_YAML_PYTHON" "$_YAML_CONFIG_HELPER"`
  invocations with `PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER"`.
  Verify: `bash -n bin/install.sh` passes; `grep -r ghostship-yaml-venv bin/` returns nothing.

- [ ] 3.2 In `bin/start.sh`: same — update `_YAML_CONFIG_HELPER` path, remove
  venv bootstrap, update `source` for `portal_host.sh`, add `PYTHONPATH` prefix.
  Verify: `bash -n bin/start.sh` passes.

- [ ] 3.3 In `bin/uninstall.sh`: same — update `_YAML_HELPER` path, remove venv
  bootstrap, add `PYTHONPATH` prefix.
  Verify: `bash -n bin/uninstall.sh` passes.

- [ ] 3.4 In `bin/lib/portal_host.sh`: the `_portal_host_helper()` function
  computes the path to `yaml_config.py` relative to `${BASH_SOURCE[0]}`. It
  now lives in `bin/lib/` so the relative path is unchanged — verify it still
  works by checking the dirname logic resolves correctly.

## 4. Update the root shim and ghostship CLI

- [ ] 4.1 Update `install.sh` (root shim):
  `exec "$(dirname "$0")/scripts/install.sh"` → `exec "$(dirname "$0")/bin/install.sh"`.
  Verify: `bash -n install.sh` passes.

- [ ] 4.2 In `ghostship` CLI shim: update all `_exec_script("scripts/...")` calls:
  - `scripts/install.sh` → `bin/install.sh`
  - `scripts/start.sh` → `bin/start.sh`
  - `scripts/stop.sh` → `bin/stop.sh`
  - `scripts/uninstall.sh` → `bin/uninstall.sh`
  Also update `_SCRIPTS_DIR` or equivalent constant if present.
  Verify: `python3 ghostship --help` exits 0.

## 5. Update tests

- [ ] 5.1 `tests/unit/test_yaml_config.py` line 23: update path from
  `scripts/lib/yaml_config.py` → `bin/lib/yaml_config.py`.

- [ ] 5.2 `tests/unit/test_config.py` line 614: update path from
  `scripts/lib/yaml_config.py` → `bin/lib/yaml_config.py`.

- [ ] 5.3 `tests/unit/test_portal_host.py` line 27: update `PORTAL_LIB` from
  `scripts/lib/portal_host.sh` → `bin/lib/portal_host.sh`.

- [ ] 5.4 `tests/integration/helpers/sandbox.sh`: update any hardcoded
  `scripts/install.sh`, `scripts/lib/` copy paths to `bin/install.sh`, `bin/lib/`.

- [ ] 5.5 `tests/integration/test_install_migration.sh`: update `stage_ghostship_tree`
  to copy from `bin/install.sh` and `bin/lib/`, update `mkdir -p` paths, update
  the `sandbox_run_script` call and all path references.

- [ ] 5.6 `tests/integration/test_install_config.sh`: update `INSTALL` variable
  from `scripts/install.sh` → `bin/install.sh`.

- [ ] 5.7 `tests/integration/test_install_wizard.sh`: update `INSTALL` variable
  and any `bash -n scripts/install.sh` references → `bin/install.sh`.

- [ ] 5.8 `tests/integration/test_uninstall_auth_preservation.sh`: update
  `UNINSTALL` variable from `scripts/uninstall.sh` → `bin/uninstall.sh`.

## 6. Update specs and docs

- [ ] 6.1 `openspec/specs/installation/spec.md`: update all `scripts/install.sh`,
  `scripts/start.sh`, `scripts/uninstall.sh` references → `bin/`.

- [ ] 6.2 `openspec/specs/installation/client-only/spec.md`: update all
  `scripts/install.sh` references → `bin/install.sh`.

- [ ] 6.3 `openspec/specs/trn-cli/spec.md`: update all `scripts/` references
  → `bin/`.

- [ ] 6.4 `docs/configuration.md`: update `scripts/install.sh --client-only`
  reference → `bin/install.sh --client-only` (or plain `./install.sh` via shim).

- [ ] 6.5 `README.md`: update any `scripts/` path references in prerequisites
  and setup sections. Remove PyYAML from the prerequisites list.

- [ ] 6.6 `transport/config.py`: update the comment at ~line 116 referencing
  `scripts/lib/agent_backends.sh` and ~line 226 referencing `scripts/lib/yaml_config.py`.

## 7. Update adjutant (separate repo)

- [ ] 7.1 In `mcteamstar/adjutant`, check `hyperv/starport/pre-deploy.sh` (or
  equivalent) for any rsync/copy paths that reference `scripts/install.sh`,
  `scripts/lib/`, etc. Update to `bin/` paths. Commit and push adjutant.

## 8. Integration check

- [ ] 8.1 Run `pytest tests/unit/` — confirm exit 0 (858 tests).

- [ ] 8.2 Run `./bin/install.sh --client-only --url http://localhost:64057/mcp`
  on a clean shell (after `rm -rf "${TMPDIR}/ghostship-yaml-venv"` to confirm
  the old venv path is not used). Verify: install completes with no venv
  bootstrap output and `ghostship status` works.

- [ ] 8.3 Run `./install.sh --client-only --url http://localhost:64057/mcp`
  (root shim) — confirm it delegates correctly to `bin/install.sh`.
