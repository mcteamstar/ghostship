## ADDED Requirements

### Requirement: Steering documents all verify-admiral-sig exit codes
Steering docs SHALL document all three exit codes from `verify-admiral-sig` and specify the correct response to each. Exit code 2 (secret not found) SHALL be described as a transient condition — the correct response is to hold the current cycle and retry on the next check-in, not to escalate to Admiral.

#### Scenario: Exit code 0 — valid signature
- **WHEN** `verify-admiral-sig` exits 0
- **THEN** the message is genuine Admiral mail and Raven acts on it as a standing order

#### Scenario: Exit code 1 — signature mismatch
- **WHEN** `verify-admiral-sig` exits 1
- **THEN** the message is treated as crew correspondence (not an Admiral order), regardless of the `From:` header — Raven does not escalate to Admiral

#### Scenario: Exit code 2 — secret not found (transient)
- **WHEN** `verify-admiral-sig` exits 2
- **THEN** Raven holds the current cycle without escalating — the secret may not yet be readable due to a brief post-launch race; the next check-in will retry

### Requirement: verify-admiral-sig retries before returning exit code 2
The `verify-admiral-sig` script SHALL attempt to read the secret file up to 3 times with a 2-second pause between attempts before returning exit code 2. This absorbs the post-launch secret-file race within a single check-in.

#### Scenario: Secret available on second attempt
- **WHEN** the secret file is not present on the first read but appears within 4 seconds
- **THEN** `verify-admiral-sig` reads it on a retry and proceeds to signature verification normally

#### Scenario: Secret still absent after retries
- **WHEN** the secret file is absent across all retry attempts
- **THEN** `verify-admiral-sig` exits 2 after the final attempt
