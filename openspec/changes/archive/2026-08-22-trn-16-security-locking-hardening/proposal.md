## Why

Security and concurrency issues identified in the holistic code review
(docs/research/code-review.md), plus launch-blocking bugs discovered during
TRN-18 testing.

## What Changes

### Launch-blocking (priority — new crews cannot launch)

**`_bootstrap.p` crash during kirocrew token mint**

New crew launches fail because kirocrew's bootstrap process crashes during
`kirocrew token` (cookie minting). Root cause: `_inject_auth` uses
`container_exec` (not `container_exec_checked`) and checks for the string
`"injected"` in the output rather than the exit code. A failed auth injection
that happens to contain "injected" in its error message passes silently,
leaving the kiro-cli SQLite DB unseeded. When `kirocrew token` runs against
an uninitialised DB, it crashes.

Fix: replace `container_exec` with `container_exec_checked` in `_inject_auth`,
and check the exit code rather than matching strings.

### Security

**`admiral_secret` plaintext in `crews.json`**

The HMAC signing secret for Admiral mail and policy signing is stored plaintext
in the transport registry. Anyone with access to `DATA_DIR` or
`podman inspect ga-transport` can read it and forge standing orders or policies.
For single-user local deployments this is acceptable and documented in
`docs/auth.md` (TRN-15). For multi-operator deployments it is a real compromise
path.

Options: encrypt at rest, use a separate secrets file with tighter permissions,
or derive per-crew from a master secret held outside the registry.

### Concurrency

**`_reconcile_registry` holds registry lock for full restart sequence**

The startup reconciliation path holds the registry lock while waiting for each
crew gateway (up to 30 seconds per crew). This blocks all concurrent operations
during transport startup. The normal `_ensure_crew_running` path uses per-crew
events to minimise lock hold time; startup should be updated to match.

**`POST /login` TOCTOU**

The auth-file check and `_login_pending` check are two separate reads with the
lock not held across both. Two concurrent `POST /login` requests can both pass
both guards and each start a login container. Fix: hold the lock across the full
guard-and-set, set `_login_pending` as a placeholder inside the lock before
releasing.

## Decisions

- `_inject_auth` fix is the immediate priority — it blocks new crew launches.
- `admiral_secret` plaintext is acceptable for v1 single-user; address in a
  subsequent pass if multi-operator becomes a use case.
- `_reconcile_registry` locking improvement is a robustness improvement, not
  a correctness fix — lower priority than the launch-blocking bugs.

## Impact

- `transport/server.py` — `_inject_auth`, `_reconcile_registry`, login handler
- `transport/test_transport.py` — tests for fixed auth injection, startup lock
