## ADDED Requirements

### Requirement: Presigned URL issuance is audited
Every presigned URL issued by the `supply` or `evac` MCP tools SHALL produce an audit
event via `audit_auth_event`. The event SHALL record at minimum: `action` (`"presign_supply"`
or `"presign_evac"`), `outcome` (`"issued"` on success, `"denied"` on auth failure), and
`source` (the caller's identity key as derived by the transport). The event SHALL NOT
include the presigned URL itself, the HMAC secret, or the caller's raw API key.

#### Scenario: Evac presign emits audit event
- **WHEN** a caller invokes the `evac` MCP tool and a presigned download URL is generated
- **THEN** an audit event with `action="presign_evac"` and `outcome="issued"` is recorded

#### Scenario: Supply presign emits audit event
- **WHEN** a caller invokes the `supply` MCP tool and a presigned upload URL is generated
- **THEN** an audit event with `action="presign_supply"` and `outcome="issued"` is recorded

#### Scenario: Audit event contains no secret material
- **WHEN** a presign audit event is recorded for either tool
- **THEN** the event dict does not contain the HMAC secret, the presigned URL, or any raw
  API key value

### Requirement: Token verification outcome is audited
Every call to `_verify_file_token` (the HMAC token verifier used by the file-download and
file-upload HTTP handlers) SHALL produce an audit event. The event SHALL record `action`
(`"verify_file_token"`), `outcome` (`"valid"` or `"invalid"`), and the operation type
(`get` or `put`). On expiry the `outcome` SHALL be `"expired"`.

#### Scenario: Valid token verification emits audit event
- **WHEN** a file-handler request presents a valid, non-expired presigned token
- **THEN** an audit event with `action="verify_file_token"` and `outcome="valid"` is recorded

#### Scenario: Invalid HMAC emits audit event with outcome=invalid
- **WHEN** a file-handler request presents a token with a bad HMAC signature
- **THEN** an audit event with `action="verify_file_token"` and `outcome="invalid"` is recorded

#### Scenario: Expired token emits audit event with outcome=expired
- **WHEN** a file-handler request presents a token whose `expires` timestamp is in the past
- **THEN** an audit event with `action="verify_file_token"` and `outcome="expired"` is recorded
