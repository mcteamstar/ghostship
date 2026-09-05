---
name: ghostship-command
description: Command a ghostship fleet over the `ghostship` MCP server — launch crew containers, seed and extract workspace files, dispatch OpenSpec work to the six agent personas, poll or steer running tasks, run a crew on autopilot via Captain, and tear crews down. Use whenever the `ghostship` MCP tools (crews, launch, supply, evac, dispatch, pickup, steer, captain, schedule, nuke) are available and there's fleet work to do — this skill has no assumed repo context, it is the context.
metadata:
  author: ghostship
  version: "0.3.0"
---

# Ghostship Command

Ghostship runs isolated [KiroCrew](https://github.com/kirodotdev/KiroCrew)
instances ("ghostships") in containers and puts you — the **Admiral** — in
command over MCP. This skill is written for whoever is holding the MCP
connection, with no assumption you have the `ghostship` repo checked out or
its docs loaded. If a tool call here fails or drifts from what's described,
trust the live tool/resource output over this file — it can go stale, the
transport can't.

No `ghostship` MCP connection yet? That's `ghostship-admin`'s job (install,
connect a client, upgrade, tear down) — this skill starts after that's
already done. Want to add new agent personas, skills, or MCP servers to the
catalogue, or build a new crew composition? That's `ghostship-capability`.

## Mental model

**Intended workflow order:** `launch → supply → dispatch → pickup/steer → evac → nuke`.
That is the spine of everything below — a crew is launched, seeded with a
repo, given tasks, watched (and redirected) while they run, its output pulled
out, and finally torn down. For any non-trivial work (more than ~20 min),
don't drive that relay by hand — hand it to **Captain autopilot** (a recurring
Raven check-in that runs the whole SDD lifecycle and survives timeouts and
restarts); see [Autopilot — Captain](#autopilot--captain-prefer-this-for-non-trivial-work).

```
Fleet (you, the Admiral, over MCP)
 └─ Crew ("gs-<id>", one per launch(crew_id))     ← isolated container + 2 volumes
     ├─ workspace volume                           ← repo/, subagent_<task_id>/ dirs, shared openspec/
     ├─ home volume
     └─ Tasks (dispatch() → task_id)                ← one KiroCrew agent persona, one job
         ghost / spectre / banshee / wraith / reaper / raven
```

- A **crew** is a durable, reusable workspace — launch it once, dispatch many
  tasks into it over time. It is not torn down between tasks.
- A **task** is one `dispatch()` call to one persona. Each task runs in its
  own `subagent_<task_id>/` directory inside the crew — tasks in the same
  crew do not share a working directory. They *do* share one OpenSpec store
  at the workspace root and can reach each other over the crew's internal
  mail.
- **Sessions persist after completion** until the crew is nuked — `steer` on
  a finished task continues it with full prior context intact. Don't nuke a
  crew just to "clean up" completed tasks; those sessions are valuable.
- **composition** (e.g. `spec-ops`) selects what a crew is built from —
  which agents/skills/steering it ships with. Not the same axis as *persona*
  (which agent a given task runs on).

## Step 0 — Discover before assuming anything

Before you `launch`, `dispatch`, or plan any of the workflow steps above,
read the live state. Compositions, personas, and standing-order templates are
configurable per install and can differ from what's described below. Don't
hardcode them:

- `crews()` — every live crew, its status, and its currently running tasks.
  Per crew you get `status`, `created_at`, `last_task_at`, and — for running
  crews — `uptime_secs` (seconds since the container started; null when
  stopped). Each running task lists `task_id`, `agent`, `done`, and
  `elapsed_secs`. This is a fleet overview: it does NOT carry the current tool
  or latest output for a task — call `pickup` when you need live per-task
  detail.
- resource `transport://compositions` — available `composition` values for `launch`.
- resource `transport://agents` — the real roster and description for `dispatch`'s `agent` values.
- resource `transport://orders` — built-in `captain(template=...)` bodies, in full.
- resource `transport://jobs` — every scheduled job across every crew.
- resource `transport://version` — transport version and each running crew's image version.

Treat the tables in this skill as the common case, not a guarantee.

## Core lifecycle

```
launch(crew_id)                     → crew ready (~30s cold; auto-restarts if idled)
supply(path, crew_id, ...)          → presigned upload URL; POST bytes yourself
dispatch(task, agent, crew_id, model=...) → task_id
pickup(task_id, crew_id, ...)       → poll or collect
steer(task_id, message, crew_id)    → redirect running / continue completed
evac(path, crew_id, ...)            → presigned download URL; GET bytes yourself
nuke(crew_id, confirm=True)         → destroys container + BOTH volumes
```

### 1. `launch(crew_id, composition="spec-ops")`

Name `crew_id` after the work — lowercase letters/digits/hyphens, 1–50 chars.
There's no single required convention; pick whatever makes the crew's purpose
obvious at a glance. A rough hierarchy of what to anchor to:

1. **Repo-scoped work** — use the repo name or a short form: `ghostship`, `hermes-fix`
2. **Ticket-scoped work** — use the ticket ID: `trn-70-impl`, `srv-69-rate-limit`
3. **Topic/purpose** — use a verb-noun or descriptive slug: `review-security`, `icon-eval`, `auth-research`

Any of these work; the main goal is that `crews()` output makes sense at a
glance. One crew can be reused across related work; only launch a new one
when you genuinely want workspace isolation from an existing one.

A crew that idled out (no activity for ~5 min by default) is not gone — the
next call against it restarts it transparently. Don't `nuke` a crew just
because `crews()` shows it stopped; `nuke` is for when you want the
workspace permanently gone.

**`dashboard=True`** allocates a dedicated port and returns a `dashboard_url`
for the crew's browser UI. The dashboard is opt-in (`dashboard=False` by
default). ⚠️ Dashboard ports are unauthenticated beyond an auto-injected
session cookie — the cookie is issued to any visitor who loads the page. Only
use `dashboard=True` on deployments protected by Tailscale or a firewall. Do
not enable it on any deployment reachable from the public internet.

