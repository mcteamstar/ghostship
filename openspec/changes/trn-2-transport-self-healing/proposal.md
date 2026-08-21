## Why

The transport is the only intended interface to ghostship crews — users should
never need SSH access to the host or direct podman interaction. Today, when the
KiroCrew gateway crashes and restarts itself inside a running container, the
transport's session cookie and CSRF registration become stale. Every subsequent
API call returns `400 Bad Request` (CSRF check failed) and the only recovery
path is stopping and starting the container manually — which requires either SSH
or operator-level access that users of a remote ghostship instance won't have.

The transport already has the Podman socket, already mints cookies, and already
owns the full recovery path for stopped containers. It should apply the same
ownership to in-container gateway crashes.

This is a stub only — capturing the direction for a future design pass.

## What Changes (sketch, not final)

- **CSRF/cookie auto-recovery** — when `_crew_api` receives a `400`/`401`/`403`
  from a running container, the transport detects a stale cookie, re-mints it
  via `container_exec` (`kirocrew token --ttl ...`), updates the registry, and
  retries the original request — all transparently, without user intervention.
  If the re-mint fails, escalate to a full container restart via
  `_ensure_crew_running`.

- **Gateway liveness detection** — distinguish between "container stopped" (current
  recovery path) and "container running but gateway dead/crashed". A quick HTTP
  probe on the gateway URL before assuming the container is healthy. If the probe
  fails on a running container, treat it as a gateway crash and run the recovery
  hook.

- **Retry with backoff** — wrap `_crew_api` calls in a thin retry layer:
  on `400`/`401`/`403`, attempt cookie refresh once; on connection error on a
  running container, attempt gateway restart once; after two failures, surface
  a clear error to the user.

- **Clear user-facing errors** — when recovery fails, return a message the user
  can act on: "crew srv-X is unresponsive — the transport attempted recovery but
  the gateway did not come back. Try calling pickup again in a moment." Not a raw
  HTTP error code.

- **Gateway dashboard port forward** (nice-to-have, investigate) — expose a
  transport endpoint (`GET /crew/{crew_id}/dashboard`) that port-forwards to the
  crew's gateway dashboard on port 5476, so operators can open it in a browser
  without SSH tunnels. Note: KiroCrew's dashboard shows chat sessions and cron
  jobs but not the spawn pool (background agents dispatched via `/api/spawn`),
  so crew tasks won't be visible there — `pickup` remains the primary
  observability surface for agent work.

- **`crews()` gateway health field** — add `gateway_healthy: bool` to each crew
  entry so operators can see at a glance which crews have a responsive gateway
  vs a running-but-broken one.

## Capabilities

### Modified Capabilities
- `crew-lifecycle`: transport self-heals from gateway crashes without user
  intervention — not yet specced, pending the real design pass.
- `mcp-server`: clearer error messages when crew recovery fails.

## Impact

- `transport/server.py` — `_crew_api`, `_ensure_crew_running`, cookie refresh
  logic, retry wrapper
- `transport/test_transport.py` — tests for recovery scenarios
- Not yet scoped: exact retry/backoff parameters, gateway liveness probe
  implementation, dashboard port-forward mechanism
