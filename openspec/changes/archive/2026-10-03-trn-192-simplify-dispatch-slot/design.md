## Context

See `proposal.md — Why` for motivation. The relevant implementation state:

`_resolve_dispatch_slot(agent, slot, crew)` in `transport/lifecycle.py` currently
handles four slot modes:

| Input | Behavior |
|:------|:---------|
| `slot=None`, agent enrolled | → member slot + `parent_session="dashboard:member-<slug>"` |
| `slot=None`, agent not enrolled, dashboard active | → `"bridge"` + `parent_session="dashboard:bridge"` |
| `slot=None`, agent not enrolled, no dashboard | → `(None, None)` headless |
| `slot=True` | → UUID hex slug, `parent_session="dashboard:<uuid>"` (not attested) |
| `slot="<string>"` | → named slot, `parent_session="dashboard:<name>"` (not attested) |

The `dispatch()` MCP tool in `transport/server.py` and `_dispatch_batch` in
`transport/lifecycle.py` both call this helper. The single-task path has a
`slot_pre_create` block that POSTs to `/api/chat/slots` for `slot is True` and
`isinstance(slot, str)` cases. The batch path has per-task UUID generation inside
the task loop (`slot=True` calls `_resolve_dispatch_slot` a second time per
task to generate a fresh UUID) and emits a `task_slots` map in the response.

## Goals / Non-Goals

**Goals:**
- Remove `slot is True` and `isinstance(slot, str)` branches from
  `_resolve_dispatch_slot`
- Route unenrolled agents to headless (not bridge) when `slot` is omitted
- Change `slot` type annotation to `bool | None` across `dispatch()` and
  `_dispatch_batch`
- Remove `slot_pre_create` calls that were only needed for named/UUID slots
- Remove per-task UUID generation and `task_slots` from `_dispatch_batch`
- Update docstrings and documentation to reflect two-mode slot semantics

**Non-Goals:**
- Changing the member slot name format (`member-{slug}`) or enrollment mechanics
- Modifying how the gateway creates or looks up member DM sessions
- Removing the bridge session from the gateway itself — the slot routing in the
  transport stops using it, but the gateway slot still exists

## Decisions

### Remove bridge fallback for unenrolled agents

**Decision:** When `slot=None` and the agent is not enrolled, route headless
(`(None, None)`) unconditionally — drop the `crew.get("dashboard_port")` check
that currently routes unenrolled agents to `"bridge"`.

**Rationale:** Bridge sessions are not attested. Since TRN-186/187 all
expected personas are enrolled by default. An unenrolled agent is either a
custom/third-party agent or a misconfigured one; neither benefits from an
unattested bridge slot, and headless dispatch is safer and cheaper.

**Alternative considered:** Keep bridge as fallback for unenrolled agents, but
mark it deprecated and emit a warning. Rejected — bridge is not attested and
the warning would be invisible to callers. A clean removal is clearer.

### `slot=False` for explicit headless

**Decision:** Accept `False` as the explicit-headless signal instead of `None`.
`None` (default) means "let the system decide" (member slot if enrolled,
headless if not). `False` means "headless unconditionally, regardless of
enrollment."

**Rationale:** Using `None` for both default and explicit-headless collapses a
meaningful distinction. `False` is a clear opt-out signal.

**Type annotation:** `slot: bool | None`. `True` is no longer a valid value;
passing `True` at runtime should be treated identically to `None` (the old
default path) or rejected with a warning — the tasks.md approach of removing
the branch handles this cleanly since `True` will route through the `slot=None`
enrolled path.

### Remove `slot_pre_create` calls

**Decision:** Delete the `POST /api/chat/slots` calls in `dispatch()` and
`_dispatch_batch` that pre-created named and UUID slots.

**Rationale:** Member DM slots are pre-created at enrollment time by
`_enroll_crew_members`. They do not need pre-creation at dispatch time. Headless
dispatch creates no session at all. There is no remaining code path that
introduces a novel slot name requiring pre-creation.

### Remove `task_slots` from batch response

**Decision:** Drop the `task_slots: dict[str, str]` from `_dispatch_batch` and
from the `dispatch` tool docstring.

**Rationale:** `task_slots` only carried value when `slot=True` generated
distinct per-task UUID names that the caller needed to reference. With UUID slots
gone, no per-task slot names are generated. All batch tasks route to the same
member slot (or all headless); the single `slot` field in the response is
sufficient.

## Risks / Trade-offs

**Breaking change for callers using `slot=True` or named slots:** Any caller
that passes `slot=True`, `slot="bridge"`, or `slot="<name>"` will see different
behavior after this change (UUID/named slot routing is gone). In practice these
are transport-internal patterns; the public-facing crew orchestration layer never
exposed named slot routing as a stable API. The tasks include a README and skill
doc update to communicate the change.
→ Mitigation: Migration notes in the specs REMOVED blocks; README and skill doc
updates in tasks 4.1 and 4.2.

**`True` passed as `slot` still accepted by Python type system:** Removing the
`slot is True` branch means a caller passing `slot=True` at runtime silently
falls through to the enrolled-agent path rather than erroring. This is acceptable
because `True` is an invalid input under the new type annotation.
→ Mitigation: Update the type annotation to `bool | None` and document in the
docstring that `True` is not a valid value. A stricter guard (explicit `if slot
is True: raise ValueError`) can be added but is not required for correctness.

## Migration Plan

1. Land the code changes in `transport/lifecycle.py` and `transport/server.py`
   (tasks 1 and 2).
2. Update tests to remove UUID/named/bridge coverage (task 3).
3. Update README and skill doc (task 4).
4. Deploy to academy and verify the two attested paths smoke-test clean (task 5).

No database migration. No rollback complexity — `_resolve_dispatch_slot` is
purely in-memory routing logic. A rollback is a revert of the changed files.
