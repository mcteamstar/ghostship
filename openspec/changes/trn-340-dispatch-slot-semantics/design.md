# Design

## Context

See proposal.md. Current dispatch resolves the default using persona enrollment: enrolled agents use pre-created member DM sessions; unenrolled agents are headless. slot=False forces headless. Arbitrary slot names and slot=True are no longer accepted.

## Goals / Non-Goals

**Goals:**
- Make the specification and operator guidance state the same slot contract exposed by the tool.
- Preserve guidance about member-session process and memory costs.

**Non-Goals:**
- Change enrollment, session creation, or dispatch routing behavior.
- Reintroduce bridge or arbitrary named slots.

## Decisions

- Replace the full Task dispatch requirement because obsolete defaults and scenarios are embedded in it.
- Treat enrollment, not dashboard_port, as the basis for slot=None.
- Retain slot=False as the supported explicit opt-out, and describe True and strings as rejected values.
- Keep dashboard visibility and resource costs documented separately from slot resolution.

## Risks / Trade-offs

- [A stale MCP tool description still promises old values] → Cross-check generated tool descriptions and docs as part of the task.
- [Headless guidance is interpreted as default for enrolled personas] → State enrolled and unenrolled outcomes separately and test both.
