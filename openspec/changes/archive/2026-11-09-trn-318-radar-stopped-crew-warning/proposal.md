# Proposal

## Why

Radar reports an unreachable gateway for stopped crews, although the gateway is expected to be unavailable while the crew is stopped.

## What Changes

- Hide the gateway warning for stopped crews while retaining warnings for unreachable running crews.
- Verify the row rendering for stopped, healthy running and unhealthy running crews.
- Order crews by creation time, newest first, within the running and inactive sections by default; retain the Last Task sort control.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ga-radar`: make gateway health warnings reflect crew state.

## Impact

Radar's fleet table rendering and its frontend verification. A local change has already been made and will be reviewed as part of implementation.