### 2. Seed the workspace — `supply`

**A freshly launched crew's workspace is empty.** `launch` only seeds the
shared `openspec/` store automatically — not a repo, not any code. If the
work you're about to `dispatch` needs a codebase, run `supply` first.
Dispatching into an empty crew is the single most common mistake — the agent
lands with nothing to read or edit and either stalls or invents context.

`supply` (and `evac`) do **not** move bytes through the MCP call itself —
the tool call returns a presigned URL. You then POST the bytes yourself with
`curl` or equivalent:

```bash
# Single file
curl -X POST "<url>" --data-binary @./config.json

# Directory tree (set unpack=True on the supply() call)
tar -czf - ./myrepo | curl -X POST "<url>&unpack=1" --data-binary @-

# Full git history — recommended for SDD work (set bundle=True on the supply() call)
# IMPORTANT: ALWAYS build a fresh bundle immediately before calling supply().
# Never reuse a /tmp/*.bundle file built for a previous crew or at an earlier
# point in time — a stale bundle silently seeds the crew with an outdated repo
# snapshot, missing commits made since the bundle was built.
# Name the bundle after the crew_id to make reuse of the wrong file obvious.
git bundle create /tmp/<crew_id>.bundle --all
curl -X POST "<url>&bundle=1" --data-binary @/tmp/<crew_id>.bundle
```

Always deliver the repo to `path="ghostship"` or `path="repo"` — a sibling
to the crew's shared `openspec/` store, never inside it. Every persona and
skill looks for the repo at this level. Using `bundle=True` is preferred
over `unpack=True` because it preserves full git history and lets the agent
run `git log`, `git diff`, and `git bundle` for `evac`.

### 3. Do work — `dispatch`

```
dispatch(task, agent="ghost", crew_id, model=...) → { task_id, ... }
```

The optional `model` pins the model for this one task. It is a create-time
setting only: `steer` and `continue` cannot change an existing session's model.
It outranks both the crew's per-agent model and `KC_MODEL_OVERRIDE` for this
call, so `KC_MODEL_OVERRIDE` is not an absolute ceiling when a caller supplies
`model=`.

The dispatched agent has **no context beyond `task`** — no memory of this
conversation, no idea what you're trying to accomplish beyond what you wrote.
Be specific: state what to do, what "done" looks like, the relevant file
paths or change names, and anything about prior work it needs to know.

Persona roster (confirm against `transport://agents` — this is the
`spec-ops` default):

