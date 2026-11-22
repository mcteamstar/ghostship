## Context

Lifecycle currently owns authenticated HTTP calls and recovery. Launcher, monitors, tools and Captain rely on that behavior, including both one-shot and recovering calls.

## Decisions

- Add one CrewGatewayClient per Transport process, constructed in lifecycle during Transport bootstrap. This is a transitional assembly point so flat container imports and callers that load lifecycle without server.py share the same instance. Moving construction into server.py would require a second initialization path for those callers. Inject the installed HTTP client, credential refresh and crew restoration callbacks. Keep redaction, URL and header construction, request formatting and gateway response decoding behind this boundary.
- Move the existing recovery policy intact. Compatibility wrappers and migrated callers must delegate to the same client and per-crew recovery lock. Keep lifecycle compatibility functions for call sites that do not migrate in this change. Retain exception and response shapes at those boundaries.
- Keep CrewLauncher responsible for container lifecycle and CrewRegistry responsible for persistence. Startup and enrollment must use the one-shot gateway path so they cannot reacquire the gateway recovery lock. Never hold the registry lock across network I/O.
- Keep the container entry point and local package imports working. No global dependency-stub cleanup beyond the tests needed to exercise the real HTTP client.

## Risks

A misplaced call can cause re-entry or change visible retry behavior. Characterize current wire and recovery behavior before moving code.
