# Delta Spec: file-transfer-security — force flag in signed payload (TRN-109)

## MODIFIED Requirements

### Requirement: Operation-typed tokens
Download tokens and upload tokens MUST be cryptographically non-interchangeable.
The HMAC payload MUST include the operation type (`get` or `put`) as a prefix.
A token issued for download MUST be rejected when presented for upload, and vice versa.

The `force` flag SHALL be treated as part of the operation type for upload tokens: a token signed with `force=False` MUST NOT be accepted as authorisation for a pre-clone deletion, and a token signed with `force=True` MUST NOT be accepted for a non-destructive upload. The HMAC payload for `supply` presigned upload tokens SHALL include `force` in the sorted flags string alongside `bundle` and `unpack`. The payload format is:

```
{crew_id}:{path}:{expires}:POST::{flags}
```

where `flags` is the sorted, colon-joined set of active boolean options from `{bundle, force, unpack}`. `_sign_upload_url()` and the upload path of `_verify_file_token()` SHALL both include `force` in this flags string so their payloads remain identical.

#### Scenario: Download token rejected on upload endpoint
- **WHEN** a caller presents a valid evac (download) presigned URL to the supply (upload) endpoint
- **THEN** the transport returns 403 Forbidden

#### Scenario: Upload token rejected on download endpoint
- **WHEN** a caller presents a valid supply (upload) presigned URL to the evac (download) endpoint
- **THEN** the transport returns 403 Forbidden

#### Scenario: Correct token accepted on correct endpoint
- **WHEN** a caller presents a valid token to the endpoint it was issued for
- **THEN** the request is accepted and processed

#### Scenario: Token signed with force=False rejected for force=True operation
- **WHEN** a presigned upload URL was generated with `force=False` (flags string does not contain `force`)
- **AND** the verification context would require `force=True` (flags string contains `force`)
- **THEN** the HMAC comparison fails and the transport returns 403 Forbidden

#### Scenario: Token signed with force=True rejected for force=False operation
- **WHEN** a presigned upload URL was generated with `force=True` (flags string contains `force`)
- **AND** the verification context corresponds to `force=False`
- **THEN** the HMAC comparison fails and the transport returns 403 Forbidden

#### Scenario: Matching force flag passes verification
- **WHEN** a presigned upload URL is generated and verified with the same `force` value
- **THEN** HMAC verification passes and the upload proceeds normally
