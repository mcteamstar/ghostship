# Proposal

## Why

When dashboard authentication is enabled, a client without a dashboard session can open a WebSocket through the dashboard port. Ghostship supplies its own trusted gateway cookie upstream, so KiroCrew cannot identify the original unauthenticated client.

## What Changes

- Validate the original client's dashboard session before opening an upstream WebSocket when an API key is configured.
- Enforce an appropriate browser origin policy for cookie-authenticated handshakes, and preserve deliberately unauthenticated installations.
- Reconcile the proxy specification with the existing transport-side authentication requirement and add regression coverage through the actual proxy path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/dashboard-proxy`: require client authentication and origin protection before proxying dashboard WebSockets.

## Impact

Transport WebSocket dispatch, dashboard session validation, proxy tests, and dashboard integration checks. Existing dashboards on keyed installations require valid sessions; installations with no configured API key retain open access.
