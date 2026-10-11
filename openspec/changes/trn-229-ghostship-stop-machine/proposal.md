# Proposal

## Why

`ghostship stop` only stops the `ga-transport` container, leaving the Podman machine (macOS) or dedicated Podman socket service (Linux) and all crew containers running and consuming RAM. There is no "fleet sleep" command that frees all resources without destroying state — operators must manually stop the machine.

## What Changes

- `ghostship stop` extended to also stop the Podman machine / dedicated service after stopping `ga-transport` and `ga-portal`.
  - macOS: `podman machine stop <GA_MACHINE_NAME>`
  - Linux (dedicated): `systemctl --user stop podman-<GA_MACHINE_NAME>.service` (or equivalent socket stop)
  - Linux (non-dedicated): `systemctl --user stop podman.socket` or `podman system service` teardown
- `ghostship start` already handles machine/service restart — no changes needed there.
- `ga-portal` is also stopped (currently missing from `cmd_stop`).
- All crew containers and volumes are preserved; `_ensure_crew_running` restarts them on next use.
- The `ghostship status` output helpfully reflects when the machine is stopped vs just the transport.
- `docs/configuration.md` and CLI help text updated to describe the new stop behaviour.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `trn-cli`: extend the `ghostship stop` requirement to cover machine/service shutdown.

## Impact

- `ghostship` CLI script (`cmd_stop`) — ~20 lines
- `scripts/start.sh` — already handles machine restart, no changes needed
- `docs/configuration.md` — stop behaviour description
- Unit tests for `cmd_stop`
