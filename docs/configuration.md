# Configuration

## Environment variables

These variables are baked into the transport container by `install.sh` at `podman run` time (via `-e "VAR=value"`). Operators do **not** set them by exporting shell variables — `install.sh` resolves each through its default → config file → CLI flag hierarchy and passes the resolved value to the container.

| Variable | Default | Description |
|:---------|:--------|:------------|
| `HOST` | `0.0.0.0` | Interface the transport binds to inside the container. `install.sh` adds `-p "127.0.0.1:PORT:PORT"` so the port is only reachable from localhost on the host. |
| `PORT` | `64057` | Transport server port (MCP + file routes). Set via `install.sh --port <port>`. |
| `KC_IMAGE` | `localhost/spec-ops:latest` | Crew container image. |
| `KC_BASE_IMAGE` | `ghcr.io/kirodotdev/kirocrew:0.5.0` | Base KiroCrew image for ephemeral login containers (`/login` flow). Not the crew runtime image (`KC_IMAGE`). Override when pulling from a private registry or pinning a tag. |
| `GA_MAX_CREWS` | `20` | Maximum registered crews (running + stopped). Stopped crews cost no memory; this is a housekeeping limit. |
| `GA_MAX_ACTIVE_CREWS` | `3` | Maximum simultaneously running crews. Enforced on restart — if the running count equals this limit, restart is refused until another crew idles out. Set to `0` to disable. At ~2–3 GB per running crew, the default of 3 fits an 8 GB host. |
| `GA_IDLE_TIMEOUT_SECS` | `300` | Seconds idle before the container is stopped. |
| `KC_MODEL_OVERRIDE` | _(unset)_ | Operator-wide model override (via `--model`). Takes precedence over per-agent defaults. Leave unset to use each agent's own default. |
| `KC_MODEL_DEFAULT` | _(unset)_ | Global model fallback written as `default_model` in `config.local.json`. Lower precedence than `KC_MODEL_OVERRIDE` and per-agent model fields. Set via `--model-default`. Full precedence: `KC_MODEL_OVERRIDE` > per-agent model > `KC_MODEL_DEFAULT` > KiroCrew built-in. |
| `TRANSPORT_DATA_DIR` | `/data` | Registry and data directory. |
| `PODMAN_SOCKET` | `/run/user/1000/podman/podman.sock` | Podman socket path. On Linux uses host uid (`id -u`); on macOS uses the `podman machine` guest uid (`podman machine ssh -- id -u`), which may differ. |
| `GA_HOST_URL` | `http://localhost:<PORT>` | Base URL baked into presigned `evac`/`supply` links. Set for externally-reachable deployments. |
| `GA_FILE_SECRET` | unset (random per process) | HMAC secret signing presigned file URLs. Set explicitly if presigned URLs must survive a transport restart. |
| `GA_API_KEY` | _(unset)_ | API key delivered via Podman secret (`--secret ga-api-key`). Set via `install.sh --api-key <key>` — persisted to the data directory and reused on later installs; `--api-key ""` clears it. **Never log, print, or embed this value.** See [auth.md](auth.md). |
| `KIRO_IDENTITY_PROVIDER` | unset (Builder ID fallback) | kiro-cli identity provider URL for crew logins. See [auth.md](auth.md). |
| `KIRO_REGION` | unset | AWS region for the identity provider. |
| `KIRO_LICENSE` | unset | kiro-cli license type, if required by the identity provider. |
| `KIRO_API_KEY` | _(unset)_ | API key for headless kiro-cli authentication in crew containers — bypasses the interactive device auth flow. See [auth.md](auth.md). |
| `GA_MIN_FREE_MEM_GB` | `2.0` | Minimum available memory (GB) before starting a crew container. Checked against `MemAvailable` from `/proc/meminfo` (falls back to `MemFree`), polled every 5 s for up to 60 s. Set to `0` to disable. |
| `GA_DEDICATED_MACHINE` | `true` | Provisions a dedicated Podman machine (macOS) or systemd socket-activated instance (Linux) for Ghost Academy. Set to `false` to use the default socket. |
| `GA_MACHINE_CPUS` | `8` | vCPUs for the dedicated Podman machine VM (macOS only; a cap, not a reservation). Ignored on Linux. |
| `GA_MACHINE_MEMORY` | `16384` | Memory in MB for the dedicated Podman machine VM (macOS only). A ceiling backed on demand by Apple's Virtualization.framework; idle usage stays well below this. Ignored on Linux. |
| `GA_MACHINE_DISK` | `100` | Disk in GB for the dedicated Podman machine VM (macOS only). Backed by a sparse file. Ignored on Linux. |
| `GA_MACHINE_NAME` | `ghost-academy` | Dedicated machine name (macOS) or systemd service suffix (Linux). Used in `podman machine` commands and as the `podman-<name>.socket`/`.service` name. |
| `GA_SPAWN_MIN_MEMORY_GB` | `1.5` | Patched into each crew's `spawn_min_memory_gb` (KiroCrew subagent admission gate). Set lower than `GA_MIN_FREE_MEM_GB` so the transport's outer gate fires first. |
| `GA_RESOURCE_PRESSURE_GB` | `2.0` | Patched into each crew's `resource_pressure_gb` — KiroCrew throttles subagent spawning below this threshold. |
| `GA_RESOURCE_CRITICAL_GB` | `1.0` | Patched into each crew's `resource_critical_gb` — KiroCrew refuses subagent spawning below this hard floor. |
| `GA_SUBAGENT_TIMEOUT_SECS` | `3600` | Patched into each crew's `subagent_timeout_secs` — maximum wall-clock seconds per subagent task. |
| `GA_SUBAGENT_MAX_TURNS` | `200` | Patched into each crew's `subagent_max_turns` — maximum tool-call turns per subagent task. |
| `GA_BATCH_MAX_TASKS` | `20` | Maximum tasks in a single batch dispatch call (`tasks=[...]`). Requests exceeding this are rejected before any task is spawned. |
| `GA_PREWARM_ENABLED` | `false` | Master switch for ACP prewarm. When `false` (default), the `prewarm` tool and `POST /crews/{crew_id}/prewarm` endpoint do nothing. Set to `true` (or `1`/`yes`/`on`) to allow on-demand warm-up of a crew's `kiro-cli-chat` session before dispatch. Prewarm respects `GA_MIN_FREE_MEM_GB` and `GA_MAX_ACTIVE_CREWS`; warmed-but-unused sessions are reaped by `session.timeout_secs`. |
| `GA_PREWARM_TTL_SECS` | `300` | Idempotency window for prewarm (seconds). A `prewarm` call on a crew warmed within this window returns `already_warm`. Capped at the crew's effective `session.timeout_secs` (300). Only consulted when `GA_PREWARM_ENABLED=true`. |
| `GA_CREW_AGENT` | `kiro` | Patched into each crew's `agent` field in `config.local.json`. KiroCrew 0.5.0 requires this field — crew creation fails with 4xx if absent. Override only if your instance uses a differently-named built-in agent. |
| `GA_TLS_MIN_VERSION` | `1.2` | Minimum TLS version when the transport terminates TLS directly (`1.2` or `1.3`). Only takes effect when both `GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` are set. |
| `GA_TLS_CERTFILE` | _(unset)_ | Path to a TLS certificate file. Setting both this and `GA_TLS_KEYFILE` enables direct TLS termination. |
| `GA_TLS_KEYFILE` | _(unset)_ | Path to the TLS private key paired with `GA_TLS_CERTFILE`. |
| `GA_ENABLE_SECURITY_HEADERS` | `1` | Emit baseline security response headers (HSTS, etc.). Disable by setting to `0`, `false`, or empty. |
| `GA_RATE_LIMIT_ENABLED` | `true` | Master switch for HTTP rate limiting. Set to `false` to disable `RateLimitMiddleware` entirely. See [Rate limiting](#rate-limiting). |
| `GA_RATE_LIMIT_LOGIN_GET` | `30:60` | `GET /login` limit (`<count>:<window_secs>`). On parse failure the default is used and a `WARNING` is logged. |
| `GA_RATE_LIMIT_LOGIN_POST` | `5:300` | `POST /login` limit (`<count>:<window_secs>`). |
| `GA_RATE_LIMIT_MCP` | `300:60` | `/mcp` (and sub-paths) limit (`<count>:<window_secs>`). |
| `GA_RATE_LIMIT_FILES` | `60:60` | `/files/*` limit (`<count>:<window_secs>`). |
| `GA_RATE_LIMIT_CREW_API` | `120:60` | `/crews/*/api/*` limit (`<count>:<window_secs>`). |
| `GA_RATE_LIMIT_DASHBOARD_AUTH` | `600:60` | `/dashboard/auth` limit — the Caddy `forward_auth` endpoint polled on every dashboard request. |
| `GA_GIT_AUTHOR_NAME` | _(unset)_ | Injected as `GIT_AUTHOR_NAME` and `GIT_COMMITTER_NAME` into every crew container at setup. When set with `GA_GIT_AUTHOR_EMAIL`, all agent commits carry the operator's identity. Config-file-only. |
| `GA_GIT_AUTHOR_EMAIL` | _(unset)_ | Injected as `GIT_AUTHOR_EMAIL` and `GIT_COMMITTER_EMAIL`. Both this and `GA_GIT_AUTHOR_NAME` must be set for injection to occur. Config-file-only. |
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First host port in the dashboard proxy port range. Config-file-only. |
| `GA_DASHBOARD_DEFAULT` | `false` | When `true`, every `launch()` call allocates a dashboard by default. Equivalent to always passing `dashboard=True`. Explicit `dashboard=False` on a `launch()` call overrides this. |
| `GA_ORDERS_DIR` | _(unset)_ | Path to an operator-managed directory of additional standing-order template `.md` files. When set and the path exists, its templates are merged with built-in `academy/orders/` templates; a user-defined template whose filename stem matches a built-in name takes precedence. A warning is logged if the path is set but missing. Config-file-only. |
| `GA_PORTAL_TLS_MODE` | `off` | TLS mode for Caddy-owned listeners. One of: `internal` (Caddy built-in CA; requires a one-time `caddy trust` step), `tailscale` (browser-trusted `.ts.net` certs), `acme` (Let's Encrypt; requires `GA_PORTAL_DOMAIN` and ports 80/443), `off` (plain HTTP). Unrecognised values fall back to `internal` with a WARNING. |
| `GA_PORTAL_DOMAIN` | _(unset)_ | Domain name for ACME certificate requests. Required when `GA_PORTAL_TLS_MODE=acme`. |
| `PORT` / ~~`GA_PORTAL_PORT`~~ | `64057` | Port Caddy listens on. `GA_PORTAL_PORT` is the deprecated alias; `install.sh` auto-migrates config files still using it. |
| `GA_PORTAL_SESSION_TTL_SECS` | `86400` | TTL (seconds) for `gs_session` cookies issued by `/dashboard/login`. Sessions are in-memory and reset on transport restart. |
| `GA_TRANSPORT_SECRET` | _(auto-generated by `install.sh`)_ | **Not user-settable directly.** Shared secret between `ga-portal` (Caddy) and `ga-transport`. Generated with `openssl rand -hex 32`, stored as Podman secret `ga-transport-secret`. Caddy injects it as `X-Transport-Token` on every upstream request; the transport rejects requests with a missing or wrong token with HTTP 401. Preserved across reinstalls. To rotate: delete the `ga-transport-secret` Podman secret and re-run `install.sh`. |

> **Network topology:** Two static Podman networks replace the retired `ga-net`:
> - **`ga-portside`** — `ga-portal` ↔ `ga-transport` only. Crew containers are not on this network.
> - **`ga-starboard`** — `ga-transport` ↔ all crew containers (`gs-*`) and login containers.
>
> Crew containers on `ga-starboard` can dial `ga-transport` at the TCP layer but are blocked at the application layer by `GA_TRANSPORT_SECRET`. `ga-portal` cannot reach crew containers by hostname. See `docs/architecture.md` for the full security model.
>
> **Upgrading from `ga-net`:** The transport automatically migrates existing crew containers from `ga-net` to `ga-starboard` on first startup after the upgrade. No operator action required. `ga-net` is removed when empty.

> **Internal constant — not user-settable:**
> `CREW_GATEWAY_PORT` (`5476`) is the port the transport uses to reach each crew container's gateway over `ga-starboard`. It is hardcoded in `server.py` and is not configurable.

## Model precedence

Resolved highest to lowest:

1. **`dispatch(model=...)`** — per-call override. Always wins.
2. **`KC_MODEL_OVERRIDE`** — operator-wide override via `--model`.
3. **Per-agent model field** — the `model` field in the agent's JSON under `academy/agents/`.
4. **`KC_MODEL_DEFAULT`** — operator-wide fallback written as `default_model` in `config.local.json`.
5. **KiroCrew built-in default** — used when no operator or per-agent setting is present.

Common patterns:

- **Uniform model**: set `KC_MODEL_OVERRIDE`.
- **Per-agent with fallback**: leave `KC_MODEL_OVERRIDE` unset, set `KC_MODEL_DEFAULT` as the baseline, add per-agent model fields where needed.
- **KiroCrew default everywhere**: leave both unset.

## Config file

`install.sh` accepts `--config <path>` pointing to a shell file that sets default values. The file is sourced before argument parsing, so **CLI flags always win over config-file values**.

### Resolution order

1. **Built-in default** (e.g. `PORT=64057`)
2. **Config file** (sourced from `--config <path>`)
3. **CLI flag** (e.g. `--port 9000`)

> **⚠️ No ambient-environment-variable tier.** Exporting a variable in the invoking shell has no effect on `install.sh` or `uninstall.sh`. Only config files and CLI flags are supported. Move any previously exported values into a config file and pass `--config <path>`.
>
> **Exception — `PODMAN_SOCK`:** Read from the ambient environment before config-file sourcing as a narrow exception to allow overriding the Podman socket without a config file. Does not generalise to other variables.

### Format

A plain shell file that assigns (or exports) variables. Lines starting with `#` are comments.

### Supported variables (flag-mapped)

| Variable | Corresponding flag |
|:---------|:-------------------|
| `PORT` | `--port` |
| `KIRO_IDENTITY_PROVIDER` | `--identity-provider` |
| `KIRO_REGION` | `--region` |
| `KIRO_LICENSE` | `--license` |
| `KC_MODEL_OVERRIDE` | `--model` |
| `KC_MODEL_DEFAULT` | `--model-default` |
| `GA_API_KEY` | `--api-key` |
| `GA_HOST_URL` | `--public-url` |
| `GA_PORTAL_DOMAIN` | `--caddy-domain` |
| `GA_PORTAL_TLS_MODE` | `--caddy-tls-mode` |

Variables not in this table (`GA_MAX_CREWS`, `GA_DEDICATED_MACHINE`, `GA_MACHINE_NAME`, `GA_MIN_FREE_MEM_GB`, `GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_ORDERS_DIR`, `GA_PORTAL_SESSION_TTL_SECS`) are **config-file-only** — no CLI flag, no ambient-environment input.

### Error handling

If `--config <path>` is passed and the file does not exist or is unreadable, `install.sh` aborts immediately. Omitting `--config` skips config-file sourcing (no error).

### Example config file

```bash
# ghostship.conf — site-specific install defaults
# Reference with: ./install.sh --config ./ghostship.conf

KIRO_IDENTITY_PROVIDER="https://identitycenter.amazonaws.com/ssoins-abc123"
KIRO_REGION="us-east-1"
KIRO_LICENSE="pro"
PORT=9000
KC_MODEL_OVERRIDE="anthropic/claude-sonnet-4-20250514"
GA_HOST_URL="https://academy.example.com"
```

CLI flags override any config-file value:

```bash
./install.sh --config ./ghostship.conf --port 8080
# PORT=8080 (flag wins), all other values from config file
```

## Client-only install

`scripts/install.sh --client-only` wires the `ghostship` CLI and agent harnesses (kiro-cli, Claude Code, opencode) to an already-running transport — typically a shared remote academy — without any container infrastructure. In this mode `install.sh` skips Podman prerequisites, machine/network setup, image builds, and `compose up`; it installs the `~/.local/bin/ghostship` symlink and calls `ghostship setup` to register MCP entries and skill symlinks for every detected agent client.

```bash
./install.sh --client-only --url https://academy.example.com/mcp
```

Flags accepted in `--client-only` mode:

- `--url <transport-url>` — MCP endpoint the client connects to. Default: `http://localhost:64057/mcp`.
- `--api-key <key>` — optional bearer token. When supplied, `ghostship setup` registers the MCP entry with an `Authorization: Bearer` header.

`--client-only` is idempotent. These flags are one-shot wiring options and are not config-file variables.

## Git repository transfer

See [Repository transfer](architecture.md#repository-transfer) in architecture.md for bundle instructions (supply, evac, incremental bundles).

## Deployment security boundary

`install.sh` publishes the transport port on `127.0.0.1` only. For remote or shared-network deployments, set `GA_API_KEY` to require bearer authentication on MCP requests and terminate TLS at a trusted reverse proxy or encrypted VPN.

File-transfer routes use HMAC presigned-URL authorization and do **not** require the API key. A valid presigned URL is a bearer capability until its TTL expires, regardless of `GA_API_KEY`. See [auth.md](auth.md).

The Podman socket and unsandboxed crew runtime are additional deployment risks not addressed by API-key authentication.

## Rate limiting

The transport applies per-endpoint HTTP rate limiting via a `RateLimitMiddleware` ASGI layer that sits **outside** bearer-auth middleware, so every caller — including unauthenticated `/login` requests — is subject to limits.

Each limiter is a sliding window keyed on caller identity: source IP alone when no bearer token is presented, or `SHA-256(token)[:8]:<ip>` when one is (the raw token is never stored). The source IP is taken from the first hop of `X-Forwarded-For` when present, falling back to the ASGI client address.

When a caller exceeds a limit:

```
HTTP/1.1 429 Too Many Requests
Content-Type: text/plain; charset=utf-8
Retry-After: <window_secs>

Rate limit exceeded. Retry after <window_secs> seconds.
```

`Retry-After` is the full window duration. `/health` and `/version` are unconditionally exempt. Paths not matched by any registered limiter pass through without a rate check.

| Variable | Default | Endpoint |
|:---------|:--------|:---------|
| `GA_RATE_LIMIT_ENABLED` | `true` | Master switch. `false` removes the middleware entirely and logs an `INFO` confirmation. |
| `GA_RATE_LIMIT_LOGIN_GET` | `30:60` | `GET /login` |
| `GA_RATE_LIMIT_LOGIN_POST` | `5:300` | `POST /login` |
| `GA_RATE_LIMIT_MCP` | `300:60` | `/mcp` and sub-paths |
| `GA_RATE_LIMIT_FILES` | `60:60` | `/files/*` |
| `GA_RATE_LIMIT_CREW_API` | `120:60` | `/crews/{id}/api/*` |
| `GA_RATE_LIMIT_DASHBOARD_AUTH` | `600:60` | `/dashboard/auth` — Caddy `forward_auth` endpoint |

**State is in-memory only.** Restarting the transport resets all counters.

## Extending the crew image

Edit `crews/spec-ops/Containerfile` and re-run `./install.sh`:

```dockerfile
FROM ghcr.io/kirodotdev/kirocrew:0.5.0
USER root
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    nodejs npm \   # already included
    your-package \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER kirocrew
```

The new image is built at install time. Existing crews use the old image until nuked and re-called-down.

## Updating academy/ and crews/

`install.sh` snapshots `academy/` (agents, skills, steering, policies, orders, mcp) and `crews/` from the repo into the data volume at install time. The transport container mounts these from the data volume — it has no runtime dependency on the repo checkout path.

- **Edits under `academy/` or `crews/` take effect only after re-running `./install.sh`.** The transport reads the data-volume snapshot, not the live repo.
- **Moving or deleting the repo after install does not break the transport** — content is fully self-contained in the data volume.
- **Reinstalling is safe** — `install.sh` uses `rsync --delete` (or `rm -rf` + `cp -r` if rsync is absent) to keep the snapshot an exact mirror of the repo, removing stale files automatically.

## MCP server catalogue

Crew agents can be given MCP servers (external tools) that vary by composition. Server definitions live in a catalogue at `academy/mcp/`; compositions opt in via their `manifest.json`.

### Catalogue format (`academy/mcp/`)

Each file in `academy/mcp/` is a named MCP server definition in JSON. The filename stem is the server name referenced from a manifest. `install.sh` snapshots `academy/mcp/` into the data volume, mounted read-only at `/mcp`.

Each JSON object conforms to the kiro-cli `mcpServers` entry format: at minimum a `type` field and either a `url` (HTTP/SSE) or a `command` (stdio) field.

**Stdio server** (`academy/mcp/playwright.json`, shipped as an example):

```json
{
  "type": "stdio",
  "command": "npx",
  "args": ["@playwright/mcp@latest"]
}
```

**HTTP server:**

```json
{
  "type": "streamable-http",
  "url": "http://armory.example.com/mcp"
}
```

**HTTP server with auth header:**

```json
{
  "type": "streamable-http",
  "url": "http://nexus.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ${NEXUS_API_KEY}"
  }
}
```

An empty catalogue is valid — no `mcp.json` is written into crew containers and agents run with only their built-in tools.

### Declaring servers in a composition (`manifest.json → mcpServers`)

A composition's `crews/<name>/manifest.json` gains an optional `mcpServers` array of catalogue server names:

```json
{
  "agents": "*",
  "skills": "*",
  "steering": "*",
  "mcpServers": ["armory", "nexus"]
}
```

At crew setup, `_copy_agents()` resolves each name against `/mcp/<name>.json`, substitutes `${VAR}` references, and writes the resolved configs into `~/.kiro/mcp.json` inside the crew container. Agents reference servers via `@<name>` in their `tools` list.

Behaviour:

- **No `mcpServers` key (or empty array)** → no `mcp.json` written.
- **Name with no matching catalogue file** → warning logged, entry skipped; remaining servers still written, crew setup continues.
- **Entry with a `headers` field** → `poolable: false` added automatically when written into `mcp.json` (KiroCrew 0.5.0 must not pool auth-bearing HTTP servers).

### Secret substitution (`${VAR}`)

Any `${VAR}` reference in a catalogue entry's string values is substituted from the **transport container's environment** when `_copy_agents()` writes the crew's `mcp.json`. This keeps secrets out of committed files.

- **Variable set**: value is substituted.
- **Variable unset**: a warning is logged, the literal `${VAR}` string is written, and crew setup continues (the server will auth-fail at call time).

Pass secrets into the transport environment via the same `install.sh` configuration mechanism used for other `GA_*`/`KIRO_*` variables.

### Per-agent servers

Individual agent JSON files in `academy/agents/` may declare their own `mcpServers` map for servers specific to that agent. kiro-cli resolves agent-level entries before the composition-level `mcp.json`, so a name declared in both is served from the agent's entry. An agent may set `includeMcpJson: false` to opt out of the composition-level `mcp.json` entirely.

## Fixed headless overrides

Every crew launched by the transport receives fixed headless-optimised values written into `config.local.json` at startup by `_patch_crew_config`. These are not operator-tunable.

| Config path | Value | Rationale |
|:------------|:------|:----------|
| `stt.enabled` | `false` | No microphone in a headless crew. Disables Whisper STT (~148 MB base model). |
| `session.eager_spawn` | `false` | Stops pre-forking `kiro-cli-chat` at container startup (~340 MB); spawned on first dispatch instead (adds 2–5 s first-dispatch latency). |
| `session.timeout_secs` | `300` | Reclaim session memory 5 minutes after task completion (vs. 1-hour default). |
| `session.watchdog_rss_max_mb` | `2000` | Hard RSS ceiling per session process (KiroCrew 0.5.0+). Set above the ~1.9 GB active-task peak to avoid recycling healthy sessions; catches runaway RSS accumulation. |
| `telemetry.beacon_enabled` | `false` | Suppress outbound telemetry beacon pings. |
| `auto_update` | `false` | Prevents KiroCrew from self-updating inside a pinned container image. |

### Memory profile

| State | RSS |
|:------|:----|
| Idle (no active task) | ~160 MB (gateway process only) |
| Active task peak | ~1.5–1.9 GB (session + subagents) |
| Post-task (after `session.timeout_secs`) | ~160 MB (session reaped) |

Without these overrides (KiroCrew 0.5.0 defaults), idle RSS is ~470 MB due to the eagerly pre-spawned `kiro-cli-chat` process.

### `session.watchdog_rss_max_mb` guidance

The 2000 MB ceiling is a safety net for accumulation, not a tight budget. If session processes are recycled on legitimate large tasks (e.g. intensive reviews of very large codebases), raise the limit by editing `_patch_crew_config` in `transport/lifecycle.py`.

---

## Remote deployment

Run the transport on a remote Linux host and connect MCP clients from your local machine.

### Prerequisites

- Linux host with Podman >= 4.4 and podman-compose (Ubuntu 22.04+ verified)
- **API key** — required for any non-loopback deployment

### Install

```bash
./install.sh --api-key <your-secret-key> \
  --public-url https://mcp.your-domain.com
```

| Flag | Purpose |
|:-----|:--------|
| `--api-key <key>` | Require bearer auth on all MCP requests |
| `--public-url <url>` | Base URL for all externally-visible links (presigned URLs and MCP endpoint) |
| `--port <port>` | Override the transport listen port |

For IAM Identity Center logins, add `--identity-provider` and `--region` — see [auth.md](auth.md#identity-provider-config).

### TLS

`ga-portal` (Caddy) handles TLS via `GA_PORTAL_TLS_MODE` — see [portal.md](portal.md). To front ghostship with your own existing reverse proxy, proxy to port `64057`:

```nginx
server {
    listen 443 ssl http2;
    server_name mcp.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:64057;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        chunked_transfer_encoding on;
    }
}
```

Or use `GA_PORTAL_TLS_MODE=acme` to let Caddy manage certificates directly:

```bash
GA_PORTAL_TLS_MODE=acme
GA_PORTAL_DOMAIN=mcp.your-domain.com
GA_HOST_URL=https://mcp.your-domain.com
```

### MCP client registration

**kiro-cli:**
```bash
kiro-cli mcp add --name ghostship \
  --url https://mcp.your-domain.com/mcp \
  --headers '{"Authorization": "Bearer ${GHOSTSHIP_API_KEY}"}' \
  --scope global
```

**Claude Code** (`~/.claude.json`):
```json
"ghostship": {
  "type": "http",
  "url": "https://mcp.your-domain.com/mcp",
  "headers": { "Authorization": "Bearer ${GHOSTSHIP_API_KEY}" }
}
```

### Linger (headless servers)

`install.sh` enables `loginctl enable-linger` automatically. Without linger, all user services stop when your last SSH session disconnects.

### Known limitations

- **Single-host only** — no horizontal scaling or HA. Running two transports against the same data directory is unsupported and will corrupt the registry.
- **File transfer** — presigned URLs travel in plaintext when `GA_PORTAL_TLS_MODE=off`; use a non-`off` TLS mode or an external reverse proxy for remote deployments.
- **Podman socket security** — restrict access to `DATA_DIR` and the Podman socket to the service account running the transport on shared hosts.
