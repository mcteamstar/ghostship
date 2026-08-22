## MODIFIED Requirements

### Requirement: Security policy is signed by the Admiral using the 0.3.x governance API
The transport SHALL compute the policy signature using the KiroCrew 0.3.x `canonical_signing_bytes` function from `kiro_crew.platform.governance`, embed the result as `identity.signature` inside `security_policy.json`, and write `admission_policy.json` with `require_policy_signature: true`. The old HMAC-SHA256-over-JSON-body `trust_keys` approach SHALL NOT be used.

#### Scenario: Admission policy written alongside security policy
- **WHEN** a crew's security policy is injected
- **THEN** `~/.kiro/crew/admission_policy.json` is written with `require_policy_signature: true` and no `trust_keys` field; the signature lives inside `security_policy.json` as `identity.signature`

#### Scenario: Policy tampering is detected at gateway boot
- **WHEN** `security_policy.json` is modified inside the container after injection (e.g. by a compromised tool) and the gateway reloads
- **THEN** the gateway detects the invalid `identity.signature`, rejects the policy, and refuses to continue — the agent cannot forge a valid policy without the `admiral_secret`

#### Scenario: Signature is embedded in the policy document, not in the admission policy
- **WHEN** the transport injects a security policy
- **THEN** `security_policy.json` contains an `identity.signature` field computed via `canonical_signing_bytes`, and `admission_policy.json` does not contain a `trust_keys` field
