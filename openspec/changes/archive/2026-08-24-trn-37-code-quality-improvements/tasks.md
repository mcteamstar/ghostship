## 1. Preparation

- [x] 1.1 Audit the MCP library's tool-dispatch path — grep for `run_in_executor`, `asyncio`, `thread_pool` in the installed `mcp` package to determine whether sync tool handlers run on the event loop or in a thread-pool executor (F-03). Record the finding as a code comment adjacent to the `time.sleep(min(3, remaining))` calls in `pickup` / `_pickup_list`.
- [x] 1.2 Confirm `container_exec_pty` call sites — grep `server.py` for calls to `container_exec_pty` (the non-stdin overload) to verify zero callers before removal (D-08 / F-05).
- [x] 1.3 Confirm `_login_flags` / `_initiate_login` call sites — grep `server.py` for callers of both functions; confirm they are dead code before deletion.

## 2. Critical fixes (HIGH — must land before 0.1.0)

- [x] 2.1 Add `_NEVER_FIRE_AT: float = 9_999_999_999.0` constant at module level (D-01 / F-01).
- [x] 2.2 Replace all `float("inf")` occurrences in `_advance_next_fire_at` (one-shot branch, unknown-type branch) with `_NEVER_FIRE_AT` (F-01).
- [x] 2.3 Replace the `next_fire_at` default and comparison in `_schedule_monitor` (`sched.get("next_fire_at", float("inf"))`) with `_NEVER_FIRE_AT` (F-01).
- [x] 2.4 Add `_host_memory_cache_lock = threading.Lock()` alongside `_host_memory_cache` at module level (D-02 / F-02).
- [x] 2.5 Wrap the read (check + return) and write in `_get_host_memory_gb_cached` inside `with _host_memory_cache_lock:` blocks — keep the lock scope tight (D-02 / F-02).
- [x] 2.6 Fix `_advance_next_fire_at` cron branch: replace `time.time() + 60` with `croniter(job["cron_expr"], time.time()).get_next(float)`, catching any `croniter` exception and falling back to `time.time() + 60` with a `logger.warning` (D-04 / F-08).
- [x] 2.7 Apply F-03 finding: if sync tools run on the event loop, convert `pickup` / `_pickup_list` `time.sleep(min(3, remaining))` to `await asyncio.sleep(...)` and mark handlers `async def`; if they run in a thread-pool, add a comment confirming `time.sleep` is safe and no code change is needed (D-03 / F-03).

## 3. Threading and correctness fixes (MEDIUM)

- [x] 3.1 Refactor `_append_captain_mail` to consolidate the two `_registry_lock` acquisitions into a single read-acquire block for `signing_secret` / `supersedes_id`, keeping `_format_captain_mail` (pure computation) and `container_exec_checked` (I/O) outside the lock (D-05 / F-06).
- [x] 3.2 Replace the two `assert` guards in `nuke` with explicit `RuntimeError` raises that include the offending value in the message; add a `RuntimeError` catch alongside the existing `KeyError` catch at the call site if applicable (D-06 / F-09).
- [x] 3.3 Call `_patch_crew_config(podman, container)` in `_reconcile_registry` immediately after `_wait_gateway` returns `True` in the stopped-crew restart branch, before the `updates[cid]` write-back (D-07 / F-10).

## 4. Dead code removal

- [x] 4.1 Delete `container_exec_pty` (the PTY-without-stdin overload) from `PodmanClient` — the `container_exec_pty_stdin` overload replaces it (F-05). Confirm zero call sites from task 1.2 first.
- [x] 4.2 Delete `_login_flags()` and `_initiate_login()` from `server.py` (confirmed dead in task 1.3). Remove any `import shlex` line that becomes unused as a result.

## 5. Minor quality improvements (LOW)

- [x] 5.1 Improve `_load_or_create_file_secret` warning to include `secret_path` in the message: `"Could not persist file secret to %s: %s", secret_path, e` (F-11).
- [x] 5.2 Add `encoding='utf-8'` to `open()` calls in inline container Python scripts in `_copy_agents` and `_copy_skills` (F-12). Note: resolved by replacing the base64/exec approach with `container_archive_put` in tasks 5.4/5.5 — the inline scripts are gone.
- [x] 5.3 Add `container_archive_put` method to `PodmanClient` using `PUT /libpod/containers/{name}/archive?path=<dest>` with a tar body. Verify the method doesn't already exist before adding (D-09 / F-13). Note: already existed in PodmanClient — no addition needed.
- [x] 5.4 Refactor `_copy_agents` to build an in-memory tar per agent file and call `container_archive_put` instead of embedding base64 in an f-string (D-09 / F-13).
- [x] 5.5 Refactor `_copy_skills` similarly — build a tar per SKILL.md file and call `container_archive_put` (D-09 / F-13).
- [x] 5.6 Add a comment on the `HOST = os.environ.get("HOST", "0.0.0.0")` line explaining the variable: default binds all interfaces; set to `127.0.0.1` to restrict to loopback (F-14).

## 6. Verification

- [x] 6.1 Run the existing test suite (`pytest tests/ -x -q`) and confirm no regressions.
- [x] 6.2 Manually verify `json.dumps({"next_fire_at": _NEVER_FIRE_AT})` round-trips without error in a Python REPL or quick smoke test.
- [x] 6.3 Confirm `openspec validate` passes on the change after implementation.
