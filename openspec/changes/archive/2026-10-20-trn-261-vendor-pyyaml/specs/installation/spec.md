# Spec delta — installation

## MODIFIED Requirements

### Scripts at scripts/start.sh and scripts/uninstall.sh

The user-facing executables SHALL be located at `bin/install.sh`, `bin/start.sh`,
and `bin/uninstall.sh`. Their support libraries (`yaml_config.py`,
`portal_host.sh`, `agent_backends.sh`) SHALL be located under `bin/lib/`.
The root `install.sh` shim SHALL delegate to `bin/install.sh` with all arguments
forwarded unchanged, preserving backward compatibility.

## ADDED Requirements

### PyYAML vendored — python3 is the only YAML config prerequisite

The ghostship repository SHALL include a vendored copy of the PyYAML pure-Python
package at `bin/lib/vendor/yaml/`. `bin/install.sh`, `bin/start.sh`, and
`bin/uninstall.sh` SHALL invoke `yaml_config.py` with
`PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3` so that `import yaml`
always resolves to the vendored copy without requiring PyYAML to be installed
on the system Python, and without creating a virtual environment. The only
prerequisite for YAML config parsing SHALL be a working `python3` binary.
