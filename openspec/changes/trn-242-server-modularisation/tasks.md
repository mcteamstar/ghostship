# Tasks

Each task is scoped to one commit with tests green. No task leaves a broken
intermediate state. Tasks within a numbered group may be done in any order;
numbered groups must be done in order.

---

## 1. Extract `transport/captain_engine.py`

Moves the captain dispatch/steer engine out of `server.py`, breaking the
`monitors.py → server` deferred call-time import.

- [x] 1.1  **Create `transport/captain_engine.py`.**
  Move the following from `transport/server.py` to `captain_engine.py`:
  - `_MEMORY_PRESSURE_MARKER` (str constant, line ~3232)
  - `class _MemoryPressureSkip(RuntimeError)` (line ~3235)
  - `_check_in_memory_pressure() -> float | None` (line ~3242)
  - `_is_memory_pressure_refusal(resp) -> bool` (line ~3261)
  - `_mail_admiral(crew_id, subject, body)` (line ~3275)
  - `_record_memory_pressure_cycle(crew_id)` (line ~3309)
  - `_dispatch_captain_checkin(crew, crew_id, model=None) -> str` (line ~3335)
  - `_steer_captain_checkin(crew, crew_id, model=None) -> str` (line ~3462)
  - `_captain_do_order(crew_id, message, template, change_name, cron, interval,
    timezone, fire_immediately, model) -> dict` (line ~3576)
  - `_captain_do_status(crew_id) -> dict` (line ~3751)
  - `_captain_do_stop(crew_id) -> dict` (line ~3845)

  `captain_engine.py` imports from: `config`, `registry`, `captain`,
  `lifecycle` (`_ensure_crew_running`, `_crew_api_with_recovery`, `_to_crew`,
  `_get_podman`, `_write_dashboard_cookie`, `_require_crew`, `registry`,
  `CrewUnresponsiveError`), `podman` (`_get_podman`). Follow the established
  dual-path import pattern (container flat layout vs local dev package).

  `server.py` adds re-export imports so `patch('server.X')` in existing tests
  continues to resolve:
  ```python
  from transport.captain_engine import (  # noqa: F401
      _MEMORY_PRESSURE_MARKER, _MemoryPressureSkip,
      _check_in_memory_pressure, _is_memory_pressure_refusal,
      _mail_admiral, _record_memory_pressure_cycle,
      _dispatch_captain_checkin, _steer_captain_checkin,
      _captain_do_order, _captain_do_status, _captain_do_stop,
  )
  ```
  The `captain()` MCP tool in `server.py` still calls `_captain_do_order` /
  `_captain_do_status` / `_captain_do_stop` by their imported names — no
  change to call sites inside `server.py` yet (tools extraction is Step 2).
  Verify: `python3 -c "import transport.captain_engine"` exits 0.
  Verify: `pytest tests/unit/ -q` green.

- [x] 1.2  **Update `monitors.py` to import from `captain_engine` directly.**
  In `monitors.py::_captain_monitor`, replace the deferred call-time import:
  ```python
  # OLD (call-time)
  try:
      from server import _steer_captain_checkin, _dispatch_captain_checkin
  except ModuleNotFoundError:
      from transport.server import _steer_captain_checkin, _dispatch_captain_checkin
  ```
  with a top-level module import at the top of `monitors.py`:
  ```python
  try:
      from captain_engine import _steer_captain_checkin, _dispatch_captain_checkin
  except ModuleNotFoundError:
      from transport.captain_engine import _steer_captain_checkin, _dispatch_captain_checkin
  ```
  Remove the try/except block that was inside the loop body. Verify that
  `bind_lifecycle()` in `monitors.py` does not need updating (these names are
  not injected via `bind_lifecycle`; they are now direct imports from the leaf).
  Verify: `pytest tests/unit/ -q` green.

---

## 2. Extract `transport/tools.py`

Moves the MCP tool functions and their helpers out of `server.py`. The `mcp`
instance stays in `server.py`; tools are registered via `register_tools(mcp,
caddy_portal, dashboard_gate)`.

- [x] 2.1  **Create `transport/tools.py` skeleton with `register_tools`.**
  Create `tools.py` with module-level config setup (`Config.from_env()` once),
  the necessary dual-path imports from `registry`, `lifecycle`, `captain_engine`,
  `captain`, `academy`, `files`, `podman`, `constants`, `crew`. Define the
  `register_tools(mcp_instance, caddy_portal, dashboard_gate)` function stub
  (empty body for now). Verify: `python3 -c "import transport.tools"` exits 0.
  No tests yet — skeleton only.

