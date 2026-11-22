# testing/file-transfer Specification

## Purpose

Defines verification coverage for file transfer behavior.

## Requirements

### Requirement: HMAC sign/verify machinery has direct unit tests

`tests/unit/test_files.py` SHALL include direct tests for the HMAC token signing
and verification functions in `transport/files.py`, covering:

- A valid signed URL verifies successfully
- A tampered signature is rejected
- An expired token is rejected
- A token signed for GET cannot be used on a PUT (mode mismatch)
- Path-traversal attempts are rejected by `_safe_workspace_path`

#### Scenario: Valid signed URL verifies
- **WHEN** a URL is signed with `_sign_file_url` and verified with `_verify_file_token`
- **THEN** verification succeeds and returns the expected payload

#### Scenario: Tampered signature is rejected
- **WHEN** the `sig` query parameter is modified after signing
- **THEN** `_verify_file_token` raises or returns a failure

#### Scenario: Expired token is rejected
- **WHEN** a token is signed with an expiry in the past
- **THEN** `_verify_file_token` rejects it

#### Scenario: Mode mismatch is rejected
- **WHEN** a token signed for GET method is used in a PUT request
- **THEN** `_verify_file_token` rejects it

#### Scenario: Path traversal is rejected
- **WHEN** a path containing `../` or absolute path components is passed to `_safe_workspace_path`
- **THEN** the function raises or returns a safe rejection

### Requirement: Streaming transfer classes have test coverage

`_ResponseChunkReader` and `_TarMemberStream` in `transport/files.py` SHALL have unit tests covering: normal reads, cross-chunk-boundary reads, empty stream, missing tar member (raises ValueError), truncated/invalid archive (raises), close idempotency, and context manager protocol.

#### Scenario: ResponseChunkReader reads across chunk boundaries
- **WHEN** a `_ResponseChunkReader` is constructed from multiple small chunks
- **THEN** `read(n)` returns exactly n bytes assembled correctly across chunk boundaries

#### Scenario: TarMemberStream raises on missing member
- **WHEN** a `_TarMemberStream` is constructed with an `expected_path` that is not present in the archive
- **THEN** a `ValueError` is raised at construction time

#### Scenario: _transfer_upload slash-ref workaround is exercised
- **WHEN** `_transfer_upload` is called and `git rev-parse HEAD` fails (empty working tree after clone)
- **THEN** `git checkout -b <branch> origin/<branch>` is called to check out the first available remote branch
