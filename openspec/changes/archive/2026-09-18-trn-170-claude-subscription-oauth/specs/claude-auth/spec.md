## Purpose

Defines the Claude Code OAuth device-code login flow, credential storage, injection into crew containers, and logout — a parallel auth state machine to the existing kiro-cli auth path, enabling Claude Pro/Max subscription users to run Claude-backend crews without an Anthropic API key.

## ADDED Requirements

### Requirement: Claude auth state machine

The Ghost Academy has a Claude auth state machine with exactly three states — unauthenticated, pending, and authenticated — determined by the presence and content of `DATA_DIR/ga-claude-auth`. Transitions are: unauthenticated → pending via `POST /login/claude`; pending → authenticated via `GET /login/claude` completing; authenticated → unauthenticated via `POST /logout/claude`. No other transitions are valid. This state machine is independent of the kiro auth state machine.

#### Scenario: POST /login/claude starts device flow when unauthenticated
- **WHEN** `POST /login/claude` is called and `ga-claude-auth` does not exist or is empty
- **THEN** the transport starts a Claude Code OAuth device-code flow, returns HTTP 200 with `{"login_url": "<url>", "code": "<code>"}`, and stores the pending flow state

#### Scenario: POST /login/claude returns 409 when already authenticated
- **WHEN** `POST /login/claude` is called and `ga-claude-auth` exists and is non-empty
- **THEN** the transport returns HTTP 409 with a message indicating Claude auth is already present and `POST /logout/claude` must be called first

#### Scenario: POST /login/claude returns 409 when flow already in progress
- **WHEN** `POST /login/claude` is called while a Claude login flow is already pending
- **THEN** the transport returns HTTP 409 indicating a flow is in progress and `GET /login/claude` should be polled

#### Scenario: GET /login/claude returns pending while user has not approved
- **WHEN** `GET /login/claude` is polled and the user has not yet approved the device
- **THEN** the transport returns HTTP 200 with `{"status": "pending", "login_url": "<url>"}`

#### Scenario: GET /login/claude completes and writes ga-claude-auth
- **WHEN** `GET /login/claude` is polled and the Claude Code OAuth grant has completed inside the login container
- **THEN** the transport writes the Claude credential data to `DATA_DIR/ga-claude-auth` (mode 0600), cleans up the login container, and returns HTTP 200 with `{"status": "complete"}`

#### Scenario: GET /login/claude returns 404 when no flow is pending
- **WHEN** `GET /login/claude` is polled and no login flow is in progress
- **THEN** the transport returns HTTP 404

#### Scenario: POST /logout/claude clears credential and wipes running crews
- **WHEN** `POST /logout/claude` is called and `ga-claude-auth` exists
- **THEN** `ga-claude-auth` is deleted and the transport removes the Claude credential from every running Claude-backend crew's container without restarting those crews

#### Scenario: POST /logout/claude returns 409 when not authenticated
- **WHEN** `POST /logout/claude` is called and `ga-claude-auth` does not exist
- **THEN** the transport returns HTTP 409 indicating there is no Claude auth to clear

### Requirement: Claude login uses PTY to handle interactive prompts

The `claude auth login` command may present interactive prompts (consent confirmation, URL display) in a terminal context. The transport SHALL run it via a PTY exec (same `container_exec_pty_stdin` mechanism used for kiro-cli login), reading output and answering any prompts automatically, then extracting the device verification URL from the output stream.

#### Scenario: Login URL extracted from PTY output
- **WHEN** `claude auth login` is run via PTY inside the login container and outputs a device verification URL
- **THEN** the transport captures the URL from the PTY output stream and returns it to the caller within the 45-second deadline

#### Scenario: PTY timeout returns error
- **WHEN** `claude auth login` does not produce a verification URL within 45 seconds
- **THEN** the login container is cleaned up and `POST /login/claude` returns an error

### Requirement: Claude credential injected into crew containers at launch

When `GA_CREW_ACP_BACKEND=claude` and `ga-claude-auth` exists, the transport SHALL inject the Claude credential into each new crew container's `~/.claude/` directory during setup, so `claude-agent-acp` can authenticate without an API key.

#### Scenario: OAuth credential injected at crew setup
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` and `ga-claude-auth` is present
- **THEN** the Claude credential is written into the crew container's `~/.claude/` before the gateway starts; no `ANTHROPIC_API_KEY` env var is injected

#### Scenario: API key path unaffected when GA_CREW_ANTHROPIC_API_KEY is set
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is set (regardless of `ga-claude-auth` presence)
- **THEN** the API key env var path takes precedence; OAuth credential injection is skipped

### Requirement: Orphaned Claude login containers cleaned up on startup

When the transport starts and one or more containers named `ga-claude-login-*` exist, they SHALL be stopped and removed during `_reconcile_registry` before any other operations.

#### Scenario: Orphaned login containers removed on startup
- **WHEN** the transport starts and one or more containers named `ga-claude-login-*` exist
- **THEN** those containers are stopped and removed during `_reconcile_registry` before any other operations
