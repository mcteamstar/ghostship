## Why

`transport/captain.py` contains logic that has no unit test coverage — helper
functions for order-template loading, placeholder substitution, mail formatting
with Ed25519 signing, mailbox counting, sentinel-file handling, and captain-job
utilities. Without tests these helpers are vulnerable to silent regressions
whenever captain or related modules are changed.

## What Changes

- Add `tests/unit/test_captain.py` — a new unittest-based test file covering
  the pure-Python helpers in `transport/captain.py`.
- No production code is modified; no APIs change.

## Capabilities

### New Capabilities

- `test-captain-helpers`: Unit tests for `transport/captain.py` pure helpers —
  template parsing, placeholder substitution, order-resolution, mail formatting
  and signing, mailbox counting utilities, sentinel-file parsing, job filtering,
  and the captain-order-lock factory.

### Modified Capabilities

*(none — no spec-level behaviour changes)*

## Impact

- New file: `tests/unit/test_captain.py`
- Uses existing `tests/fakes.FakePodmanClient` and `FakeArchiveResponse` (plus
  `_build_tar_with_file`) already present in the test suite.
- Requires the cryptography stub already installed in `conftest.py` for
  `_format_captain_mail` signing tests.
- No external dependencies added; no production files touched.
