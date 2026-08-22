# Configuration

Environment variables read by the transport server:

| Variable | Default | Description |
|:---------|:--------|:------------|
| `HOST` | `0.0.0.0` | Interface the MCP and file servers bind to inside the container — `install.sh` only ever publishes `127.0.0.1` on the host, so this is not normally a reason to change it |
| `PORT` | `64057` | MCP server port. The file server always runs on `PORT+1` (`64058` by default) — set via `install.sh --port <port>` |
| `KC_IMAGE` | `localhost/kirocrew-crew:latest` | Crew container image |
| `GA_MAX_CREWS` | `6` | Max concurrent crews |
| `GA_IDLE_TIMEOUT_SECS` | `300` | Seconds idle before stopping container |
| `KC_MODEL_OVERRIDE` | _(unset)_ | When set, overrides the model in all agent JSON files at launch — takes precedence over per-agent defaults. Set via `install.sh --model <model>`. Leave unset to use each agent's own default. |
| `TRANSPORT_DATA_DIR` | `/data` | Registry + data dir |
| `PODMAN_SOCKET` | `/run/user/1000/podman/podman.sock` | Podman socket path — on Linux this is your host uid (`id -u`); on macOS it's the `podman machine` guest's uid (`podman machine ssh -- id -u`), which is often different |
| `GA_PUBLIC_URL` | `http://localhost:<PORT+1>` | Base URL baked into presigned `evac`/`supply` links |
| `GA_FILE_TTL_SECS` | `300` | Seconds a presigned `evac`/`supply` URL stays valid before expiring |
| `KC_GATEWAY_TOKEN_TTL` | `24h` | Duration passed to `kirocrew token --ttl` when setup, restart recovery, or startup reconciliation mints a gateway session token; independent of file URL expiry |
| `GA_FILE_SECRET` | unset (random per process) | HMAC secret signing presigned file URLs — set explicitly if you need presigned URLs to survive a transport restart |
| `GA_API_KEY` | _(unset)_ | Static bearer API key for MCP endpoint authentication. When set, every MCP request must include `Authorization: Bearer <key>`. Unset/empty disables authentication (localhost-trust model). Set via `install.sh --api-key <key>` — persisted to your data directory and reused on later installs automatically; `--api-key ""` clears it. **Never log, print, or embed this value.** See [auth.md](auth.md) for client configuration and rollback. |
| `KIRO_IDENTITY_PROVIDER` | unset (Builder ID fallback) | kiro-cli identity provider URL for crew logins — see [auth.md](auth.md) |
| `KIRO_REGION` | unset | AWS region for that identity provider |
| `KIRO_LICENSE` | unset | kiro-cli license type, if required by the identity provider |

## Config file

`install.sh` accepts a `--config <path>` flag pointing to a shell file that
sets default values for any of the variables below. The file is sourced
before argument parsing, so **command-line flags always override config-file
values**.

### Format

A plain shell file that exports (or simply assigns) variables. Lines
starting with `#` are comments.

### Resolution order

For every settable variable, the effective value is resolved in this order
(first non-empty wins):

1. **Command-line flag** (e.g. `--port 9000`)
2. **Config file** (sourced from `--config <path>`)
3. **Built-in default** (e.g. `PORT=64057`)

### Supported variables

| Variable | Corresponding flag |
|:---------|:-------------------|
| `PORT` | `--port` |
| `KIRO_IDENTITY_PROVIDER` | `--identity-provider` |
| `KIRO_REGION` | `--region` |
| `KIRO_LICENSE` | `--license` |
| `KC_MODEL_OVERRIDE` | `--model` |
| `GA_API_KEY` | `--api-key` |
| `GA_FILE_PUBLIC_URL` | `--file-public-url` |
| `GA_MCP_PUBLIC_URL` | `--mcp-public-url` |

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
GA_FILE_PUBLIC_URL="https://files.academy.example.com"
GA_MCP_PUBLIC_URL="https://mcp.academy.example.com"
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
> | `KC_PUBLIC_URL` | `GA_PUBLIC_URL` |
> | `KC_FILE_PUBLIC_URL` | `GA_FILE_PUBLIC_URL` |
> | `KC_MCP_PUBLIC_URL` | `GA_MCP_PUBLIC_URL` |
>
> Until renamed, deployments that set these variables will silently fall back
> to built-in defaults.
>
>  `your-deployment/ghostship.conf`
> (separate deployment repository) must also be updated:
> `KC_FILE_PUBLIC_URL` → `GA_FILE_PUBLIC_URL`,
> `KC_MCP_PUBLIC_URL` → `GA_MCP_PUBLIC_URL`.

Then override any single value at the command line:

```bash
./install.sh --config ./ghostship.conf --port 8080
# PORT=8080 (flag wins), all other values from config file
```

## Git repository transfer

`launch` creates the crew workspace only; it does not clone a caller-owned
repository. For a history-preserving seed, create a bundle locally, request a
bundle delivery URL, and upload the bytes:

```bash
git bundle create ./project.bundle --all
# Call supply(path="repo", crew_id="<id>", bundle=True), then:
curl -X POST "<delivery_url>" --data-binary @./project.bundle
```

To bring Git history back out, request `evac(path="repo", crew_id="<id>",
bundle=True)`, download the URL, and clone or fetch the resulting bundle:

```bash
curl -fsSL "<evac_url>" -o ./crew.bundle
git clone ./crew.bundle ./crew-repo
git bundle list-heads ./crew.bundle
git fetch ./crew.bundle refs/heads/main:refs/remotes/crew/main
```

`git bundle create ./changes.bundle old-ref..new-ref` creates an incremental
bundle. A range bundle can be fetched only after the receiver has the
`old-ref` prerequisite.

## Deployment security boundary

`install.sh` publishes both the MCP port and the file-transfer port on
`127.0.0.1` only. For remote or shared-network deployments, set `GA_API_KEY`
to require bearer authentication on MCP requests and terminate TLS at a
trusted reverse proxy or encrypted VPN.

The file-transfer port (`PORT+1`) retains its existing HMAC presigned-URL
authorization — it does **not** require the API key. A valid presigned URL
remains a bearer capability until its TTL expires, regardless of whether
`GA_API_KEY` is set. See [auth.md](auth.md) for the full authentication
model.

The Podman socket and the unsandboxed crew runtime are additional deployment
risks not redesigned by API-key authentication.

## Extending the crew image

Edit `crews/kirocrew/Containerfile` and re-run `./install.sh`:

```dockerfile
FROM ghcr.io/kirodotdev/kirocrew:stable
USER root
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    nodejs npm \   # already included
    your-package \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER kirocrew
```

The new image is built at install time. Existing crews continue using the
old image until nuked and re-called-down.
