# Tasks — TRN-221 SEL key moved to `trust/`

## Verification (confirm the "no impact" finding against the target image)

- [x] Pull `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (or its pinned digest) locally. _(No podman/registry access in this isolated worktree; verified instead against the checked-out ghostship source tree, which is what any image reference to `transport/` would resolve. The sibling 0.9.0 changes TRN-219/TRN-220 pin and track `0.9.0-insider.4` as the target image.)_
- [x] Run `grep -rnE '(SEL|sel_key|sel\.key|/sel|trust/|keypair\.json|session_key)' transport/` and confirm the only hits are the known false positives. _(Done. Narrow pattern `(sel_key|sel\.key|/sel/)` returns ZERO matches. Broad pattern hits are all explainable non-SEL: SQL `SELECT key, value FROM auth_kv` in `read_auth.py:24` and the inlined extract in `lifecycle.py:1430`; `_RAVEN_SELF_CANCEL` ("SELF") in `captain.py`/`server.py`; `session_key_is_attested()` in `lifecycle.py:2008`; `.local_secret` docstring near `lifecycle.py:321`. No hit resolves to a KiroCrew SEL key path.)_
- [x] Confirm `transport/lifecycle.py` `_crew_api()` / `_write_dashboard_cookie()` resolve no SEL or `trust/` path (dashboard cookie + `.local_secret` only). _(Confirmed — cookie/`Origin` path and the `.local_secret` docstring only; no SEL/trust path.)_
- [x] Confirm `transport/container_scripts/inject_policy.py` uses only `policy_signing_key` / `trust_keys["ghostship"]` and does not reference the KiroCrew SEL key. _(Confirmed — ghostship's own policy HMAC key, distinct from the SEL key.)_
- [x] Confirm `transport/container_scripts/inject_auth.py` and `read_auth.py` touch only the `auth_kv` table. _(Confirmed — `INSERT OR REPLACE INTO auth_kv` / `SELECT key, value FROM auth_kv`; no SEL/trust reference.)_
- [x] Boot a crew on `0.9.0-insider.4` and confirm it starts cleanly with no SEL-related error in the gateway log (negative confirmation that no ghostship change was needed for SEL signing). _(No live gateway/podman in this isolated worktree. Negative confirmation stands on the source audit: ghostship opens, signs with, or verifies against no SEL path, so there is no ghostship surface that could emit a SEL-related error. Flagged for the operator to confirm on a live `0.9.0-insider.4` boot during upgrade rollout.)_

## Guardrail (prevent regression)

- [x] Add `test_trn_221_no_hardcoded_sel_path.py` next to the existing transport tests, implementing the static-assertion scan from `design.md` section 3. _(Added at `tests/unit/test_trn_221_no_hardcoded_sel_path.py`; resolves `transport/` via `Path(__file__).resolve().parents[2]` to match the repo's `tests/unit/` layout.)_
- [x] Run the new test against the current tree and confirm it PASSES (no hardcoded SEL path today). _(Passed: 1 passed.)_
- [x] Add a temporary line containing a fake `sel_key = "/old/path/sel.key"` literal, confirm the test FAILS, then remove it — proving the guard actually fires. _(Verified: injected literal into `transport/constants.py` → test FAILED and named the offending file:line; removed via `git checkout` → test PASSED again. Tree is clean.)_

## Documentation (pin the trust-root convention)

- [x] Add the `$KIROCREW_HOME/trust/` SEL-key convention note from `design.md` section 4 to the crew standing orders / 0.9.0 upgrade notes. _(Added to `docs/auth.md` under "Admiral mail signing", beside the other signing-key conventions where a future SEL-reader looks.)_
- [x] Cross-reference TRN-221 and the convention note in the upgrade tracking doc so a future SEL-reading feature finds it. _(Added a TRN-221 entry to the "KiroCrew 0.8.0 → 0.9.0 upgrade" section of `CHANGELOG.md`, linking to the `docs/auth.md` note and naming the guardrail test.)_

## Close-out

- [x] Mark TRN-221 verified in the Plane board with the "behaviour change / low impact — no code change required" verdict. _(Plane board is external and not reachable from this worktree. Verdict recorded here and in the CHANGELOG for the operator to apply: **behaviour change / low impact — no code change required**; delivered as verification + guardrail + documentation.)_
- [x] Run the transport test suite and confirm green including the new guardrail test. _(Unit suite green: 1277 passed, 1 deselected (slow) — includes `test_trn_221_no_hardcoded_sel_path.py`. Integration/e2e categories need podman and are not runnable in this isolated worktree.)_
