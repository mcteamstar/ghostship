# testing/registry Specification

## Purpose

Defines verification coverage for registry behavior.

## Requirements

### Requirement: _reconcile_registry test coverage

The test suite SHALL exercise every branch of `_reconcile_registry` using a mock
`PodmanClient`, verifying observable side effects on the registry JSON file.

#### Scenario: Orphaned login container is swept
- **WHEN** `_reconcile_registry` runs AND a container named `ga-login-*` exists
- **THEN** the container is removed (via `_nuke_login_container`) and does not appear in the registry

#### Scenario: Gone crew is removed from registry
- **WHEN** `_reconcile_registry` runs AND a registered crew's container no longer exists (podman reports not found)
- **THEN** that crew entry is removed from the registry

#### Scenario: Stopped crew is restarted and cookie refreshed
- **WHEN** `_reconcile_registry` runs AND a registered crew's container exists but is stopped AND the gateway becomes ready within 30s
- **THEN** the container is started, a new cookie is minted, and the registry entry is updated with status "running" and the new cookie

#### Scenario: Stopped crew gateway fails to start
- **WHEN** `_reconcile_registry` runs AND a stopped crew's container is started but the gateway does not become ready within 30s
- **THEN** the registry entry is updated with status "stopped" (not removed)

#### Scenario: Running crew is left alone
- **WHEN** `_reconcile_registry` runs AND a registered crew's container is running
- **THEN** no action is taken on that crew entry

#### Scenario: Stale launching placeholder is cleaned up
- **WHEN** `_reconcile_registry` runs AND a registry entry has status "launching" but the container does not exist
- **THEN** that entry is removed from the registry

#### Scenario: _mint_cookie returns a non-empty token and stores it in the registry
- **WHEN** `_mint_cookie` is called for a running crew
- **THEN** it returns a non-empty token string and the token is written into the registry entry for that crew

#### Scenario: _refresh_cookie updates the in-memory entry atomically
- **WHEN** `_refresh_cookie` is called while a crew is active
- **THEN** the registry entry's cookie field is updated atomically without a window where a stale cookie is observable (regression guard for H-1 fix)

### Requirement: _reconcile_registry handles stale snapshot

When `_reconcile_registry` reads the registry snapshot and then releases the
lock for the per-crew restart loop, the registry state may have changed by the
time it writes back. The write-back SHALL re-read the registry under the lock
and merge only changes for crews that still exist in the current registry,
to avoid resurrecting entries that were removed concurrently.

#### Scenario: Crew removed between snapshot and write-back
- **WHEN** `_reconcile_registry` snapshots crew X, releases the lock, and another thread removes crew X before the write-back lock is acquired
- **THEN** the write-back does NOT re-add crew X to the registry

### Requirement: Crew registry key compatibility has test coverage
The test suite SHALL cover canonical `comps` loading, the legacy `compositions` alias, matching dual keys, and conflicting dual keys.

#### Scenario: Canonical comps key is loaded
- **WHEN** a registry fixture contains a valid `comps` key
- **THEN** the test verifies all configured comps are available

#### Scenario: Legacy compositions key is loaded
- **WHEN** a registry fixture contains only `compositions`
- **THEN** the test verifies all configured comps are available

#### Scenario: Matching registry keys are accepted
- **WHEN** a registry fixture contains both keys with equal entries
- **THEN** the test verifies the entries are loaded once

#### Scenario: Conflicting registry keys prefer comps
- **WHEN** a registry fixture contains both keys with different entries
- **THEN** the test verifies the `comps` entries are loaded and `compositions` is ignored
