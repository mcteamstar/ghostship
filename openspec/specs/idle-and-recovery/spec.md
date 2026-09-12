# Idle and Recovery Specification

## Purpose

Free host resources by stopping idle crew containers automatically, restart them transparently on next use, and recover the crew registry after a transport restart or full machine reboot — without the caller needing to manage container lifecycle manually.

## Requirements

### Requirement: Idle container stop
The system SHALL stop a crew's container after it has had no active dispatched tasks, no running cron execution, and no cron execution since its last activity for `GA_IDLE_TIMEOUT_SECS`, and SHALL NOT stop a crew that has active work regardless of elapsed idle time. A crew that has just completed setup SHALL have its activity timestamp initialized at setup completion, so the timeout is measured from that point rather than from a missing or zero timestamp. Any enabled cron job — regardless of whether it has fired yet — SHALL by itself count as active work and prevent an idle stop, since an enabled schedule is a standing commitment to run that a fire-history check alone cannot see before its first firing. When the idle monitor cannot determine crew activity due to a transient API error (connection failure, timeout, or unexpected response), it SHALL skip the crew for the current cycle and leave it running — it SHALL NOT proceed to stop a crew whose activity state is unknown.

#### Scenario: A freshly scheduled job with a long interval survives to its first firing
- **WHEN** a crew has an enabled cron job whose `every_secs` exceeds `GA_IDLE_TIMEOUT_SECS`, and that job has never yet fired
- **THEN** the idle monitor does not stop the crew, because the enabled job alone counts as active work

#### Scenario: A disabled job does not keep a crew alive
- **WHEN** a crew's only cron job is disabled and there is no other activity
- **THEN** the idle monitor does not treat that job as active work, and the crew is stopped once past `GA_IDLE_TIMEOUT_SECS`

#### Scenario: Crew idle past timeout
- **WHEN** a running crew has no non-done tasks and its `last_used` timestamp is more than `GA_IDLE_TIMEOUT_SECS` seconds in the past
- **THEN** the idle monitor stops the crew's container and marks its registry status `stopped`

#### Scenario: Crew has active tasks
- **WHEN** a crew's idle time exceeds `GA_IDLE_TIMEOUT_SECS` but it still has at least one non-done task
- **THEN** the idle monitor updates `last_used` and leaves the container running

#### Scenario: Cron execution keeps crew alive
- **WHEN** a running crew's gateway reports a cron execution in progress, or a cron `last_run_ts` newer than the crew registry's `last_used` timestamp
- **THEN** the idle monitor refreshes `last_used` and leaves the container running

#### Scenario: Crew awaiting auth
- **WHEN** a crew's registry status is `auth_required`
- **THEN** the idle monitor skips it entirely, never stopping a container that hasn't finished setup

#### Scenario: Newly completed setup receives a full idle window
- **WHEN** crew setup completes successfully and the crew is registered as `running`
- **THEN** the registry records the current time as `last_used` before the idle monitor can evaluate the crew

#### Scenario: API error during activity check
- **WHEN** the idle monitor's request to `/api/spawn` or `/api/crons` fails with a connection error, timeout, or unexpected HTTP response
- **THEN** the idle monitor skips that crew for the current cycle and leaves it running

### Requirement: Transparent restart on next use
The system SHALL detect a stopped crew container on the next `dispatch`, `pickup`, `steer`, `evac`, `deliver`, or `schedule` call, or on the next file GET/PUT request against the `/files/` endpoints (which is what actually moves bytes for `evac`/`deliver`), restart it, wait for its gateway, and refresh its session cookie before forwarding the request or returning a presigned URL. Because the required configuration patch is applied through `container_exec`, the restart path SHALL start the stopped container provisionally, apply the patch while that container is running, stop it, start it again, and wait for the gateway exactly once after the final start. The patch SHALL create its destination directory when it is absent, and the path SHALL NOT wait for the gateway after the provisional start. After the gateway is ready, the system SHALL reconcile the crew's schedule registry with the gateway's current cron state before reseeding — reading `/api/crons` and updating the registry entry for each job present in the gateway to match its reported enabled state and schedule type; only jobs absent from the gateway are then registered from the registry. The gateway is the source of truth for schedule state; the registry is a reseed bootstrap cache only.

#### Scenario: First caller after idle-stop
- **WHEN** any of those tools or file requests is made for a crew whose container is stopped
- **THEN** the system starts the container provisionally, applies configuration patches through exec, stops and starts the container again so the patch is loaded, waits for the gateway once, mints a new session cookie, updates the registry, and then forwards the original request

#### Scenario: Concurrent callers during restart
- **WHEN** a second call for the same crew arrives while a restart triggered by an earlier call is still in progress
- **THEN** the second caller waits for the in-progress restart to finish and then uses the refreshed crew record, rather than triggering a second concurrent restart

#### Scenario: deliver() returns a URL after restarting the crew
- **WHEN** the `deliver` tool is called for a crew whose container is currently stopped
- **THEN** the tool call itself performs the provisional start, exec patch, final restart, and single gateway wait before signing and returning the upload URL, and the later file POST retains its own recovery check

