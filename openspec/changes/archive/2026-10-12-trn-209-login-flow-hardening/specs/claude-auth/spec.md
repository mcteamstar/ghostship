## MODIFIED Requirements

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
