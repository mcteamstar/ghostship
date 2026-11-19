# Proposal

## Why

The deployed Compose topology attaches Radar to `ga-portside`, but the network-split and configuration specs describe that network as Portal and Transport only. Other steady-state docs still describe the retired `ga-net` layout, making the source of truth contradictory.

## What Changes

- Reconcile the network-split, Radar, crew-lifecycle, and installation requirements with the current steady-state Compose topology.
- Correct operator documentation and retain `ga-net` only where it describes a real migration step.
- Do not change network membership or add networks as part of this change.

## Capabilities

### New Capabilities

### Modified Capabilities

- `transport/network-split`: document the current membership of `ga-portside` and `ga-starboard` consistently.
- `crew-lifecycle`: name `ga-starboard` as the crew network in the resource-naming contract.
- `installation`: update idempotent-install and dedicated-instance descriptions to use the current static networks.

## Impact

OpenSpec network and lifecycle specs, `docs/configuration.md`, and related architecture documentation. Compose behavior is the reference point; no runtime change is proposed.