#### Scenario: Single gateway wait on wake
- **WHEN** a stopped crew container is woken through the normal stopped-container path
- **THEN** the container is started exactly twice, stopped once for the configuration bounce, and the gateway wait is performed exactly once after the final start; no gateway wait occurs between the provisional start and the exec patch

#### Scenario: Paused cron in gateway syncs to registry on restart
- **WHEN** a crew container restarts and its gateway reports a cron job with `"enabled": false`
- **THEN** the transport updates the registry entry for that job to `enabled: false`, does not re-register it, and the idle monitor subsequently sees no enabled cron job for that crew

#### Scenario: Missing cron registered from registry on restart
- **WHEN** a crew container restarts and a registry schedule entry is absent from the gateway's `/api/crons` response
- **THEN** the transport registers it in the gateway (the true bootstrap case — brand new container)

### Requirement: Registry reconciliation on startup
The system SHALL reconcile its crew registry against actual Podman state every time the transport process starts, removing entries for containers that no longer exist and restarting containers that exist but are stopped.

#### Scenario: Container no longer exists
- **WHEN** transport starts and a registered crew's container cannot be found in Podman
- **THEN** the system removes that crew from the registry

#### Scenario: Container exists but stopped
- **WHEN** transport starts and a registered crew's container exists but is not running (e.g. after a host or podman-machine reboot)
- **THEN** the system starts the container, waits for its gateway, refreshes its session cookie, and marks it `running`; if the gateway does not come back within the timeout, the crew is left marked `stopped` rather than removed

### Requirement: Survives podman-machine / host restarts
The system SHALL keep the transport container itself restarting automatically across a full Podman restart (machine stop/start on macOS, or a `systemctl --user` restart / relogin on Linux), via `--restart=always` plus an enabled `podman-restart.service`.

#### Scenario: Podman machine or host restarts
- **WHEN** the podman machine (macOS) or the user's systemd session (Linux) restarts
- **THEN** the `ga-transport` container comes back up on its own once Podman is running again, without any manual `podman run` or `podman start`

### Requirement: Schedule monitor reads gateway cron state as source of truth for enabled status

The schedule monitor SHALL determine whether a job is enabled by reading the `enabled` field from the gateway's `/api/crons` response for the crew, not from the transport registry. The registry's `sched["enabled"]` field SHALL be treated as a reseed bootstrap cache only — the same contract that applies to all other cron state since TRN-82.

When the gateway reports `enabled: false` for a scheduled job, the schedule monitor SHALL skip firing that job and SHALL write `enabled: false` back to the registry entry for that job, keeping the registry in sync with gateway state.

When the crew container is stopped and cannot be woken (gateway is unreachable), the schedule monitor SHALL fall back to the registry's `enabled` field as a best-effort signal — preserving the existing fail-open behaviour for stopped crews.

#### Scenario: Gateway reports job disabled — monitor skips and writes back

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": false`
- **THEN** the monitor does not fire the job, and writes `enabled: false` to the registry entry for that job

#### Scenario: Gateway reports job enabled — monitor fires normally

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": true`
- **THEN** the monitor fires the job as normal (existing behaviour)

#### Scenario: Crew stopped, gateway unreachable — monitor falls back to registry

- **WHEN** the schedule monitor evaluates a job for a crew that cannot be woken (`_ensure_crew_running` raises or the crew was already stopped before the gateway fetch), so the gateway's `/api/crons` response is unavailable
- **THEN** the monitor falls back to the registry's `enabled` field to decide whether to skip; if the registry shows `enabled: false` the job is skipped; if the registry shows `enabled: true` (or the field is absent) the job proceeds with the existing wake-and-fire path

#### Scenario: Gateway cron payload field is absent — monitor treats job as enabled

- **WHEN** the gateway's `/api/crons` response includes a job entry but the `"enabled"` field is absent
- **THEN** the monitor treats the job as enabled and fires it (fail-open, preserving existing behaviour)

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

### Requirement: _ensure_crew_running waiter propagates leader failure

When the leader coroutine in `_ensure_crew_running` fails to restart a crew (memory gate exceeded, active-crew limit, gateway timeout, or any other exception), it SHALL record an explicit failure outcome on the shared Event before releasing it. Waiter coroutines that wake from that Event SHALL read the recorded outcome and raise the leader's error rather than inferring crew health from registry status.

#### Scenario: Leader restart fails — memory gate
- **WHEN** `_ensure_crew_running` is called for a stopped crew AND the memory gate blocks the restart
- **THEN** the leader sets a failure outcome on the Event AND waiters that were blocked on the same crew raise the same error (not proceed with a stale "running" status)

#### Scenario: Leader restart fails — gateway timeout
- **WHEN** `_ensure_crew_running` is called AND the restarted container's gateway does not become ready within the timeout
- **THEN** the leader records the failure on the Event AND waiters propagate the timeout error

#### Scenario: Leader restart succeeds — waiters proceed normally
- **WHEN** `_ensure_crew_running` completes successfully
- **THEN** the leader records success on the Event AND waiters proceed to make their API call as before
