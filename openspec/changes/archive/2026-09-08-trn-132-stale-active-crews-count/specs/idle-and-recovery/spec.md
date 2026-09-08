## ADDED Requirements

### Requirement: Eager registry self-healing for externally stopped containers

The transport SHALL correct stale `status: "running"` registry entries for
crew containers that have been stopped outside ghostship (e.g. via direct
`podman stop`, a VM reboot, or a Podman machine restart) during normal
operation — not only at transport startup reconciliation. Specifically,
whenever `crews()` or `_ensure_crew_running` checks container state and
discovers a registry entry with `status: "running"` whose container is not
actually running, it SHALL write `status: "stopped"` back to the registry
for that entry before returning.

This self-healing is a side effect of the state verification performed in
those two code paths. It does not replace startup reconciliation; it
supplements it so that the registry converges to accurate state within the
first operation that observes the discrepancy, rather than waiting for the
next transport restart.

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
