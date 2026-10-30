# Design — TRN-289 Crew Dashboard Main-Port Response

## Context

See `proposal.md — Why` for motivation.

The main Caddy port has no route for `/crews/*/ui*`. Caddy's fallback returns
`200 Content-Length: 0` when no route matches, rather than 404. The per-crew
dedicated port (`64058+`) correctly serves the KiroCrew SPA via `caddy.py`'s
`register_crew()` — that path is not broken.

The transport does have a `_handle_crew_ui_proxy` handler registered at
`(GET, /crews/*/ui)` in `auth.py`'s route dispatch. The issue is that this
handler is reachable from the transport's ASGI dispatch but not from the main
Caddy port, because the Caddy config written by `install.sh` has no
`/crews/*/ui` match in the ga-main server.

## Goals / Non-Goals

**Goals:**
- Main port never returns empty 200 for crew UI paths
- Crew with a dashboard port: redirect to the correct per-crew port URL
- Crew without a dashboard port: return 404

**Non-Goals:**
- Serving the KiroCrew SPA from the main port (that's the dedicated port's job)
- Changing `caddy.py` or the per-crew server config
- Fixing `/crews/*/ui` proxying through the main port (not needed — dedicated port works)

## Decisions

### D1 — Add a `/crews/*/ui*` route to the main Caddy port that proxies to `ga-transport`

The transport already has `_handle_crew_ui_proxy` which:
1. Parses the path
2. Resolves the crew and wakes it if stopped
3. Proxies the request to `gs-{id}:5476/{sub_path}`

Adding this path to the main Caddy port's `ga-transport-misc` match list means
the transport handler fires. It will return the crew gateway's HTML response
(the KiroCrew SPA), which is technically correct.

**Problem:** KiroCrew's SPA is built assuming it owns the entire origin. When
served at `localhost:64057/crews/{id}/ui/`, the SPA's asset chunks are loaded
from `/assets/*.js` — relative to `localhost:64057`, not the transport proxy
path. This means `/assets/*.js` on the main port still returns empty 200 (no
route for it). The U+FFFD error returns.

### D2 — Redirect `/crews/{id}/ui` → per-crew dedicated port (chosen)

Add a transport handler `_handle_crew_ui_redirect` that:
1. Parses the crew_id from the path
2. Looks up `dashboard_port` from the registry
3. If port exists: return `302 Location: http://<host>:<dashboard_port>/`
4. If no port: return `404`

This is the correct fix — it sends the browser to the origin that actually owns
the SPA. The SPA runs at `localhost:<port>/` where all asset paths resolve
correctly.

**Why not D1?** Proxying through the main port breaks SPA asset routing due to
the absolute `/assets/` paths. Redirect avoids this entirely.

**Alt considered:** Return 404 always from the main port, let operators use the
`dashboard_url` from the `launch()` response. Rejected — operators will
naturally navigate to `/crews/{id}/ui/` by muscle memory or copy-paste. A
redirect is a better UX than a silent empty 200 or a cryptic JS parse error.

### D3 — Route added to `ga-transport-misc` match list in `install.sh`

The Caddy config `ga-transport-misc` route in `install.sh` already covers
`/dashboard/*`, `/login*`, `/logout*`, etc. Adding `/crews/*/ui*` to its path
match list means all such requests reach the transport, which runs
`_handle_crew_ui_redirect`.

**Alternative:** Register a separate `ga-crew-ui` Caddy route. Not needed —
the misc route is the right bucket for transport-owned paths that don't fit the
main MCP/files/radar categories.

## Risks / Trade-offs

- **Redirect changes URL in browser.** The browser ends up at
  `localhost:64058/` not `localhost:64057/crews/{id}/ui/`. This is correct
  behaviour — the dedicated port owns the SPA origin — but operators who
  bookmarked or copy-pasted the old path will end up at a different URL.
  Low risk: the old path never worked correctly anyway.
- **Crew must have dashboard port allocated.** If the crew was launched without
  `dashboard=True`, it has no port and gets a 404. Operators need to allocate a
  port via `POST /crews/{id}/dashboard` first.

## Migration Plan

1. Add `_handle_crew_ui_redirect` to `transport/server.py`
2. Register `(GET, /crews/*/ui)` in the route dict pointing to the new handler
3. Add `/crews/*/ui*` to the `ga-transport-misc` Caddy route match list in
   `bin/install.sh`
4. Run `ghostship upgrade` to pick up the new config
5. Test: `curl -I localhost:64057/crews/{id}/ui/` → 302 to dedicated port

Rollback: revert the two changes and re-run `ghostship upgrade`.
