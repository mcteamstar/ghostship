# Proposal

**Plane ticket:** TRN-247

## Why

`transport/caddy.py` has zero unit-test coverage. The module owns three
behaviorally distinct areas — UI port pool allocation, Caddy admin-API
crew (de)registration (including reverse-proxy configuration generation and
virtual-host management), and TLS-related configuration handling — all of which
are reachable without a live Caddy or Podman process and can be exercised with
the same stub-injection pattern already used by the existing unit suite.
Adding coverage here prevents regressions on the port-exhaustion guard,
the forward-auth / WebSocket routing split, and the exponential-backoff retry
logic the first time any of those paths are touched.

## What Changes

- Add `tests/unit/test_caddy.py` — new unit test file covering `caddy.py`
- Three test groups:
  1. **Port pool** (`CaddyPortal.allocate_port` / `release_port` and the
     module-level thin wrappers `_allocate_dashboard_port` /
     `_release_dashboard_port`): allocation scan, wrap-around exhaustion,
     release-then-reallocate, idempotent release of absent port.
  2. **Reverse proxy / virtual-host management** (`CaddyPortal.register_crew` /
     `deregister_crew` and thin wrappers `_caddy_register_crew` /
     `_caddy_deregister_crew`): happy-path PUT 200/201, idempotent 409, retry
     on transient failure then success, exhausted retries (no raise), DELETE
     200/204, graceful 404 deregister, deregister failure (no raise).
     Assertions cover the JSON body structure (routes, WebSocket route before
     HTTP catch-all, forward-auth handler presence/absence based on api_key,
     rewrite URI, transport-token header injection).
  3. **TLS / config handling** (`_validate_caddy_tls_mode` via `Config`,
     `_caddy_admin_url` return value, `CaddyPortal` constructor field wiring):
     confirms admin URL is hard-coded to `http://ga-portal:2019`, constructor
     stores fields correctly, and TLS mode validation (already tested in
     `test_config.py`) is not duplicated.
- No new dependencies — uses `unittest.mock.patch` / `unittest.Mock` and the
  `httpx2` stub already installed by `conftest.py`.

## Capabilities

### New Capabilities

- `transport-test-coverage/caddy`: Unit tests for `transport/caddy.py` covering
  port pool management, reverse proxy configuration generation, virtual host
  registration/deregistration, and retry/error handling.

### Modified Capabilities

*(none — no spec-level behaviour changes to existing capabilities)*

## Impact

- `tests/unit/test_caddy.py` — new file (~350–450 lines)
- No changes to `transport/caddy.py` or any other production file
- Runs under the existing `pytest tests/unit/` invocation; no new test
  infrastructure needed
