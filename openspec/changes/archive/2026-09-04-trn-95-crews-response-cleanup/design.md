## Context

See proposal.md for motivation.

The `crews()` handler (transport/server.py, `_crews()`) already fetches live agent data from the crew gateway via `GET /api/spawn` — `last_tool` and `elapsed_secs` come from that live call, not from the registry. `last_task_at` is already stored in the registry (added in TRN-89) and surfaced in the response.

`uptime_secs` is the only genuinely new data source: it requires a Podman container inspect (`GET /libpod/containers/{name}/json`) to read the `State.StartedAt` field.

## Goals / Non-Goals

**Goals:**
- Remove `last_tool` from agent entries in `crews()` — the raw tool string (e.g. `"Reading SKILL.md:1"`) is too low-signal to be useful at the fleet overview level.
- Add `uptime_secs` to running crew entries — gives the Admiral a sense of how long a crew has been alive without calling `pickup`.
- Ensure `last_task_at` is consistently present (already is; confirm null when no task dispatched).

**Non-Goals:**
- Changing the data source for `elapsed_secs` — it stays live from `/api/spawn`.
- Changing `pickup` or `captain status` response shapes.
- Adding any other new fields to the `crews()` response.

## Decisions

**Remove `last_tool`, keep `elapsed_secs`**

`elapsed_secs` is computed from task start time and tells the Admiral how long an agent has been running — genuinely useful for spotting stuck tasks at a glance. `last_tool` is a raw tool invocation string with no context; the Admiral must call `pickup` to make sense of it anyway. Removing `last_tool` reduces noise without losing signal.

**`uptime_secs` from Podman inspect, only when running**

The container `State.StartedAt` timestamp is available from the Podman containers API (`GET /libpod/containers/{name}/json`). `PodmanClient` already has `container_inspect` defined but it's not currently used in the `crews()` handler. We call it once per running crew, compute `int((datetime.now(UTC) - started_at).total_seconds())`, and include it in the response. For stopped crews the field is omitted (or null) — there is no meaningful uptime.

Alternatives considered:
- Deriving uptime from `created_at` in the registry — rejected, that's crew creation time not container start time. A crew that stopped and restarted has a very different uptime than its age.
- Caching inspect results — unnecessary for the `crews()` call frequency; one inspect per running crew is cheap.

**No change to `last_task_at` data source**

Already populated at dispatch time (TRN-89) and stored in the registry. No change needed.

## Risks / Trade-offs

- **Inspect call per running crew** — adds one Podman API call per running crew to the `crews()` response time. Acceptable given typical fleet sizes (1–6 crews). If Podman is slow, the inspect can fail gracefully with `uptime_secs: null`.
- **Breaking change for callers parsing `last_tool`** — any tool description or skill that references `last_tool` in `crews()` output needs updating. The `ghostship-command` skill and MCP tool docstring are the only known callers. Both are in-repo.

## Migration Plan

1. Remove `last_tool` from the two `agents` list comprehensions in `_crews()`.
2. Call `podman.container_inspect(container_name)` for running crews; parse `State.StartedAt`; compute `uptime_secs`.
3. Add `uptime_secs` to the crew entry when running; omit when stopped.
4. Update MCP tool docstring for `crews` to reflect removed/added fields.
5. Update `ghostship-command` skill guidance.
6. Update test assertions on `crews()` response shape.

No deployment migration needed — `GA_PORTSIDE_ENABLED` is unrelated. This is a clean in-place change with no persistent state migration.
