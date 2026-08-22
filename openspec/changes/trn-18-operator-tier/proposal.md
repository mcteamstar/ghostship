## Why

Ghostship is a KiroCrew operator in the upstream architectural sense — it
controls each crew container at boot and has filesystem access to inject files
before the gateway starts. The KiroCrew operator tier is a static-file-at-boot
governance model: write config files into the container, and the gateway
enforces them as an unforgeable ceiling the agent cannot weaken. No code runs
inside the gateway; the files are the API.

Ghostship currently only uses three environment variables
(`KIROCREW_HOME`, `KIROCREW_PORT`, `KIROCREW_CORS_ORIGINS`). This leaves an
entire governance tier unused. Most significantly:

- **Nothing currently confines agents to the workspace subtree** — an agent
  could write to `~/.kiro/` itself, `/etc/`, or anywhere the container user
  can reach.
- **No sandbox floor** — the default sandbox level is `off`; an agent can
  disable the sandbox entirely via its own config.
- **No governance signing** — the upstream operator tier supports HMAC-signing
  the security policy so that a tampered policy causes a boot failure. We
  already do this for Admiral mail (TRN-1); applying the same principle to
  governance policy closes a meaningful gap.

## What Changes

### 1. Per-crew `security_policy.json`

The transport injects a `security_policy.json` into
`~/.kiro/crew/security_policy.json` in each crew container during
`_finish_crew_setup`, after the gateway is ready.

The policy is rendered from a template keyed by composition name. The default
`kirocrew` composition gets a sensible baseline policy. Other compositions
(e.g. `kirocrew-research`) can declare a looser or tighter variant via the
composition registry.

### 2. Default policy baseline (kirocrew composition)

The container is the security boundary — agents inside it are already isolated
from the host and other crews. The default policy focuses on **platform
integrity** (preventing agents from subverting the control plane) rather than
access restriction. Operators who need tighter controls can override with a
custom composition policy.

```json
{
  "version": "1",
  "commands": {
    "deny": [
      "^git push",
      "^git remote add",
      "^gh ",
      "^curl.*\\|.*sh",
      "^wget.*\\|.*sh"
    ]
  },
  "channels": {
    "deny": ["slack", "discord", "telegram", "teams", "webex", "wecom", "wechat"]
  }
}
```

`commands.deny` covers the operations that would escape the container or
inject arbitrary code: pushing to external git remotes, using the GitHub CLI
(which has network credentials), and pipe-to-shell curl/wget patterns. It does
NOT restrict filesystem writes, sandbox level, or network egress — those are
container-level concerns, not policy-level ones.

`channels.deny` blocks messaging integrations entirely — agents should not be
independently connecting to Slack, Discord, or other messaging platforms.

Operators who need tighter controls can supply a custom policy via a named
composition (e.g. `kirocrew-strict`) with additional `filesystem.write`
bounds, `sandbox.min_level`, or broader `commands.deny` patterns.

### 3. Composition-specific policy variants

The composition manifest (from `CREW_REGISTRY_PATH`) gains an optional
`security_policy` key pointing to a named policy variant. If absent, the
default `kirocrew` policy applies.

Policy variants live in a new `academy/policies/` directory. Example:

```
academy/policies/
  default.json         ← kirocrew composition baseline
  research.json        ← broader network.egress, looser filesystem.write
```

### 4. Admiral-signed policy

The transport generates a per-crew HMAC-SHA256 signature over the policy body
at injection time, using the same `admiral_secret` already stored in the
registry for that crew (introduced in TRN-1). The signature is written to
`~/.kiro/crew/admission_policy.json`:

```json
{
  "require_policy_signature": true,
  "trust_keys": [
    {
      "id": "admiral",
      "key": "<hex-hmac-sha256-of-policy-body>"
    }
  ]
}
```

This means: if the `security_policy.json` is tampered with inside the
container (e.g. by an agent that finds a path to write it), the gateway
detects the mismatch at the next reload and refuses to continue. The Admiral
holds the only valid key.

Note: `verify-admiral-sig` (TRN-1) already handles the mail signing verification
inside the container. Policy signing verification is handled by KiroCrew itself
— the transport does not need to implement the verifier.

### 5. Transport changes

In `_finish_crew_setup`:
1. Resolve the policy template for this composition.
2. Render the policy JSON.
3. Compute HMAC-SHA256 of the policy body using the crew's `admiral_secret`.
4. Write `security_policy.json` to `~/.kiro/crew/security_policy.json`.
5. Write `admission_policy.json` to `~/.kiro/crew/admission_policy.json`.

Both are injected via `container_exec` (same mechanism as auth injection and
admiral_secret injection).

### 6. `launch()` response + `crews()` add `policy_version`

Include the policy version that was applied in the `launch()` result and in
each crew's `crews()` entry, so the Admiral can verify governance state.

## Capabilities

### Modified Capabilities
- `crew-lifecycle`: `_finish_crew_setup` gains policy injection step;
  `launch()` response and `crews()` include `policy_version`.
- `crew-auth` (new spec, or extend existing): Admiral-signed policy governance
  — HMAC signing of security policy, admission_policy.json injection.

### New Capabilities
- `crew-governance`: per-crew security policies, sandbox floors, filesystem
  bounds, channel deny, command force-pins. New spec at
  `openspec/specs/crew-governance/spec.md`.

## Decisions

- Policy templates live in `academy/policies/` (alongside agents/, skills/,
  steering/) — part of the Ghost Academy curriculum, copied at launch.
- Policy signing uses the existing `admiral_secret` (not a separate key) —
  one secret per crew, used for both mail signing and policy signing.
- Default policy is intentionally open — the container is the security
  boundary. Policy controls platform integrity (control-plane escape paths)
  not agent access restriction. Operators wanting tighter controls use a
  custom composition.
- No `sandbox.min_level`, no `filesystem.write` bounds, no `network.egress`
  restriction in the default — these are available as operator options via
  custom composition policies but not imposed by default.

## Impact

- `academy/policies/default.json` — new file
- `academy/policies/research.json` — new file (looser egress variant)
- `transport/server.py` — `_finish_crew_setup`, `_inject_policy`, `launch()`,
  `crews()`
- `transport/test_transport.py` — tests for policy injection
- `openspec/specs/crew-governance/spec.md` — new spec
- `docs/architecture.md` — document operator tier usage
- `docs/auth.md` — document policy signing alongside mail signing
