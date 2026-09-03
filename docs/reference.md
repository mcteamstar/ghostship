# Ghostship Reference

Quick reference for operators and developers. For full docs see the linked files.

## MCP Tools

### Ship operations

| Tool | What it does | Also known as |
|:-----|:-------------|:--------------|
| `crews` | List all registered crews, their status, and active agents | list crews, show workspaces, what's running, sitrep |
| `launch` | Create a new crew container + workspace | calldown, create workspace, launch crew, init environment |
| `supply` | Get a presigned URL to deliver files/tars/bundles into a crew workspace | deliver, inject, upload, seed workspace, push file |
| `evac` | Get a presigned URL to extract files, diffs, or git bundles from a crew workspace | extract, exfil, pull, get file, show diff |
| `nuke` | Permanently destroy a crew — container + both volumes. Not routine cleanup. | destroy, teardown, kill |

### Crew operations

| Tool | What it does | Also known as |
|:-----|:-------------|:--------------|
| `dispatch` | Spawn a task on a named agent persona | dropoff, send, assign |
| `pickup` | Check a task / list all tasks / wait for completion + mail state | see below |
| `steer` | Redirect a running task or continue a completed one | redirect, update, continue, follow up, add context |
| `captain` | Manage the crew's standing-orders Captain (Raven check-in) | supervise, oversee, autopilot, govern, sitrep, status |
| `schedule` | Create a recurring task on a crew (cron or interval in seconds) | book, recur, cron, timer, automate |

### pickup aliases by usage

| Usage | Aliases |
|:------|:--------|
| `pickup(task_id, crew_id)` — check one task immediately | collect, get result, check progress |
| `pickup(crew_id)` — list all tasks in a crew | list, overview, what's happening |
| `pickup(timeout_secs=N)` — wait until done or timeout | bridge, watch, wait, monitor, hold, patrol, poll |
| `pickup(agent="ghost", crew_id)` — skim one agent's mailbox only | check ghost mail, ghost inbox |

### pickup response fields (key additions in 0.2.4)

**Task-level** (`pickup(task_id, crew_id)`):
- `created_at`, `started_at`, `completed_at` — ISO 8601 UTC timestamps (`null` when not yet reached)
- `<agent>_subjects`, `captain_subjects`, `admiral_subjects` — subject lines with `{subject, received_at}`

**Crew-level** (`pickup(crew_id)`):
- `agent_subjects` — dict of all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral), each a list of `{subject, received_at}`

**Agent-filter** (`pickup(agent="ghost", crew_id)`):
- `{"agent": "ghost", "subjects": [...], "mail": N}` — single-inbox response, no task list

### Resources (read-only, not tools)

| Resource | What it returns |
|:---------|:----------------|
| `transport://agents` | Available agent personas and their roles |
| `transport://compositions` | Available crew compositions for `launch` |
| `transport://orders` | Built-in Captain standing-order templates |

---

## HTTP Proxy Routes

These routes proxy directly through to a crew's gateway. They require the same
`Authorization: Bearer <GA_API_KEY>` header as MCP routes (when `GA_API_KEY` is set).
Both proxy routes respect a **60 s request timeout** — use `evac` for large file
downloads from a crew workspace.

### Health probe

```
GET /health
```

Returns `200 OK` when the transport process is alive. No auth required. Suitable
for load-balancer health checks and startup probes.

### Gateway UI proxy

```
GET|POST /crews/{crew_id}/ui
GET|POST /crews/{crew_id}/ui/{path:path}
```

Proxies to `http://gs-{crew_id}:5476/{path}`. Opens the crew's KiroCrew dashboard
in a browser. Auto-wakes a stopped crew before proxying. No session cookie is
injected — the browser goes through the normal gateway login flow.

Example (open in browser when no API key is set):
```
http://<transport-host>:<PORT>/crews/my-crew/ui
```

### Gateway API proxy

```
GET|POST|PUT|PATCH|DELETE /crews/{crew_id}/api/{path:path}
```

Proxies to `http://gs-{crew_id}:5476/api/{path}` with the internal session cookie
(`mc_token_5476`) automatically injected. Useful for operator or automation access
to the gateway REST API without separately obtaining a session.

On upstream 401/403, the cookie is refreshed and the request is retried once.

Example curl commands:
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

## Agent Personas

See [`docs/agents.md`](agents.md) for full detail. Quick summary:

| Agent | Role | OpenSpec ownership |
|:------|:-----|:-------------------|
| **Ghost** | General-purpose — implements tasks, handles end-to-end work | All six operations |
| **Spectre** | Planning — proposes, explores, updates changes | explore, propose, update-change |
| **Banshee** | Review/fix — independent second pass, finds bugs, runs tests | explore, propose, update-change, apply-change |
| **Wraith** | Recon/docs — research and documentation, read-only over code | None |
| **Reaper** | Cleanup — syncs specs and archives completed changes | sync-specs, archive-change |
| **Raven** | Coordinator — runs the Captain check-in loop, dispatches personas | Dispatch only (via CLI + gateway REST) |

### SDD cycle (who does what)

```
dispatch(spectre)   → explore + propose
dispatch(spectre)   → update-change (revisions)
dispatch(ghost)     → apply-change (implement tasks)
dispatch(banshee)   → review + fix findings
dispatch(reaper)    → sync-specs + archive
```

Or autonomously via `captain(action="order", template="sdd", change_name="...", interval=60)`.

---

## Composition (crew type)

`launch(composition="spec-ops")` — default, full agent/skill/steering set.

Add new compositions to [`crews/registry.json`](../crews/registry.json). Read available options via the `transport://compositions` resource.

---

## Key env vars

| Var | Default | Purpose |
|:----|:--------|:--------|
| `GA_IDLE_TIMEOUT_SECS` | `300` | Seconds idle before auto-stopping a crew container |
| `GA_HOST_URL` | _(falls back to `localhost:PORT`)_ | Externally-visible base URL for all links (MCP endpoint and presigned `evac`/`supply` links). Set `--public-url` on `install.sh` to configure |
| `KC_MODEL_OVERRIDE` | _(unset)_ | Override model for all crew agent JSONs |
| `GA_API_KEY` | _(unset)_ | Static bearer key protecting the MCP endpoint |

Full list: [`docs/configuration.md`](configuration.md).
