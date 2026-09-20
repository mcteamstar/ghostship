## Context

See proposal.md — Why.

`_migrate_crew_network` (lifecycle.py ~L1392–1465) moves a container from `ga-net` to
`ga-starboard`. It is called from `_reconcile_registry` at transport startup (~L1510–1515).
A follow-up cleanup block (~L1574–1592) attempts to delete the `ga-net` network if no
containers remain on it. The `ga-net` network is never created for new crews; any
pre-0.6.0 containers that survived on a running instance would have been migrated on
the first 0.6.0 startup. There are none left on academy or any known deployment.

## Goals / Non-Goals

**Goals**
- Remove `_migrate_crew_network` and all call sites from `lifecycle.py`
- Remove the `ga-net` cleanup block from `_reconcile_registry`
- Clean up any `ga-net` references in comments describing the reconciliation flow

**Non-Goals**
- Removing `GA_STARBOARD_NETWORK` constant or any other network-related code
- Changing reconciliation logic beyond the migration path

## Decisions

**Delete unconditionally, no feature flag.**
There is no scenario where `_migrate_crew_network` needs to run on a 0.6.0+
transport. All new crews are created on `ga-starboard`. A flag would add complexity
for zero benefit.

**Delete cleanup block too.**
`ga-net` is never created on a fresh install. The cleanup block is a no-op that
needlessly calls the Podman containers API on every startup.

## Risks / Trade-offs

[Risk] An operator somehow has a pre-0.6.0 container still on `ga-net` →
Mitigation: Extremely unlikely — anyone on 0.6.0+ would have had the shim run on
their first startup months ago. Accept the risk; document in CHANGELOG if needed.

## Migration Plan

No deployment steps needed beyond the normal code change + deploy cycle.
The function is deleted; `ga-net` containers (if any) would simply not be migrated —
but that scenario cannot occur on a 0.6.0+ transport.
