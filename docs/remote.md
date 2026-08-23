# Remote Deployment

Run the Ghostship transport on a remote Linux host and connect MCP clients
from your local machine over the network.

## Prerequisites

- **Linux host** — Ubuntu 22.04+, Fedora 39+, or any distro with Podman ≥ 4.0
  and cgroup v2. See [manual-install.md](manual-install.md) for distro-specific
  notes.
- **Podman rootless** — `podman info` should succeed as a non-root user.
- **Port exposure** — the transport port (default `64057`) serves all routes:
  MCP, REST API, and file transfer. Only one port needs to be exposed.
  (default `64058`) must be reachable from your client. Open them in your
  firewall or security group.
- **API key** — required for any non-loopback deployment. Without it, anyone
  who can reach the port has full MCP access.

## Install

```bash
# On the remote host:
./install.sh --api-key <your-secret-key> \
  --mcp-public-url https://mcp.your-domain.com \
  --file-public-url https://files.your-domain.com
```

### Key flags

| Flag | Purpose |
|:-----|:--------|
| `--api-key <key>` | Require bearer auth on all MCP requests |
| `--mcp-public-url <url>` | Base URL clients use for MCP (set to your reverse proxy's public HTTPS address) |
| `--public-url <url>` | Base URL baked into presigned `evac`/`supply` links (set to the public HTTPS address) |
| `--port <port>` | Override the transport listen port (MCP, REST, and file transfer all on this port) |

### Identity provider (org-licensed)

For IAM Identity Center logins, add `--identity-provider` and `--region`:

```bash
./install.sh --api-key <key> \
  --identity-provider "https://identitycenter.amazonaws.com/ssoins-abc123" \
  --region us-east-1 \
  --license pro \
  --mcp-public-url https://mcp.your-domain.com \
  --file-public-url https://files.your-domain.com
```

Or use a config file (`--config ./ghostship.conf`). See
[configuration.md](configuration.md#config-file).

## TLS termination via reverse proxy

The transport binds plain HTTP inside the container. For production remote
deployments, terminate TLS at a reverse proxy. Example with nginx:

```nginx
# /etc/nginx/sites-available/ghostship-mcp
server {
    listen 443 ssl http2;
    server_name mcp.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/mcp.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:64057;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE / streaming support
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }
}

# /etc/nginx/sites-available/ghostship-files
server {
    listen 443 ssl http2;
    server_name files.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/files.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/files.your-domain.com/privkey.pem;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:64058;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Caddy is simpler if you prefer automatic certificate management:

```
mcp.your-domain.com {
    reverse_proxy localhost:64057
}

files.your-domain.com {
    reverse_proxy localhost:64058
}
```

## MCP client registration (remote host)

Once TLS is in place, register the remote endpoint on your local machine:

**Kiro CLI:**
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

Set `GHOSTSHIP_API_KEY` in your local shell environment.

## First login (remote)

After install, trigger device auth:

```bash
curl -sX POST https://mcp.your-domain.com/login \
  -H "Authorization: Bearer $GHOSTSHIP_API_KEY" | jq
```

Open the returned URL in a browser, complete the sign-in, then poll:

```bash
curl -s https://mcp.your-domain.com/login \
  -H "Authorization: Bearer $GHOSTSHIP_API_KEY" | jq .status
```

Once `complete`, the transport is ready to launch crews.

## Known limitations

- **Single-host only** — no horizontal scaling or high availability. One
  transport process manages all crews on one host. If the host goes down,
  crews are unavailable until it recovers.
- **No HA** — there is no replication, failover, or state sync between
  multiple transport instances. Running two transports against the same
  data directory is unsupported and will corrupt the registry.
- **File transfer: HMAC-only, no TLS natively** — the file transfer routes
  use HMAC presigned URLs for authorization but the transport does not speak
  TLS itself. You must terminate TLS at a reverse proxy (see above) to
  protect file content in transit. Without TLS, presigned URLs and file
  bytes travel in plaintext.
- **No native certificate management** — the transport does not handle
  certificates, ACME, or renewal. Use your reverse proxy or a sidecar
  (certbot, Caddy) for certificate lifecycle.
- **Podman socket security** — the transport requires access to the Podman
  socket, which grants container management privileges for the user. On a
  shared host, restrict access to `DATA_DIR` and the Podman socket to the
  service account running the transport.

## Linger (headless servers)

`install.sh` enables `loginctl enable-linger` automatically. This is
essential for headless or SSH-only servers — without linger, all user
services (including the transport container and Podman socket) stop when
your last SSH session disconnects.

Verify: `loginctl show-user "$(whoami)" --property=Linger` → `Linger=yes`.

See [troubleshooting.md](troubleshooting.md#linger-and-reboot-recovery) for
more details.
