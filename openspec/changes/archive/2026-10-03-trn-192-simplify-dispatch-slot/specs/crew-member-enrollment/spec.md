## MODIFIED Requirements

### Requirement: Member-based dispatch for enrolled agents

Enrolled persona agents dispatched via the `dispatch()` MCP tool SHALL be
routed into their member DM slot (`parent_session="dashboard:member-{slug}"`)
rather than a generic chat slot. This gives the agent an attested session
identity. The slot returned to the caller SHALL echo the clean agent name (e.g.
`"ghost"`, not `"member-ghost"`). Crews without `enrolled_agents` SHALL route
unenrolled agents to headless dispatch (no `parent_session`). The `slot`
parameter on `dispatch` SHALL accept only `None` (the default) or `False`;
string slot names and `True` (UUID auto-generation) are no longer accepted
values.

#### Scenario: Enrolled agent dispatch uses member slot

- **WHEN** `dispatch(agent="ghost", crew_id=...)` is called on a crew with
  `enrolled_agents` containing `"ghost"` and `slot` is omitted
- **THEN** the spawned task uses `parent_session="dashboard:member-ghost"`
- **THEN** the returned slot echoes `"ghost"`

#### Scenario: Unenrolled agent falls back to bridge/headless

- **WHEN** `dispatch(agent="custom", crew_id=...)` is called on a crew whose
  `enrolled_agents` does not contain `"custom"` and `slot` is omitted
- **THEN** the task is dispatched headless with no `parent_session`
- **THEN** the returned slot is `null`

#### Scenario: Explicit headless overrides member slot

- **WHEN** `dispatch(agent="ghost", slot=False, crew_id=...)` is called on a
  crew with `enrolled_agents` containing `"ghost"`
- **THEN** the task is dispatched headless with no `parent_session`
- **THEN** the returned slot is `null`

## REMOVED Requirements

### Requirement: UUID slot auto-generation

**Reason**: UUID slots are not attested for enrolled agents, cost the same
memory as member slots (~300 MB), and offer no advantage. The member slot
already provides per-agent session isolation and dashboard visibility.

**Migration**: Use the default `slot` omission (or `slot=None`) to route
enrolled agents to their member DM slot. For headless dispatch, use
`slot=False`. There is no equivalent for UUID auto-generated slots — callers
relying on `slot=True` to get per-task isolated sessions should instead dispatch
into the member slot, which provides isolation at the agent level.

### Requirement: Named and bridge slot routing

**Reason**: Arbitrary string slots (`slot="bridge"`, `slot="myname"`) are not
attested, breaking downstream spawn calls for enrolled agents. Member slots now
cover all legitimate use cases for slotted dispatch.

**Migration**: Replace `slot="bridge"` or any named string slot with the default
(omit `slot`), which routes enrolled agents to their member DM slot. For
unenrolled agents or cases where no session is desired, use `slot=False`.
