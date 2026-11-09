# Design

## Context

`_store` in `transport/login.py` writes the profile envelope and then calls `_propagate_oauth` (and the Kiro equivalent) inside `commit_if_current`, under `_credential_transaction_lock`, from an async handler. Any injection exception surfaces as a 500 "credential could not be saved" and leaves the pending flow open. `ensure_running` in `transport/launcher.py` calls `_validate_static_credential` before its healthy early return, so every hot-path call on a running crew inspects the container and fails after a rotation.

## Goals / Non-Goals

**Goals:**
- Login outcome depends only on durable storage.
- Running crews are not affected by credential rotation.

**Non-Goals:**
- Live rotation of static credentials into running containers (environment cannot change in place).
- Changing which crews propagation targets; backend and profile filtering from TRN-317 stays.

## Decisions

- **Commit, then propagate outside the transaction.** `commit_if_current` covers only the store write and pending-flow completion. Propagation runs afterwards via `asyncio.to_thread`, iterates matching running crews, catches per-crew exceptions and logs them with crew id. Alternative considered: keep propagation inside the lock but swallow errors. Rejected because it still blocks the event loop and every other login for the duration of N Podman calls.
- **Accept a narrow ordering window.** Without the lock, a logout racing a just-committed login could in theory propagate a credential that has just been deleted. Propagation re-reads the store per crew and skips injection when the profile is no longer present, which closes the practical window.
- **Validate only on the start path.** Move the `_validate_static_credential` call inside the leader branch that starts a stopped container. The healthy early return no longer inspects the container. Alternative considered: exempt only evac. Rejected because the operating rule is to leave running crews alone, and a partial exemption keeps the hot-path inspect cost.

## Risks / Trade-offs

- [A running crew keeps using a revoked key until it idles out] → Documented behaviour; operators relaunch to adopt a new key, as before. Idle-stop then wake applies validation.
- [Per-crew propagation failures become quieter] → Each failure is logged at warning with crew id and profile, and the login response includes a list of crews that did not receive the credential.
