# Delta Spec: crew-lifecycle — KiroCrew 0.6.0 upgrade (TRN-149)

This delta overrides only the requirements from the main
`openspec/specs/crew-lifecycle/spec.md` that are affected by the 0.6.0 upgrade.
All other requirements remain unchanged.

---

## Requirement: Base image version

The transport SHALL use `ghcr.io/kirodotdev/kirocrew:0.6.0` as the default value
of `KC_BASE_IMAGE` (both the `Config` dataclass field and the `from_env()`
fallback). The version string SHALL appear in exactly two places in
`transport/config.py` and nowhere else as a hardcoded literal.

**Supersedes**: The implicit version constraint in the existing
`kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.5.0"` field.

### Scenario: Default base image is 0.6.0

- **WHEN** `Config.from_env()` is called without `KC_BASE_IMAGE` set
- **THEN** `cfg.kc_base_image` is `"ghcr.io/kirodotdev/kirocrew:0.6.0"`

### Scenario: KC_BASE_IMAGE override is respected

- **WHEN** `KC_BASE_IMAGE=ghcr.io/myorg/custom:latest` is set
- **THEN** `cfg.kc_base_image` is `"ghcr.io/myorg/custom:latest"`

---

## Requirement: Crew config patches sandbox=off for Podman rootless compatibility (updated for 0.6.0)

The `_patch_crew_config` function SHALL write `"sandbox": "off"` into the
`agent` block of `config.local.json`. This disables the KiroCrew inner namespace
sandbox, which performs a `MS_REMOUNT|MS_BIND|MS_RDONLY` bind-mount to seal
credential directories read-only and exits rc=1 (fail-closed) if that mount
fails.

In KiroCrew 0.5.0 this behaviour was introduced. In KiroCrew 0.6.0 the sandbox
mode `"auto"` became the explicit gateway default (previously the default was
named `"off"` on hosts that did not support namespaces, but is now `"auto"` on
all capable hosts). Under Podman rootless the kernel denies the remount with
EPERM because user namespaces inside rootless containers lack the required mount
privilege; without this override every agent spawn fails with `AcpRuntimeDead
rc=1`. The `"sandbox": "off"` value is a pre-existing KiroCrew config option —
it short-circuits `detect_backend()` to return `"none"` before the mount is
attempted. The Podman container itself remains the OS-level isolation boundary.

**Supersedes**: The version-specific text in the main spec's sandbox
requirement referencing "0.5.0" exclusively.

### Scenario: Crew spawns succeed on Podman rootless with 0.6.0 image

- **WHEN** a crew is launched using `ghcr.io/kirodotdev/kirocrew:0.6.0` on a
  Podman rootless host
- **THEN** `config.local.json` contains `"sandbox": "off"` inside the `agent` block
- **AND** agent dispatches complete without `AcpRuntimeDead: process exited (rc=1)`

### Scenario: sandbox=off does not affect authentication or governance

- **WHEN** `"sandbox": "off"` is patched into the crew config
- **THEN** kiro-cli authentication, model selection, and all governance policy
  checks remain fully enforced
- **AND** only the inner Linux user-namespace bind-mount step is bypassed

---

## Requirement: subagent_max_turns ceiling documentation

The `_patch_crew_config` function writes `GA_SUBAGENT_MAX_TURNS` (default 200)
into `config.local.json` as `subagent_max_turns`. This value is subject to a
KiroCrew-enforced ceiling:

- KiroCrew 0.5.0: ceiling was 200
- KiroCrew 0.6.0: ceiling raised to 1000

The transport default of 200 is within the 0.6.0 ceiling. Operators who wish to
allow longer-running tasks may set `GA_SUBAGENT_MAX_TURNS` up to 1000 without
a KiroCrew validation error.

**Supersedes**: Any inline comment or scenario text that refers to the ceiling
as "UI cap 200".

### Scenario: Default subagent_max_turns is within 0.6.0 ceiling

- **WHEN** `GA_SUBAGENT_MAX_TURNS` is unset
- **THEN** `subagent_max_turns` is patched to 200, which is within the
  KiroCrew 0.6.0 ceiling of 1000

### Scenario: GA_SUBAGENT_MAX_TURNS up to 1000 is accepted

- **WHEN** `GA_SUBAGENT_MAX_TURNS=1000`
- **THEN** `subagent_max_turns` is patched to 1000 without a gateway rejection

### Scenario: GA_SUBAGENT_MAX_TURNS above 1000 behaviour

- **WHEN** `GA_SUBAGENT_MAX_TURNS=2000`
- **THEN** the transport writes 2000 to the config; KiroCrew 0.6.0 may clamp
  or reject this at runtime. Operators should stay within the documented ceiling.

---

## Requirement: subagent_timeout_secs ceiling (unchanged; documented for 0.6.0)

In KiroCrew 0.6.0 the `subagent_timeout_secs` ceiling was raised to 10800 s
(3 h). The transport default `GA_SUBAGENT_TIMEOUT_SECS=3600` (1 h) is within
this ceiling and does not require a change. Operators may raise this up to
10800 without a KiroCrew validation error.

**No spec text changes required** — this is informational only and consistent
with the main spec's existing timeout requirement.
