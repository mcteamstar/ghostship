## Why

A single key (`admiral_secret`) serves two unrelated purposes: Admiral mail HMAC authentication, and KiroCrew security policy signature verification. Because `trust_keys` in `admission_policy.json` is a hard dependency of the KiroCrew governance API, the `admiral_secret` must currently be written there — making it readable by any agent with code execution inside the crew container (0600 permissions are meaningless when gateway and agents share the same `kirocrew` UID). Separating the keys removes the Admiral signing secret from any agent-readable path.

## What Changes

- Generate a separate `policy_signing_key` at crew launch (distinct from `admiral_secret`)
- `policy_signing_key` goes into `admission_policy.json` `trust_keys` — used only for policy signature verification; low-value even if read
- `admiral_secret` no longer written to `admission_policy.json`; stays only in `.admiral_secret` (0600)
- `policy_signing_key` stored in `crews.json` (same threat model as `admiral_secret` already stored there)
- Fix `docs/auth.md` post-implementation to reflect the new two-key model (docs were updated to describe the current risk but will need updating again after the fix)

## Capabilities

### Modified Capabilities

- `crew-governance`: `admission_policy.json` `trust_keys` now holds `policy_signing_key`, not `admiral_secret`
- `crew-auth`: `admiral_secret` delivery path — no longer via `admission_policy.json`

## Impact

- `transport/container_scripts/inject_policy.py` — accept `policy_signing_key` instead of `admiral_secret`
- `transport/lifecycle.py` — `_inject_policy`, `_finish_crew_setup`: generate both keys, pass separately
- `crews.json` schema — add `policy_signing_key` field
- `docs/auth.md` — update post-implementation
- `tests/unit/test_lifecycle.py`, `tests/unit/test_server.py` — update `trust_keys` assertions

## Open Questions

<!-- To be answered during design -->
- Should `policy_signing_key` be rotated on each crew restart, or only at crew creation? (Rotating on restart means updating `admission_policy.json` on every wake — is that safe mid-lifecycle?)
- Does `crews.json` storing `policy_signing_key` in plaintext introduce any new risk vs the current state? (Probably not — `admiral_secret` is already there.)
- Are there any existing crew containers on the academy that would break on upgrade (old `trust_keys` format vs new)? Migration path needed?
