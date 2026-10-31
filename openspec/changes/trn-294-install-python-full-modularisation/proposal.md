# Proposal

## Why

`bin/install.sh` has grown to ~1633 lines of bash covering config resolution,
Podman machine setup, image builds, compose.yml generation, Caddy
initial-config.json generation, secret management, and the interactive wizard
flow. Agents cannot safely read or modify it — TRN-286 Ghost spent 40+ minutes
on install.sh alone — and the bash heredocs that generate YAML are untestable
and silently fragile. The indy-0.10.0 review (H-2) also flagged the
`eval "$_RESOLVED"` pattern on yaml_config.py output as an injection surface.

The fix: extract every substantive section into a Python module under
`bin/lib/`, leaving `install.sh` as a ~50 line glue entry point that does
nothing but bootstrap Python and delegate.

## What Changes

- **New `bin/lib/compose.py`** — compose.yml generation. Replaces the bash
  heredoc (lines ~1065–1230). Takes config as env vars, renders compose.yml
  via explicit field construction. Eliminates the eval injection surface
  (config values flow through Python, never through `eval`). Unit-testable.

- **New `bin/lib/caddy.py`** — Caddy `initial-config.json` generation.
  Replaces the heredoc section (lines ~1231–1431). Mirrors the runtime
  `transport/caddy.py` structure for install-time bootstrap config.

- **New `bin/lib/podman.py`** — Podman machine setup and socket resolution.
  Replaces lines ~529–790. macOS-vs-Linux branching, machine create/start,
  socket path detection.

- **New `bin/lib/wizard.py`** — Interactive wizard flow. Replaces lines ~62–165
  and ~1542–1625. Pure Python prompts, harness registration, auth handoff.

- **New `bin/lib/install.py`** — Top-level install orchestrator. Ties the
  modules together: arg parsing, config resolution, build steps, compose up,
  health check, PATH setup. The only bash caller.

- **`bin/install.sh` reduced to ~50 line glue entry point** — shebang, PATH
  bootstrap, Python availability check, `exec python3 bin/lib/install.py "$@"`.
  No logic.

- **New `tests/unit/test_compose.py`** — unit tests for compose.yml generation.
- **New `tests/unit/test_caddy_install.py`** — unit tests for Caddy config generation.
- **New `tests/unit/test_podman_setup.py`** — unit tests for Podman setup logic.
- **New `tests/unit/test_wizard.py`** — unit tests for wizard prompts and flow.

No user-visible behaviour changes. All existing flags, env vars, config keys,
and install outcomes are identical.

## Capabilities

### New Capabilities

None — pure internal refactor. No spec-level behaviour changes.
(`skip_specs: true` in `.openspec.yaml`)

### Modified Capabilities

None.

## Impact

- `bin/install.sh` — reduced to glue; no logic remains
- `bin/lib/compose.py` — new
- `bin/lib/caddy.py` — new
- `bin/lib/podman.py` — new
- `bin/lib/wizard.py` — new
- `bin/lib/install.py` — new top-level orchestrator
- `tests/unit/test_compose.py` — new
- `tests/unit/test_caddy_install.py` — new
- `tests/unit/test_podman_setup.py` — new
- `tests/unit/test_wizard.py` — new
- `bin/lib/yaml_config.py` — already Python; unchanged
- `bin/lib/vendor/` — already Python (PyYAML); unchanged
- All adjutant `deploy.sh` references to `bin/install.sh` — entry point path
  unchanged, behaviour identical
- Eliminates the H-2 `eval` injection surface from indy-0.10.0 review
