## Context

See proposal.md — Why.

`server.py` currently holds 52 top-level definitions. Prior extraction work (TRN-71, TRN-86, TRN-116) moved lifecycle, auth, caddy, podman, monitors, and academy out, but left behind three categories of implementation code that still belong elsewhere:

1. A 15-line boilerplate block repeated verbatim at the top of each of the four proxy handlers
2. Pickup/dispatch helper functions (`_pickup_single`, `_pickup_list`, `_dispatch_batch`, `_record_last_task_at`) that are pure helpers with no `@mcp.tool()` decoration and belong next to `_pickup_batch` in `lifecycle.py`
3. The entire login machinery (`_initiate_login`, login state globals, auth file helpers) which runs PTY exec, manages a login container, and reads/writes auth files — all lifecycle concerns that live alongside `_inject_auth`, `_start_login_container`, `_nuke_login_container` already in `lifecycle.py`

Additionally, `FakeHTTP`/`FakeResponse` test stubs are independently defined in four test files; `helpers.py` was created to centralise shared mocks but the migration was never completed.

## Goals / Non-Goals

**Goals:**
- `server.py` reduced to ~3,700 lines with no implementation functions that belong elsewhere
- `lifecycle.py` becomes the single home for all crew interaction logic (login, pickup polling, dispatch batching)
- Proxy handlers are readable without mentally skipping the boilerplate preamble
- Test mock duplication removed from four files

**Non-Goals:**
- Not introducing new classes (that is TRN-141)
- Not moving the proxy handler functions themselves out of `server.py` (that is the `proxy.py` module work, TRN-141)
- Not decomposing `_ensure_crew_running` or other long lifecycle functions (separate concern)

## Decisions

### D1: `_resolve_crew_for_proxy` stays in `server.py`

The four proxy handlers it serves all live in `server.py`. Moving it would require either a new `proxy.py` module (premature — TRN-141) or importing it from `lifecycle.py` (wrong layer). Keeping it in `server.py` is the right choice for this change.

### D2: Move `_pickup_single` and `_pickup_list` to `lifecycle.py`, not a new `pickup.py`

`_pickup_batch` already lives in `lifecycle.py` and is structurally identical. A new module would be premature given there are only three functions. If pickup grows further, extraction to `pickup.py` is a natural follow-on.

### D3: Move `_read_auth_file` / `_write_auth_file` / `_auth_file_path` to `lifecycle.py`

These are currently in `server.py` because `_handle_login_post` and `_handle_login_get` call them, and those handlers live in `server.py`. Since `_initiate_login` is moving to `lifecycle.py`, the auth file helpers follow naturally. The HTTP handlers in `server.py` import them from `lifecycle`.

### D4: `server.py` keeps the HTTP handlers for login (`_handle_login_post`, `_handle_login_get`, `_handle_logout_post`)

These are thin request/response wrappers registered as Starlette routes. Moving them to `lifecycle.py` would give lifecycle a Starlette dependency it doesn't currently have. The split is: lifecycle owns the state and logic, server.py owns the HTTP layer.

### D5: Consolidate test mocks via import, not copy

The consolidated `FakeHTTP` and `FakeResponse` in `helpers.py` should be importable by all four test files. Tests that define them inline will be updated to import from `helpers`. The inline definitions are deleted.

## Risks / Trade-offs

- [Tests patch `server._pickup_single`, `server._dispatch_batch`, etc.] → After moving, the canonical patch target changes to `lifecycle._pickup_single`. Any test patching the old `server.*` location needs updating. The `pickup` and `dispatch` MCP tool implementations in `server.py` will call the lifecycle functions, so patching `server.*` would still work if server re-exports, but the correct approach is to patch the owning module. Audit test patch targets after each move.
- [`_initiate_login` move is the highest-risk item] → It is 202 lines, uses `_login_pending` / `_login_pending_lock` globals, spawns a thread, and is called from `_handle_login_post` in `server.py`. The move requires careful import threading (no circular import `lifecycle → server`). Lifecycle must not import from `server`. The HTTP handlers in `server.py` will import the moved function from `lifecycle`.
- [FakeHTTP consolidation may require adjusting constructor signatures] → The four independent definitions may have slightly different interfaces. Reconcile to a single interface in `helpers.py`, update call sites.

## Migration Plan

1. Add `_resolve_crew_for_proxy` helper in `server.py`; replace the four proxy handler preambles
2. Move `_pickup_single`, `_pickup_list` to `lifecycle.py`; move `_dispatch_batch`, `_record_last_task_at` to `lifecycle.py`; update `server.py` callers to import from `lifecycle`
3. Move `_read_auth_file`, `_write_auth_file`, `_auth_file_path` to `lifecycle.py`; move `_initiate_login` and `_login_pending`/`_login_pending_lock` to `lifecycle.py`; update `server.py` callers
4. Consolidate `FakeHTTP`/`FakeResponse` into `helpers.py`; update the four test files
5. Run full suite after each step; fix patching targets
6. Single commit: `refactor: slim server.py — move misplaced functions to lifecycle`
