# claude-auth Specification

## Purpose

Defines the Claude Code OAuth device-code login flow, credential storage, injection into crew containers, and logout — a parallel auth state machine to the existing kiro-cli auth path, enabling Claude Pro/Max subscription users to run Claude-backend crews without an Anthropic API key.

## Requirements

### Requirement: Claude login uses PTY to handle interactive prompts

The `claude auth login` command may present interactive prompts (consent confirmation, URL display) in a terminal context. The transport SHALL run it via a PTY exec (same `container_exec_pty_stdin` mechanism used for kiro-cli login), reading output and answering any prompts automatically. Before extracting the authorisation URL and code from the output stream, the transport SHALL remove terminal control sequences (ANSI CSI, OSC including OSC-8 hyperlinks, and BEL), so the returned URL is exactly the URL the CLI printed.

Before the PTY output loop begins, any bytes received in the same network chunk as the HTTP 101 upgrade response headers SHALL be prepended to the accumulated PTY output, so no authorisation URL printed in that initial burst is discarded. The raw socket SHALL have a socket timeout applied before the first read so that a hung Podman socket does not block the transport indefinitely.

#### Scenario: Login URL extracted from PTY output
- **WHEN** `claude auth login` is run via PTY inside the login container and outputs an authorisation URL
- **THEN** the transport captures the URL from the PTY output stream and returns it to the caller within the 45-second deadline

#### Scenario: Terminal control sequences removed from the URL
- **WHEN** the CLI wraps the authorisation URL in colour codes or OSC-8 hyperlink sequences
- **THEN** the returned `login_url` contains only the URL characters, with no escape bytes, BEL characters, or trailing sequence fragments

#### Scenario: PTY timeout returns error
- **WHEN** `claude auth login` does not produce an authorisation URL within 45 seconds
- **THEN** the login container is cleaned up and `POST /login/claude` returns an error

#### Scenario: Login URL present in the same chunk as the 101 headers is not lost
- **GIVEN** the PTY exec socket for a Claude login
- **WHEN** the Podman daemon sends the HTTP 101 upgrade headers and the first PTY bytes (including the authorisation URL) in a single TCP segment
- **THEN** the transport returns the authorisation URL correctly — it is not silently discarded

### Requirement: Claude login abandonment expires without polling

An in-progress Claude login flow that has been in the `awaiting_code` state for more than 900 seconds SHALL be expired by the periodic maintenance sweep, independent of `GET /login/claude` being polled. An in-progress Claude login flow that has been in the `code_submitted` state for more than 120 seconds SHALL likewise be expired by the sweep. On expiry the transport SHALL remove the login container (best-effort), clear `_claude_login_pending`, and record `action=login outcome=failure` in the audit log.

#### Scenario: Unpolled awaiting-code flow expires via sweep
- **GIVEN** a Claude login flow has been in `awaiting_code` state for more than 900 seconds and `GET /login/claude` has never been called
- **WHEN** the periodic maintenance sweep runs
- **THEN** the `ga-claude-login-<token>` container is removed and `_claude_login_pending` is set to None — a subsequent `POST /login/claude` is accepted

#### Scenario: Unpolled code-submitted flow expires via sweep
- **GIVEN** a Claude login flow has been in `code_submitted` state for more than 120 seconds and `GET /login/claude` has not been called since the code was submitted
- **WHEN** the periodic maintenance sweep runs
- **THEN** the `ga-claude-login-<token>` container is removed and `_claude_login_pending` is set to None

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

### Requirement: Orphaned Claude login containers cleaned up on startup

When the transport starts and one or more containers named `ga-claude-login-*` exist, they SHALL be stopped and removed during `_reconcile_registry` before any other operations.

#### Scenario: Orphaned login containers removed on startup
- **WHEN** the transport starts and one or more containers named `ga-claude-login-*` exist
- **THEN** those containers are stopped and removed during `_reconcile_registry` before any other operations

### Requirement: Claude login accepts a pasted authorisation code

After `POST /login/claude` returns a login URL, the user completes the browser approval and copies the code shown on the redirect page. The transport SHALL expose `POST /login/claude/code` accepting `{"code": "<code>"}` and SHALL write that code, followed by a newline, to the pending login's PTY so the CLI can complete the token exchange. The code SHALL NOT be logged or echoed in any response.

#### Scenario: Code accepted for a pending flow
- **WHEN** `POST /login/claude/code` is called with a non-empty `code` and a Claude login flow is pending
- **THEN** the transport writes the code to the login PTY, returns HTTP 202, and the next `GET /login/claude` poll reports the outcome of the exchange

#### Scenario: Code rejected when no flow is pending
- **WHEN** `POST /login/claude/code` is called and no Claude login flow is in progress
- **THEN** the transport returns HTTP 404 and writes nothing

