# Proposal

## Why

The on-demand wake path added in TRN-316 has two correctness gaps. A wake that fails after the container starts leaves it running while the registry records it stopped, and memory admission reads live host memory without counting starts still in flight, so two simultaneous wakes can both pass. The unit test that claims to cover in-flight memory accounting stubs in the missing behaviour, so it passes without testing the code.

## What Changes

- A wake that fails after `container_start` (config patch, gateway wait or cookie mint) stops the container it started before reporting failure, so the registry and Podman agree.
- A successful gateway wake updates registry status even when a session cookie cannot be minted, and waiters see the leader's real outcome.
- Memory admission subtracts an estimate for each reserved in-flight start before comparing against the free-memory floor.
- The memory wait no longer holds the capacity lock for its full timeout, so one low-memory start does not block unrelated launches.
- Replace `test_pending_start_is_included_in_memory_admission` with a test that exercises the real accounting.
- Remove the unused `_run_restart_cycle`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `idle-and-recovery`: the "Due work wakes stopped crews after startup" requirement gains in-flight memory accounting and failed-wake cleanup scenarios.

## Impact

- `transport/launcher.py`: `ensure_running` wake leader path, `_check_memory_gate`, `_wait_for_memory` call site, `_run_restart_cycle` removal.
- `tests/unit/test_lifecycle.py`, `tests/integration/test_on_demand_recovery.py`.
- No API change.
