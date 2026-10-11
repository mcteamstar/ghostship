# Tasks — TRN-221 SEL key moved to `trust/`

## Verification (confirm the "no impact" finding against the target image)

- [ ] Pull `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (or its pinned digest) locally.
- [ ] Run `grep -rnE '(SEL|sel_key|sel\.key|/sel|trust/|keypair\.json|session_key)' transport/` and confirm the only hits are the known false positives: the `SELECT` in `transport/container_scripts/read_auth.py:24` and the `.local_secret` docstring near `transport/lifecycle.py:321`.
- [ ] Confirm `transport/lifecycle.py` `_crew_api()` / `_write_dashboard_cookie()` resolve no SEL or `trust/` path (dashboard cookie + `.local_secret` only).
- [ ] Confirm `transport/container_scripts/inject_policy.py` uses only `policy_signing_key` / `trust_keys["ghostship"]` and does not reference the KiroCrew SEL key.
- [ ] Confirm `transport/container_scripts/inject_auth.py` and `read_auth.py` touch only the `auth_kv` table.
- [ ] Boot a crew on `0.9.0-insider.4` and confirm it starts cleanly with no SEL-related error in the gateway log (negative confirmation that no ghostship change was needed for SEL signing).

## Guardrail (prevent regression)

- [ ] Add `test_trn_221_no_hardcoded_sel_path.py` next to the existing transport tests, implementing the static-assertion scan from `design.md` section 3.
- [ ] Run the new test against the current tree and confirm it PASSES (no hardcoded SEL path today).
- [ ] Add a temporary line containing a fake `sel_key = "/old/path/sel.key"` literal, confirm the test FAILS, then remove it — proving the guard actually fires.

## Documentation (pin the trust-root convention)

- [ ] Add the `$KIROCREW_HOME/trust/` SEL-key convention note from `design.md` section 4 to the crew standing orders / 0.9.0 upgrade notes.
- [ ] Cross-reference TRN-221 and the convention note in the upgrade tracking doc so a future SEL-reading feature finds it.

## Close-out

- [ ] Mark TRN-221 verified in the Plane board with the "behaviour change / low impact — no code change required" verdict.
- [ ] Run the transport test suite and confirm green including the new guardrail test.
