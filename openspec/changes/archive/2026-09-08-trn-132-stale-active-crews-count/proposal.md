## Why

When a crew container is stopped outside ghostship (via `podman stop`, a VM reboot, or the idle monitor stopping a crew that the registry hasn't caught up with), the registry entry retains `status: "running"`. Because both the `crews()` response and the `_ensure_crew_running` active-limit check count running crews by reading registry status rather than querying Podman, a stopped container inflates `active_crews` until the next transport restart. On constrained installs this can prevent legitimate dispatches or launches even though capacity is actually available.

## What Changes

- **`crews()` response**: compute `active_crews` by querying actual Podman container state rather than trusting registry `status` field. A container that is registered as `running` but not actually running SHALL NOT count toward `active_crews` or appear with `status: "running"` in the response.
- **`_ensure_crew_running` active-limit check**: when counting running crews against `GA_MAX_ACTIVE_CREWS`, cross-check each `status == "running"` registry entry against Podman; entries whose container is not running SHALL be excluded from the count (and the registry entry updated to `stopped` as a side effect).
- **Registry self-healing write-back**: both code paths above SHALL write `status: "stopped"` back to any registry entry where the container is found to be stopped, so the registry converges without waiting for a transport restart.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `crew-lifecycle`: The active crew limit check and the `crews()` active_crews count must reflect actual Podman container state, not stale registry status.
- `idle-and-recovery`: Registry entries for externally stopped containers are healed eagerly (on next `crews()` or `_ensure_crew_running` call) rather than only at transport startup reconciliation.

## Impact

- `transport/server.py` — `crews()` handler: Podman `container_is_running` check per crew; write-back if mismatch; derive `active_crews` from actual running count.
- `transport/lifecycle.py` — `_ensure_crew_running`: active-limit count loop adds `container_is_running` check; writes back stale entries.
- `tests/unit/test_server.py` — tests for `active_crews` field when a registered-running crew's container is stopped.
- `tests/unit/test_lifecycle.py` — tests for active-limit count excluding containers that are registered running but actually stopped.
- No breaking changes to the MCP tool interface; `active_crews` and per-crew `status` values become more accurate, not different in schema.
