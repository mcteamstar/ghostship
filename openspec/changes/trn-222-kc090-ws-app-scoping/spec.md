# Spec Delta: TRN-222 — WS Scoping & Redaction Compatibility

This delta records the *behavioural contract* ghostship's WS proxy must satisfy
after the `0.9.0-insider.4` upgrade. No interface or config key changes; the
delta is a MUST/MUST-NOT contract plus the verification evidence.

## Behaviour: WebSocket authentication (unchanged, now explicitly specified)

- The per-crew dashboard WebSocket upgrade MUST continue to be authenticated by
  the `gs_session` session cookie, established on the SPA's initial HTTP load.
- The WS route MUST NOT be migrated to app-token authentication
  (`X-App-Token` or equivalent) as part of this upgrade.
- RATIONALE: KiroCrew 0.9.0 per-app WS event scoping filters events only for
  **app-token-authenticated** connections. A cookie-authenticated connection is
  outside that filter and continues to receive the full crew event stream, which
  is the behaviour the ghostship portal depends on.

### Interface after change (identical to before)

Caddy server object, per crew (`transport/caddy.py`,
`CaddyPortal.register_crew`):

```python
ws_route = {
    "match": [{"header": {"Connection": ["Upgrade"]}}],
    "handle": [crew_proxy_handler],   # proxy straight through, no forward_auth
}
```

`crew_proxy_handler` forwards to `ga-transport` with:

```python
"headers": {"request": {"set": {
    "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"],
}}},
```

No `X-App-Token` header is set, now or after the upgrade.

## Behaviour: WS broadcast content redaction tolerance

- The ghostship portal MUST read message **content** (assistant text, tool-call
  titles, tool output) from the REST API
  (`GET /api/sessions/{id}/messages`), NOT from WebSocket payload bodies.
- The portal MAY rely on WS messages only for **session-state change
  notifications** (turn started, turn ended, new-message signal).
- RATIONALE: KiroCrew 0.9.0 strips non-user content (`assistant_content`,
  `tool_title`) from the WS broadcast. Reading content from REST makes this
  stripping invisible to the portal.

### Fields the portal MUST NOT depend on from WS payloads

| Field | Status after 0.9.0 | Portal action |
|---|---|---|
| `assistant_content` | Redacted from WS broadcast | Read from REST instead |
| `tool_title` | Redacted from WS broadcast | Read from REST instead |
| session/turn lifecycle signals | Still broadcast | OK to consume from WS |

## Configuration

- **No new config keys.** The WS proxy is driven entirely by the Caddy server
  object built in `CaddyPortal.register_crew`; there is no per-app WS toggle to
  set.
- `GA_API_KEY` (existing) still gates the HTTP catch-all route via
  `forward_auth`; the WS route deliberately bypasses `forward_auth` (TRN-189)
  and relies on the already-validated `gs_session` cookie. This is unchanged.

## Acceptance (behavioural)

1. With `KC_BASE_IMAGE = 0.9.0-insider.4`, a logged-in operator's dashboard WS
   connection continues to receive crew session events (turn start/end, new
   message) with no filtering, confirming the cookie path is not subject to
   per-app scoping.
2. The portal renders full assistant/tool content for a running session, sourced
   from REST, confirming WS redaction causes no visible content loss.
