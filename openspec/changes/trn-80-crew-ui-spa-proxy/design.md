## Context

See proposal.md — Why for motivation.

The existing UI proxy handler `_handle_crew_ui_proxy` (server.py:659) works correctly for the initial page load at `/crews/{id}/ui/`. After that, the browser fetches SPA assets using root-absolute paths (`/static/app.js`) which hit the transport root and 404 — there is no catch-all that re-routes them. Separately, `KIROCREW_CORS_ORIGINS` is set at `container_create` time (server.py:1816) to only the crew's internal origin, so the crew gateway rejects cross-origin requests from the transport's public URL.

## Goals / Non-Goals

**Goals:**
- Root-absolute SPA asset requests are transparently re-routed to the originating crew.
- Transport origin is in the crew's CORS allowlist from container start.
- Fallback for service-worker fetches that lack a `Referer` header.

**Non-Goals:**
- Supporting multiple simultaneous crew UIs in the same browser tab.
- Rewriting SPA asset paths in HTML responses (no HTML munging).
- Changing the crew gateway's CORS implementation.

## Decisions

**D1: Catch-all route at lowest priority using Referer parsing**

A catch-all `GET /{path:path}` route is added to the transport's routing table at the lowest priority (after all specific routes). When a request arrives with a `Referer` header matching `/crews/{crew_id}/ui/`, the catch-all proxies it through the existing `_handle_crew_ui_proxy` logic for that crew. If no Referer matches and no cookie is present, it returns 404.

Alternatives considered:
- *Rewrite `<base href>` in proxied HTML*: fragile, requires HTML parsing, breaks if SPA uses `document.baseURI` directly.
- *Serve all `/static/**` paths from a dedicated handler*: too narrow — SPA asset paths vary by framework; a Referer-based catch-all handles them all.

**D2: crew_ui_context cookie as Referer fallback**

Service workers and some fetch() calls don't send `Referer`. A short-lived `crew_ui_context={crew_id}` cookie (HttpOnly, SameSite=Strict, 1h TTL) is set on the initial `/crews/{id}/ui/` response. The catch-all reads it only when `Referer` is absent or doesn't match.

Cookie is HttpOnly and SameSite=Strict to prevent cross-site abuse. 1h TTL is short enough to be safe and long enough for a typical work session.

**D3: Transport origin appended to KIROCREW_CORS_ORIGINS**

At `container_create` time, the transport derives its public origin from `GA_HOST_URL` (or `http://localhost:{PORT}`) and appends it to `KIROCREW_CORS_ORIGINS`, comma-separated. Any pre-existing value from the composition config is preserved.

This is the minimal change — only the transport knows its own public origin, and that knowledge is already available at container create time.

## Risks / Trade-offs

- **Catch-all absorbs unintended 404s** → The catch-all only proxies when Referer or cookie identifies a valid crew; otherwise it returns 404 as before. No silent swallowing of unrelated paths.
- **Stale cookie after crew nuke** → Cookie has a 1h TTL. If the crew is nuked and a new one started with the same id, the cookie still works correctly (same id → same upstream). If the id changes, the catch-all will return a 404 from the proxy (crew not found in registry), which is the correct behavior.
- **Multiple tabs with different crews** → The cookie stores only one crew_id. If a user has two crew UIs open in the same browser, the cookie is overwritten by the most recent `/crews/{id}/ui/` load. Referer-based routing is unaffected and remains correct per-request. This is a known edge case and acceptable given the low-traffic nature of the UI proxy.

## Migration Plan

- No schema changes. No data migration.
- Existing crews started before this change won't have the transport origin in `KIROCREW_CORS_ORIGINS`. They will need to be stopped and restarted (or nuked and re-launched) for the CORS fix to take effect.
- Rollback: revert the two code changes (catch-all + CORS injection). No persistent state is modified.
