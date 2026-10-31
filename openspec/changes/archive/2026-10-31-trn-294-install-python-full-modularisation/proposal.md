# Proposal

## Why

`bin/install.sh` remains a ~1633-line monolith despite TRN-287 planning its
decomposition. The compose.yml heredoc (Phase 1), Caddy config (Phase 2),
Podman machine/instance setup (Phase 3), and wizard flow (Phase 4) are all still
embedded bash that is untestable, injection-prone (the `eval "$_RESOLVED"` surface
remains), and the hardest code in the repo for agents and maintainers alike to
navigate. TRN-287 only produced a proposal and no implementation; this change
executes the full modularisation plan.

## What Changes

- **New module `bin/lib/compose.py`** — replaces the compose.yml heredoc in
  `install.sh` with a Python function; renders via dataclass + PyYAML dump rather
  than string interpolation; fully unit-testable.
- **New module `bin/lib/caddy.py`** — replaces the Caddy `initial-config.json`
  generation block in `install.sh`; returns structured JSON, no bash heredoc or
  string interpolation.
- **New module `bin/lib/podman_setup.py`** — replaces the Podman machine/instance
  provisioning, socket waiting, and dedicated-instance wiring blocks in
  `install.sh`; Python subprocess calls eliminate the eval-over-config-output
  injection risk.
- **New module `bin/lib/wizard.py`** — replaces the `_interactive_setup` function
  and post-install auth offers in `install.sh`; owns all interactive terminal I/O.
- **Shrunk `bin/install.sh`** — reduced from ~1633 lines to a ~80-line glue entry
  point: config resolution (already Python), argument parsing, and shelling out to
  the four new modules in order.
- **New unit tests** — `tests/unit/test_compose.py`, `tests/unit/test_caddy.py`,
  `tests/unit/test_podman_setup.py`, `tests/unit/test_wizard.py`; each asserts
  correct output structure given controlled inputs, no Podman required.
- **Existing `bin/lib/agent_backends.sh` and `bin/lib/portal_host.sh`** — migrated
  to `bin/lib/agent_backends.py` and `bin/lib/portal_host.py`; the shell wrappers
  become one-line callers so install.sh changes minimally for sourcing.

## Capabilities

### New Capabilities

- `installation/python-modules`: install.sh logic is implemented in tested Python
  modules under `bin/lib/`; `install.sh` is a thin shell entry point that delegates
  to those modules; the bash `eval "$_RESOLVED"` injection surface is fully removed.

### Modified Capabilities

- `installation`: Multiple requirements describe `install.sh` behaviour that is
  being re-implemented in the new Python modules; no requirement text changes, but
  the implementation contract moves from shell to Python. The existing install spec
  remains authoritative; no requirement delta is needed.
- `config-file`: The `eval "$_RESOLVED"` pattern that `install.sh` currently uses
  to ingest `yaml_config.py` output is replaced with direct Python imports; the
  install spec requirement "config file sourcing with correct precedence" is
  implemented without shell eval. Spec text unchanged — skip_specs covers this.

## Impact

- `bin/install.sh` — dramatically shortened; each major section replaced by a
  `python3 bin/lib/<module>.py` call.
- `bin/lib/compose.py` — new module (replaces heredoc in install.sh).
- `bin/lib/caddy.py` — new module (replaces Caddy JSON heredoc in install.sh).
- `bin/lib/podman_setup.py` — new module (replaces Podman provisioning in install.sh).
- `bin/lib/wizard.py` — new module (replaces `_interactive_setup` in install.sh).
- `bin/lib/agent_backends.py` — new module (replaces `agent_backends.sh`).
- `bin/lib/portal_host.py` — new module (replaces `portal_host.sh`).
- `tests/unit/test_compose.py`, `test_caddy.py`, `test_podman_setup.py`,
  `test_wizard.py` — new test files.
- `bin/start.sh`, `bin/uninstall.sh` — updated to call the Python modules for
  shared logic they currently replicate from `portal_host.sh` / `agent_backends.sh`.
- No user-visible change: `./install.sh` flags and behaviour are identical.
- PyYAML remains the only non-stdlib dependency (already vendored at
  `bin/lib/vendor/yaml`); no new packages introduced.
