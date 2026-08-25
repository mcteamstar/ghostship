## MODIFIED Requirements

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
