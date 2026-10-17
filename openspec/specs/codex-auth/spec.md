# codex-auth Specification

## Purpose

Defines the Codex/OpenAI login flow, credential storage, injection into crew containers, and logout — a parallel auth state machine to the kiro-cli and Claude auth paths, enabling ChatGPT-subscription operators to run Codex-backend crews without an OpenAI API key.

## Requirements

### Requirement: Codex ChatGPT sign-in uses the device-code flow
`POST /login/codex/chatgpt` SHALL start a ChatGPT sign-in in an ephemeral login container by running Codex's device-code login (`codex login --device-auth`) and SHALL return the device URL and one-time code. `GET /login/codex` SHALL report `pending` until `~/.codex/auth.json` exists in the container, then store it as codex's active credential (method `chatgpt`), remove the container and report `complete`. The browser-redirect login SHALL NOT be used.

#### Scenario: Device code returned
- **WHEN** `POST /login/codex/chatgpt` is called with no codex flow pending
- **THEN** the response contains a `login_url` and a non-empty `code` taken from the device-code output

#### Scenario: Completion stores the ChatGPT credential
- **WHEN** the operator completes sign-in and `GET /login/codex` is polled
- **THEN** codex's active credential is the captured `auth.json`, tagged `chatgpt`, replacing any codex API key, and the login container is gone

#### Scenario: Device code login not enabled on the account
- **WHEN** Codex reports that device code login is unavailable for the account or workspace
- **THEN** the flow fails with an error telling the operator to enable device code login in ChatGPT security settings (or ask a workspace admin), and no credential is stored

#### Scenario: Flow already pending
- **WHEN** `POST /login/codex/chatgpt` is called while a codex flow is pending
- **THEN** the transport returns HTTP 409

#### Scenario: Abandoned flow expires
- **WHEN** a codex flow is not completed within its expiry window
- **THEN** the pending state is cleared and the login container removed without any client polling
