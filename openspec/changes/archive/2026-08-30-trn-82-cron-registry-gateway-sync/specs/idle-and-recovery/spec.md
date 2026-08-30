## MODIFIED Requirements

### Requirement: Transparent container restart on next use
The system SHALL detect a stopped crew container on the next `dispatch`, `pickup`, `steer`, `evac`, `deliver`, or `schedule` call, or on the next file GET/PUT request against the `/files/` endpoints (which is what actually moves bytes for `evac`/`deliver`), restart it, wait for its gateway, and refresh its session cookie before forwarding the request or returning a presigned URL. Because the required configuration patch is applied through `container_exec`, the restart path SHALL start the stopped container provisionally, apply the patch while that container is running, stop it, start it again, and wait for the gateway exactly once after the final start. The patch SHALL create its destination directory when it is absent, and the path SHALL NOT wait for the gateway after the provisional start. After the gateway is ready, the system SHALL reconcile the crew's schedule registry with the gateway's current cron state before reseeding — reading `/api/crons` and updating the registry entry for each existing job to match the gateway's reported state (enabled/paused, interval); jobs found in the gateway are not re-registered; only jobs missing from the gateway are registered from the registry. Jobs deleted inside the container and absent from the gateway SHALL be removed from the registry. The gateway is the source of truth for schedule state; the registry is a reseed bootstrap cache only.

#### Scenario: Paused cron in gateway syncs to registry on restart
- **WHEN** a crew container restarts and its gateway reports a cron job with `"enabled": false`
- **THEN** the transport updates the registry entry for that job to `enabled: false`, does not re-register it, and the idle monitor subsequently sees no enabled cron job for that crew

#### Scenario: Deleted cron in gateway removed from registry on restart
- **WHEN** a crew container restarts and the gateway's `/api/crons` response does not include a job that exists in the transport registry
- **THEN** the transport removes that job from the registry

#### Scenario: Missing cron registered from registry on restart
- **WHEN** a crew container restarts and a registry schedule entry is absent from the gateway's `/api/crons` response
- **THEN** the transport registers it in the gateway (the true bootstrap case — brand new container)
