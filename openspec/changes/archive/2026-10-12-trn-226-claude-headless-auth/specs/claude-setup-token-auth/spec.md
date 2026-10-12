## Purpose

Provides a synchronous, non-interactive Claude auth route for headless and server deployments, replacing the multi-step OAuth device-code flow with a single `POST /login/claude/setup-token` call that calls `claude setup-token` inside the login container and stores the resulting credential as `ga-claude-auth`.

## ADDED Requirements

### Requirement: POST /login/claude/setup-token completes auth synchronously

The transport SHALL expose `POST /login/claude/setup-token` that runs `claude setup-token` via non-interactive container exec inside a `ga-claude-login-*` container, extracts the resulting credential, writes it to `ga-claude-auth`, and returns `{"status": "complete"}` — all in a single synchronous request. The route SHALL NOT require a valid `ga-claude-auth` to exist (it is a public route exempt from bearer auth middleware, the same exemption applied to `POST /login/claude` and `POST /login/claude/code`).

#### Scenario: Successful setup-token auth
- **WHEN** `POST /login/claude/setup-token` is called, claude is an enabled backend, and no existing `ga-claude-auth` is present
- **THEN** the transport starts a `ga-claude-login-*` container, runs `claude setup-token` via container exec, writes the resulting credential to `ga-claude-auth` (mode 0600), nukes the login container, and returns HTTP 200 with `{"status": "complete"}`

#### Scenario: Already authenticated returns 409
- **WHEN** `POST /login/claude/setup-token` is called and `ga-claude-auth` already exists and is non-empty
- **THEN** the transport returns HTTP 409 with a message indicating Claude auth is already present and `POST /logout/claude` must be called first; no login container is created

#### Scenario: OAuth flow in progress returns 409
- **WHEN** `POST /login/claude/setup-token` is called while a Claude OAuth login flow is already pending
- **THEN** the transport returns HTTP 409 indicating a login is already in progress; no setup-token container is created

#### Scenario: claude not an enabled backend returns 400
- **WHEN** `POST /login/claude/setup-token` is called and claude is not an enabled backend
- **THEN** the transport returns HTTP 400 naming `GA_AGENT_BACKENDS`; no login container is created

#### Scenario: setup-token exec failure returns 500
- **WHEN** `claude setup-token` exits non-zero or does not write a credential within 60 seconds
- **THEN** the login container is nuked, `ga-claude-auth` is NOT written, and the transport returns HTTP 500 with `{"error": "<message>"}`

#### Scenario: Route requires API key auth
- **WHEN** `GA_API_KEY` is configured and `POST /login/claude/setup-token` is called without a valid bearer token
- **THEN** the transport responds with HTTP 401 Unauthorized

### Requirement: setup-token credential is compatible with the existing injection path

The credential written to `ga-claude-auth` by `POST /login/claude/setup-token` SHALL be byte-for-byte compatible with the tar archive format written by the OAuth completion path, so that `_inject_claude_auth` and `_archive_has_claude_credential` work without modification on credentials obtained via either route.

#### Scenario: setup-token credential injects into crew containers
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` after `POST /login/claude/setup-token` has completed
- **THEN** `_inject_claude_auth` writes the Claude credential into the crew container's `~/.claude/` successfully, using the same code path as for an OAuth-obtained credential

#### Scenario: setup-token credential detected by archive check
- **WHEN** `_archive_has_claude_credential` is called on a `ga-claude-auth` produced by the setup-token flow
- **THEN** it returns true, consistent with an OAuth-produced credential
