# TRN-191 — WebSocket 403: set dashboard.url in crew config so gateway allows proxied WS origin

## Problem

After TRN-189 (Caddy WS forward_auth fix), WebSocket upgrades now reach the
KiroCrew gateway but are rejected with 403: `WebSocket origin not allowed`.
HTTP requests through the same cookie-injection path return 200 — the failure
is WS-specific.

## Root cause

KiroCrew's WS handler calls `_check_ws_origin` → `check_origin(request,
require=True)`, which validates the `Origin` header against
`app["allowed_origins"]`. That set is built at gateway startup from
`dashboard.url` in the crew config.

Ghostship does not set `dashboard.url` in `config.local.json` at crew launch —
it is left as the KiroCrew default (empty string). With no configured URL,
`build_allowed_origins` falls back to loopback-only:

```
{"http://localhost:5476", "http://127.0.0.1:5476"}
```

The transport's WS proxy injects `Origin: http://gs-{crew_id}:5476` on the
upstream handshake (the internal container hostname). This is neither a
loopback address nor in the allowed set → 403.

## Proposed fix

In `_patch_crew_config` (`transport/lifecycle.py`), add `dashboard.url` to the
`config.local.json` patch so the gateway knows its own hostname:

```python
"dashboard": {"url": f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"}
```

KiroCrew deep-merges `config.local.json` over `config.json` on every start, so
this takes effect without any restart logic changes. The gateway will then
include `http://gs-{crew_id}:5476` in its allowed origins — exactly what the
transport sends as `Origin`.

## Scope

- `transport/lifecycle.py` — `_patch_crew_config`: add `dashboard.url` to the
  config patch dict
- `openspec/specs/transport/dashboard-proxy/spec.md` — add/update the WS
  scenario to document this requirement
- Tests: add a unit test asserting `_patch_crew_config` includes
  `dashboard.url` in the patched config

## Impact

- Fixes: KiroCrew dashboard WS connection (101 instead of 403), unlocking the
  sessions list, live task updates, and import modal dismissal
- No security regression: `dashboard.url` is the gateway's own origin; the
  allowed set still excludes all external/attacker origins
- No API or MCP tool changes
- Prerequisite: TRN-189 (merged)
