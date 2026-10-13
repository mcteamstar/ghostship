# Proposal

**Plane ticket:** TRN-238

## Why

Two concurrency bugs found in the 0.7.0 independent review (indy-070) affect the lifecycle layer. Both are latent in production — QA-1 causes multi-second registry lockouts at higher crew counts; QA-2 causes silent post-nuke setup failures that are hard to diagnose. Neither was covered by TRN-208 (crew-lifecycle-resilience), which addressed deadlocks and registry durability.

## What Changes

- **QA-1 — Release `_registry_lock` before `container_stop`**: `_idle_monitor` currently holds `_registry_lock` across the entire `container_stop` call (`transport/monitors.py ~L551–575`), which can block for 10–30s. Fix: release the lock before calling `container_stop`, set an in-flight state flag to prevent double-stop, re-acquire for the registry write-back.
- **QA-2 — Check registry entry existence after restart**: `_ensure_crew_running` writes the dashboard cookie and continues post-start setup after `container_start` returns, without verifying the registry entry still exists. A concurrent `nuke()` may have removed it. Fix: add an existence check after `container_start` and before post-start setup; log and return if the entry is gone.
- **QA-3 (low) — Harden `/continue` path-component match**: `_crew_api_with_recovery` uses `'continue' in path` substring match to bypass cookie refresh on 400 responses. Harden to `path.endswith('/continue')` to prevent false matches on future routes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: add requirements for lock-release-before-stop pattern in idle monitor, post-restart registry existence check in `_ensure_crew_running`, and hardened path-component match in `_crew_api_with_recovery`.

## Impact

- `transport/monitors.py` — `_idle_monitor`: release lock before `container_stop`, in-flight flag
- `transport/lifecycle.py` — `_ensure_crew_running`: existence check after `container_start`; `_crew_api_with_recovery`: endswith match
- Tests: unit tests for each fix
