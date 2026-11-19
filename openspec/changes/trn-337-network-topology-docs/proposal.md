# Proposal

## Why

The generated Compose topology attaches Radar to `ga-portside`, but the network-split and configuration requirements omit Radar. Other steady-state requirements use the retired `ga-net` layout or omit current Ghost Academy containers from the dedicated-instance inventory. The dashboard-proxy requirements also describe a crew-hostname WebSocket origin that the transport no longer sends.

## What Changes

- Reconcile the network-split, crew-lifecycle, installation, dashboard-proxy, and dashboard-auth requirements with the current Compose and runtime network assignments.
- Correct operator documentation and specify code-backed legacy `ga-net` cleanup: install removes it only when empty, and uninstall attempts removal after Ghost Academy containers are removed. Remove the unsupported Transport-startup crew-migration requirement.
- Add the same complete network membership table to configuration and architecture documentation, including every backend-specific login-container prefix.
- Remove the obsolete crew-hostname WebSocket Origin requirement and retain the loopback Origin currently sent by the transport.
- Do not change Compose or runtime network assignments.

## Capabilities

### New Capabilities

### Modified Capabilities

- `transport/network-split`: document current static and per-container membership and keep only code-backed legacy cleanup behavior.
- `transport/dashboard-proxy`: identify `ga-starboard` as the Transport-to-crew network.
- `transport/dashboard-auth`: describe direct Transport access over the current networks.
- `crew-lifecycle`: name `ga-starboard` as the crew network in the resource-naming contract.
- `installation`: update idempotent-install and dedicated-instance descriptions to use the current static networks and service inventory.

## Impact

OpenSpec network, dashboard, lifecycle, and installation specs, plus `docs/configuration.md` and `docs/architecture.md`. Compose behavior is the reference point; no runtime change is proposed.
