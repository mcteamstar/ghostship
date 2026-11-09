# Spec Delta

## MODIFIED Requirements

### Requirement: Config patch applied on reconcile restart

When a stopped crew is started on demand after a transport restart, the system SHALL apply pending configuration patches, including `spawn_min_memory_gb`, before marking it running, using the normal recovery path. Startup reconciliation SHALL NOT start a stopped container solely to apply patches.

#### Scenario: Stopped crew restored after transport restart
- **WHEN** an operation or due work wakes a stopped crew after transport restart
- **THEN** `_patch_crew_config` is called before the crew is marked running

#### Scenario: Config patch idempotent on repeated restarts
- **WHEN** the same crew is woken after repeated transport restarts
- **THEN** each demand-driven recovery applies `_patch_crew_config` without error and reflects current transport defaults
