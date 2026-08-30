## Why

`transport/server.py` is ~5700 lines — a single-file monolith that simultaneously owns 12 distinct concerns: Podman client, registry/persistence, crew lifecycle, session/cookie management, mail system, schedule engine, idle manager, file transfer, HTTP proxy, auth state machine, config, and the MCP tool layer. There are no internal layer boundaries and no injected interfaces anywhere in the critical call stack. The Wraith architecture review (2026-08-29) identified this as the root cause of most quality, testability, and concurrency risks in the codebase.

This is a **pure structural refactor** — no behaviour changes, no correctness fixes. Code moves to modules; all existing tests must continue to pass. Correctness findings (F2 registry TOCTOU, F4 crew dict mutation) are deferred to follow-on tickets.

## What Changes

- `transport/` becomes a Python package (`__init__.py` added)
- Six new modules extracted from `server.py` in dependency order:
  - `registry.py` — handler: owns `crews.json`, `_registry_lock`, all CRUD on crew/schedule entries
  - `podman.py` — helper: `PodmanClient` class (already a class), `ContainerRuntime` ABC, `_podman` singleton, HTTP clients, memory cache
  - `files.py` — helper: presigned URL signing/verification, file upload/download handlers, `_TarMemberStream`, `_ResponseChunkReader`
  - `captain.py` — handler: owns `_captain_order_locks`, mail injection, order template loading/substitution, captain constants
  - `lifecycle.py` — handler: owns `_startup_events`, `_recovery_locks`, `_ensure_crew_running`, `_reconcile_registry`, `_finish_crew_setup`, `_cleanup_crew`
  - `server.py` — reduced to thin orchestration: ASGI app, route wiring, MCP tool registration, login state machine, background thread starts
- `transport/Containerfile` switches from individual file copies to `COPY transport/ /app/` (flat layout inside container)
- One commit per module extraction so each step is independently reviewable and bisectable
- All test imports updated to match new module locations

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — pure structural refactor. No externally visible behaviour changes.

## Impact

- `transport/` — new package structure with 6 new modules
- `transport/Containerfile` — COPY directive update
- `tests/unit/` — import paths updated; no test logic changes
- **Prerequisite:** This change should be based on `release/0.2.1` after TRN-74 (container scripts) and TRN-75 (config dataclass) have landed, so the extracted modules start from the already-cleaned state
