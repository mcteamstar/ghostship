# Proposal

## Why

Two friction points addressed together since they touch the same files:

**scripts/ layout is unclear.** User-facing scripts (`install.sh`, `start.sh`,
`stop.sh`, `uninstall.sh`) live alongside dev/CI tools (`generate_openapi.py`,
`security_scan.py`) with no distinction. The convention `bin/` for user-facing
executables and `scripts/` for dev/CI tools makes the intent obvious.

**PyYAML venv bootstrap fails on constrained Linux hosts.** The TRN-256 venv
bootstrap requires `python3-venv`, `uv`, or network access to `get-pip.py`.
On starport (Ubuntu, Python 3.14) this caused a failed install until
`python3-venv` was manually installed. The fix is to vendor PyYAML's pure-Python
source — it's 200KB, zero dependencies, MIT licensed, and needs only `python3`.

## What Changes

### 1. Restructure scripts/ → bin/

Move user-facing executables and their support libraries:
- `scripts/install.sh` → `bin/install.sh`
- `scripts/start.sh` → `bin/start.sh`
- `scripts/stop.sh` → `bin/stop.sh`
- `scripts/uninstall.sh` → `bin/uninstall.sh`
- `scripts/lib/yaml_config.py` → `bin/lib/yaml_config.py`
- `scripts/lib/portal_host.sh` → `bin/lib/portal_host.sh`

Dev/CI tools stay in `scripts/`: `generate_openapi.py`, `security_scan.py`,
`setup.py`, and any other non-user-facing tools.

Update all internal references:
- `ghostship` CLI shim — `_exec_script()` and `GHOSTSHIP_DIR` path constants
- `tests/integration/` — script paths in test helpers
- `scripts/run.sh` — integration test loop
- `Containerfile` and `compose.yml` template — any `scripts/` refs
- `adjutant` deploy script — `pre-deploy.sh` rsync paths
- `README.md` and `docs/` — any path references

### 2. Vendor PyYAML into bin/lib/vendor/

- Copy PyYAML pure-Python source (17 `.py` files) into `bin/lib/vendor/yaml/`.
  Commit it — it's intentional and must be present in every checkout.
- Replace all venv bootstrap blocks (`_YAML_VENV`, `_YAML_PYTHON`,
  `uv`/`ensurepip`/`get-pip.py` chain) in `bin/install.sh`, `bin/start.sh`,
  and `bin/uninstall.sh` with:
  `PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER"`
- Add `bin/lib/vendor/README.md` noting version and license.
- Update README prerequisites: PyYAML no longer needed; `python3` is sufficient.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `installation`: `bin/` layout documented; PyYAML prerequisite removed;
  `python3` is sufficient for YAML config parsing.

## Impact

- `bin/` — new directory, four scripts
- `bin/lib/` — new directory, two support files + vendored yaml/
- `scripts/` — user-facing scripts removed; dev tools remain
- `ghostship` CLI shim — path constants updated
- `tests/` — integration test paths updated
- `adjutant` — deploy script rsync paths updated (separate repo)
- README, docs — path references updated
