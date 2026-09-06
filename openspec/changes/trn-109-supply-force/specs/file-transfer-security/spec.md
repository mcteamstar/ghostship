# Delta Spec: file-transfer-security — force flag in signed payload (TRN-109)

## Changes to Requirement: Operation-typed tokens

The `force` flag SHALL be treated as part of the operation type for upload tokens. A token signed with `force=False` MUST NOT be accepted as authorisation for a pre-clone deletion, and a token signed with `force=True` MUST NOT be accepted for a non-destructive upload.

### Updated: signed payload for upload tokens

The HMAC payload for `supply` presigned upload tokens SHALL include `force` in the sorted flags string alongside `bundle` and `unpack`. The payload format is:

```
{crew_id}:{path}:{expires}:POST::{flags}
```

where `flags` is the sorted, colon-joined set of active boolean options from `{bundle, force, unpack}`.

`_sign_upload_url()` and the upload path of `_verify_file_token()` SHALL both include `force` in this flags string so their payloads remain identical.

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
