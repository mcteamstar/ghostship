# TRN-221 — SEL key moved to `trust/` (KiroCrew 0.9.0)

- **Plane ticket:** TRN-221
- **Upgrade context:** ghostship on KiroCrew `0.8.0` → `0.9.0-insider.4`
- **Upstream change:** PR #2421 / issue #1881 — "Re-vet cron jobs at fire time; SEL key moved to `trust/`"
- **Priority verdict (from Wraith research report, `kc-090-research.md`):**
  **BEHAVIOUR CHANGE — LOW IMPACT.** Not a hard break. Indirect impact only;
  no code change is strictly required for the upgrade to succeed.

## What is changing

In KiroCrew 0.9.0 the Security Event Log (SEL) signing key is relocated into a
new `trust/` directory under the gateway's KiroCrew home
(`$KIROCREW_HOME/trust/`). The SEL key is an internal KiroCrew credential used
by the gateway to sign security-audit entries. The move consolidates signing
material under one trust root, alongside the other verification keys the 0.9.0
governance work introduced.

## Why this proposal exists

The SEL key path change is **internal to the KiroCrew gateway process**.
Ghostship's transport and container scripts do not read, verify, or reference
the SEL key at any hardcoded path.

A source audit of `transport/` (grep for `sel_key`, `SEL_KEY`, `sel.key`,
`/sel`, `trust/`, `keypair.json`, `session_key`) returned **no matches** to the
SEL key or to a `trust/` path. The nearest signing-related code in ghostship is
unrelated:

- `transport/lifecycle.py:321` — references `.local_secret`, the gateway's own
  **internal-API secret** written by the gateway at startup. This is not the SEL
  key and is not moved by this change.
- `transport/container_scripts/inject_policy.py` — signs
  `security_policy.json` / `admission_policy.json` with a dedicated
  `policy_signing_key` (and stores it under `trust_keys` in
  `admission_policy.json`). This is ghostship's **own** HMAC policy-signing key,
  distinct from the KiroCrew SEL key, and is unaffected.

Because ghostship never touches the SEL key, the upgrade works unchanged today.
This proposal therefore delivers **a verification gate plus a forward-looking
guardrail**, not a refactor:

1. Verify, against the `0.9.0-insider.4` image, that no ghostship surface
   depends on the old SEL key location (confirm the research finding against the
   actual target image rather than against 0.8.0 only).
2. Record a standing rule so that any **future** TRN that adds SEL-reading
   behaviour (e.g. audit-log monitoring) is written against
   `$KIROCREW_HOME/trust/` from the start, never the pre-0.9.0 location.

## Affected ghostship files / functions

No code change is required to the following; they are listed because they are
the surfaces the research report audited and the ones a reviewer should
re-confirm:

- `transport/lifecycle.py` — `_crew_api()`, `_write_dashboard_cookie()`,
  `.local_secret` reference (line ~321). Uses the dashboard-cookie and
  internal-API-secret paths; neither is the SEL key.
- `transport/container_scripts/inject_auth.py` — `inject_auth()`. Writes
  `auth_kv` rows only; no SEL/trust reference.
- `transport/container_scripts/read_auth.py` — `read_auth()`. Reads `auth_kv`
  rows only; no SEL/trust reference.
- `transport/container_scripts/inject_policy.py` — `sign_policy()`,
  `inject_policy()`. Uses ghostship's own `policy_signing_key`, not the SEL key.

## Out of scope

- No new SEL-reading feature is introduced here.
- The internal-API-secret (`.local_secret`) handling is unchanged.
- The policy-signing path (`inject_policy.py` / `trust_keys` in
  `admission_policy.json`) is unchanged.
