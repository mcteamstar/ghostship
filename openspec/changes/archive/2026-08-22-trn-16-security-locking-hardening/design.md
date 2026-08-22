## Context

See proposal.md for motivation. Three areas in `transport/server.py`:

1. `_inject_auth` (line ~1550) — uses `container_exec` and checks `"injected" in result`. A Python exception raised inside the exec'd script is returned as a string by `container_exec` (non-zero exit is swallowed), so a failed inject silently returns `True` if the error message happens to contain "injected". This leaves the kiro-cli SQLite DB unseeded, causing `kirocrew token` to crash and `_mint_cookie` to return `None`.

2. `_reconcile_registry` (line ~1147) — holds `_registry_lock` across the full restart loop including `_wait_gateway(timeout=30)`. With N stopped crews on startup, the lock is held for up to `30 * N` seconds, blocking all concurrent operations.

3. `POST /login` TOCTOU (line ~1864) — `_read_auth_file()` is checked without the lock, then `_login_pending` is checked with the lock. A concurrent request can pass the auth-file check, then both requests reach the lock check — one wins, but the window exists.

## Goals / Non-Goals

**Goals:**
- Fix `_inject_auth` exit-code check (unblocks all new crew launches)
- Fix `POST /login` concurrent guard to be atomic
- Reduce `_reconcile_registry` lock hold time during startup

**Non-Goals:**
- `admiral_secret` encryption at rest (documented as acceptable for v1)
- Full test coverage of reconcile/idle paths (TRN-17 scope)
- KiroCrew DB migration handling (pre-seeded in crew image, not needed)

## Decisions

**`_inject_auth`: use `container_exec_checked`, remove string check**

`container_exec_checked` raises `CrewExecError` on non-zero exit — the exception propagates up through `_finish_crew_setup`, which already has a teardown path. No new error handling needed. The `print(f"injected {len(rows)} auth rows")` line in the injected Python stays for logging; we just stop using it as a success signal.

```python
# Before
result = podman.container_exec(container, ["python3", "-c", inject])
logger.info("Auth inject for %s: %s", container, result.strip())
return "injected" in result

# After
podman.container_exec_checked(container, ["python3", "-c", inject])
logger.info("Auth injected for %s", container)
return True
```

**`POST /login`: expand lock scope to cover both guards**

Move the `_read_auth_file()` check inside the `_login_pending_lock` block. The auth-file read is fast (file stat + read), so holding the lock for it is not a concern.

```python
# Before
if _read_auth_file():
    return 409
with _login_pending_lock:
    if _login_pending is not None:
        return 409

# After
with _login_pending_lock:
    if _read_auth_file():
        return 409
    if _login_pending is not None:
        return 409
```

**`_reconcile_registry`: release lock between per-crew restart operations**

Load the registry under the lock, snapshot the crew list, release the lock, then perform restarts outside the lock. Re-acquire the lock per-crew to write back the updated cookie/status. This matches how `_ensure_crew_running` handles per-crew events.

Risk: another operation reads a stale status between snapshot and write-back. Acceptable — reconcile only runs at startup before any external requests are being served, so concurrent writes are unlikely. If a race does occur, the worst outcome is a spurious cookie refresh on the next request, handled by existing CSRF recovery.

## Risks / Trade-offs

- `_reconcile_registry` lock narrowing is a best-effort improvement. Startup is single-threaded in practice (the server starts listening only after `_reconcile_registry` returns), so the practical impact is low. The change is still correct and reduces lock hold time for future scenarios.
- Expanding the login lock scope means `_read_auth_file()` runs under the lock. The auth file is local disk — sub-millisecond read. No meaningful contention risk.

## Migration Plan

- No data migration needed
- Deploy via `./deploy.sh academy` after merge
- Verify by launching a new crew post-deploy — `"Failed to mint session cookie"` error should not appear
- No rollback risk — the change is purely a correctness fix to error detection
