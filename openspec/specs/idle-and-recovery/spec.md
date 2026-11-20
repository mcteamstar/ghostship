# Idle and Recovery Specification

## Purpose

Free host resources by stopping idle crew containers automatically, restart them transparently on next use, and recover the crew registry after a transport restart or full machine reboot — without the caller needing to manage container lifecycle manually.

## Requirements

### Requirement: Idle container stop

The system SHALL stop a crew only after `GA_IDLE_TIMEOUT_SECS` with no active task, cron execution, or recent activity; completed setup SHALL initialize a fresh activity timestamp, and active work SHALL prevent stopping.

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

### Requirement: Enabled schedules keep a crew alive

Any enabled gateway cron SHALL keep a crew alive, even before its first firing. An enabled Captain entry with `next_fire_at < _NEVER_FIRE_AT` SHALL also keep it alive; gateway state comes from `/api/crons`, Captain state from the transport registry.

#### Scenario: A freshly scheduled job with a long interval survives to its first firing
- **WHEN** a crew has an enabled cron job whose `every_secs` exceeds `GA_IDLE_TIMEOUT_SECS`, and that job has never yet fired
- **THEN** the idle monitor does not stop the crew, because the enabled job alone counts as active work

#### Scenario: Crew with enabled captain schedule is not idle-stopped
- **WHEN** a crew has an enabled captain schedule entry with `next_fire_at` in the near future and no active spawned tasks or gateway crons
- **THEN** the idle monitor does NOT stop the crew

#### Scenario: Crew with disabled captain schedule may be idle-stopped
- **WHEN** a crew has a captain schedule entry with `enabled: false` and no other active work
- **THEN** the idle monitor treats it as idle and may stop the crew after `GA_IDLE_TIMEOUT_SECS`

#### Scenario: Crew with captain schedule at NEVER_FIRE_AT may be idle-stopped
- **WHEN** a crew's captain schedule entry has `next_fire_at == _NEVER_FIRE_AT` (one-shot fired or manually stopped) and no other active work
- **THEN** the idle monitor treats it as idle and may stop the crew after `GA_IDLE_TIMEOUT_SECS`

#### Scenario: Enabled gateway cron still prevents idle stop
- **WHEN** a crew has an enabled gateway cron job (in `/api/crons`) and no active spawned tasks
- **THEN** the idle monitor does NOT stop the crew (existing behaviour preserved)

### Requirement: Unknown activity state fails safe

If the idle monitor cannot determine activity because of an API error, it SHALL skip that crew and leave it running for the current cycle.

#### Scenario: API error during activity check
- **WHEN** the idle monitor's request to `/api/spawn` or `/api/crons` fails with a connection error, timeout, or unexpected HTTP response
- **THEN** the idle monitor skips that crew for the current cycle and leaves it running
### Requirement: Stopped crews restart on the next request

The next dispatch, pickup, steer, evac, deliver, schedule, or file GET/PUT SHALL restart a stopped crew, wait for its gateway, and refresh its cookie before forwarding work or returning a URL.

#### Scenario: First caller after idle-stop
- **WHEN** any of those tools or file requests is made for a crew whose container is stopped
- **THEN** the system starts the container provisionally, applies configuration patches through exec, stops and starts the container again so the patch is loaded, waits for the gateway once, mints a new session cookie, updates the registry, and then forwards the original request

#### Scenario: deliver() returns a URL after restarting the crew
- **WHEN** the `deliver` tool is called for a crew whose container is currently stopped
- **THEN** the tool call itself performs the provisional start, exec patch, final restart, and single gateway wait before signing and returning the upload URL, and the later file POST retains its own recovery check

### Requirement: Restart applies required configuration before final gateway wait

The restart path SHALL start provisionally, apply the config patch (creating its directory if needed), stop and start again, then wait once for the final gateway; it SHALL NOT wait after the provisional start.

#### Scenario: Single gateway wait on wake
- **WHEN** a stopped crew container is woken through the normal stopped-container path
- **THEN** the container is started exactly twice, stopped once for the configuration bounce, and the gateway wait is performed exactly once after the final start; no gateway wait occurs between the provisional start and the exec patch

### Requirement: Concurrent restart callers share a stable outcome

A restart leader SHALL release waiters only after recording its outcome; concurrent callers SHALL receive the same generation-stable result.

#### Scenario: Concurrent callers during restart
- **WHEN** a second call for the same crew arrives while a restart triggered by an earlier call is still in progress
- **THEN** the second caller waits for the in-progress restart to finish and then uses the refreshed crew record, rather than triggering a second concurrent restart

