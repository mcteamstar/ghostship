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
| `KC_BASE_IMAGE` | `ghcr.io/kirodotdev/kirocrew:stable` | Base KiroCrew image used for ephemeral login containers (`/login` flow). Not the crew runtime image — that is `KC_IMAGE`. Override when pulling from a private registry or pinning a specific tag |
| `GA_MAX_CREWS` | `20` | Maximum number of registered crews (running + stopped). Stopped crews cost no memory, so this is primarily a housekeeping limit on how many persistent workspaces you keep around. Raise it freely on unconstrained hosts |
| `GA_MAX_ACTIVE_CREWS` | `3` | Maximum number of simultaneously running (active) crew containers. Enforced when a stopped crew is restarted — if the running count already equals this limit, the restart is refused until another crew idles out. Set to `0` to disable the active limit entirely. At ~2–3 GB per running crew, the default of 3 fits comfortably on an 8 GB host |
| `GA_IDLE_TIMEOUT_SECS` | `300` | Seconds idle before stopping container |
| `KC_MODEL_OVERRIDE` | _(unset)_ | When set, overrides the model in all agent JSON files at launch — takes precedence over per-agent defaults. Set via `install.sh --model <model>`. Leave unset to use each agent's own default. |
| `KC_MODEL_DEFAULT` | _(unset)_ | Global model fallback written as `default_model` in `config.local.json`. Applies when no per-agent model field overrides it. Lower precedence than `KC_MODEL_OVERRIDE` and per-agent model field. Set via `install.sh --model-default <model>`. Full precedence order: `KC_MODEL_OVERRIDE` > per-agent model > `KC_MODEL_DEFAULT` > KiroCrew built-in. Omit to leave KiroCrew's built-in default unchanged. |
| `TRANSPORT_DATA_DIR` | `/data` | Registry + data dir |
| `PODMAN_SOCKET` | `/run/user/1000/podman/podman.sock` | Podman socket path — on Linux this is your host uid (`id -u`); on macOS it's the `podman machine` guest's uid (`podman machine ssh -- id -u`), which is often different |
| `GA_HOST_URL` | `http://localhost:<PORT>` | Base URL baked into presigned `evac`/`supply` links. Replaces the deprecated `GA_MCP_PUBLIC_URL` and `GA_FILE_PUBLIC_URL` variables — set this single var for all externally-reachable URLs |
| `GA_MCP_PUBLIC_URL` | _(unset)_ | **DEPRECATED.** Legacy fallback for `GA_HOST_URL`. If `GA_HOST_URL` is unset and this is set, it is used with a deprecation warning. Migrate to `GA_HOST_URL` |
| `GA_FILE_PUBLIC_URL` | _(unset)_ | **DEPRECATED.** No longer read by the transport — passing it via `-e` to the container has no effect. `install.sh --file-public-url` still accepts this flag and stores the value for backward-compatible config files, but the transport ignores it at runtime. Migrate to `GA_HOST_URL` / `--public-url`. |
| `GA_FILE_TTL_SECS` | `300` | Seconds a presigned `evac`/`supply` URL stays valid before expiring |
| `KC_GATEWAY_TOKEN_TTL` | `24h` | Duration passed to `kirocrew token --ttl` when setup, restart recovery, or startup reconciliation mints a gateway session token; independent of file URL expiry |
| `GA_FILE_SECRET` | unset (random per process) | HMAC secret signing presigned file URLs — set explicitly if you need presigned URLs to survive a transport restart |
| `GA_API_KEY` | _(unset)_ | **DEPRECATED as an env var.** The API key is now delivered via Podman secret (`--secret ga-api-key`, read from `/run/secrets/ga-api-key`). The env var is a deprecated fallback for pre-migration installs — a warning is logged at startup when it is used. Re-run `install.sh` to migrate. Set via `install.sh --api-key <key>` — persisted to your data directory and reused on later installs automatically; `--api-key ""` clears it. **Never log, print, or embed this value.** See [auth.md](auth.md) for client configuration and rollback. |
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

> **Internal constant — not user-settable:**
> `CREW_GATEWAY_PORT` (`5476`) is the port the transport uses to reach each
> crew container's gateway over the internal `ga-net` network. It is
> hardcoded in `server.py` and is **not** configurable via environment
> variable. Changing it would require rebuilding both the crew image and the
> transport. All user-facing ports are controlled by `PORT` (MCP) and
> `PORT+1` (file server) above.

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
| `GA_FILE_PUBLIC_URL` | `--file-public-url` _(deprecated, migrate to `GA_HOST_URL`)_ |
| `GA_MCP_PUBLIC_URL` | `--mcp-public-url` _(deprecated, migrate to `GA_HOST_URL`)_ |

Variables outside this table (e.g. `GA_MAX_CREWS`, `GA_DEDICATED_MACHINE`,
`GA_MACHINE_NAME`, `GA_MIN_FREE_MEM_GB`) are **config-file-only** — they
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

> **Migration note (prior-release operators):** The following environment
> variable names changed in this release. Rename them in your
> `compose.yml`, systemd unit, or config file before upgrading:
>
> | Old name | New name |
> |:---------|:---------|
> | `KC_MAX_CREWS` | `GA_MAX_CREWS` |
> | `KC_IDLE_TIMEOUT_SECS` | `GA_IDLE_TIMEOUT_SECS` |
> | `KC_FILE_SECRET` | `GA_FILE_SECRET` |
> | `KC_FILE_TTL_SECS` | `GA_FILE_TTL_SECS` |
> | `KC_PUBLIC_URL` | `GA_HOST_URL` |
> | `KC_FILE_PUBLIC_URL` | `GA_FILE_PUBLIC_URL` |
> | `KC_MCP_PUBLIC_URL` | `GA_MCP_PUBLIC_URL` |
>
> Until renamed, deployments that set these variables will silently fall back
> to built-in defaults.
>
> **Port unification (trn-32):** The file-transfer routes now share the same
> port as MCP (`PORT`, default 64057). There is no longer a separate file
> server on `PORT+1`. Replace `GA_FILE_PUBLIC_URL` and `GA_MCP_PUBLIC_URL`
> with a single `GA_HOST_URL` pointing at the unified endpoint.
> `GA_MCP_PUBLIC_URL` still works as a deprecated fallback (with a warning);
> `GA_FILE_PUBLIC_URL` is no longer read by the transport.

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
