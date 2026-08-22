# Agent Personas — Delta Spec (srv-68-raven-decouple)

## Modified Requirement: Raven is a sixth, coordination-only persona

Replace the existing requirement body with:

The system SHALL define Raven as a lean, general-purpose watcher and messenger persona. Raven's prompt SHALL describe only generic crew-watching and mail behaviour: reading all mailboxes (including Admiral), writing mail to any address, watching crew task state, dispatching named personas via the crew gateway REST API, and using the `kirocrew` CLI for routine ops. Raven's prompt SHALL NOT embed Captain-loop-specific behaviour (self-cancellation, standing-order ownership, OpenSpec store resolution, or cron job management).

Captain-loop-specific behaviour — reading `/var/mail/captain`, self-cancelling when standing orders are met, the order-change contract, sanctioned persona list for dispatch, and OpenSpec store resolution — SHALL be injected by the Captain standing-order template at job creation time, not baked into the persona definition.

Raven's prompt SHALL retain guidance on the four operations that require direct gateway REST API calls (dispatch a named persona, get per-task detail, steer a running task, continue a finished task) and how to authenticate those calls.

#### Scenario: Raven dispatched directly reads all mailboxes
- **WHEN** an Admiral dispatches Raven directly (not via Captain) to read or relay mail
- **THEN** Raven reads `/var/mail/admiral` and all persona mailboxes as a core capability, without requiring any standing order to enable this behaviour

#### Scenario: Captain-loop Raven receives its loop behaviour via the standing order
- **WHEN** `captain(action="order")` creates or updates a standing-orders check-in
- **THEN** the resolved standing order message injected into the Raven dispatch contains: read `/var/mail/captain`, self-cancel when done, the order-change contract, and sanctioned persona list — none of which come from `raven.json` itself

#### Scenario: Directly dispatched Raven has an isolated session
- **WHEN** Raven is dispatched via `dispatch(agent="raven", ...)`
- **THEN** Raven runs in a dedicated KiroCrew session with no shared memory from Captain-loop check-ins, which run under the shared background session

#### Scenario: Raven's lean prompt still covers gateway auth
- **WHEN** Raven needs to dispatch a named persona, steer a task, or continue a finished task
- **THEN** Raven's base prompt provides guidance on using the gateway REST API with `.local_secret` authentication, since this is generic dispatch capability not Captain-loop-specific
