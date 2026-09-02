## ADDED Requirements

### Requirement: Crew secrets not persisted in plaintext after injection
After the transport successfully injects `admiral_secret` and `policy_signing_key` into a
crew container, the registry entry written to `crews.json` SHALL NOT contain the plaintext
values of those secrets. Instead, the registry SHALL store a non-reversible identifier
derived from each secret (a truncated HMAC-SHA256 keyed by a stable per-installation salt,
or a SHA-256 hex digest prefixed with a label) sufficient for log correlation but useless
for replay. The plaintext values MAY remain in memory only for the duration of the injection
call; they MUST be overwritten or replaced in the crew entry dict before the entry is
committed to `crews.json`.

#### Scenario: crews.json entry does not contain plaintext admiral_secret after launch
- **WHEN** a crew is launched and `_finish_crew_setup` completes successfully
- **THEN** the `admiral_secret` field in the crew's `crews.json` entry is absent or contains
  only a non-reversible identifier, not the 32-byte hex secret that was injected

#### Scenario: crews.json entry does not contain plaintext policy_signing_key after launch
- **WHEN** a crew is launched and policy injection succeeds
- **THEN** the `policy_signing_key` field in the crew's `crews.json` entry is absent or
  contains only a non-reversible identifier, not the 32-byte hex secret

#### Scenario: Injection still works after credential hygiene
- **WHEN** the transport injects the admiral secret and policy signing key
- **THEN** both files (`/.admiral_secret` and the policy JSON) inside the crew container
  are correctly written with the real secret values, confirming that hygiene of `crews.json`
  does not break the injection path
