# Proposal

## Why

The credential store enforces exactly one active credential per backend (kiro,
claude, codex). There is no way to hold a personal kiro credential alongside a
corporate one simultaneously — every context switch requires logout and re-login.
TRN-252 adds named `profile` support as a sub-namespace under each backend so
multiple credentials can coexist and the right one is selected at launch time.

## What Changes

- `CredentialStore` gains a `profile` dimension; credentials are stored at
  `credentials/<backend>/<profile>.json` instead of `credentials/<backend>.json`.
- `CredentialStore.get`, `put`, and `delete` accept an optional `profile` parameter
  (default: `"default"`).
- New `CredentialStore.list_profiles(backend)` returns profile names for a backend.
- New `CredentialStore.status_all()` returns a two-level map: `{backend → {profile → status}}`.
- **Backward compatibility**: existing flat `credentials/<backend>.json` files are
  migrated to `credentials/<backend>/default.json` on first access — no manual step
  required; the old path is never written again.
- `launch` gains an optional `profile` param. If omitted and only one profile exists
  for the backend, it is selected implicitly; otherwise `"default"` is used.
- Crew registry entries gain an `acp_profile` field alongside `acp_backend`.
- Post-login auth injection is filtered by `acp_profile` so only crews launched with
  the matching profile receive fresh credentials.
- `ghostship auth login <backend> --profile <name>` stores under a named profile.
- `ghostship auth status` lists all profiles per backend grouped by backend.
- `ghostship auth logout <backend> --profile <name>` targets a specific named profile.
- HTTP login/logout routes accept `profile` in the request body (POST) or as a query
  parameter (GET/POST logout), defaulting to `"default"` when absent.
- New route `GET /login/<backend>/profiles` lists all stored profile names for a backend.

## Capabilities

### New Capabilities

- `auth/credential-profiles`: Named per-backend credential profiles — storage schema,
  store API, migration, HTTP auth routes, and `ghostship auth` CLI surface.
- `launch/profile-selection`: Profile-aware crew launch — selecting the right credential
  profile at `launch` time, recording `acp_profile` in the crew registry, and filtering
  post-login auth injection by profile.

### Modified Capabilities

<!-- No existing specs exist; both capabilities above are new. -->

## Impact

- **`transport/credentials.py`**: `CredentialStore` — schema, all public methods, new
  helper methods.
- **`transport/login.py`**: All login/logout HTTP handlers (profile param); login flow
  singletons (profile in pending dict); `_logout` shared function.
- **`transport/tools.py`**: `launch` function (new `profile` param, credential
  resolution, registry write).
- **`transport/server.py`**: Route table — add `GET /login/{backend}/profiles` for each
  backend.
- **`ghostship`** CLI binary: `auth_login`, `auth_logout`, `auth_status` functions; help
  text.
- **Registry entries**: new `acp_profile` field; `crews()` and internal fleet payload
  expose it.
- **No external dependencies added.**
