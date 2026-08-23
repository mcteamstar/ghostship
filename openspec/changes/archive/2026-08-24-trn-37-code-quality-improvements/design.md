## Context

All changes are in `transport/server.py`. The file runs under an ASGI server
(FastAPI/Starlette + Uvicorn); the MCP tool handlers are called either directly
on the event loop or via `asyncio.run_in_executor` depending on whether the MCP
library wraps them — F-03 must settle this before deciding whether `time.sleep`
is safe. The scheduler runs in a background daemon thread (`_schedule_monitor`);
the idle monitor and request handlers may also run in threads.

See `proposal.md` — Why for the full motivation.

## Goals / Non-Goals

**Goals:**
- Eliminate the `float("inf")` / JSON serialization failure.
- Make `_host_memory_cache` thread-safe.
- Correct `_advance_next_fire_at` cron branch.
- Fix `_append_captain_mail` double-lock gap.
- Replace bare `assert` guards in `nuke` with `RuntimeError`.
- Apply `_patch_crew_config` during `_reconcile_registry` restart path.
- Remove dead code (`container_exec_pty`, `_login_flags`, `_initiate_login`).
- Minor quality improvements (warning messages, encoding, container copy API).

**Non-Goals:**
- Rewriting the scheduler or switching cron library.
- Changing any public MCP tool signature or REST route.
- Adding new features or changing scheduling semantics beyond correctness.

## Decisions

### D-01 · Sentinel value for "never fires" — `9_999_999_999.0`

`float("inf")` is non-finite and `json.dumps` raises `ValueError` for it by
default. The sentinel `9_999_999_999.0` (≈ year 2286 Unix timestamp) is finite,
JSON-serialisable, and practically unreachable. All comparisons `next_fire >
now` remain correct because the sentinel is always larger than any real `now`.

Alternatives: use `None` (requires null-checks throughout), use `0` with a
"disabled" flag (two-field invariant, more error-prone), or patch `json.dumps`
with a custom default (hides the root cause). `9_999_999_999.0` is the
simplest correct option.

Constant `_NEVER_FIRE_AT: float = 9_999_999_999.0` defined at module level
so it is auditable and grep-able.

### D-02 · Thread-safety for `_host_memory_cache` — module-level `Lock`

Add `_host_memory_cache_lock = threading.Lock()` alongside the cache variable.
Both the read-then-check and the write must happen inside the same `with`
block to prevent a second thread from reading a partially-written tuple.

Alternative: use `functools.lru_cache` with a TTL wrapper — not stdlib,
requires a dependency. Alternative: store in a thread-local — defeats the
purpose (each thread would cache independently). Module-level `Lock` is
idiomatic and obvious.

### D-03 · MCP sync-tool execution context investigation

Before changing `time.sleep`, audit the MCP library's tool-dispatch path:

```
grep -n "run_in_executor\|asyncio\|thread_pool\|sync\|executor" \
    $(python3 -c "import mcp; print(mcp.__file__)")
```

If sync tool handlers run in a thread-pool executor (the standard pattern for
Python MCP servers), `time.sleep` is safe — it blocks only the worker thread,
not the event loop. Document the finding in a code comment adjacent to the
`time.sleep(min(3, remaining))` calls.

If they run directly on the event loop, replace with `await asyncio.sleep(...)`.
This requires the handler to become `async def`, which is a narrow, contained
change.

Decision to make at implementation time based on audit result.

### D-04 · Cron next-fire calculation — `croniter`

`croniter` is already imported and used elsewhere in `server.py` (confirmed via
grep). Use `croniter(expr, time.time()).get_next()` to compute the true next
fire time.

```python
from croniter import croniter
job["next_fire_at"] = croniter(job["cron_expr"], time.time()).get_next(float)
```

If for any reason `croniter` raises on an expression (invalid), fall back to
`time.time() + 60` and log a warning — same behaviour as today, but now only
for malformed expressions.

### D-05 · `_append_captain_mail` double-lock gap — single read-modify-write

Current code: acquire lock → read `signing_secret` + `supersedes_id` →
**release lock** → (work) → acquire lock → read registry again → write
`last_captain_message_id` → release.

The gap between the two lock acquisitions allows a concurrent call to read a
stale `supersedes_id` and then overwrite with the wrong `last_captain_message_id`.

Fix: hold `_registry_lock` for the entire read-modify-write sequence. The
`_format_captain_mail` call (pure computation, no I/O) can remain inside the
lock because it is cheap. The `container_exec_checked` call (I/O) must stay
outside the lock to avoid holding it across a network call.

