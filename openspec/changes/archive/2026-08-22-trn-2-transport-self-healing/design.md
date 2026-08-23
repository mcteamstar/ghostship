## Context

The transport's `_crew_api` function is a thin HTTP wrapper that sends a request with a stored session cookie and raises on non-2xx. When the gateway crashes inside a running container (OOM, segfault, Python unhandled exception), the container stays running but the cookie/CSRF state is lost. The current `_ensure_crew_running` only checks container state — a running container with a dead gateway passes all existing guards. Every subsequent call returns 400 (CSRF) and the only recovery is a manual container restart.

The existing `_ensure_crew_running` already handles: stopped container → start → wait gateway → refresh cookie. The proposal extends that pattern to cover the "running but broken" case.

See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Transparent self-healing: callers never see a stale-cookie 400 under normal conditions
- Gateway crash detection without requiring a separate monitoring process
- Bounded recovery: at most one retry cycle per request, deterministic failure after two attempts
- Clear error surface for operators when recovery is exhausted

**Non-Goals:**
- Dashboard port-forward endpoint (deferred to a separate change)
- Monitoring/alerting integration — the `gateway_healthy` field exposes state; consuming it is out of scope
- Changing the idle-stop/restart logic — that remains as-is in `idle-and-recovery`
- Handling partial gateway failures (e.g. some endpoints work, others don't) — the liveness probe is binary

## Decisions

### 1. Retry wraps `_crew_api`, not individual callers

**Decision:** Introduce a `_crew_api_with_recovery(crew, crew_id, method, path, **kw)` function that wraps `_crew_api` with the retry/recovery logic. All tool handlers call this instead of `_crew_api` directly.

**Rationale:** Keeps recovery logic in one place. The alternative (each tool handler doing its own retry) duplicates code across 20+ call sites and risks inconsistency.

**Alternatives considered:**
- Decorator on `_crew_api` — rejected because `_crew_api` takes a crew dict but recovery needs `crew_id` to call `_ensure_crew_running` and update the registry.
- Middleware in httpx — rejected because recovery involves Podman operations, not just HTTP retries.

### 2. Liveness probe is a GET to the gateway root

**Decision:** Probe the gateway at `GET {crew_url}/` with a 5-second timeout. Any 2xx confirms liveness. Non-2xx, connection refused, or timeout = dead.

**Rationale:** The gateway's root always responds (it's a Starlette app with a catch-all). No need for a dedicated `/health` endpoint in the existing codebase — adding one is more invasive for the same signal. 5-second timeout balances fast detection against momentary GC pauses.

**Alternatives considered:**
- `GET /api/status` — some gateway builds don't have this; root is more reliable.
- TCP connect only — insufficient; a half-crashed process can hold the port open.
- Process-level health check via `container_exec` — slower and more complex.

### 3. Recovery sequence: refresh first, restart second

**Decision:** On a 400/401/403 from a running container:
1. Attempt cookie re-mint (fast, ~1s).
2. Retry the request with the new cookie.
3. If step 1 or 2 fails, escalate to full `_ensure_crew_running` (restart + wait + cookie).
4. Retry the request once more.
5. If still failing, surface the error.

On a connection error from a running container:
1. Run the liveness probe to confirm the gateway is dead.
2. Escalate immediately to `_ensure_crew_running`.
3. Retry the request once.
4. If still failing, surface the error.

**Rationale:** Cookie refresh alone fixes the majority of cases (gateway restarted itself but container stayed up). A full restart is heavier (30s worst case) and only needed when the process is truly gone.

**Alternatives considered:**
- Always restart — simpler but much slower for the common case (cookie expiry without crash).
- Exponential backoff with multiple retries — rejected; deterministic single-retry is sufficient for the failure modes described and avoids masking persistent issues.

### 4. `gateway_healthy` is computed on-demand in `crews()`

**Decision:** `crews()` runs the liveness probe for each crew at call time rather than caching health in the registry.

**Rationale:** Health is inherently point-in-time. Caching introduces staleness without reducing probe cost (the idle monitor already runs periodically). The probe is fast enough (5s timeout × N crews, parallelizable) for the expected fleet size (≤10 crews per host).

**Alternatives considered:**
- Periodic health sweep stored in registry — adds complexity, stale by definition.
- Background thread with an event — over-engineered for the use case.

### 5. Error messages follow a template

**Decision:** Recovery-failure errors use the format:
```
crew <crew_id> is unresponsive — transport attempted <actions taken> but
the gateway did not recover. Suggestion: <next step>.
```

**Rationale:** Operators need: which crew, what was tried, what to do next. No raw codes, no tracebacks.

## Risks / Trade-offs

- **[Risk] Liveness probe adds latency to `_ensure_crew_running`** → Mitigated by 5s timeout and only probing when the container is confirmed running. Net add is ≤5s in the failure path, 0s in the success path (probe succeeds fast).
- **[Risk] Cookie refresh races with concurrent requests** → Mitigated by the existing `_startup_events` serialisation lock in `_ensure_crew_running`. The new wrapper must hold a similar per-crew lock during the refresh-retry sequence.
- **[Risk] Silent retry masks persistent configuration errors** → Mitigated by the strict one-retry cap and clear error surfacing. Repeated recovery triggers will be visible in transport logs.
- **[Risk] `crews()` latency increases with fleet size** → Acceptable for ≤10 crews. If fleet grows, probe can be parallelised with `concurrent.futures.ThreadPoolExecutor`.

## Migration Plan

1. Add `_crew_api_with_recovery` alongside existing `_crew_api`. Keep `_crew_api` unchanged for internal uses that should not retry (e.g. inside `_ensure_crew_running` itself).
2. Replace all tool-handler calls from `_crew_api(...)` to `_crew_api_with_recovery(crew, crew_id, ...)`.
3. Add the liveness probe to `_ensure_crew_running` (after the `container_is_running` check, before returning).
4. Add `gateway_healthy` to the `crews()` output.
5. All changes are in `transport/server.py`; no database migration, no config file changes, no external service dependency.
6. Rollback: revert the single file. The retry wrapper is additive — removing it restores current behaviour.
