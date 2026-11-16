# Spec Delta

## ADDED Requirements

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
