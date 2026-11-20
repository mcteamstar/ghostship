# crew-member-enrollment Specification

## Purpose
Binds deployed agents to named KiroCrew member threads at launch and restart, recording enrollment so dispatch can use each agent’s attested member session.

## Requirements

### Requirement: Agent enrollment at crew launch

Before a crew is ready, the transport SHALL enroll each deployed agent through the gateway, record enrolled slugs, and repeat enrollment after restart. Enrollment SHALL be idempotent and a per-agent failure SHALL NOT prevent launch.

#### Scenario: Agents are enrolled at fresh crew launch

- **WHEN** a crew is launched
- **THEN** the transport calls `POST /api/members/{slug}/thread` for each
  deployed agent after the gateway is ready
- **THEN** `enrolled_agents` is persisted in the crew registry

#### Scenario: Enrollment survives crew restart

- **WHEN** a stopped crew is restarted
- **THEN** the transport re-enrolls all agents before declaring the crew ready
- **THEN** `enrolled_agents` is updated in the crew registry

#### Scenario: Enrollment is idempotent and non-fatal
- **WHEN** an already-enrolled agent is enrolled again, or one agent enrollment fails during launch
- **THEN** duplicate enrollment is a no-op and a per-agent failure does not prevent the crew from launching

### Requirement: Agent memory store defaults at enrollment

Each enrolled agent SHALL use `memory_store: "default"`; the gateway SHALL own vector-similarity defaults without additional memory configuration keys.

#### Scenario: memory_store "default" accepted under KiroCrew 0.9.0

- **WHEN** a crew is launched against a KiroCrew 0.9.0+ base image
- **THEN** the agent enrollment payload containing `"memory_store": "default"` is accepted by the gateway without a validation error
- **THEN** the enrolled agent has a working memory store using vector-similarity retrieval

#### Scenario: No extra memory config key required at enrollment

- **WHEN** a crew is launched against a KiroCrew 0.9.0+ base image
- **THEN** the enrollment payload contains no embedding-model, ranking-mode, or re-embedding config key beyond `"memory_store": "default"`
- **THEN** the crew launches and agents enroll successfully without those keys
### Requirement: Member-based dispatch for enrolled agents

Dispatch SHALL route enrolled agents to `dashboard:member-{slug}` and echo the clean name; unenrolled agents and explicit `slot=False` SHALL dispatch headless with no `parent_session` and a null slot. `slot` SHALL accept only `None` or `False`.

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

#### Scenario: Only supported slot values are accepted
- **WHEN** `dispatch` receives a `slot` value other than `None` or `False`
- **THEN** the request is rejected as an invalid slot value
