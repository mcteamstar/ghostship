# Spec Delta

## MODIFIED Requirements

### Requirement: Claude credential injected into crew containers at launch

When claude's active method is `oauth`, the transport SHALL inject the stored Claude credential into each new Claude-backend crew container's `~/.claude/` directory during setup, so `claude-agent-acp` can authenticate without an API key or token.

#### Scenario: OAuth credential injected at crew setup
- **WHEN** a claude crew is launched and claude's active method is `oauth`
- **THEN** the Claude credential is written into the crew container's `~/.claude/` before the gateway starts; no `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` env var is injected

#### Scenario: API key path unaffected when GA_CREW_ANTHROPIC_API_KEY is set
- **WHEN** a claude crew is launched and claude's active method is `api-key`
- **THEN** `ANTHROPIC_API_KEY` is injected and nothing is written into the crew container's `~/.claude/` credential location

#### Scenario: OAuth credential injection skipped when the OAuth token is set
- **WHEN** a claude crew is launched and claude's active method is `setup-token`
- **THEN** `CLAUDE_CODE_OAUTH_TOKEN` is injected and nothing is written into the crew container's `~/.claude/` credential location

## ADDED Requirements

### Requirement: Claude authorisation-code flow state machine
The Claude authorisation-code flow SHALL have three states: idle, pending and complete. `POST /login/claude/oauth` moves idle to pending. `GET /login/claude` moves pending to complete once a code has been submitted through `POST /login/claude/oauth/code`, storing the result as claude's active credential (method `oauth`). The transport MUST NOT make any other transition. Clearing is done with `POST /logout/claude`.

#### Scenario: POST /login/claude/oauth starts the flow
- **WHEN** `POST /login/claude/oauth` is called and no Claude login flow is pending, whether or not claude already holds a credential
- **THEN** the transport starts a Claude Code OAuth authorisation flow, returns HTTP 200 with `{"login_url": "<url>", "code": null}` where `login_url` contains no terminal control sequences, and stores the pending flow state. `code` is null because the authorisation code is shown in the browser after approval, not in the CLI output

#### Scenario: POST /login/claude/oauth returns 409 when flow already in progress
- **WHEN** `POST /login/claude/oauth` is called while a Claude login flow is already pending
- **THEN** the transport returns HTTP 409 indicating a flow is in progress and `GET /login/claude` should be polled

#### Scenario: GET /login/claude returns pending while user has not approved
- **WHEN** `GET /login/claude` is polled and the Claude CLI has not yet written its credential file inside the login container
- **THEN** the transport returns HTTP 200 with `{"status": "pending", "login_url": "<url>"}`

#### Scenario: GET /login/claude completes and stores the credential
- **WHEN** `GET /login/claude` is polled and the credential file written by the Claude CLI after a successful token exchange exists and is non-empty
- **THEN** the transport stores an archive containing that credential file as claude's active credential (mode 0600, method `oauth`), replacing any previous claude credential, cleans up the login container, records a successful login in the audit log, and returns HTTP 200 with `{"status": "complete"}`

#### Scenario: GET /login/claude returns 404 when no flow is pending
- **WHEN** `GET /login/claude` is polled and no login flow is in progress
- **THEN** the transport returns HTTP 404

#### Scenario: Clearing claude wipes running crews
- **WHEN** `POST /logout/claude` is called and claude's active method is `oauth`
- **THEN** the credential is deleted and the transport removes the Claude credential from every running Claude-backend crew's container without restarting those crews

## REMOVED Requirements

### Requirement: Claude auth state machine
**Reason**: Replaced by "Claude authorisation-code flow state machine": the flow no longer refuses to start when claude holds a credential (completion replaces it), and `POST /logout/claude` now clears any claude credential and is idempotent.
**Migration**: `POST /login/claude` moves to `POST /login/claude/oauth` and `POST /login/claude/code` to `POST /login/claude/oauth/code`; `GET /login/claude` and `POST /logout/claude` keep their paths.
