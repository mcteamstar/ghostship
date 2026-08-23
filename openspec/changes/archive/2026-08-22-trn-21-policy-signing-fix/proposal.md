# Proposal: trn-21-policy-signing-fix

## Why

Two related signing failures, one `admiral_secret`:

1. **Policy signing broken** — TRN-18 signed the security policy using HMAC-SHA256 and stored the result as a `trust_keys` list entry in `admission_policy.json`. KiroCrew 0.3.x changed the API: the signature must be embedded as `identity.signature` inside the policy document itself, and `trust_keys` in `admission_policy.json` must be a dict keyed by issuer (`{"ghostship": "<secret>"}`). Result: `require_policy_signature=False` — policy enforcement active but tamper detection disabled.

2. **Captain loop broken** — Admiral mail signing uses `admiral_secret` correctly (HMAC-SHA256 of the body), but `verify-admiral-sig` has a trailing newline mismatch: the transport signs `body.rstrip("\r\n")` but `email.message_from_file().get_payload()` returns the body with a trailing `\n`, so the HMAC never matches. Raven rejects every captain order.

Both failures use `admiral_secret`. Fix both in one change:
- Policy: use `identity.signature` in the policy document + `trust_keys: {"ghostship": admiral_secret}` in `admission_policy.json`
- Mail: fix `verify-admiral-sig` to strip the trailing newline before verifying

## What Changes

- Re-implement `_inject_policy()` to embed `identity.signature` in `security_policy.json` and write `admission_policy.json` with `require_policy_signature: true` and `trust_keys: {"ghostship": admiral_secret}`
- Fix `verify-admiral-sig` to strip trailing newline from the parsed mail body before HMAC verification
- Update `test_transport.py` to cover both fixes

## Capabilities

### Modified Capabilities

- `crew-governance` — Policy signing re-enabled with correct 0.3.x schema: `identity.signature` in policy, `trust_keys` dict in admission policy
- `crew-login` — Admiral mail verification fixed; captain loop becomes functional

## Impact

- `transport/server.py` — `_inject_policy()` rewritten
- `crews/kirocrew/verify-admiral-sig` — one-line trailing newline fix
- `transport/test_transport.py` — policy and mail signing tests updated
- `academy/policies/` — no changes to policy content
