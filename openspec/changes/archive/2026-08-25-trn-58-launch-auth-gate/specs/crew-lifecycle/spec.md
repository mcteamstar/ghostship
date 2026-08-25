## NEW Requirements

### Requirement: Authentication gate precedes registry write in launch
The system SHALL check for a valid auth file at the very start of `launch`, before writing any placeholder into the crew registry. If no valid auth is present, `launch` SHALL initiate the device auth flow (equivalent to `POST /login`) and return the `login_url` and `code` in the error response so the caller can complete authentication and then retry `launch` without a separate API call. The crew registry SHALL NOT be modified when launch fails the auth gate.

#### Scenario: launch called before authentication
- **WHEN** `launch` is called and no valid auth file exists
- **THEN** the device auth flow is initiated automatically, the response includes `error: "not_authenticated"`, `login_url`, and `code` (or `null` if the URL could not be extracted within the timeout), no registry entry is written for the crew, and the caller can open the `login_url`, complete auth, and retry `launch` without calling `POST /login` first

#### Scenario: launch called while a login flow is already pending
- **WHEN** `launch` is called, no valid auth file exists, and a login flow is already in progress
- **THEN** the response includes `error: "not_authenticated"` and `login_pending: true` indicating the caller should poll `GET /login` before retrying

#### Scenario: launch called after completing auth
- **WHEN** `launch` is called and a valid auth file exists
- **THEN** the auth gate passes, the registry placeholder is written, and launch proceeds normally
