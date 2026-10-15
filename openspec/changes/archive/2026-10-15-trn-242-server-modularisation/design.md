# Design

## Context

See proposal.md. This is a file-organisation refactor following the same
zero-behaviour-change contract established by TRN-240.

### Measured current state

```
server.py        5 060 lines   proxy handlers, MCP tools, captain engine, login handlers,
                               config/globals, mcp wiring, entrypoint
lifecycle.py     3 041 lines   crew lifecycle, auth flows, batch/pickup, monitors re-exports
login.py           618 lines   LoginFlow ABC + KiroLoginFlow / ClaudeLoginFlow / CodexLoginFlow
monitors.py        826 lines   _schedule_monitor, _idle_monitor, _captain_monitor
captain.py         797 lines   captain mailbox, order templates, check-in job helpers
launcher.py        822 lines   CrewLauncher (ensure_running, finish_setup)
registry.py        587 lines   CrewRegistry, schedule/batch/secret helpers
```

### The deferred-import problem

`monitors.py::_captain_monitor` imports `_steer_captain_checkin` and
`_dispatch_captain_checkin` from `server` at *call time* (inside the loop body)
rather than at module load:

```python
try:
    from server import _steer_captain_checkin, _dispatch_captain_checkin
except ModuleNotFoundError:
    from transport.server import _steer_captain_checkin, _dispatch_captain_checkin
```

This deferred import exists solely because those two functions live in
`server.py` and `server.py` imports `monitors.py` (transitively via
`lifecycle.py`), creating a load-time cycle if they were top-level imports.
Extracting them to a leaf module breaks the cycle cleanly.

### Import graph before TRN-242

```
config ─── (zero deps)
constants ─ (zero deps)
security ── (zero deps)
crew ─────── config
registry ─── config, crew
podman ───── config, constants
captain ──── registry, podman, constants
academy ──── config, constants
login ────── config, constants                        (deps injected via lifecycle at call time)
monitors ─── podman, registry, constants
             + lifecycle functions via bind_lifecycle()
             + server._steer_captain_checkin DEFERRED (call-time import)
lifecycle ── config, security, podman, registry, crew, captain, academy,
             login, monitors, auth, caddy, dashboard, launcher
server ────── ALL of the above + openapi + mcp
```

### Import graph after TRN-242

```
captain_engine ── config, registry, captain, podman, lifecycle  (NEW leaf)
tools ─────────── config, registry, captain, captain_engine,
                  lifecycle, files, podman, academy, mcp        (NEW leaf)
login (extended) ── login (existing), lifecycle, security       (HTTP handlers added here)
monitors ────────── podman, registry, constants
                    + lifecycle functions via bind_lifecycle()
                    + captain_engine._steer_captain_checkin     (DIRECT, not deferred)
server ──────────── config, security, auth, caddy, dashboard,
                    openapi, login (HTTP handlers), tools (registers on mcp),
                    mcp, uvicorn                                 (SLIMMED)
```

---

## Goals / Non-Goals

**Goals:**
- Split `server.py` into three focused modules without any behaviour change.
- Resolve the `monitors → server` deferred import by giving captain dispatch/steer a real home.
- Each intermediate state leaves `pytest tests/unit/ -q` green.

**Non-Goals:**
- No new behaviour, no new MCP tools, no new REST endpoints.
- No changes to `crews.json` schema, REST API shape, or MCP tool signatures.
- No test migration or refactoring — tests patch names where they currently live; this change must preserve those names.
- No further OO refactoring beyond what TRN-240 already established.

---

## Decisions

### D1 — `captain_engine.py` as the new home for captain dispatch/steer

The three functions `_dispatch_captain_checkin`, `_steer_captain_checkin`, and
the `_captain_do_*` trio, together with their private helpers
(`_MemoryPressureSkip`, `_check_in_memory_pressure`, `_is_memory_pressure_refusal`,
`_mail_admiral`, `_record_memory_pressure_cycle`), form a self-contained sub-system:
they sit between the `captain()` MCP tool and `captain.py`, and they are called
by `monitors.py::_captain_monitor`. The name `captain_engine.py` mirrors the
existing `captain.py` (which owns data structures and helpers) while signalling
"this is the execution side".

