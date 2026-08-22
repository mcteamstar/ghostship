## Context

The `schedule` tool in `transport/server.py` currently only creates recurring jobs via `POST /api/crons` on the crew gateway. There is no way to cancel or list jobs through the MCP tool surface — only through direct gateway REST calls or the `kirocrew` CLI from inside the crew. The `dispatch` tool spawns immediately with no delay option. See proposal.md for motivation.

The crew gateway already exposes:
- `GET /api/crons` — returns all jobs with id, name, schedule, agent, enabled, last_run, last_status
- `POST /api/crons` — creates a job
- `POST /api/crons/{id}/enable` — enables/disables a job

There is no `DELETE /api/crons/{id}` endpoint currently — this will need to be confirmed or implemented gateway-side.

## Goals / Non-Goals

**Goals:**
- Expose cancel and list as first-class actions on the `schedule` MCP tool
- Add a one-shot delayed dispatch primitive to `dispatch`
- Expose a `transport://jobs` MCP resource for passive job discovery

**Non-Goals:**
- Modifying the gateway's cron implementation itself (we call its API)
- Adding job editing/updating (pause/resume already exists via captain)
- Recurring delayed dispatch (combining fire_after_secs with interval/cron)

## Decisions

### 1. Action-based routing on `schedule`

**Decision:** Add an `action` parameter to `schedule` with values `"create"` (default, preserving backward compatibility), `"cancel"`, and `"list"`.

**Rationale:** The schedule tool is already the semantic home for job lifecycle. Adding actions keeps the tool surface cohesive rather than creating separate `cancel_schedule`/`list_schedules` tools. The default `action="create"` ensures existing callers are unaffected.

**Alternatives considered:**
- Separate `schedule_cancel` / `schedule_list` tools — rejected because it fragments the schedule concept across multiple tools and clutters the tool registry.

### 2. Cancel via DELETE on gateway API

**Decision:** Call `DELETE /api/crons/{job_id}` on the crew gateway. If this endpoint does not exist, implement it as `POST /api/crons/{job_id}/remove` (matching the existing enable pattern).

**Rationale:** DELETE is the RESTful choice for job removal. The fallback to POST ensures we can ship even if the gateway version in use doesn't have DELETE support yet.

**Alternatives considered:**
- Disable instead of delete — rejected because cancel implies permanent removal; pause already covers temporary disabling via captain.

### 3. fire_after_secs as a one-shot cron job

**Decision:** Implement `fire_after_secs` on `dispatch` by creating a cron job with `delay` (seconds from now), which the gateway already supports as the `at` one-shot mechanism. The cron job auto-deletes after firing.

**Rationale:** The gateway's cron system already supports one-shot jobs via the `at` (unix timestamp) or `delay` (seconds from now) parameters. We reuse this rather than building a separate timer mechanism. The job auto-removes after execution, so no cleanup is needed.

**Alternatives considered:**
- Sleep-then-dispatch in a wrapper task — rejected because it ties up a slot and is fragile to restarts.
- New dedicated timer subsystem — rejected as over-engineering when cron already supports one-shot semantics.

### 4. transport://jobs resource reads from all running crews

**Decision:** The resource iterates all tracked crews, calls `GET /api/crons` on each, and aggregates results into a plain-text roster (matching the pattern of `transport://agents`).

**Rationale:** The existing `transport://agents` resource follows the same pattern — enumerate crews, collect data, format as plain text. This keeps the resource layer consistent and lightweight. Errors on individual crews are reported inline rather than failing the whole read.

## Risks / Trade-offs

- **[Gateway DELETE endpoint may not exist]** → Mitigation: Check at runtime; fall back to disable+error message asking the user to upgrade, or use an alternative POST endpoint.
- **[One-shot job timing precision]** → The gateway's cron scheduler has jitter (0–5min for non-strict jobs). Mitigation: Set `strict_schedule=True` on delayed dispatch jobs so they fire at the intended time.
- **[Captain job protection]** → The cancel action must refuse to cancel the reserved captain check-in job. Mitigation: Check job name against `_CAPTAIN_CHECKIN_JOB_NAME` before deletion, same guard as schedule creation.
- **[transport://jobs latency with many crews]** → Mitigation: Sequential API calls with short timeouts; report unavailable crews inline rather than blocking.
