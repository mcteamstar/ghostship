# Design

## Context

See proposal.md. Single root cause: `KIROCREW_CREW_ID` not injected. One-line fix.

## Relevant code

**`transport/server.py` ~line 2736–2755** — container env construction in `launch`:

```python
# transport's public origin to KIROCREW_CORS_ORIGINS so those calls are
# accepted by the gateway's CORS policy.
...
    "KIROCREW_CORS_ORIGINS": _cors_origins,
```

`KIROCREW_CREW_ID` must be added here alongside `KIROCREW_CORS_ORIGINS`.

**`transport/captain.py` line 60** — the self-cancel script:

```bash
crew_id="$KIROCREW_CREW_ID"
curl -X POST "http://ga-transport:64057/crews/${crew_id}/captain/stop" \
  -H "Cookie: mc_token_5476=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)" \
  -H "Origin: $(echo $KIROCREW_CORS_ORIGINS | cut -d, -f1)"
```

**`transport/auth.py` lines 431–447** — transport-secret bypass already correct:

```python
if (
    scope["method"] == "POST"
    and len(_parts) == 4
    and _parts[0] == "crews"
    and _parts[2] == "captain"
    and _parts[3] == "stop"
):
    stop_handler = self._public_routes.get(("POST", "/crews/*/captain/stop"))
    if stop_handler is not None:
        ...
        return True
```

**`transport/server.py` line 5032** — route registered in `public_routes`:

```python
("POST", "/crews/*/captain/stop"): _handle_captain_stop_post,
```

## Fix

```python
# server.py ~line 2751 — add alongside KIROCREW_CORS_ORIGINS
container_env["KIROCREW_CREW_ID"] = crew_id
```

That's it. With a non-empty `crew_id`, the self-cancel URL is `/crews/<crew_id>/captain/stop`, which matches the auth.py pattern, bypasses the transport-secret gate, and reaches the endpoint which validates the dashboard cookie.

## Also check: reconcile_registry restart path

`_patch_crew_config` is also called from `_reconcile_registry` at `lifecycle.py:1844`. The container env for restarted crews is set via podman's `container_start` — the env was baked in at `create` time. `KIROCREW_CREW_ID` only needs to be set at `container_create` time (in `launch`), not at restart. No change needed in `_reconcile_registry`.
