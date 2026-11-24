# Proposal

## Why

During device-code login, operators must switch to a browser and manually open or copy the printed URL. Letting them press Enter in the waiting terminal removes that extra step while preserving the existing manual route.

## What Changes

- Show an Enter-to-open hint while an interactive device-code login is waiting.
- On Enter, open the displayed login URL in the user's default browser and continue polling authentication.
- Keep browser-launch errors non-fatal so operators can still use the printed URL.
- Leave authorization-code login and non-interactive invocations unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `cli`: Interactive device-code login can open its login URL on Enter while polling.

## Impact

The `ghostship auth login` CLI wait loop and its unit tests are affected. The behavior uses Python's standard-library browser integration and adds no dependency or transport API change.
