---
name: ghostship-command
description: Command a ghostship fleet over the `ghostship` MCP server — launch crew containers, seed and extract workspace files, dispatch OpenSpec work to the six agent personas, poll or steer running tasks, run a crew on autopilot via Captain, and tear crews down. Use whenever the `ghostship` MCP tools (crews, launch, supply, evac, dispatch, pickup, steer, captain, schedule, nuke) are available and there's fleet work to do — this skill has no assumed repo context, it is the context.
metadata:
  author: ghostship
  version: "1.0"
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
already done.

## Mental model

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
- **composition** (e.g. `spec-ops`) selects what a crew is built from —
  which agents/skills/steering it ships with. Not the same axis as *persona*
  (which agent a given task runs on).

## Discover before assuming anything

Compositions, personas, and standing-order templates are configurable per
install and can differ from what's described below. Before planning work,
read the live state instead of hardcoding it:

- `crews()` — every live crew, its status, and its currently running tasks.
- resource `transport://compositions` — available `composition` values for `launch`.
- resource `transport://agents` — the real roster and description for `dispatch`'s `agent` values.
- resource `transport://orders` — built-in `captain(template=...)` bodies, in full.
- resource `transport://jobs` — every scheduled job across every crew; the authoritative thing to check against `schedule`'s and `captain`'s own `list`/`status` actions.
- resource `transport://version` — transport version and each running crew's image version; relevant to the image-rebuild guardrail below.

Treat the tables in this skill as the common case, not a guarantee.

## Core lifecycle

```
launch(crew_id)                     → crew ready (~30s cold; auto-restarts if idled)
supply(path, crew_id, ...)          → presigned upload URL; POST bytes yourself
dispatch(task, agent, crew_id)      → task_id
pickup(task_id, crew_id, ...)       → poll or collect
steer(task_id, message, crew_id)    → redirect running / continue completed
evac(path, crew_id, ...)            → presigned download URL; GET bytes yourself
nuke(crew_id, confirm=True)         → destroys container + BOTH volumes
```

### 1. `launch(crew_id, composition="spec-ops")`

`crew_id` is yours to name (lowercase letters/digits/hyphens, 1–50 chars) —
pick something meaningful to the work, e.g. `srv-69-rate-limit`, not a
random id. One crew can be reused across many features; only launch a new
one when you actually want workspace isolation from an existing crew.

First-ever use on an install needs kiro-cli identity set up first — that's
`ghostship-admin`'s `/login` flow, done once via shell before any of this.
If it was skipped, `launch` falls back to its own device-auth trigger and
returns `login_url`/`code` instead of a ready crew; surface that URL/code
to your human operator to complete, then call `launch` again with the same
`crew_id`. Don't rely on this fallback if you have a choice — it's known to
fail silently for IAM Identity Center installs, and any crew partially
created while unauthenticated can't be salvaged, only nuked. Prefer
confirming auth is already done (or asking your operator to run
`ghostship-admin`'s login flow) over hitting this path.

A crew that idled out (no activity for five minutes by default) is not
gone — the next call against it (`dispatch`, `pickup`, `steer`, `evac`,
`supply`, `schedule`) restarts it transparently. Don't `nuke` a crew just
because `crews()` shows it stopped; `nuke` is for when you want the
workspace gone.

### 2. Seed the workspace — `supply`

**A freshly launched crew's workspace is empty** except the shared
`openspec/` store `launch` seeds automatically — no repo, no files. If the
work you're about to `dispatch` needs a codebase (almost all OpenSpec
work does), run `supply` first. Skipping this and dispatching straight
into an empty crew is a real failure mode, not a hypothetical one — the
agent lands with nothing to explore, read, or edit, and either stalls or
invents context that isn't there. Confirm you've seeded a repo before your
first repo-touching `dispatch` in a crew.

`supply` (and `evac`) do **not** move bytes through the MCP call itself —
the tool call only returns a presigned URL. You then have to actually
transfer the bytes with an HTTP client (`curl` from wherever you're
running, e.g. via Bash):

```bash
# Single file
curl -X POST "<url>" --data-binary @./config.json

# Directory tree — set unpack=True on the supply() call, then POST a tar
tar -czf - ./myrepo | curl -X POST "<url>&unpack=1" --data-binary @-

# Real git history — set bundle=True on the supply() call, then POST the bundle
git bundle create ./myrepo.bundle --all
curl -X POST "<url>&bundle=1" --data-binary @./myrepo.bundle
```

Deliver a repo to `path="repo"` — the working tree location every persona
and skill expects. It sits as a sibling to the crew's shared `openspec/`
store, never inside it, so seeding never touches OpenSpec state.

`evac` is the same pattern in reverse: `evac(path, crew_id, ref=..., bundle=...)`
returns a download URL; `ref` alone (no `bundle`) gets you a diff, `bundle=True`
gets you a full git bundle to clone/fetch locally, and a bare `path` gets
you that one file.

