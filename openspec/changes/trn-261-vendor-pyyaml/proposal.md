# Proposal

## Why

The PyYAML venv bootstrap (TRN-256) fails on Linux hosts where `python3-venv`
is not installed — e.g. starport (vm23, Ubuntu, Python 3.14). Ghostship
deployed to carrier required a manual `apt install python3-venv` before the
installer could proceed. The venv approach requires `uv`, `ensurepip`, or a
network-accessible `get-pip.py` — all three can fail in constrained or
air-gapped environments. The dependency is disproportionate for a tool whose
only job is parsing a config file at install time.

## What Changes

- Copy PyYAML's pure-Python source (`yaml/` directory, 17 `.py` files, ~200 KB,
  zero transitive dependencies, MIT licensed) into `scripts/lib/vendor/yaml/`
  and commit it as a vendored dependency.
- Replace all `"$_YAML_PYTHON" "$_YAML_CONFIG_HELPER"` invocations in
  `install.sh`, `start.sh`, and `uninstall.sh` with
  `PYTHONPATH="${GHOSTSHIP_DIR}/scripts/lib/vendor" python3 "$_YAML_CONFIG_HELPER"`.
- Remove the entire venv bootstrap block (`_YAML_VENV`, `_YAML_PYTHON`, the
  `uv`/`ensurepip`/`get-pip.py` fallback chain) from all three scripts. Also
  remove it from the `ghostship` CLI shim if it duplicates the same logic.
- Update README and `docs/configuration.md` prerequisites: PyYAML is no longer
  a prerequisite; `python3` is the only requirement (already checked).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `installation`: prerequisite for PyYAML removed; `python3` is sufficient.

## Impact

- `scripts/install.sh`, `scripts/start.sh`, `scripts/uninstall.sh` — venv
  bootstrap replaced with `PYTHONPATH` prefix
- `scripts/lib/vendor/yaml/` — new vendored directory (17 files, ~200 KB)
- `README.md`, `docs/configuration.md` — prerequisite docs updated
- No behaviour change: `yaml_config.py` imports `yaml` identically either way
