## Why

The transport runs two separate uvicorn bindings: port 8000 for MCP + REST
and port 8001 for the file server. But the file server is just two REST
route handlers (`PUT /files/...` and `GET /files/...`) living in the same
`server.py` as everything else. There is no technical reason for the split —
it's artificial complexity.

Port 8000 already mixes MCP (`/mcp`) and REST (`/login`, `/logout`, `/health`,
`/version`). Files are REST too. Keeping them on a separate port forces:

- Two uvicorn bindings instead of one
- Two Caddy upstreams instead of one
- Two public URL config vars (`GA_MCP_PUBLIC_URL` + `GA_FILE_PUBLIC_URL`)
  that must be kept in sync
- Any TLS or auth middleware must cover both ports
- Remote operators must open/proxy two ports

Collapsing to one port eliminates all of this with no functional change.

## What Changes

- Remove the second uvicorn binding; file routes mount on the main Starlette app
- Replace `GA_MCP_PUBLIC_URL` + `GA_FILE_PUBLIC_URL` with a single `GA_PUBLIC_URL`
- Update presigned URL generation (`supply`, `evac`) to use `GA_PUBLIC_URL`
- Simplify `install.sh` Caddyfile — one upstream, one `reverse_proxy localhost:${PORT}`
- Remove the `FILE_PORT` / `--file-port` concept entirely from `install.sh`
- Update `docs/configuration.md` — remove old vars, add `GA_PUBLIC_URL`
- Migration note: `GA_FILE_PUBLIC_URL` removed; existing installs must set `GA_PUBLIC_URL`

## Capabilities

### Modified Capabilities
- `mcp-server`: file transfer endpoints unified onto the main transport port; `GA_PUBLIC_URL` replaces the split URL config

## Impact

- `transport/server.py` — remove second uvicorn binding, mount file routes on main app
- `install.sh` — remove `FILE_PORT`, simplify Caddyfile to one upstream
- `docs/configuration.md` — update env var table
- `transport/test_transport.py` — update URL assertions that reference port 8001
