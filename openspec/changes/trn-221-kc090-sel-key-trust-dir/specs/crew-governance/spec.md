## ADDED Requirements

### Requirement: SEL signing key is resolved from the KiroCrew trust root

Any ghostship code that reads or references the KiroCrew Security Event Log
(SEL) signing key SHALL resolve it under `$KIROCREW_HOME/trust/`. No ghostship
code SHALL hardcode a pre-0.9.0 SEL key path or a bare relative path to the
SEL key. This requirement applies to any future feature that consumes SEL audit
material; it is a forward-looking contract, not a description of existing
behaviour (no ghostship code reads the SEL key today).

The SEL signing key is a KiroCrew gateway-internal credential. It is distinct
from the following ghostship-managed keys and SHALL NOT be confused with them:

- `.local_secret` — the gateway's internal-API secret, used only by
  `transport/lifecycle.py` for dashboard-cookie writes.
- `policy_signing_key` — ghostship's own HMAC key for `security_policy.json`
  and `admission_policy.json`, managed by `transport/container_scripts/inject_policy.py`.
- `admiral_secret` — the per-crew admiral authentication secret.

#### Scenario: Future SEL-reading code uses the trust root path

- **WHEN** any ghostship module is written or modified to read, verify, or
  reference the KiroCrew SEL signing key
- **THEN** it SHALL resolve the key under `$KIROCREW_HOME/trust/` and SHALL NOT
  contain a string literal matching `sel_key`, `sel-key`, `sel.key`, or `/sel/`
  as a path segment

#### Scenario: Grep of transport/ finds no pre-0.9.0 SEL path literal

- **WHEN** `grep -rnE '(sel_key|sel\.key|/sel/)' transport/` is run against the
  ghostship source tree
- **THEN** it returns no matches that resolve to a KiroCrew SEL key path; the
  only permitted hits are the known unrelated literals: the SQL `SELECT` keyword
  in `transport/container_scripts/read_auth.py` and the `.local_secret`
  docstring near `transport/lifecycle.py:321`

#### Scenario: Crew boots on KiroCrew 0.9.0 without SEL-related error

- **WHEN** a ghostship-managed crew is launched against a KiroCrew `0.9.0`
  (or later) gateway
- **THEN** the gateway log contains no SEL-related error attributable to a
  missing or incorrect ghostship SEL key reference; ghostship requires no code
  change for SEL signing to function
