# auth/backend-credentials Specification

## Purpose

Defines stored backend credentials, their status and removal.

## Requirements

### Requirement: Backend credentials persisted under DATA_DIR
The transport SHALL persist each backend's credential as a file under `DATA_DIR` with mode `0600`. Writes SHALL be atomic: a reader SHALL see either the previous credential or the new one, never a partial file. Credential values SHALL never be logged, echoed in responses, or written anywhere else.

#### Scenario: Stored credential file permissions
- **WHEN** a credential is stored for any backend
- **THEN** its file under `DATA_DIR` has mode `0600`

#### Scenario: Interrupted write leaves previous credential intact
- **WHEN** the transport is killed partway through replacing a backend's credential
- **THEN** on restart the backend's credential is either the complete previous value or the complete new value

#### Scenario: Credential value never returned
- **WHEN** any credential endpoint responds
- **THEN** the response body contains no credential value

### Requirement: Supported credential methods per backend
The transport SHALL support only these methods. kiro: `api-key`, `builder-id`, `identity-center`. claude: `oauth`, `api-key`, `setup-token`. codex: `chatgpt`, `api-key`. The method names SHALL be the same in login routes, status responses and the CLI's `--method`.

#### Scenario: Method names consistent
- **WHEN** a codex ChatGPT login completes and `GET /login/codex` is called
- **THEN** codex's method is reported as `chatgpt`, the same segment used in `POST /login/codex/chatgpt` and `ghostship auth login codex --method chatgpt`

### Requirement: Interactive credential flows store into the same slot
Each interactive flow SHALL, on completion, store its result as the selected backend and profile's stored credential, tagged `builder-id`, `identity-center`, `oauth` or `chatgpt`, under the same replacement rule as static credentials. Identity Center SHALL use the start URL and region from the request, or else the configured `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION`, and record them with the credential.

#### Scenario: Identity Center login records provider settings
- **WHEN** a kiro `identity-center` flow is started with a start URL and region and the user completes it
- **THEN** the selected Kiro profile's credential is the resulting kiro-cli login state, tagged `identity-center`, together with that start URL and region

#### Scenario: Builder ID login needs no provider settings
- **WHEN** a kiro `builder-id` flow is started with no start URL or region and the user completes it
- **THEN** the selected Kiro profile's credential is tagged `builder-id`

#### Scenario: Completed authorisation-code flow replaces an API key
- **WHEN** a Claude profile holds an `api-key` credential and an authorisation-code flow completes for that profile
- **THEN** the selected Claude profile's credential is the login archive, tagged `oauth`, and the API key is gone

### Requirement: Credential status reported per backend
`GET /login/{backend}` SHALL return whether the backend is enabled, whether the selected profile is configured, its public method and storage metadata, and any pending flow for that profile (`pending`, then `complete`); clients poll it while a flow runs. For kiro it SHALL also return the configured Identity Center `start_url` and `region`, if any. It SHALL include no credential values.

#### Scenario: Status for a configured backend
- **WHEN** `GET /login/claude` is called and claude has a stored `setup-token`
- **THEN** the response reports claude as configured with `method: setup-token` and its stored time

#### Scenario: Status for an unconfigured backend
- **WHEN** `GET /login/kiro` is called and kiro holds no credential
- **THEN** the response reports no credential and no pending flow

#### Scenario: Polling a pending flow
- **WHEN** a codex ChatGPT flow is pending and `GET /login/codex` is called
- **THEN** the response reports `status: pending` with the flow's `login_url`, and after completion reports `status: complete` with `method: chatgpt`

#### Scenario: Kiro status exposes Identity Center defaults
- **WHEN** `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are configured and `GET /login/kiro` is called
- **THEN** the response includes those values as `identity_center.start_url` and `identity_center.region`

### Requirement: Logout removes stored backend credentials

Logout SHALL remove the selected profile's credential regardless of method. Omitted profile selection follows the credential-profiles contract. Removal failures SHALL return HTTP 500; if the container runtime is unavailable, the credential SHALL still be removed and cancellation SHALL return HTTP 500.

#### Scenario: Logout removes stored credential
- **WHEN** `POST /logout/kiro` is called while kiro holds a credential
- **THEN** kiro's credential file is removed and `GET /login/kiro` reports no credential

#### Scenario: Store-only credential is cleared
- **WHEN** `POST /logout/claude` is called while claude's active method is `setup-token` or `api-key`
- **THEN** the transport returns HTTP 200, the credential is removed, and `GET /login/claude` reports no credential

#### Scenario: A failed removal is an error
- **WHEN** `POST /logout/{backend}` is called and the stored credential cannot be deleted
- **THEN** the transport returns HTTP 500, records a failed logout in the audit log, and does not report `logged_out`

#### Scenario: Container runtime unavailable
- **WHEN** `POST /logout/{backend}` is called while the container runtime cannot be reached
- **THEN** the stored credential is still removed, and the transport returns HTTP 500 saying a pending login could not be cancelled, without reporting `logged_out`

### Requirement: Logout is idempotent when no credential is stored

Logout SHALL return HTTP 200 without changing state when the resolved profile has no stored credential or pending flow.

#### Scenario: Logout with nothing stored
- **WHEN** `POST /logout/codex` is called and codex holds no credential
- **THEN** the transport returns success and changes nothing

### Requirement: Credential replacement is scoped to one backend and profile

Each backend and credential profile SHALL hold at most one stored credential, tagged with the method that produced it. Storing a credential SHALL replace only the selected profile's credential, including when the method changes. Other profiles and backends SHALL retain their credentials. Profile naming, omitted-profile resolution and legacy migration follow the credential-profiles contract.

#### Scenario: New method replaces old in the selected profile
- **WHEN** a Claude profile holds an OAuth credential and a setup token is stored into that profile
- **THEN** the selected profile reports `setup-token`, while any other Claude profile and other backend credentials are unchanged
