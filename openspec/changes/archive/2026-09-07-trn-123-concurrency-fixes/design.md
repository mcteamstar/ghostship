## Context

See `proposal.md — Why` for motivation.

The transport server is a Starlette/uvicorn ASGI application. MCP tool handlers (`dispatch`, `pickup`, `steer`, etc.) are executed via `run_in_executor` in a thread-pool, so they run in worker threads. The asyncio event loop itself is the main thread. This creates two distinct threading contexts that share module-level mutable state:

- `_task_timestamps: dict[str, dict]` (server.py) — written by `dispatch` (worker thread) and read-modified-written by `_pickup_single` and `_pickup_list` (worker threads). No lock exists today.
- `_dashboard_port_crew: dict[int, str]` (server.py) — written in `_handle_crew_dashboard_post`, `_handle_crew_dashboard_delete`, `launch`, `nuke`, and `_main` (mix of asyncio coroutines and startup code). No lock exists today.
- `_ensure_crew_running` (lifecycle.py) — called from both MCP tool handlers (worker threads, via `asyncio.to_thread`) and directly from async handlers. The current per-crew serialisation uses `threading.Event` to gate concurrent restarts, but it gates on the *restart branch only*: the `container_is_running` probe and the branch that skips directly to `_touch_crew` are not inside the critical section. Two concurrent callers can both observe `not is_running`, both enter the restart leader election, and one (non-leader) waits while the other starts — but the non-leader path re-reads the crew dict from the registry after the event fires and returns without a second start. **However**, the existing `threading.Event` mechanism already handles the double-start case correctly; the real gap is that the per-crew `_startup_events` dict itself is not the same as a per-crew asyncio lock, and async callers (coroutines awaiting `asyncio.to_thread`) need the critical section around the probe-then-start path.

After a careful re-read of the code: the `_startup_events` dict with leader election already prevents double `container_start`. The remaining risk is that **async callers** using `await asyncio.to_thread(_ensure_crew_running, ...)` can run the thread in the executor where the `_startup_events_lock` and `threading.Event` are fully functional, so the current code is safer than the ticket description implies. The ticket's concern about `_ensure_crew_running` is still valid as a belt-and-suspenders measure: adding a per-crew asyncio lock at the call site in async handlers (UI proxy, WS proxy, API proxy) prevents unnecessary thread dispatches when the check is clearly a no-op for an already-running container.

## Goals / Non-Goals

**Goals:**
- Eliminate the data race on `_task_timestamps` with a `threading.Lock`.
- Eliminate the data race on `_dashboard_port_crew` with a `threading.Lock`.
- Add a per-crew asyncio lock at the `_ensure_crew_running` call sites inside async handlers so concurrent coroutine callers for the same crew are serialised before touching the thread pool, as belt-and-suspenders on top of the existing `threading.Event` mechanism.
- Add targeted unit tests for the new lock paths.

**Non-Goals:**
- Replacing the existing `threading.Event` leader-election in `_ensure_crew_running` — it is correct and should be preserved.
- Adding locks to `_registry_lock` or any already-protected dict (e.g. `_gs_session_store`).
- Performance optimisation; locking granularity beyond what is needed to eliminate the races.
- Any observable behaviour change for callers.

## Decisions

### D1: `threading.Lock` for `_task_timestamps` and `_dashboard_port_crew`

Both dicts are accessed from worker threads (MCP tool handlers run in thread-pool executors). `threading.Lock` is the correct primitive — `asyncio.Lock` cannot be acquired from a non-async context, and these access sites are synchronous functions.

Lock scope: hold only for the minimal read-modify-write critical section, not across blocking I/O. All existing access sites are dict reads/writes with no blocking I/O, so a coarse "wrap the whole access" approach is acceptable and adds negligible contention.

Naming: `_task_timestamps_lock` and `_dashboard_port_crew_lock`, module-level singletons alongside the dicts they protect.

Alternative considered: `threading.RLock` — unnecessary, no recursive acquisition pattern.

### D2: Per-crew asyncio lock for `_ensure_crew_running` async call sites

The async proxy handlers (`_handle_crew_ui_proxy`, `_handle_crew_ui_ws_proxy`, `_handle_crew_api_proxy`) all call `await asyncio.to_thread(_ensure_crew_running, crew, crew_id)`. Adding a per-crew `asyncio.Lock` in a module-level dict (`_ensure_running_locks`) means concurrent coroutines for the same crew serialise in the event loop *before* dispatching a thread, avoiding redundant thread dispatches when the crew is already running.

Dict protected by a regular `threading.Lock` (`_ensure_running_locks_lock`) for lazy population, since the dict initialisation happens in a non-async startup path as well.

Alternative considered: moving the lock into `_ensure_crew_running` itself — the function is synchronous and called from both async and sync contexts, making an `asyncio.Lock` inside it awkward. Keeping the lock at the call site is cleaner.

Alternative considered: removing `asyncio.to_thread` and making `_ensure_crew_running` async — too invasive; lifecycle.py is also called from sync tool handlers.

### D3: No changes to `_ensure_crew_running`'s internal `threading.Event` mechanism

The existing leader-election already prevents double `container_start`. Replacing it with the asyncio lock would require making the function async or adding a complex synchronous awaitable. Belt-and-suspenders at the call site is sufficient.

## Risks / Trade-offs

- [Risk] Lock contention on `_task_timestamps_lock` under very high dispatch/pickup rates → Mitigation: lock scope is narrow (dict read/write only); contention window is microseconds.
- [Risk] Deadlock if a lock holder blocks on another lock → Mitigation: no nesting of the new locks with each other or with `_registry_lock`; lock acquisition order is unambiguous.
- [Risk] asyncio lock overhead on the hot path of every proxy request → Mitigation: the lock is only acquired when the crew may be stopped (`not container_is_running`); a fast pre-check outside the lock avoids the asyncio overhead for the common case (crew already running, gateway healthy).

## Migration Plan

- No config, API, or wire-format changes. Drop-in: add the locks and wrap existing access sites.
- No container restart or deployment ordering constraint.
- Rollback: revert the lock additions; the underlying dict behaviour is unchanged.
