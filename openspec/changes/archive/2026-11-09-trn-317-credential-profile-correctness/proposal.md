# Proposal

## Why

The launch response omits the selected `acp_profile`, causing an existing end-to-end assertion to fail. Review also found that named OAuth profiles resolve to a shared legacy archive during injection and that login can report success after a profile-store write fails.

## What Changes

- Return the resolved profile in successful crew launch responses.
- Isolate OAuth credential capture, storage, injection and refresh by backend and profile, retaining supported legacy default-profile migration.
- Make credential persistence failures observable and retryable without falsely reporting a successful login or silently selecting another profile.
- Add targeted unit, integration and end-to-end coverage without using real credentials.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth/credential-profiles`: profile selection, OAuth isolation, persistence failure semantics and launch response contract.

## Impact

Credential store and login flows, crew launch and credential injection, migration paths, API response documentation and tests. Existing logged-in credentials and default-profile users require careful compatibility handling.
