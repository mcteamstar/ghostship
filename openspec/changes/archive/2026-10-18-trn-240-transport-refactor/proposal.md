# Proposal

**Plane ticket:** TRN-240

## Why

The transport has grown organically into a procedural codebase. `server.py`
(5128 lines, 60+ top-level functions, one class) and `lifecycle.py` (4239
lines, 80+ top-level functions, one exception class) are flat collections of
module-level functions sharing state through global variables and a single
JSON-backed registry dict. The domain has clear objects — crews, login flows,
the registry, the launcher state machine — but none of them are modelled as
classes.

Measured problems from the actual code:

**Global state sprawl.** The registry dict (`_registry_lock` + `_load_registry`
+ `_save_registry`) is accessed in 83 places across five files. The pattern
`with _registry_lock: reg = _load_registry(); ...; _save_registry(reg)` appears
43 times in `server.py`, 17 times in `lifecycle.py`, 13 times in `monitors.py`,
7 times in `registry.py`, and 3 times in `captain.py`. Every caller replicates
the same three-step read-modify-write pattern with no shared abstraction.

**Crew dict proliferation.** The crew data structure is a raw `dict` accessed
via string keys (`crew["container"]`, `crew.get("cookie")`, etc.) at 51+
call sites across `server.py`, `lifecycle.py`, and `files.py`. There is no
type safety, no documentation of what keys are valid, and no centralised place
to add methods that operate on crew state.

**Login flow triplication.** Three structurally identical login device-flows
(kiro, claude, codex) each duplicate the same six-phase state machine:
sentinel-under-lock → start container → wait for binary → PTY exec → 45-second
read loop → finalise. Each backend has its own `_pending` dict, its own lock,
its own `_initiate_*`, `_poll_*`, `_abort_*`, `_start_*_container`,
`_nuke_*_container`, `_*_auth_file_path`, `_*_auth_exists`, `_write_*_auth_file`,
`_inject_*_auth`. Zero code sharing across the three.

**Academy copy duplication.** `_copy_agents`, `_copy_skills`, `_copy_steering`
are structurally the same function (source dir → manifest filter → tar → archive
put) with different source paths. `_inject_policy` uses the same container exec
pattern but with signing steps.

**Launcher fragmentation.** The "bring a crew to ready state" operation is
fragmented across `_ensure_crew_running` (320+ lines, lifecycle.py:747),
`_finish_crew_setup` (240+ lines, lifecycle.py:2168), and
`_reconcile_registry` (120+ lines, lifecycle.py:1769). These three functions
collectively own the crew launch state machine but call each other at arm's
length, share mutable globals, and cannot be tested in isolation without
mocking the entire module.

## What Changes

Introduce classes at the five natural object boundaries. No behaviour changes,
no API changes. The goal is encapsulation of identity and state, not file
splitting.

### `Crew` dataclass

Replace the raw `dict` passed through 51+ call sites with a typed `@dataclass`.
Fields: `container`, `volume`, `home_volume`, `cookie`, `internal_cookie`,
`composition`, `acp_backend`, `status`, `created_at`, `last_used`,
`warm_until`, `enrolled_agents`, `admin_secret_id`, `policy_version`,
`policy_signing_key_id`, `crew_image_version`, `port`. Methods:
`to_dict()`, `from_dict(cls, d)`, `is_idle(timeout_secs)`, `is_warm()`,
`gateway_url()`.

### `CrewRegistry`

Wrap the global `_registry_lock` + `_load_registry` + `_save_registry` pattern
(83 call sites). Implement `get(crew_id)`, `put(crew_id, crew)`, `remove(crew_id)`,
`list()` and a context manager for atomic read-modify-write. Delegate all
schedule, batch, and secret helpers to the same class interface. Lives in
`transport/registry.py` alongside the existing helpers.

### `LoginFlow` ABC + three subclasses

Abstract base with the six-phase flow state machine template: `initiate()`,
`poll()`, `abort()`. Backend-specific subclasses (`KiroLoginFlow`,
`ClaudeLoginFlow`, `CodexLoginFlow`) override only the parts that differ
(binary name, URL patterns, prompt patterns, auth-injection method). Shared
logic — TOCTOU sentinel, PTY exec via `_run_pty_login_flow`, drain thread,
expiry checks — lives in the base class. Lives in `transport/login.py`.

### `AcademyLoader`

Replace `_copy_agents`, `_copy_skills`, `_copy_steering` with a single class
that takes `(podman, container, composition_entry)` and calls `copy(kind)` for
each. The four kinds are `agents`, `skills`, `steering`, and `policy` (policy
has signing steps; `copy("policy", signing_key=...)` covers that). Lives in
`transport/academy.py` (already exists; extend it).

### `CrewLauncher`

Consolidate `_ensure_crew_running`, `_finish_crew_setup`, and the
`_reconcile_registry` restart loop into one class. Constructor takes
`(registry, podman, cfg)` — no global state. `ensure_running(crew_id)` is the
public surface; `_cold_launch`, `_warm_resume`, `_restart_stopped`, `_finish_setup`,
`_phase0/1/2` are private. Lives in `transport/launcher.py`.

### What stays as functions

`_crew_api`, `_crew_api_with_recovery`, `_probe_gateway`, `_refresh_cookie`,
`_mint_cookie`, `_mint_internal_cookie`, `_wait_gateway`, `_patch_crew_config`,
`_patch_models`, `_seed_openspec_store`, `_enroll_crew_members`, all route
handlers, all pure utilities (`_validate_model`, `_sanitise_query_string`,
`_jwt_exp`), all monitor loops (`_idle_monitor`, `_schedule_monitor`,
`_captain_monitor`). The goal is not to wrap everything.

## Non-Goals

- No behaviour or API changes — all MCP tools and REST endpoints unchanged
- No new features
- File organisation is a secondary outcome, not a primary goal

## Impact

- `transport/` — new `login.py`, `launcher.py`; extended `academy.py`,
  `registry.py`, `lifecycle.py`
- All existing tests must pass unchanged; new unit tests for each class
- `docs/architecture.md` updated to reflect the new class model
