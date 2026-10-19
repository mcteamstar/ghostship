## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Claude authorisation-code flow state machine
**Reason**: Logout no longer removes the Claude credential from running crews (logout acts on the transport only). Replaced by "Claude authorisation-code flow states", which is otherwise unchanged.
**Migration**: None for operators. A running claude crew keeps its credential after `ghostship auth logout claude`; relaunch or nuke it to drop it.
