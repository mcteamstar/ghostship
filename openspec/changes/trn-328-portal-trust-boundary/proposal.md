# Proposal

## Why

The Caddy admin API is reachable on the shared portside network even though only Transport needs it to manage dashboard routes. Radar also holds the transport secret, which currently lets a direct HTTP request reach the crew UI proxy without passing Caddy's dashboard-session check. The intended boundary is that Transport manages Caddy and Radar reads fleet data; the fix should preserve the existing network topology where possible.

## What Changes

- Restrict Caddy admin access to Transport without adding a network solely for this purpose; prefer a permissioned Unix-domain socket shared only with Transport. Use an authenticated proxy only if explicit request credentials are required.
- Require dashboard-session authorization at the Transport HTTP UI proxy when API-key authentication is enabled, including direct internal callers.
- Preserve Radar's intended fleet-reading behavior and add regression coverage for both trust boundaries.

## Capabilities

### New Capabilities

### Modified Capabilities
- `transport/caddy-proxy`: restrict Caddy's high-privilege admin interface to Transport using a permissioned local socket.
- `transport/dashboard-proxy`: enforce dashboard sessions at the Transport UI proxy for keyed installations.

## Impact

Compose socket-volume configuration, Caddy initial configuration and dynamic admin API use, dashboard proxy authorization, and focused control-plane/authentication tests. No public network, dashboard URL, or port changes are intended.
