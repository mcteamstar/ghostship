## Context

See proposal.md for motivation.

`active_crews` is currently derived in two places:

1. **`crews()` handler** (`server.py`): counts registry entries where `status == "running"`.
2. **`_ensure_crew_running` active-limit check** (`lifecycle.py`): iterates registry entries and counts those where `status == "running"`.

Neither calls `container_is_running`. `_reconcile_registry()` runs only at transport startup, so the window between an external container stop and the next transport restart is unbounded.

Both sites already have access to `podman` and the registry. The registry lock pattern is established. The fix is surgical: add a `container_is_running` check at each count site, then write back any discovered discrepancies.

## Goals / Non-Goals

**Goals:**
- `active_crews` in `crews()` reflects the number of Podman-confirmed running containers at call time.
- The `GA_MAX_ACTIVE_CREWS` limit in `_ensure_crew_running` counts only Podman-confirmed running containers.
- Stale `status: "running"` entries are corrected to `"stopped"` on first observation by either code path.

**Non-Goals:**
- Replacing or modifying `_reconcile_registry` — startup reconciliation remains unchanged.
- Adding new Podman calls elsewhere (e.g. `dispatch`, `pickup`) — `_ensure_crew_running` is already called on those paths and handles state correction.
- Eager restart of externally stopped containers — the self-heal only corrects the registry; restart still happens only when a tool call requires the crew.

## Decisions

### Decision: Check container state at the count site, not before

**Chosen**: Add `container_is_running` inside the loop that counts active crews, excluding and writing back entries where there is a mismatch.

**Alternative**: Call `_reconcile_registry()` at the top of `crews()` and `_ensure_crew_running`. Rejected — reconciliation also does network migrations and config patches; it is too heavy and has side effects unrelated to counting.

**Alternative**: Add a background poller that periodically syncs registry to Podman state. Rejected — adds concurrency complexity and a background thread; the on-demand check is simpler, sufficient, and self-limiting in cost.

### Decision: Podman checks outside the lock; write-back is a separate acquisition

The established pattern in `_reconcile_registry` is: load registry under `_registry_lock`, release lock, do Podman calls outside the lock, then re-acquire to write back. Both sites MUST follow this pattern — Podman queries (`container_is_running`) SHALL NOT be made while holding `_registry_lock`, as that creates unnecessary lock contention.

`_ensure_crew_running` currently loads and counts in a single `with _registry_lock` block. The new version will: acquire lock → load snapshot → release lock → iterate snapshot and call `container_is_running` per entry → re-acquire lock → apply corrections and save → release lock.

`crews()` already releases the lock after `_load_registry()` before doing any Podman work. The write-back will be a second acquisition (the same pattern used throughout the codebase), not the same one as the load.

### Decision: `crews()` does Podman check only for `status == "running"` entries

`stopped` and `auth_required` entries are skipped — they already reflect a non-running state and do not require a Podman call. This keeps the `container_is_running` call count proportional to the number of running entries, not total registered crews.

### Decision: `uptime_secs` calculation in `crews()` already calls `container_inspect`

The existing `crews()` code calls `container_inspect` for each `status == "running"` crew to derive `uptime_secs`. The new `container_is_running` check is lighter (uses `/libpod/containers/{name}/json` or a list filter). Ordering: check `container_is_running` first; only proceed to `container_inspect` for uptime if the container is confirmed running.

## Risks / Trade-offs

**Extra Podman calls per `crews()` invocation** → One `container_is_running` call per `status == "running"` registry entry. On a typical install with ≤6 crews this is negligible. Mitigation: call is a fast metadata query, not a start/stop operation.

**Registry write on every `crews()` call that finds a discrepancy** → Bounded: only triggers when there is an actual mismatch, not on every call. The write is a small JSON file update with the established fsync pattern.

**Race with `_reconcile_registry` on transport startup** → Both may try to write the same entry to `"stopped"`. The registry lock serialises them; the second write is a no-op (already `"stopped"`).

## Migration Plan

No schema changes. The `status` field in the registry and in `crews()` responses already has `"running"` and `"stopped"` as valid values; callers that see `"stopped"` where they previously saw `"running"` for a container they didn't stop are corrected, not broken. No deployment steps beyond a normal transport image rebuild and restart.