- [x] 2.2  **Move helper functions to `tools.py`.**
  Move from `server.py` to `tools.py` (these are used only by tools and
  do not belong to captain_engine):
  - `_registry_guard(fn)` decorator (line ~2316)
  - `_validate_model(model)` (line ~406)
  - `_bg_prewarm(crew, crew_id)` and inner `_run()` (line ~2930)
  - `_schedule_cancel(job_id, crew_id)` (line ~4219)
  - `_schedule_list(crew_id)` (line ~4287)
  `server.py` adds re-export imports for these names.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.3  **Move `crews()` and `resource_compositions()` tools to `tools.py`.**
  Register them inside `register_tools` using `mcp_instance.tool()` and
  `mcp_instance.resource(...)` decorators applied programmatically. Preserve all
  docstrings and decorator arguments exactly. `caddy_portal` and `dashboard_gate`
  are closure-captured from the `register_tools` arguments.
  `server.py` re-exports `crews` and `resource_compositions` by name.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.4  **Move `launch()` tool to `tools.py`.**
  `launch()` references `_caddy_portal`, `_dashboard_gate`, `GA_MAX_CREWS`,
  `COMPOSITION_REGISTRY`, `CREW_CONTAINER_PREFIX`, `cfg.ga_portal_tls_mode`,
  `cfg.ga_host_url`. These are resolved from `tools.py`'s own `cfg` singleton
  and the injected `caddy_portal` / `dashboard_gate` parameters. Test: run
  `pytest tests/unit/test_server.py -k "launch" -q` green.
  `server.py` re-exports `launch`.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.5  **Move `supply()`, `evac()`, `nuke()` tools to `tools.py`.**
  `nuke()` references `_caddy_portal`, `_dashboard_gate`, `_captain_order_locks`,
  `_captain_order_locks_lock` (the last two from `captain.py`). Import
  `_captain_order_locks`, `_captain_order_locks_lock` from `captain`.
  `server.py` re-exports `supply`, `evac`, `nuke`.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.6  **Move `captain()` and `schedule()` tools to `tools.py`.**
  `captain()` delegates to `_captain_do_order` / `_captain_do_status` /
  `_captain_do_stop` imported from `captain_engine`. `schedule()` uses
  `_schedule_cancel`, `_schedule_list`, `_bg_prewarm`, `_is_memory_pressure_refusal`,
  `_MemoryPressureSkip`, `_MEMORY_PRESSURE_MARKER` (from `captain_engine`).
  `server.py` re-exports `captain`, `schedule`.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.7  **Move `dispatch()`, `steer()`, `pickup()` tools to `tools.py`.**
  `dispatch()` uses `_validate_model`, `_validate_agent`, `_dispatch_batch`,
  `_resolve_dispatch_slot`, `_crew_api_with_recovery`, `_ensure_crew_running`,
  `_require_crew`, `_task_timestamps`, `_task_timestamps_lock`,
  `_record_last_task_at`. `pickup()` uses `_pickup_batch`, `_pickup_single`,
  `_pickup_list`, `_find_batch_by_task_ids`, `_update_batch_status`,
  `_skim_all_mailboxes`, `PERSONA_ALLOWLIST`.
  `server.py` re-exports `dispatch`, `steer`, `pickup`.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.8  **Move resource functions to `tools.py`.**
  Move `resource_agents()`, `resource_orders()`, `resource_orders_by_name()`,
  `resource_version()`, `resource_jobs()` to `tools.py`. Register them inside
  `register_tools`. `resource_version()` needs `TRANSPORT_VERSION`; import it
  from `lifecycle` (which re-exports it) or define it fresh via
  `_read_transport_version()` duplicated into `tools.py`. Preferred: import
  `TRANSPORT_VERSION` from `lifecycle` to avoid duplication.
  `server.py` re-exports the resource function names.
  Verify: `pytest tests/unit/ -q` green.

- [x] 2.9  **Wire `register_tools` in `server.py`.**
  After creating the `mcp` instance and the `_caddy_portal` / `_dashboard_gate`
  objects in `server.py`, call:
  ```python
  from transport.tools import register_tools
  register_tools(mcp, _caddy_portal, _dashboard_gate)
  ```
  (or the flat-path equivalent). Ensure this call happens BEFORE
  `mcp.streamable_http_app(...)` is called in `__main__`. Verify that the
  OpenAPI schema generation in `__main__` still references the correct handler
  callables.
  Verify: `pytest tests/unit/ -q` green. Run a smoke check:
  `python3 -c "import transport.server"` exits 0.

---

## 3. Move login HTTP handlers to `transport/login.py`

Moves the ten HTTP route handlers and their local helpers out of `server.py`
and into `login.py` alongside the `LoginFlow` hierarchy they delegate to.

