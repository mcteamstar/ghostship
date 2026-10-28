## MODIFIED Requirements

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
