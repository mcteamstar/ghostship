# Proposal

## Why

Independent review of the v0.10.0 release (indy-review crew, 2026-10-30) identified
three security hardening items that do not block the current release but should be
addressed in the next sprint.

## What Changes

### H-5 — No brute-force lockout on MCP bearer token auth

`BearerAuthMiddleware` in `transport/auth.py` performs a constant-time comparison
of the provided bearer token against `GA_API_KEY`, but applies no rate limiting
or lockout on repeated failures. An attacker can make unlimited attempts against
the bearer endpoint.

`FailureThrottle` already exists in `security.py` and is wired to the dashboard
login (`/dashboard/login`). Wire it to bearer auth too — after N failures from
a source IP within a window, return 429 instead of 401.

### H-3 — Batch task status lost on transport restart

`_dispatch_batch` in `lifecycle.py` writes the batch record to disk
(`_write_batch`) atomically at dispatch time, but per-task status updates are
maintained in-memory. If the transport restarts while a batch is in flight,
individual task statuses are lost and the batch cannot be correctly reconstituted
from the registry.

Fix: write each task's status update to the batch record on disk as it completes,
so a restart can reconstruct accurate task-level status.

### H-2 — `install.sh` eval injection — document the assumption

`bin/install.sh` uses `eval "$_RESOLVED"` on the output of `yaml_config.py`.
The helper emits shell-quoted `KEY=value` pairs derived from a controlled YAML
schema, so exploitation requires an attacker to have write access to
`ghostship.yaml` — at which point they already own the installation. The risk
is theoretical but worth documenting explicitly in a comment, and a future
refactor should replace `eval` with explicit `export VAR=value` lines.

## Capabilities

### Modified Capabilities

- `transport/auth`: add requirement that bearer token auth must apply rate
  limiting after repeated failures.
- `transport/batch-dispatch`: add requirement that per-task status must be
  durable across transport restarts.

## Impact

- `transport/auth.py` — wire `FailureThrottle` to `BearerAuthMiddleware`
- `transport/lifecycle.py` — write per-task status to disk in `_dispatch_batch`
- `bin/install.sh` — add comment documenting the eval trust assumption
