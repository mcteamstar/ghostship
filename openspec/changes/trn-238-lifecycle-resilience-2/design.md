# Design

## Context

See proposal.md. Two concurrency bugs in `transport/monitors.py` and `transport/lifecycle.py`.

## Goals

- Release `_registry_lock` before blocking I/O in the idle monitor
- Detect concurrent nuke in `_ensure_crew_running` before post-start setup
- Harden `/continue` path detection

## Non-Goals

- Redesigning the registry locking model broadly (TRN-208 scope)
- Parallelising container_stop operations

## Decisions

### D1 — In-flight flag for double-stop prevention (QA-1)

The pattern for releasing the lock before `container_stop`:

```python
with _registry_lock:
    if info.get("_stopping"):  # in-flight guard
        continue
    info["_stopping"] = True
    _registry[crew_id] = info  # write flag while holding lock

podman.container_stop(info["container"])  # lock NOT held

with _registry_lock:
    info = _registry.get(crew_id, {})
    if info:
        info.pop("_stopping", None)
        info["status"] = "stopped"
        _registry[crew_id] = info
```

The `_stopping` flag lives only in the in-memory registry. It is not persisted. If the transport restarts mid-stop, the flag is lost — harmless, since Podman is idempotent on already-stopped containers.

**Alt considered:** a separate `_stopping_crews: set` module-level variable. Rejected — keeps state outside the registry, harder to reason about.

### D2 — Registry existence check in _ensure_crew_running (QA-2)

After `container_start` and before the cookie write:

```python
with _registry_lock:
    if crew_id not in _registry:
        logger.info("_ensure_crew_running: crew %s was nuked mid-restart, aborting setup", crew_id)
        return {"status": "nuked_during_restart"}
```

Return value is advisory — the leader already returned a success response to the original caller (e.g. dispatch). The nuke path logs at INFO, not ERROR, since this is an expected race.

### D3 — endswith vs substring for /continue (QA-3)

Change `'continue' in path` to `path.endswith('/continue')`. One-line change, no tradeoffs.
