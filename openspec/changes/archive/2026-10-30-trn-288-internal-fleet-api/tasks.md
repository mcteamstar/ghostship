# Tasks — TRN-288 Internal Fleet API

## T1 — Add `_build_internal_fleet_payload` to `transport/tools.py`

Copy the structure of `_build_crews_payload` into a new function
`_build_internal_fleet_payload(podman) -> dict` in `transport/tools.py`.

Changes from `_build_crews_payload`:
- **Remove the `_crew_api` call.** The `agents` key SHALL always be set to `[]`
  directly. Do not call `_crew_api(info, "GET", "/api/spawn")`.
- **Add `last_checkin_at` to the captain dict.** After reading `captain_entry`
  from the registry schedule list, add:
  ```python
  "last_checkin_at": captain_entry.get("last_checkin_at"),
  ```
  to the `entry["captain"]` dict alongside the existing `enabled`, `schedule`,
  and `current_task_id` fields.
- All other fields (`crew_id`, `status`, `composition`, `acp_backend`,
  `uptime_secs`, `last_task_at`, `dashboard_url`, `policy_version`,
  `gateway_healthy`, `container`) are identical to `_build_crews_payload`.

Add a docstring explaining the registry-only contract and the `agents: []`
invariant.

## T2 — Wire `_handle_internal_crews_get` to the new builder

In `transport/server.py`, in `_handle_internal_crews_get`:

Replace:
```python
from tools import _build_crews_payload, _get_podman  # container: flat /app/
```
with:
```python
from tools import _build_internal_fleet_payload, _get_podman  # container: flat /app/
```

and the local dev fallback:
```python
from transport.tools import _build_crews_payload  # local dev
```
with:
```python
from transport.tools import _build_internal_fleet_payload  # local dev
```

Replace the `_build_crews_payload(podman)` call with
`_build_internal_fleet_payload(podman)`.

## T3 — Update `tests/unit/test_fleet.py`

Add two test cases to `tests/unit/test_fleet.py`:

1. **`test_internal_crews_includes_last_checkin_at`** — build a registry with a
   crew that has a captain schedule entry containing `last_checkin_at`. Call
   `GET /internal/crews` and assert `captain.last_checkin_at` is present in the
   response and matches the registry value.

2. **`test_internal_crews_agents_always_empty`** — verify that `agents` is `[]`
   in the internal endpoint response even when a running crew has tasks (confirm
   no `_crew_api` mock is needed — i.e. the test does not need to patch
   `_crew_api` at all for the internal endpoint).

Both tests should follow the pattern of the existing `TestInternalCrewsGet`
class in `test_fleet.py`.

## T4 — Update `radar/static/app.js`

In the expanded-row detail section of the captain panel, add display of
`last_checkin_at` when present:

- If `captain.last_checkin_at` is a non-null ISO 8601 string, render it as a
  relative timestamp using the existing `timeAgo()` helper, labelled
  "last check-in".
- If `captain.last_checkin_at` is null or absent, show nothing (do not render
  a blank row).

Example target output in the expanded detail:
```
Captain: enabled — every 300s
Last check-in: 3m ago
```

## T5 — Run tests and verify

```bash
bash scripts/run.sh --unit
```

All tests must pass. Verify:
- `GET /internal/crews` returns `agents: []`
- `GET /internal/crews` returns `captain.last_checkin_at` when available
- `GET /api/crews` still returns the live `agents` list (unchanged)
