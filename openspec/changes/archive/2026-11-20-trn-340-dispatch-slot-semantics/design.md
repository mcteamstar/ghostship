# Design

## Context

The dispatch contract is enrollment-based: `slot=None` routes enrolled agents to their pre-created member DM sessions and leaves unenrolled agents headless. `slot=False` forces headless dispatch. The current resolver logs a warning for `slot=True` and treats it as `None`; it does not create a per-task slot. The MCP tool parameter is boolean-or-null, so string-valued slots are outside its input contract.

## Goals / Non-Goals

**Goals:**
- Make the specification and operator guidance state the supported slot contract accurately.
- Preserve guidance about member-session process and memory costs.
- Describe legacy values without changing their existing runtime handling.

**Non-Goals:**
- Change enrollment, session creation, dispatch routing, or runtime input validation.
- Add bridge, per-task, or arbitrary named slot modes.

## Decisions

- Use enrollment, not `dashboard_port`, to resolve `slot=None`.
- Keep `slot=False` as the supported explicit opt-out.
- Reject `slot=True` as a distinct routing mode while documenting the existing warning and fallback to `slot=None`.
- Document string-valued slots as invalid tool inputs; do not add runtime handling for them.
- Resolve the slot once per batch; every task in the batch shares the resolved member slot or is headless.
- Keep dashboard visibility and resource costs documented separately from slot resolution.

## Risks / Trade-offs

- Calling `slot=True` “rejected” could be read as a failed dispatch. State that it is rejected as a per-task slot mode and currently falls back to the default with a warning.
- The tool annotation permits booleans, including `True`; do not imply that the schema rejects `True` itself.
- Stale main-spec text may remain until the updated delta is synced during the normal lifecycle.
