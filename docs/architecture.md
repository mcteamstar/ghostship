# Architecture

## Components

**ga-transport** — the MCP server (`transport/server.py`). Runs as a plain
`podman run` container, bound straight to `localhost`. Manages crew
containers via the Podman socket. Exposes the `ghostship` tools (see the
main README).

**Crew containers** — on-demand KiroCrew instances, each a **ghostship**
(`localhost/kirocrew-crew:latest`), named `gs-<id>`. Each has two
volumes: a workspace volume (`gs-vol-<id>`) and a home volume
(`gs-home-<id>`). Created by `launch`, torn down by `nuke`. All join
`ga-net` so transport can reach them by container name
(`http://gs-<id>:5476`).

**Crew image** (`crews/kirocrew/Containerfile`) — extends the official `ghcr.io/kirodotdev/kirocrew:stable`
(Debian 13, Python 3.12, git, curl). Adds Node.js 24 LTS via NodeSource, and
the `openspec` CLI (`@fission-ai/openspec`) that the `openspec-*` skills shell
out to. Built locally at install time (`localhost/kirocrew-crew:latest`). See
[configuration.md](configuration.md#extending-the-crew-image) to add packages.

## Ghost Academy

Every ghostship is built from the same foundation: [`academy/agents/`](../academy/agents/),
[`academy/skills/`](../academy/skills/), and
[`academy/steering/`](../academy/steering/) — the Ghost Academy's shared
curriculum, bind-mounted into transport and copied into every crew at
`launch` (steps 9–11 below), filtered against the crew type's manifest
(`crews/<crew-type>/manifest.json`, also bind-mounted into transport). Each
manifest key (`agents`, `skills`, `steering`) is either the literal string
`"*"` or an explicit array of exact names to include from the
corresponding Academy pool. The only crew type today, `kirocrew`
(`crews/kirocrew/manifest.json`), specifies `"*"` for every key, so every
ghostship still gets the whole curriculum in practice — the manifest is
groundwork for a future second crew type to select a different combination,
not a restriction on this one. Within whatever a crew type's manifest
selects, it's each persona's own prompt that narrows its focus further, not
a technical restriction (see
[agents.md](agents.md#steering-not-enforcement)).

Development inside a ghostship runs on
[OpenSpec](https://github.com/Fission-AI/OpenSpec)'s spec-driven
workflow — explore → propose → apply → archive — which the five worker
personas split up between them: Spectre drives the front half
(explore, propose, update-change), turning an idea into a spec-backed
plan before Ghost implements it and Reaper syncs specs and archives the
change. Raven is the sixth, coordination-only persona for recurring
standing-orders work. See [agents.md](agents.md) for what each persona owns,
and [Steering](#steering) below for the crew-wide context every persona gets
regardless of its own prompt.

## Crew lifecycle

```
launch(crew_id)
  1. Check the ga-kiro-auth file (DATA_DIR/ga-kiro-auth, not a Podman secret)
     └── missing → start kiro-cli device auth flow, return login URL
                   call launch again after auth to finish setup
  2. Create gs-vol-<id> + gs-home-<id> volumes
  3. Start crew container (localhost/kirocrew-crew:latest)
  4. Wait for gateway ready (GET / on :5476, 30s timeout)
  5. Inject kiro-cli auth rows into crew's SQLite DB
  6. Patch KiroCrew config (sandbox=none, skip_permissions=true, spawn_min_memory_gb=0)
  7. Restart container (workers pick up auth + config)
  8. Wait for gateway ready again
  9. Copy manifest-selected agent JSONs (spectre/ghost/banshee/reaper/wraith/raven,
     by default) from /agents bind-mount
  10. Copy manifest-selected skill dirs (openspec-*, radio, ..., by default)
      from /skills bind-mount
  11. Copy manifest-selected steering docs (all, by default) from /steering
      bind-mount (see below)
  12. Seed a shared OpenSpec store at the workspace root (see below)
  13. Patch agent model files to the model pinned in each agent's JSON
  14. Mint a session token with `KC_GATEWAY_TOKEN_TTL` (24h default), exchange for cookie
  15. Register in /data/crews.json with `last_used` set to setup completion time
  └── returns { status: "ready" } (~30s)

nuke(crew_id, confirm=True)
  └── stop container, remove container + both volumes, deregister
```

### Repository transfer

`launch(crew_id)` creates a workspace but does not clone or authenticate to a
caller-owned repository. Seed a Git checkout explicitly after the crew is
ready: create a self-contained bundle on the caller's machine, request
`supply(path="repo", crew_id="<id>", bundle=True)`, and POST the bundle to the
returned URL.

```bash
git bundle create ./project.bundle --all
curl -X POST "<delivery_url>" --data-binary @./project.bundle
```

The bundle is cloned into `repo/` inside the crew, preserving commits,
authorship, branches, and tags. To extract that history, request
`evac(path="repo", crew_id="<id>", bundle=True)`, download its URL, and either
clone it or fetch it into an existing checkout:

```bash
curl -fsSL "<evac_url>" -o ./crew.bundle
git clone ./crew.bundle ./crew-repo
git bundle list-heads ./crew.bundle
git fetch ./crew.bundle refs/heads/main:refs/remotes/crew/main
```

Use `git bundle create ./changes.bundle old-ref..new-ref` for an incremental
range; the receiving repository must already contain the range's prerequisite.

### Captain supervision

The manual persona sequence remains the default. Captain has one opt-in
mechanism per crew: an Admiral calls
`captain(crew_id, action="order", message="<standing order>", interval=<n>)`
or supplies a cron expression. The transport appends the order to the crew's
`captain@localhost` mailbox and ensures one recurring `/api/crons` job named
`captain` dispatches Raven with a persistent session. When `interval` is set,
Raven is also dispatched once immediately on job creation (before the first
interval tick) by default — `fire_immediately=False` suppresses this, and
`fire_immediately=True` enables it for cron-based check-ins. Resuming a
previously paused job never triggers an immediate dispatch.

For standard OpenSpec work, use the built-in template:
`captain(crew_id, action="order", template="sdd", change_name="<change>",
interval=<n>)`. Its fixed prose tells Raven to assess real OpenSpec status and
`tasks.md` state as a whole, dispatch Spectre while planning is incomplete,
Ghost while tasks remain unchecked, Banshee for an independent review, and
Reaper to sync specs and archive after a clean review. One unresolved review
cycle may be fixed and re-reviewed; unresolved findings after that cycle are
escalated to the Admiral, and archival is confirmed from OpenSpec state.

`captain(..., action="status")` reports whether the Raven job is enabled, its
last-run summary, and both Captain and Admiral mailbox counts. `action="stop"` pauses the job
with `POST /api/crons/{job_id}/enable` rather than deleting its history or
mailbox. A scheduled check-in has a `job_id`, not a dispatch `task_id`, so
`steer` is not its control channel. The `transport://orders` resource exposes
the name, description, and complete body of every built-in template alongside
the `transport://agents` roster resource.


## Steering

kiro-cli loads every `.md` file under `~/.kiro/steering/` for every session,
regardless of working directory — unlike agents and skills, which apply per
persona or per skill, steering is crew-wide standing context every dispatched
task gets automatically. `_copy_steering` copies the crew type's
manifest-selected `.md` files from `academy/steering/` into that path at
every `launch` (`"*"` for the `kirocrew` crew type today).

Kept deliberately narrow: environment facts every persona needs regardless of
its own prompt (the working-directory isolation model, the shared OpenSpec
store, when to reach for radio) — not project conventions, which belong in
whatever repository the caller delivers into `repo/` and get read naturally
as part of exploring that codebase. See
[academy/steering/STANDING_ORDERS.md](../academy/steering/STANDING_ORDERS.md)
for the current content.

## Shared OpenSpec store

Every `dispatch` runs in its own `subagent_<task_id>/` subdirectory —
isolated from every other task in the same crew, including earlier ones.
Left alone, this means two agents can never share OpenSpec state: one
proposing a change and another later implementing it would each resolve
`openspec` commands to their own private, empty store and never see each
other's work (the `openspec-*` skills document the resolution rule: without
an explicit `--store`, commands act on "the nearest local `openspec/`
root" — a git-like upward directory search).

`launch` closes that gap by running `openspec init --tools none
--no-animation --force` once at the workspace root (`_seed_openspec_store`
in `server.py`), a level above every `subagent_*/` dir. Every dispatched
task's `openspec` commands then resolve up to that same shared store
automatically — no path-passing between agents required. It sits as a
sibling to `repo/` (where a caller may deliver a project's working tree or
Git bundle), never inside it, so this never touches or pollutes a user's own
repository. `--force` makes the call idempotent, safe on every `launch`.

## Task retention and force-stop

Every `dispatch` request asks the crew gateway for a dedicated, retained run
(`keep=true`). This keeps each task's session data independent and available
for later continuation, including after a forceful stop.

`steer(task_id, message, crew_id, force=False)` preserves the normal turn-boundary
behavior by default: a running task receives `/steer`, while a completed task
uses `/continue`. With `force=True` on a running task, transport first calls
`DELETE /api/spawn/{task_id}` to stop that task's process, then calls
`POST /api/spawn/{task_id}/continue` with the message and returns
`force_redeployed`. A completed task follows the normal `/continue` path even
when `force=True`.

Recurring jobs created by `schedule` use the KiroCrew gateway's retained
`persistent_session=True` default for `/api/crons`; the cron REST path does not
use the direct `/api/spawn` `keep` field.

`pickup(task_id=None, crew_id=None, timeout_secs=0)` is the unified status and
polling tool. `bridge` is removed — use `pickup(timeout_secs=N)` directly
(also aliased as: bridge, patrol, poll, watch, wait, monitor, hold).

- **timeout_secs=0 (default):** check once and return immediately.
- **timeout_secs > 0:** poll every 3s until the task completes or the timeout
  elapses. Returns the not-done state on timeout without raising an error.

`pickup` always includes mail state in its response:

- **Single-task:** `agent_mail` (unread count for the task's agent persona) and
  `admiral_mail` (Admiral mailbox count).
- **List-all:** `mail_summary` (dict of persona → count for all personas with
  unread mail) and `admiral_mail`.

When polling (`timeout_secs > 0`), `pickup` captures the Admiral mail count at
loop start. If the count increases during any poll cycle, it returns early with
`reason: "admiral_mail"` alongside the current state, allowing the caller to
react to escalations without waiting for the full timeout.

## Idle stop + auto-restart

Crew containers are stopped automatically after `GA_IDLE_TIMEOUT_SECS` (default
300s) of no activity. This timer uses the registry's `last_used` timestamp;
setup initializes it when a crew is first registered as running. Active
`dispatch` tasks refresh the timestamp and prevent a stop. Cron executions are
tracked separately by the crew gateway, so a running cron or a cron whose
`last_run_ts` is newer than the registry timestamp also refreshes `last_used`.
An enabled schedule by itself does not pin a crew or proactively wake it; if no
execution occurs within the idle window, the container may stop and the next
transport call restarts it.

**Captain check-in interval:** The recommended Raven check-in interval is 60s
(`interval=60`). This keeps the gap between a worker task finishing and Raven
noticing well inside the idle timeout, so an active SDD cycle never accidentally
idles the container between steps. The 300s idle timeout provides a comfortable
safety margin even at 60s polling.

On the next `dispatch`, `pickup`, `steer`, `evac`, `supply`, or
`schedule` call, `_ensure_crew_running` detects the stopped container, restarts it,
waits for the gateway, and refreshes the session cookie — all
transparently before forwarding the request or returning a presigned URL.
`pickup(timeout_secs > 0)` performs this recovery before beginning its polling loop.
`supply` performs this recovery during the MCP tool call before signing its
upload URL. The later file POST repeats the recovery check because a crew can
idle-stop after URL issuance; file GET requests do the same for `evac`.

Concurrent restart races are serialised with a per-crew `threading.Event` — the
first caller does the restart, subsequent callers wait then use the refreshed
crew dict.

## Known workarounds

These are deliberate hacks for upstream bugs or limitations. Each is marked with
`# WORKAROUND:` in the source and should be removed when the upstream issue is fixed.

### spawn_min_memory_gb not read from config files (KiroCrew bug)

**Symptom:** Agent spawns are refused with "only N GB available (need 4 GB)" even
after setting `spawn_min_memory_gb: 0` in `config.local.json` or `config.json`.

**Root cause:** KiroCrew's `AgentConfig` loader explicitly constructs the config
object from a dict but never reads `spawn_min_memory_gb` — the field always uses
its dataclass default of `4.0`. Other fields (`resource_pressure_gb`,
`resource_critical_gb`) are read correctly. Only `spawn_min_memory_gb` is affected.

**Workaround (in `_ensure_crew_running`):** After every container restart, re-run
`_patch_crew_config` (which writes `spawn_min_memory_gb=0` into `config.json`),
then stop and restart the gateway so it re-seeds `config.json` before the loader
runs. This adds one extra stop/start cycle to every auto-restart but is the only
reliable way to keep the spawn gate disabled across restarts.

**Remove when:** KiroCrew upstream fixes `AgentConfig.load()` to read
`spawn_min_memory_gb` from `config.local.json`.

### Direct SQLite writes into kiro-cli's internal database

**Location:** `_inject_auth`, `_read_auth_from_crew` in `transport/server.py`.

**What we do:** Write auth rows directly into kiro-cli's `auth_kv` SQLite table
using `INSERT OR REPLACE`, bypassing kiro-cli's own migration and ORM layer. We
also read rows back the same way to copy auth between containers.

**Why it's fragile:** If kiro-cli changes the `auth_kv` schema (renames the table,
adds a NOT NULL column, changes key names, or moves to a different storage
backend), auth injection silently fails — no error is raised, crews just fail to
authenticate. The comment "schema and migrations are pre-seeded in the crew image"
is true but only holds as long as the upstream schema is stable.

**Why we do it:** kiro-cli provides no external API for injecting auth. The only
alternative is running `kiro-cli login` inside every new crew container, which
requires a full device auth flow per crew. Direct DB writes let us authenticate
once and propagate to all crews.

**Remove when:** kiro-cli exposes an official mechanism for pre-seeding auth
(config file, env var, or CLI flag).

### Cookie minting via `kirocrew token` + HTTP Set-Cookie header scraping

**Location:** `_mint_cookie` in `transport/server.py`.

**What we do:** Run `kirocrew token --ttl <ttl>` inside the container to get a
short-lived token, then make an HTTP GET to the gateway with that token as a query
param and scrape the `mc_token_5476=` value from the `Set-Cookie` response header
by string splitting.

**Why it's fragile:** The cookie name `mc_token_5476` is port-specific — it
embeds the gateway port. If the port changes, the scraping logic breaks silently
(no cookie found, all crew operations fail). The token-exchange flow is also
undocumented internal KiroCrew API that could change without notice.

**Why we do it:** The gateway requires a session cookie for all API calls. There
is no documented way to mint one from outside the gateway. The `kirocrew token`
subcommand is the only path we found.

**Remove when:** KiroCrew exposes a stable, documented way to obtain a session
credential for the gateway REST API.

### Idle-stop vs. nuke

These are two distinct lifecycle operations and should not be confused:

- **Idle-stop** — automatic, transparent, reversible, no data loss. The container stops after a timeout and restarts on the next command. This is the normal resource management path; operators do not need to take any action.
- **Nuke** — explicit, permanent, workspace-destroying. Removes the container and both volumes entirely. Use only when you intentionally want to discard the crew's workspace, history, and context. Not a routine post-task step.

Idle-stop is what keeps a fleet of crews from consuming resources when inactive. Nuke is for when a crew's purpose is fully served and its data is no longer needed.

## Rebuilding images

`podman start` (used by `_ensure_crew_running` for idle-stop recovery, and by
`nuke`'s counterpart on transport restart) restarts the *existing* container
object — it does not recreate it from the current image tag. A container is
bound to whichever image it was created from at `podman run` time, so
rebuilding `localhost/transport:latest` or `localhost/kirocrew-crew:latest`
has no effect on containers that already exist; only a fresh `podman run`
(i.e. `install.sh` for transport, `launch` for a crew) picks up the new
image.

| You rebuilt... | What needs recreating | How |
|:----------------|:-----------------------|:----|
| `transport/` (`localhost/transport:latest`) | The `ga-transport` container | `./install.sh` — it `podman rm -f`s and re-`run`s `ga-transport` unconditionally, no crew impact |
| `crews/kirocrew/Containerfile` (`localhost/kirocrew-crew:latest`) | Each existing crew container | `nuke(crew_id, confirm=True)` then `launch(crew_id)` per crew — destroys that crew's workspace and home volumes, so pull out anything needed via `evac` first |

Restarting a stopped crew (idle-stop recovery, or transport's own reboot
`_reconcile_registry` pass) never picks up a rebuilt crew image — it's the
same container, just started again. Only `nuke` + `launch` recreates it
against the current `localhost/kirocrew-crew:latest`.

## Reboot recovery

`podman-restart.service` is enabled at install time — inside the podman
machine guest on macOS, directly on the host on Linux — so the transport
container comes back automatically once Podman is running again (verified —
`--restart=always` alone does not survive a full `podman machine` stop/start
on macOS without this; on Linux it covers a `systemctl --user` restart or
relogin with lingering enabled).

On transport startup, `_reconcile_registry` checks all registered crews:
- Container missing → remove from registry
- Container stopped → restart it, refresh cookie, mark running

## Project layout

```
ghostship/
├── install.sh             # builds images, sets up podman machine, runs transport
├── transport/             # transport MCP server
│   ├── Containerfile
│   ├── server.py
│   └── requirements.txt
├── academy/               # Ghost Academy: the shared pool crews are composed from
│   ├── agents/            # KiroCrew agent definitions — see docs/agents.md
│   │   ├── ghost.json
│   │   ├── spectre.json
│   │   ├── banshee.json
│   │   ├── wraith.json
│   │   ├── reaper.json
│   │   └── raven.json
│   ├── skills/            # KiroCrew skill files, manifest-selected per crew type
│   │   ├── openspec-*/    # explore/propose/apply-change/update-change/sync-specs/archive-change
│   │   └── radio/         # inter-agent mbox messaging
│   └── steering/          # crew-wide standing context, manifest-selected per crew type — see docs/architecture.md#steering
│       └── STANDING_ORDERS.md
├── openspec/              # this project's own OpenSpec state (config.yaml, changes/, specs/)
├── crews/                 # crew type definitions — each composes a crew from academy/
│   └── kirocrew/          # the one crew type today
│       ├── Containerfile  # FROM kirocrew:stable + Node 24 LTS + openspec CLI + extras
│       ├── seed_kiro_db.py
│       └── manifest.json  # which academy/ agents, skills, steering this crew type includes
└── docs/                  # this folder
```