**Alternative considered:** fold these into `captain.py`. Rejected — `captain.py`
explicitly must NOT import from `lifecycle` or `server` (its docstring says so):
"Must NOT import from lifecycle or server (lifecycle imports captain for
mail-on-login — the dependency runs one way)." `captain_engine.py` needs to
import from `lifecycle` (for `_ensure_crew_running`, `_crew_api_with_recovery`,
`_to_crew`, `_write_dashboard_cookie`, `_get_podman`) so it cannot be merged
into `captain.py` without violating that invariant.

### D2 — `tools.py` registers its tools against the `mcp` instance passed from `server.py`

MCP tools are registered via the `@mcp.tool()` decorator, which means the
decorated functions must see the same `mcp` object that `server.py` passes to
`mcp.streamable_http_app(...)`. Options:

a) Import the `mcp` object from `server` into `tools.py` — creates a cycle.  
b) Create `mcp` in a separate `transport/mcp_server.py` leaf and import from both — feasible but adds another file.  
c) Pass `mcp` as a parameter to a `register_tools(mcp)` function in `tools.py` — simple, explicit.  
d) Have `tools.py` define functions without decorators; `server.py` applies `@mcp.tool()` decorators inline — impractical at scale.

**Decision: option (c).** `tools.py` exports `register_tools(mcp_instance)`.
`server.py` calls `register_tools(mcp)` after creating the `mcp` object.
The tool functions themselves are module-level in `tools.py`; the decorator
is applied inside `register_tools` using `mcp_instance.tool()(fn)`.

This pattern is already how `mcp_instance.streamable_http_app(...)` is called —
`server.py` owns the `mcp` lifecycle, other modules just use it.

**Invariant:** MCP tool introspection (name, signature, docstring) is
unchanged — `functools.wraps` is applied as before.

### D3 — Login HTTP handlers move to `login.py`, not a new `transport/login_handlers.py`

The six HTTP handlers (`_handle_login_post`, `_handle_login_get`,
`_handle_logout_post`, `_handle_claude_login_post`, `_handle_claude_login_get`,
`_handle_claude_login_code_post`, `_handle_claude_logout_post`,
`_handle_codex_login_post`, `_handle_codex_login_get`,
`_handle_codex_logout_post`) each call one or two functions from `login.py`
(via the `KIRO_FLOW`, `CLAUDE_FLOW`, `CODEX_FLOW` singletons) and from
`lifecycle.py` (for auth file helpers, `_inject_auth`, `_read_auth_file`, etc.).
The handlers are thin wrappers with no independent state.

**Rationale:** `login.py` already owns the `LoginFlow` hierarchy and the
three singletons. The handlers are the HTTP surface of those singletons.
Keeping them together avoids a new file for ~600 lines and keeps all
login-domain code in one place.

**Helpers that travel with the handlers:** `_warn_inert_backend_settings`,
`_backend_enabled`, `_backend_not_enabled_message` — used exclusively by the
login handlers. They move to `login.py` as well.

`server.py` imports the handler callables from `login` and registers them with
`BearerAuthMiddleware` exactly as today, so the middleware wiring is unchanged.

### D4 — Global constants/config in `tools.py` are imported from `config.py` / `lifecycle.py` not redeclared

`tools.py` uses: `GA_MAX_CREWS`, `GA_MAX_ACTIVE_CREWS`, `GA_RESOURCE_CRITICAL_GB`,
`GA_SPAWN_PRESSURE_ESCALATE_CYCLES`, `COMPOSITION_REGISTRY`, `CREW_CONTAINER_PREFIX`,
`PERSONA_ALLOWLIST`, `_validate_model`, `_registry_guard`. Rather than
re-reading `Config.from_env()` in `tools.py`, these are imported from
`lifecycle` (which re-exports them as module-level names) or from `config` /
`academy` / `constants` directly. `_validate_model` stays in `server.py`
(used only by tools) and is passed to `tools.py` via the `register_tools`
call, OR `tools.py` creates its own `cfg` singleton for the handful of values
it needs. Because `tools.py` is a pure leaf imported by `server.py`, reading
`Config.from_env()` once in `tools.py` at import time is safe and mirrors the
pattern already in `lifecycle.py`.

