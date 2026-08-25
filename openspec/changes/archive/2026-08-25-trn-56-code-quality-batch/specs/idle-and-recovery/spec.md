## MODIFIED Requirements

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
