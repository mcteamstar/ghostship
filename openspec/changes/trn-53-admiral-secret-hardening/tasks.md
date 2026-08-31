## 1. Update inject_policy.py

- [ ] 1.1 Rename the `admiral_secret` parameter of `inject_policy()` to `policy_signing_key` and update its docstring to reflect that this is a dedicated policy-signing key, not the Admiral auth secret
- [ ] 1.2 Update the base64 payload key read in `main()` from `"admiral_secret"` to `"policy_signing_key"` so the JSON payload `{"policy": ..., "policy_signing_key": ...}` is parsed correctly
- [ ] 1.3 Verify that `admission_policy.json` is written with `trust_keys: {"ghostship": policy_signing_key}` (not `admiral_secret`) — this is already the structure; only the value source changes
- [ ] 1.4 Update the module-level docstring to describe the new payload key name

## 2. Update lifecycle.py: generate and thread policy_signing_key

- [ ] 2.1 In `_finish_crew_setup()`, generate `policy_signing_key = secrets.token_hex(32)` immediately after `admiral_secret` is generated (line ~1208)
- [ ] 2.2 Update `_inject_policy()` signature: replace `admiral_secret: str` parameter with `policy_signing_key: str`
- [ ] 2.3 Update the payload built inside `_inject_policy()`: change `{"policy": policy, "admiral_secret": admiral_secret}` to `{"policy": policy, "policy_signing_key": policy_signing_key}`
- [ ] 2.4 Update the call site in `_finish_crew_setup()` to pass `policy_signing_key` instead of `admiral_secret` to `_inject_policy()`
- [ ] 2.5 Remove or update the now-inaccurate comment in `_inject_policy()` that describes `admission_policy.json` as containing `trust_keys (the admiral_secret)`

## 3. Update crews.json schema: store policy_signing_key

- [ ] 3.1 In `_finish_crew_setup()`, add `"policy_signing_key": policy_signing_key` to the `crew_entry` dict written into `crews.json` (alongside the existing `"admiral_secret"` field)
- [ ] 3.2 Confirm the field is only written when `policy_version is not None` (i.e. policy injection succeeded) — if injection failed there is no valid `policy_signing_key` to store

## 4. Tests

- [ ] 4.1 Update any existing unit tests for `inject_policy()` that pass `admiral_secret` as the signing key — change the argument name/key to `policy_signing_key`
- [ ] 4.2 Add a unit test asserting that after `inject_policy()` runs, `admission_policy.json` contains `policy_signing_key` in `trust_keys` and does NOT contain `admiral_secret`
- [ ] 4.3 Add a unit test for `_inject_policy()` / `_finish_crew_setup()` verifying that two distinct secrets are generated and that `policy_signing_key` (not `admiral_secret`) is the one forwarded to the container exec call
- [ ] 4.4 Add a unit test for the `crews.json` entry asserting that `policy_signing_key` is present in the registry entry when policy injection succeeds

## 5. Documentation and comments

- [ ] 5.1 Update `docs/auth.md` (threat model section) to note that `admission_policy.json` no longer contains `admiral_secret`; reference the new `policy_signing_key` field
- [ ] 5.2 Update any inline comments in `lifecycle.py` that reference `admiral_secret` flowing into `trust_keys`
