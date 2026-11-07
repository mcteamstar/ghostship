# Design

## Context

See proposal.md — Why for motivation.

In `transport/tools.py`, the `nuke()` function has two separate `with registry:` blocks near the
end of its execution:

1. **First lock** (line ~1435): reads `schedules` from the registry.
2. **Second lock** (line ~1449): calls `deregister_crew()` and `release_port()` **inside** the
   lock, then pops the crew entry from the registry.

The second block holds `_registry_lock` across `_caddy_portal.deregister_crew(crew_id)`, which
makes a blocking HTTP `DELETE` to the Caddy admin API. The fix pattern already exists in
`server.py`: `_handle_crew_dashboard_delete` explicitly moves the Caddy call outside the lock
(the "C-1 pattern" noted in the existing code comment at line ~1146 of `tools.py`).

## Goals / Non-Goals

**Goals:**
- Release `_registry_lock` before calling `_caddy_portal.deregister_crew()` and the port-release
  calls in `nuke()`.
- Keep the registry write (pop crew entry, clear batch records) atomic under the lock.
- Verify the fix with a call-order unit test.

**Non-Goals:**
- Changing the `launch()` Caddy registration path (already correct — see C-1 comment).
- Changing any other lock usage in `tools.py`.
- Changing the best-effort/log-on-failure contract for Caddy calls.

## Decisions

**Extract dashboard port before releasing lock; call Caddy after.**

The current second `with registry:` block reads `_ui_p` (dashboard port), calls Caddy, and pops
the crew entry — all inside one lock acquisition. The fix splits this into two phases:

```
Phase 1 — under lock:
    _ui_p = registry._reg["crews"].get(crew_id, {}).get("dashboard_port")
    _crew_entry.pop("batches", None)
    registry._reg["crews"].pop(crew_id, None)

Phase 2 — outside lock:
    if _ui_p is not None:
        _caddy_portal.deregister_crew(crew_id)         # blocking HTTP
        _dashboard_gate.release_port(int(_ui_p))
        _caddy_portal.release_port(int(_ui_p))
```

*Alternative considered: wrap only the Caddy call in a try/finally outside the lock.*
Rejected — cleaner to read `_ui_p` under the lock (consistent with the existing pattern) and
make the whole Caddy interaction post-lock.

**No ordering guarantee needed for Caddy call vs. registry removal.**

The registry entry is removed first (under lock). A concurrent `crews()` call will see the crew
as gone before Caddy deregisters. This is acceptable — the dedicated dashboard port stops
receiving new connections the moment the crew entry disappears from the registry, because portal
routes are based on the Caddy server config (still registered for a few milliseconds), but the
crew container will have been nuked already so any in-flight request to the port returns 502.
This is an improvement over the current state, not a regression.

## Risks / Trade-offs

**[Race] Tiny window where Caddy still has the crew route after registry removal.**
→ Negligible: the crew container is already stopped/removed at this point, so forwarded requests
return 502 rather than reaching live crew code. The deregister call follows immediately.

**[Test] Mocking `_caddy_portal` in `test_tools.py` requires a bit of setup.**
→ The existing `FakePodmanClient` + registry stub pattern is sufficient. `_caddy_portal` can be
replaced with a `MagicMock` in the test.
