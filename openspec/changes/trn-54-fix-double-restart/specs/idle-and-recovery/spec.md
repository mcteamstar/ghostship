## MODIFIED Requirements

### Requirement: Transparent restart on next use
The system SHALL detect a stopped crew container on the next `dispatch`, `pickup`, `steer`, `evac`, `deliver`, or `schedule` call, or on the next file GET/PUT request against the `/files/` endpoints (which is what actually moves bytes for `evac`/`deliver`), restart it, wait for its gateway, and refresh its session cookie before forwarding the request or returning a presigned URL. The system SHALL apply any required crew configuration patches **before** starting the container, so the gateway boots with the correct configuration already in place and only a single start/wait cycle is required. The restart path SHALL NOT stop and restart the container a second time after the initial start.

#### Scenario: First caller after idle-stop
- **WHEN** any of those tools or file requests is made for a crew whose container is stopped
- **THEN** the system applies configuration patches, starts the container once, waits for the gateway to become reachable, mints a new session cookie, updates the registry, and then forwards the original request

#### Scenario: Concurrent callers during restart
- **WHEN** a second call for the same crew arrives while a restart triggered by an earlier call is still in progress
- **THEN** the second caller waits for the in-progress restart to finish and then uses the refreshed crew record, rather than triggering a second concurrent restart

#### Scenario: deliver() returns a URL after restarting the crew
- **WHEN** the `deliver` tool is called for a crew whose container is currently stopped
- **THEN** the tool call itself restarts the container and waits for the gateway before signing and returning the upload URL, and the later file POST retains its own recovery check

#### Scenario: Single start/wait cycle on wake
- **WHEN** a stopped crew container is woken by any tool call
- **THEN** the container is started exactly once and the gateway wait is performed exactly once before the crew is considered ready
