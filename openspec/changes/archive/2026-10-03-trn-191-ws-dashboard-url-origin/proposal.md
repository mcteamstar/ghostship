# TRN-191 — WebSocket 403: fix WS dispatch and upstream Origin header

## Problem

After TRN-189 (Caddy WS forward_auth fix), WebSocket upgrades still returned
403 through the dashboard. Two bugs remained:

1. `BearerAuthMiddleware` in `auth.py` dispatched WS upgrades for
   `/crews/*/ui` paths by looking up the handler in `_routes` — the
   bearer-protected dict. The WS handler is registered in `_public_routes`
   (gated by Caddy's `gs_session`, not bearer). Handler was always `None` →
   fell through to downstream → 403. This was the root cause.

2. The transport's WS proxy sent `Origin: http://gs-{crew_id}:5476`
   (the container hostname). KiroCrew's `build_allowed_origins()` always
   includes `http://localhost:{port}` and `http://127.0.0.1:{port}`
   unconditionally, but only adds `dashboard_url` origins when token auth
   middleware is active — which Ghostship's gateway does not use. So the
   container hostname origin was always rejected.

## Fix

**`transport/auth.py` — `BearerAuthMiddleware.__call__`:**
Check `_public_routes` first when looking up the WS handler:

```python
ws_handler = self._public_routes.get(
    ("WS", "/crews/*/ui")
) or self._routes.get(("WS", "/crews/*/ui"))
```

**`transport/server.py` — `_handle_crew_ui_ws_proxy`:**
Send `Origin: http://localhost:{CREW_GATEWAY_PORT}` instead of the container
hostname — always in the gateway's allowed set:

```python
crew_origin = f"http://localhost:{CREW_GATEWAY_PORT}"
```

## What was NOT the fix

Setting `dashboard.url` in `config.local.json` (the v1 approach) had no
effect. KiroCrew only adds `dashboard_url` to `allowed_origins` when token
auth middleware is active (a security invariant in `server.py:6094`). Ghostship
runs without token auth. The v1 `dashboard.url` patch was reverted.

## Impact

- Fixes: KiroCrew dashboard WS connection (101 instead of 403)
- Sessions list loads, live task updates work, import modal dismissable
- No API or MCP tool changes
- Prerequisites: TRN-189
