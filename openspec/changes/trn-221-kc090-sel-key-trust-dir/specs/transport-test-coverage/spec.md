## ADDED Requirements

### Requirement: Static guardrail test prevents hardcoded pre-0.9.0 SEL path

The test suite SHALL include a static-assertion test that scans all Python
files under `transport/` and fails if any file contains a string literal
matching a pre-0.9.0 KiroCrew SEL key path pattern (`sel_key`, `sel-key`,
`sel.key`, or `/sel/` as a path segment). This test SHALL pass on the current
tree (no such literal exists today) and SHALL fail if such a literal is
introduced in a future commit, preventing silent regression to the pre-0.9.0
path convention.

The test SHALL NOT flag:

- The SQL `SELECT` keyword (a false-positive on `sel`) in
  `transport/container_scripts/read_auth.py`.
- The `.local_secret` docstring in `transport/lifecycle.py` (unrelated
  internal-API-secret reference).
- The `policy_signing_key` / `trust_keys` strings in
  `transport/container_scripts/inject_policy.py` (ghostship's own policy key,
  not the SEL key).

#### Scenario: Test passes on clean tree

- **WHEN** the guardrail test is run against the transport source tree that
  contains no pre-0.9.0 SEL key path literal
- **THEN** the test passes with zero offenders reported

#### Scenario: Test fails when a pre-0.9.0 SEL literal is introduced

- **WHEN** any Python file under `transport/` is modified to include a string
  literal matching `sel_key`, `sel-key`, `sel.key`, or `/sel/` as a path segment
- **THEN** the guardrail test fails and identifies the offending file and line
  number

#### Scenario: SQL SELECT keyword is not a false positive

- **WHEN** the guardrail test runs and `transport/container_scripts/read_auth.py`
  contains `SELECT key, value FROM auth_kv`
- **THEN** the test passes; the SQL `SELECT` keyword does not match the SEL
  path pattern

#### Scenario: policy_signing_key and local_secret are not false positives

- **WHEN** the guardrail test runs and `transport/container_scripts/inject_policy.py`
  contains `policy_signing_key` and `trust_keys`, and `transport/lifecycle.py`
  contains `.local_secret`
- **THEN** the test passes; neither string matches the SEL path pattern
