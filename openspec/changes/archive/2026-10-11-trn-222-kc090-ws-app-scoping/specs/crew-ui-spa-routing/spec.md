## ADDED Requirements

### Requirement: Portal reads message content from REST, not WebSocket payload bodies
The ghostship portal SHALL read message content (assistant text, tool-call
titles, tool output) exclusively from the REST API
(`GET /api/sessions/{id}/messages`). The portal MAY consume WebSocket messages
only for session-state change notifications (turn started, turn ended,
new-message signal). The portal SHALL NOT depend on `assistant_content`,
`tool_title`, or any other non-user content field being present in WebSocket
broadcast payloads. This separation ensures that upstream WS broadcast
redaction of non-user content is invisible to the portal.

#### Scenario: Full message content rendered despite WS broadcast redaction
- **WHEN** the upstream crew gateway strips `assistant_content` and `tool_title` from WS broadcast payloads (as in KiroCrew 0.9.0+)
- **THEN** the portal still renders complete assistant text and tool-call content, sourced from `GET /api/sessions/{id}/messages` via REST

#### Scenario: WS messages used only for lifecycle notifications
- **WHEN** a crew session is active and the upstream gateway emits WS session-state events (turn started, turn ended, new message)
- **THEN** the portal updates its live-session state indicators based on those WS signals

#### Scenario: Portal does not break when WS payload drops assistant_content
- **WHEN** a WS broadcast payload for a completed turn contains no `assistant_content` field
- **THEN** the portal produces no console error referencing `assistant_content` and displays the turn's content fetched from REST

#### Scenario: Portal does not break when WS payload drops tool_title
- **WHEN** a WS broadcast payload for a tool-call event contains no `tool_title` field
- **THEN** the portal produces no console error referencing `tool_title` and displays the tool-call title fetched from REST
