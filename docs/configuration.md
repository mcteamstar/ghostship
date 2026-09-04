# Configuration

## Environment variables in the transport container

The following variables are baked into the transport container's runtime
environment by `install.sh` at `podman run` time (via `-e "VAR=value"`
flags). They are **not** variables an operator sets by exporting them in
any shell — `install.sh` resolves each variable internally using the
built-in default → config file → CLI flag hierarchy, then passes the
resolved value to the container. The table documents what the transport
process sees and what each default means:

| Variable | Default | Description |
|:---------|:--------|:------------|
| `HOST` | `0.0.0.0` | Interface the transport binds to inside the container. `install.sh` adds `-p "127.0.0.1:PORT:PORT"` so the port is only reachable from localhost on the host regardless of this value. |
| `PORT` | `64057` | Transport server port (MCP + file routes on the same port) — set via `install.sh --port <port>` |
| `KC_IMAGE` | `localhost/spec-ops:latest` | Crew container image |
| `KC_BASE_IMAGE` | `ghcr.io/kirodotdev/kirocrew:0.4.0` | Base KiroCrew image used for ephemeral login containers (`/login` flow). Not the crew runtime image — that is `KC_IMAGE`. Override when pulling from a private registry or pinning a specific tag |
| `GA_MAX_CREWS` | `20` | Maximum number of registered crews (running + stopped). Stopped crews cost no memory, so this is primarily a housekeeping limit on how many persistent workspaces you keep around. Raise it freely on unconstrained hosts |
| `GA_MAX_ACTIVE_CREWS` | `3` | Maximum number of simultaneously running (active) crew containers. Enforced when a stopped crew is restarted — if the running count already equals this limit, the restart is refused until another crew idles out. Set to `0` to disable the active limit entirely. At ~2–3 GB per running crew, the default of 3 fits comfortably on an 8 GB host |
| `GA_IDLE_TIMEOUT_SECS` | `300` | Seconds idle before stopping container |
| `KC_MODEL_OVERRIDE` | _(unset)_ | When set, overrides the model in all agent JSON files at launch — takes precedence over per-agent defaults. Set via `install.sh --model <model>`. Leave unset to use each agent's own default. |
| `KC_MODEL_DEFAULT` | _(unset)_ | Global model fallback written as `default_model` in `config.local.json`. Applies when no per-agent model field overrides it. Lower precedence than `KC_MODEL_OVERRIDE` and per-agent model field. Set via `install.sh --model-default <model>`. Full precedence order: `KC_MODEL_OVERRIDE` > per-agent model > `KC_MODEL_DEFAULT` > KiroCrew built-in. Omit to leave KiroCrew's built-in default unchanged. |
| `TRANSPORT_DATA_DIR` | `/data` | Registry + data dir |
| `PODMAN_SOCKET` | `/run/user/1000/podman/podman.sock` | Podman socket path — on Linux this is your host uid (`id -u`); on macOS it's the `podman machine` guest's uid (`podman machine ssh -- id -u`), which is often different |
| `GA_HOST_URL` | `http://localhost:<PORT>` | Base URL baked into presigned `evac`/`supply` links — set this for all externally-reachable deployments |
| `GA_FILE_TTL_SECS` | `300` | Seconds a presigned `evac`/`supply` URL stays valid before expiring |
| `KC_GATEWAY_TOKEN_TTL` | `24h` | Duration passed to `kirocrew token --ttl` when setup, restart recovery, or startup reconciliation mints a gateway session token; independent of file URL expiry |
| `GA_FILE_SECRET` | unset (random per process) | HMAC secret signing presigned file URLs — set explicitly if you need presigned URLs to survive a transport restart |
| `GA_API_KEY` | _(unset)_ | API key delivered via Podman secret (`--secret ga-api-key`, read from `/run/secrets/ga-api-key`). Set via `install.sh --api-key <key>` — persisted to your data directory and reused on later installs automatically; `--api-key ""` clears it. **Never log, print, or embed this value.** See [auth.md](auth.md) for client configuration. |
| `KIRO_IDENTITY_PROVIDER` | unset (Builder ID fallback) | kiro-cli identity provider URL for crew logins — see [auth.md](auth.md) |
| `KIRO_REGION` | unset | AWS region for that identity provider |
| `KIRO_LICENSE` | unset | kiro-cli license type, if required by the identity provider |
| `GA_MIN_FREE_MEM_GB` | `2.0` | Minimum available memory (GB) required before starting a crew container. Compared against `MemAvailable` from `/proc/meminfo` (which includes reclaimable page cache and buffers), with a fallback to `MemFree` on kernels that do not expose `MemAvailable`. The transport polls in 5-second intervals up to `GA_MEMORY_WAIT_SECS` for the balloon/hypervisor to free memory. Set to `0` to disable the pre-launch memory gate entirely |
| `GA_DEDICATED_MACHINE` | `true` | Provisions a dedicated Podman machine (macOS) or systemd socket-activated instance (Linux) exclusively for Ghost Academy. Crew containers are fully isolated from the host's default Podman runtime. Set to `false` to use the default socket instead |
| `GA_MACHINE_CPUS` | `8` | vCPUs allocated to the dedicated Podman machine VM (macOS only) — a cap on concurrent vCPU threads, not a reservation; the host scheduler time-shares real cores across them like any other process. Ignored on Linux |
| `GA_MACHINE_MEMORY` | `16384` | Memory in MB allocated to the dedicated Podman machine VM (macOS only) — a ceiling, not an upfront reservation (Apple's Virtualization.framework backs guest RAM on demand, so idle usage stays far below this). Ignored on Linux |
| `GA_MACHINE_DISK` | `100` | Disk size in GB allocated to the dedicated Podman machine VM (macOS only) — backed by a sparse file, so this is an apparent-size ceiling; actual disk blocks are only consumed as data is written. Ignored on Linux |
| `GA_MACHINE_NAME` | `ghost-academy` | Name of the dedicated machine (macOS) or systemd service suffix (Linux). Used as the machine name in `podman machine` commands and as the service name in `podman-<name>.socket`/`.service` |
| `GA_MEMORY_WAIT_SECS` | `60` | Maximum seconds to wait for sufficient memory before returning an error. Only relevant when `GA_MIN_FREE_MEM_GB > 0` |
| `GA_SPAWN_MIN_MEMORY_GB` | `1.5` | Value patched into each crew's `spawn_min_memory_gb` config (KiroCrew's internal subagent admission gate). Set lower than `GA_MIN_FREE_MEM_GB` so the transport's outer gate triggers first |
| `GA_RESOURCE_PRESSURE_GB` | `2.0` | Value patched into each crew's `resource_pressure_gb` config — KiroCrew throttles subagent spawning below this threshold |
| `GA_RESOURCE_CRITICAL_GB` | `1.0` | Value patched into each crew's `resource_critical_gb` config — KiroCrew refuses subagent spawning below this hard floor |
| `GA_SUBAGENT_TIMEOUT_SECS` | `3600` | Value patched into each crew's `subagent_timeout_secs` config — maximum wall-clock seconds per subagent task. Increase for long-running implementation work |
| `GA_SUBAGENT_MAX_TURNS` | `200` | Value patched into each crew's `subagent_max_turns` config — maximum tool-call turns per subagent task. Increase for complex multi-file changes |
| `GA_CREW_AGENT` | `kiro` | Value patched into each crew's `agent` config field in `config.local.json`. KiroCrew 0.4.0 requires this field to be present — crew creation fails at the gateway with a 4xx if it is absent. Defaults to `kiro` (KiroCrew's built-in agent name); override only if your KiroCrew instance uses a differently-named built-in agent |
| `GA_PICKUP_MAX_POLL_SECS` | `30` | Maximum seconds the transport holds an HTTP connection open during a `pickup(timeout_secs=N)` long-poll. When this cap fires before the caller's `timeout_secs` elapses, `pickup` returns a normal JSON response with `"reason": "timeout"` so the caller can re-poll — the MCP transport error path is never used for a clean timeout expiry. Set lower if your MCP client has a short read timeout; set higher if you have confirmed your client tolerates longer-lived connections |
| `GA_TLS_MIN_VERSION` | `1.2` | Minimum TLS version enforced when the transport terminates TLS directly (passed as `ssl_version` to uvicorn). Values: `1.2` or `1.3`. Only takes effect when `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` are set |
| `GA_TLS_CERTFILE` | _(unset)_ | Path to a TLS certificate file. Setting both this and `GA_TLS_KEYFILE` enables direct TLS termination in the transport rather than relying on an edge terminator |
| `GA_TLS_KEYFILE` | _(unset)_ | Path to the TLS private key file paired with `GA_TLS_CERTFILE` |
| `GA_ENABLE_SECURITY_HEADERS` | `1` | Emit baseline security response headers (HSTS, etc.). On unless set to `0`, `false`, or empty |
| `GA_ENFORCE_HTTPS_REDIRECT` | `0` | 301-redirect plaintext HTTP requests to HTTPS. Staged rollout — default off until the monitored plaintext window and client notice are complete. Enable with `1` or `true` |
| `GA_CSP_ENFORCE` | `0` | Send the Content-Security-Policy header as enforcing rather than report-only. Staged rollout — default off until report-only violations are triaged. Enable with `1` or `true` |
| `GA_RATE_LIMIT_ENABLED` | `true` | Master switch for HTTP rate limiting. Set to `false` to disable the `RateLimitMiddleware` entirely; any other value (default) leaves it enabled. See [Rate limiting](#rate-limiting) below |
| `GA_RATE_LIMIT_LOGIN_GET` | `30:60` | `GET /login` limit in `<count>:<window_secs>` format (both positive integers). On parse failure the default is used and a `WARNING` is logged naming the variable |
| `GA_RATE_LIMIT_LOGIN_POST` | `5:300` | `POST /login` limit in `<count>:<window_secs>` format |
| `GA_RATE_LIMIT_MCP` | `300:60` | `/mcp` (and sub-paths) limit in `<count>:<window_secs>` format |
| `GA_RATE_LIMIT_FILES` | `60:60` | `/files/*` limit in `<count>:<window_secs>` format |
| `GA_RATE_LIMIT_CREW_API` | `120:60` | `/crews/*/api/*` limit in `<count>:<window_secs>` format |
| `GA_GIT_AUTHOR_NAME` | _(unset)_ | Operator name injected as `GIT_AUTHOR_NAME` and `GIT_COMMITTER_NAME` into every crew container at setup time. When set together with `GA_GIT_AUTHOR_EMAIL`, all agent commits carry the operator's identity. When unset, per-persona git identity is used (e.g. `Ghost <ghost@localhost>`). Config-file-only — no CLI flag |
| `GA_GIT_AUTHOR_EMAIL` | _(unset)_ | Operator email injected as `GIT_AUTHOR_EMAIL` and `GIT_COMMITTER_EMAIL` into every crew container at setup time. Both this and `GA_GIT_AUTHOR_NAME` must be set for injection to occur. Config-file-only — no CLI flag |
| `GA_DASHBOARD_PORT_ENABLED` | `true` | Enable/disable the per-crew dashboard proxy. When `true` (default), a `launch(dashboard=True)` call (or `POST /crews/{id}/dashboard`) allocates a dedicated host port and returns a `dashboard_url`. Set to `false` to disable port allocation entirely. Config-file-only. See [dashboard-proxy.md](dashboard-proxy.md) |
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First host port in the dashboard proxy port range. Config-file-only |
| `GA_DASHBOARD_PORT_RANGE_SIZE` | `50` | Number of ports in the range (the cap on concurrent crew dashboards). Config-file-only |
| `GA_PORTSIDE_ENABLED` | `false` | Opt into the Caddy reverse-proxy layer (TRN-92). When `true`, a `ga-portside` container is added to the compose stack; it binds ports 443/80 **and** the dashboard port range and becomes the sole TLS terminator and auth gate. The transport's per-port uvicorn listeners are not started. **Breaking** — re-run `install.sh` after changing this value; no coexistence with the old per-port mode. See [caddy.md](caddy.md) |
| `GA_PORTSIDE_ADMIN_URL` | `http://ga-portside:2019` | URL of the Caddy admin API reachable from inside the transport container. Override when running Caddy at a non-default address |
| `GA_PORTSIDE_TLS_MODE` | `internal` | TLS mode for all Caddy-owned listeners. One of: `internal` (Caddy built-in CA; requires a one-time `caddy trust` step — path printed by `install.sh` and `ghostship status`), `tailscale` (browser-trusted `.ts.net` certs via Tailscale ACME; no trust step), `acme` (public Let's Encrypt; requires `GA_PORTSIDE_DOMAIN` and ports 80/443), `off` (plain HTTP). An unrecognised value logs a WARNING and falls back to `internal` |
| `GA_PORTSIDE_DOMAIN` | _(unset)_ | Domain name used for ACME (Let's Encrypt) certificate requests. Required when `GA_PORTSIDE_TLS_MODE=acme` |
| `GA_PORTSIDE_PORT` | `443` | HTTPS port Caddy listens on for the main server (MCP, files, auth endpoints) |
| `GA_PORTSIDE_HTTP_PORT` | `80` | HTTP port Caddy listens on for ACME challenges and HTTP→HTTPS redirects |
| `GA_PORTSIDE_SESSION_TTL_SECS` | `86400` | TTL (seconds) for `gs_session` cookies issued by `/dashboard-login`. Sessions are held in-memory and reset on transport restart |

> **Internal constant — not user-settable:**
> `CREW_GATEWAY_PORT` (`5476`) is the port the transport uses to reach each
> crew container's gateway over the internal `ga-net` network. It is
> hardcoded in `server.py` and is **not** configurable via environment
> variable. Changing it would require rebuilding both the crew image and the
> transport. All user-facing routes — MCP, the REST API, and file transfer —
> are served on the single `PORT` above; there is no separate file-server port.

## Config file

`install.sh` accepts a `--config <path>` flag pointing to a shell file that
sets default values for any of the variables below. The file is sourced
before argument parsing, so **command-line flags always override config-file
values**.

### Resolution order

For every settable variable, the effective value is resolved in this order
(later tiers unconditionally override earlier ones):

1. **Built-in default** (literal assignment in `install.sh`, e.g. `PORT=64057`)
2. **Config file** (sourced from `--config <path>`, overwrites the built-in)
3. **Command-line flag** (e.g. `--port 9000`, overwrites both)

> **⚠️ Behavior change:** There is **no ambient-environment-variable tier**
> for `install.sh` configuration.
> Exporting a variable in the invoking shell (or in a wrapper script, CI job,
> `.bashrc`, etc.) has no effect on `install.sh` or `uninstall.sh`. Only the
> config file and CLI flags are supported configuration inputs. If you
> previously relied on exported variables reaching the installer, move those
> values into a config file and pass `--config <path>`.
>
> **Exception — `PODMAN_SOCK`:** This single variable *is* read directly from
> the ambient environment by `install.sh`, before config-file sourcing, to
> allow overriding the Podman socket path without a config file. This is a
> deliberate, narrow exception and does not generalise to any other variable.

### Format

A plain shell file that exports (or simply assigns) variables. Lines
starting with `#` are comments.

### Supported variables (flag-mapped)

These variables have a corresponding CLI flag. If neither the config file
nor the flag sets them, the built-in default applies.

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

Variables outside this table (e.g. `GA_MAX_CREWS`, `GA_DEDICATED_MACHINE`,
`GA_MACHINE_NAME`, `GA_MIN_FREE_MEM_GB`, `GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`,
`GA_DASHBOARD_PORT_ENABLED`, `GA_DASHBOARD_PORT_RANGE_START`,
`GA_DASHBOARD_PORT_RANGE_SIZE`, `GA_PORTSIDE_ENABLED`, `GA_PORTSIDE_TLS_MODE`,
`GA_PORTSIDE_DOMAIN`, `GA_PORTSIDE_PORT`, `GA_PORTSIDE_HTTP_PORT`, `GA_PORTSIDE_SESSION_TTL_SECS`) are **config-file-only** — they
have no CLI flag and no ambient-environment-variable input.

### Error handling

If `--config <path>` is passed and the file does not exist or is not
readable, `install.sh` aborts immediately with a clear error message.
Omitting `--config` entirely skips config-file sourcing (no error).

### Example config file

```bash
# ghostship.conf — site-specific install defaults
# Place anywhere; reference with: ./install.sh --config ./ghostship.conf

KIRO_IDENTITY_PROVIDER="https://identitycenter.amazonaws.com/ssoins-abc123"
KIRO_REGION="us-east-1"
KIRO_LICENSE="pro"
PORT=9000
KC_MODEL_OVERRIDE="anthropic/claude-sonnet-4-20250514"
GA_HOST_URL="https://academy.example.com"
```

Then override any single value at the command line:

```bash
./install.sh --config ./ghostship.conf --port 8080
# PORT=8080 (flag wins), all other values from config file
```

## Git repository transfer

See the [Seed or extract a Git repository](../README.md#seed-or-extract-a-git-repository)
section in the README for full bundle instructions (supply, evac, incremental bundles).

## Deployment security boundary

`install.sh` publishes the transport port on `127.0.0.1` only. For remote or
shared-network deployments, set `GA_API_KEY` to require bearer authentication
on MCP requests and terminate TLS at a trusted reverse proxy or encrypted VPN.

The file-transfer routes retain their existing HMAC presigned-URL
authorization — they do **not** require the API key. A valid presigned URL
remains a bearer capability until its TTL expires, regardless of whether
`GA_API_KEY` is set. See [auth.md](auth.md) for the full authentication
model.

The Podman socket and the unsandboxed crew runtime are additional deployment
risks not redesigned by API-key authentication.

## Rate limiting

The transport applies per-endpoint HTTP rate limiting via a
`RateLimitMiddleware` ASGI layer that sits **outside** the bearer-auth
middleware, so every caller — including unauthenticated `/login` requests — is
subject to limits. It complements the brute-force `Throttle` (which counts
failed auth attempts) by bounding request *volume* regardless of outcome.

Each limiter is a sliding window keyed on caller identity: the source IP alone
when no bearer token is presented, or `SHA-256(token)[:8]:<ip>` when one is (the
raw token value is never stored in limiter state). The source IP is taken from
the first hop of `X-Forwarded-For` when present, falling back to the ASGI
client address.

When a caller exceeds a limit the middleware returns:

```
HTTP/1.1 429 Too Many Requests
Content-Type: text/plain; charset=utf-8
Retry-After: <window_secs>

Rate limit exceeded. Retry after <window_secs> seconds.
```

`Retry-After` is the full window duration (conservative — it tells the client
to back off for the whole window rather than retry-looping near the boundary).
`/health` and `/version` are unconditionally exempt and never return `429`. Any
path not matched by a registered limiter (e.g. `/logout`, the `/crews/{id}/ui/`
browser-asset proxy) passes through without a rate check.

Every limit is configured via a `GA_RATE_LIMIT_*` environment variable in
`<count>:<window_secs>` format (both positive integers). On a parse failure the
built-in default is used and a `WARNING` naming the variable is logged.

| Variable | Default | Endpoint |
|:---------|:--------|:---------|
| `GA_RATE_LIMIT_ENABLED` | `true` | Master switch (`true`/`false`). `false` removes the middleware entirely and logs an `INFO` entry confirming rate limiting is disabled |
| `GA_RATE_LIMIT_LOGIN_GET` | `30:60` | `GET /login` — polling allowed, hammering blocked |
| `GA_RATE_LIMIT_LOGIN_POST` | `5:300` | `POST /login` — tight limit enforces deliberate use |
| `GA_RATE_LIMIT_MCP` | `300:60` | `/mcp` and sub-paths — headroom for multi-tool orchestration |
| `GA_RATE_LIMIT_FILES` | `60:60` | `/files/*` — protects git subprocess execution |
| `GA_RATE_LIMIT_CREW_API` | `120:60` | `/crews/{id}/api/*` — the proxied crew REST API |

**State is in-memory only and is not persisted.** Restarting the transport
process resets all counters to zero — no caller is pre-limited based on
pre-restart history. This is the intended behaviour for the single-process
local deployment; a deliberate restart is an effective limit reset.

## Extending the crew image

Edit `crews/spec-ops/Containerfile` and re-run `./install.sh`:

```dockerfile
FROM ghcr.io/kirodotdev/kirocrew:0.4.0
USER root
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    nodejs npm \   # already included
    your-package \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER kirocrew
```

The new image is built at install time. Existing crews continue using the
old image until nuked and re-called-down.

## Updating academy/ and crews/

`install.sh` snapshots `academy/` (agents, skills, steering, policies, orders,
mcp) and `crews/` from the repo into the data volume at install time. The
transport container mounts these from the data volume — it has no runtime
dependency on the repo checkout path.

This means:

- **Editing files under `academy/` or `crews/` in the repo takes effect only
  after re-running `./install.sh`.** A running transport reads the snapshot in
  the data volume, not the live repo.
- **Moving or deleting the repo after install does not break the transport** —
  the academy/crews content is fully self-contained in the data volume.
- **Reinstalling is always safe** — `install.sh` uses `rsync --delete` (or
  `rm -rf` + `cp -r` if rsync is absent) so the data-volume snapshot is always
  an exact mirror of the repo at install time. Stale files from a previous
  install are removed automatically.

## MCP server catalogue

Crew agents can be given MCP servers (external tools) that vary by composition.
Server definitions live in a **catalogue** at `academy/mcp/`, and compositions
opt in to specific servers via their `manifest.json`.

### Catalogue format (`academy/mcp/`)

Each file in `academy/mcp/` is a named MCP server definition in JSON. The
filename without the `.json` extension is the server name referenced from a
manifest. `install.sh` snapshots `academy/mcp/` into the data volume and the
transport container mounts it read-only at `/mcp`.

Each JSON object conforms to the kiro-cli `mcpServers` entry format: at minimum
a `type` field and either a `url` (HTTP/SSE) or a `command` (stdio) field.

**Stdio server** — `academy/mcp/playwright.json` (shipped as an example, not
wired into any composition by default):

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

**HTTP server with an auth header:**

```json
{
  "type": "streamable-http",
  "url": "http://nexus.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ${NEXUS_API_KEY}"
  }
}
```

An empty catalogue (no JSON files) is valid — no `mcp.json` is written into
crew containers and agents run with only their built-in tools.

### Declaring servers in a composition (`manifest.json → mcpServers`)

A composition's `crews/<name>/manifest.json` gains an optional `mcpServers`
array of catalogue server names:

```json
{
  "agents": "*",
  "skills": "*",
  "steering": "*",
  "mcpServers": ["armory", "nexus"]
}
```

At crew setup, `_copy_agents()` resolves each name against `/mcp/<name>.json`,
substitutes any `${VAR}` references, and writes the resolved configs into
`~/.kiro/mcp.json` inside the crew container. Agents reference these servers
via `@<name>` in their `tools` list.

Behaviour:

- **No `mcpServers` key (or an empty array)** → no `mcp.json` is written.
- **A name with no matching catalogue file** → a warning is logged and that
  entry is skipped; the remaining servers are still written and crew setup
  continues.
- **An entry containing a `headers` field** → `poolable: false` is added
  automatically when written into `mcp.json` (KiroCrew 0.4.0 must not pool
  auth-bearing HTTP servers). The catalogue file does not need to declare it.

### Secret substitution (`${VAR}`)

Any `${VAR}` reference in a catalogue entry's string values is substituted from
the **transport container's environment** at the point `_copy_agents()` writes
the crew's `mcp.json`. This keeps secrets (API keys, tokens) out of committed
files — the catalogue stores `${NEXUS_API_KEY}`, and the real token is injected
at crew setup from the transport environment.

- If the variable **is set**: its value is substituted into the written entry.
- If the variable **is not set**: a warning is logged, the literal `${VAR}`
  string is written, and crew setup continues (the server will auth-fail at
  call time rather than blocking the crew from starting).

Pass secrets into the transport container's environment via `install.sh`
configuration (config file or environment the transport inherits at
`podman run` time), the same mechanism used for other `GA_*` / `KIRO_*`
runtime variables.

### Per-agent servers

Individual agent JSON files in `academy/agents/` may also declare their own
`mcpServers` map for servers specific to that agent regardless of the
composition. kiro-cli resolves the agent's own `mcpServers` entry before the
composition-level `mcp.json`, so a name declared in both is served from the
agent's entry (the `mcp.json` entry is shadowed — no error). An agent may set
`includeMcpJson: false` to opt out of the composition-level `mcp.json`
entirely.
