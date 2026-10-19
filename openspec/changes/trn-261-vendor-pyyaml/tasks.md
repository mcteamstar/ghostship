# Tasks

## 1. Vendor PyYAML

- [ ] 1.1 Copy the PyYAML pure-Python source into `scripts/lib/vendor/yaml/`:
  extract the `yaml/` directory from an installed PyYAML (e.g.
  `pip download pyyaml --no-deps --no-binary :all:` then extract, or copy from
  an existing install). Commit all 17 `.py` files. Do NOT include `_yaml.cpython-*.so`
  or any compiled extensions — pure Python only. Verify:
  `python3 -c "import sys; sys.path.insert(0,'scripts/lib/vendor'); import yaml; yaml.safe_load('a: 1')"` exits 0.

- [ ] 1.2 Add a `scripts/lib/vendor/README.md` noting the vendored package,
  version, and license (MIT). Verify: file exists with PyYAML version recorded.

## 2. Replace venv bootstrap in scripts

- [ ] 2.1 In `install.sh`: remove the `_YAML_VENV` / `_YAML_PYTHON` venv
  bootstrap block entirely (the `uv`/`ensurepip`/`get-pip.py` chain). Set
  `_YAML_PYTHON="python3"` and prepend
  `PYTHONPATH="${GHOSTSHIP_DIR}/scripts/lib/vendor"` to every invocation of
  `"$_YAML_PYTHON" "$_YAML_CONFIG_HELPER"`. Verify: `bash -n scripts/install.sh`
  passes; no `_YAML_VENV` or `ghostship-yaml-venv` references remain.

- [ ] 2.2 In `start.sh`: same — remove the venv bootstrap block, set
  `_YAML_PYTHON="python3"`, add `PYTHONPATH` prefix. Verify: `bash -n scripts/start.sh`
  passes; no venv references remain.

- [ ] 2.3 In `uninstall.sh`: same. Verify: `bash -n scripts/uninstall.sh`
  passes; no venv references remain.

## 3. Update docs and tests

- [ ] 3.1 Update `README.md` Prerequisites section: remove any mention of
  PyYAML as a prerequisite. `python3` is the only requirement for config parsing.
  Verify: `grep -i pyyaml README.md` returns nothing in the Prerequisites section.

- [ ] 3.2 Update `docs/configuration.md`: remove any mention of the PyYAML
  venv bootstrap. Verify: no stale venv references remain.

- [ ] 3.3 Update `tests/unit/test_config.py` and any other tests that reference
  the venv or `_YAML_PYTHON`: remove or update assertions about the venv path.
  Verify: `pytest tests/unit/ -q` exits 0.

## 4. Integration check

- [ ] 4.1 Run `pytest tests/unit/` — confirm exit 0.
- [ ] 4.2 Run `./install.sh --client-only --url http://localhost:64057/mcp` on a
  clean shell (after `rm -rf "${TMPDIR}/ghostship-yaml-venv"` to confirm the old
  venv is not used). Verify: install completes without any venv bootstrap output.