- [x] 3.1  **Move login helper functions to `login.py`.**
  Move from `server.py` to `login.py`:
  - `_warn_inert_backend_settings()` (line ~1873)
  - `_backend_enabled(backend)` (line ~1899)
  - `_backend_not_enabled_message(backend)` (line ~1910)
  These are used only by the login handlers moved in 3.2. `login.py` already
  imports `Config` and `security`; add any additional imports needed.
  `server.py` adds re-exports for these three names.
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.2  **Move kiro login/logout handlers to `login.py`.**
  Move from `server.py`:
  - `_handle_login_post(request)` (line ~1693)
  - `_handle_login_get(request)` (line ~1736)
  - `_handle_logout_post(request)` (line ~1801)
  These handlers use `login.KIRO_FLOW`, `_read_auth_file`, `_write_auth_file`,
  `_inject_auth`, `_initiate_login`, `registry`, `_get_podman`, `logger`,
  `_security`, `_request_source`, `SCRIPTS_DIR`, `KIRO_CLI_DB`. All these are
  available from `lifecycle` or the existing `login.py` imports.
  `server.py` re-exports `_handle_login_post`, `_handle_login_get`,
  `_handle_logout_post` for test backwards-compatibility.
  `BearerAuthMiddleware` wiring in `server.py` is unchanged — it still
  references the same callable names (now re-exported from `login`).
  Verify: `pytest tests/unit/test_lifecycle.py -q` green.
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.3  **Move claude login/logout handlers to `login.py`.**
  Move from `server.py`:
  - `_handle_claude_login_post(request)` (line ~1917)
  - `_handle_claude_login_get(request)` (line ~1964)
  - `_handle_claude_login_code_post(request)` (line ~2030)
  - `_handle_claude_logout_post(request)` (line ~2067)
  These use `login.CLAUDE_FLOW`, `_claude_auth_exists`, `_write_claude_auth_file`,
  `_inject_claude_auth`, `_initiate_claude_login`, `_security`, `_request_source`.
  `server.py` re-exports all four handler names.
  Verify: `pytest tests/unit/ -q` green.

- [x] 3.4  **Move codex login/logout handlers to `login.py`.**
  Move from `server.py`:
  - `_handle_codex_login_post(request)` (line ~2141)
  - `_handle_codex_login_get(request)` (line ~2188)
  - `_handle_codex_logout_post(request)` (line ~2244)
  These use `login.CODEX_FLOW`, `_codex_auth_exists`, `_inject_codex_auth`,
  `_initiate_codex_login`, `_security`, `_request_source`.
  `server.py` re-exports all three handler names.
  Verify: `pytest tests/unit/ -q` green.

---

## 4. Cleanup

- [x] 4.1  **Audit re-exports in `server.py` and remove those with no test coverage.**
  Run:
  ```
  grep -r "server\._steer_captain\|server\._dispatch_captain\|server\._captain_do\|
           server\._MemoryPressure\|server\.crews\|server\.launch\|server\.dispatch\|
           server\.pickup\|server\.steer\|server\.nuke\|server\.captain\|server\.schedule\|
           server\.supply\|server\.evac\|server\._validate_model\|server\._registry_guard\|
           server\._handle_login\|server\._handle_logout\|server\._handle_claude\|
           server\._handle_codex\|server\._warn_inert\|server\._backend_enabled" tests/
  ```
  Keep re-exports for any name that appears in test patches. Remove re-exports
  that appear nowhere in tests. Document which re-exports were retained and why.
  Verify: `pytest tests/unit/ -q` green.

- [x] 4.2  **Update module-level docstrings.**
  - `server.py`: update to describe its remaining scope (proxy handlers, mcp
    wiring, middleware stack, `__main__`). Remove references to MCP tools,
    captain engine, or login handlers.
  - `captain_engine.py`: write a module docstring describing the captain
    dispatch/steer engine and its dependency boundary.
  - `tools.py`: write a module docstring describing the MCP tool registry
    and the `register_tools` entry point.
  - `login.py`: extend docstring to mention the HTTP handlers and the
    dependency on the `LoginFlow` singletons.
  Verify: `pytest tests/unit/ -q` green (docstring-only changes; no logic
  regressions).

- [x] 4.3  **Verify final line counts and import graph.**
  Run `wc -l transport/server.py transport/tools.py transport/captain_engine.py transport/login.py`
  and confirm:
  - `server.py` ≤ 1 600 lines
  - `tools.py` ~1 800–2 200 lines
  - `captain_engine.py` ~600–750 lines
  - `login.py` ~1 100–1 300 lines
  Confirm no circular imports: `python3 -c "import transport.captain_engine; import transport.tools; import transport.login; import transport.server"` exits 0.
  Confirm monitors no longer does a deferred import from server:
  `grep -n "from server import\|from transport.server import" transport/monitors.py` returns nothing.
  Verify: `pytest tests/unit/ -q` green (final clean pass).
