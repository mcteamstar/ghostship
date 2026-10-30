# Design — TRN-286 ga-radar container

## Architecture

```
                    ga-portside network
                    ┌─────────────────────────────────────────┐
Browser ──► ga-portal ──► ga-radar ──► ga-transport      │
                    │         :8080              :64057        │
                    │                                ↓         │
                    │                        ga-starboard      │
                    │                        gs-* crews        │
                    └─────────────────────────────────────────┘

MCP client ──► ga-portal ──► ga-transport
```

## New container: ga-radar

**Image:** `localhost/ga-radar:latest` — built at install time from `radar/Containerfile`

**Runtime:** Python + FastAPI (same stack as transport, minimal deps)

**Network:** `ga-portside` only — no `ga-starboard` membership

**Ports:** `8080` internal (not published to host)

**Mounts:**
- No bind mounts — static files (`index.html`, `style.css`, `app.js`) are baked into the image via `COPY` in the Containerfile. `ghostship upgrade` rebuilds the image to pick up changes.
- No data volume needed

**Responsibilities:**
- `GET /` — serve `index.html`
- `GET /static/*` — serve CSS/JS
- `GET /api/crews` — fetch from `http://ga-transport:64057/internal/crews` with `X-Transport-Token` header, return to browser
- Health: `GET /health` → 200

## Transport changes

- Remove `_handle_radar_get()` and `LIGHTHOUSE_HTML` from `server.py`
- Remove the public `GET /api/crews` route from `server.py`
- Add `GET /internal/crews` — same payload as current `/api/crews`, bound to portside callers only (validated by `X-Transport-Token` from Caddy, or by source IP check since portside is a trusted network)
- `BearerAuthMiddleware`: `/internal/crews` added to `_TRANSPORT_SECRET_ONLY_ROUTES` (requires `X-Transport-Token`, no bearer key)

## Caddy changes (install.sh)

Update `_LIGHTHOUSE_ROUTE` in `bin/install.sh`:

```
# Before: reverse_proxy to ga-transport
# After: reverse_proxy to ga-radar:8080
```

The `forward_auth` chain, redirect-on-401, and session gating are unchanged — those stay at the portal layer.

## File layout

```
radar/
├── Containerfile          # FROM python:3.12-slim, installs fastapi+uvicorn
├── requirements.txt       # fastapi, uvicorn, httpx
├── server.py              # FastAPI app: serves static + proxies /api/crews
└── static/
    ├── index.html         # SPA (extracted from LIGHTHOUSE_HTML heredoc)
    ├── style.css          # All styles (extracted from <style> block)
    └── app.js             # All JS (extracted from <script> block)
```

## Internal API contract

Radar calls transport at:
```
GET http://ga-transport:64057/internal/crews
X-Transport-Token: <shared secret>
```

Response: identical to current `/api/crews` response shape. No change to the payload schema.

## Compose changes

`install.sh` generates `compose.yml` — add `ga-radar` service:

```yaml
ga-radar:
  image: localhost/ga-radar:latest
  networks:
    - ga-portside
  environment:
    - TRANSPORT_URL=http://ga-transport:64057
  secrets:
    - ga-transport-secret
  restart: unless-stopped
  depends_on:
    - ga-transport
```

`ga-radar` reads the transport secret from `/run/secrets/ga-transport-secret` at startup (same pattern as `ga-transport`). No plaintext secret in the environment.

## Build changes

`install.sh` builds `ga-radar` image after `ga-transport`:
```bash
podman build -t localhost/ga-radar:latest radar/
```

## Security

- `ga-radar` is on `ga-portside` — it can reach `ga-transport` but not crew containers
- The `X-Transport-Token` authenticates radar → transport calls (same mechanism Caddy uses)
- Browser never reaches `ga-transport` for UI traffic — all UI goes through `ga-radar`
- No secrets stored in the radar container (token passed via environment from compose)

## Migration

Existing installs: `ghostship upgrade` rebuilds images and restarts. The `ga-radar` container is new — compose creates it. The old `LIGHTHOUSE_HTML` route on transport returns 404 after upgrade (Caddy now routes to radar before the request reaches transport). No data migration needed.
