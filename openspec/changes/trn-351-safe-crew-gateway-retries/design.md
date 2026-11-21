## Context

TRN-350 establishes the gateway client. TRN-349 demonstrated that an accepted continuation can report a terminal restore failure later and that a fresh spawn can be rejected independently.

## Decisions

- Model confirmed rejection, refreshable auth refusal, busy, transport unavailable and unknown acceptance as distinct outcomes. Keep accepted IDs and terminal task status as separate values. Scrub credentials from diagnostics.
- Define policy by operation, including spawn, continue, steer, and any other mutations that use the wrapper. Retry reads within a budget. For writes, allow a retry only with operation-specific evidence of non-execution. A live probe, generic 5xx or connection reset cannot prove non-execution.
- Move Captain to typed results first. Keep an active or busy Raven ID, preserve its restore-failure behavior, and preserve recovery for explicit missing sessions, and reconcile unknown acceptance without blind respawn. Adopt a task only when the gateway can link exactly one ID to a stable identifier recorded for that attempt before submission. Persona, timestamps, or a similar prompt alone cannot establish identity. If the operation lacks a reliable correlation mechanism or roster evidence is inconclusive, retain the durable hold and expose it in Captain status for operator review. Preserve external MCP/HTTP response compatibility and include a clear diagnostic where acceptance is unknown.
- Keep cookie refresh and liveness recovery bounded and retain the launcher lock boundary established by TRN-350.

## Risks

Gateway response shapes may vary. Pin classification to supported wire evidence and test unknown or malformed responses explicitly.
