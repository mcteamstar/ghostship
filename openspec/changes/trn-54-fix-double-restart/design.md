## Context

`_ensure_crew_running` in `transport/server.py` is the hot path for every tool call against a stopped crew. It currently follows this sequence when a crew needs to wake:

```
_patch_crew_config    ← writes spawn_min_memory_gb=0 to config.json (workaround)
container_start
_wait_gateway         ← wait up to 30s
_patch_crew_config    ← (missing — this is what was originally intended)
container_stop
container_start
_wait_gateway         ← wait up to 30s again
_mint_cookie
```

The workaround comment says: patch config, then bounce the gateway so it re-seeds config.json before the loader runs. The intent is to ensure KiroCrew reads the patched config on startup. But the current code does the first `container_start` before patching, which means the first `_wait_gateway` is wasted — the gateway that just started has the wrong config. It then stops, starts again, and waits again. The fix is simply to patch before the first start.

## Goals / Non-Goals

**Goals:**
- Reduce wake latency by eliminating one full stop/start/wait cycle (~30–45 s)
- Keep the KiroCrew spawn_min_memory_gb workaround intact and correct
- No change to the externally observable behaviour or error surface

**Non-Goals:**
- Removing the workaround entirely (requires upstream KiroCrew fix)
- Changing the gateway dead-inside-running-container path (separate probe+stop logic above the leader section)
- Changing reconcile-restart path (already correct — patches before start)

## Decisions

**Patch before start, not after.** The KiroCrew config loader reads config.json at gateway boot. Patching after the gateway has started is too late — the loader has already run. Patching before `container_start` ensures the loader sees the patched value on its first and only run, so only one start/wait cycle is needed.

Alternative considered: write the config into the container image. Rejected — the workaround is temporary and image-level changes require a full rebuild.

Alternative considered: use `podman exec` to hot-patch the config after start without a bounce. Rejected — KiroCrew does not reload config at runtime; a restart is still required.

**Keep `_patch_crew_config` call in place.** The function is idempotent and cheap. Calling it unconditionally before start is safe regardless of whether the container has been patched before — it overwrites the same file with the same value.

## Risks / Trade-offs

**[Risk] `_patch_crew_config` may fail before the container has started** — `_patch_crew_config` uses `podman exec` against the container. A stopped container cannot exec. Mitigation: `_patch_crew_config` must switch to writing the config via the volume mount directly, or the patching must happen via a different mechanism.

This is the key design constraint. Looking at `_patch_crew_config`:
- It uses `podman exec` to write `config.json` inside a running container
- A stopped container cannot exec

**Resolution:** Instead of using `podman exec`, write the config by mounting the volume directly using `podman unshare` + volume path, or by starting the container with a short-lived exec that writes the file. The cleanest option given the existing podman client API is to start the container, patch via exec, then let it continue — but the gateway will already be loading.

Actually the simplest fix: start the container in a state where the gateway hasn't launched yet, patch, then start the gateway. But KiroCrew starts the gateway automatically on container start.

**Revised approach:** Use `podman run --rm` against the crew volume to write the file before starting the crew container, bypassing exec entirely. This is volume-level file I/O independent of container state.

Or: accept one start, exec-patch, and restart — but reduce from two full `_wait_gateway` calls to one by skipping the wait on the first start (just long enough to exec, ~2–3 s), then restart and do the real wait.

The cleanest is: `container_start` (no gateway wait) → immediate `_patch_crew_config` via exec (the process is up, KiroCrew may not have seeded config yet) → `container_stop` → `container_start` → `_wait_gateway`. This removes one `_wait_gateway` call (30 s savings) while keeping the same number of start/stop cycles. This is what the code was probably intended to do.

Simplest correct fix: remove the first `_wait_gateway` call (it serves no purpose if we're going to stop anyway), keep the patch-and-bounce, save ~30 s.

## Migration Plan

Single-file change to `transport/server.py`. No migration needed — the change only affects the restart sequence, which is transparent to callers. Deploy via normal `install.sh` re-run.

## Open Questions

None — the approach is clear. The simplest correct fix (remove the first `_wait_gateway`, keep patch-and-bounce) is straightforward and saves ~30 s per wake without changing the number of container lifecycle transitions.
