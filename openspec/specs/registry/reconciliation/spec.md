# registry/reconciliation Specification

## Purpose

Defines reconciliation of durable crew registry records with runtime state.

## Requirements

### Requirement: Config patch applied on reconcile restart

When a stopped crew is started on demand after a transport restart, the system SHALL apply pending configuration patches, including `spawn_min_memory_gb`, before marking it running, using the normal recovery path. Startup reconciliation SHALL NOT start a stopped container solely to apply patches.

#### Scenario: Stopped crew restored after transport restart
- **WHEN** an operation or due work wakes a stopped crew after transport restart
- **THEN** `_patch_crew_config` is called before the crew is marked running

#### Scenario: Config patch idempotent on repeated restarts
- **WHEN** the same crew is woken after repeated transport restarts
- **THEN** each demand-driven recovery applies `_patch_crew_config` without error and reflects current transport defaults

### Requirement: Registry reconciliation is idempotent

`_reconcile_registry` SHALL produce the same registry state whether
called once or multiple times in succession for the same set of running
containers.

#### Scenario: Reconcile called twice without container changes
- **WHEN** `_reconcile_registry` is called a second time while all
  previously-reconciled crews are already running
- **THEN** no container is restarted again and registry state is unchanged

#### Scenario: Reconcile tolerates containers already running
- **WHEN** a crew container is already in running state at reconcile time
- **THEN** `_reconcile_registry` does not restart it and does not error

### Requirement: Reconcile registry deletion is timestamp-guarded

`_reconcile_registry` SHALL NOT delete a crew entry that was re-registered between
the snapshot and the write-back. Before deleting any entry from `to_remove`, the
transport SHALL verify under the write-back lock that the entry's `created_at`
timestamp matches the value captured in the snapshot.

#### Scenario: Concurrent launch prevents stale reconcile deletion
- **WHEN** `_reconcile_registry` marks crew X for removal
- **AND** a concurrent `launch()` re-registers crew X with a new `created_at` before
  the write-back lock is acquired
- **THEN** the reconcile write-back DOES NOT delete the new crew X entry

#### Scenario: Genuinely stale entry is still removed
- **WHEN** `_reconcile_registry` marks crew X for removal
- **AND** no concurrent launch re-registers crew X
- **THEN** the reconcile write-back removes crew X as normal

### Requirement: Registry reconciliation on startup

The system SHALL reconcile the crew registry against actual Podman state on transport startup without starting stopped crew containers. It SHALL preserve their workspaces, schedules, dashboard allocations and registry records, and SHALL mark existing stopped containers stopped. It SHALL retain the existing guarded handling of containers confirmed absent and tolerate transient Podman errors without deleting records.

#### Scenario: Container no longer exists
- **WHEN** transport starts and a registered crew's container is confirmed absent from Podman
- **THEN** the system removes that crew from the registry under the existing guarded deletion rules

#### Scenario: Container exists but stopped
- **WHEN** transport starts and a registered crew's container exists but is not running
- **THEN** it remains stopped and registered without a gateway readiness wait or cookie mint

#### Scenario: Container is already running
- **WHEN** transport starts and a registered crew's container is running
- **THEN** it is reconciled without an unnecessary restart

#### Scenario: Podman state is unavailable
- **WHEN** an existence or running-state check fails transiently
- **THEN** the affected crew record is retained and the error is logged

#### Scenario: A crew wakes while reconciliation is in progress
- **WHEN** reconciliation observes a stopped crew and a concurrent operation starts it before the status write
- **THEN** the stale observation does not overwrite the newer running state

### Requirement: Eager registry self-healing for externally stopped containers

When `crews()` or `_ensure_crew_running` finds a registry entry marked running whose container is stopped, the transport SHALL write `status: "stopped"` before returning. This supplements startup reconciliation and SHALL NOT restart the container.

#### Scenario: crews() heals a stale running entry
- **WHEN** `crews()` is called and a crew has `status: "running"` in the
  registry but its Podman container is not running
- **THEN** the registry entry for that crew is updated to `status: "stopped"`
  before `crews()` returns

#### Scenario: _ensure_crew_running heals stale entries found during limit check
- **WHEN** `_ensure_crew_running` iterates registry entries to count running
  crews and finds an entry with `status: "running"` whose container is not
  actually running
- **THEN** that entry's registry status is corrected to `"stopped"` as part
  of the count loop, before `_ensure_crew_running` makes its limit decision

#### Scenario: Self-healing does not affect entries that are correctly stopped
- **WHEN** a registry entry already has `status: "stopped"` and its container
  is confirmed not running
- **THEN** no registry write occurs for that entry — the write-back is only
  triggered by a `running`-to-`stopped` discrepancy

#### Scenario: Self-healing does not restart the container
- **WHEN** a stale `status: "running"` entry is healed to `"stopped"` during
  a `crews()` or limit-check call
- **THEN** the container is NOT automatically restarted — healing only corrects
  the registry status; restart happens only when a tool call explicitly
  requires the crew (dispatch, pickup, etc.)
