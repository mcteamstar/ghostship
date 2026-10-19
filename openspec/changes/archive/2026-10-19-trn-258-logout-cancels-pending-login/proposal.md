# Proposal

## Why

`ghostship auth logout <backend>` (`POST /logout/{backend}`) is meant to be the one way to both log out and abort a login. Today it does neither reliably.

The TRN-233 routes delete the credential-store entry and then delegate to the pre-TRN-233 handlers. Those handlers still gate on the *legacy* auth files:

- **kiro:** returns `404 Not authenticated.` unless `ga-kiro-auth` exists. A pending device login is never cancelled when you aren't logged in, and a new login is refused with 409 because the old one is still pending. An `api-key` credential (store-only) is deleted, but the response is still 404.
- **claude:** returns `409` unless `ga-claude-auth` exists, so `setup-token`/`api-key` logouts fail the same way, and a pending authorisation-code flow is not cancelled.
- **codex:** returns `200` early when `ga-codex-auth` is absent, without cancelling a pending flow.

An aborted `ghostship auth login kiro` therefore leaves its pending flow and login container behind until the 15-minute TTL *and* a later cleanup sweep. Restarting the transport is the only way to clear it.

Logout also reaches into running crews to delete device-flow logins (kiro's `auth_kv`, claude's `~/.claude/`, codex's `~/.codex/`). It can't do the same for credentials delivered as environment variables (`api-key`, claude `setup-token`), so the behaviour is inconsistent, and it interrupts work in crews that are already running. Logout should act on the transport only: crews that are already running keep the credential they launched with.

## What Changes

- One operation, one end state: `ghostship auth logout <kiro|claude|codex>` is how you log out *and* how you abort a login. Afterwards the transport holds no credential for that backend and no login is pending, whatever the starting state. No new routes or HTTP methods are added.
- `POST /logout/{backend}` SHALL always cancel any pending login flow first, removing its login container. It then removes the stored credential (credential store and legacy auth file, whichever exist).
- It SHALL return `200` `{"status": "logged_out"}` in every non-error case, with `aborted_pending_login: true` when a flow was cancelled. There are no more `404`/`409` "not authenticated" responses. It fails (500) when a credential could not be removed, or when the container runtime is unavailable so a pending login cannot be cancelled (the credential is still removed).
- **BREAKING:** logout SHALL NOT touch running crews. Device-flow logins are no longer deleted from running crews (kiro `auth_kv`, claude `~/.claude/`, codex `~/.codex/`). A running crew keeps its launch-time credential until it is relaunched or nuked. A completed kiro device login is still injected into running crews, but only into kiro crews: since TRN-259 a transport can run claude and codex crews alongside kiro ones, and those are left alone.
- Race fixes, so the end state actually holds:
  - Logging out while a login container is still being created no longer leaves an orphaned container.
  - A login that a poll was completing when logout cancelled it cannot store its credential afterwards.
- A failed credential-store delete is reported as an error instead of being treated as "nothing stored".
- The 409 "already authenticated" and "login already in progress" responses from all three login POST routes now direct the user to `ghostship auth logout <backend>` instead of the raw `POST /logout/{backend}` REST route.
- Out of scope: the CLI calling logout automatically on Ctrl-C. Aborting a re-login through logout also removes the credential being replaced; that follows from the single end state and is accepted.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `backend-credentials`: "Credentials cleared per backend" becomes transport-only (cancel first, idempotent 200, error only on failed removal, race guarantees). "Credentials resolved at each crew launch" drops the "logout clears it from them" exception.
- `crew-auth`: "Kiro auth state machine" is replaced by "Kiro auth state transitions". It is identical except that the "auth cleared from all running crews on logout" scenario becomes "logout leaves running crews untouched", logout from pending is stated explicitly, and login completion injects only into running kiro crews.
- `claude-auth`: "Claude authorisation-code flow state machine" is replaced by "Claude authorisation-code flow states". It is identical except that the "clearing claude wipes running crews" scenario becomes "logout leaves running claude crews untouched".

## Impact

- **Code:** `transport/login.py`:
  - The three logout routes and the legacy handlers they delegate to (`_handle_logout_post`, `_handle_claude_logout_post`, `_handle_codex_logout_post`, also imported in `server.py`).
  - `LoginFlow.initiate()` (orphan fix) and the three completion paths (cancelled-flow guard).
  - The kiro `GET /login/kiro` completion's running-crew injection, filtered to crews whose `acp_backend` is `kiro`.
  - `transport/credentials.py` `CredentialStore.delete()` (distinguish "absent" from "failed").
  - `transport/container_scripts/wipe_auth.py` becomes unused and is removed.
- **Tests:** `tests/unit/test_credentials_routes.py` logout cases, plus new unit tests for the races.
- **Docs:** `docs/auth.md` logout sections; CHANGELOG.
- **Operators:** after `ghostship auth logout <backend>`, running crews keep working on their existing credential; relaunch or nuke them to drop it. Callers that relied on `404`/`409` meaning "not logged in" now get `200`; `GET /login/{backend}` remains the status API.