### 3. Do work — `dispatch`

```
dispatch(task, agent="ghost", crew_id) → { task_id, ... }
```

The dispatched agent has **no context beyond `task`** — no memory of this
conversation, no idea what you're trying to accomplish beyond what you
write. Be specific: what to do, what "done" looks like, and anything about
prior work it needs to know (a change name, a commit hash, a mail address
to report back to).

Persona roster (confirm against `transport://agents` — this is the
`spec-ops` default):

| Agent | Use for |
|:------|:--------|
| **ghost** | One well-scoped task end to end — including the full OpenSpec cycle if the task is self-contained enough not to need a hand-off |
| **spectre** | Front half of a change — explore, propose, revise the plan |
| **banshee** | Independent review — a second pair of eyes across the whole change, not just one task; fixes what it finds via `openspec-update-change`/`openspec-propose`, hands the formal close-out to reaper |
| **wraith** | Research and docs — read-only over code, writes report/doc files only |
| **reaper** | Sync specs and archive a finished change |
| **raven** | Watches mailboxes, checks task state, dispatches bounded next steps. Also the one Captain autopilot runs (see below) |

Small work doesn't need the full five-persona relay — a single `ghost`
dispatch is enough for a self-contained task. Reach for the fuller cycle
(spectre → ghost → banshee → reaper) for anything that benefits from a
plan, an implementer, and an independent reviewer being different passes.

### 4. Watch and guide — `pickup` / `steer`

```
pickup(task_id, crew_id)                      → check once, now
pickup(task_id, crew_id, timeout_secs=N)      → poll every 3s up to N, or until done
pickup(crew_id=...)                           → list every task in the crew (no task_id)
```

Polling returns early with `reason: "admiral_mail"` if new mail lands in
your (Admiral) mailbox mid-poll — treat that as a signal to go read it, not
noise.

```
steer(task_id, message, crew_id)              → running task: redirected mid-flight
                                                  completed task: resumed with full prior context
steer(task_id, message, crew_id, force=True)  → hard-stop a running task first, then resume
```

Sessions persist after completion until the crew is nuked — `steer` on a
finished task is a real continuation, not a fresh start. A `job_id` from
`schedule`/`captain` lives in a different namespace than `task_id`, so
`steer` can't touch a scheduled check-in; use `captain(action="stop")` or
`schedule(action="cancel")` for those instead.

### 5. Recurring or delayed work — `schedule`

```
schedule(name, message, crew_id, cron=... | interval=... | delay=...)
schedule(action="list" | "cancel", ...)
```

Both `dispatch` and `schedule` default to `ghost`; pass `agent=` explicitly
for anything else. `interval` jobs fire once immediately on creation by
default (`fire_immediately`); `cron` jobs don't. Minimum `interval` is 60s.
A `cron` expression is interpreted in `timezone`, which defaults to
`Australia/Sydney` — pass it explicitly if you mean a different zone. Same
default applies to `captain`'s `cron` below.

## Autopilot — Captain

Manual relay (you calling `dispatch`/`pickup`/`steer` yourself, persona by
persona) is the default and always available. `captain` is the one opt-in
autonomous mechanism per crew: it books a recurring job that dispatches
**raven** in a persistent session to watch the crew and move work forward
on its own.

```
captain(crew_id, action="order", template="sdd", change_name="<change>", interval=60)
captain(crew_id, action="order", message="<free-form standing order>", cron="0 * * * *")
captain(crew_id, action="status")   # job enabled?, last-run summary, Captain + Admiral mailbox counts
captain(crew_id, action="stop")     # pauses the job, keeps its history/mailbox
```

The built-in `sdd` template (full body via `transport://orders`) has Raven
read real OpenSpec + `tasks.md` state each check-in, then dispatch spectre
while planning is incomplete, ghost while tasks are unchecked, and banshee
for review. After one unresolved fix/re-review cycle, it escalates to you
rather than looping forever.

Use `interval=60` for check-ins on active SDD work — comfortably inside the
300s idle-stop window, so the container never idles out mid-cycle. A
scheduled check-in existing does **not** by itself keep a crew warm between
runs; only actual dispatch/cron activity refreshes the idle timer.

## Mail

Personas talk to each other and to you over Maildir mailboxes inside the
container — you don't reach in and read `/var/mail/*` directly (see
guardrails). Two ways to see mail state without opening a mailbox yourself:

- Every `pickup` response includes mail counts (`agent_mail`/`admiral_mail`
  single-task; `mail_summary`/`admiral_mail` for a list).
- `captain(action="status")` reports Captain + Admiral mailbox counts.

To actually **read** mail content, dispatch **raven** with a task asking it
to check the relevant mailbox and report back — raven is the
watcher/messenger persona and is what the crew's own `ghostship-mail` skill
is written for. Don't dispatch `ghost` for a mail-reading task; that's not
what it's for and it won't know the mail conventions the way raven's
prompt does.

