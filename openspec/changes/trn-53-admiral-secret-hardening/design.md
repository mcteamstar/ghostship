## Context

See proposal.md — Why for motivation.

Currently `transport/container_scripts/inject_policy.py` receives a base64-encoded JSON
payload containing `{"policy": ..., "admiral_secret": ...}` and places `admiral_secret`
directly into `admission_policy.json` under `trust_keys`. This runs inside the crew container,
so the secret ends up in a 0600 file on the home volume — readable by any process running as
the `kirocrew` user inside that container.

The `admiral_secret` is generated in `lifecycle.py:_finish_crew_setup()` at line 1208 via
`secrets.token_hex(32)`, then passed down through `_inject_policy()` to `inject_policy.py`.
It is also stored in `crews.json` (transport-side) and written to `.admiral_secret` inside
the container.

Relevant call chain:
```
_finish_crew_setup()
  → admiral_secret = secrets.token_hex(32)        # line 1208
  → inject_admiral_secret.py writes .admiral_secret
  → _inject_policy(podman, container, composition, admiral_secret)  # line 1249
      → inject_policy.py inject_policy(crew_dir, policy, admiral_secret)
          → trust_keys: {"ghostship": admiral_secret}   # THE BUG
  → crews.json stores admiral_secret              # line 1293
```

## Goals / Non-Goals

**Goals:**
- `admission_policy.json` inside the container never contains `admiral_secret`
- The fix is minimal: a new key, a small signature-path change, and a registry schema addition
- Existing crews continue to function without re-injection

**Non-Goals:**
- Rotating `admiral_secret` for existing crews
- Adding a re-injection endpoint or API
- Changing `.admiral_secret` (it stays as-is; agents don't need the Admiral auth key, but
  the gateway already has its own handling for that file)
- Changing the KiroCrew gateway API or container image

## Decisions

### Decision: Generate policy_signing_key as a separate secret at crew creation

**Chosen:** `policy_signing_key = secrets.token_hex(32)` generated in `_finish_crew_setup()`
immediately after (or alongside) `admiral_secret`. It is passed to `_inject_policy()` instead
of `admiral_secret`.

**Alternatives considered:**
- _Derive from admiral_secret (e.g. HKDF):_ Would reduce key storage to one field, but
  derivation means knowing `admiral_secret` still implies knowing `policy_signing_key` —
  defeating the separation goal if the derivation is known.
- _Use a fixed transport-level key:_ Simpler, but means all crews share the same signing key;
  a compromised one crew leaks the key for all. Per-crew key is strictly better.

**Rationale:** Independent generation means compromising the policy signing key (e.g. via a
container escape) doesn't hand the attacker the Admiral auth secret, and vice versa.

---

### Decision: Reuse policy_signing_key across container restarts (no rotation)

**Chosen:** Generate once at crew creation; reuse for the life of the crew. The
`policy_signing_key` is stored in `crews.json` alongside `admiral_secret`.

**Why not rotate on restart?**
The policy files (`security_policy.json`, `admission_policy.json`) live on the home volume,
which persists across restarts. If the key in `crews.json` rotated at restart but the files
on disk did not, the gateway would reject the policy on the next boot. Re-injecting fresh
files on every restart would work but adds complexity, latency, and a new failure mode.
Rotation-at-recreate (the crew destroy/recreate cycle) is sufficient — it already triggers
full re-injection.

**Risk:** A long-lived crew accumulates risk that `policy_signing_key` is stolen from the
home volume over its lifetime. Accepted for now — this is the same risk profile as the
current `admiral_secret`-in-trust_keys situation, and the fix still improves it by isolating
the blast radius.

---

### Decision: Store policy_signing_key in crews.json (no new secret store)

**Chosen:** Add `policy_signing_key` as a plain field in the `crews.json` registry entry,
exactly like `admiral_secret`.

**Risk assessment:** `crews.json` is transport-side only — it never enters the container.
Both `admiral_secret` and `policy_signing_key` live in it. Storing `policy_signing_key`
there introduces no new risk profile: an attacker who can read `crews.json` can already
read `admiral_secret`. The threat we are closing is the container-side exposure of
`admiral_secret` via `admission_policy.json`, not the transport-side storage.

---

### Decision: Change inject_policy.py interface: rename argument from admiral_secret to policy_signing_key

**Chosen:** The `inject_policy()` Python function and its callers change the parameter name
and semantics. The base64 payload key changes from `"admiral_secret"` to
`"policy_signing_key"`.

**Why not keep admiral_secret as a parameter name?**
Naming is the contract. If the parameter is still called `admiral_secret` but now receives a
different key, future readers will assume the Admiral secret flows through and re-introduce
the bug. Renaming makes the boundary explicit.

---

### Decision: Migration — no forced re-injection for existing crews

**Chosen:** Existing live crews are left as-is. Their `admission_policy.json` continues to
use the old `trust_keys` format (keyed by `admiral_secret`). The old format still validates
correctly in KiroCrew; it just contains the wrong secret in the wrong key.

**Why not re-inject on first access?**
Re-injection requires the crew container to be running and the policy files to be rewritten
atomically. It also means the transport needs to detect "old format" at runtime, generating
churn for a security fix that only applies to future crews. The incremental risk from leaving
existing crews alone is low: they already had `admiral_secret` in `trust_keys`, and the fix
only prevents the exposure for new crews. The improvement takes full effect once all crews
are recreated (natural turnover).

**Migration path for operators who want immediate hardening:** destroy and recreate the crew.
No data is lost for stateless crews; for stateful crews the operator can export first.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| `policy_signing_key` stolen from `crews.json` lets attacker forge policies for that crew | Same risk as `admiral_secret` today; transport-side file is outside the container threat model |
| Long-lived crews never get the hardening benefit until recreated | Acceptable; full coverage after natural turnover; operator can force recreate |
| Renaming the payload key (`admiral_secret` → `policy_signing_key`) breaks any out-of-band caller that constructs the payload manually | The payload is internal to `lifecycle.py`; there is no external caller |
| Two separate `secrets.token_hex(32)` calls at crew creation adds ~1ms | Negligible |

## Migration Plan

1. **Deploy:** New transport with this change deployed as normal. No flag day.
2. **New crews:** Immediately get the hardened format — `policy_signing_key` in `trust_keys`,
   `admiral_secret` absent from `admission_policy.json`.
3. **Existing crews:** Continue running unaffected. Their `admission_policy.json` retains the
   old format; the gateway still validates it (KiroCrew's `trust_keys` API is stable).
4. **Full coverage:** Achieved after all existing crews are destroyed and recreated (natural
   churn, or operator-initiated if urgency demands).
5. **Rollback:** Revert the transport deploy. Old crews are unaffected. New crews created
   after rollback will revert to the old format.

## Open Questions

None — all design-level questions resolved above.
