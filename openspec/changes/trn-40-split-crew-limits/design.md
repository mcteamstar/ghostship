## Context

`GA_MAX_CREWS = 6` is checked once in `launch()` against `len(reg["crews"])`.
Stopped crews count equally against it, limiting how many persistent workspaces
an operator can keep around without them eating memory. The memory pressure is
actually from *running* containers, not registered ones.

## Goals / Non-Goals

**Goals:**
- Separate "how many workspaces can I keep" from "how many can run at once"
- Protect memory on constrained hosts without penalising idle workspace retention
- `GA_MAX_ACTIVE_CREWS=0` as an escape hatch to disable the active limit

**Non-Goals:**
- Evicting running crews automatically to make room (that's the idle monitor's job)
- Per-composition limits

## Decisions

### GA_MAX_CREWS default: 6 → 20

Stopped crews cost nothing meaningful. 20 gives ample room for long-lived
per-feature workspaces without implying memory risk. Operators on constrained
hosts can lower it.

### GA_MAX_ACTIVE_CREWS default: 3

At ~2-3 GB active per crew, 3 running simultaneously fits comfortably on an
8 GB host alongside the transport and OS. Operators with more RAM can raise it.

### Check placement: `_ensure_crew_running`, not `launch`

The active limit only matters when a stopped crew is about to start, not when
it is registered. Checking it in `_ensure_crew_running` catches both explicit
restarts and implicit wake-on-demand (when an MCP tool triggers auto-restart).

### Count method: registry scan

Count `status == "running"` entries in the registry. This is already loaded
by callers. A container that is actually dead but marked "running" in the
registry still counts — the next `_ensure_crew_running` call will correct its
status. False positives are safe (slightly over-protective); false negatives
(under-counting) would defeat the purpose.

### `GA_MAX_ACTIVE_CREWS=0` disables the check

Zero means "no active limit" — useful for development or large-memory hosts.
The registered-crew limit still applies.

### crews() response: add active_crews count

Include `active_crews` (count of running) and `max_active_crews` in the
`crews()` response alongside `host_memory_available_gb`, so the Admiral can
see headroom at a glance.

## Implementation sketch

```python
# Module level
GA_MAX_CREWS = int(os.environ.get("GA_MAX_CREWS", "20"))
GA_MAX_ACTIVE_CREWS = int(os.environ.get("GA_MAX_ACTIVE_CREWS", "3"))

# In _ensure_crew_running, before the restart block:
if GA_MAX_ACTIVE_CREWS > 0:
    with _registry_lock:
        reg = _load_registry()
        active = sum(1 for c in reg["crews"].values() if c.get("status") == "running")
    if active >= GA_MAX_ACTIVE_CREWS:
        raise CrewUnresponsiveError(
            f"Active crew limit ({GA_MAX_ACTIVE_CREWS}) reached — "
            "wait for a running crew to idle out or nuke one first"
        )
```

**Note on error type:** `CrewUnresponsiveError` is semantically wrong here — it implies a gateway/container failure, not a capacity limit. Consider raising a plain `RuntimeError` with a clear message, or introducing a new `ActiveCrewLimitError`. The spec says "raises `CrewUnresponsiveError` (or equivalent)" — implementer should choose the cleaner option at apply time.
