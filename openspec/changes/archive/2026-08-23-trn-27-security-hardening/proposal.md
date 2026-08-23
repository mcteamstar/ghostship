# Proposal: trn-27-security-hardening

## Why

Two security issues surfaced in the post-0.3.x code review:

1. **GA_API_KEY plain env var** — the API key is passed as `-e GA_API_KEY=...` to the transport container and is visible via `podman inspect` and `/proc/<pid>/environ` inside the container. Any process that can run `podman inspect` on the host or read the transport's `/proc` environ has the key.

2. **Login TOCTOU write-side sentinel missing** — TRN-16 closed the read-side race in `_handle_login_post` (both guards now checked atomically), but the write-side sentinel is still absent. The lock is released ~130 lines before `_login_pending` is set, leaving a window where a second concurrent `POST /login` passes both guards and starts a second login container. A related narrower race in `_handle_login_get`: the final `_login_pending = None` can clobber a newly-started concurrent login that arrived between the nuke and the clear.

## What Changes

- Migrate `GA_API_KEY` to a Podman secret: `podman secret create` in `install.sh`, `--secret` flag in the transport container invocation, read via `/run/secrets/GA_API_KEY` inside the container
- Set `_login_pending` sentinel while still holding `_login_pending_lock` immediately after the guard checks pass, before releasing the lock
- Guard `_handle_login_get`'s `_login_pending = None` clear against concurrent login: verify the container name matches before clearing
- Update `docs/auth.md` and `docs/configuration.md` to document the secrets-based API key approach

## Capabilities

### Modified Capabilities

- `crew-login` — Login TOCTOU sentinel fix: `_login_pending` set atomically while lock is held; `_handle_login_get` clear guarded against concurrent start

## Impact

- `install.sh` — API key creation via `podman secret create`, transport container invocation updated
- `transport/server.py` — `_handle_login_post` sentinel write, `_handle_login_get` clear guard
- `docs/auth.md`, `docs/configuration.md` — secrets-based API key documentation
