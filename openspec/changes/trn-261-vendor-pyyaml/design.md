# Design

## Context

See proposal.md — Why. The venv bootstrap exists because TRN-256 couldn't
assume PyYAML was installed on the system Python. Vendoring sidesteps that
entirely: the library travels with the repo, no network or package manager
involved.

PyYAML's pure-Python package is a single directory (`yaml/`) with 17 `.py`
files. The optional C extension (`_yaml` / `cyaml.py`) is only used if
compiled — `safe_load` works without it. Zero transitive deps. MIT licensed.

## Goals / Non-Goals

**Goals:** First-time install works with only `python3` present. No venv, no
pip, no uv, no network. Existing installs keep working.

**Non-Goals:** Vendoring any other dependency. Keeping the venv code as a
fallback (remove it entirely — having both paths is confusing and the venv path
is the one that breaks).

## Decisions

**Vendor location: `scripts/lib/vendor/yaml/`**

Keeps vendored code visually separate from ghostship's own lib code. The
`PYTHONPATH` prefix points at `scripts/lib/vendor/` so `import yaml` resolves
to the vendored copy even if a system yaml exists (PYTHONPATH takes precedence
over site-packages).

**Commit the vendor directory**

Not gitignored. It's intentional and needs to be present in every checkout,
including CI and the adjutant submodule. A `.gitignore` entry would silently
break deploys after a fresh clone.

**Remove venv bootstrap entirely, don't leave it as fallback**

A two-path system (try venv, fall back to vendor) would be confusing and hide
the fact that the vendor copy is always sufficient. One path, always vendor.

**Keep `yaml_config.py` unchanged**

It imports `yaml` at the top. `PYTHONPATH` makes this resolve to the vendor
copy automatically. No code change needed in the helper.

## Migration Plan

1. Copy `yaml/` from the installed PyYAML into `scripts/lib/vendor/yaml/`
2. Update `install.sh`, `start.sh`, `uninstall.sh`: replace the venv bootstrap
   block and `_YAML_PYTHON`/`_YAML_VENV` vars with a `_YAML_PYTHON` set to
   plain `python3`, and prefix invocations with
   `PYTHONPATH="${GHOSTSHIP_DIR}/scripts/lib/vendor"`.
3. Update docs.
4. Verify on a clean system (no PyYAML installed) that `install.sh --client-only`
   works end-to-end.

Rollback: revert the commit. The venv approach is gone but can be restored from
git history.

## Open Questions

None.
