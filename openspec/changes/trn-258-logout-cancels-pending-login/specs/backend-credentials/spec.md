## MODIFIED Requirements

### Requirement: Credentials cleared per backend
`POST /logout/{backend}` acts on the transport only. It SHALL first cancel any pending login flow for that backend, removing its login container, then remove the backend's stored credential whichever method produced it. It SHALL NOT modify running crews. It SHALL succeed when nothing is stored or pending (idempotent), returning HTTP 200. It SHALL fail with HTTP 500 when a credential could not be removed, or when a pending login could not be cancelled because the container runtime is unavailable; the credential is removed in the second case too.

#### Scenario: Logout removes stored credential
- **WHEN** `POST /logout/kiro` is called while kiro holds a credential
- **THEN** kiro's credential file is removed and `GET /login/kiro` reports no credential

#### Scenario: Logout with nothing stored
- **WHEN** `POST /logout/codex` is called and codex holds no credential
- **THEN** the transport returns success and changes nothing

#### Scenario: Logout cancels a pending login with nothing stored
- **WHEN** a kiro device login is pending, kiro holds no credential, and `POST /logout/kiro` is called
- **THEN** the transport returns HTTP 200 with `aborted_pending_login: true`, the login container is removed, and `GET /login/kiro` reports no pending flow

#### Scenario: A new login can start after cancelling
- **WHEN** a pending login was cancelled by `POST /logout/{backend}`
- **THEN** a following `POST /login/{backend}/{method}` starts a new flow instead of returning 409 for an already-pending flow

#### Scenario: Store-only credential is cleared
- **WHEN** `POST /logout/claude` is called while claude's active method is `setup-token` or `api-key`
- **THEN** the transport returns HTTP 200, the credential is removed, and `GET /login/claude` reports no credential

#### Scenario: Running crews are left alone
- **WHEN** `POST /logout/{backend}` is called while crews of that backend are running
- **THEN** no running crew is executed into, restarted or stopped, and each keeps the credential it launched with until it is relaunched

#### Scenario: A failed removal is an error
- **WHEN** `POST /logout/{backend}` is called and the stored credential cannot be deleted
- **THEN** the transport returns HTTP 500, records a failed logout in the audit log, and does not report `logged_out`

#### Scenario: Container runtime unavailable
- **WHEN** `POST /logout/{backend}` is called while the container runtime cannot be reached
- **THEN** the stored credential is still removed, and the transport returns HTTP 500 saying a pending login could not be cancelled, without reporting `logged_out`

#### Scenario: Logout during login startup leaves no container
- **WHEN** `POST /logout/{backend}` cancels a flow whose login container is still being created
- **THEN** the login request that was starting the flow removes the container it created and reports the flow as cancelled, so no login container remains

#### Scenario: Logout while waiting for a login URL
- **WHEN** `POST /logout/{backend}` cancels a flow while its login request is still waiting for the login URL
- **THEN** that login request returns a cancelled error with no URL, removes its container, and does not clear a flow started after the cancel

#### Scenario: A cancelled flow cannot complete
- **WHEN** a pending login is cancelled by `POST /logout/{backend}` while a `GET /login/{backend}` poll is completing it
- **THEN** that poll does not store a credential, and `GET /login/{backend}` reports no credential and no pending flow

### Requirement: Credentials resolved at each crew launch
The transport SHALL read a backend's active credential from the store when it launches a crew, not once at startup. A credential stored, replaced or cleared SHALL take effect for the next crew launch without restarting the transport. Crews already running keep the credential they launched with: logout does not touch them, and the only exception is that a completed kiro device login is injected into running kiro crews (crew-auth).

#### Scenario: Rotation without restart
- **WHEN** a new claude API key is stored while the transport is running and a claude crew is then launched
- **THEN** the new crew receives the new key, with no transport restart or reinstall

#### Scenario: Logout takes effect at the next launch
- **WHEN** a backend is logged out while one of its crews is running, and a new crew of that backend is then launched
- **THEN** the running crew keeps working with its launch-time credential, and the new crew receives no credential and starts that backend's login instead
