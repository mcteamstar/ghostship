# Lighthouse — Fleet Dashboard

Lighthouse is the ghostship fleet observability dashboard. Opening `GET /` in a browser shows all crews, their status, active tasks, Captain state, and schedule — no MCP agent session required.

## Accessing Lighthouse

Navigate to the transport URL in a browser:

```
http://localhost:64057/          # local dev (no API key)
https://your-portal-hostname/    # production (API key required)
```

When `GA_API_KEY` is set, you will be redirected to `/dashboard/login` first. Log in once; the `gs_session` cookie covers all subsequent dashboard and Lighthouse requests in the same browser session.

## What it shows

| Column | Description |
|:-------|:------------|
| Crew | Crew ID with activity badges (see below) |
| Status | `running` (green glow) or `stopped` (dimmed row) |
| Backend | `kiro`, `claude`, or `codex` |
| Composition | e.g. `spec-ops` |
| Uptime | Running time for live crews; `—` for stopped |
| Last Task | Relative time since last dispatch (e.g. `3m ago`) |
| Dashboard | Link to per-crew KC dashboard (when `dashboard=True` at launch) |

**Activity badges** on the crew name:
- `N active` (cyan) — the crew has N running agent tasks
- `⚑ captain` (purple) — an active Captain schedule is running
- `⚑ paused` (muted) — a Captain schedule exists but is paused

Click any row to expand per-crew detail: active tasks (ID, agent, done/running indicator, elapsed), Captain state (enabled/paused, schedule, current task ID), and any other scheduled jobs.

The table polls `GET /api/crews` every 5 seconds. Open rows stay open across refreshes.

## REST API

`GET /api/crews` is the same data as the MCP `crews()` tool, available as plain JSON:

```bash
# No API key (local dev)
curl http://localhost:64057/api/crews | jq

# With API key
curl -H "Authorization: Bearer <key>" https://your-host/api/crews | jq
```

Response shape:

```json
{
  "crews": [
    {
      "crew_id": "my-crew",
      "status": "running",
      "acp_backend": "kiro",
      "composition": "spec-ops",
      "uptime_secs": 1842,
      "last_task_at": "2026-10-29T12:34:56Z",
      "dashboard_url": null,
      "agents": [
        { "task_id": "abc123", "agent": "ghost", "done": false, "elapsed_secs": 47 }
      ],
      "captain": {
        "enabled": true,
        "schedule": "every 600s",
        "current_task_id": "def456"
      }
    }
  ],
  "host_memory_available_gb": 4.1,
  "active_crews": 1,
  "max_active_crews": 6
}
```

`captain` is `null` when no Captain schedule exists for that crew.

## Auth

Lighthouse is session-gated via `gs_session` cookie. No bearer token needed. When `GA_API_KEY` is unset, session check is skipped. See [portal.md#auth](portal.md#auth).
