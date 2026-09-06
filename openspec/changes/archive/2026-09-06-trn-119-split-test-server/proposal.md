## Why

`tests/unit/test_server.py` is 6217 lines — larger than the module it tests after TRN-116 extracted auth, caddy, and monitors into their own modules. The test file will keep growing as new features land and has become difficult to navigate.

## What Changes

- Split `tests/unit/test_server.py` into four focused test files matching the new module structure from TRN-116:
  - `tests/unit/test_auth.py` — `BearerAuthMiddleware`, security hardening, and auth wiring test classes from `test_server.py` (rate limiting and transport secret tests already have their own files)
  - `tests/unit/test_caddy.py` — Caddy admin API and dashboard port test classes; consolidates with existing `tests/unit/test_trn92_caddy.py`
  - `tests/unit/test_monitors.py` — schedule and idle monitor test classes
  - `tests/unit/test_server.py` — remaining routing, handler, and proxy test classes
- Delete `tests/unit/test_trn92_caddy.py` after merging its content into the new `test_caddy.py`
- No mock path changes needed — TRN-116 already updated all mock paths to point at the new module locations
- No behaviour changes — all 698+ tests must pass after the split

## Capabilities

### New Capabilities

_None — pure test reorganisation._

### Modified Capabilities

_None — no spec-level behaviour changes._

## Impact

- `tests/unit/test_server.py` — reduced; remaining server routing/handler/proxy tests only
- `tests/unit/test_auth.py` — new file
- `tests/unit/test_caddy.py` — new file (absorbs `test_trn92_caddy.py`)
- `tests/unit/test_monitors.py` — new file
- `tests/unit/test_trn92_caddy.py` — deleted
- `tests/run.sh` — verify it discovers all test files (uses a glob pattern; should pick up new files automatically)
- No transport code changes, no API changes, no container image changes
