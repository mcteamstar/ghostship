# crew-lifecycle/idle-and-wake Specification

## Purpose

Defines crew idling, wake-up and safe handling of concurrent activity.

## Requirements

### Requirement: Idle monitor releases registry lock before container_stop
The idle monitor SHALL release `_registry_lock` before calling `container_stop` on a crew container. An in-flight state flag SHALL be set inside the lock before releasing it to prevent a concurrent idle monitor tick from issuing a second `container_stop` on the same container. The lock SHALL be re-acquired for the subsequent registry write-back after `container_stop` returns.

#### Scenario: Registry lock is not held during container_stop
- **WHEN** the idle monitor stops a crew container
- **THEN** `_registry_lock` is released before the blocking `container_stop` call, so concurrent registry reads and writes (launch, dispatch, schedule monitor) can proceed during the stop

#### Scenario: Double-stop is prevented by in-flight flag
- **WHEN** two idle monitor ticks overlap and both identify the same crew as idle
- **THEN** only one issues `container_stop`; the second detects the in-flight flag and skips

### Requirement: Idle stop and crew wake are serialized
The transport SHALL coordinate an idle monitor's container stop with any concurrent operation that wakes or restarts the same crew. A wake SHALL NOT report success while an idle stop can still stop that crew afterward. If an idle stop has already begun, the wake SHALL wait for that stop to finish and then ensure the crew is running before returning.

#### Scenario: Wake starts after idle stop is claimed
- **WHEN** the idle monitor has claimed an idle crew for stopping and a dispatch concurrently requires that crew
- **THEN** the dispatch does not report the crew running before the stop completes
- **THEN** the dispatch ensures the container is running after the stop and the final registry status is `running`

#### Scenario: Crew activity advances before idle stop is claimed
- **WHEN** a crew is touched by a wake or dispatch before the idle monitor claims its stop
- **THEN** the idle monitor observes the activity and skips stopping the crew
- **THEN** the crew remains running

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
