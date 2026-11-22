# Proposal

## Why

When the external-bind secret guard is enabled, a wildcard transport bind currently bypasses it. With no transport secret, middleware is pass-through, so a listener bound to all interfaces can start without the protection the operator explicitly requested.

## What Changes

- Treat wildcard binds as externally reachable for the enabled missing-secret guard.
- Refuse startup for wildcard binds with no transport secret when the guard is enabled.
- Preserve the current warn-and-continue behavior when the guard is false or unset, and preserve startup when a secret is present.
- Update focused server tests for wildcard, specific external, and loopback binds.

## Capabilities

- `transport/bind-guard`
- `testing/server`

## Impact

Transport startup validation and its tests change. The default guard remains warn-only, so default installations without an explicitly enabled guard retain their current startup behavior.
