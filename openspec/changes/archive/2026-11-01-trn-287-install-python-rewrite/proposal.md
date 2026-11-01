# Proposal

## Why

`bin/install.sh` has grown to ~1633 lines of bash handling config parsing,
YAML generation, Podman machine setup, image builds, Caddy route management,
compose.yml templating, secret management, and wizard flows. It is the hardest
file in the codebase for agents to read and modify correctly — TRN-286 Ghost
spent 40+ minutes navigating install.sh alone.

Additional motivation from the indy-0.10.0 review:
- **H-2**: `install.sh` uses `eval "$_RESOLVED"` on yaml_config.py output.
  Extracting to Python eliminates this injection surface entirely.
- **TRN-287-compose**: The compose.yml heredoc is the most fragile section —
  embedded YAML inside bash, untestable, and breaks on any quoting edge case.

## Approach — incremental module extraction

Each phase extracts one self-contained section into a `bin/lib/` Python module.
`install.sh` shells out to the new module with the same env var inputs and the
same side effects — zero user-visible change per phase. `install.sh` shrinks
each release until it is a ~50 line glue entry point.

## Target structure

```
bin/
├── install.sh           ← shrinks each phase → ~50 line glue entry point
├── ghostship            ← CLI
└── lib/
    ├── yaml_config.py   ← already here
    ├── vendor/          ← PyYAML (already here)
    ├── compose.py       ← Phase 1 (this change)
    ├── caddy.py         ← Phase 2
    ├── podman.py        ← Phase 3
    └── wizard.py        ← Phase 4
```

## Phase 1 — compose.py (this change)

Extract compose.yml generation (install.sh lines ~1065–1230) into
`bin/lib/compose.py`. This is the highest-value target:

- Bash heredoc with embedded YAML — one misplaced quote breaks the entire
  install silently
- All variable substitutions happen via `${VAR}` expansion inside the heredoc —
  no quoting safety, no validation
- Completely untestable as bash

Replace with a Python module that takes config as env vars or a dict and
renders compose.yml using `string.Template` or explicit field construction.
`install.sh` calls `python3 bin/lib/compose.py` after config resolution.

The module is also unit-testable: `test_compose.py` can assert that given a
set of config values, the rendered YAML has the correct structure.

## Capabilities

No new external capabilities. Internal refactor only — `skip_specs: true`.

## Impact (Phase 1)

- `bin/lib/compose.py` — new module
- `bin/install.sh` — replace heredoc section with `python3 bin/lib/compose.py`
- `tests/unit/test_compose.py` — new unit tests for compose generation
- `tests/integration/test_install_config.sh` — verify compose output unchanged
