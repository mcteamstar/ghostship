# Delta Spec — TRN-221 SEL key moved to `trust/`

## Summary of behaviour change

| Aspect | Before (KiroCrew 0.8.0) | After (KiroCrew 0.9.0) |
|---|---|---|
| SEL signing key location | gateway-internal, pre-0.9.0 location | `$KIROCREW_HOME/trust/` (new consolidated trust root) |
| Who reads the SEL key | KiroCrew gateway only | KiroCrew gateway only |
| ghostship code touching the SEL key | none | none |
| ghostship effective behaviour | unchanged | unchanged |

The SEL key move is a **gateway-internal relocation**. From ghostship's
perspective there is no observable behaviour change in the current codebase: no
ghostship surface opens, signs with, or verifies against the SEL key at any
path.

## Interface / configuration after the change

### No new or modified ghostship config keys

This change introduces **no** new config keys in ghostship's
`config.local.json`, no new environment variables (`GA_CREW_*`), and no changes
to `_patch_crew_config()` in `transport/lifecycle.py`. The SEL key is never
surfaced through ghostship configuration.

### Trust-root convention (forward-looking)

The behavioural contract this change pins for ghostship is a **convention**, not
a config key:

> Any ghostship code that reads KiroCrew-managed SEL/audit signing material MUST
> resolve it under `$KIROCREW_HOME/trust/` and MUST NOT hardcode a pre-0.9.0
> SEL path.

Today no such code exists, so the convention is enforced by documentation and
by the implementation tasks' verification step rather than by a code path.

### Distinction from ghostship's own signing keys (unchanged)

The following remain exactly as they are and are explicitly **not** the SEL key:

- `.local_secret` — the gateway's internal-API secret, parallel to the
  dashboard cookie written by `_write_dashboard_cookie()`
  (`transport/lifecycle.py`). Unchanged.
- `policy_signing_key` / `trust_keys["ghostship"]` — ghostship's own HMAC key
  for `security_policy.json` and `admission_policy.json`, written by
  `inject_policy()` (`transport/container_scripts/inject_policy.py`). This is a
  ghostship-managed key written into the crew's `.kiro/crew` directory, NOT the
  KiroCrew gateway's SEL key, and is unaffected by the SEL relocation.

## Acceptance criteria

- A grep of `transport/` for SEL/trust-key path literals against the running
  `0.9.0-insider.4` image confirms zero ghostship references to the SEL key.
- The crew boots on `0.9.0-insider.4` and SEL audit entries are produced by the
  gateway without any ghostship intervention (negative confirmation: nothing in
  ghostship needed to change for SEL signing to work).
- A standing-orders / docs note records the `$KIROCREW_HOME/trust/` convention
  for any future SEL-reading feature.
