## Context

`_ensure_crew_running` is the hot path for every tool call against a stopped crew. The restart workaround uses `podman exec` to patch `spawn_min_memory_gb`, so the container must be running before `_patch_crew_config` can execute. The feasible sequence is:

```
container_start          (provisional; no gateway wait)
_patch_crew_config       (exec-patch while the container is running)
container_stop
container_start          (final start)
_wait_gateway            (the only gateway readiness wait)
_mint_cookie
```

Before this change, `_wait_gateway` also ran immediately after the provisional start. That wait was discarded when the workaround stopped the container, so it added latency without improving readiness of the final start. `_patch_crew_config` creates its destination directory when needed, so the provisional exec patch does not depend on gateway-seeded config files.

## Goals / Non-Goals

**Goals:**
- Remove the unnecessary provisional gateway wait and reduce wake latency by up to the gateway wait timeout.
- Keep the `spawn_min_memory_gb` workaround intact and correctly applied before the final gateway start.
- Preserve the externally observable recovery behavior and error surface.

**Non-Goals:**
- Removing the workaround entirely (requires an upstream KiroCrew loader fix).
- Replacing the exec-based patch with volume-level file I/O or changing the Podman client API.
- Changing the gateway-dead-inside-running-container path above the leader section.
- Changing the transport-startup reconcile path; it has its own lifecycle and remains outside this change.

## Decisions

**Keep the exec patch and bounce.** `_patch_crew_config` writes the crew configuration through `container_exec`; it cannot patch a stopped container. Retaining the provisional start, patch, stop, and final start is therefore required by the current transport API and keeps the existing workaround behavior unchanged.

**Do not wait after the provisional start.** The provisional start exists only to make `container_exec` available. Waiting for its gateway is unnecessary because that container is stopped before the crew is considered ready. The final start remains followed by exactly one `_wait_gateway` call.

**Keep `_patch_crew_config` idempotent.** The patch runs on every auto-restart and writes the operator's current configuration values. Reapplying it is safe and ensures the final gateway start sees the workaround value.

## Risks / Trade-offs

- The provisional container start must reach an exec-capable state before `_patch_crew_config` runs; this is the same operational precondition used by the prior implementation.
- The workaround still performs a stop/start bounce, so this change removes one wait but does not remove either container start. That narrower scope is intentional and avoids an unvalidated volume-mount implementation.
- If the final gateway does not become reachable, the existing recovery error is still raised and concurrent waiters are still released by the existing `finally` block.

## Verification

- The normal stopped-container unit test asserts two `container_start` calls and exactly one `_wait_gateway` call.
- The existing restart tests are run with the full unit suite to verify that no test depends on the former double-wait behavior.

## Migration Plan

No migration is needed. The change is limited to the stopped-crew recovery sequence and can be deployed through the normal transport installation path.

## Open Questions

None. The implementation and lifecycle delta intentionally describe the same exec-based sequence.
