# Proposal: trn-21-policy-signing-fix

## Why

TRN-18 implemented `_inject_policy()` using HMAC-SHA256 over the JSON body stored as a `trust_keys` entry in `admission_policy.json`. KiroCrew 0.3.x changed the governance API: it now expects the signature embedded as `identity.signature` inside the policy document itself, computed via `canonical_signing_bytes` from `kiro_crew.platform.governance`. As a result, boot-time signature verification is currently disabled (`require_policy_signature: false`), leaving policy tampering undetectable.

## What Changes

- Re-implement `_inject_policy()` in `transport/server.py` to compute the policy signature using the 0.3.x `canonical_signing_bytes` API and embed it as `identity.signature` inside `security_policy.json`
- Set `require_policy_signature: true` in `admission_policy.json` once the correct signature is in place
- Update the admission policy structure to match the 0.3.x schema (remove the old `trust_keys` field)
- Update `test_transport.py` to cover the new signing path

## Capabilities

### Modified Capabilities

- `crew-governance` — The requirement that the transport signs the security policy and that the gateway verifies it at boot will now be satisfied. The signing mechanism changes from a HMAC trust key to an embedded `identity.signature`.

## Impact

- `transport/server.py` — `_inject_policy()` rewritten
- `transport/test_transport.py` — signing test updated
- `academy/policies/` — no changes to policy content, only how the signature is attached
- Requires the KiroCrew 0.3.x `kiro_crew.platform.governance` module to be accessible inside the transport container (it is — the transport already shells into the crew container to run kiro-cli commands, and `canonical_signing_bytes` is called inside the container via `container_exec_checked`)
