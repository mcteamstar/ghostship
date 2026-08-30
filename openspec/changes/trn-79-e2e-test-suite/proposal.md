## Why

The automated test suite (unit + integration) never talks to a real transport instance — all coverage is mocked or simulated locally. The only end-to-end verification that currently exists is the manual smoke test (launch → dispatch → pickup → nuke) run by hand before releases. Automating that coverage gives a repeatable regression signal against a live transport and catches issues that mocks cannot — container lifecycle, auth injection, presigned URL flow, actual Podman interactions.

## What Changes

- Implement `tests/e2e/test_transport_e2e.py` replacing the existing placeholder
- Tests skip gracefully when `GHOSTSHIP_E2E_URL` is unset — safe to run in CI without a transport
- Six test cases covering the live transport surface:
  - Health check — `GET /health` and `GET /version` return expected shapes
  - Crew lifecycle — launch, verify in `crews()`, nuke, verify gone
  - Dispatch + pickup — dispatch a trivial task, poll until done, verify result
  - Supply + evac round-trip — upload a file via presigned URL, download back, verify content
  - Auth gate — when `GA_API_KEY` is set, unauthenticated requests are rejected
  - Version check — transport reports the correct version (confirms config was loaded)
- Each test is fully independent — creates its own crew, nukes on teardown
- Suite completes in under 5 minutes total with appropriate timeouts
- `tests/run.sh --e2e` already wired; no run.sh changes needed

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — adds tests only. No production code changes.

## Impact

- `tests/e2e/test_transport_e2e.py` — replaces placeholder with real tests
- `tests/e2e/test_placeholder.py` — removed (replaced by the above)
- No changes to `transport/`, `install.sh`, or any docs
