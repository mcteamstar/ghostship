## Why

Three production bugs found by stevemac007 during migration assessment work cause auth false-positives, silent crew idle-stop failures, and broken API proxy calls. All three affect core flows and are straightforward to fix.

## What Changes

- `_read_auth_from_crew`: validate that fetched `auth_kv` rows contain an actual token/credential before treating login as complete — not just that rows exist
- `_idle_monitor`: extend the `401` cookie-refresh branch to also handle `403`, preventing fail-open behaviour when the gateway returns a CSRF mismatch
- `_handle_crew_api_proxy`: strip `cookie` (case-insensitive) from forwarded headers before injecting the session cookie, the same way `host` is already stripped
- Regression tests for each of the three fixes

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: auth read now requires a token/credential row, not merely any row in `auth_kv`; idle monitor now handles 403 as a recoverable error rather than fail-open

## Impact

- `transport/server.py` — three targeted changes, no interface or behaviour changes for callers
- `tests/unit/test_transport.py` — new test cases for each fix
