# Tasks — trn-21-policy-signing-fix

- [x] **Task 1 — Rewrite `_inject_policy()` in `transport/server.py`**

  Replace the body of `_inject_policy()` per design.md §Fix 1:
  1. Load policy template (composition-specific or default) — same as current
  2. Add `identity: {"issuer": "ghostship"}` to the policy dict
  3. Build exec script that:
     - Passes `admiral_secret` via `base64.b64encode(admiral_secret.encode()).decode()` and decodes inside the script — do NOT interpolate as a Python literal
     - Inlines canonicalization (`json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")`) — do NOT import `kiro_crew`
     - Excludes `identity.signature` from signing payload
     - Computes `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()`
     - Embeds result as `policy["identity"]["signature"]`
     - Writes `security_policy.json` with full policy at 0o600
     - Writes `admission_policy.json` as `{"require_policy_signature": true, "trust_keys": {"ghostship": "<secret>"}}` at 0o600
  4. Remove old `hmac.new(...)` computation and "signature verification disabled" comment

- [x] **Task 2 — Fix `verify-admiral-sig`**

  File: `crews/kirocrew/verify-admiral-sig`

  Change:
  ```python
  body = msg.get_payload() or ''
  ```
  To:
  ```python
  body = (msg.get_payload() or '').rstrip('\n')
  ```

  This matches the `body.rstrip("\r\n")` in `_format_captain_mail` before signing.

- [x] **Task 3 — Update `test_transport.py`**

  Update `TestInjectPolicy`:
  - Rename `test_inject_policy_admission_disables_signature` → `test_inject_policy_admission_enables_signature_verification`
  - Assert `admission["require_policy_signature"]` is `True`
  - Assert `admission["trust_keys"] == {"ghostship": secret}`
  - Assert `security_policy.json` contains `identity.issuer == "ghostship"` and `identity.signature` is non-empty hex
  - Add `test_inject_policy_signature_is_correct` — re-derive expected HMAC in test, assert it matches `identity.signature`

  Add `TestCaptainMail` round-trip test:
  - Format mail via `_format_captain_mail(body, signing_secret=secret)`
  - Parse back with `email.message_from_string`
  - Simulate `verify-admiral-sig` (strip trailing `\n`, compute HMAC), assert matches `X-Admiral-Sig`

- [x] **Task 4 — Run tests**

  ```bash
  python3 -m unittest discover -s transport -p "test_*.py" -q
  ```
  All tests must pass.

- [x] **Task 5 — Smoke test on Academy**

  1. Deploy updated transport
  2. Launch a test crew — should return `policy_version: 1`
  3. Check transport logs: `policy injected version=1` present, `UNVERIFIED` absent
  4. Issue a captain order — Raven should accept it, no "failed signature verification" mail to Admiral
  5. Nuke the test crew
