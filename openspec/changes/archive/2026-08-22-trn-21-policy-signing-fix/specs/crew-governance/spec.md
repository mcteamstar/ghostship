## MODIFIED Requirements

### Requirement: Security policy is signed by the Admiral using the 0.3.x governance API
The transport SHALL embed the HMAC-SHA256 signature as `identity.signature` inside `security_policy.json` (with `identity.issuer: "ghostship"`), and SHALL write `admission_policy.json` with `require_policy_signature: true` and `trust_keys: {"ghostship": <admiral_secret>}`. The old flat `trust_keys` list approach SHALL NOT be used.

#### Scenario: Admission policy written alongside security policy
- **WHEN** a crew's security policy is injected
- **THEN** `~/.kiro/crew/admission_policy.json` is written with `require_policy_signature: true` and `trust_keys` as a dict keyed by issuer; the signature lives inside `security_policy.json` as `identity.signature`

#### Scenario: Policy tampering is detected at gateway boot
- **WHEN** `security_policy.json` is modified inside the container after injection and the gateway reloads
- **THEN** the gateway detects the invalid `identity.signature` and refuses to continue

#### Scenario: Signature is embedded in the policy document not in the admission policy
- **WHEN** the transport injects a security policy
- **THEN** `security_policy.json` contains `identity.issuer` and `identity.signature`; `admission_policy.json` contains `trust_keys` as a dict mapping the issuer to the HMAC secret

#### Scenario: Policy injection failure does not abort launch
- **WHEN** the exec script writing `security_policy.json` or `admission_policy.json` fails inside the container
- **THEN** the failure is logged as a warning, `launch()` continues without `policy_version` in the response, and the crew boots ungoverned rather than failing to launch
