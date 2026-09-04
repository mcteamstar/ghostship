## Context

See proposal.md. The current `captain stop` code in `server.py` (around line 3346):

```python
if action == "stop" and standing_job.get("enabled", False):
    try:
        toggle = _crew_api_with_recovery(..., f"/api/crons/{id}/enable", json={"enabled": False})
        if isinstance(toggle, dict) and toggle.get("ok") is False:
            return {"error": "Could not stop Captain check-in: job not found"}
    except Exception as exc:
        return {"error": f"Could not stop Captain check-in: {exc}"}
    standing_job["enabled"] = False

    # Registry update (only reached if API call succeeded)
    with _registry_lock:
        ...
        sched["enabled"] = False
```

Two problems:
1. The registry update is inside the `if ... standing_job.get("enabled", False)` guard — if the gateway already shows `false`, the registry is never updated.
2. The registry update is inside the `try` block after the API call — if the API returns an error dict, execution hits `return {"error": ...}` before the registry update runs.

## Fix

Restructure the stop block so the registry update always runs:

```python
if action == "stop":
    # Best-effort: disable the gateway cron if it's currently enabled.
    if standing_job.get("enabled", False):
        try:
            toggle = _crew_api_with_recovery(..., f"/api/crons/{id}/enable", json={"enabled": False})
            if isinstance(toggle, dict) and toggle.get("ok") is False:
                logger.warning("captain stop: gateway cron %s not found for crew %s", id, crew_id)
            # Do not return error — fall through to registry update regardless
        except Exception as exc:
            logger.warning("captain stop: gateway cron disable failed for crew %s: %s", crew_id, exc)
            # Do not return error — fall through to registry update regardless

    # Always update the registry to disabled, regardless of gateway call result.
    standing_job = dict(standing_job)
    standing_job["enabled"] = False
    try:
        with _registry_lock:
            reg = _load_registry()
            schedules = _get_crew_schedules(reg, crew_id)
            for sched in schedules:
                if sched.get("job_id") == standing_job.get("id"):
                    sched["enabled"] = False
                    break
            _save_registry(reg)
    except Exception as exc:
        logger.warning("captain stop: could not update registry for crew %s: %s", crew_id, exc)
```

The key changes:
- Gateway API failure is now a warning, not an early return
- Registry update runs unconditionally after the (best-effort) gateway call
- The `if standing_job.get("enabled", False)` guard only wraps the gateway call, not the registry update

## No other changes needed

The idle monitor already correctly queries the gateway. Once the registry is `enabled: false`, TRN-82's reconcile-on-restart will keep it consistent. The fix is entirely in `server.py`.
