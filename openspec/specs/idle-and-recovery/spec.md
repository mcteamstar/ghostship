# Idle and Recovery Specification

## Purpose

Free host resources by stopping idle crew containers automatically, restart them transparently on next use, and recover the crew registry after a transport restart or full machine reboot — without the caller needing to manage container lifecycle manually.

## Requirements

### Requirement: Idle container stop
The system SHALL stop a crew's container after it has had no active dispatched tasks, no running cron execution, and no cron execution since its last activity for `GA_IDLE_TIMEOUT_SECS`, and SHALL NOT stop a crew that has active work regardless of elapsed idle time. A crew that has just completed setup SHALL have its activity timestamp initialized at setup completion, so the timeout is measured from that point rather than from a missing or zero timestamp. Any enabled cron job — regardless of whether it has fired yet — SHALL by itself count as active work and prevent an idle stop, since an enabled schedule is a standing commitment to run that a fire-history check alone cannot see before its first firing.

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

### Requirement: Transparent restart on next use
The system SHALL detect a stopped crew container on the next `dispatch`, `pickup`, `steer`, `evac`, `deliver`, or `schedule` call, or on the next file GET/PUT request against the `/files/` endpoints (which is what actually moves bytes for `evac`/`deliver`), restart it, wait for its gateway, and refresh its session cookie before forwarding the request or returning a presigned URL. Because the required configuration patch is applied through `container_exec`, the restart path SHALL start the stopped container provisionally, apply the patch while that container is running, stop it, start it again, and wait for the gateway exactly once after the final start. The patch SHALL create its destination directory when it is absent, and the path SHALL NOT wait for the gateway after the provisional start.

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
