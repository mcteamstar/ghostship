# Tasks — TRN-286 ga-radar container

## T1 — Create radar/ directory and Containerfile

- Create `radar/Containerfile`: `FROM python:3.12-slim`, install `fastapi uvicorn httpx`, `COPY static/ /app/static/`, `COPY server.py /app/`
- Create `radar/requirements.txt`
- Create `radar/server.py`: FastAPI app with `/`, `/static/*`, `/api/crews`, `/health` routes
  - On startup, read transport secret from `/run/secrets/ga-transport-secret`
  - `/api/crews` fetches from `$TRANSPORT_URL/internal/crews` with `X-Transport-Token: <secret>`
  - `/` serves `/app/static/index.html`
  - `/static/*` serves files from `/app/static/`
  - `/health` returns `{"status": "ok"}`
  - `/api/crews` returns 502 with error JSON if transport is unreachable

## T2 — Extract SPA into radar/static/

- Create `radar/static/index.html` — extract HTML from `LIGHTHOUSE_HTML` in `transport/server.py`
- Create `radar/static/style.css` — extract all CSS from the `<style>` block
- Create `radar/static/app.js` — extract all JS from the `<script>` block
- Update `index.html` to reference `/static/style.css` and `/static/app.js` as external files
- Update `app.js` poll target: `fetch('/api/crews')` — relative path, works behind any proxy prefix
- Verify visual parity with the current heredoc version

## T3 — Add GET /internal/crews to transport

- Add route `GET /internal/crews` to `transport/server.py`
- Handler: call `_build_crews_payload()` (same as current `/api/crews`) and return JSON
- Auth: require `X-Transport-Token` (add to `_TRANSPORT_SECRET_ONLY_ROUTES` in `TransportSecretMiddleware`)
- No bearer key required — this is a portside-internal route

## T4 — Remove Radar from transport

- Delete `LIGHTHOUSE_HTML` constant from `transport/server.py`
- Delete `_handle_radar_get()` from `transport/server.py`
- Delete `_handle_api_crews_get()` from `transport/server.py`
- Remove the `GET /` and `GET /api/crews` route registrations
- Update `BearerAuthMiddleware` `public_routes`: remove `/` and `/api/crews`, add `/internal/crews` to transport-secret-only routes

## T5 — Update Caddy route in install.sh

- In `bin/install.sh`, update `_LIGHTHOUSE_ROUTE`: change `reverse_proxy ga-transport:64057` to `reverse_proxy ga-radar:8080`
- No other changes to the route block (forward_auth, redirect, session gating all stay)

## T6 — Add ga-radar to compose.yml generation in install.sh

- Add `ga-radar` service to the compose template in `bin/install.sh`:
  - image: `localhost/ga-radar:latest`
  - networks: `ga-portside`
  - environment: `TRANSPORT_URL=http://ga-transport:64057`
  - secrets: `ga-transport-secret` (Podman secret, mounted at `/run/secrets/ga-transport-secret`)
  - restart: `unless-stopped`
  - depends_on: `ga-transport`
- Add `podman build -t localhost/ga-radar:latest radar/` to the build sequence in `install.sh` (after `ga-transport` image build)

## T7 — Update tests

- Remove unit tests for `_handle_radar_get` and `_handle_api_crews_get` from `tests/unit/test_fleet.py`
- Add unit tests for `GET /internal/crews`:
  - returns fleet payload with valid `X-Transport-Token`
  - returns 401 with missing or wrong token
- Add `tests/unit/test_radar_server.py`:
  - `/health` returns 200
  - `/api/crews` with mocked transport response returns correct payload
  - `/api/crews` with transport unavailable returns 502
  - `/` returns HTML
  - `/static/style.css` returns CSS content-type
  - `/static/app.js` returns JS content-type

## T8 — Update docs

- Update `docs/architecture.md` networking diagram to show `ga-radar` on `ga-portside`
- Update `docs/radar.md`: note that Radar is now its own container; update the "Auth" section to reflect the new topology
- Update `docs/portal.md` routing diagram to show `GET /` → `ga-radar`
- Update `docs/configuration.md`: add `ga-radar` to the components overview if present

## T9 — Run full test suite and verify

- `bash scripts/run.sh --unit` — all tests pass
- Manual smoke test: `ghostship upgrade` on corsair, verify Radar loads at `http://localhost:64057/`
- Verify `GET /api/crews` returns fleet JSON
- Verify transport no longer serves `GET /` (should 404 or redirect)
