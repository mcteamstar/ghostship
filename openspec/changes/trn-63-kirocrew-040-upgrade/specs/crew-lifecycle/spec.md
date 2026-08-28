## MODIFIED Requirements

### Requirement: Crew session creation
A crew session SHALL be created by calling `POST /api/chat/slots` with `mode="crew"` and a non-empty `agent` field that names a valid agent template. A creation request with an absent or empty `agent` field SHALL be rejected with a 4xx error. The agent template SHALL exist in the agents registry before the creation request is made; if the named template is absent the call SHALL fail with a clear error.

#### Scenario: Crew created with valid agent template
- **WHEN** `POST /api/chat/slots` is called with `mode="crew"` and a non-empty `agent` value that names a registered template
- **THEN** the crew session is created successfully and returns a slot ID

#### Scenario: Crew creation rejected when agent field is absent
- **WHEN** `POST /api/chat/slots` is called with `mode="crew"` and no `agent` field (or an empty string)
- **THEN** the request is rejected with a 4xx response and no session is created

#### Scenario: Crew creation rejected when agent template does not exist
- **WHEN** `POST /api/chat/slots` is called with a non-empty `agent` value that does not match any registered template
- **THEN** the request is rejected with a 4xx response and no session is created

### Requirement: Agent template registration
A custom agent template SHALL be registered via `POST /api/agents` when the KiroCrew gateway is running. Direct filesystem writes to the agents configuration directory (`~/.kiro/agents/`) SHALL be rejected by the runtime once the gateway has started. Agent templates that must exist before the first crew creation SHALL be registered either (a) before the gateway starts by placing the JSON file in the agents directory at build/image time, or (b) at runtime via `POST /api/agents`.

#### Scenario: Agent template registered via API at runtime
- **WHEN** `POST /api/agents` is called with a valid agent template JSON while the gateway is running
- **THEN** the template becomes available for crew creation immediately

#### Scenario: Filesystem write to agents directory rejected at runtime
- **WHEN** a process attempts to write a file directly to `~/.kiro/agents/` while the KiroCrew gateway is running
- **THEN** the write is rejected with a permission error and the registry is not modified

#### Scenario: Agent template placed before gateway start
- **WHEN** an agent JSON file is placed in the agents directory before the KiroCrew gateway process starts
- **THEN** the template is available for crew creation once the gateway starts

### Requirement: Session reload in place
A running crew session SHALL support a reload-in-place operation that restarts the session without changing its slot identity. A reload SHALL pick up updated agent configuration, preserve the existing conversation history, and allow connected clients to maintain their connections. Reload-in-place SHALL be used in preference to a stop/start cycle whenever only agent config changes are being applied to a running session.

#### Scenario: Session reloads with updated agent config
- **WHEN** the reload-in-place endpoint is called on an active crew slot after the slot's agent template has been updated
- **THEN** the session restarts in place, picks up the new agent config, and the slot ID remains unchanged

#### Scenario: Connected clients survive reload
- **WHEN** a reload-in-place is triggered on a slot with active client connections
- **THEN** clients can reconnect to the same slot ID without requiring a new session negotiation

#### Scenario: Conversation history preserved across reload
- **WHEN** a reload-in-place completes on a slot that had existing conversation history
- **THEN** the conversation history is intact after the reload
