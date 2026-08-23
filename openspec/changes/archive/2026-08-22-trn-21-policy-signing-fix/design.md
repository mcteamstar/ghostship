# Design — trn-21-policy-signing-fix

## Context

See proposal.md. Two bugs, one `admiral_secret`:

1. Policy signing used wrong 0.3.x schema — `trust_keys` was a flat list, must be a dict keyed by issuer; `identity.signature` was missing from the policy document itself.
2. Admiral mail verification has a trailing newline mismatch — transport signs `body.rstrip("\r\n")` but `email.message_from_file().get_payload()` returns body with trailing `\n`.

## Goals / Non-Goals

**Goals:**
- `require_policy_signature: true` works at gateway boot
- Captain loop works — Raven accepts Admiral orders
- No new key material, no new secrets — `admiral_secret` serves both

**Non-goals:**
- Asymmetric signing (future, when KiroCrew supports it)
- Changing policy content (`academy/policies/`)

## The 0.3.x Signing API (from local KiroCrew source)

```python
# kiro_crew.platform.admission
def canonical_signing_bytes(body: Mapping[str, object]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

def hmac_signature(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

# kiro_crew.platform.governance
def policy_signing_payload(data: Mapping[str, object]) -> bytes:
    """Whole document minus identity.signature. identity.issuer IS covered."""
    body = {k: v for k, v in data.items() if k != "identity"}
    identity = data.get("identity")
    if isinstance(identity, dict):
        rest = {k: v for k, v in identity.items() if k != "signature"}
        if rest:
            body["identity"] = rest
    elif identity is not None:
        body["identity"] = identity
    return canonical_signing_bytes(body)
```

Verification: `_policy_signature_state` looks up `trust_keys[identity.issuer]` from `admission_policy.json` and calls `hmac_signature(secret, policy_signing_payload(data))`.

## Fix 1 — Policy signing

### New `admission_policy.json` schema
```json
{
  "require_policy_signature": true,
  "trust_keys": {"ghostship": "<admiral_secret>"}
}
```

The key was previously a flat list — now it must be a dict keyed by issuer.

### New `security_policy.json` structure
Add `identity` block to the policy before signing:
```json
{
  "version": 1,
  "boot": {},
  "commands": {...},
  "identity": {
    "issuer": "ghostship",
    "signature": "<hmac_hex>"
  }
}
```

### Signing flow in `_inject_policy`

The signing runs inside the container via `container_exec_checked` — inlining the canonicalization rather than importing `kiro_crew` (avoids import side-effects during setup):

```python
# 1. Load template, add identity block without signature
policy = json.loads(template_path.read_text())
policy["identity"] = {"issuer": "ghostship"}

# 2. Send exec script to container
script = f"""
import json, hmac, hashlib, base64, pathlib, os
policy = {json.dumps(policy)}
# Build signing payload: whole doc minus identity.signature
body = {{k: v for k, v in policy.items() if k != "identity"}}
identity = policy.get("identity", {{}})
rest = {{k: v for k, v in identity.items() if k != "signature"}}
if rest:
    body["identity"] = rest
payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
secret_b64 = base64.b64decode("{base64.b64encode(admiral_secret.encode()).decode()}").decode()
sig = hmac.new(secret_b64.encode("utf-8"), payload, hashlib.sha256).hexdigest()
policy["identity"]["signature"] = sig
policy_body = json.dumps(policy, indent=2)
admission = json.dumps({{"require_policy_signature": True, "trust_keys": {{"ghostship": secret_b64}}}}, indent=2)
crew_dir = pathlib.Path("/home/kirocrew/.kiro/crew")
crew_dir.mkdir(parents=True, exist_ok=True)
for fname, content in [("security_policy.json", policy_body), ("admission_policy.json", admission)]:
    p = crew_dir / fname
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, content.encode()); os.close(fd)
print("policy injected")
"""
```

## Fix 2 — Admiral mail verification

One-line fix in `crews/kirocrew/verify-admiral-sig`:

```python
# Before:
body = msg.get_payload() or ''
# After:
body = (msg.get_payload() or '').rstrip('\n')
```

This matches `body.rstrip("\r\n")` applied in `_format_captain_mail` before signing.

## Test strategy

- `TestInjectPolicy`: flip `require_policy_signature` assertion to `True`, assert `trust_keys == {"ghostship": secret}`, assert `identity.signature` present and correct in policy
- New `TestVerifyAdmiralSig` (or extend existing): round-trip test — format a mail with `_format_captain_mail`, parse it back, verify signature passes
