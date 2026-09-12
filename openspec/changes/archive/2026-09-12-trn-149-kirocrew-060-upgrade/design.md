# TRN-149 Design: KiroCrew 0.6.0 Upgrade

## Scope

Exactly three files require code changes. Everything else is comment / spec
updates that carry no behavioural risk.

```
transport/
  config.py          ← bump KC_BASE_IMAGE default
  lifecycle.py       ← update stale comments (sandbox, watchdog, max_turns cap)
openspec/
  specs/crew-lifecycle/spec.md   ← update spec text (delta spec below)
```

No new config fields, no new environment variables, no API changes.

---

## D1: `transport/config.py` — bump `kc_base_image`

**Location**: `Config` dataclass field, line ~`kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.5.0"`

**Change**:
```python
# Before
kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.5.0"

# After
kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.6.0"
```

**And the matching `from_env()` default**:
```python
# Before
kc_base_image=os.environ.get("KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew:0.5.0"),

# After
kc_base_image=os.environ.get("KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew:0.6.0"),
```

These are the only two occurrences of the version string in `config.py`.

---

## D2: `transport/lifecycle.py` — update stale comments

### D2a: `_patch_crew_config` — sandbox comment

Current comment (line block referencing 0.5.0):
```python
# ``sandbox="off"`` disables the kiro-cli inner namespace sandbox.
# The config key and value are not new — "off" has been valid since
# before 0.5.0. What changed in 0.5.0 is that sandbox="auto" (the
# default) now issues a MS_REMOUNT|MS_BIND|MS_RDONLY mount to seal
# credential directories read-only, and this call is fail-closed:
# kiro-cli calls sys.exit(rc=1) if the mount fails rather than
# continuing unsandboxed. Under Podman rootless the kernel denies the
# remount (errno EPERM — no seccomp allowance for MS_REMOUNT inside a
# user namespace), so every agent spawn failed with AcpRuntimeDead rc=1.
```

Updated comment:
```python
# ``sandbox="off"`` disables the kiro-cli inner namespace sandbox.
# The config key and value are not new — "off" has been valid since
# before 0.5.0. sandbox="auto" (the default since 0.6.0, and present
# in fail-closed form since 0.5.0) issues a MS_REMOUNT|MS_BIND|MS_RDONLY
# mount to seal credential directories read-only; kiro-cli calls
# sys.exit(rc=1) if that mount fails (fail-closed). Under Podman rootless
# the kernel denies the remount (errno EPERM — no seccomp allowance for
# MS_REMOUNT inside a user namespace), so every agent spawn fails with
# AcpRuntimeDead rc=1 unless this is set to "off".
# Setting "off" short-circuits detect_backend() to return "none", so the
# namespace sandbox setup (and the failing mount) are never attempted.
# The Podman container itself remains the OS-level isolation boundary.
```

### D2b: `_patch_crew_config` — `subagent_max_turns` comment

Current inline comment:
```python
"subagent_max_turns": GA_SUBAGENT_MAX_TURNS,
# ``sandbox="off"`` ...
# ... subagent_max_turns: >= 1 (UI cap 200).
```

Find the comment block above `agent_overrides` that says "UI cap 200" and
update to "UI cap 1000 (raised in KiroCrew 0.6.0)".

### D2c: `_start_login_container` — watchdog comment

Current comment:
```python
# Use the default gateway command — kirocrew-entrypoint seeds
# ~/.kiro/crew/config.json which kiro-cli requires. The gateway will
# stall on AcpAuthRequired (no auth yet) and be killed by the 0.5.0
# loop watchdog after ~35s, but GET /login polls the auth DB
# continuously and will catch a completed auth before that window.
```

Updated comment:
```python
# Use the default gateway command — kirocrew-entrypoint seeds
# ~/.kiro/crew/config.json which kiro-cli requires. The gateway will
# stall on AcpAuthRequired (no auth yet) and the loop watchdog will
# recycle it after a timeout, but GET /login polls the auth DB
# continuously and will catch a completed auth before that window.
```

---

## D3: `openspec/specs/crew-lifecycle/spec.md` — delta updates

Two spec scenarios require text updates (no behavioural change, just accuracy):

1. In the "Crew config patches sandbox=off for Podman rootless compatibility"
   requirement, the phrase "since 0.5.0" should be updated to note that the
   default is `"auto"` from 0.6.0 onward (was `"auto"` in detect in 0.5.0 but
   now is the explicit gateway default too).

2. In the `subagent_max_turns` scenario table comment referencing the "(UI cap
   200)" annotation, update to "(UI cap 1000, raised in KiroCrew 0.6.0)".

The delta spec (in this change's `specs/crew-lifecycle/spec.md`) carries only
the changed requirements.

---

## Implementation sequence

1. `transport/config.py` — bump both occurrences of `0.5.0` to `0.6.0` (D1)
2. `transport/lifecycle.py` — update three comment blocks (D2a, D2b, D2c)
3. `openspec/specs/crew-lifecycle/spec.md` delta — update two requirement blocks (D3)
4. Run tests: `python -m pytest transport/tests/ -x -q`
5. Pull the new image manually to confirm it is published:
   `podman pull ghcr.io/kirodotdev/kirocrew:0.6.0`

---

## What is explicitly NOT changing

- The `"sandbox": "off"` patch value — it remains required on Podman rootless
- All timeout defaults (`GA_SUBAGENT_TIMEOUT_SECS`, `GA_SUBAGENT_MAX_TURNS`)
- The `_patch_crew_config` structure or logic
- The login flow PTY timeouts
- Any public API or MCP tool signature
