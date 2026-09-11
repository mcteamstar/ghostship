# Ghostship Reference

Quick reference for operators and developers. Full docs in linked files.

## MCP Tools

### Ship operations

| Tool | What it does | Also known as |
|:-----|:-------------|:--------------|
| `crews` | List all registered crews, their status, and active agents | list crews, show workspaces, sitrep |
| `launch` | Create a new crew container + workspace | calldown, create workspace, init environment |
| `supply` | Get a presigned URL to deliver files/tars/bundles into a crew workspace | deliver, inject, upload, seed workspace |
| `evac` | Get a presigned URL to extract files, diffs, or git bundles from a crew workspace | extract, exfil, pull, get file, show diff |
| `nuke` | Permanently destroy a crew — container + both volumes | destroy, teardown, kill |

### Crew operations

| Tool | What it does | Also known as |
|:-----|:-------------|:--------------|
| `dispatch` | Spawn a task on a named agent persona; pass `tasks=[...]` for atomic batch dispatch (returns `batch_id` + per-task `task_ids`) | dropoff, send, assign |
| `pickup` | Check a task / list all tasks / wait for completion + mail state | see below |
| `steer` | Redirect a running task or continue a completed one | redirect, update, continue, add context |
| `captain` | Manage the crew's standing-orders Captain (Raven check-in) | supervise, oversee, autopilot, govern |
| `schedule` | Create a recurring task on a crew (cron or interval in seconds) | book, recur, cron, automate |

### pickup aliases by usage

| Usage | Aliases |
|:------|:--------|
| `pickup(task_id, crew_id)` — check one task immediately | collect, get result, check progress |
| `pickup(crew_id)` — list all tasks in a crew | list, overview, what's happening |
| `pickup(timeout_secs=N)` — wait until done or timeout | bridge, watch, wait, monitor, poll |
| `pickup(agent="ghost", crew_id)` — skim one agent's mailbox only | check ghost mail, ghost inbox |

### pickup response fields

**Task-level** (`pickup(task_id, crew_id)`):
- `created_at`, `started_at`, `completed_at` — ISO 8601 UTC (`null` when not yet reached)
- `<agent>_subjects`, `captain_subjects`, `admiral_subjects` — subject lines with `{subject, received_at}`

**Crew-level** (`pickup(crew_id)`):
- `agent_subjects` — dict of all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral), each a list of `{subject, received_at}`

**Agent-filter** (`pickup(agent="ghost", crew_id)`):
- `{"agent": "ghost", "subjects": [...], "mail": N}` — single-inbox response, no task list

### Resources (read-only)

| Resource | What it returns |
|:---------|:----------------|
| `transport://agents` | Available agent personas and their roles |
| `transport://compositions` | Available crew compositions for `launch` |
| `transport://orders` | Summary index of built-in Captain standing-order templates |
| `transport://orders/{name}` | Full resolved body of the named template |
| `transport://version` | Transport version and per-crew image versions |
| `transport://jobs` | Scheduled jobs across all running crews |

---

## HTTP Proxy Routes

Routes proxy through to a crew's gateway. Require `Authorization: Bearer <GA_API_KEY>` (when set). Both proxy routes enforce a **60 s request timeout** — use `evac` for large downloads.

### Health probe

```
GET /health
```

Returns `200 OK`. No auth required.

### Gateway UI proxy

```
GET|POST /crews/{crew_id}/ui
GET|POST /crews/{crew_id}/ui/{path:path}
```

Proxies to `http://gs-{crew_id}:5476/{path}`. Auto-wakes a stopped crew. No session cookie injected — browser uses the normal login flow.

```
http://<transport-host>:<PORT>/crews/my-crew/ui
```

### Gateway API proxy

```
GET|POST|PUT|PATCH|DELETE /crews/{crew_id}/api/{path:path}
```

Proxies to `http://gs-{crew_id}:5476/api/{path}` with the internal session cookie (`mc_token_5476`) auto-injected. On upstream 401/403 the cookie is refreshed and the request retried once.

```bash
# List active tasks
curl -H "Authorization: Bearer $GA_API_KEY" \
     http://<transport-host>:<PORT>/crews/my-crew/api/spawn

# Dispatch a task
curl -H "Authorization: Bearer $GA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"task": "check the objective", "agent": "ghost"}' \
     http://<transport-host>:<PORT>/crews/my-crew/api/spawn
```

---

## Agent Personas

See [`docs/agents.md`](agents.md) for full detail.

### SDD cycle

```
dispatch(spectre)   → explore + propose
dispatch(spectre)   → update-change (revisions)
dispatch(ghost)     → apply-change (implement tasks)
dispatch(banshee)   → review + fix findings
dispatch(reaper)    → sync-specs + archive
```

Or autonomously: `captain(action="order", template="sdd", change_name="...", interval=60)`.

---

## Composition

`launch(composition="spec-ops")` — default, full agent/skill/steering set.

Add new compositions to [`crews/registry.json`](../crews/registry.json). Read options via `transport://compositions`.

---

## Key env vars

| Var | Default | Purpose |
|:----|:--------|:--------|
| `GA_IDLE_TIMEOUT_SECS` | `300` | Seconds idle before auto-stopping a crew container |
| `GA_HOST_URL` | _(falls back to `localhost:PORT`)_ | Externally-visible base URL for MCP endpoint and presigned links. Set via `--public-url` on `install.sh` |
| `KC_MODEL_OVERRIDE` | _(unset)_ | Override model for all crew agent JSONs |
| `GA_API_KEY` | _(unset)_ | Static bearer key protecting the MCP endpoint |

Full list: [`docs/configuration.md`](configuration.md).
