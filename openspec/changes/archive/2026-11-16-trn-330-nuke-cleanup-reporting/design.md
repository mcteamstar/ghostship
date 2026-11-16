# Design

## Context

`_cleanup_crew` is shared by launch rollback and explicit `nuke`. It suppresses Podman errors because rollback may run before resources exist. `nuke` currently cannot distinguish that expected absence from failed removal.

## Goals / Non-Goals

**Goals:**
- Preserve launch rollback's best-effort behavior.
- Give explicit `nuke` a cleanup result that distinguishes complete removal from resource-removal failures.
- Attempt every resource cleanup even after an earlier operation fails.

**Non-Goals:**
- Add an orphan-resource registry or automatic retry queue.
- Change best-effort schedule cancellation or Caddy deregistration behavior.

## Decisions

- Keep `_cleanup_crew` as the best-effort rollback helper. Add a nuke-specific cleanup path that records failures from container and volume removal while attempting each remaining removal.
- Treat a 404/already-absent response as successful cleanup, consistent with the Podman client contract. Report the resource name and failed removal operation for other errors.
- Continue removing the crew registry entry after cleanup attempts, as nuke is an explicit destructive teardown. Return a distinct cleanup-failure status and structured `cleanup_failures` details rather than claiming success. Operators can use the named resources for manual cleanup.
- Unit-test partial failures independently for container removal, workspace volume removal, and home volume removal, including cases where later operations still succeed.

## Risks / Trade-offs

- [Risk] Removing the registry entry means the MCP `nuke` tool cannot retry a failed resource removal → Include exact Podman resource names and operation failures in the response and logs so an operator can clean them up directly.
- [Risk] Stop failure may be recoverable if force-removal succeeds → Do not report a stop error as an orphan if the subsequent container removal succeeds; report failed resource removals, not transient intermediate errors.
