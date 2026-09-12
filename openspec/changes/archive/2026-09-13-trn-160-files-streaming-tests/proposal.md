# TRN-160: Add tests for files.py streaming transfer error paths

## Why

`_ResponseChunkReader`, `_TarMemberStream`, and the `_transfer_upload` slash-ref workaround in `transport/files.py` have zero test coverage. A regression in any of these paths silently corrupts supply/evac file transfers — the caller receives a partial or empty file with no error indication. These are listed in `test_files.py`'s docstring as coverage targets but were never implemented.

The blocker was that `tests/unit/_stubs.py` didn't register `httpx2`, making `import transport.files` fail outside the venv. TRN-155 fixed `_stubs.py` to include `httpx2`; the tests can now be written.

## What Changes

- New test file `tests/unit/test_streaming_transfer.py` with:
  - `_ResponseChunkReader`: single-chunk, multi-chunk, sized reads, zero-read, empty stream, cross-boundary reads, EOF handling
  - `_TarMemberStream`: exact path match, basename match, missing member (raises), empty archive (raises), truncated input (raises), close idempotency, context manager
  - `_transfer_upload` slash-ref path: verify branch checkout is called when `rev-parse HEAD` fails after clone; verify it is NOT called when HEAD resolves normally

## Capabilities

- `transport-test-coverage` (existing delta spec) — no new spec changes needed; this is purely adding tests for already-specified behaviour
