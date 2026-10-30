## MODIFIED Requirements

### Requirement: Cookie refresh is atomic under the registry lock

The transport SHALL update the in-memory crew entry's `cookie` field inside the
registry lock, atomically with the registry persistence call. No window SHALL exist
between the registry save and the in-memory update during which a concurrent reader
could observe a stale cookie value.

#### Scenario: Concurrent request sees fresh cookie after refresh
- **WHEN** `_refresh_cookie` completes for crew X
- **THEN** any concurrent request reading `crew["cookie"]` for crew X sees either
  the old cookie (before lock acquisition) or the new cookie (after release), never
  a state where the registry has the new cookie but the dict still has the old one

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

### Requirement: ensure_running leader election is single-lock

The early-in-progress check and the leader election in `ensure_running` SHALL be
performed under a single lock acquisition. No lock-free read of startup state SHALL
precede the locked election.

#### Scenario: Only one caller wins leader election under concurrency
- **WHEN** two concurrent callers both enter `ensure_running` for the same crew
- **THEN** exactly one becomes the leader (starts the container)
- **THEN** the other becomes a waiter (blocks until the leader signals readiness)
- **THEN** the container is started exactly once
