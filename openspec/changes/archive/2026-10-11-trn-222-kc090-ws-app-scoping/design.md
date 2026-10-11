# Design: TRN-222 — WS Scoping & Redaction Verification

This is a **verification-only** change. There is no production code diff; the
design records the exact source locations and the invariants that make the two
0.9.0 WS changes no-ops for ghostship, so a reviewer can confirm each claim
against the running gateway.

## D1 — WS auth is cookie-based, not app-token (per-app scoping is a no-op)

### Source evidence (`transport/caddy.py`, `CaddyPortal.register_crew`)

The crew proxy handler forwards WS upgrades to the transport with a transport
secret header only — no app token:

```python
crew_proxy_handler: dict = {
    "handler": "reverse_proxy",
    "upstreams": [{"dial": _transport_addr}],   # ga-transport:{self._port}
    "rewrite": {"uri": f"/crews/{crew_id}/ui{{http.request.uri.path}}"},
    "headers": {"request": {"set": {
        "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"],
    }}},
}
```

The dedicated WS route (added for TRN-189) proxies straight through, bypassing
`forward_auth`, and its own comment states the auth model:

```python
# TRN-189: WebSocket upgrades (Connection: Upgrade) must bypass
# forward_auth. ... No auth regression: reaching this port at all required
# the gs_session that forward_auth validated on the SPA's initial HTTP load,
# and the WS inherits that authenticated browser context.
ws_route = {
    "match": [{"header": {"Connection": ["Upgrade"]}}],
    "handle": [crew_proxy_handler],
}
```

### Invariant

The WS handshake carries the browser's `gs_session` cookie (plus the
`X-Transport-Token` injected by Caddy). It carries **no** `X-App-Token`.
KiroCrew 0.9.0 per-app WS scoping filters events by app token; with no app
token present the connection is treated as a full-stream (session-cookie)
client, exactly as in 0.8.0.

### Verification (no code change)

- Confirm `register_crew` still sets only `X-Transport-Token` in the WS proxy
  handler and sets no `X-App-Token`.
- Against `0.9.0-insider.4`, confirm a logged-in operator's dashboard WS stream
  still receives all crew session events (turn start/end, new message).

## D2 — Portal reads content from REST, not WS (redaction is invisible)

### Source evidence (`transport/dashboard.py`, `DashboardGate.handle_auth`)

The only WS-adjacent handler in the transport is the forward_auth endpoint. It
validates the session cookie and returns 200/401 — it never reads a WS payload
body:

```python
async def handle_auth(self, request: Request) -> Response:
    if not self._api_key:
        return Response(status_code=200)
    token = request.cookies.get("gs_session", "")
    if not token or not self._sessions.validate(token):
        return Response(status_code=401)
    ...
    return Response(status_code=200)
```

There is no `assistant_content` or `tool_title` access anywhere in
`dashboard.py` or in the Caddy WS route in `caddy.py`. The transport does not
decode WS frame bodies; it reverse-proxies them.

### Invariant

The portal consumes WS for *lifecycle notifications* only and fetches message
content via REST (`GET /api/sessions/{id}/messages`). KiroCrew 0.9.0 stripping
`assistant_content` / `tool_title` from the WS broadcast therefore removes
fields the portal never reads from WS.

### Verification (no code change)

- Grep the transport for `tool_title` / `assistant_content` reads on the WS
  path — expected: none.
- Against `0.9.0-insider.4`, open a running session in the dashboard and confirm
  full assistant/tool content renders (sourced from REST), with live turn
  start/end updates still arriving over WS.

## D3 — Future-break guard

If a later ghostship change introduces app-token-authenticated WS connections
(e.g. an embedded app surface), per-app scoping would then apply and could hide
events the portal expects. Any such PR must re-open this baseline and decide
explicitly whether the app token should see cross-app events. This is recorded
here so the decision is not made implicitly.

## Why no code change

Both upstream changes key off a surface ghostship does not use on its WS path
(app tokens) or a payload field ghostship does not read from WS (model/tool
content). The correct engineering action is to **verify and document the
baseline**, not to add defensive code against a condition that cannot arise
under the current cookie-authenticated, REST-content architecture.
