## ADDED Requirements

### Requirement: Nuke dry-run reports scheduled jobs
The `nuke` dry-run response (called without `confirm=True`) SHALL include the count and names of all scheduled jobs registered for the crew in the transport registry, so the operator can see what recurring work will be discarded before confirming teardown.

#### Scenario: Crew has scheduled jobs
- **WHEN** `nuke` is called for a crew that has one or more entries in its transport registry `schedules` list, without `confirm=True`
- **THEN** the response includes `scheduled_jobs: <count>` (integer) and `scheduled_job_names: [<name>, ...]` (list of job name strings) alongside the existing `active_tasks` and `volumes` fields

#### Scenario: Crew has no scheduled jobs
- **WHEN** `nuke` is called for a crew that has no entries in its transport registry `schedules` list, without `confirm=True`
- **THEN** the response includes `scheduled_jobs: 0` and `scheduled_job_names: []`

### Requirement: Confirmed nuke clears scheduled jobs before container teardown
When `nuke(confirm=True)` is called, the system SHALL attempt to cancel all scheduled jobs from the transport registry by issuing a `DELETE /api/crons/<job_id>` request to the gateway for each job before tearing down the container or removing the registry entry. If the gateway is unreachable, individual cancellation failures SHALL be logged at `WARNING` level and SHALL NOT prevent the nuke from proceeding. The crew registry entry (including all schedule entries) SHALL be removed after teardown regardless of individual cancellation outcomes.

#### Scenario: Confirmed nuke with running container and active schedules
- **WHEN** `nuke(confirm=True)` is called for a crew that is running and has two scheduled jobs in the transport registry
- **THEN** the system issues `DELETE /api/crons/<job_id>` for each job to the gateway, then stops and removes the container, removes both volumes, and removes the crew registry entry (including all schedule entries)

#### Scenario: Confirmed nuke with stopped container and active schedules
- **WHEN** `nuke(confirm=True)` is called for a crew whose container is stopped and that has scheduled jobs in the transport registry
- **THEN** the gateway cancellation is best-effort (errors are logged at WARNING level), the container removal and registry deletion proceed regardless, and the registry entry (including all schedule entries) is removed

#### Scenario: Confirmed nuke cancellation failure does not block teardown
- **WHEN** `nuke(confirm=True)` is called and the `DELETE /api/crons/<job_id>` request fails for one or more jobs due to a gateway error
- **THEN** the failure is logged at `WARNING` level and `nuke` continues to tear down the container, remove volumes, and remove the registry entry

#### Scenario: Confirmed nuke with no scheduled jobs
- **WHEN** `nuke(confirm=True)` is called for a crew that has no entries in its transport registry `schedules` list
- **THEN** no cron cancellation requests are issued and the teardown proceeds as before
