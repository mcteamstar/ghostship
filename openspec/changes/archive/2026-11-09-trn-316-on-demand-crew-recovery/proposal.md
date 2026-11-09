# Proposal

## Why

Transport startup currently restarts every retained stopped crew, accumulating memory pressure and delaying readiness after an upgrade or reboot. Most workspaces do not need to run until requested.

## What Changes

- Reconcile existing container state without starting stopped crews; keep their workspaces, registry and routes available.
- Wake crews on demand and when enabled Ghostship-tracked work becomes due; document the limitation for gateway-only schedules.
- Guard startup status writes against concurrent wakeups and coordinate capacity admission across crews.
- Document that waking an existing crew retains its existing image rather than upgrading it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `idle-and-recovery`: replace eager startup restoration with on-demand recovery.
- `crew-lifecycle`: move stopped-crew config patching to the demand-driven restart path.

## Impact

Transport startup reconciliation, schedule and Captain monitoring, crew recovery, documentation and regression coverage.
