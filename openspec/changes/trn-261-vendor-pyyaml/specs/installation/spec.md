# Spec delta — installation

## ADDED Requirements

### PyYAML vendored — python3 is the only YAML config prerequisite

The ghostship repository SHALL include a vendored copy of the PyYAML pure-Python
package at `scripts/lib/vendor/yaml/`. `install.sh`, `start.sh`, and
`uninstall.sh` SHALL invoke `yaml_config.py` with
`PYTHONPATH="${GHOSTSHIP_DIR}/scripts/lib/vendor" python3` so that `import yaml`
always resolves to the vendored copy without requiring PyYAML to be installed on
the system Python, and without creating a virtual environment. The only
prerequisite for YAML config parsing SHALL be a working `python3` binary, which
is already checked before any YAML config operations.
