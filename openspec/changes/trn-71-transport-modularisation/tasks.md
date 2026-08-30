## Prerequisites

- [x] 0.1 Confirm `release/0.2.1` is at latest — TRN-74, 75, 76, 77, 78, 82 all landed; rebase on latest before starting
- [x] 0.2 Add `transport/__init__.py` (empty file to make transport a package)

## 1. Extract registry.py

- [x] 1.1 Create `transport/registry.py` with `_registry_lock`, `REGISTRY_PATH`, `_load_registry()`, `_save_registry()`, `_get_crew_schedules()`, `_upsert_crew_schedule()`, `_remove_crew_schedule()`, `_advance_next_fire_at()`, `_get_crew()`, `_touch_crew()`
- [x] 1.2 Update `server.py` to import from `registry` — remove the moved definitions
- [x] 1.3 Run `bash tests/run.sh --unit` — all pass
- [x] 1.4 Commit: `refactor: extract registry.py from server.py`

## 2. Extract podman.py

- [x] 2.1 Create `transport/podman.py` with `PodmanClient` class, `ContainerRuntime` ABC, `_podman` singleton + `_get_podman()`, `_http`, `_async_http`, `_host_memory_cache`, `_host_memory_cache_lock`, `_get_host_memory_gb()`, `_get_host_memory_gb_cached()`, `_wait_for_memory()`
- [x] 2.2 Update `server.py` to import from `podman` — remove moved definitions
- [x] 2.3 Run `bash tests/run.sh --unit` — all pass
- [x] 2.4 Commit: `refactor: extract podman.py from server.py`

## 3. Extract files.py

- [x] 3.1 Create `transport/files.py` with `_FILE_SECRET`, `_sign_file_url()`, `_sign_upload_url()`, `_verify_file_token()`, `_resolve_public_url_base()`, `_build_outer_transfer_tar()`, `_cleanup_transfer_stage()`, `_transfer_upload()`, `_TarMemberStream`, `_ResponseChunkReader`, `_handle_file_get()`, `_handle_file_put()`; remove now-unused transfer script constants if TRN-74 has landed
- [x] 3.2 Update `server.py` to import from `files` — remove moved definitions
- [x] 3.3 Run `bash tests/run.sh --unit` — all pass
- [x] 3.4 Commit: `refactor: extract files.py from server.py`

## 4. Extract captain.py

- [x] 4.1 Create `transport/captain.py` with `_captain_order_locks`, `_captain_order_locks_lock`, captain constants (`_CAPTAIN_MAILBOX_PATH`, `_ADMIRAL_MAILBOX_PATH`, `_CAPTAIN_CHECKIN_JOB_NAME`, `_RAVEN_*`, `_CAPTAIN_CHECKIN_TASK`), `_resolve_orders_dir()`, `_load_order_template()`, `_substitute_placeholders()`, `_validate_captain_change_name()`, `_resolve_order_template()`, `_format_captain_mail()`, `_append_captain_mail()`, `_mail_count()`, `_read_all_mail_counts()`, `_read_all_mail_subjects()`, `_captain_jobs()`, `_captain_checkin_job()`, `_captain_order_lock()`, `_captain_standing_view()`
- [x] 4.2 Update `server.py` to import from `captain` — remove moved definitions
- [x] 4.3 Verify no circular imports between `captain` → `registry`/`podman` and back
- [x] 4.4 Run `bash tests/run.sh --unit` — all pass
- [x] 4.5 Commit: `refactor: extract captain.py from server.py`

## 5. Extract lifecycle.py

- [ ] 5.1 Create `transport/lifecycle.py` with `_startup_events`, `_startup_events_lock`, `_recovery_locks`, `_recovery_locks_lock`, `CrewUnresponsiveError`, `_ensure_crew_running()`, `_reconcile_registry()`, `_finish_crew_setup()`, `_cleanup_crew()`, `_inject_auth()`, `_wait_gateway()`, `_copy_agents()`, `_copy_skills()`, `_copy_steering()`, `_seed_openspec_store()`, `_patch_models()`, `_load_crew_manifest()`, `_manifest_selects()`, `_substitute_env_vars()`, `_patch_crew_config()`, `_inject_policy()`, `_inject_git_identity()`, `_mint_cookie()`, `_read_auth_from_crew()`, `_reseed_crew_schedules()`, `_probe_gateway()`, `_refresh_cookie()`, `_crew_api_with_recovery()`, `_crew_api()`, `_crew_url()`, `_crew_cookie()`, `_get_recovery_lock()`, `_require_crew()`, `_validate_agent()`, `_validate_academy()`, `_cron_activity_since()`, `_cron_has_enabled_job()`, `_schedule_monitor()` body, `_idle_monitor()` body
- [ ] 5.2 Update `server.py` to import from `lifecycle` — remove moved definitions; keep thread-start calls in `server.py`
- [ ] 5.3 Verify no circular imports: `lifecycle` → `registry`, `podman`, `captain`; none back
- [ ] 5.4 Run `bash tests/run.sh --unit` — all pass
- [ ] 5.5 Commit: `refactor: extract lifecycle.py from server.py`

## 6. server.py cleanup + Containerfile

- [ ] 6.1 Verify `server.py` now contains only: ASGI app, route definitions, middleware wiring, MCP tool + resource registration, login state machine, HTTP proxy handlers, background thread starts
- [ ] 6.2 Update `transport/Containerfile` — replace individual `COPY` lines (`COPY server.py .`, `COPY security.py .`, `COPY config.py .`) with `COPY transport/ /app/`; then add `RUN rm -rf /app/container_scripts/` to exclude the crew-side scripts from the transport image (those belong in the crew image via `crews/_base/admission/Containerfile`, not here)
- [ ] 6.3 Update all test files that import from `transport.server` to import from the correct new modules where needed
- [ ] 6.4 Run `bash tests/run.sh` (unit + integration) — all pass
- [ ] 6.5 Commit: `refactor: slim server.py to thin orchestration layer, update Containerfile`

## 7. Verification

- [ ] 7.1 Deploy to vm23 via servers submodule bump
- [ ] 7.2 Smoke test: launch crew, dispatch task, pickup result, nuke