#### Scenario: Third concurrent caller does not corrupt prior waiters' outcome reads

- **GIVEN** a crew restart is in progress (leader A, waiter B)
- **WHEN** caller C arrives after the leader fires the event but before waiter B reads the outcome, and C is elected as the new leader for a fresh restart cycle
- **THEN** B detects the generation change and raises a RuntimeError rather than reading A's outcome as if it were valid for C's cycle
- **AND** B does not proceed against a crew whose state is indeterminate

#### Scenario: Generation stable — normal two-caller restart is unaffected

- **WHEN** exactly a leader and one waiter complete a restart cycle without any third caller
- **THEN** the generation counter does not change between the waiter's capture and its post-wait read, and the waiter proceeds normally using the leader's outcome

### Requirement: Gateway cron state is reconciled after restart

Once ready, the transport SHALL read `/api/crons`, update registry state for jobs present in the gateway, and reseed only jobs absent there; the gateway is the source of truth.

#### Scenario: Paused cron in gateway syncs to registry on restart
- **WHEN** a crew container restarts and its gateway reports a cron job with `"enabled": false`
- **THEN** the transport updates the registry entry for that job to `enabled: false`, does not re-register it, and the idle monitor subsequently sees no enabled cron job for that crew

#### Scenario: Missing cron registered from registry on restart
- **WHEN** a crew container restarts and a registry schedule entry is absent from the gateway's `/api/crons` response
- **THEN** the transport registers it in the gateway (the true bootstrap case — brand new container)
### Requirement: Registry reconciliation on startup

The system SHALL reconcile the crew registry against actual Podman state on transport startup without starting stopped crew containers. It SHALL preserve their workspaces, schedules, dashboard allocations and registry records, and SHALL mark existing stopped containers stopped. It SHALL retain the existing guarded handling of containers confirmed absent and tolerate transient Podman errors without deleting records.

#### Scenario: Container no longer exists
- **WHEN** transport starts and a registered crew's container is confirmed absent from Podman
- **THEN** the system removes that crew from the registry under the existing guarded deletion rules

#### Scenario: Container exists but stopped
- **WHEN** transport starts and a registered crew's container exists but is not running
- **THEN** it remains stopped and registered without a gateway readiness wait or cookie mint

#### Scenario: Container is already running
- **WHEN** transport starts and a registered crew's container is running
- **THEN** it is reconciled without an unnecessary restart

#### Scenario: Podman state is unavailable
- **WHEN** an existence or running-state check fails transiently
- **THEN** the affected crew record is retained and the error is logged

#### Scenario: A crew wakes while reconciliation is in progress
- **WHEN** reconciliation observes a stopped crew and a concurrent operation starts it before the status write
- **THEN** the stale observation does not overwrite the newer running state

### Requirement: Due work wakes stopped crews after startup

After restart, monitors SHALL wake stopped crews only for due enabled work, preserving Ghostship schedules and Captain state. Future or disabled work SHALL NOT wake crews. Admitted starts SHALL count against memory until ready, and a failed wake SHALL leave its started container stopped; gateway-only schedules remain undiscoverable until wake and SHALL be documented.

#### Scenario: Enabled work is due
- **WHEN** an enabled schedule or Captain check-in becomes due for a stopped crew
- **THEN** the monitor attempts guarded crew recovery and processes the due work under existing scheduling semantics

#### Scenario: Work is not due
- **WHEN** a stopped crew has only future or disabled scheduled work
- **THEN** the monitor leaves the crew stopped until due work or an explicit operation requires it

#### Scenario: Several crews have due work
- **WHEN** several stopped crews have work due together
- **THEN** cross-crew admission atomically reserves capacity so simultaneous starts cannot independently consume the same available capacity, and per-crew restart coordination remains effective

#### Scenario: A start fails after reserving capacity
- **WHEN** a start fails or is cancelled after admission
- **THEN** its reservation is released and later eligible starts can proceed

#### Scenario: Gateway-only schedule on stopped crew
- **WHEN** a schedule exists only in a stopped crew gateway and is absent from the transport registry
- **THEN** it cannot trigger a wake until the crew is started for another reason, and the documented limitation applies

#### Scenario: In-flight start counts against free memory
- **WHEN** one crew has been admitted and started but its gateway is not yet ready, and a second crew requests a start while live free memory minus the in-flight estimate is below the configured floor
- **THEN** the second start waits or is refused for memory rather than being admitted on the live reading alone

