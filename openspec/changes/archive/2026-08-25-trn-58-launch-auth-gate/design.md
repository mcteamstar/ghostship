## Context

`launch()` in `transport/server.py` currently writes a `{status: "launching"}` registry placeholder *before* checking for auth. If auth is absent the function returns `not_authenticated` but the placeholder is already in the registry — the caller must `nuke` the crew to clear it. Additionally, the error gives no actionable next step; the caller must separately call `POST /login`.

## Goals / Non-Goals

**Goals:**
- Move the auth check to before the registry write so a failed auth gate leaves no orphan
- On auth failure, automatically start the device auth flow and return `login_url` + `code` inline
- Handle the already-pending case cleanly

**Non-Goals:**
- Changing `POST /login`, `GET /login`, or `POST /logout` endpoints themselves
- Changing the happy path (authenticated callers see no difference)

## Decisions

**Extract `_initiate_login(podman)`:** `_handle_login_post` is an async HTTP handler — it can't be called directly from the sync `launch()` function. Extract the core login-start logic into a new sync helper `_initiate_login(podman) -> dict` that returns `{"login_url": ..., "code": ..., "login_pending": False}` on success or `{"login_pending": True}` if a flow is already in progress. `_handle_login_post` calls this helper and wraps the result into a `JSONResponse`. `launch()` calls the same helper directly.

**Move auth check above `_registry_lock` block:** The current sequence is: validate crew_id → resolve composition → get podman → acquire registry lock → write placeholder → **auth check**. The new sequence is: validate crew_id → resolve composition → **auth check (no lock, no registry write)** → get podman → acquire registry lock → write placeholder → continue. The auth file read is cheap and doesn't need the registry lock.

**Error response shape from `launch`:** On auth failure:
```json
{
  "error": "not_authenticated",
  "login_url": "https://...",
  "code": "XXXX-XXXX",
  "instructions": "Open login_url to authenticate, then call launch again."
}
```
When a flow is already pending:
```json
{
  "error": "not_authenticated",
  "login_pending": true,
  "instructions": "Login already in progress. Poll GET /login, then call launch again."
}
```

**`_initiate_login` needs `podman`:** Starting the login container requires a `PodmanClient`. Since `launch()` already calls `_get_podman()`, pass the client into `_initiate_login`. If `_get_podman()` itself fails before the auth check, return that error (same as before — podman unavailability is a different failure).

## Risks / Trade-offs

**[Risk] `_initiate_login` starts a real container:** If the caller calls `launch` repeatedly without auth, each call would start a new login container — but `_login_pending_lock` guards against concurrent flows, so repeated calls before the first flow completes return `login_pending: true` without starting a second container. No risk of runaway containers.

**[Risk] Timing between auth check and registry write:** The auth check is now outside the registry lock, so in theory auth could be revoked between the check and the registry write. This is acceptable — auth revocation is an operator action and is not expected to race with `launch`. The guard can be tightened in a follow-up if needed.
