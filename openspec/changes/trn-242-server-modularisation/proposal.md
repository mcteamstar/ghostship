## Why

`transport/server.py` is ~5 000 lines and contains four unrelated concerns
(HTTP infrastructure, MCP tool implementations, captain/schedule engine logic,
and login HTTP handlers) that have grown together incidentally. Navigating,
reviewing, and testing any one concern requires mentally filtering out the
others. TRN-240 already broke out `lifecycle.py`, `monitors.py`, `login.py`,
`launcher.py`, `academy.py`, `caddy.py`, `dashboard.py`, and `auth.py`; the
remaining bulk in `server.py` is the natural next step and follows the same
zero-behaviour-change pattern.

## What Changes

- **New file `transport/tools.py`** — the ten MCP tool functions (`crews`,
  `launch`, `supply`, `evac`, `nuke`, `dispatch`, `steer`, `pickup`,
  `schedule`, `captain`) and their private helpers (`_registry_guard`,
  `_validate_model`, `_bg_prewarm`, `_dispatch_batch` wrapper, `_schedule_cancel`,
  `_schedule_list`, `_registry_guard`). The `mcp` instance is owned by
  `server.py` and passed in; tools register themselves against it.
- **New file `transport/captain_engine.py`** — the three captain-engine
  helpers that sit between the `captain()` MCP tool and `captain.py`:
  `_dispatch_captain_checkin`, `_steer_captain_checkin`, `_captain_do_order`,
  `_captain_do_status`, `_captain_do_stop`, and their private helpers
  (`_MemoryPressureSkip`, `_check_in_memory_pressure`,
  `_is_memory_pressure_refusal`, `_mail_admiral`,
  `_record_memory_pressure_cycle`). Breaking these out resolves the current
  `monitors.py → server.py` deferred import that exists only because
  `_steer_captain_checkin` and `_dispatch_captain_checkin` have nowhere else
  to live.
- **`transport/login.py` absorbs remaining kiro/claude/codex HTTP handler
  helpers** — `_warn_inert_backend_settings`, `_backend_enabled`,
  `_backend_not_enabled_message` move alongside the handlers that use them,
  and the six route handlers (`_handle_login_post`, `_handle_login_get`,
  `_handle_logout_post`, `_handle_claude_login_*`, `_handle_codex_login_*`,
  `_handle_logout_post`) move to `login.py` as well. `server.py` imports
  the handler callables and registers them with `BearerAuthMiddleware`.
- **`transport/server.py` is trimmed** to: imports, config/global setup,
  `mcp` instance creation, proxy HTTP handlers (`_handle_crew_ui_proxy`,
  `_handle_crew_ui_ws_proxy`, `_handle_crew_api_proxy`,
  `_handle_crew_dashboard_*`, `_handle_captain_stop_post`,
  `_handle_health`, `_handle_version_get`, `_handle_openapi_get`), app
  wiring (middleware stack, uvicorn), and `__main__` startup.
- No behaviour changes, no API changes, no new environment variables.
  All MCP tool signatures unchanged. All REST endpoint paths unchanged.
  Tests stay green throughout.

## Capabilities

### New Capabilities
<!-- None — pure refactor, no new behaviour -->

### Modified Capabilities
<!-- None — no spec-level behaviour changes -->

## Impact

- `transport/server.py`: reduced from ~5 000 lines to ~1 200–1 500 lines
  (proxy handlers + wiring only).
- `transport/tools.py`: new file, ~2 000 lines (MCP tool functions).
- `transport/captain_engine.py`: new file, ~700 lines (captain dispatch/steer engine).
- `transport/login.py`: grows by ~600 lines (kiro/claude/codex HTTP handlers
  and their local helpers).
- `transport/monitors.py`: the deferred `from server import _steer_captain_checkin`
  at call time is replaced with a direct import from `captain_engine`.
- No changes to `crews.json` format, REST API shape, MCP tool signatures,
  or external behaviour.