| Agent | Use for |
|:------|:--------|
| **ghost** | One well-scoped task end to end — including the full OpenSpec cycle if the task is self-contained enough |
| **spectre** | Front half of a change — explore, propose, revise the plan |
| **banshee** | Independent review — a second pair of eyes; finds bugs, runs tests, fixes what it finds, gives a formal verdict |
| **wraith** | Research, docs, investigation — read-only over code, writes reports only; no edits |
| **reaper** | Sync specs and archive a finished change |
| **raven** | Watches mailboxes, checks task state, dispatches bounded next steps; used by Captain autopilot |

Small work doesn't need the full relay — a single `ghost` dispatch is enough
for a self-contained task. Use the fuller cycle (spectre → ghost → banshee →
reaper) for anything that benefits from a plan, an implementer, and an
independent reviewer being separate passes.

### 4. Watch and guide — `pickup` / `steer`

```
pickup(task_id, crew_id)                      → check once, now
pickup(task_id, crew_id, timeout_secs=N)      → poll every 3s up to N, or until done
pickup(crew_id=...)                           → list every task in the crew (no task_id)
```

Polling returns early with `reason: "admiral_mail"` if new mail lands
mid-poll — treat that as a signal to read mail, not noise.

```
steer(task_id, message, crew_id)              → running task: redirected mid-flight
                                                  completed task: resumed with full prior context
steer(task_id, message, crew_id, force=True)  → hard-stop a running task first, then resume
```

Sessions persist after completion — `steer` on a finished task is a real
continuation with full history intact. When a task times out or produces the
wrong output, `steer` it rather than dispatching fresh — you keep the agent's
full working context. Only dispatch fresh if the task is truly done and you
want a new scope.

A `job_id` from `schedule`/`captain` lives in a different namespace than
`task_id` — `steer` cannot touch scheduled jobs; use `captain(action="stop")`
or `schedule(action="cancel")` for those.

### 5. Recurring or delayed work — `schedule`

```
schedule(name, message, crew_id, cron=... | interval=... | delay=..., model=...)
schedule(action="list" | "cancel", ...)
```

Pass `model=` when creating a cron, interval, or one-shot delay job to pin
that job's model. The override is create-time-only — it has no effect through
`steer`/`continue` and cannot alter an existing job. It outranks the crew's
per-agent model and `KC_MODEL_OVERRIDE`; operators using `KC_MODEL_OVERRIDE` as
an absolute model ceiling should treat any caller with dispatch access as able
to override it per call.

Both `dispatch` and `schedule` default to `ghost`; pass `agent=` explicitly
for anything else. `interval` jobs fire immediately on creation by default;
`cron` jobs don't. Minimum `interval` is 60s. Pass `timezone` explicitly if
you don't mean UTC (the default).

## Autopilot — Captain (prefer this for non-trivial work)

**Captain is the default for any work expected to take more than ~20 minutes.**
A single `dispatch` has a 60-minute hard timeout and no automatic recovery —
if the agent times out, you manually intervene. Captain survives timeouts,
crashes, and container restarts: Raven picks up where it left off on the
next check-in cycle.

```
captain(crew_id, action="order", template="sdd", change_name="<change>", interval=300)
captain(crew_id, action="order", message="<free-form standing order>", interval=300)
captain(crew_id, action="status")   # job state, last-run summary, unread mail counts
captain(crew_id, action="stop")     # pauses the job without deleting it
```

For `captain(action="order")`, `model=` pins only a newly created Captain
check-in job; it is ignored when resuming an existing paused job. This is also
create-time-only and cannot change a model through `steer`/`continue`. The
per-call value outranks the crew's per-agent model and `KC_MODEL_OVERRIDE`, so
`KC_MODEL_OVERRIDE` is not an absolute ceiling for callers allowed to create a
Captain job.

Use `interval=300` (5 min) for SDD work — comfortably inside the idle-stop
window. A scheduled check-in existing does **not** by itself keep a crew
warm between runs; only actual dispatch/cron activity refreshes the idle timer.

The built-in `sdd` template (full body via `transport://orders`) drives Raven
to read real OpenSpec + `tasks.md` state each check-in, then dispatch spectre
while planning is incomplete, ghost while tasks are unchecked, banshee for
review, and reaper to archive. After one unresolved fix/re-review cycle, it
escalates to you rather than looping forever. Raven self-pauses the cron
once the lifecycle is complete — `captain status` will show `status: paused`.

For monitoring orders (watch a one-shot task, report when done), write a
free-form message and Raven will pause the cron after sending the completion
report.

**Checking on a captained crew:**

```
captain(crew_id, action="status")   # last Raven cycle summary + unread mail counts
crews()                             # see active tasks across all crews
pickup(crew_id=...)                 # full task list including Raven cycles
```

