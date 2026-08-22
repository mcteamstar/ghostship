# Design — trn-18-operator-tier

## Overview

The transport injects two files into each crew container during
`_finish_crew_setup`:

1. `~/.kiro/crew/security_policy.json` — governance ceiling, HMAC-signed
2. `~/.kiro/crew/admission_policy.json` — requires signature verification

Policy content is rendered from templates in `academy/policies/` keyed by
composition. The Admiral's signing key (`admiral_secret`) is reused from the
registry — one key per crew, two uses (mail signing + policy signing).

## File Layout

```
academy/
  policies/
    default.json       ← kirocrew composition (all non-research crews)
    research.json      ← kirocrew-research composition (broader egress)

transport/server.py
  _inject_policy()     ← new helper: render, sign, write both files
  _finish_crew_setup() ← calls _inject_policy after admiral_secret is set

openspec/specs/
  crew-governance/
    spec.md            ← new spec
```

## Policy Template Structure

Each template is a JSON object with a `version` field and the standard
KiroCrew security policy fields. Templates are read from `academy/policies/`
mounted at `/policies/` in the transport container (same mechanism as
`/steering/` and `/agents/`).

If no template matches the composition, the `default.json` template is used.

### `academy/policies/default.json`

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

Container is the security boundary. Default policy covers only platform
integrity: block control-plane escape paths (`git push`, `gh`, pipe-to-shell)
and messaging integrations. No filesystem bounds, sandbox level, or network
egress restriction in the default.

### `academy/policies/research.json`

Same as default — research crews get the same open defaults. Included as a
template for operators who want to customise research crew behaviour (e.g.
allow `gh` for report publishing, or add `filesystem.write` bounds).

### `academy/policies/strict.json` (example custom policy)

Not shipped by default — documented as an example for operators who want
tighter controls:

```json
{
  "version": "1",
  "sandbox": { "min_level": "standard" },
  "filesystem": {
    "write": {
      "mode": "allow",
      "prefixes": ["~/workplace", "~/.kiro", "~/.local/share/kiro-cli", "/var/mail", "/tmp"]
    }
  },
  "commands": {
    "deny": ["^git push", "^git remote add", "^gh ", "^curl.*\\|.*sh", "^wget.*\\|.*sh",
             "^sudo ", "^rm -rf /"]
  },
  "channels": {
    "deny": ["slack", "discord", "telegram", "teams", "webex", "wecom", "wechat"]
  },
  "network": { "egress": { "mode": "allow" } }
}
```

## `_inject_policy()` implementation

```python
def _inject_policy(
    podman: PodmanClient,
    container: str,
    composition: str,
    admiral_secret: str,
) -> str:
    """Inject security_policy.json and admission_policy.json into the crew.

    Returns the policy version string for registry storage.
    """
    # 1. Load template
    policy_template_path = Path("/policies") / f"{composition}.json"
    if not policy_template_path.exists():
        policy_template_path = Path("/policies/default.json")
    policy = json.loads(policy_template_path.read_text())
    policy_body = json.dumps(policy, indent=2, sort_keys=True)
    policy_version = policy.get("version", "1")

    # 2. Compute signature over canonical (sorted) policy body
    sig = hmac.new(
        admiral_secret.encode(),
        policy_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # 3. Build admission policy
    admission = {
        "require_policy_signature": True,
        "trust_keys": [{"id": "admiral", "key": sig}],
    }
    admission_body = json.dumps(admission, indent=2)

    # 4. Write both files via container_exec
    policy_b64 = base64.b64encode(policy_body.encode()).decode()
    admission_b64 = base64.b64encode(admission_body.encode()).decode()

    script = f"""\
import base64, pathlib, os
crew_dir = pathlib.Path('/home/kirocrew/.kiro/crew')
crew_dir.mkdir(parents=True, exist_ok=True)

policy_path = crew_dir / 'security_policy.json'
fd = os.open(str(policy_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, base64.b64decode('{policy_b64}')); os.close(fd)

admission_path = crew_dir / 'admission_policy.json'
fd = os.open(str(admission_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, base64.b64decode('{admission_b64}')); os.close(fd)

print('policy injected version={policy_version}')
"""
    result = podman.container_exec_checked(container, ["python3", "-c", script])
    logger.info("Injected security policy for %s: %s", container, result.strip())
    return policy_version
```

## `_finish_crew_setup()` changes

Add `_inject_policy` call after `admiral_secret` is set and before the
built-in agent removal step:

```python
# After: admiral_secret = secrets.token_hex(32) + inject to container + save to registry
# New:
policy_version = _inject_policy(podman, container, composition, admiral_secret)

# Store policy_version in registry alongside admiral_secret
with _registry_lock:
    reg = _load_registry()
    if crew_id in reg["crews"]:
        reg["crews"][crew_id]["policy_version"] = policy_version
        _save_registry(reg)
```

## `launch()` response changes

Add `policy_version` to the returned dict:

```python
return {
    "crew_id": crew_id,
    "container": container,
    "gateway_url": crew_url,
    "status": "ready",
    "policy_version": policy_version,  # new
}
```

## `crews()` changes

Add `policy_version` per crew entry from the registry, alongside
`gateway_healthy`. Absent for crews launched before this change (no backfill).

## Transport container: mount `academy/policies/`

`academy/policies/` must be bind-mounted into the transport container the
same way `academy/agents/`, `academy/skills/`, and `academy/steering/` are.
Update `docker-compose.yml` / `install.sh` to add the bind mount at
`/policies`.

## Security properties

| Property | Default guarantee | Available via custom policy |
|:---------|:-----------------|:---------------------------|
| Control-plane escape | `git push`, `gh`, pipe-to-shell denied | — (already default) |
| Channel isolation | Messaging integrations blocked | — (already default) |
| Policy integrity | HMAC signature; tampered policy = boot failure | — (already default) |
| Key custody | `admiral_secret` in registry; agent has no path to it | — (already default) |
| Sandbox floor | Not set by default | `sandbox.min_level` in custom policy |
| Filesystem bounds | Not set by default | `filesystem.write` prefixes in custom policy |
| Network egress | Open by default | `network.egress` mode in custom policy |

The container is the security boundary. Default controls target platform
integrity, not agent access restriction. Operators add controls via custom
composition policies.

## What this does NOT do

- Does not restrict `network.egress` by default
- Does not set `sandbox.min_level` by default
- Does not set `filesystem.write` bounds by default
- Does not address `admiral_secret` plaintext-in-registry (TRN-16)
- Does not add per-crew policy rotation (policy is set at launch)
- Does not add a policy update path for running crews (nuke/relaunch for changes)

## Implementation notes

**`admission_policy.json` schema:**
The `trust_keys: [{id, key}]` structure is derived from the Wraith research
report but not verified against the actual KiroCrew schema. During Task 3
implementation, verify the exact field names against the KiroCrew source
before committing to this structure. If the schema differs, update the design
accordingly.

## Files Changed

| File | Change |
|:-----|:-------|
| `academy/policies/default.json` | New — baseline policy for kirocrew composition |
| `academy/policies/research.json` | New — research composition variant |
| `transport/server.py` | `_inject_policy()`, `_finish_crew_setup()`, `launch()`, `crews()` |
| `transport/test_transport.py` | Policy injection tests |
| `docker-compose.yml` | Add `/policies` bind mount |
| `install.sh` | Add `/policies` bind mount |
| `openspec/specs/crew-governance/spec.md` | New spec |
| `docs/architecture.md` | Document operator tier usage |
| `docs/auth.md` | Document policy signing |