## Guardrails

- **Never `dispatch` repo-touching work into an unseeded crew.** `launch`
  only seeds the shared `openspec/` store, not a repo — check you've run
  `supply(path="repo", ...)` (or confirm one's already there, e.g. via a
  prior task's result) before dispatching anything that expects a
  codebase. This is the single most common way to waste a dispatch.
- **Stay on the transport.** Every interaction with a crew goes through
  these MCP tools — never reach for a direct `podman exec` into a crew
  container. The container is ghostship's actual security boundary:
  governance policy, mail delivery, idle-timer accounting, and task/session
  tracking are all transport-mediated, and going around it breaks all of
  that silently. If a legitimate need forces a direct exec, that's a gap in
  the transport's tool surface, not something to route around.
- **`nuke` destroys both volumes, no residue.** `evac` anything you need —
  a diff, a bundle, a file — before nuking. There's no undo.
- **`nuke(crew_id)` alone is a preview**, not a no-op skip: it shows what
  would be destroyed. You need `confirm=True` to actually destroy.
- **`crew_id` is required on almost everything** except `crews()` (lists
  all) and reading resources. `dispatch`/`schedule` accept `crew_id=None` in
  their signature but will error without one in practice — always pass it.
- **Rebuilding the crew image doesn't touch running/existing crews** — a
  container is bound to whatever image existed at its `launch` time.
  Picking up an image change means `nuke` + `launch` for that crew
  specifically (pull anything needed out first).

## Common pitfalls

| Symptom | Cause |
|:--------|:------|
| Dispatched agent reports there's nothing to work on / no code found | The crew was never seeded — `launch` alone gives you an empty workspace plus the shared `openspec/` store, nothing else. Run `supply(path="repo", ...)` before dispatching repo-touching work |
| `supply`/`evac` "succeeded" but no file appeared / download 404s | Forgot the second step — you have to actually POST/GET bytes against the returned URL, the tool call alone doesn't transfer data |
| Dispatched agent does something off-base | `task` was underspecified — it has zero context beyond what you wrote in that string |
| `steer` seems to do nothing / errors oddly | Wrong task_id, or trying to `steer` a `job_id` from `schedule`/`captain` — those aren't `steer`'s namespace |
| Crew "won't respond" after a while | It idle-stopped (300s default with no activity) — this is expected; the next call against it restarts it transparently, just costs a beat |
| Repo seeding landed in the wrong place | Should be `path="repo"`, a sibling of the shared `openspec/` store, not nested inside it |
| Nuked a crew and lost something | Should have `evac`'d first — nuke has no undo |

## Worked example — manual relay, one feature

```
launch(crew_id="srv-69-rate-limit")
supply(path="repo", crew_id="srv-69-rate-limit", bundle=True) → POST the git bundle

dispatch(task="Explore and propose a change for SRV-69: add per-IP upload rate
  limiting to the upload handler. Investigate current handler code first.",
  agent="spectre", crew_id="srv-69-rate-limit") → task_id A
pickup(task_id=A, crew_id="srv-69-rate-limit", timeout_secs=300)

# pull the actual change name from task A's result (spectre names it when
# it runs `openspec new change`) — don't paste a placeholder literally
dispatch(task="Implement the tasks in openspec change srv-69-rate-limit for SRV-69.",
  agent="ghost", crew_id="srv-69-rate-limit") → task_id B
pickup(task_id=B, crew_id="srv-69-rate-limit", timeout_secs=600)

dispatch(task="Independently review the SRV-69 change for bugs and test gaps.",
  agent="banshee", crew_id="srv-69-rate-limit") → task_id C
pickup(task_id=C, crew_id="srv-69-rate-limit", timeout_secs=300)

dispatch(task="Sync specs and archive the SRV-69 change.",
  agent="reaper", crew_id="srv-69-rate-limit") → task_id D
pickup(task_id=D, crew_id="srv-69-rate-limit", timeout_secs=180)

evac(path="repo", crew_id="srv-69-rate-limit", bundle=True) → GET the result
# keep the crew if you'll return to it; nuke(crew_id=..., confirm=True) if not
```

## Worked example — autopilot

```
launch(crew_id="srv-69-rate-limit")
supply(path="repo", crew_id="srv-69-rate-limit", bundle=True) → POST the git bundle
dispatch(task="Create the SRV-69 rate-limiting change.", agent="spectre",
  crew_id="srv-69-rate-limit")   # or let Raven's first check-in start it

captain(crew_id="srv-69-rate-limit", action="order", template="sdd",
  change_name="srv-69-rate-limit", interval=60)

# later, periodically:
captain(crew_id="srv-69-rate-limit", action="status")
crews()   # or pickup(crew_id="srv-69-rate-limit") to see active tasks

# when status shows the change archived:
evac(path="repo", crew_id="srv-69-rate-limit", bundle=True)
```