## Extracting work — `evac` and merging

`evac` returns a presigned download URL. You then GET the bytes yourself.
The most common pattern is extracting a git bundle and inspecting commits:

```bash
# 1. Get the URL
evac(path="ghostship", crew_id="...", ref="release/0.2.0", bundle=True)

# 2. Download
curl -s "<url>" -o /tmp/bundle.bundle

# 3. Fetch into your local repo (creates a remote ref)
cd /path/to/local/repo
git fetch /tmp/bundle.bundle 'refs/heads/release/0.2.0:refs/remotes/crew/release/0.2.0'

# 4. Inspect new commits
git log release/0.2.0..crew/release/0.2.0 --oneline

# 5. Diff stat
git diff release/0.2.0..crew/release/0.2.0 --stat

# 6. Cherry-pick or merge selectively
git cherry-pick <commit-hash>
```

Always inspect before merging — the crew may have commits you don't want
(e.g. tool image replacements if you have your own versions, or planning
artifacts the crew modified). Cherry-pick individual commits rather than
merging the whole branch when in doubt.

## Mail

Personas communicate over Maildir mailboxes inside the container.
You don't reach in and read `/var/mail/*` directly (see guardrails).

Two ways to see mail state without a dispatch:

- Every `pickup` response includes the agent persona's mail count (`agent_mail`)
  and subject lines for the agent persona's mailbox (e.g. `ghost_subjects`,
  `raven_subjects`). Captain and admiral mailbox subjects and counts
  (`captain_subjects`, `admiral_subjects`, `captain_mail`, `admiral_mail`) are
  NOT included in pickup — those are stale when sourced from a Raven pickup
  result anyway. A poll still returns early with `reason: "admiral_mail"` when
  new Admiral mail lands mid-poll.
- `captain(action="status")` returns live `captain_subjects` and `admiral_subjects`
  arrays directly from the mailboxes (using the Podman archive API, so it works
  even on a stopped crew). Use this for an accurate mail picture of the
  captain/admiral mailboxes without dispatching or waking the container.

```
captain(crew_id, action="status")
# → { "captain_subjects": [...], "admiral_subjects": [...],
#     "captain_mail": N, "admiral_mail": M, ... }
```

To read full mail content, dispatch **raven** with a task asking it to check
a specific mailbox and report back. Raven is the watcher/messenger persona;
don't use ghost for mail-reading tasks.

## Git author identity

By default, each agent commits under its own persona identity (e.g.
`Ghost <ghost@localhost>`). When you evac and cherry-pick those commits into
your local repo, the persona labels appear in your history.

**Option 1 — configure upfront (recommended).** Add to your `ghostship.conf`:

```bash
GA_GIT_AUTHOR_NAME="Your Name"
GA_GIT_AUTHOR_EMAIL="you@example.com"
```

Then reinstall (`./install.sh --config ghostship.conf`). All agents in every
new crew will commit under your identity. Existing crews are not affected —
nuke and relaunch to pick up the change.

**Option 2 — rewrite after cherry-pick.** If you've already evac'd commits
with persona labels, rewrite them in your local repo:

```bash
# Rewrite the last N commits (adjust as needed)
git rebase --onto HEAD~N HEAD~N --exec \
  'GIT_COMMITTER_NAME="Your Name" GIT_COMMITTER_EMAIL="you@example.com" \
   git commit --amend --reset-author --no-edit'

# Or for a range of commits:
git filter-branch --env-filter '
  GIT_AUTHOR_NAME="Your Name"
  GIT_AUTHOR_EMAIL="you@example.com"
  GIT_COMMITTER_NAME="Your Name"
  GIT_COMMITTER_EMAIL="you@example.com"
' -- <first-commit>^..HEAD
```

Or using `git-filter-repo` (preferred, faster):

```bash
git filter-repo --name-callback 'return b"Your Name"' \
                --email-callback 'return b"you@example.com"'
```

## Guardrails

