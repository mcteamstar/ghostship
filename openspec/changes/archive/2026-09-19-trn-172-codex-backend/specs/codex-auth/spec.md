## Purpose

Defines the Codex/OpenAI login flow, credential storage, injection into crew containers, and logout — a parallel auth state machine to the kiro-cli and Claude auth paths, enabling ChatGPT-subscription operators to run Codex-backend crews without an OpenAI API key.

## ADDED Requirements

### Requirement: Codex auth state machine

The Ghost Academy SHALL maintain a Codex auth state machine with exactly three states — unauthenticated, pending, and authenticated — determined by the presence and content of `DATA_DIR/ga-codex-auth`. Transitions are: unauthenticated → pending via `POST /login/codex`; pending → authenticated via `GET /login/codex` completing; authenticated → unauthenticated via `POST /logout/codex`. No other transitions are valid. This state machine is independent of the kiro and Claude auth state machines.

#### Scenario: POST /login/codex starts device flow when unauthenticated
- **WHEN** `POST /login/codex` is called and `ga-codex-auth` does not exist or is empty
- **THEN** the transport starts a Codex OAuth login flow, returns HTTP 200 with `{"login_url": "<url>", "code": "<code>"}` (or `{"login_url": "<url>"}` when the flow has no separate code), and stores the pending flow state

#### Scenario: POST /login/codex returns 409 when already authenticated
- **WHEN** `POST /login/codex` is called and `ga-codex-auth` exists and is non-empty
- **THEN** the transport returns HTTP 409 indicating Codex auth is already present and `POST /logout/codex` must be called first

#### Scenario: POST /login/codex returns 409 when flow already in progress
- **WHEN** `POST /login/codex` is called while a Codex login flow is already pending
- **THEN** the transport returns HTTP 409 indicating a flow is in progress and `GET /login/codex` should be polled

#### Scenario: POST /login/codex rejected when backend is not codex
- **WHEN** `POST /login/codex` is called and `GA_CREW_ACP_BACKEND != "codex"`
- **THEN** the transport returns an error indicating `GA_CREW_ACP_BACKEND` must be `"codex"` to use `POST /login/codex`; no login container is started

#### Scenario: GET /login/codex returns pending while user has not approved
- **WHEN** `GET /login/codex` is polled and the user has not yet completed the login
- **THEN** the transport returns HTTP 200 with `{"status": "pending", "login_url": "<url>"}`

#### Scenario: GET /login/codex completes and writes ga-codex-auth
- **WHEN** `GET /login/codex` is polled and the Codex login has completed inside the login container
- **THEN** the transport captures the resulting `~/.codex/` credential directory as a tar archive, writes it to `DATA_DIR/ga-codex-auth` with owner-only permissions, tears down the login container, and returns HTTP 200 with `{"status": "authenticated"}`

### Requirement: Codex login uses an ephemeral login container

The transport SHALL run the Codex login inside an ephemeral `ga-codex-login-<token>` container built from the spec-ops image (which carries the `codex-acp` adapter only when built with `INCLUDE_CODEX_AGENT=true`), so the login flow never runs on the host and its credential output can be captured from a known path.

#### Scenario: Login container requires the Codex-enabled image
- **WHEN** `POST /login/codex` is called and the spec-ops image was not built with `INCLUDE_CODEX_AGENT=true` (the Codex adapter is absent)
- **THEN** the transport returns an error naming `GA_INCLUDE_CODEX_AGENT=true` as the prerequisite; no persistent credential is written

#### Scenario: Login container is removed after the flow ends
- **WHEN** a Codex login flow completes, fails, or is abandoned
- **THEN** the `ga-codex-login-<token>` container is stopped and removed (best-effort), leaving no long-lived login container

### Requirement: Codex credential is injected into crew containers at launch

When `GA_CREW_ACP_BACKEND=codex` and `ga-codex-auth` is the active credential source, the transport SHALL inject the archived `~/.codex/` contents into the crew container's `/home/kirocrew/.codex/` at launch time, matching the path the `codex-acp` adapter reads for credentials.

#### Scenario: OAuth credential injected on launch
- **WHEN** a Codex-backend crew is launched, `GA_CREW_OPENAI_API_KEY` is unset, and `ga-codex-auth` exists and is non-empty
- **THEN** the transport untars `ga-codex-auth` into the crew container's `/home/kirocrew/.codex/` before the gateway starts

#### Scenario: API key takes precedence over OAuth credential
- **WHEN** a Codex-backend crew is launched and `GA_CREW_OPENAI_API_KEY` is set
- **THEN** the transport injects `OPENAI_API_KEY` as an env var and does not inject the `ga-codex-auth` archive

### Requirement: Codex logout clears the credential

`POST /logout/codex` SHALL remove `DATA_DIR/ga-codex-auth`, returning the Codex auth state machine to unauthenticated. Running crews are unaffected (their credential was already injected at launch).

#### Scenario: Logout removes the credential archive
- **WHEN** `POST /logout/codex` is called and `ga-codex-auth` exists
- **THEN** the transport deletes `ga-codex-auth` and returns HTTP 200; a subsequent `POST /login/codex` is accepted (state is unauthenticated)

#### Scenario: Logout is idempotent when already unauthenticated
- **WHEN** `POST /logout/codex` is called and `ga-codex-auth` does not exist
- **THEN** the transport returns HTTP 200 and the state remains unauthenticated
