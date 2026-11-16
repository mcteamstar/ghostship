# Proposal

## Why

The documented `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND` guard is not passed into the generated Transport container environment, and its documentation describes the API key and portal host even though the runtime check concerns the transport secret and transport bind address. The README also says the portal publishes on all interfaces by default, while the installer defaults to loopback. Operators cannot rely on these docs to understand the effective exposure or configure the guard they intend.

## What Changes

- Carry the guard setting through config resolution and generated Compose into `ga-transport`.
- Document the actual guarded secret and bind address, plus the default warn-only behavior.
- Correct the README's default-bind statement to match the loopback-only portal default.
- Add tests covering generated environment and startup behavior with the guard enabled and disabled.

## Capabilities

### New Capabilities
- `transport-bind-guard`: define startup behavior and install-time delivery for the transport-secret external-bind guard.

### Modified Capabilities
- `installation`: ensure operator-facing docs agree that `HOST` defaults to loopback and controls only Caddy's published address.

## Impact

YAML/environment config mapping, installer environment construction, generated Compose, Transport startup validation, operator documentation, and focused tests. This does not change the separate API-key check on Caddy's published host address.
