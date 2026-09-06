## Why

The transport codebase has grown substantially during the 0.3.0 cycle: `server.py` is 4531 lines, `lifecycle.py` is 1884 lines, `files.py` is 794 lines, and `captain.py` is 601 lines. The result is files that are difficult to navigate, contain duplicated patterns, and have dead code that misleads readers. This cleanup pass runs before 0.4.0 development begins, when the surface area of the codebase will expand again.

_Assessed against `release/0.3.1` (post TRN-110, TRN-115). Line counts unchanged since 0.3.0; all tasks below remain undone._

## What Changes

- **Modularisation**: Extract cohesive sub-domains from `server.py` and `lifecycle.py` into their own modules. Identified candidates:
  - MCP tool handlers (routes currently scattered through `server.py`)
  - Auth middleware (`TransportSecretMiddleware`, `BearerAuthMiddleware`, `SecurityHeadersMiddleware`, and supporting helpers currently mixed into `server.py`)
  - Caddy management (`_caddy_register_crew`, `_caddy_deregister_crew`, port allocation helpers — currently in `server.py`)
  - Schedule/idle monitors (`_schedule_monitor`, `_idle_monitor`, and their helpers — currently in `lifecycle.py`)
  - Captain standing orders (`_load_order_template`, `_format_captain_mail`, `_skim_all_mailboxes`, check-in job helpers — currently in `captain.py`, 601 lines and growing with new templates)
- **Dead code removal**:
  - `_inject_git_identity` in `lifecycle.py` is a documented no-op; remove the function body and its call site in `_finish_crew_setup`
  - `KIROCREW_ALLOW_UNSANDBOXED` env var in `server.py` is redundant with `sandbox: off` config (FINDING-3 from the 0.3.0 review); remove the env injection
- **Deduplication** (targeted, small PRs):
  - Auth header validation logic is repeated across `BearerAuthMiddleware` and call sites; consolidate into a single helper
  - Registry lock (`_registry_lock`) acquire/release patterns appear across `lifecycle.py` and `server.py`; document or unify the conventions so readers can trace them
  - `podman.container_exec` / `container_exec_checked` wrappers have similar error-handling inline at call sites; identify whether a shared wrapper is appropriate
- **Simplification and internal documentation**:
  - `_crew_api_with_recovery` (three-phase recovery: 503 task-spawning transient, 401/403 cookie refresh, connection error restart) is well-implemented but its nested exception handling is hard to follow and makes mutation testing difficult; add inline phase labels and extract each phase into a helper function
  - `_initiate_login` PTY state machine (~185 lines in `server.py`): add a phase header comment structure matching `_crew_api_with_recovery`, and document the reason for the 45-second deadline and the `select`-based read loop
  - `_schedule_monitor` and `_idle_monitor` loops in `lifecycle.py`: document exit conditions and the sleep intervals used
- **Test coverage**:
  - Add coverage for `_handle_crew_ui_proxy` upstream error paths (noted as a gap in the 0.3.0 review)
  - Add coverage for Caddy-off TLS mode dashboard URL construction (noted as a gap in the 0.3.0 review)

No behaviour changes. All changes are internal to the transport package.

## Capabilities

### New Capabilities

_None — this is a pure refactor._

### Modified Capabilities

_None — no spec-level behaviour changes. `skip_specs: true` is set in `.openspec.yaml`._

## Impact

- `transport/server.py`, `transport/lifecycle.py`, `transport/files.py` (primary)
- New modules extracted from the above (e.g. `transport/auth.py`, `transport/caddy.py`, `transport/monitors.py`) if modularisation tasks proceed
- `tests/unit/test_server.py`, `tests/unit/test_lifecycle.py` — mocking paths change if internal structure is reorganised
- No API changes, no container image changes, no config schema changes
