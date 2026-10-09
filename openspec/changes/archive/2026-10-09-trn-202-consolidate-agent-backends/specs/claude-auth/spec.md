# Spec Delta

## MODIFIED Requirements

### Requirement: Claude backend is opt-in

The Claude backend SHALL be available only when `claude` is an enabled backend, as defined by the `agent-backends` capability (`GA_AGENT_BACKENDS`). Kiro remains the default. Claude login SHALL be available whenever claude is enabled, including when it is not the default backend. When claude is not enabled, `POST /login/claude` SHALL return HTTP 400 naming `GA_AGENT_BACKENDS`, and the transport SHALL refuse to start with claude as the default backend.

#### Scenario: Login refused when the image lacks the Claude CLI
- **WHEN** claude is not an enabled backend and `POST /login/claude` is called
- **THEN** the transport returns HTTP 400 with a message naming `GA_AGENT_BACKENDS`, and no login container is created

#### Scenario: Launch refused when the image lacks the Claude CLI
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and claude is not an enabled backend
- **THEN** the transport raises a `ConfigError` at startup naming both settings, so no launch or Claude login flow can start

#### Scenario: Kiro is the default backend
- **WHEN** `GA_CREW_ACP_BACKEND` is unset
- **THEN** crews launch on kiro and no Claude login or opt-in check applies to them

#### Scenario: Claude login available while kiro is the default
- **WHEN** claude is an enabled backend, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/claude` is called
- **THEN** the Claude login flow starts
