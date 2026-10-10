## MODIFIED Requirements

### Requirement: Codex login uses an ephemeral login container

The transport SHALL run the Codex login inside an ephemeral `ga-codex-login-<token>` container built from the spec-ops image (which carries the `codex-acp` adapter only when codex is an enabled backend in `GA_AGENT_BACKENDS`), so the login flow never runs on the host and its credential output can be captured from a known path. Codex login SHALL be available whenever codex is enabled, including when it is not the default backend.

Before the PTY output loop begins, any bytes received in the same network chunk as the HTTP 101 upgrade response headers SHALL be prepended to the accumulated PTY output, so no login URL or device code printed in that initial burst is discarded. The raw socket SHALL have a socket timeout applied before the first read so that a hung Podman socket does not block the transport indefinitely.

The pattern used to extract the optional short device code from PTY output SHALL distinguish a code from prose. Specifically:
- When a `user_code=` query parameter is present in the login URL, the value of that parameter SHALL be used as the code.
- When no URL parameter is available, the code SHALL only be extracted from a prose line if it appears after a `Code:` or `code:` label and consists entirely of uppercase letters and/or digits (4–8 characters, word boundary on both sides). Lowercase words SHALL NOT be captured as a device code.

#### Scenario: Login container requires the Codex-enabled image
- **WHEN** `POST /login/codex` is called and codex is not an enabled backend
- **THEN** the transport returns HTTP 400 naming `GA_AGENT_BACKENDS` and the `ghostship install` re-run as the remedy; no login container is created and no credential is written

#### Scenario: Login container is removed after the flow ends
- **WHEN** a Codex login flow completes, fails, or is abandoned
- **THEN** the `ga-codex-login-<token>` container is stopped and removed (best-effort), leaving no long-lived login container

#### Scenario: Codex login available while another backend is the default
- **WHEN** codex is an enabled backend, `GA_CREW_ACP_BACKEND` is unset, and `POST /login/codex` is called
- **THEN** the Codex login flow starts

#### Scenario: Login URL present in the same chunk as the 101 headers is not lost
- **GIVEN** the PTY exec socket for a Codex login
- **WHEN** the Podman daemon sends the HTTP 101 upgrade headers and the first PTY bytes (including the login URL) in a single TCP segment
- **THEN** the transport returns the login URL correctly — it is not silently discarded

#### Scenario: Prose expiry message does not produce a spurious device code
- **GIVEN** a Codex PTY output stream containing the line "The code will expire in 15 minutes"
- **WHEN** the transport applies the device-code extraction pattern
- **THEN** no device code is extracted from that line — `will`, `expire`, or any other prose word is not treated as a code

#### Scenario: Uppercase device code extracted from prose line
- **GIVEN** a Codex PTY output stream containing the line "Code: ABCD1234"
- **WHEN** the transport applies the device-code extraction pattern
- **THEN** the device code `ABCD1234` is extracted

#### Scenario: Device code extracted from user_code query parameter
- **GIVEN** a Codex login URL containing `?user_code=ABCD1234`
- **WHEN** the transport applies the device-code extraction pattern
- **THEN** the device code `ABCD1234` is extracted from the URL parameter

### Requirement: Abandoned Codex login flows expire without polling

An in-progress Codex login flow (`_codex_login_pending` is non-None) that has not completed within 900 seconds of starting SHALL be expired by a periodic maintenance sweep, independent of whether `GET /login/codex` is polled. On expiry the transport SHALL stop and remove the `ga-codex-login-<token>` container (best-effort) and clear `_codex_login_pending`.

#### Scenario: Abandoned Codex flow is expired by the maintenance sweep
- **GIVEN** a Codex login flow has been pending for more than 900 seconds
- **WHEN** the periodic maintenance sweep runs
- **THEN** the `ga-codex-login-<token>` container is stopped and removed and `_codex_login_pending` is set to None — a subsequent `POST /login/codex` is accepted

#### Scenario: Active Codex flow is not expired prematurely
- **GIVEN** a Codex login flow started less than 900 seconds ago
- **WHEN** the periodic maintenance sweep runs
- **THEN** `_codex_login_pending` is unchanged and the container is not removed
