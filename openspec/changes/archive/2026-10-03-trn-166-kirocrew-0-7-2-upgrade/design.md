# Design: TRN-166 KiroCrew 0.7.2 upgrade

## Sandbox: off → sandbox_allow_unsandboxed_exec

### Problem

Ghostship currently patches `"sandbox": "off"` into `config.local.json` for
every crew because Podman rootless cannot perform the user-namespace bind mounts
the sandbox requires (EPERM). In KiroCrew 0.7.0, the text-based credential gate
was removed — bind masks are now the **only** fence. With `sandbox: off` there
is no credential protection at all.

### Solution

KiroCrew 0.7.0 introduced `agent.sandbox_allow_unsandboxed_exec: true` as an
explicit opt-in for hosts that cannot sandbox. Set this instead of `sandbox: off`.

Find the config patch location in `scripts/install.sh`:
```bash
grep -n "sandbox" scripts/install.sh
```

Replace (exact syntax depends on current patch code):
```json
"sandbox": "off"
```
with:
```json
"sandbox_allow_unsandboxed_exec": true
```

Verify the agent starts after the change on academy:
```bash
# After ./install.sh rebuild, launch a crew and check logs
./install.sh && ghostship status
```

## Cron policy vetting

In 0.7.0, cron jobs are re-vetted against current policy at fire time. Any
cron created under a more permissive policy will fail silently if the policy
has since tightened.

### Audit checklist

For each crew cron definition:
1. Captain check-in (Raven, recurring): confirm `agent.raven` still has
   permission to read mailboxes and spawn messages.
2. Raven patrol: same permissions check. Add `minimal_context: true` for cost.
3. Heartbeat (if present): confirm it still fires cleanly.

### minimal_context

0.7.0 added `minimal_context` on cron jobs. Set this on all polling/scanning
crons (Raven, heartbeat) to reduce token cost. Locate where these are
created in the transport or install script and add the flag.

## orchestrator.max_plan_duration_seconds

New in 0.7.0, defaults to 7200 (2h). Long SDD runs (Spectre → Ghost → Banshee
→ Reaper) can exceed 2h on large codebases. Set to 14400 (4h) or higher.

Location: the config patch in `scripts/install.sh` or the base config applied
by the transport. Confirm the key path:
```bash
grep -r "max_plan_duration" src/kiro_crew/config/ 2>/dev/null | head -5
# (run from KiroCrew repo if needed)
```

## KIRO_API_KEY removal

KiroCrew 0.7.0 scrubs `KIRO_API_KEY` from agent env. Check if it appears in:
- `scripts/install.sh` environment injection
- `transport/server.py` or any env-passing code
- Docker/Podman run commands in tests

## Resume behaviour change

Resumed sessions no longer re-inject full memory/lessons/skills. This affects:
- Raven patrol loop (runs repeatedly in the same session)
- Long-running Captain check-ins

Validation: after the upgrade, run a Captain check-in, observe that Raven still
produces a coherent patrol summary without full context re-injection.

## Files changed

| File | Change |
|------|--------|
| `crews/_base/admission/Containerfile` | Bump `FROM` to `0.7.2`, update comment |
| `scripts/install.sh` | Sandbox config, orchestrator timeout, cron minimal_context, KIRO_API_KEY removal |
| `openspec/specs/installation/spec.md` | Document new config options |
| `docs/architecture.md` | Note 0.7.2 base image |
