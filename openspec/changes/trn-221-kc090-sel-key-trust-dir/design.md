# Design — TRN-221 SEL key moved to `trust/`

## Design stance

The research report's source-grounded finding is that **ghostship contains no
SEL key reference**, so the correct implementation is a **verification +
guardrail** design, not a code refactor. Writing speculative SEL-reading code
now would add an unused path and a maintenance liability. This design therefore:

1. Confirms the "no reference" finding against the actual `0.9.0-insider.4`
   target image.
2. Documents the `$KIROCREW_HOME/trust/` convention where a future reader would
   look for it.
3. Adds a lightweight regression guard so a later PR cannot silently reintroduce
   a hardcoded pre-0.9.0 SEL path.

## 1. Verification against the target image

The research audit ran against the checked-out source. Re-run the same audit as
an explicit gate against the image ghostship will actually bump to.

Grep scope: `transport/` (transport process + `transport/container_scripts/`),
mirroring the research report's search:

```bash
grep -rnE '(SEL|sel_key|sel\.key|/sel|trust/|keypair\.json|session_key)' transport/
```

Expected result: **no matches that resolve to a KiroCrew SEL key path.** The
only hits should be the known-unrelated ones:

- `transport/lifecycle.py` ~line 321 — docstring mentioning `.local_secret`
  (internal-API secret, not SEL).
- `transport/container_scripts/read_auth.py:24` — `SELECT key, value ...`
  (SQL keyword `SELECT`, a false-positive on `SEL`, not the SEL key).

Both are explainable non-SEL hits; neither opens a SEL/trust path. If any new,
unexplained hit appears against `0.9.0-insider.4`, escalate — the finding would
change from "no impact" to a real break.

## 2. Confirm the unaffected adjacent surfaces

Read-only confirmation that the two signing-adjacent surfaces are genuinely
untouched:

- `transport/lifecycle.py` — `_crew_api()` (uses `Cookie` + `Origin` only, via
  `_crew_cookie()`), `_write_dashboard_cookie()` (writes `.dashboard_cookie`,
  mode `0600`), and the `.local_secret` docstring. None of these resolve a SEL
  or `trust/` path. No edit.
- `transport/container_scripts/inject_policy.py` — `sign_policy()` and
  `inject_policy()` sign with `policy_signing_key` and store it under
  `trust_keys["ghostship"]` in `admission_policy.json`. This is ghostship's own
  policy-signing key written into the crew's `.kiro/crew` directory, explicitly
  documented in the module as "distinct from `admiral_secret`" — it is **not**
  the KiroCrew SEL key. No edit.
- `transport/container_scripts/inject_auth.py` / `read_auth.py` — operate on the
  `auth_kv` table only (`INSERT OR REPLACE INTO auth_kv`, `SELECT key, value
  FROM auth_kv`). No SEL/trust reference. No edit.

## 3. Guardrail: regression test for a hardcoded SEL path

Add a tiny static-assertion test so a future PR cannot reintroduce a pre-0.9.0
SEL path literal without tripping CI. This is the only *new code* in the change
and it is test-only.

Suggested location: alongside the existing transport test suite (match the
repo's existing test layout; the test imports nothing from `kiro_crew`).

```python
# test_trn_221_no_hardcoded_sel_path.py
import pathlib
import re

# Pre-0.9.0 SEL path literals that must NOT reappear in ghostship transport code.
_FORBIDDEN = re.compile(r"""(?xi)
    (?:['"][^'"]*/)?            # optional path prefix in a string literal
    sel[_.-]?key                # sel_key / sel-key / sel.key / selkey
  | /sel/                       # a /sel/ path segment
""")

_TRANSPORT = pathlib.Path(__file__).resolve().parents[1] / "transport"

def test_no_hardcoded_sel_key_path():
    offenders = []
    for py in _TRANSPORT.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN.search(line):
                offenders.append(f"{py}:{i}: {line.strip()}")
    assert not offenders, (
        "SEL key must be read from $KIROCREW_HOME/trust/ (KiroCrew 0.9.0); "
        "no hardcoded pre-0.9.0 SEL path is allowed:\n" + "\n".join(offenders)
    )
```

The pattern deliberately targets `sel_key` / `/sel/` style literals and does
**not** match the SQL `SELECT` keyword or the unrelated `.local_secret` /
`policy_signing_key` strings, so it passes on today's tree and fails only if a
real SEL path literal is added.

## 4. Documentation: the trust-root convention

Record the convention where a future SEL-reading implementer will see it. The
natural home is the crew standing orders / upgrade notes (the same place the
0.9.0 upgrade findings are tracked). Add a short note:

> **SEL key (KiroCrew 0.9.0+):** the Security Event Log signing key lives under
> `$KIROCREW_HOME/trust/`. It is a gateway-internal credential. If a future
> feature needs to read or verify SEL audit entries, resolve the key under
> `$KIROCREW_HOME/trust/` — never a hardcoded pre-0.9.0 location, and never
> confuse it with ghostship's own `.local_secret` (internal-API secret) or
> `policy_signing_key` (policy HMAC).

## What this design does NOT do

- Does not add a SEL reader, verifier, or any runtime path that opens the SEL
  key. There is no current consumer, so adding one would be dead code.
- Does not change `_patch_crew_config()`, config keys, or environment variables.
- Does not touch the auth-injection or policy-signing scripts.