**Decision:** `tools.py` calls `Config.from_env()` once at module level, same
as `lifecycle.py`. This is already the established pattern; no Config singleton
sharing mechanism exists.

### D5 — Extraction order: `captain_engine.py` first, then `tools.py`, then login handlers

1. `captain_engine.py` — breaks the `monitors → server` deferred import. Low
   risk: ~700 lines, self-contained, clear dependency boundary.
2. `tools.py` + `register_tools(mcp)` — larger but mechanical: move ~2 200 lines
   of MCP tool functions; `server.py` calls `register_tools(mcp)`.
3. Login HTTP handlers to `login.py` — touches test surface (test patches on
   `server._handle_login_post` etc. must move to `login._handle_login_post`).
   Kept last so the captain and tools extractions are independently testable
   before touching the login handler test surface.

### D6 — `server.py` re-exports extracted names for backwards-compatible patching

Tests that patch `server._steer_captain_checkin`, `server._dispatch_captain_checkin`,
`server._captain_do_order`, `server._validate_model`, etc. must continue to
work. The approach is the same as TRN-240's one-line wrapper pattern:
`server.py` re-imports these names after the extraction so `patch('server.X')`
still resolves.

```python
# server.py — re-exports after extraction
from transport.captain_engine import (  # noqa: F401
    _dispatch_captain_checkin,
    _steer_captain_checkin,
    _captain_do_order,
    _captain_do_status,
    _captain_do_stop,
    _MemoryPressureSkip,
    _MEMORY_PRESSURE_MARKER,
)
from transport.tools import register_tools  # noqa: F401
```

Login handler re-exports in `server.py` for test backwards-compatibility:
```python
from transport.login import (  # noqa: F401
    _handle_login_post,
    _handle_login_get,
    _handle_logout_post,
    _handle_claude_login_post,
    ...
)
```

---

## Risks / Trade-offs

**[R1] monitors.py deferred import removal breaks if captain_engine has a
load-time cycle.** Mitigation: verify `python3 -c "import transport.captain_engine"`
succeeds before removing the deferred import from `monitors.py`. The import
graph analysis above shows no cycle.

**[R2] Tests patch `server.X` for names that move to `captain_engine` or
`tools`.** Mitigation: D6 re-exports. Run `grep -r "server\._steer\|server\._dispatch_captain\|server\._captain_do\|server\._memory_pressure\|server\.crews\|server\.launch\|server\.dispatch\|server\.pickup\|server\.steer\|server\.nuke\|server\.captain\|server\.schedule\|server\.supply\|server\.evac" tests/` before removing re-exports to confirm no test patches by the internal name.

**[R3] `login.py` grows by ~600 lines and its dependency set widens** (it will
import from `lifecycle`, `security`, and Starlette). Mitigation: `login.py`
already imports `lifecycle` lazily at call time in the flow subclasses; adding
the HTTP handlers does not change the module-load DAG.

**[R4] `tools.py` accesses `_caddy_portal` and `_dashboard_gate`** — two
object instances created in `server.py` that are not module-level constants.
The `launch()` and `nuke()` tools need them.  Mitigation: expose them via a
thin accessor module (`server.py` publishes `get_caddy_portal()` /
`get_dashboard_gate()`) or inject them into `register_tools(mcp, caddy_portal,
dashboard_gate)`. The latter is cleaner; `server.py` already creates these
objects before calling `register_tools`.

---

## Migration Plan

Each task commits independently with `pytest tests/unit/ -q` green.

### Step 1: Extract `transport/captain_engine.py`

Move from `server.py` to new `captain_engine.py`:
- `_MemoryPressureSkip`, `_MEMORY_PRESSURE_MARKER`
- `_check_in_memory_pressure`, `_is_memory_pressure_refusal`
- `_mail_admiral`, `_record_memory_pressure_cycle`
- `_dispatch_captain_checkin`, `_steer_captain_checkin`
- `_captain_do_order`, `_captain_do_status`, `_captain_do_stop`

