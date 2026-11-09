# Tasks

## 1. Launch response and profile audit

- [x] 1.1 Add the resolved `acp_profile` to every successful launch response and update its API documentation; verify explicit, sole-profile and default resolution match the crew registry.
- [x] 1.2 Trace all backend-specific login, launch, injection, propagation, restart, refresh and logout paths, including legacy storage and API-key flows; document concrete findings and verify affected call sites are covered by the tasks below.

## 2. Profile-safe OAuth handling

- [x] 2.1 Inject the selected Codex and Claude OAuth profile payload instead of a shared archive and fail clearly for missing or malformed named payloads; verify two distinct synthetic profiles and existing default-profile compatibility without leaking secrets.
- [x] 2.2 Restrict legacy default migration or fallback to the implicit default without overwriting newer profile credentials; verify idempotence, corrupt and partial writes, and preservation of named profiles. Upgrades are forward-only.
- [x] 2.3 Make OAuth completion report success only after the selected profile is durably stored and retain safe retry or recovery on failure; verify injected write errors, retry, cancellation and concurrent login/logout for Kiro, Claude and Codex as applicable.
- [x] 2.4 Scope reauthentication, credential propagation, restart and refresh to matching backend/profile crews; verify one profile's rotation and logout leave other profiles and crews unchanged, including existing API-key and setup-token paths.

## 3. Integration and verification

- [x] 3.1 Run focused credential, login, launcher and profile tests with synthetic payloads and verify logs and responses contain no credential values.
- [x] 3.2 Run the existing E2E launch response test on Corsair and exercise two-profile selection with a non-production fixture in an isolated transport; record test outcomes and any deployment requirements.
