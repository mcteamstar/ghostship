# TRN-149: Upgrade crew base image from KiroCrew 0.5.0 to 0.6.0

## Summary

Bump `kc_base_image` from `ghcr.io/kirodotdev/kirocrew:0.5.0` to
`ghcr.io/kirodotdev/kirocrew:0.6.0` and update every transport-side patch,
constant, and comment that references 0.5.0 behaviour so ghostship keeps
working correctly against the new runtime.

KiroCrew 0.6.0 shipped 2026-09-11. The release is the largest in the project's
history, covering multi-machine crew federation, selectable agent harnesses,
large timeout expansions, sandbox hardening changes, and a Python 3.12 floor.
The changes that matter to ghostship are narrow but require careful handling.

---

## What changed in 0.6.0 (ghostship-relevant subset)

### A. Timeouts expanded

| Config key | 0.5.0 ceiling | 0.6.0 ceiling |
|---|---|---|
| `agent.subagent_timeout_secs` | 1800 s (30 min) | 10800 s (3 h) |
| `agent.subagent_max_turns` | 200 | 1000 |
| `agent.chat_turn_timeout_secs` | 7200 s | 14400 s |

Ghostship currently pins `GA_SUBAGENT_TIMEOUT_SECS=3600` and
`GA_SUBAGENT_MAX_TURNS=200` in `_patch_crew_config`. These explicit overrides
are still valid in 0.6.0 (the ceiling went up, the config keys did not change),
so no forced change is required.  However 0.6.0's higher ceiling means we can
optionally raise defaults to match the new runtime capability.

### B. Sandbox default changed: `off` → `auto`

**This is the most important breaking change for ghostship.**

In 0.5.0 ghostship already patched `"sandbox": "off"` into every crew config
(TRN-125 / existing crew-lifecycle spec) precisely because under Podman rootless
the default `"auto"` mode attempted an `MS_REMOUNT|MS_BIND|MS_RDONLY` bind-mount
that was denied (EPERM) and caused every spawn to fail with `AcpRuntimeDead rc=1`.

In 0.6.0 the sandbox default changed from `"off"` to `"auto"` on any capable
host (the 0.6.0 release notes say: "A host that cannot sandbox refuses to run
the agent: armv7l, riscv64, ppc64le and s390x Linux, a libc without `prctl`, and
Windows with Kiro CLI's internal sandbox off all fail closed unless you set
`agent.sandbox` to `off` or `agent.sandbox_allow_unsandboxed_exec` to `true`").

The net effect for ghostship is: **the existing `"sandbox": "off"` patch is still
required for Podman rootless deployments on amd64/arm64**.  Without it every crew
spawn will fail.  The patch must remain in `_patch_crew_config`.

An explicit comment in `lifecycle.py` currently says the `"sandbox": "off"` was
needed from 0.5.0 onward; that comment must be updated to reflect 0.6.0.

### C. `agent.session_control` is now on by default

0.6.0 introduces `agent.session_control` (agents can start, revise, and stop
monitoring loops from within a session). It defaults to `true`. Ghostship does
not need to disable this; the crew's monitoring tooling (monitor_start etc.) is
already used by agents and this is additive.

No patch required unless there is a reason to opt out.

### D. `agent.subagent_max_turns` ceiling lifted to 1000

Ghostship currently hard-pins `subagent_max_turns=200` in `_patch_crew_config`.
In 0.6.0 the KiroCrew gateway raises the UI cap to 1000.  The current transport
default of 200 remains valid.  The spec comment "UI cap 200" in `lifecycle.py`
becomes stale and should be updated to reflect the new cap of 1000.

### E. Login container: gateway loop watchdog behaviour

The 0.5.0 release notes said the gateway would "stall on AcpAuthRequired and be
killed by the 0.5.0 loop watchdog after ~35s".  Ghostship's login flow comment
in `_start_login_container` references this explicitly.  In 0.6.0 the watchdog
behaviour is likely still present (it is part of the startup sequence), but the
exact timing and description may differ.  A low-risk update: remove the "0.5.0
loop watchdog after ~35s" specificity from the comment.

### F. `resumed sessions no longer re-inject their full memory, lessons and skills block`

This is a pure KiroCrew-side improvement and requires no ghostship transport
changes.  The reduction in resumed-session context overhead is automatically
inherited by all crew sessions.

### G. Sub-agent context scoping (new `include_memory`, `include_lessons`, `include_project` flags on `spawn_run`)

0.6.0 adds context-scoping flags to subagent dispatch.  These are exposed
through the KiroCrew agent's `spawn_run` tool and do not affect the transport
dispatch API (`POST /api/spawn`). No transport changes required.

### H. Python 3.12 floor (host-side only)

The Python 3.12 requirement applies to the KiroCrew *desktop/CLI install*, not
to the container image.  The crew containers run python inside the image;
ghostship's transport is Python already.  This has no direct impact on the
transport or the crew image itself.

### I. `/api/ready` readiness endpoint behaviour unchanged

`_wait_gateway` polls `/api/ready` for a 200 response.  The endpoint is
auth-bypassed in 0.6.0 and the semantics (200 = startup_complete) are
unchanged.

---

## Why upgrade now

1. Security: 0.6.0 includes multiple security fixes (CSE scan findings, sandbox
   hardening, loopback secret leakage fix, audit log hardening).
2. Capability: long-running sub-agents (up to 3 h, 1000 turns) dramatically
   increase the complexity of tasks that can be handled without manual
   intervention.
3. Correctness: the existing lifecycle spec comments referencing 0.5.0 behaviour
   will become misleading drift if left unupdated.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `sandbox` patch lost in a merge → all spawns fail | Low | Spec scenario preserved; test coverage exists for AcpRuntimeDead rc=1 |
| Comment drift misleads future developers | Low | Update comments as part of this change |
| Unpublished image `ghcr.io/kirodotdev/kirocrew:0.6.0` at time of deploy | Medium | Verify image pull before deploying; CI should pull and test |
| Login container watchdog timing change breaks `_start_login_container` | Low | The 35s window is already generous; login flow uses a 45s PTY read timeout |
| New `session_control=true` default causes unexpected agent behaviour | Very Low | Feature is additive; existing agents are unaffected unless they call the new tool |

---

## Out of scope

- Raising `GA_SUBAGENT_TIMEOUT_SECS` or `GA_SUBAGENT_MAX_TURNS` defaults.
  The image bump alone unlocks the higher ceiling; a separate change can tune
  defaults if desired.
- Enabling new 0.6.0 features (remote crew federation, selectable harnesses,
  etc.) — those require their own design work.
- Changing the `sandbox` strategy (e.g. exploring `sandbox_allow_unsandboxed_exec`
  as an alternative).
