## MODIFIED Requirements

### Requirement: Active crew limit enforced before restart

The transport SHALL enforce a separate limit on simultaneously running crew
containers via `GA_MAX_ACTIVE_CREWS` (default: 3). Before starting a stopped
crew container, `_ensure_crew_running` SHALL count the number of currently
running containers by verifying actual Podman container state, not by reading
registry `status` alone. Any registry entry whose `status` is `"running"` but
whose Podman container is not actually running SHALL be excluded from the running
count and SHALL have its registry `status` corrected to `"stopped"` as a side
effect of the check.

This limit protects host memory independently of the registered-crew count: an
operator can keep many idle crews registered while preventing too many from
running simultaneously.

#### Scenario: Active limit not reached

- **WHEN** `_ensure_crew_running` is called for a stopped crew and fewer than
  `GA_MAX_ACTIVE_CREWS` crew containers are currently running according to Podman
- **THEN** the crew container is started normally

#### Scenario: Active limit reached

- **WHEN** `_ensure_crew_running` is called for a stopped crew and
  `GA_MAX_ACTIVE_CREWS` crew containers are actually running in Podman
- **THEN** `_ensure_crew_running` raises a clear error indicating the active crew
  limit and instructing the operator to wait for a running crew to idle out or nuke one

#### Scenario: Stale registry entry excluded from active count

- **WHEN** `_ensure_crew_running` counts running crews and a registry entry has
  `status: "running"` but `container_is_running` returns false for its container
- **THEN** that entry is NOT counted toward `GA_MAX_ACTIVE_CREWS` and its
  registry status is corrected to `"stopped"`

#### Scenario: Already-running crew is unaffected

- **WHEN** `_ensure_crew_running` is called for a crew that is already running
- **THEN** the active limit check is skipped — the crew is not counted a second time

#### Scenario: GA_MAX_ACTIVE_CREWS=0 disables the limit

- **WHEN** `GA_MAX_ACTIVE_CREWS` is set to `0`
- **THEN** the active limit check is skipped entirely — no cap on running crews

## ADDED Requirements

### Requirement: crews() active_crews reflects actual Podman state

The `crews()` tool SHALL compute `active_crews` by verifying actual Podman
container state for every registry entry whose `status` is `"running"`. A crew
SHALL be included in `active_crews` only if its container is confirmed running
via `container_is_running`. A crew whose registry says `"running"` but whose
container is not actually running SHALL be reported with `status: "stopped"` in
the response and SHALL NOT be counted in `active_crews`. The registry entry for
any such crew SHALL be corrected to `status: "stopped"` as a side effect of
the `crews()` call.

#### Scenario: Registry-running crew whose container is actually running

- **WHEN** `crews()` is called and a crew has `status: "running"` in the registry
  and its Podman container is confirmed running
- **THEN** that crew appears with `status: "running"` and is counted in `active_crews`

#### Scenario: Registry-running crew whose container is externally stopped

- **WHEN** `crews()` is called and a crew has `status: "running"` in the registry
  but its Podman container is not running
- **THEN** that crew appears with `status: "stopped"` in the response, is NOT
  counted in `active_crews`, and the registry entry is corrected to `"stopped"`

#### Scenario: active_crews matches confirmed running container count

- **WHEN** `crews()` is called after one or more crew containers have been
  stopped outside ghostship (e.g. via `podman stop` or a VM reboot)
- **THEN** `active_crews` equals the number of containers that are actually
  running in Podman, not the number of registry entries with `status: "running"`
