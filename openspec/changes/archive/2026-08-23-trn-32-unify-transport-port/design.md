## Context

`server.py` currently starts two uvicorn servers:
- Main app (MCP + REST) on `PORT`
- File app on `PORT+1` (a separate Starlette app with only the file routes)

Both are in the same process, started via `asyncio.gather`. The file routes are
already Starlette `Route` objects — moving them to the main app is trivial.

The presigned URL base is `GA_FILE_PUBLIC_URL` for file routes and
`GA_MCP_PUBLIC_URL` for MCP/REST. These need to collapse to `GA_HOST_URL`.

## Goals / Non-Goals

**Goals:**
- Single port, single Starlette app, single public URL var
- Backward compat: `GA_MCP_PUBLIC_URL` as fallback if `GA_HOST_URL` unset

**Non-Goals:**
- Changing the file route paths (`/files/{crew_id}/{path}`)
- Changing presigned URL signing mechanism (HMAC stays)
- Any auth changes

## Decisions

### 1. Mount file routes on main app

**Choice:** Add the file `Route` objects to the main app's route list. Delete
the second Starlette app and the second `uvicorn.serve()` call.

**Rationale:** One line change — move routes from one list to another. No
middleware or handler code changes needed.

### 2. GA_HOST_URL with GA_MCP_PUBLIC_URL fallback

**Choice:** Read `GA_HOST_URL` first; if absent, fall back to
`GA_MCP_PUBLIC_URL` with a deprecation warning; if neither, default to
`http://localhost:{PORT}`.

**Rationale:** Existing Academy deployments set `GA_MCP_PUBLIC_URL` in
`ghostship.conf`. A fallback avoids a hard break on redeploy.

### 3. Remove FILE_PORT from install.sh

**Choice:** Delete the `FILE_PORT=$((MCP_PORT + 1))` line and the second
`-p FILE_PORT:FILE_PORT` port mapping from the `podman run` invocation.
Simplify the Caddyfile to a single `reverse_proxy localhost:${MCP_PORT}` catch-all.

**Rationale:** The Caddy config is already catch-all since the TRN-28 simplification — this just removes the now-unused file port mapping from the container invocation.

## Migration Plan

1. `install.sh` rerun creates the container without the second port mapping
2. `ghostship.conf` migration: rename `GA_MCP_PUBLIC_URL` → `GA_HOST_URL`
   (fallback handles the transition automatically if not renamed immediately)
3. No data migration — presigned URLs are short-lived tokens
