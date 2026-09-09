## Why

`server.py` is still ~4,200 lines because implementation functions that don't belong there were never moved during the TRN-71/86/116 extraction work. It should be an assembly file — MCP tool definitions and the startup block — not an implementation file. Three categories of misplaced code can be moved now without touching any external interface.

## What Changes

- **Proxy boilerplate helper** — create `async def _resolve_crew_for_proxy(path)` that encapsulates the parse + require + ensure-running + 404/502 response block copy-pasted across `_handle_crew_ui_proxy` (×1191), `_handle_crew_api_proxy` (×1428), `_handle_crew_ui_ws_proxy` (×1306), `_handle_crew_dashboard_post` (×1514). Each handler drops ~15 lines; proxy handlers become ~40% shorter.
- **Move pickup/dispatch helpers to `lifecycle.py`** — `_pickup_single`, `_pickup_list`, `_dispatch_batch`, `_record_last_task_at` move from `server.py` to `lifecycle.py` (next to the existing `_pickup_batch`). Removes ~310 lines from `server.py`. The `pickup` and `dispatch` MCP tools in `server.py` become thin callers.
- **Move login machinery to `lifecycle.py`** — `_initiate_login` (202 lines, 6-level nesting), `_login_pending`, `_login_pending_lock`, `_read_auth_file`, `_write_auth_file`, `_auth_file_path` move to `lifecycle.py` alongside `_inject_auth`, `_start_login_container`, `_nuke_login_container`. `server.py` retains `_handle_login_post`, `_handle_login_get`, `_handle_logout_post` as thin HTTP handlers.
- **Consolidate test mocks** — `FakeHTTP` and `FakeResponse` defined independently in `test_file_transfer.py`, `test_recovery.py`, `test_monitors.py`, and `test_server.py` are consolidated into `tests/unit/helpers.py`.

## Capabilities

### New Capabilities
<!-- None — pure refactor, no spec-level behaviour changes -->

### Modified Capabilities
<!-- None -->

## Impact

- `transport/server.py` — ~500 lines removed; becomes primarily MCP tool definitions + startup wiring
- `transport/lifecycle.py` — receives `_initiate_login`, login state globals, auth file helpers, pickup helpers, dispatch batch helpers
- `tests/unit/helpers.py` — receives consolidated `FakeHTTP`, `FakeResponse`; existing importers updated
- `tests/unit/test_server.py`, `test_lifecycle.py` — patch targets updated where functions move modules
- No API, protocol, or behaviour changes
