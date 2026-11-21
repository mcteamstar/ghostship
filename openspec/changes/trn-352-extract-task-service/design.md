## Context

TRN-351 provides operation-specific gateway outcomes. Task operations currently span MCP tools, lifecycle pickup helpers, timestamps and batch registry data.

## Decisions

- Introduce an injected TaskService with dispatch, batch dispatch, pickup and steer entry points. Use CrewGatewayClient for wire calls and CrewLauncher for wake/admission where callers already require it. Keep persistence in the existing registry. Construct one TaskService per Transport process and inject that same instance into adapters and any transitional wrappers. Move the shared bounded timestamp store and its lock into that instance. Preserve expiry for completed entries and use the same store for single and batch pickup.
- Preserve slot resolution, backend and model handling, partial batch members, lost member reporting, pickup timeouts and Admiral-mail wakeups. Keep result translation and tool registration in the MCP adapter.
- Use narrow typed values for service results where useful, without duplicating the persisted task or batch records. Keep Captain, schedules, credentials, and file transfer outside this extraction.

## Risks

Parallel admission and polling can expose ordering regressions even if tool schemas stay stable. Assert task IDs, side effects and registry state across sequences.
