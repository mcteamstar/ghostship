## Context

`transport/server.py` (~5750 lines as of release/0.2.1 after TRN-74–78 merged) + `transport/security.py` (already extracted in TRN-70) + `transport/config.py` (already extracted in TRN-75) + `transport/container_scripts/` (14 helper scripts baked into the crew image at `/scripts/`, extracted in TRN-74 — not part of the modularisation, stays as-is). See proposal.md for motivation. This design captures the decisions made before implementation to guide Ghost through the extraction.

## Goals / Non-Goals

**Goals:** Pure structural move. No behaviour changes. All existing tests pass after each module extraction. One commit per module.

**Non-Goals:** Fix correctness issues (F2 TOCTOU, F4 crew dict mutation — separate tickets). Change any env var names or defaults. Change any public API or MCP tool behaviour. Optimise or simplify logic while moving it.

## Module Map

**Pre-existing modules (do not create — import from them):**
- `transport/config.py` — `Config` dataclass, all env var defaults (extracted in TRN-75)
- `transport/security.py` — policy signing/verification (extracted in TRN-70)
- `transport/container_scripts/` — 14 helper scripts baked into crew images at `/scripts/` (extracted in TRN-74); these are **not** Python modules imported by server.py — they are exec'd inside crew containers via `podman exec ... python3 /scripts/name.py`; do not move or rename them

### Handler modules (own mutable state)

**`registry.py`**
- Owns: `_registry_lock`, `REGISTRY_PATH`, `_load_registry()`, `_save_registry()`, `_get_crew_schedules()`, `_upsert_crew_schedule()`, `_remove_crew_schedule()`, `_advance_next_fire_at()`, `_get_crew()`, `_touch_crew()`
- Nothing outside `registry.py` writes the registry file directly after extraction

**`lifecycle.py`**
- Owns: `_startup_events`, `_startup_events_lock`, `_recovery_locks`, `_recovery_locks_lock`, `CrewUnresponsiveError`, `_ensure_crew_running()`, `_reconcile_registry()`, `_finish_crew_setup()`, `_cleanup_crew()`, `_inject_auth()`, `_wait_gateway()`, `_copy_agents()`, `_copy_skills()`, `_copy_steering()`, `_seed_openspec_store()`, `_patch_models()`, `_load_crew_manifest()`, `_manifest_selects()`, `_substitute_env_vars()`, `_patch_crew_config()`, `_inject_policy()`, `_inject_git_identity()`, `_mint_cookie()`, `_read_auth_from_crew()`, `_reseed_crew_schedules()`, `_probe_gateway()`, `_refresh_cookie()`, `_crew_api_with_recovery()`, `_crew_api()`, `_crew_url()`, `_crew_cookie()`, `_get_recovery_lock()`, `_require_crew()`, `_validate_agent()`, `_validate_academy()`, `_cron_activity_since()`, `_cron_has_enabled_job()`, `_schedule_monitor()` body, `_idle_monitor()` body
- Depends on: `registry`, `podman`, `captain`, `config`

**`captain.py`**
- Owns: `_captain_order_locks`, `_captain_order_locks_lock`, `_CAPTAIN_MAILBOX_PATH`, `_ADMIRAL_MAILBOX_PATH`, `_CAPTAIN_CHECKIN_JOB_NAME`, `_RAVEN_GATEWAY_ORIENTATION`, `_RAVEN_STORE_RESOLUTION`, `_RAVEN_SELF_CANCEL`, `_CAPTAIN_CHECKIN_TASK`, `_resolve_orders_dir()`, `_load_order_template()`, `_substitute_placeholders()`, `_validate_captain_change_name()`, `_resolve_order_template()`, `_format_captain_mail()`, `_append_captain_mail()`, `_mail_count()`, `_read_all_mail_counts()`, `_read_all_mail_subjects()`, `_captain_jobs()`, `_captain_checkin_job()`, `_captain_order_lock()`, `_captain_standing_view()`
- Depends on: `registry`, `podman`, `config`

### Helper modules (minimal or no mutable state)

**`podman.py`**
- Owns: `PodmanClient` class (move from server.py — already a class), `ContainerRuntime` ABC (new minimal interface), `_podman` singleton + `_get_podman()`, `_http`, `_async_http` (httpx clients), `_host_memory_cache`, `_host_memory_cache_lock`, `_get_host_memory_gb()`, `_get_host_memory_gb_cached()`, `_wait_for_memory()`
- Note: `_http` and `_async_http` also used by proxy handlers in `server.py` — import from `podman` there

**`files.py`**
- Owns: `_FILE_SECRET`, `_sign_file_url()`, `_sign_upload_url()`, `_verify_file_token()`, `_resolve_public_url_base()`, `_build_outer_transfer_tar()`, `_cleanup_transfer_stage()`, `_transfer_upload()`, `_TarMemberStream`, `_ResponseChunkReader`, `_handle_file_get()`, `_handle_file_put()`; TRN-74 replaced inline shell script constants with calls to `/scripts/transfer_raw.py` and `/scripts/transfer_cleanup.py` — no inline script constants remain
- Depends on: `podman`, `registry`, `config`

