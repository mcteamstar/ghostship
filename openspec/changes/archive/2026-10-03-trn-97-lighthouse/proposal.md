# Proposal: ga-lighthouse — Fleet-Level Observability (TRN-97)

## What

`ga-lighthouse` is a new optional container that provides a read-only,
browser-accessible fleet dashboard for a Ghostship installation. It shows
all crews, their running tasks, agent mail activity, and host resource state
in one place — a fleet-level view that does not exist today.

Today, an operator who wants to know "what is the fleet doing right now?" must
call the `crews()` MCP tool, run `pickup(task_id=None)` to scan tasks, and
call `captain(action="status")` to check mail counts. There is no human-
readable view — everything is JSON returned to a coding assistant session.
Lighthouse makes fleet state visible without a running Kiro session, to any
browser that can reach the Ghostship portal.

## Why

Three concrete operator pain points motivate this:

1. **Invisible fleet.** When `GA_MAX_ACTIVE_CREWS` is reached and new
   dispatches are queuing, there is no way to see which crews are occupied
   and which are idle without dropping into an MCP tool call.

2. **Mail accumulation goes unnoticed.** Persona inboxes accumulate unread
   mail silently. Stuck tasks (e.g. a Wraith waiting on a Spectre handoff
   that never came) are only visible by manually scanning each inbox.

3. **Resource pressure is opaque.** `host_memory_available_gb` is available
   in the `crews()` tool response, but only surfaced to operators who know
   to look at it. A low-memory event that causes dispatch rejections is hard
   to diagnose after the fact.

Lighthouse addresses all three with a polling dashboard that is always on.

## Architecture Decision

### Placement

`ga-lighthouse` joins `ga-portside` only — the same network as `ga-portal`
and `ga-transport`. It has no access to `ga-starboard` (crew containers).
All fleet data is fetched from `ga-transport` over portside.

```
  [Browser]
      │  HTTPS via PORT
  [ga-portal / Caddy]  ── ga-portside ──┬── [ga-transport] ─── ga-starboard ─── [gs-*]
                                         └── [ga-lighthouse]
                                                   │
                                             calls ga-transport
                                             over ga-portside
```

This placement enforces the network isolation invariant already established
by `ga-portal`: lighthouse never dials crew containers directly. Any path
to a crew dashboard goes `browser → ga-portal → ga-lighthouse → ga-transport
→ crew gateway`, which means cookie injection and token enforcement are
handled by the transport exactly as they are for per-crew dashboard access
today.

### Why Not Starboard Access

If lighthouse were given `ga-starboard` access it could query crew gateways
directly, bypassing the transport's `X-Transport-Token` enforcement and the
IP-bound `mc_token_5476` session cookie mechanism. Crew dashboard sessions
would break (wrong source IP) and the portside/starboard security split would
be violated. Portside-only is not a constraint to work around — it is the
correct design.

### Why a Separate Container, Not a Transport Route

Adding the SPA directly to `ga-transport` as a static route would work for
the HTML file, but:

1. The transport is a security-sensitive service. Adding a second, separate
   static asset serving concern to it conflates two responsibilities.
2. Lighthouse has its own startup, secrets, and container lifecycle. Keeping
   it separate makes it trivially disableable (`GA_LIGHTHOUSE_ENABLED=false`)
   without touching the transport.
3. Future iterations may need a separate CPU/memory budget (e.g. log tailing,
   SSE fanout). A separate container is the natural boundary.

### Optional by Default

Lighthouse is gated behind `GA_LIGHTHOUSE_ENABLED` (default: `false`). When
disabled, no service block appears in `compose.yml` and no `/lighthouse/*`
route appears in Caddy's `initial-config.json`. Existing installs are
unaffected by adding this change.

## Scope of MVP

### In scope

- New `ga-lighthouse` container: Python (uvicorn) server + vanilla JS SPA,
  zero build step, zero npm dependencies.
- Two new REST endpoints on `ga-transport`:
  - `GET /api/crews` — fleet registry + agent status (same shape as the
    `crews()` MCP tool response).
  - `GET /api/crews/{crew_id}/mail` — per-persona mail counts and recent
    subjects for one crew.
- Caddy `/lighthouse/*` route (path-prefix, stripped before forwarding) with
  `gs_session` forward-auth gate when `GA_API_KEY` is set.
- `compose.yml` service block, `ga-transport-secret` secret mount.
- `install.sh` additions: `GA_LIGHTHOUSE_ENABLED` flag, secret mount, Caddy
  route generation.
- Read-only fleet view: crew cards (status, tasks, uptime, memory), mail
  badges, a task list panel.

### Out of scope (future iterations)

- Interactive controls (dispatch, nuke, steer) — observability-first MVP.
- Server-Sent Events / WebSocket push — polling at 3–5 s is sufficient.
- Per-crew log tailing (`GET /api/crews/{id}/logs`) — requires a new podman
  endpoint in the transport; deferring to a follow-on TRN.
- Aggregated task history — requires a persisted task log; deferred.
- Subdomain routing — path prefix is sufficient and avoids DNS/TLS complexity.

## Key Risks

1. **Auth relay**: Lighthouse calls the transport and must supply
   `X-Transport-Token`. The portal secret must be mounted into the lighthouse
   container as a Podman secret, following the same pattern as `ga-portal`.

2. **Crew dashboard proxy chain**: A user navigating from the fleet view to a
   crew's dashboard passes through `ga-portal → ga-lighthouse → ga-transport →
   crew gateway`. The lighthouse server must relay this proxied connection to
   the transport's `/crews/{id}/ui/*` path correctly and must not attempt to
   dial crew containers directly. Cookie injection happens at the transport, not
   at lighthouse.

3. **Network isolation**: The `compose.yml` block must only list `ga-portside`
   in `networks`. Any accidental addition of `ga-starboard` would break the
   security model. This must be verified in code review.

4. **Optional component footprint**: When `GA_LIGHTHOUSE_ENABLED=false`, no
   part of lighthouse should appear in `compose.yml` or `initial-config.json`.
   The shell guard in `install.sh` must be complete and tested.

## References

- Wraith discovery report: `docs/lighthouse-discovery.md`
- Portside/starboard network split: `docs/architecture.md`
- Transport server: `transport/server.py`
- Caddy portal generation: `scripts/install.sh` (lines 666–873)
- Caddy portal module: `transport/caddy.py`
- Config model: `transport/config.py`
