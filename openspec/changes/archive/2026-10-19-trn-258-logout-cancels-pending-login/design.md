# Design

## Context

See proposal.md for why. Current shape:

- **Routes** (`transport/login.py`): `_handle_logout_kiro_post`, `_handle_logout_claude_post_new` and `_handle_logout_codex_post_new` call `_cred_store.delete(backend)`, then delegate to the pre-TRN-233 handlers. Those handlers start with a legacy-file guard (404 / 409 / early 200), then delete the legacy file, audit, wipe running crews (kiro `wipe_auth.py` on `auth_kv`, claude `rm -rf ~/.claude/`, codex `~/.codex/`), and call the `_abort_*_pending_login(podman)` helper last.
- **Abort helpers** (`LoginFlow.abort`, wrapped by `lifecycle._abort_*_pending_login`) are safe whether or not a flow is pending. They read `_pending` under the flow lock, remove its container, then clear `_pending` only if it is still the same dict.
- **`LoginFlow.initiate`** sets `_pending = {"container": None, "state": "starting"}` under the lock, starts the container *outside* the lock, then records the container only `if self._pending is not None`. If an abort lands in that window, the container is created but never recorded or removed.
- **Completion paths** read `_pending`, poll the login container, then store the credential with no check that the flow is still current. There are four: `_handle_login_get` (kiro), the claude and codex `GET /login/{backend}` handlers, and the launch-time poll in `tools.py` (~L661).
- **Kiro completion injection** (`_handle_login_get`, `login.py` ~L973) injects the fresh auth into every running crew regardless of `acp_backend`. Since TRN-259 a transport can run claude and codex crews alongside kiro ones. The claude and codex paths already filter on `acp_backend` (`login.py` ~L1229, ~L1401).
- **`CredentialStore.delete`** returns `False` for both "not found" and `OSError`.
- **Launch** resolves kiro auth only from the credential store or the pending login container (`tools.py`, "TRN-233: the credential store is the sole source of truth"). It never reads running crews.

## Goals / Non-Goals

**Goals:**
- After `POST /logout/{backend}` returns 200, that backend has no stored credential and no pending flow, whatever the starting state and whatever was running concurrently.
- Logout never touches running crews.

**Non-Goals:**
- A cancel-only operation, a new HTTP method, or CLI Ctrl-C handling.
- Changing *what* a completed kiro device login injects into running crews. Only *which* crews receive it changes (Decision 6).
- Cleaning up other stale legacy wording in `crew-auth` (references to the `ga-kiro-auth` file); only the running-crew fallback scenario is removed, because it contradicts transport-only logout.

## Decisions

### 1. One logout routine, parameterised per backend
`_logout(backend, request)` with a small per-backend table: abort helper, legacy auth-file path, audit account. Steps:

1. `aborted = abort_helper(podman)`, first. If the container runtime cannot be reached (`_get_podman` raises), record the error and carry on: no login poll can run without it either, so removal is still safe.
2. `store_removed = _cred_store.delete(backend)`; `legacy_removed = unlink(legacy_path)` if present.
3. If either removal *failed*: audit `logout failure`, return 500 `{"status": "error", "error": "The stored credential could not be deleted."}`.
4. If anything was removed: audit `logout success`.
5. If step 1 failed: return 500 `{"status": "error", "error": "The stored credential was removed, but a pending login could not be cancelled."}`.
6. Return 200 `{"status": "logged_out"}`, plus `aborted_pending_login: true` when `aborted`.

*Why not return early on a missing runtime:* the stored credential is the thing a user most needs gone, and the old kiro route removed it before touching podman. The 500 in step 5 is kept so the CLI does not report a clean logout while a login container may still be running.

The three routes call `_logout`. The legacy handlers and the per-backend crew-wipe code are deleted, and so is `transport/container_scripts/wipe_auth.py`, whose only caller was the kiro wipe. `wipe_failed` disappears from the response.

*Why abort first:* the pending flow is independent of stored state, and step 2 must run after it for the race argument in Decision 4.

### 2. `CredentialStore.delete` distinguishes absent from failed
Return `True` (removed) or `False` (absent), and raise on `OSError`. `_logout` catches that error and treats it as the failure case in step 3. Other callers (if any) are checked for the new exception during implementation.

### 3. `initiate()` cleans up a container it can't record
After starting the container, under the lock: if `self._pending` is not the dict this call created, the flow was cancelled while starting. Remove the container (best effort), and return `{"error": "cancelled"}` so the caller reports the cancellation rather than a login URL. Compare by identity, not `is not None`, so a *new* flow started in between isn't confused with this one.

The same identity check applies to the PTY URL read that follows. If the flow was cancelled while waiting for a URL, return `{"error": "cancelled"}` (closing the PTY socket and removing the container) and do not hand out a URL. The failure paths clear `_pending` only if it is still this call's dict, so a failed read cannot clear a flow started after the cancel.

### 4. Completion commits only for the current flow
Each completion path captures the `pending` dict it polled. It then takes the flow's lock and checks `flow._pending is pending`. If that holds, it stores the credential and clears `_pending` inside the same critical section. If it doesn't, it discards the result, removes the container, and returns `{"status": "cancelled"}` (or the launch path's `not_authenticated`). Add a `LoginFlow.commit_if_current(pending, store_fn)` helper so the four paths share it.

This guarantees the end state with logout's ordering (abort, then delete):

- **Completion commits before abort's check:** logout's delete in step 2 removes the credential.
- **Completion commits between abort's check and its clear:** abort's identity check sees `_pending` already cleared and skips; logout's delete still runs afterwards.
- **Abort clears first:** completion fails the identity check and discards.

### 5. Running crews are out of logout's reach
No exec, restart or stop of any crew. The "logout takes effect at the next launch" guarantee rests on launch reading only the credential store (true today). The spec now forbids the running-crew fallback so it can't come back.

### 6. Kiro completion injects only into kiro crews
The kiro completion's running-crew loop keeps only crews where `info.get("acp_backend", "kiro") == "kiro"`. Treating an absent field as kiro matches `Crew.from_dict`'s default, so registry entries from before the field existed are still injected. Injection runs only after `commit_if_current` succeeds, so a cancelled flow injects nothing.

*Why here:* this change already rewrites the requirement that describes the injection; restating it as "every running crew" would write the pre-TRN-259 behaviour into the spec.

## Risks / Trade-offs

- [Running crews keep a credential after logout, including a revoked or unwanted one] → Intended ("those ships have sailed"). Docs say to relaunch or nuke a crew to drop its credential.
- [Callers relied on 404/409 for "not logged in", or on `wipe_failed`] → `GET /login/{backend}` is the status API. The CLI treats only non-2xx as an error, so it's unaffected.
- [Holding the flow lock while storing the credential] → The store write is a small local file write; the container poll stays outside the lock.

## Migration Plan

Transport-only: `ghostship upgrade` recreates `ga-transport`. No data or config migration. Rollback is a reinstall of the previous version.
