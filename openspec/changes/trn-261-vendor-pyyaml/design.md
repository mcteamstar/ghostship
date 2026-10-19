# Design

## Context

See proposal.md — Why. Two changes that touch the same set of files, done
together to avoid a partial state where `bin/` exists but still uses the venv.

## Goals / Non-Goals

**Goals:** First-time install on any Linux or macOS host with only `python3`
and `podman`/`podman-compose`. Clear `bin/` vs `scripts/` layout. No venv,
no pip, no network at install time.

**Non-Goals:** Moving any file that isn't clearly user-facing to `bin/`. The
boundary is: does a user or deploy script invoke it directly? Yes → `bin/`.
No → `scripts/`.

## Decisions

**What moves to bin/ vs stays in scripts/**

| File | Decision | Reason |
|:-----|:---------|:-------|
| `install.sh` | → `bin/` | User runs directly |
| `start.sh` | → `bin/` | User runs directly |
| `stop.sh` | → `bin/` | User runs directly |
| `uninstall.sh` | → `bin/` | User runs directly |
| `lib/yaml_config.py` | → `bin/lib/` | Support for bin/ scripts only |
| `lib/portal_host.sh` | → `bin/lib/` | Sourced by bin/ scripts only |
| `setup.py` | stays `scripts/` | Invoked by ghostship CLI, not directly by users |
| `generate_openapi.py` | stays `scripts/` | Dev/CI tool |
| `security_scan.py` | stays `scripts/` | Dev/CI tool |

**Vendor location: `bin/lib/vendor/yaml/`**

Colocated with the scripts that use it. `PYTHONPATH` points at `bin/lib/vendor/`
so `import yaml` always resolves to the vendored copy. Takes precedence over any
system site-packages yaml (correct — we control the version).

**Commit the vendor directory**

Not gitignored. Vendored deps that are small, pure-Python, and zero-dependency
are legitimate to commit. A `.gitignore` entry would silently break fresh
clones and CI.

**Remove venv bootstrap entirely — no fallback**

Having a fallback-to-vendor path alongside a try-venv path would be confusing
and test two code paths. Remove the venv code entirely. The vendor copy is
always sufficient.

**`_YAML_CONFIG_HELPER` path update**

The scripts set `_YAML_CONFIG_HELPER="${GHOSTSHIP_DIR}/scripts/lib/yaml_config.py"`.
After the move this becomes `"${GHOSTSHIP_DIR}/bin/lib/yaml_config.py"`.
Invocation changes from `"$_YAML_PYTHON" "$_YAML_CONFIG_HELPER"` to
`PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER"`.

**adjutant deploy script**

`pre-deploy.sh` rsyncs the ghostship repo to starport. It may have hardcoded
`scripts/` paths that need updating. Check and update before merging.

## Migration Plan

1. Create `bin/` and `bin/lib/vendor/` directories.
2. Copy PyYAML pure-Python source into `bin/lib/vendor/yaml/`.
3. `git mv` the four scripts and two lib files.
4. Update all internal references (ghostship CLI, tests, docs).
5. Verify `bash -n` passes on all moved scripts.
6. Run `pytest tests/unit/` — confirm 858 tests pass.
7. Run `./bin/install.sh --client-only --url ...` on a shell with no venv — confirm no bootstrap output.
8. Deploy to starport to confirm carrier upgrade works cleanly.

## Open Questions

None.
