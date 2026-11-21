## ADDED Requirements

### Requirement: Captain recovers from a confirmed Raven session restore failure

Captain SHALL retire the failed Raven task reference and attempt one fresh check-in of the same enabled standing order when continuation reports a confirmed session restore failure.

#### Scenario: Continuation fails after acceptance
- **WHEN** the gateway accepts a continuation and its recorded Raven task later finishes with a confirmed session restore failure
- **THEN** the next eligible check-in retires that task reference and attempts one fresh Raven check-in instead of continuing the failed task

#### Scenario: Continuation immediately reports a restore failure
- **WHEN** the continuation request explicitly reports a confirmed session restore failure
- **THEN** Captain retires the failed task reference and attempts one fresh Raven check-in

#### Scenario: Fresh Raven encounters previously accepted work
- **WHEN** Raven starts after session recovery
- **THEN** it reconciles the standing order, durable progress, mailbox and gateway task list before dispatching more work
- **AND** it does not dispatch a duplicate for an already accepted work item or retry an intent whose outcome is uncertain

#### Scenario: Gateway failure is ambiguous
- **WHEN** the gateway is busy, task status is unavailable, or the error does not confirm a session restore failure
- **THEN** Captain retains its existing handling and does not trigger a fresh check-in under this recovery rule

#### Scenario: Recovery dispatch is deferred
- **WHEN** normal admission controls defer the fresh check-in
- **THEN** Captain leaves the failed reference retired and retries through the enabled schedule
