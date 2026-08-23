## Purpose

Defines the observable startup and recovery contracts for crew containers:
what the transport must do when launching a crew for the first time and when
restoring one after a transport restart or host reboot.

## ADDED Requirements

### Requirement: Config patch applied on reconcile restart

When the transport starts and discovers a stopped crew container in the
registry, it SHALL apply all pending configuration patches (including
`spawn_min_memory_gb`) to that container before marking it as running, in
the same way patches are applied during initial crew creation.

#### Scenario: Stopped crew restored after transport restart
- **WHEN** `_reconcile_registry` restarts a stopped crew container
- **THEN** `_patch_crew_config` is called on that container before the
  crew is marked as running in the registry

#### Scenario: Config patch idempotent on repeated restarts
- **WHEN** the transport is restarted multiple times and the same crew is
  restored each time
- **THEN** each restart applies `_patch_crew_config` without error, and
  the crew's configuration reflects the current transport defaults

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
