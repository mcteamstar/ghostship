# Spec Delta

## MODIFIED Requirements

### Requirement: Claude auth state machine

The Ghost Academy has a Claude auth state machine with exactly three states — unauthenticated, pending, and authenticated — determined by the presence and content of `DATA_DIR/ga-claude-auth`. Transitions are: unauthenticated → pending via `POST /login/claude`; pending → authenticated via `GET /login/claude` completing after a code has been submitted through `POST /login/claude/code`; authenticated → unauthenticated via `POST /logout/claude`. No other transitions are valid, and the transport MUST NOT make any other transition. This state machine is independent of the kiro auth state machine.

#### Scenario: POST /login/claude starts device flow when unauthenticated
- **WHEN** `POST /login/claude` is called and `ga-claude-auth` does not exist or is empty
- **THEN** the transport starts a Claude Code OAuth authorisation flow, returns HTTP 200 with `{"login_url": "<url>", "code": null}` where `login_url` contains no terminal control sequences, and stores the pending flow state. `code` is null because the authorisation code is shown in the browser after approval, not in the CLI output

#### Scenario: POST /login/claude returns 409 when already authenticated
- **WHEN** `POST /login/claude` is called and `ga-claude-auth` exists and is non-empty
- **THEN** the transport returns HTTP 409 with a message indicating Claude auth is already present and `POST /logout/claude` must be called first

#### Scenario: POST /login/claude returns 409 when flow already in progress
- **WHEN** `POST /login/claude` is called while a Claude login flow is already pending
- **THEN** the transport returns HTTP 409 indicating a flow is in progress and `GET /login/claude` should be polled

#### Scenario: GET /login/claude returns pending while user has not approved
- **WHEN** `GET /login/claude` is polled and the Claude CLI has not yet written its credential file inside the login container
- **THEN** the transport returns HTTP 200 with `{"status": "pending", "login_url": "<url>"}`

#### Scenario: GET /login/claude completes and writes ga-claude-auth
- **WHEN** `GET /login/claude` is polled and the credential file written by the Claude CLI after a successful token exchange exists and is non-empty
- **THEN** the transport writes an archive containing that credential file to `DATA_DIR/ga-claude-auth` (mode 0600), cleans up the login container, records a successful login in the audit log, and returns HTTP 200 with `{"status": "complete"}`

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

The `claude auth login` command may present interactive prompts (consent confirmation, URL display) in a terminal context. The transport SHALL run it via a PTY exec (same `container_exec_pty_stdin` mechanism used for kiro-cli login), reading output and answering any prompts automatically. Before extracting the authorisation URL and code from the output stream, the transport SHALL remove terminal control sequences (ANSI CSI, OSC including OSC-8 hyperlinks, and BEL), so the returned URL is exactly the URL the CLI printed.

#### Scenario: Login URL extracted from PTY output
- **WHEN** `claude auth login` is run via PTY inside the login container and outputs an authorisation URL
- **THEN** the transport captures the URL from the PTY output stream and returns it to the caller within the 45-second deadline

#### Scenario: Terminal control sequences removed from the URL
- **WHEN** the CLI wraps the authorisation URL in colour codes or OSC-8 hyperlink sequences
- **THEN** the returned `login_url` contains only the URL characters, with no escape bytes, BEL characters, or trailing sequence fragments

#### Scenario: PTY timeout returns error
- **WHEN** `claude auth login` does not produce an authorisation URL within 45 seconds
- **THEN** the login container is cleaned up and `POST /login/claude` returns an error

## ADDED Requirements

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
