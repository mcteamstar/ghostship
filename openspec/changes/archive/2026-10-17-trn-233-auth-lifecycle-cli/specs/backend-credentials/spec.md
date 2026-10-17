# Spec Delta

## Purpose

The transport-side store for model-backend credentials (kiro, claude, codex). It
is the single place credentials are persisted, inspected, replaced and cleared,
and the single source crews receive them from at launch.

## ADDED Requirements

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

### Requirement: One active credential per backend
Each backend SHALL hold at most one active credential, tagged with the method that produced it. Storing a credential for a backend SHALL replace whatever that backend held before, whichever method produced it. No precedence between methods SHALL apply.

#### Scenario: New method replaces old
- **WHEN** claude holds an authorisation-code credential and a setup-token is stored for claude
- **THEN** the authorisation-code credential is removed and claude's active method is `setup-token`

#### Scenario: Backends are independent
- **WHEN** a credential is stored for codex
- **THEN** the kiro and claude credentials are unchanged

### Requirement: Supported credential methods per backend
The transport SHALL support only these methods. kiro: `api-key`, `builder-id`, `identity-center`. claude: `oauth`, `api-key`, `setup-token`. codex: `chatgpt`, `api-key`. The method names SHALL be the same in login routes, status responses and the CLI's `--method`.

#### Scenario: Method names consistent
- **WHEN** a codex ChatGPT login completes and `GET /login/codex` is called
- **THEN** codex's method is reported as `chatgpt`, the same segment used in `POST /login/codex/chatgpt` and `ghostship auth login codex --method chatgpt`

### Requirement: Login routes are per backend and per method
The transport SHALL expose one route per backend and method: `POST /login/kiro/{api-key|builder-id|identity-center}`, `POST /login/claude/{oauth|api-key|setup-token}` (plus `POST /login/claude/oauth/code`), and `POST /login/codex/{chatgpt|api-key}`. An unknown backend or method SHALL return HTTP 404. All login and logout routes SHALL sit behind the transport's bearer authentication.

#### Scenario: Unknown method
- **WHEN** `POST /login/codex/oauth` is called
- **THEN** the transport returns HTTP 404 and starts nothing

#### Scenario: Unauthenticated login rejected on keyed transport
- **WHEN** the transport has a bearer key configured and `POST /login/kiro/api-key` arrives without it
- **THEN** the transport returns HTTP 401 and stores nothing

### Requirement: Pasted credentials stored through their login route
`POST /login/{backend}/{api-key|setup-token}` SHALL take a JSON body `{"secret": "..."}`, store it as that backend's active credential and return the backend's status (no value) without starting any flow. An empty or missing secret SHALL be rejected with HTTP 400 and leave the stored credential unchanged.

#### Scenario: Store a Claude setup-token
- **WHEN** `POST /login/claude/setup-token` is called with `{"secret": "<token>"}`
- **THEN** the token is stored as claude's active credential and the response reports `method: setup-token`

#### Scenario: Empty secret rejected
- **WHEN** `POST /login/codex/api-key` is called with an empty `secret`
- **THEN** the transport returns HTTP 400 and the stored codex credential is unchanged

### Requirement: Interactive credential flows store into the same slot
Each interactive flow SHALL, on completion, store its result as that backend's active credential, tagged `builder-id`, `identity-center`, `oauth` or `chatgpt`, under the same replacement rule as static credentials. Identity Center SHALL use the start URL and region from the request, or else the configured `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION`, and record them with the credential.

#### Scenario: Identity Center login records provider settings
- **WHEN** a kiro `identity-center` flow is started with a start URL and region and the user completes it
- **THEN** kiro's active credential is the resulting kiro-cli login state, tagged `identity-center`, together with that start URL and region

#### Scenario: Builder ID login needs no provider settings
- **WHEN** a kiro `builder-id` flow is started with no start URL or region and the user completes it
- **THEN** kiro's active credential is tagged `builder-id`

#### Scenario: Completed authorisation-code flow replaces an API key
- **WHEN** claude holds an `api-key` credential and a Claude authorisation-code flow completes
- **THEN** claude's active credential is the login archive, tagged `oauth`, and the API key is gone

### Requirement: Credential status reported per backend
`GET /login/{backend}` SHALL return whether the backend is enabled, whether a credential is stored, its method, when it was stored, and any pending flow (`pending`, then `complete`); clients poll it while a flow runs. For kiro it SHALL also return the configured Identity Center `start_url` and `region`, if any. It SHALL include no credential values.

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

### Requirement: Login requires the backend to be enabled
`POST /login/{backend}/...` SHALL return HTTP 400 naming `GA_CREW_AGENT` when the backend is not enabled, and store or start nothing. `GET /login/{backend}` and `POST /logout/{backend}` SHALL work whether or not the backend is enabled.

