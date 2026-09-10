## Why

Infrastructure constants (`CREW_GATEWAY_PORT`, `PERSONA_NAMES`, `SCRIPTS_DIR`, network names, container prefixes) are independently declared in 3–5 modules, and a lazy-import workaround in `files.py` left over from TRN-71 is now dead code. Neither problem affects behaviour, but both create drift risk when adding new constants and obscure the true import graph.

## What Changes

- **New file `transport/constants.py`** — a zero-dependency leaf module that is the single canonical home for all container-side constants currently duplicated across `lifecycle.py`, `server.py`, `podman.py`, `captain.py`, and `monitors.py`
- **All modules updated** to import constants from `transport.constants` rather than declaring their own copies; existing re-exports in `lifecycle.py` and `server.py` are removed or replaced with a single `from transport.constants import ...`
- **`monitors.py` `bind_lifecycle()` injection** of `CREW_GATEWAY_PORT` removed — replaced with a direct import from `transport.constants`
- **`files.py` lazy-import resolver removed** — the `_crew_helpers()` function and its `server.py` fallback are dead code since TRN-71 step 5 completed; replaced with a direct `from transport.lifecycle import _ensure_crew_running, _require_crew` at module load time

## Capabilities

### New Capabilities
<!-- None — pure refactor, no spec-level behaviour changes -->

### Modified Capabilities
<!-- None -->

## Impact

- `transport/constants.py` — new file
- `transport/lifecycle.py` — remove duplicate constant declarations and re-exports
- `transport/server.py` — remove duplicate constant declarations
- `transport/podman.py` — remove `CREW_CONTAINER_PREFIX` declaration, import from constants
- `transport/captain.py` — remove `SCRIPTS_DIR` declaration, import from constants
- `transport/monitors.py` — remove `bind_lifecycle()` CREW_GATEWAY_PORT injection, import from constants
- `transport/files.py` — remove `_crew_helpers()` lazy resolver and server.py fallback; add direct lifecycle import
- `tests/unit/` — update any tests that patch the old constant locations to patch `transport.constants` instead
- No API, behaviour, or protocol changes
