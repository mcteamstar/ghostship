# Change: TRN-222 — Per-App WS Scoping & WS Content Redaction (0.9.0 verification)

**Plane ticket:** TRN-222
**Upgrade context:** ghostship → KiroCrew `0.9.0-insider.4`
**Priority verdict:** **BEHAVIOUR CHANGE / LOW IMPACT** — *no code change required; verification only.*

## Why

KiroCrew 0.9.0 ships two WebSocket-layer changes that, at face value, touch
ghostship's dashboard proxy:

1. **Per-app WebSocket event scoping** (upstream PR #714) — a WS connection
   authenticated with an *app token* now sees only its own app's events.
2. **WS broadcast content redaction** (upstream PR #3628, a security fix) —
   non-user content (raw model output, tool-call titles) is stripped from the
   WS broadcast payload.

Both changes alter the gateway WS surface that ghostship's portal proxies to the
operator's browser. Before bumping `KC_BASE_IMAGE` we must confirm ghostship's
WS path is unaffected, because a silent regression here would break live session
updates in the dashboard without any build-time error.

The source-grounded assessment (research report, TRN-222 section) concludes
**neither change breaks ghostship**, for two concrete reasons derived from the
code:

- **Per-app scoping does not apply.** Ghostship's WS upgrades are authenticated
  by the **dashboard session cookie** (`gs_session`), established on the SPA's
  initial HTTP load — *not* an app token. The per-app filter keys off an app
  token (`X-App-Token`), so a cookie-authenticated WS connection is outside its
  scope and continues to receive the full event stream.
- **Content redaction does not break the portal.** Ghostship's portal uses WS
  only for *session-state change notifications* (turn started/ended, new
  message). It reads message **content** from the REST API
  (`/api/sessions/{id}/messages`), never from WS payload bodies. Stripping
  `tool_title` / `assistant_content` from WS broadcasts therefore removes fields
  the portal does not consume.

This change exists to **make that verification an auditable artifact** and to
pin the exact code locations a future reviewer must re-check, rather than to
modify behaviour.

## What Changes

- **No production code change** to the WS proxy path.
- Add a verification checklist (see `tasks.md`) that confirms, against the
  running `0.9.0-insider.4` gateway, that:
  - ghostship WS connections authenticate via `gs_session` cookie, not an app
    token (so per-app scoping is a no-op for them);
  - the portal does not read model/tool content from WS payloads.
- Record the audited code locations (see below) in `design.md` so the next
  WS-touching PR has a documented baseline.

## Affected ghostship files / functions

| File | Symbol | Role in WS path |
|---|---|---|
| `transport/caddy.py` | `CaddyPortal.register_crew` (`ws_route`, ~L192–212) | Defines the `Connection: Upgrade` route that proxies WS straight to `crew_proxy_handler`; comment at that route documents the cookie-inherited auth (TRN-189). |
| `transport/caddy.py` | `crew_proxy_handler` | The reverse-proxy upstream (`ga-transport`) the WS route forwards to; injects `X-Transport-Token`, not an app token. |
| `transport/dashboard.py` | `DashboardGate.handle_auth` | `GET /dashboard/auth` forward_auth; validates the `gs_session` cookie only — never inspects WS payload content. |
| `transport/dashboard.py` | `DashboardGate.__init__` / `_sessions` | The `gs_session` `SessionStore` that backs the cookie the WS connection inherits. |

## Scope / Non-goals

- This change does **not** introduce app-token WS auth; ghostship intentionally
  stays on the cookie path.
- It does **not** add WS-content parsing to the portal.
- If a future ghostship feature introduces app-token-authenticated WS
  connections, per-app scoping would then apply and this baseline must be
  revisited — that is explicitly out of scope here.