Revised structure:
```
with _registry_lock:
    reg = _load_registry()
    crew_entry = reg["crews"].get(crew_id, {})
    signing_secret = crew_entry.get("admiral_secret")
    supersedes_id = crew_entry.get("last_captain_message_id")

message, message_id = _format_captain_mail(...)   # outside lock, pure

if crew_id:
    with _registry_lock:
        reg = _load_registry()
        if crew_id in reg["crews"]:
            reg["crews"][crew_id]["last_captain_message_id"] = message_id
            _save_registry(reg)

podman.container_exec_checked(...)   # outside lock
```

This is identical to the existing structure but the I/O stays outside. The
remaining race window (between computing `message_id` and writing it back) is
harmless: `message_id` is a UUID generated during `_format_captain_mail`, so
even if two concurrent callers both write, the last write wins and the next
`Supersedes` header will reference the last delivered message. That is correct.

### D-06 · `nuke` guards — `RuntimeError`

Replace:
```python
assert container.startswith("gs-")
assert vol.startswith("gs-vol-")
```
With:
```python
if not container.startswith("gs-"):
    raise RuntimeError(f"Refusing to nuke non-crew container: {container!r}")
if not vol.startswith("gs-vol-"):
    raise RuntimeError(f"Refusing to nuke non-crew volume: {vol!r}")
```

Return value is `dict`, so wrap in a try/except at the call site if needed —
but `nuke` already returns `{"error": ...}` for `KeyError`; add a
`RuntimeError` catch for the same pattern.

### D-07 · `_patch_crew_config` in reconcile path

In `_reconcile_registry`, after `podman.container_start(container)` and the
`_wait_gateway` success branch, call `_patch_crew_config(podman, container)`
before updating the registry entry. This is symmetric with the startup path
in `_provision_crew`.

No risk of double-patching: `_patch_crew_config` is idempotent (overwrites
the same config value).

### D-08 · Dead code removal

- `container_exec_pty` on `PodmanClient`: replaced by `container_exec_pty_stdin`
  during the OAuth flow refactor. Confirm no call sites before deleting.
- `_login_flags()` and `_initiate_login()`: both referenced only inside
  `_initiate_login` itself (self-referential after the refactor). Confirm
  via grep before deleting.

### D-09 · `_copy_agents` / `_copy_skills` — `container_archive_put`

Current code embeds file content as a base64 literal inside a Python f-string
executed inside the container. If a filename contains a single quote or
backslash the f-string breaks.

Replace with `podman.container_archive_put(container, dest_dir, tar_bytes)`,
building a minimal in-memory tar:
```python
import tarfile, io
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as tar:
    info = tarfile.TarInfo(name=af.name)
    data = af.read_bytes()
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
buf.seek(0)
podman.container_archive_put(container, dest_dir, buf.read())
```

This requires `container_archive_put` to exist on `PodmanClient`. Verify and
add it if absent (Podman API: `PUT /libpod/containers/{name}/archive?path=...`
with a tar body).

## Risks / Trade-offs

- **F-03 async branch** → If MCP runs sync tools on the event loop, changing
  `time.sleep` to `await asyncio.sleep` requires the handler to become `async`.
  Risk is low (contained function) but the audit finding determines whether any
  change is needed at all. Mitigation: audit first, change only if confirmed.

- **`_append_captain_mail` lock duration** → Holding `_registry_lock` across
  `_format_captain_mail` adds ~microseconds inside the lock. Acceptable:
  `_format_captain_mail` is CPU-only and fast. The I/O (`container_exec_checked`)
  stays outside, so the lock is never held across a network call.

- **`container_archive_put` availability** → If the method is missing from
  `PodmanClient`, it must be added. The Podman v4 API supports the endpoint;
  risk is implementation effort only.

- **Sentinel visibility** → `_NEVER_FIRE_AT` appearing in schedule-state JSON
  returned to clients was previously hidden by `float("inf")` not being
  serialisable (it would have raised before reaching the client). Now clients
  will see `9999999999.0`. This is a minor API surface change, but only for
  one-shot and unknown-type jobs that are effectively "done". Acceptable.

## Migration Plan

All changes are in-process; no data migration is required. The only on-disk
state is the registry file (`DATA_DIR/registry.json`). After the transport
restarts with the fix:

1. Existing registry entries with stored `float("inf")` in `next_fire_at`
   will be re-serialised as `9_999_999_999.0` on the next registry write.
   The monitor loop still compares correctly because `9_999_999_999.0 > now`.
2. No rollback step needed: all changes are backward-compatible within the
   existing registry schema.

## Open Questions

- **F-03 execution model**: Confirm at implementation time whether MCP sync
  tools run in executor or on event loop. Finding determines whether
  `time.sleep` → `asyncio.sleep` swap is needed.
