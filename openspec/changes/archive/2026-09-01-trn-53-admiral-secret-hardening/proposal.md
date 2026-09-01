## Why

`admission_policy.json` currently stores the `admiral_secret` directly in `trust_keys` — the
same secret used to authenticate Admiral commands. An agent that can read its own
`~/.kiro/crew/admission_policy.json` (mode 0600, but accessible to the `kirocrew` user)
can recover the `admiral_secret` and forge Admiral messages. Separating the policy-signing key
from the Admiral secret closes this privilege-escalation path with minimal operational impact.

## What Changes

- A new `policy_signing_key` (32 bytes, hex) is generated at crew launch, alongside the
  existing `admiral_secret`.
- `inject_policy.py` / `_inject_policy()` in `lifecycle.py` use `policy_signing_key` to sign
  `security_policy.json` and populate `trust_keys` in `admission_policy.json`.
- `admiral_secret` is **no longer written into `admission_policy.json`**; it remains in
  `crews.json` (transport-side only) and in `.admiral_secret` inside the container.
- `policy_signing_key` is stored in `crews.json` alongside `admiral_secret` for re-injection
  on container restart.
- `crews.json` schema gains a new optional field `policy_signing_key`.
- Migration: existing crews (no `policy_signing_key` in their registry entry) continue to boot;
  their `admission_policy.json` retains the old format until the crew is re-created or a
  re-injection command is issued.

## Capabilities

### New Capabilities

_(none — both modified capabilities already have specs)_

### Modified Capabilities

- `crew-governance`: The `trust_keys` value in `admission_policy.json` changes from
  `admiral_secret` to a dedicated `policy_signing_key`; the governance requirement around
  what key is placed in `trust_keys` is updated accordingly.
- `crew-auth`: No requirement-level behavior change — crew auth flow is unaffected.
  _(This capability is **not** listed for a delta spec; the change is implementation-only
  in lifecycle.py and inject_policy.py.)_

## Impact

- `transport/container_scripts/inject_policy.py` — `inject_policy()` signature changes: takes
  `policy_signing_key` instead of `admiral_secret`.
- `transport/lifecycle.py` — `_inject_policy()` generates and passes `policy_signing_key`;
  `_finish_crew_setup()` stores it in `crews.json`.
- `crews.json` — new optional field `policy_signing_key` per crew entry.
- No change to the KiroCrew gateway API, container image, or external callers.
- Existing crews: tolerated at runtime; old `trust_keys` format stays until crew recreation.
