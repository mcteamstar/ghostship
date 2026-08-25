## Why

When `launch` is called without authentication, the handler already writes a `{status: "launching"}` placeholder into the crew registry before it checks for the auth file. This leaves an orphaned registry entry that can only be cleared with a `nuke` — a disruptive operation that destroys a workspace. Separately, the caller receives a bare `not_authenticated` error with no actionable next step, forcing a manual round-trip through `POST /login` before they can retry. TRN-58 fixes both problems in one pass: move the auth guard to the very top of `launch`, and when it fires, automatically start the device auth flow and return the `login_url` and `device_code` inline so the caller can complete auth without a separate API call.

## What Changes

- The auth check is moved to the very top of the `launch` MCP tool, before the registry placeholder write and before any Podman operations.
- When auth is absent, `launch` automatically calls the `POST /login` logic (via a new shared `_initiate_login()` helper) to initiate device auth.
- The error response from `launch` is enriched: when `not_authenticated`, it includes `login_url` and `code` so the caller can open the browser and complete auth immediately.
- After auth completes (`GET /login` returns `status: "complete"`), the caller retries `launch` normally — no other workflow changes.
- The `crew-lifecycle` spec gains a new requirement covering the pre-registry auth gate and the inline login-initiation behaviour.
- The `crew-login` spec gains a scenario covering the login flow being triggered from within `launch`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: New requirement — the auth check must precede the registry write; if auth is absent, `launch` initiates the device auth flow and returns `login_url` and `code` in the error response.
- `crew-login`: New scenario — `POST /login` equivalent invoked from within `launch`; the 409 "already in progress" guard still applies; `launch` surfaces the same `login_url` and `code` fields.

## Impact

- **`transport/server.py`**: `launch()` — move `_read_auth_file()` check above the `_registry_lock` block; extract `_initiate_login()` helper from `_handle_login_post` and call it from `launch`.
- **Auth error response shape**: adds `login_url` (string) and `code` (string | null) fields alongside `error: "not_authenticated"`.
- **Caller workflow**: callers that previously handled `not_authenticated` by separately calling `POST /login` should now read those fields from the `launch` error response directly.
- No breaking changes to authenticated callers — the `launch` happy path is unchanged.
- No changes to `POST /login`, `GET /login`, or `POST /logout` endpoints themselves.