### Thin orchestration (stays in server.py)

- ASGI app construction, route definitions, middleware wiring
- MCP tool registration (`@mcp.tool` decorators): `crews`, `launch`, `supply`, `evac`, `nuke`, `captain`, `schedule`, `dispatch`, `steer`, `pickup`
- MCP resource registration: `transport://agents`, `transport://orders`, `transport://compositions`, `transport://jobs`, `transport://version`
- Login state machine: `_login_pending`, `_login_pending_lock`, `_handle_login_post()`, `_handle_login_get()`, `_handle_logout_post()`, `_start_login_container()`, `_nuke_login_container()`, `_initiate_login()`
- Background thread starts: `_schedule_monitor`, `_idle_monitor` (loop bodies move to `lifecycle.py`, thread-start calls stay here)
- HTTP proxy handlers: `_handle_crew_ui_proxy()`, `_handle_crew_api_proxy()`, `_extract_crew_proxy_parts()`, `_handle_version_get()`, `_handle_health()`
- `BearerAuthMiddleware`, `SecurityHeadersMiddleware` (or move auth middleware to `security.py`)

## Global State Ownership

| Global | Owner | Rationale |
|--------|-------|-----------|
| `_registry_lock` | `registry.py` | Guards registry file writes |
| `_startup_events` | `lifecycle.py` | Serialises concurrent container restarts |
| `_startup_events_lock` | `lifecycle.py` | Guards `_startup_events` dict |
| `_recovery_locks` | `lifecycle.py` | Per-crew lock for `_crew_api_with_recovery` |
| `_recovery_locks_lock` | `lifecycle.py` | Guards `_recovery_locks` dict |
| `_captain_order_locks` | `captain.py` | Per-crew lock for captain mail |
| `_captain_order_locks_lock` | `captain.py` | Guards `_captain_order_locks` dict |
| `_podman` singleton | `podman.py` | Single PodmanClient instance |
| `_http`, `_async_http` | `podman.py` | Shared HTTP clients |
| `_host_memory_cache` | `podman.py` | Cached memory reading |
| `_host_memory_cache_lock` | `podman.py` | Guards cache |
| `_login_pending` | `server.py` | Login state machine — stays in server |
| `_login_pending_lock` | `server.py` | Guards login state |
| `_FILE_SECRET` | `files.py` | HMAC signing secret for presigned URLs |
| Config vars (GA_*, KC_*) | `config.py` | Already extracted in TRN-75 |

## Extraction Order and Containerfile

Extract in dependency order so each step leaves the codebase in a runnable state:

1. `registry.py` — no deps on other new modules
2. `podman.py` — no deps on other new modules
3. `files.py` — depends on registry + podman
4. `captain.py` — depends on registry + podman
5. `lifecycle.py` — depends on registry + podman + captain
6. `server.py` cleanup + Containerfile update

The Containerfile update (step 6) switches from:
```
COPY server.py .
COPY security.py .
COPY config.py .
```
to:
```
COPY transport/ /app/
```
This requires `transport/__init__.py` to exist (added in step 1). All test imports of `transport.server` continue to work; new imports like `transport.registry` work from step 1 onwards.

Note: `transport/container_scripts/` must be excluded from the transport image — those scripts are baked into the **crew image** by `install.sh` (via `crews/_base/admission/Containerfile`), not the transport image. Add a `.dockerignore` or use an explicit `COPY transport/*.py /app/` + `COPY transport/*/ /app/` pattern that excludes `container_scripts/`. The simplest approach: `COPY transport/ /app/` then `RUN rm -rf /app/container_scripts/` in the Containerfile. Alternatively keep the individual `COPY` lines for each module.

## Constraints

- **No behaviour changes** — if in doubt, move it verbatim
- **One commit per module** — commit after each extraction with tests passing
- **Tests must pass at each step** — run `bash tests/run.sh --unit` after each module
- **Base on latest `release/0.2.1`** after TRN-74 has landed (TRN-75, TRN-76, TRN-77, TRN-78, TRN-82 already landed)
- **`config.py` and `security.py` are pre-existing** — do not recreate them; new modules import from them

## Risks / Trade-offs

- Circular imports: `lifecycle.py` imports from `captain.py` for mail-on-login. `captain.py` must not import from `lifecycle.py`. Verify no cycle exists before committing each module.
- `_schedule_monitor` and `_idle_monitor` use both lifecycle and registry — their loop bodies move to `lifecycle.py`, thread start stays in `server.py`. If a function is used by both, it stays in the lower-dependency module and is imported upward.
- TRN-71 touching many files will conflict with any concurrent `server.py` changes. Sequence after TRN-74 lands; rebase on latest `release/0.2.1` before starting.