#### Scenario: Memory wait does not block unrelated starts indefinitely
- **WHEN** one start is waiting for memory to recover
- **THEN** other crews' admission decisions are not held behind that wait for its full timeout

#### Scenario: Wake fails after the container started
- **WHEN** the configuration patch, gateway wait or cookie mint fails after the container was started during a wake
- **THEN** the container is stopped, its reservation is released, the registry records it stopped, and the caller receives the failure

#### Scenario: Gateway ready but cookie mint fails
- **WHEN** the gateway becomes ready during a wake but a fresh session cookie cannot be minted
- **THEN** the wake is reported as failed, the container is stopped, and waiters receive the same failure rather than a generic stopped-status error
### Requirement: Survives podman-machine / host restarts
The system SHALL keep the transport container itself restarting automatically across a full Podman restart (machine stop/start on macOS, or a `systemctl --user` restart / relogin on Linux), via `--restart=always` plus an enabled `podman-restart.service`.

#### Scenario: Podman machine or host restarts
- **WHEN** the podman machine (macOS) or the user's systemd session (Linux) restarts
- **THEN** the `ga-transport` container comes back up on its own once Podman is running again, without any manual `podman run` or `podman start`

### Requirement: Schedule monitor uses gateway enabled state

When reachable, the schedule monitor SHALL read `/api/crons` for enabled status, skip disabled jobs, and write `enabled: false` back to the registry.

#### Scenario: Gateway reports job disabled — monitor skips and writes back

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": false`
- **THEN** the monitor does not fire the job, and writes `enabled: false` to the registry entry for that job

#### Scenario: Gateway reports job enabled — monitor fires normally

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": true`
- **THEN** the monitor fires the job as normal (existing behaviour)

### Requirement: Schedule monitor falls back to registry when gateway is unreachable

For a stopped crew that cannot be woken, the monitor SHALL use registry `enabled` as a best-effort fallback; a missing gateway field SHALL default to enabled.

#### Scenario: Crew stopped, gateway unreachable — monitor falls back to registry

- **WHEN** the schedule monitor evaluates a job for a crew that cannot be woken (`_ensure_crew_running` raises or the crew was already stopped before the gateway fetch), so the gateway's `/api/crons` response is unavailable
- **THEN** the monitor falls back to the registry's `enabled` field to decide whether to skip; if the registry shows `enabled: false` the job is skipped; if the registry shows `enabled: true` (or the field is absent) the job proceeds with the existing wake-and-fire path

#### Scenario: Gateway cron payload field is absent — monitor treats job as enabled

- **WHEN** the gateway's `/api/crons` response includes a job entry but the `"enabled"` field is absent
- **THEN** the monitor treats the job as enabled and fires it (fail-open, preserving existing behaviour)
### Requirement: Eager registry self-healing for externally stopped containers

When `crews()` or `_ensure_crew_running` finds a registry entry marked running whose container is stopped, the transport SHALL write `status: "stopped"` before returning. This supplements startup reconciliation and SHALL NOT restart the container.

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

The restart leader SHALL record success or failure on the shared Event before releasing it, including failures during initial probe/setup. Waiters SHALL raise the leader's recorded error rather than infer health from registry state.

#### Scenario: Leader restart fails — memory gate
- **WHEN** `_ensure_crew_running` is called for a stopped crew AND the memory gate blocks the restart
- **THEN** the leader sets a failure outcome on the Event AND waiters that were blocked on the same crew raise the same error (not proceed with a stale "running" status)

#### Scenario: Leader restart fails — gateway timeout
- **WHEN** `_ensure_crew_running` is called AND the restarted container's gateway does not become ready within the timeout
- **THEN** the leader records the failure on the Event AND waiters propagate the timeout error

#### Scenario: Leader restart succeeds — waiters proceed normally
- **WHEN** `_ensure_crew_running` completes successfully
- **THEN** the leader records success on the Event AND waiters proceed to make their API call as before

#### Scenario: Initial container probe fails
- **WHEN** the elected restart leader's initial Podman running-state probe raises an exception
- **THEN** the leader records the failure and signals the shared Event
- **THEN** all waiters wake and receive the leader failure without waiting for the timeout

#### Scenario: Early stop before restart body fails
- **WHEN** the elected restart leader attempts to stop a running container whose gateway probe failed and `container_stop` raises
- **THEN** the leader records the failure and signals the shared Event
- **THEN** all waiters wake and receive the leader failure without waiting for the timeout