- **Never dispatch repo-touching work into an unseeded crew.** `launch` only
  seeds the shared `openspec/` store. Confirm you've run `supply(path="...",
  bundle=True)` before dispatching anything that expects code.
- **Stay on the transport.** Never reach for `podman exec` into a crew
  container. Container exec bypasses governance policy, mail delivery, idle
  accounting, and task tracking — silently breaking all of it.
- **`nuke` destroys both volumes, no residue.** `evac` everything you need
  before nuking. There is no undo.
- **`nuke(crew_id)` without `confirm=True` is a preview only**, not a no-op.
  Add `confirm=True` to actually destroy.
- **Rebuilding the crew image doesn't touch existing crews.** A container is
  bound to the image it was launched with. Picking up a new crew image means
  `evac` + `nuke` + `launch` for that crew.

## Common pitfalls

| Symptom | Cause |
|:--------|:------|
| Agent reports nothing to work on / no code found | Crew not seeded — run `supply(path="...", bundle=True)` before dispatching |
| `supply`/`evac` "succeeded" but nothing appeared | Forgot the second step — you must POST/GET bytes against the returned URL |
| `steer` errors oddly or does nothing | Wrong task_id, or trying to `steer` a `job_id` from `schedule`/`captain` |
| Crew won't respond after a while | Idle-stopped (expected) — next call restarts it transparently |
| Repo landed in wrong place | Use `path="ghostship"` or `path="repo"`, not nested inside `openspec/` |
| Nuked a crew and lost work | Should have `evac`'d first — no undo |
| Agent did wrong thing despite timeout steer | Used fresh `dispatch` instead of `steer` — lost full prior context |
| Captain sending many duplicate admiral mails | Raven correctly reporting completion each cycle; Raven self-pauses on SDD template — check `captain status` for `paused`. For free-form orders, the dedup check prevents most repeats but a manual `captain(action="stop")` may be needed |

## Worked example — captain autopilot (recommended for non-trivial work)

```python
# 1. Launch + seed
launch(crew_id="trn-70-impl")
supply(path="ghostship", crew_id="trn-70-impl", bundle=True)
# → POST /tmp/myrepo.bundle to the returned URL

# 2. Optional: start spectre to kick off planning if OpenSpec change doesn't exist yet
dispatch(task="Create an OpenSpec change for TRN-70: ...", agent="spectre", crew_id="trn-70-impl")
pickup(task_id=..., crew_id="trn-70-impl", timeout_secs=600)

# 3. Set captain to drive the full SDD lifecycle
captain(crew_id="trn-70-impl", action="order", template="sdd",
        change_name="trn-70-security-hardening", interval=300)

# 4. Monitor periodically
captain(crew_id="trn-70-impl", action="status")   # summary + mail counts
crews()                                            # active tasks

# 5. When captain status shows paused (lifecycle complete):
evac(path="ghostship", crew_id="trn-70-impl", ref="release/0.2.0", bundle=True)
# → curl -s "<url>" -o /tmp/bundle.bundle
# → git fetch /tmp/bundle.bundle ... && git log ... && git cherry-pick <hash>
nuke(crew_id="trn-70-impl", confirm=True)
```

## Worked example — manual relay (full control)

```python
launch(crew_id="srv-69-rate-limit")
supply(path="repo", crew_id="srv-69-rate-limit", bundle=True)  # POST the bundle

dispatch(task="Explore and propose a change for SRV-69: add per-IP upload rate "
         "limiting. Investigate the current upload handler first.",
         agent="spectre", crew_id="srv-69-rate-limit")  # → task_id A
pickup(task_id=A, crew_id="srv-69-rate-limit", timeout_secs=600)

# Use the exact change name from task A's result — don't invent it
dispatch(task="Implement all tasks in openspec change srv-69-rate-limit.",
         agent="ghost", crew_id="srv-69-rate-limit")  # → task_id B
pickup(task_id=B, crew_id="srv-69-rate-limit", timeout_secs=3600)
# If ghost times out: steer(task_id=B, message="Continue from where you left off...", ...)

dispatch(task="Independently review the SRV-69 change. Fix any findings. "
         "Give a verdict: APPROVED or UNRESOLVED FINDINGS.",
         agent="banshee", crew_id="srv-69-rate-limit")  # → task_id C
pickup(task_id=C, crew_id="srv-69-rate-limit", timeout_secs=600)

dispatch(task="Sync specs and archive the SRV-69 change.",
         agent="reaper", crew_id="srv-69-rate-limit")   # → task_id D
pickup(task_id=D, crew_id="srv-69-rate-limit", timeout_secs=300)

evac(path="repo", crew_id="srv-69-rate-limit", bundle=True)
# → curl, git fetch, inspect, cherry-pick
nuke(crew_id="srv-69-rate-limit", confirm=True)
```
