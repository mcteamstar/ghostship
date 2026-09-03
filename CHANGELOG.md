# Changelog

## v0.2.4 (2026-09-03)

### TRN-80 — Per-crew dashboard proxy
- `launch(dashboard=True)` allocates a dedicated port and returns a `dashboard_url` for the crew's browser UI (opt-in; `dashboard=False` by default)
- HTTP and WebSocket proxying to the KiroCrew SPA via per-port uvicorn daemon threads
- `POST/DELETE /crews/{id}/dashboard` REST API to attach or detach a dashboard port without nuke+relaunch
- Session cookie injection and CORS origin injection for browser authentication
- `GA_DASHBOARD_PORT_ENABLED`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE` environment variables
- Known limitation: dashboard ports are network-auth only (Tailscale/firewall); TRN-91/92 cover auth hardening

### TRN-89 — Timestamps on tool responses
- `dispatch` response includes `created_at`
- `pickup` (task-level) response includes `created_at`, `started_at`, `completed_at` (ISO 8601 UTC, `null` until reached)
- `captain status` response includes `last_checkin_at`
- Mail subjects (pickup, captain status) include `received_at` parsed from the message `Date` header

### TRN-90 — Bundle clone HEAD fix
- Fixed: `evac(bundle=True)` followed by `supply(bundle=True)` now correctly checks out the working tree when the bundle HEAD ref contains slashes (e.g. `release/0.2.4`)

### TRN-93 — Security hardening
- Admiral secret delivered via stdin instead of argv — no longer visible in `ps` or `/proc`
- `crews.json` stores an opaque sha256 identifier instead of the plaintext secret
- Container hardening: `no_new_privileges=True`, `cap_drop=[CAP_NET_RAW, CAP_SYS_ADMIN]`
- `KC_GATEWAY_TOKEN_TTL` validated on transport startup
- File-transfer audit logging

### TRN-94 — Broad mailbox skim
- `captain status` returns `agent_mail` covering all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral)
- Crew-level `pickup` (no `task_id`) returns `agent_subjects` covering all 8 mailboxes
- `pickup(agent="ghost", crew_id=...)` — new agent filter returns a single-inbox response with no task list
- `read_mail_subjects.py` updated to return `{subject, received_at}` dicts

### Fixes
- WebSocket pump: `asyncio.wait(FIRST_COMPLETED)` + cancel (replaces leaky `asyncio.gather`)
- httpx client pooling: one pooled `AsyncClient` per dashboard port (was re-created per request)
- DELETE dashboard atomicity: stop and release inside `_registry_lock`

---

## v0.2.3 and earlier

See git log for history prior to v0.2.4.