`server.py` re-exports all of them (D6).  
Update `monitors.py` to import `_steer_captain_checkin` and
`_dispatch_captain_checkin` from `captain_engine` directly (top-level) instead
of the deferred call-time import.  
Verify: `pytest tests/unit/ -q` green; `python3 -c "import transport.captain_engine"` clean.

### Step 2: Extract `transport/tools.py`

Move from `server.py`:
- `_registry_guard`, `_validate_model`, `_bg_prewarm`
- `crews()`, `resource_compositions()`, `launch()`, `supply()`, `evac()`, `nuke()`
- `captain()`, `schedule()`, `_schedule_cancel()`, `_schedule_list()`
- `dispatch()`, `steer()`, `pickup()`
- `resource_agents()`, `resource_orders()`, `resource_orders_by_name()`,
  `resource_version()`, `resource_jobs()`

Create `register_tools(mcp_instance, caddy_portal, dashboard_gate)` in `tools.py`.  
`server.py` calls `register_tools(mcp, _caddy_portal, _dashboard_gate)`.  
`server.py` re-exports all tool function names (D6).  
Verify: `pytest tests/unit/ -q` green.

### Step 3: Move login HTTP handlers to `transport/login.py`

Move from `server.py` to `login.py`:
- `_warn_inert_backend_settings`, `_backend_enabled`, `_backend_not_enabled_message`
- `_handle_login_post`, `_handle_login_get`, `_handle_logout_post`
- `_handle_claude_login_post`, `_handle_claude_login_get`,
  `_handle_claude_login_code_post`, `_handle_claude_logout_post`
- `_handle_codex_login_post`, `_handle_codex_login_get`,
  `_handle_codex_logout_post`

`server.py` imports the handler callables from `login` and re-exports them (D6).  
`BearerAuthMiddleware` wiring in `server.py` unchanged — it still references
the same callable objects.  
Verify: `pytest tests/unit/ -q` green.

### Step 4: Cleanup

- Remove dead re-exports from `server.py` confirmed unused by test grep.
- Update module-level docstrings in all affected files.
- No test changes needed (re-exports keep all patch targets alive).

### Rollback

Each step is a single commit. Rolling back means reverting that commit; the
prior commit is always fully green.

---

## Module structure after TRN-242

```
transport/
  server.py          ~1 400 lines  proxy handlers, middleware wiring, __main__, mcp setup
  tools.py           ~2 200 lines  MCP tool functions (NEW)
  captain_engine.py    ~700 lines  captain dispatch/steer engine (NEW)
  login.py           ~1 200 lines  LoginFlow + HTTP handlers (EXTENDED from ~618)
  lifecycle.py       ~3 041 lines  crew lifecycle, auth flows, batch/pickup, monitor re-exports
  monitors.py          ~826 lines  schedule / idle / captain monitor threads
  captain.py           ~797 lines  captain mailbox helpers, order templates
  launcher.py          ~822 lines  CrewLauncher
  registry.py          ~587 lines  CrewRegistry
  auth.py              ~800 lines  middleware (unchanged)
  caddy.py             ~450 lines  CaddyPortal (unchanged)
  dashboard.py         ~475 lines  DashboardGate (unchanged)
  academy.py           ~500 lines  AcademyLoader (unchanged)
  login.py             ...         (see above)
  files.py             ~820 lines  file transfer (unchanged)
  podman.py            ~950 lines  PodmanClient (unchanged)
  config.py            ~450 lines  Config (unchanged)
  crew.py              ~200 lines  Crew dataclass (unchanged)
  constants.py          ~80 lines  shared constants (unchanged)
  security.py          ~540 lines  security helpers (unchanged)
  openapi.py           ~430 lines  OpenAPI schema generation (unchanged)
```

---

## Invariants

- All MCP tool signatures unchanged.
- All REST endpoint paths and response shapes unchanged.
- `pytest tests/unit/ -q` green after every commit.
- No new environment variables or config keys.
- No changes to `crews.json` serialisation format.
- `monitors.py` `bind_lifecycle` injection pattern preserved.
- The `monitors.py → server` deferred import is eliminated by Step 1.
- No circular imports introduced; import graph remains a DAG.
