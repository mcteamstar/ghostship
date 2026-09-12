# Architecture

## Components

**ga-transport** — the MCP server (`transport/server.py`). Runs as a `podman run` container bound to `localhost`. Manages crew containers via the Podman socket and exposes the `ghostship` tools. Optionally runs on a **dedicated Podman machine** (macOS) or **dedicated systemd socket-activated instance** (Linux) — see `GA_DEDICATED_MACHINE` in [configuration.md](configuration.md).

**Crew containers** — on-demand KiroCrew instances (`localhost/spec-ops:latest`), named `gs-<id>`. Each has a workspace volume (`gs-vol-<id>`) and a home volume (`gs-home-<id>`). Created by `launch`, torn down by `nuke`. All join `ga-starboard` so transport can reach them by name (`http://gs-<id>:5476`). Isolated from `ga-portal` by network topology — see [Networking](#networking-trn-107-portsidestarboard-split).

**Crew image** (`crews/spec-ops/Containerfile`) — extends `ghcr.io/kirodotdev/kirocrew:0.6.0` (Debian 12, Python 3.12, git, curl). Adds Node.js 24 LTS and the `openspec` CLI. Built locally at install time as `localhost/spec-ops:latest` via three stages:

1. **`base-admission`** — mail stack and auth layer: installs `mailutils`, `msmtp-mta`, provisions Maildir structure, adds `maildeliver` and `verify-admiral-sig`. Extends `ghcr.io/kirodotdev/kirocrew:0.6.0`.
2. **`spec-ops` composition** — adds Node.js 24 LTS and the `openspec` CLI. Extends `base-admission`.
3. **`base-graduation`** — pre-seeds the kiro-cli SQLite DB schema (`seed_kiro_db.py`) so auth injection works without migrations at every launch. Extends the `spec-ops` intermediate image.

See [configuration.md](configuration.md#extending-the-crew-image) to add packages.

## Ghost Academy

![Fleet and crew hierarchy: Admiral → fleet → ghostship → crew → Captain → agents](images/docs-fleet-hierarchy.png)

Every ghostship shares the same foundation: [`academy/agents/`](../academy/agents/), [`academy/skills/`](../academy/skills/), and [`academy/steering/`](../academy/steering/) — bind-mounted into transport and copied into every crew at `launch`, filtered by the crew type's manifest (`crews/<crew-type>/manifest.json`). Each manifest key (`agents`, `skills`, `steering`) is either `"*"` or an explicit array. The only crew type today, `spec-ops`, uses `"*"` for every key — the manifest is groundwork for a future second crew type, not a current restriction.

Development inside a ghostship follows [OpenSpec](https://github.com/Fission-AI/OpenSpec)'s spec-driven workflow — explore → propose → apply → archive — split across five worker personas: Spectre drives the front half (explore, propose, update-change); Ghost implements; Reaper syncs specs and archives. Raven is the sixth, coordination-only persona. See [agents.md](agents.md) and [Steering](#steering).

## Crew lifecycle

```
launch(crew_id)
  1. Check the ga-kiro-auth file (DATA_DIR/ga-kiro-auth, not a Podman secret)
     └── missing → start kiro-cli device auth flow, return login URL
                   call launch again after auth to finish setup
  2. Create gs-vol-<id> + gs-home-<id> volumes
  3. Generate the Admiral Ed25519 keypair and register the public key as a
     Podman secret (`admiral-pubkey-<id>`). Must precede container creation:
     a Podman secret can only be attached at create time. The private seed is
     persisted (hex, mode 0600) to DATA_DIR/secrets/<id>.admiral_secret;
     crews.json stores only a non-reversible identifier.
  4. Start crew container with the public key as a read-only secret at
     `/run/secrets/.admiral_public_key` (root-owned, 0444). Placed outside
     home/workspace volumes — Podman creates secret parent dirs as root:root,
     which would block the crew from writing its own config.
  5. Wait for gateway ready (GET / on :5476, 30s timeout)
  6. Inject kiro-cli auth rows into crew's SQLite DB
  7. Patch KiroCrew config (agent, dangerously_skip_permissions=true,
     spawn_min_memory_gb, resource_pressure_gb, resource_critical_gb,
     subagent_timeout_secs, subagent_max_turns, default_agent=ghost,
     reasoning_effort=max)
  8. Restart container (workers pick up auth + config)
  9. Wait for gateway ready again
  10. Copy manifest-selected agent JSONs from /agents bind-mount
  11. Copy manifest-selected skill dirs from /skills bind-mount
  12. Copy manifest-selected steering docs from /steering bind-mount
  13. Seed a shared OpenSpec store at the workspace root (see below)
  14. GA_GIT_AUTHOR_NAME/GA_GIT_AUTHOR_EMAIL are set as container env vars at
      create time — no action needed at this step
  15. Inject governance policy: HMAC-SHA256-sign the canonical policy body and
      write security_policy.json + admission_policy.json into ~/.kiro/crew/.
      Failure is logged but never aborts launch.
  16. Patch agent model files to the pinned model in each agent's JSON
  17. Mint a session token (TTL 24h), exchange for cookie
  18. Register in /data/crews.json with last_used set to setup completion time
  └── returns { status: "ready" } (~30s)

nuke(crew_id, confirm=True)
  └── stop container, remove container + both volumes, deregister
```

### Repository transfer

See [configuration.md](../docs/configuration.md#git-repository-transfer) for bundle instructions. Create a bundle locally, call `supply(path="repo", crew_id="<id>", bundle=True)`, and POST the bundle bytes to the returned URL. For extraction, call `evac(path="repo", ..., bundle=True)` and clone or fetch the downloaded bundle.

### Captain supervision

The manual persona sequence is the default. To opt in: call `captain(crew_id, action="order", message="<standing order>", interval=<n>)` or supply a cron expression. Transport appends the order to `captain@localhost` and creates a recurring `/api/crons` job that dispatches Raven. When `interval` is set, Raven is dispatched immediately by default — `fire_immediately=False` suppresses this.

For standard OpenSpec work use the built-in `sdd` template:
`captain(crew_id, action="order", template="sdd", change_name="<change>", interval=<n>)`. Raven assesses OpenSpec status and `tasks.md`, dispatches Spectre while planning is incomplete, Ghost while tasks remain unchecked, Banshee for review, and Reaper to sync and archive after a clean review. One unresolved review cycle may be fixed and re-reviewed; further findings are escalated to the Admiral. `change_name` accepts a single name or comma-separated list for parallel multi-change execution with automatic worktree isolation.

For multi-angle review use the `independent-review` template:
`captain(crew_id, action="order", template="independent-review", interval=<n>)`. On each tick, Raven dispatches four concurrent reviewers (Banshee × 3 for security/quality/test-coverage, Wraith for docs) and mails a consolidated summary to the Admiral.

`captain(..., action="status")` reports Raven job state, last-run summary, and mailbox counts. `action="stop"` pauses the job without deleting history or the mailbox.

`transport://orders` returns a summary index (name + one-line description per template). `transport://orders/{name}` returns the full resolved body. `GA_ORDERS_DIR` lets operators point at custom `.md` templates that merge with and can override `academy/orders/`.

## Steering

kiro-cli loads every `.md` under `~/.kiro/steering/` for every session — steering is crew-wide standing context every dispatched task gets automatically. `_copy_steering` copies manifest-selected files from `academy/steering/` into that path at every `launch`.

Kept deliberately narrow: environment facts every persona needs (working-directory isolation, shared OpenSpec store, when to use mail) — not project conventions, which belong in whatever repo the caller delivers into `repo/`. See [academy/steering/STANDING_ORDERS.md](../academy/steering/STANDING_ORDERS.md).

## Shared OpenSpec store

Every `dispatch` runs in its own `subagent_<task_id>/` subdirectory. Without intervention, two agents could never share OpenSpec state — each would resolve to its own private, empty store.

`launch` closes this by running `openspec init --tools none --no-animation --force` once at the workspace root, one level above every `subagent_*/` dir. All dispatched tasks then resolve to the same shared store automatically. The store sits as a sibling to `repo/`, never inside it. `--force` makes the call idempotent.

## Task retention and force-stop

Every `dispatch` requests a retained run (`keep=true`), keeping each task's session data available for continuation after a forceful stop.

`steer(task_id, message, crew_id, force=False)` defaults to turn-boundary behaviour: a running task receives `/steer`; a completed task uses `/continue`. With `force=True` on a running task, transport calls `DELETE /api/spawn/{task_id}` then `POST /api/spawn/{task_id}/continue` and returns `force_redeployed`. A completed task follows the normal `/continue` path even with `force=True`.

Recurring jobs created by `schedule` use `persistent_session=True` on `/api/crons`.

`pickup(task_id=None, crew_id=None, timeout_secs=0)` — unified status and polling tool (aliases: bridge, patrol, poll, watch, wait, monitor, hold).

- **timeout_secs=0 (default):** check once and return immediately.
- **timeout_secs > 0:** poll every 3s until the task completes or the timeout elapses; returns not-done state on timeout.

`pickup` always includes mail state:

- **Single-task:** `agent_mail` (unread count for the task's agent persona) and `admiral_mail`.
- **List-all:** `mail_summary` (dict of persona → count) and `admiral_mail`.

When polling, `pickup` captures the Admiral mail count at loop start. If the count increases mid-poll, it returns early with `reason: "admiral_mail"`.

## Idle stop + auto-restart

Crew containers stop after `GA_IDLE_TIMEOUT_SECS` (default 300s) of no activity, tracked via `last_used`. Active `dispatch` tasks and cron executions refresh the timestamp. An enabled schedule alone does not pin a crew.

**Captain check-in interval:** Recommended Raven check-in is 60s (`interval=60`), keeping the gap between worker completion and Raven's next check inside the 300s idle window.

`_ensure_crew_running` transparently restarts a stopped container, waits for the gateway, and refreshes the session cookie before forwarding the request. Called by `dispatch`, `pickup`, `steer`, `evac`, `supply`, and `schedule`. Concurrent restart races are serialised with a per-crew `threading.Event`.

## Known workarounds

Deliberate hacks for upstream bugs or limitations. Each is marked `# WORKAROUND:` in the source. See [docs/troubleshooting.md](troubleshooting.md#known-workarounds) for the full inventory and removal conditions.

## Rebuilding images

`podman start` restarts the *existing* container — it does not recreate from the current image tag. Rebuilding an image has no effect on existing containers; only a fresh `podman run` picks up the new image.

| You rebuilt... | What needs recreating | How |
|:----------------|:-----------------------|:----|
| `transport/` (`localhost/transport:latest`) | The `ga-transport` container | `./install.sh` — `podman rm -f`s and re-`run`s `ga-transport`, no crew impact |
| `crews/spec-ops/Containerfile` (`localhost/spec-ops:latest`) | Each existing crew container | `nuke(crew_id)` then `launch(crew_id)` — destroys workspace and home volumes; pull anything needed via `evac` first |

Restarting a stopped crew never picks up a rebuilt image — only `nuke` + `launch` recreates against the current image.

## Starting and restarting

`./start.sh` brings ghostship back up after a stop — starts the Podman service (or machine on macOS) and `ga-transport`.

```bash
./start.sh                            # auto-discovers config
./start.sh --config ~/ghostship.conf  # explicit config
./start.sh --machine-name my-academy  # override machine name
```

`start.sh` uses `podman compose up -d` against a Compose file generated at install time at `${DATA_DIR}/compose.yml`.

Config discovery order (first match wins):
1. `<ghostship-dir>/ghostship.conf`
2. `~/ghostship.conf`
3. `~/.config/ghostship/ghostship.conf`

On Linux with systemd, `start.sh` uses `systemctl --user start` for the Podman service. Without systemd (WSL) it spawns the service as a background process directly.

**Linger (Linux):** `install.sh` runs `loginctl enable-linger` so the user's systemd slice stays alive after logout — required for unattended operation on headless/SSH-only servers. See `docs/troubleshooting.md` for verification.

On transport startup, `_reconcile_registry` checks all registered crews:
- Container missing → remove from registry
- Container stopped → restart it, refresh cookie, mark running

## Project layout

```
ghostship/
├── install.sh             # builds images, sets up podman service/machine, runs transport
├── start.sh               # starts Podman + ga-transport; run after a reboot or manual stop
├── uninstall.sh           # tears down transport; --purge-auth also removes kiro-cli credentials
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
│   │   └── ghostship-mail/  # inter-agent mbox messaging
│   ├── steering/          # crew-wide standing context — see docs/architecture.md#steering
│   │   └── STANDING_ORDERS.md
│   ├── orders/            # built-in Captain standing-order templates (e.g. sdd)
│   └── policies/          # governance policy templates (bind-mounted as /policies/<composition>.json)
├── .claude-plugin/        # dual-format plugin package (Agent Plugins v1.0.0 + Claude Code)
│   ├── plugin.json
│   ├── .claude-plugin/plugin.json
│   ├── mcp.json
│   ├── .mcp.json
│   ├── marketplace.json
│   ├── PACKAGING.md
│   └── skills/
│       ├── EXTERNAL_SKILLS.md
│       ├── ghostship-admin/   # install, connect, upgrade, tear down
│       └── ghostship-command/ # drives a connected fleet: launch, dispatch, pickup/steer, Captain, nuke
├── config/                # example config files (ghostship.conf.example)
├── crews/                 # crew type definitions
│   ├── registry.json
│   ├── _base/
│   │   ├── admission/     # stage 1: mail stack + auth layer
│   │   └── graduation/    # stage 3: kiro-cli DB pre-seed
│   └── spec-ops/          # stage 2: adds Node.js 24 LTS + openspec CLI
│       ├── Containerfile
│       └── manifest.json
├── tests/                 # test suite (unit/, integration/, e2e/)
├── openspec/              # this project's own OpenSpec state (config.yaml, changes/, specs/)
└── docs/                  # this folder
```

## Operator governance

Ghostship uses the KiroCrew **operator tier** — a static-file-at-boot governance model where transport writes config into each crew container during setup and the gateway enforces it as an unforgeable ceiling the agent cannot weaken.

### Policy injection

During `_finish_crew_setup`:

1. Transport reads a policy template from `/policies/<composition>.json` (bind-mounted from `academy/policies/`), falling back to `/policies/default.json`.
2. The canonical (sorted-keys) JSON body is HMAC-SHA256 signed with the crew's `policy_signing_key` — distinct from the Admiral keypair.
3. Two files are written into `~/.kiro/crew/` inside the container:
   - `security_policy.json` — the governance ceiling
   - `admission_policy.json` — contains `require_policy_signature: true` and the HMAC signature
4. `policy_version` is stored in the crew registry and returned in `launch()` and `crews()` responses.

Policy injection failure is logged but never aborts launch.

### Policy templates

| Template | Used by | Description |
|:---------|:--------|:------------|
| `default.json` | `spec-ops` (and any composition without its own template) | Platform-integrity focus: blocks `git push`, `gh`, pipe-to-shell, messaging integrations |
| `research.json` | `kirocrew-research` | Same as default; starting point for customisation |
| `strict.json` | Example only (not applied by default) | Adds `sandbox.min_level`, `filesystem.write` bounds, broader command denials |

### Security properties

- The container is the security boundary. Default policy covers platform integrity only — no filesystem, sandbox, or network restrictions.
- Policy is HMAC-signed with `policy_signing_key`. A tampered policy causes a signature mismatch and the gateway refuses to continue.
- The Admiral private key never enters the container, so the agent cannot forge an Admiral standing order. The agent can read `policy_signing_key` from `admission_policy.json` and could forge a policy signature — see [auth.md](auth.md) for the threat model.
- Policy is set once at launch. To change policy, nuke and relaunch.

## Networking

Ghost Academy uses two static Podman networks, replacing the retired `ga-net`:

```
  Internet / host
       │
  [ga-portal] ──────────────────────────────┐
       │        ga-portside                  │
  [ga-transport]                            │
       │        ga-starboard                │
  [gs-alpha]  [gs-beta]  [gs-gamma]  ...   │
  (all crews, login containers)             │
                                           │
  GA_TRANSPORT_SECRET flows on ga-portside ───┘
  (ga-transport rejects any request missing X-Transport-Token)
```

**ga-portside** — connects `ga-portal` (Caddy) and `ga-transport` only. Crew containers are NOT on this network.

**ga-starboard** — connects `ga-transport` and all crew containers (`gs-*`) plus ephemeral `ga-login-*` containers. `ga-portal` is NOT on this network.

### Three-control security model

1. **Network split** — `ga-portal` cannot resolve crew container hostnames; crew containers cannot resolve `ga-portal`.
2. **GA_TRANSPORT_SECRET** — `ga-portal` injects `X-Transport-Token` on every upstream request. `ga-transport`'s `TransportSecretMiddleware` rejects missing or wrong tokens (HTTP 401). Crew containers can dial `ga-transport` at TCP but never receive `GA_TRANSPORT_SECRET` and cannot forge the header.
3. **IP-bound cookies** — crew gateway cookies (`mc_token_5476`) are bound to the originating IP. Cross-crew session attempts return 403.

### GA_TRANSPORT_SECRET lifecycle

- Generated by `install.sh` using `openssl rand -hex 32`, stored as Podman secret `ga-transport-secret` (idempotent).
- Mounted into `ga-transport` at `/run/secrets/ga-transport-secret`.
- Mounted into `ga-portal`; Caddy reads it via `{file./run/secrets/ga-transport-secret}` in the reverse proxy config.
- Registered with the transport's log redaction filter at startup; never appears in logs or errors.

