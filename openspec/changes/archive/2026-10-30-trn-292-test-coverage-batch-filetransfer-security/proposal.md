# Proposal

## Why

Independent review of the v0.10.0 release (indy-review crew, 2026-10-30) identified
zero unit test coverage on three areas of the transport that handle high-value
operations: batch dispatch/pickup, file transfer, and security primitives.

## What Changes

### C-1 — No unit tests for batch dispatch/pickup

`_dispatch_batch` and `_pickup_batch` in `lifecycle.py` implement the
`tasks=[...]` and `task_ids=[...]` batch operations exposed via the MCP tools.
These code paths have no unit tests. Key scenarios to cover:

- Successful batch dispatch: batch_id returned, task_ids populated
- Partial batch (crew dies mid-dispatch): `status: "partial"`, surviving task_ids
- Batch pickup: all done returns `done: true`; mixed states; `lost: true` for unknown task_ids
- Timeout behaviour on pickup

### C-2 — No unit tests for file transfer handlers

`_handle_file_get` and `_handle_file_put` in `files.py` (or `server.py`) handle
`supply` and `evac` presigned URL operations. These have no unit tests. Key
scenarios:

- Valid presigned URL: request dispatched to correct path
- Expired/invalid signature: 403
- Missing file on get: 404
- Successful put: 200 with correct content-type

### H-6 — No unit tests for security.py encoding helpers and CSP nonce

`security.py` contains encoding utilities (`_encode_*`), CSP nonce generation,
and the `needs_rehash` path in `verify_password`. These are security-critical
but have no direct unit test coverage (they are exercised indirectly through
integration paths). Key scenarios:

- CSP nonce: correct length, URL-safe base64, unique per call
- `needs_rehash`: returns True when scrypt params are outdated
- Encoding helpers: round-trip correctness

## Capabilities

No new capabilities. Tests only.

## Impact

- `tests/unit/test_lifecycle.py` or new `test_batch.py` — batch dispatch/pickup tests
- `tests/unit/test_files.py` or new `test_filetransfer.py` — file transfer handler tests
- `tests/unit/test_security.py` — encoding, CSP nonce, needs_rehash tests
