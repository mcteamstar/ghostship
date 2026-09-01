## MODIFIED Requirements

### Requirement: Security policy is signed by the Admiral using the 0.3.x governance API

The transport SHALL embed the HMAC-SHA256 signature as `identity.signature` inside
`security_policy.json` (with `identity.issuer: "ghostship"`), and SHALL write
`admission_policy.json` with `require_policy_signature: true` and
`trust_keys: {"ghostship": <policy_signing_key>}`.

The key placed in `trust_keys` SHALL be a dedicated `policy_signing_key` — a separate
secret generated at crew creation that is distinct from `admiral_secret`. The
`admiral_secret` SHALL NOT appear in `admission_policy.json` or in any file readable
by processes running inside the crew container.

The old flat `trust_keys` list approach SHALL NOT be used.

#### Scenario: Admission policy written alongside security policy

- **WHEN** a crew's security policy is injected
- **THEN** `~/.kiro/crew/admission_policy.json` is written with `require_policy_signature: true`
  and `trust_keys` as a dict keyed by issuer using the crew's `policy_signing_key`; the
  signature lives inside `security_policy.json` as `identity.signature`

#### Scenario: policy_signing_key is distinct from admiral_secret

- **WHEN** a new crew is created
- **THEN** the transport generates two separate secrets: `admiral_secret` (used for Admiral
  command authentication, written only to `crews.json` and `.admiral_secret` inside the
  container) and `policy_signing_key` (used only for policy signing, written to
  `crews.json` and placed in `trust_keys`)
- **AND** `admission_policy.json` inside the container contains only `policy_signing_key`,
  never `admiral_secret`

#### Scenario: Policy tampering is detected at gateway boot

- **WHEN** `security_policy.json` is modified inside the container after injection (e.g. by
  a compromised tool) and the gateway reloads
- **THEN** the gateway detects the invalid `identity.signature` and refuses to continue —
  the agent cannot forge a valid policy without the `policy_signing_key`

#### Scenario: Signature is embedded in the policy document not in the admission policy

- **WHEN** the transport injects a security policy
- **THEN** `security_policy.json` contains `identity.issuer` and `identity.signature`;
  `admission_policy.json` contains `trust_keys` as a dict mapping the issuer to the
  `policy_signing_key`

#### Scenario: Policy injection failure does not abort launch

- **WHEN** the exec script writing `security_policy.json` or `admission_policy.json` fails
  inside the container
- **THEN** the failure is logged as a warning, `launch()` continues without `policy_version`
  in the response, and the crew boots ungoverned rather than failing to launch

## ADDED Requirements

### Requirement: policy_signing_key is persisted in the crew registry

The transport SHALL store `policy_signing_key` in the `crews.json` registry entry for each
crew, alongside `admiral_secret`. This allows the transport to re-inject the correct policy
on container restart without regenerating the key (which would invalidate the existing
`trust_keys` inside the container).

#### Scenario: policy_signing_key written to crews.json at crew creation

- **WHEN** `_finish_crew_setup()` completes successfully and writes the crew registry entry
- **THEN** the entry in `crews.json` includes a `policy_signing_key` field containing the
  hex-encoded key that was used to sign and inject the crew's policy

#### Scenario: policy_signing_key absent for pre-trn-53 crews

- **WHEN** a crew entry in `crews.json` predates this change and has no `policy_signing_key`
  field
- **THEN** the transport treats the field as absent and makes no attempt to re-inject or
  validate the policy for that crew during normal operation

### Requirement: policy_signing_key is rotated only at crew creation

The `policy_signing_key` SHALL be generated once per crew at creation time and reused for
the lifetime of the crew. It SHALL NOT be rotated on container restart. Rotation occurs
implicitly when a crew is destroyed and recreated.

#### Scenario: Container restart does not change trust_keys

- **WHEN** a crew container is stopped and restarted (e.g. idle-stop recovery via
  `_ensure_crew_running`)
- **THEN** the `policy_signing_key` in `crews.json` is unchanged, and the existing
  `admission_policy.json` inside the container (on the home volume) remains valid
