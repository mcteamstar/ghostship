## MODIFIED Requirements

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

Each agent enrolled at launch SHALL carry a `memory_store` config key set to
`"default"`. Under KiroCrew 0.9.0+, `"default"` SHALL remain a valid store
identifier — the store internally switches to vector-similarity retrieval, but
the string `"default"` is still accepted without modification. Ghostship SHALL
NOT be required to add any additional memory-related config key (embedding
model, ranking mode, or re-embedding flag) to the agent enrollment payload; the
gateway owns those defaults entirely.

#### Scenario: Agents are enrolled at fresh crew launch

- **WHEN** a crew is launched
- **THEN** the transport calls `POST /api/members/{slug}/thread` for each
  deployed agent after the gateway is ready
- **THEN** `enrolled_agents` is persisted in the crew registry

#### Scenario: Enrollment survives crew restart

- **WHEN** a stopped crew is restarted
- **THEN** the transport re-enrolls all agents before declaring the crew ready
- **THEN** `enrolled_agents` is updated in the crew registry

#### Scenario: memory_store "default" accepted under KiroCrew 0.9.0

- **WHEN** a crew is launched against a KiroCrew 0.9.0+ base image
- **THEN** the agent enrollment payload containing `"memory_store": "default"` is accepted by the gateway without a validation error
- **THEN** the enrolled agent has a working memory store using vector-similarity retrieval

#### Scenario: No extra memory config key required at enrollment

- **WHEN** a crew is launched against a KiroCrew 0.9.0+ base image
- **THEN** the enrollment payload contains no embedding-model, ranking-mode, or re-embedding config key beyond `"memory_store": "default"`
- **THEN** the crew launches and agents enroll successfully without those keys
