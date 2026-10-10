# Crew member enrollment

## ADDED Requirements

### Requirement: Agent enrollment at crew launch

Every agent deployed into a crew at launch time SHALL be enrolled as a named
KiroCrew crew member before the crew is declared ready. Enrollment is performed
by calling the gateway's `POST /api/members/{slug}/thread` endpoint for each
deployed agent's slug after the gateway is ready and agent files are deployed.
Enrollment is idempotent — re-enrolling an already-enrolled agent is a no-op.
Enrollment failures for individual agents are non-fatal: the crew still
launches; unenrolled agents operate without attestation. The set of enrolled
agent slugs SHALL be stored in the crew registry and consulted at dispatch time.
On crew restart or recovery, enrollment SHALL be re-run to ensure bindings
survive gateway restarts.

#### Scenario: Agents are enrolled at fresh crew launch

- **WHEN** a crew is launched
- **THEN** the transport calls `POST /api/members/{slug}/thread` for each
  deployed agent after the gateway is ready
- **THEN** `enrolled_agents` is persisted in the crew registry

#### Scenario: Enrollment survives crew restart

- **WHEN** a stopped crew is restarted
- **THEN** the transport re-enrolls all agents before declaring the crew ready
- **THEN** `enrolled_agents` is updated in the crew registry

### Requirement: Member-based dispatch for enrolled agents

Enrolled persona agents dispatched via the `dispatch()` MCP tool SHALL be
routed into their member DM slot (`parent_session="dashboard:member-{slug}"`)
rather than a generic chat slot. This gives the agent an attested session
identity. The slot returned to the caller SHALL echo the clean agent name (e.g.
`"ghost"`, not `"member-ghost"`). Crews without `enrolled_agents` SHALL fall
back to the previous bridge/headless behaviour.

#### Scenario: Enrolled agent dispatch uses member slot

- **WHEN** `dispatch(agent="ghost", crew_id=...)` is called on a crew with
  `enrolled_agents` containing `"ghost"`
- **THEN** the spawned task uses `parent_session="dashboard:member-ghost"`
- **THEN** the returned slot echoes `"ghost"`

#### Scenario: Unenrolled agent falls back to bridge/headless

- **WHEN** `dispatch(agent="custom", crew_id=...)` is called on a crew whose
  `enrolled_agents` does not contain `"custom"`
- **THEN** the task routes to the bridge slot (if dashboard crew) or headless
