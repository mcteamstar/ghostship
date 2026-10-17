# Spec Delta

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Codex auth state machine
**Reason**: Replaced by "Codex ChatGPT sign-in uses the device-code flow" and backend-credentials; state now comes from the credential store.
**Migration**: Run `ghostship auth login codex`. Credential state is reported by `GET /login/codex` (backend-credentials).

### Requirement: Codex login uses an ephemeral login container
**Reason**: Replaced by "Codex ChatGPT sign-in uses the device-code flow", which runs `codex login --device-auth` instead of `codex-acp login`.
**Migration**: None.

### Requirement: Abandoned Codex login flows expire without polling
**Reason**: Folded into "Codex ChatGPT sign-in uses the device-code flow" ("Abandoned flow expires").
**Migration**: None.

### Requirement: Codex credential is injected into crew containers at launch
**Reason**: Superseded by backend-credentials "Credential delivered to crews according to its method" (`OPENAI_API_KEY` for `api-key`, `~/.codex/auth.json` for `chatgpt`).
**Migration**: None (breaking). Existing `ga-codex-auth` archives are ignored; log in again with `ghostship auth login codex`.

### Requirement: Codex logout clears the credential
**Reason**: Superseded by backend-credentials "Credentials cleared per backend".
**Migration**: None; `POST /logout/codex` keeps its path and now follows the shared logout behaviour.
