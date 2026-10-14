# Proposal

**Plane ticket:** TRN-241

## Why

Raven's self-cancel mechanism (`_RAVEN_SELF_CANCEL` in `transport/captain.py`) fails with 401. The script reads:

```bash
crew_id="$KIROCREW_CREW_ID"
curl -X POST "http://ga-transport:64057/crews/${crew_id}/captain/stop" \
  -H "Cookie: mc_token_5476=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)" \
  -H "Origin: $(echo $KIROCREW_CORS_ORIGINS | cut -d, -f1)"
```

Investigation from inside a crew container (gs-investigate-selfcancel, task 59fb74422658725f) found one root cause: **`KIROCREW_CREW_ID` is not injected into the crew container environment.** The variable is empty, so the URL becomes `/crews//captain/stop` with an empty path segment, which does not match the registered route pattern and falls through to the transport-secret gate, returning 401.

`KIROCREW_CORS_ORIGINS` is injected at `server.py:2751` alongside container env setup. `KIROCREW_CREW_ID` was simply never added.

Note: the transport-secret bypass for `POST /crews/*/captain/stop` is already correctly implemented in `auth.py` (lines 431–447) and the route is registered in `public_routes` (server.py:5032). The endpoint auth (dashboard cookie) is correct. The only missing piece is the env var.

## What Changes

- In `transport/server.py`, add `"KIROCREW_CREW_ID": crew_id` to the `container_env` dict at the same site where `KIROCREW_CORS_ORIGINS` is set (~line 2751)
- Add a unit test confirming `KIROCREW_CREW_ID` is present in the container env built by the launch path

## Impact

- `transport/server.py` — one line added to container env construction
- `tests/unit/` — one test assertion added
