# Vendored dependencies

## PyYAML 6.0.3

- **License:** MIT
- **Source:** https://github.com/yaml/pyyaml
- **Why vendored:** ghostship's install scripts need to parse `ghostship.yaml`
  at install time. PyYAML is not part of the Python standard library and
  requiring operators to install it creates friction (venv bootstrapping,
  pip access). The pure-Python package is 17 files (~200KB), has zero
  transitive dependencies, and works on any Python 3.6+ interpreter.
- **What's included:** The `yaml/` package directory (pure Python only).
  The optional C extension (`_yaml`) is excluded — `safe_load` works without it.
- **Usage:** `PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 bin/lib/yaml_config.py`