#### Scenario: Code rejected when the body is malformed
- **WHEN** `POST /login/claude/code` is called with a missing, empty, or non-string `code`
- **THEN** the transport returns HTTP 400 and writes nothing to the PTY

#### Scenario: Pasted code that never completes the exchange expires
- **WHEN** a code was submitted and `GET /login/claude` is polled more than 120 seconds later with no credential written
- **THEN** the transport removes the login container, clears the pending state, records `action=login outcome=failure` in the audit log, and returns HTTP 410 with `{"status": "expired"}`

#### Scenario: Login never approved expires
- **WHEN** no code has been submitted and `GET /login/claude` is polled more than 900 seconds after the flow started
- **THEN** the transport removes the login container, clears the pending state, records `action=login outcome=failure` in the audit log, and returns HTTP 410 with `{"status": "expired"}`

#### Scenario: Code never appears in logs
- **WHEN** `POST /login/claude/code` is called with a valid code
- **THEN** no log line, audit entry, or response body contains the submitted code

### Requirement: Claude login completion is verified against the credential

The transport SHALL treat a Claude login as complete only when the credential file written by the Claude CLI after a successful token exchange exists and is non-empty. Other files under the Claude config directory, including backups and settings, SHALL NOT count as completion. The transport SHALL NOT write `ga-claude-auth` or record a successful login unless this check passes.

#### Scenario: Config backup alone does not complete login
- **WHEN** `GET /login/claude` is polled and only a non-credential file (such as a `.claude.json` backup) exists under the Claude config directory
- **THEN** the transport returns `{"status": "pending"}`, does not write `ga-claude-auth`, and records no login outcome

#### Scenario: Audit log records success only on a verified credential
- **WHEN** a Claude login completes and `ga-claude-auth` is written
- **THEN** the audit log entry `action=login outcome=success` is written at that point and not earlier

### Requirement: Claude backend is opt-in

The Claude backend SHALL be available only when `claude` is an enabled backend, as defined by the `agent-backends` capability (`GA_AGENT_BACKENDS`). Kiro remains the default. Claude login SHALL be available whenever claude is enabled, including when it is not the default backend. When claude is not enabled, `POST /login/claude` SHALL return HTTP 400 naming `GA_AGENT_BACKENDS`, and the transport SHALL refuse to start with claude as the default backend.

The operator documentation (`docs/auth.md`) SHALL document `CLAUDE_CODE_OAUTH_TOKEN` (generated with `claude setup-token`) as the recommended Claude auth path for headless and server deployments, and SHALL document the OAuth device-code flow (`POST /login/claude` + `POST /login/claude/code`) as the alternative for interactive use. The known-limitation note about OAuth token expiry causing cross-crew invalidation SHALL be scoped to the OAuth path only and SHALL NOT apply to the token path.

#### Scenario: Login refused when the image lacks the Claude CLI
- **WHEN** claude is not an enabled backend and `POST /login/claude` is called
- **THEN** the transport returns HTTP 400 with a message naming `GA_AGENT_BACKENDS`, and no login container is created

#### Scenario: Setup-token login refused when the image lacks the Claude CLI
- **WHEN** claude is not an enabled backend and `POST /login/claude/setup-token` is called
- **THEN** the transport returns HTTP 404 because the route no longer exists, and no login container is created

#### Scenario: Launch refused when the image lacks the Claude CLI
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and claude is not an enabled backend
- **THEN** the transport raises a `ConfigError` at startup naming both settings, so no launch or Claude login flow can start

#### Scenario: Kiro is the default backend
- **WHEN** `GA_CREW_ACP_BACKEND` is unset
- **THEN** crews launch on kiro and no Claude login or opt-in check applies to them

#### Scenario: Claude login available while kiro is the default
- **WHEN** claude is an enabled backend, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/claude` is called
- **THEN** the Claude login flow starts

#### Scenario: Setup-token login available while kiro is the default
- **WHEN** claude is an enabled backend, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/claude/setup-token` is called
- **THEN** the transport returns HTTP 404 because the route no longer exists; headless Claude auth is configured through `CLAUDE_CODE_OAUTH_TOKEN` instead

### Requirement: Claude authorisation-code flow states
The Claude authorisation-code flow SHALL have three states: idle, pending and complete. `POST /login/claude/oauth` moves idle to pending. `GET /login/claude` moves pending to complete once a code has been submitted through `POST /login/claude/oauth/code`, storing the result as claude's active credential (method `oauth`). The transport MUST NOT make any other transition. Clearing is done with `POST /logout/claude`, which also cancels a pending flow and leaves running crews untouched.

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

#### Scenario: Logout leaves running claude crews untouched
- **WHEN** `POST /logout/claude` is called and claude's active method is `oauth` while claude crews are running
- **THEN** the stored credential is deleted, and no running crew's `~/.claude/` is modified