#### Scenario: Login to a disabled backend
- **WHEN** codex is not in `GA_CREW_AGENT` and `POST /login/codex/api-key` is called
- **THEN** the transport returns HTTP 400 telling the operator to add codex to `GA_CREW_AGENT`, and stores nothing

#### Scenario: Logout from a disabled backend
- **WHEN** claude is not enabled but holds a stored credential and `POST /logout/claude` is called
- **THEN** the credential is removed

### Requirement: Bare login and logout paths are unassigned
The transport SHALL NOT serve any route at bare `/login` or `/logout` (any method). They are reserved for a future browser login page.

#### Scenario: Bare paths
- **WHEN** `GET /login`, `POST /login` or `POST /logout` is called
- **THEN** the transport returns HTTP 404

### Requirement: Credentials cleared per backend
`POST /logout/{backend}` SHALL remove that backend's stored credential whichever method produced it, cancel any pending login flow for it, and clear the credential from running crews of that backend. It SHALL succeed when nothing is stored (idempotent).

#### Scenario: Logout removes stored credential
- **WHEN** `POST /logout/kiro` is called while kiro holds a credential
- **THEN** kiro's credential file is removed and `GET /login/kiro` reports no credential

#### Scenario: Logout with nothing stored
- **WHEN** `POST /logout/codex` is called and codex holds no credential
- **THEN** the transport returns success and changes nothing

### Requirement: Credentials resolved at each crew launch
The transport SHALL read a backend's active credential from the store when it launches a crew, not once at startup. A credential stored, replaced or cleared SHALL take effect for the next crew launch without restarting the transport. Crews already running keep the credential they launched with, except that logout clears it from them and a completed kiro device login is injected into running kiro crews (crew-auth).

#### Scenario: Rotation without restart
- **WHEN** a new claude API key is stored while the transport is running and a claude crew is then launched
- **THEN** the new crew receives the new key, with no transport restart or reinstall

### Requirement: Credential delivered to crews according to its method
At crew launch the transport SHALL deliver only the backend's active credential. `api-key` (kiro, claude, codex) SHALL be set as `KIRO_API_KEY`, `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` respectively. Claude `setup-token` SHALL be set as `CLAUDE_CODE_OAUTH_TOKEN`. Kiro device-flow, Claude authorisation-code and Codex `chatgpt` credentials SHALL be installed as the CLI's login state inside the crew (for codex, `~/.codex/auth.json`).

#### Scenario: Exactly one Claude credential reaches the crew
- **WHEN** claude's active method is `setup-token` and a claude crew launches
- **THEN** the crew has `CLAUDE_CODE_OAUTH_TOKEN` set, and has neither `ANTHROPIC_API_KEY` nor an installed `~/.claude/` login

#### Scenario: Codex ChatGPT credential reaches the crew as login state
- **WHEN** codex's active method is `chatgpt` and a codex crew launches
- **THEN** the crew's `~/.codex/auth.json` holds the stored login and `OPENAI_API_KEY` is not set

### Requirement: Launch starts the backend's interactive login when no credential is stored
When a crew is launched on a backend with no stored credential, the transport SHALL NOT create the crew. It SHALL start that backend's interactive login and return `not_authenticated` with its `login_url`, any `code`, and instructions to complete it and call launch again. kiro uses `identity-center` when Identity Center is configured, else `builder-id`; claude uses `oauth`; codex uses `chatgpt`.

#### Scenario: Kiro with Identity Center configured
- **WHEN** a kiro crew is launched, kiro has no stored credential, and `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are configured
- **THEN** launch starts the Identity Center device-code flow with those values and returns `not_authenticated` with its `login_url` and `code`

#### Scenario: Kiro without Identity Center configured
- **WHEN** a kiro crew is launched, kiro has no stored credential, and no Identity Center settings are configured
- **THEN** launch starts the Builder ID device-code flow and returns `not_authenticated` with its `login_url` and `code`

#### Scenario: Codex without credential
- **WHEN** a codex crew is launched and codex has no stored credential
- **THEN** launch starts the ChatGPT device-code flow and returns `not_authenticated` with its `login_url` and `code`, and creates no crew container

#### Scenario: Claude without credential
- **WHEN** a claude crew is launched and claude has no stored credential
- **THEN** launch starts the Claude authorisation-code flow and returns `not_authenticated` with its `login_url`; the code is submitted through `POST /login/claude/oauth/code`

#### Scenario: Flow already pending
- **WHEN** a crew is launched while that backend's login flow is already pending
- **THEN** launch returns `not_authenticated` with the pending flow's `login_url` rather than starting a second flow

#### Scenario: Stored credential skips login
- **WHEN** a crew is launched and its backend holds any stored credential, including an API key
- **THEN** no login flow is started and the crew is created with that credential
